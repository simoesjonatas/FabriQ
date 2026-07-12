import logging

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from apps.accounts.mixins import AcessoModuloMixin
from apps.accounts.perfis import usuario_acessa_modulo
from apps.core import formatos
from apps.core.views import SalvarComUsuarioMixin
from apps.estoque.models import LocalEstoque, Movimentacao, TipoMovimentacao

from .forms import (
    AnexoRecebimentoFormSet,
    ItemRecebimentoFormSet,
    RecebimentoForm,
    obter_ou_criar_lote,
)
from .models import (
    DecisaoQuarentena,
    ItemRecebimento,
    Recebimento,
    StatusQuarentena,
    local_quarentena,
)

logger = logging.getLogger("fabriq")

MODULO_RECEBIMENTO = "recebimento"
MODULO_QUARENTENA = "quarentena"


class RecebimentoListView(AcessoModuloMixin, ListView):
    modulo = MODULO_RECEBIMENTO
    model = Recebimento
    template_name = "recebimento/lista.html"
    context_object_name = "recebimentos"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            Recebimento.objects.select_related("fornecedor", "criado_por")
            .annotate(
                total_itens=Count("itens"),
                pendentes=Count(
                    "itens",
                    filter=Q(
                        itens__status__in=[
                            StatusQuarentena.EM_QUARENTENA,
                            StatusQuarentena.BLOQUEADO,
                        ]
                    ),
                ),
            )
        )

        filtros = self.request.GET
        termo = filtros.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                Q(nota_fiscal__icontains=termo)
                | Q(fornecedor__razao_social__icontains=termo)
                | Q(fornecedor__nome_fantasia__icontains=termo)
            )
        if filtros.get("de"):
            queryset = queryset.filter(data_recebimento__gte=filtros["de"])
        if filtros.get("ate"):
            queryset = queryset.filter(data_recebimento__lte=filtros["ate"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.request.GET
        context.update(
            {
                "filtro_q": filtros.get("q", "").strip(),
                "filtro_de": filtros.get("de", ""),
                "filtro_ate": filtros.get("ate", ""),
            }
        )
        return context


class RecebimentoCriarView(AcessoModuloMixin, SalvarComUsuarioMixin, CreateView):
    modulo = MODULO_RECEBIMENTO
    model = Recebimento
    form_class = RecebimentoForm
    template_name = "recebimento/form.html"

    def get_formsets(self, instance=None):
        kwargs = {"instance": instance or getattr(self, "object", None)}
        if self.request.method in {"POST", "PUT"}:
            kwargs["data"] = self.request.POST
        anexos_kwargs = dict(kwargs)
        if self.request.method in {"POST", "PUT"}:
            anexos_kwargs["files"] = self.request.FILES
        return (
            ItemRecebimentoFormSet(prefix="itens", **kwargs),
            AnexoRecebimentoFormSet(prefix="anexos", **anexos_kwargs),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "itens_formset" not in kwargs or "anexos_formset" not in kwargs:
            itens_formset, anexos_formset = self.get_formsets()
            context.setdefault("itens_formset", itens_formset)
            context.setdefault("anexos_formset", anexos_formset)
        else:
            context["itens_formset"] = kwargs["itens_formset"]
            context["anexos_formset"] = kwargs["anexos_formset"]
        return context

    def form_valid(self, form):
        form.instance.criado_por = self.request.user
        form.instance.atualizado_por = self.request.user
        self.object = form.save(commit=False)

        itens_formset, anexos_formset = self.get_formsets(instance=self.object)
        if not itens_formset.is_valid() or not anexos_formset.is_valid():
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    itens_formset=itens_formset,
                    anexos_formset=anexos_formset,
                )
            )

        with transaction.atomic():
            self.object.save()
            quarentena = local_quarentena()

            for item_form in itens_formset.forms:
                if not item_form.cleaned_data or item_form.cleaned_data.get("DELETE"):
                    continue
                item_recebido = item_form.save(commit=False)
                item_recebido.recebimento = self.object
                item_recebido.lote = obter_ou_criar_lote(
                    item_recebido.item,
                    item_form.cleaned_data["lote_codigo"],
                    item_form.cleaned_data.get("lote_validade"),
                    self.request.user,
                )
                item_recebido.save()

                movimentacao = Movimentacao(
                    tipo=TipoMovimentacao.ENTRADA,
                    lote=item_recebido.lote,
                    quantidade=item_recebido.quantidade,
                    local_destino=quarentena,
                    motivo=f"Recebimento {self.object.numero}",
                    documento=f"NF {self.object.nota_fiscal}",
                    criado_por=self.request.user,
                    atualizado_por=self.request.user,
                )
                setattr(
                    movimentacao,
                    self._campo_item(item_recebido),
                    item_recebido.item,
                )
                movimentacao.full_clean()
                movimentacao.save()

            for anexo_form in anexos_formset.forms:
                if not anexo_form.cleaned_data or anexo_form.cleaned_data.get("DELETE"):
                    continue
                if not anexo_form.cleaned_data.get("arquivo"):
                    continue
                anexo = anexo_form.save(commit=False)
                anexo.recebimento = self.object
                anexo.criado_por = self.request.user
                anexo.atualizado_por = self.request.user
                anexo.save()

        messages.success(
            self.request,
            f"Recebimento {self.object.numero} registrado — itens em quarentena.",
        )
        logger.info(
            "Recebimento %s registrado por %s", self.object.numero, self.request.user
        )
        return redirect(self.object.get_absolute_url())

    @staticmethod
    def _campo_item(item_recebido) -> str:
        if item_recebido.produto_id:
            return "produto"
        if item_recebido.materia_prima_id:
            return "materia_prima"
        return "embalagem"


class RecebimentoDetalheView(AcessoModuloMixin, DetailView):
    modulo = MODULO_RECEBIMENTO
    model = Recebimento
    template_name = "recebimento/detalhe.html"
    context_object_name = "recebimento"

    def get_queryset(self):
        return Recebimento.objects.select_related(
            "fornecedor", "criado_por"
        ).prefetch_related(
            "itens__produto",
            "itens__materia_prima",
            "itens__embalagem",
            "itens__lote",
            "itens__decisoes__responsavel",
            "itens__decisoes__local_destino",
            "anexos",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["locais_liberacao"] = LocalEstoque.objects.filter(ativo=True).exclude(
            pk=local_quarentena().pk
        )
        context["pode_decidir"] = usuario_acessa_modulo(
            self.request.user, MODULO_QUARENTENA
        )
        return context


class QuarentenaFilaView(AcessoModuloMixin, ListView):
    modulo = MODULO_QUARENTENA
    model = ItemRecebimento
    template_name = "recebimento/quarentena.html"
    context_object_name = "itens"
    paginate_by = 30

    def get_queryset(self):
        queryset = (
            ItemRecebimento.objects.filter(
                status__in=[StatusQuarentena.EM_QUARENTENA, StatusQuarentena.BLOQUEADO]
            )
            .select_related(
                "recebimento__fornecedor",
                "produto",
                "materia_prima",
                "embalagem",
                "lote",
            )
            .order_by("recebimento__data_recebimento", "id")
        )
        termo = self.request.GET.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                Q(lote__codigo__icontains=termo)
                | Q(recebimento__nota_fiscal__icontains=termo)
                | Q(recebimento__fornecedor__razao_social__icontains=termo)
                | Q(produto__nome__icontains=termo)
                | Q(materia_prima__nome__icontains=termo)
                | Q(embalagem__nome__icontains=termo)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filtro_q"] = self.request.GET.get("q", "").strip()
        context["locais_liberacao"] = LocalEstoque.objects.filter(ativo=True).exclude(
            pk=local_quarentena().pk
        )
        return context


class DecidirItemView(AcessoModuloMixin, View):
    modulo = MODULO_QUARENTENA

    def post(self, request, pk):
        item = get_object_or_404(
            ItemRecebimento.objects.select_related("recebimento", "lote"), pk=pk
        )
        decisao = request.POST.get("decisao", "")
        observacoes = request.POST.get("observacoes", "").strip()
        local_destino_id = request.POST.get("local_destino", "")
        proxima = request.POST.get("proxima") or item.recebimento.get_absolute_url()

        rotulos = dict(StatusQuarentena.choices)
        if decisao not in dict(item.decisoes_possiveis):
            messages.error(
                request,
                f"O item está “{item.get_status_display()}” e não aceita a "
                f"decisão “{rotulos.get(decisao, decisao)}”.",
            )
            return redirect(proxima)

        if decisao in {StatusQuarentena.REPROVADO, StatusQuarentena.BLOQUEADO} and not observacoes:
            messages.error(request, "Informe as observações da decisão.")
            return redirect(proxima)

        local_destino = None
        if decisao == StatusQuarentena.LIBERADO:
            if not local_destino_id.isdigit():
                messages.error(request, "Escolha o local de destino da liberação.")
                return redirect(proxima)
            local_destino = get_object_or_404(
                LocalEstoque, pk=local_destino_id, ativo=True
            )

        with transaction.atomic():
            if decisao == StatusQuarentena.LIBERADO:
                movimentacao = Movimentacao(
                    tipo=TipoMovimentacao.TRANSFERENCIA,
                    lote=item.lote,
                    quantidade=item.quantidade,
                    local_origem=local_quarentena(),
                    local_destino=local_destino,
                    motivo=f"Liberação da quarentena — {item.recebimento.numero}",
                    documento=f"NF {item.recebimento.nota_fiscal}",
                    criado_por=request.user,
                    atualizado_por=request.user,
                )
                setattr(
                    movimentacao,
                    RecebimentoCriarView._campo_item(item),
                    item.item,
                )
                movimentacao.full_clean()
                movimentacao.save()

            item.status = decisao
            item.save()

            DecisaoQuarentena.objects.create(
                item=item,
                decisao=decisao,
                responsavel=request.user,
                observacoes=observacoes,
                local_destino=local_destino,
            )

        quantidade = formatos.quantidade_com_unidade(
            item.quantidade, item.item.get_unidade_display()
        )
        messages.success(
            request,
            f"{rotulos[decisao]}: {item.item} · lote {item.lote.codigo} "
            f"({quantidade}).",
        )
        logger.info(
            "Quarentena: item %s -> %s por %s", item.pk, decisao, request.user
        )
        return redirect(proxima)
