import logging

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.accounts.mixins import AcessoModuloMixin
from apps.auditoria import servicos as auditoria
from apps.auditoria.models import AcaoAuditoria
from apps.auditoria.views import TrilhaAuditoriaMixin
from apps.core import formatos
from apps.core.views import SalvarComUsuarioMixin
from apps.pedidos.models import HistoricoPedido

from .forms import ComponenteFormSet, FormulaForm, OrdemProducaoForm
from .models import (
    ComponenteFormula,
    Formula,
    HistoricoOP,
    OrdemProducao,
    SnapshotFormulaOP,
    StatusFormula,
    StatusOP,
)

logger = logging.getLogger("fabriq")

MODULO = "ordens"


class OrdemListView(AcessoModuloMixin, ListView):
    modulo = MODULO
    model = OrdemProducao
    template_name = "ordens/lista.html"
    context_object_name = "ordens"
    paginate_by = 20

    def get_queryset(self):
        queryset = OrdemProducao.objects.select_related(
            "item_pedido__pedido__cliente",
            "item_pedido__produto",
            "formula",
            "equipamento",
            "operador",
        )

        filtros = self.request.GET
        if filtros.get("status") in StatusOP.values:
            queryset = queryset.filter(status=filtros["status"])
        if filtros.get("de"):
            queryset = queryset.filter(data_programada__gte=filtros["de"])
        if filtros.get("ate"):
            queryset = queryset.filter(data_programada__lte=filtros["ate"])

        termo = filtros.get("q", "").strip()
        if termo:
            filtro = Q(item_pedido__produto__nome__icontains=termo) | Q(
                item_pedido__produto__codigo__icontains=termo
            ) | Q(item_pedido__pedido__cliente__razao_social__icontains=termo)
            somente_digitos = "".join(c for c in termo if c.isdigit())
            if somente_digitos:
                filtro |= Q(pk=int(somente_digitos))
            queryset = queryset.filter(filtro)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.request.GET
        context.update(
            {
                "status_choices": StatusOP.choices,
                "filtro_status": filtros.get("status", ""),
                "filtro_q": filtros.get("q", "").strip(),
                "filtro_de": filtros.get("de", ""),
                "filtro_ate": filtros.get("ate", ""),
            }
        )
        return context


class OrdemFormBase(AcessoModuloMixin, SalvarComUsuarioMixin):
    modulo = MODULO
    model = OrdemProducao
    form_class = OrdemProducaoForm
    template_name = "ordens/form.html"

    def form_valid(self, form):
        criando = form.instance.pk is None
        with transaction.atomic():
            response = super().form_valid(form)
            self.object.gerar_materiais()

            if criando:
                HistoricoOP.registrar(
                    self.object,
                    self.request.user,
                    f"OP emitida para {self.object.produto} "
                    f"({formatos.quantidade(self.object.quantidade)} "
                    f"{self.object.produto.get_unidade_display().lower()})",
                )
                HistoricoPedido.registrar(
                    pedido=self.object.pedido,
                    usuario=self.request.user,
                    descricao=(
                        f"Ordem de produção {self.object.numero} emitida "
                        f"para o item {self.object.produto.codigo}"
                    ),
                )
            else:
                HistoricoOP.registrar(
                    self.object,
                    self.request.user,
                    "OP alterada: " + (", ".join(form.changed_data) or "materiais"),
                )

        messages.success(
            self.request,
            f"Ordem {self.object.numero} salva — confira o checklist de liberação.",
        )
        logger.info(
            "OP %s %s por %s",
            self.object.numero,
            "emitida" if criando else "alterada",
            self.request.user,
        )
        return response


class OrdemCriarView(OrdemFormBase, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        item_id = self.request.GET.get("item", "")
        if item_id.isdigit():
            initial["item_pedido"] = item_id
        return initial


class OrdemEditarView(OrdemFormBase, UpdateView):
    def dispatch(self, request, *args, **kwargs):
        ordem = self.get_object()
        if request.user.is_authenticated and not ordem.editavel:
            messages.warning(
                request,
                f"A OP {ordem.numero} está “{ordem.get_status_display()}” "
                "e não pode mais ser editada.",
            )
            return redirect(ordem.get_absolute_url())
        return super().dispatch(request, *args, **kwargs)


class OrdemDetalheView(AcessoModuloMixin, TrilhaAuditoriaMixin, DetailView):
    modulo = MODULO
    model = OrdemProducao
    template_name = "ordens/detalhe.html"
    context_object_name = "ordem"

    def get_queryset(self):
        return OrdemProducao.objects.select_related(
            "item_pedido__pedido__cliente",
            "item_pedido__produto",
            "formula",
            "equipamento",
            "operador",
            "criado_por",
            "liberado_por",
            "lote_produto",
            "snapshot_formula",
        ).prefetch_related(
            "materiais__materia_prima",
            "materiais__embalagem",
            "materiais__consumos__lote",
            "materiais__consumos__local",
            "historico__usuario",
            "atividades__funcionario",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["condicoes"] = self.object.condicoes_liberacao()
        context["pode_liberar"] = self.object.editavel and all(
            condicao["ok"] for condicao in context["condicoes"]
        )
        return context


class OrdemLiberarView(AcessoModuloMixin, View):
    modulo = MODULO

    def post(self, request, pk):
        ordem = get_object_or_404(OrdemProducao, pk=pk)

        if not ordem.editavel:
            messages.error(
                request, f"A OP {ordem.numero} não está mais em rascunho."
            )
            return redirect(ordem.get_absolute_url())

        condicoes = ordem.condicoes_liberacao()
        pendentes = [c for c in condicoes if not c["ok"]]
        if pendentes:
            messages.error(
                request,
                "A OP não pode ser liberada. Pendências: "
                + "; ".join(c["rotulo"] for c in pendentes)
                + ".",
            )
            return redirect(ordem.get_absolute_url())

        from apps.producao.models import AtividadeOP, TipoAtividadeOP

        with transaction.atomic():
            ordem.status = StatusOP.LIBERADA
            ordem.liberado_por = request.user
            ordem.liberado_em = timezone.now()
            ordem.atualizado_por = request.user
            ordem.save()

            lote = ordem.reservar_lote_produto(request.user)
            snapshot = SnapshotFormulaOP.congelar(ordem, request.user)

            AtividadeOP.registrar(
                ordem,
                TipoAtividadeOP.LIBERACAO,
                request.user,
                "OP liberada para produção",
            )
            AtividadeOP.registrar(
                ordem,
                TipoAtividadeOP.ATRIBUICAO_LOTE,
                request.user,
                f"Lote interno {lote.codigo} reservado",
            )
            auditoria.registrar_evento(
                ordem,
                AcaoAuditoria.LIBERACAO,
                request.user,
                valor_novo=(
                    "OP liberada para produção — fórmula "
                    f"{snapshot.nome} v{snapshot.versao} congelada"
                ),
            )
            HistoricoOP.registrar(
                ordem,
                request.user,
                f"OP liberada para produção — lote interno {lote.codigo} "
                f"reservado e fórmula {snapshot.nome} v{snapshot.versao} congelada",
            )
            HistoricoPedido.registrar(
                pedido=ordem.pedido,
                usuario=request.user,
                descricao=f"Ordem de produção {ordem.numero} liberada",
            )

        messages.success(
            request,
            f"OP {ordem.numero} liberada para produção — "
            f"lote interno {lote.codigo} reservado.",
        )
        logger.info("OP %s liberada por %s", ordem.numero, request.user)
        return redirect(ordem.get_absolute_url())


class OrdemCancelarView(AcessoModuloMixin, View):
    modulo = MODULO

    def post(self, request, pk):
        ordem = get_object_or_404(OrdemProducao, pk=pk)
        motivo = request.POST.get("motivo", "").strip()

        if not ordem.pode_cancelar:
            messages.error(
                request, f"A OP {ordem.numero} não pode mais ser cancelada."
            )
            return redirect(ordem.get_absolute_url())

        if not motivo:
            messages.error(request, "Informe o motivo do cancelamento.")
            return redirect(ordem.get_absolute_url())

        with transaction.atomic():
            ordem.status = StatusOP.CANCELADA
            ordem.motivo_cancelamento = motivo
            ordem.atualizado_por = request.user
            ordem._justificativa_auditoria = motivo
            ordem.save()

            auditoria.registrar_evento(
                ordem,
                AcaoAuditoria.CANCELAMENTO,
                request.user,
                justificativa=motivo,
            )
            HistoricoOP.registrar(
                ordem, request.user, f"OP cancelada. Motivo: {motivo}"
            )
            HistoricoPedido.registrar(
                pedido=ordem.pedido,
                usuario=request.user,
                descricao=f"Ordem de produção {ordem.numero} cancelada. Motivo: {motivo}",
            )

        messages.success(request, f"OP {ordem.numero} cancelada.")
        logger.info("OP %s cancelada por %s", ordem.numero, request.user)
        return redirect(ordem.get_absolute_url())


class OrdemImprimirView(AcessoModuloMixin, DetailView):
    modulo = MODULO
    model = OrdemProducao
    template_name = "ordens/imprimir.html"
    context_object_name = "ordem"

    def get_queryset(self):
        return OrdemDetalheView.get_queryset(self)


# Fórmulas


class FormulaListView(AcessoModuloMixin, ListView):
    modulo = MODULO
    model = Formula
    template_name = "ordens/formula_lista.html"
    context_object_name = "formulas"
    paginate_by = 20

    def get_queryset(self):
        queryset = Formula.objects.select_related("produto").prefetch_related(
            "componentes__materia_prima", "componentes__embalagem"
        )
        termo = self.request.GET.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                Q(nome__icontains=termo)
                | Q(produto__nome__icontains=termo)
                | Q(produto__codigo__icontains=termo)
            )
        status = self.request.GET.get("status", "")
        if status == "ativos":
            queryset = queryset.filter(ativo=True)
        elif status == "inativos":
            queryset = queryset.filter(ativo=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["termo"] = self.request.GET.get("q", "").strip()
        context["status"] = self.request.GET.get("status", "")
        return context


class FormulaFormBase(AcessoModuloMixin, SalvarComUsuarioMixin):
    modulo = MODULO
    model = Formula
    form_class = FormulaForm
    template_name = "ordens/formula_form.html"
    success_url = reverse_lazy("ordens:formula_lista")

    def get_formset(self, instance=None):
        kwargs = {
            "instance": instance if instance is not None else getattr(self, "object", None),
            "prefix": "componentes",
        }
        if self.request.method in {"POST", "PUT"}:
            kwargs["data"] = self.request.POST
        return ComponenteFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["componentes_formset"] = (
            kwargs.get("componentes_formset") or self.get_formset()
        )
        return context

    def form_valid(self, form):
        criando = form.instance.pk is None
        if criando:
            form.instance.criado_por = self.request.user
        form.instance.atualizado_por = self.request.user
        self.object = form.save(commit=False)

        formset = self.get_formset(instance=self.object)
        if not formset.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form, componentes_formset=formset)
            )

        # Fórmula com OP emitida nunca é alterada no lugar: a edição gera
        # uma NOVA VERSÃO e a atual vira histórica (PDF 2.4/4.2).
        versionar = (
            not criando
            and (form.has_changed() or formset.has_changed())
            and OrdemProducao.objects.filter(formula_id=form.instance.pk).exists()
        )

        if versionar and not (
            form.cleaned_data.get("justificativa_alteracao") or ""
        ).strip():
            # Alterações só nos componentes não passam pelo mixin de
            # justificativa — mas toda nova versão precisa de motivo.
            form.add_error(
                "justificativa_alteracao",
                "Informe a justificativa para gerar a nova versão da fórmula.",
            )
            return self.render_to_response(
                self.get_context_data(form=form, componentes_formset=formset)
            )

        if versionar:
            with transaction.atomic():
                self.object = self._criar_nova_versao(form, formset)
            messages.success(
                self.request,
                f"A fórmula tinha OP emitida: criada a versão "
                f"v{self.object.versao} (vigente) — a v{self.object.versao - 1} "
                "ficou histórica e as OPs existentes não mudam.",
            )
            logger.info(
                "Fórmula %s versionada para v%s por %s",
                self.object.nome,
                self.object.versao,
                self.request.user,
            )
        else:
            self.object.aprovada_por = self.request.user
            self.object.aprovada_em = timezone.now()
            with transaction.atomic():
                self.object.save()
                formset.save()
            messages.success(self.request, f"Fórmula “{self.object}” salva.")
        return redirect("ordens:formula_lista")

    def _criar_nova_versao(self, form, formset) -> Formula:
        """Congela a versão atual como histórica e grava a nova como vigente."""
        usuario = self.request.user
        justificativa = (
            form.cleaned_data.get("justificativa_alteracao") or ""
        ).strip()

        anterior = Formula.objects.get(pk=form.instance.pk)
        anterior.status = StatusFormula.HISTORICA
        anterior.atualizado_por = usuario
        anterior._justificativa_auditoria = justificativa
        anterior.save()

        nova = Formula(
            produto=anterior.produto,
            nome=form.cleaned_data["nome"],
            versao=anterior.versao + 1,
            rendimento=form.cleaned_data["rendimento"],
            observacoes=form.cleaned_data["observacoes"],
            ativo=form.cleaned_data["ativo"],
            aprovada_por=usuario,
            aprovada_em=timezone.now(),
            criado_por=usuario,
            atualizado_por=usuario,
        )
        nova._justificativa_auditoria = justificativa
        nova.save()

        for componente_form in formset.forms:
            dados = componente_form.cleaned_data
            if not dados or dados.get("DELETE"):
                continue
            ComponenteFormula.objects.create(
                formula=nova,
                materia_prima=componente_form.instance.materia_prima,
                embalagem=componente_form.instance.embalagem,
                quantidade=dados["quantidade"],
            )

        auditoria.registrar_evento(
            anterior,
            AcaoAuditoria.ALTERACAO,
            usuario,
            justificativa=justificativa,
            campo="versão",
            valor_anterior=f"v{anterior.versao} vigente",
            valor_novo=f"substituída pela v{nova.versao}",
        )
        return nova


class FormulaCriarView(FormulaFormBase, CreateView):
    pass


class FormulaEditarView(TrilhaAuditoriaMixin, FormulaFormBase, UpdateView):
    def dispatch(self, request, *args, **kwargs):
        formula = self.get_object()
        if request.user.is_authenticated and not formula.vigente:
            messages.warning(
                request,
                f"A fórmula {formula} é histórica e não pode ser editada — "
                "altere a versão vigente.",
            )
            return redirect("ordens:formula_lista")
        return super().dispatch(request, *args, **kwargs)
