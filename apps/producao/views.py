import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts.mixins import AcessoModuloMixin
from apps.accounts.perfis import pode_autorizar_excecao
from apps.estoque.models import LocalEstoque, Lote
from apps.ordens.models import OrdemProducao, StatusOP

from .forms import (
    AtividadeOPForm,
    ConcluirProducaoForm,
    FotoProducaoForm,
    OcorrenciaForm,
    ParadaForm,
)
from .models import (
    AtividadeOP,
    ConsumoMaterialOP,
    ExecucaoOP,
    Parada,
    apontar_consumos,
    posicoes_para_apontamento,
    sugerir_consumos_fefo,
)

logger = logging.getLogger("fabriq")

MODULO = "producao"

# OPs que interessam à produção
STATUS_NA_PRODUCAO = [StatusOP.LIBERADA, StatusOP.EM_PRODUCAO, StatusOP.CONCLUIDA]


class FilaView(AcessoModuloMixin, ListView):
    modulo = MODULO
    model = OrdemProducao
    template_name = "producao/fila.html"
    context_object_name = "ordens"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            OrdemProducao.objects.filter(status__in=STATUS_NA_PRODUCAO)
            .select_related(
                "item_pedido__pedido__cliente",
                "item_pedido__produto",
                "equipamento",
                "operador",
                "execucao",
            )
            .order_by("data_programada", "id")
        )

        filtros = self.request.GET
        status = filtros.get("status", "")
        if status in dict(StatusOP.choices):
            queryset = queryset.filter(status=status)

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
        context["status_choices"] = [
            (valor, rotulo)
            for valor, rotulo in StatusOP.choices
            if valor in STATUS_NA_PRODUCAO
        ]
        context["filtro_status"] = filtros.get("status", "")
        context["filtro_q"] = filtros.get("q", "").strip()
        return context


class PainelView(AcessoModuloMixin, DetailView):
    modulo = MODULO
    model = OrdemProducao
    template_name = "producao/painel.html"
    context_object_name = "ordem"

    def get_queryset(self):
        return OrdemProducao.objects.select_related(
            "item_pedido__pedido__cliente",
            "item_pedido__produto",
            "formula",
            "equipamento",
            "operador",
            "lote_produto",
        ).prefetch_related(
            "materiais__materia_prima",
            "materiais__embalagem",
            "materiais__consumos__lote",
            "materiais__consumos__local",
            "atividades__funcionario",
            "execucao__paradas__registrado_por",
            "execucao__ocorrencias__registrado_por",
            "execucao__fotos",
        )

    def get_context_data(self, **kwargs):
        from apps.recebimento.models import local_quarentena

        context = super().get_context_data(**kwargs)
        context["execucao"] = getattr(self.object, "execucao", None)
        context["pode_iniciar"] = self.object.status == StatusOP.LIBERADA
        context["em_producao"] = self.object.status == StatusOP.EM_PRODUCAO
        context["parada_form"] = ParadaForm()
        context["ocorrencia_form"] = OcorrenciaForm()
        context["foto_form"] = FotoProducaoForm()
        context["atividade_form"] = AtividadeOPForm()
        context["concluir_form"] = ConcluirProducaoForm(
            excluir_local=local_quarentena()
        )
        context["materiais_sem_apontamento"] = [
            material.item.codigo
            for material in self.object.materiais.all()
            if not material.consumos.all()
        ]
        return context


class IniciarView(AcessoModuloMixin, View):
    modulo = MODULO

    def post(self, request, pk):
        ordem = get_object_or_404(OrdemProducao, pk=pk)
        try:
            with transaction.atomic():
                ExecucaoOP.iniciar(ordem, request.user)
        except ValidationError as erro:
            messages.error(request, "; ".join(erro.messages))
        else:
            messages.success(request, f"Produção da OP {ordem.numero} iniciada.")
            logger.info("Produção %s iniciada por %s", ordem.numero, request.user)
        return redirect("producao:painel", pk=ordem.pk)


class _ExecucaoActionView(AcessoModuloMixin, View):
    """Base para ações que exigem uma execução em andamento."""

    modulo = MODULO

    def get_execucao_em_andamento(self, request, pk):
        ordem = get_object_or_404(OrdemProducao, pk=pk)
        execucao = getattr(ordem, "execucao", None)
        if execucao is None or ordem.status != StatusOP.EM_PRODUCAO:
            messages.error(request, "A produção não está em andamento.")
            return None, ordem
        return execucao, ordem


class AbrirParadaView(_ExecucaoActionView):
    def post(self, request, pk):
        execucao, ordem = self.get_execucao_em_andamento(request, pk)
        if execucao is None:
            return redirect("producao:painel", pk=ordem.pk)

        if execucao.tem_parada_aberta:
            messages.warning(request, "Já existe uma parada em aberto.")
            return redirect("producao:painel", pk=ordem.pk)

        form = ParadaForm(request.POST)
        if form.is_valid():
            Parada.objects.create(
                execucao=execucao,
                motivo=form.cleaned_data["motivo"],
                observacoes=form.cleaned_data["observacoes"],
                registrado_por=request.user,
            )
            messages.success(request, "Parada aberta.")
        else:
            messages.error(request, "Selecione um motivo válido para a parada.")
        return redirect("producao:painel", pk=ordem.pk)


class EncerrarParadaView(_ExecucaoActionView):
    def post(self, request, pk):
        execucao, ordem = self.get_execucao_em_andamento(request, pk)
        if execucao is None:
            return redirect("producao:painel", pk=ordem.pk)

        parada = execucao.paradas.filter(fim__isnull=True).first()
        if parada is None:
            messages.warning(request, "Nenhuma parada em aberto.")
        else:
            parada.fim = timezone.now()
            parada.save()
            messages.success(request, "Parada encerrada.")
        return redirect("producao:painel", pk=ordem.pk)


class OcorrenciaView(_ExecucaoActionView):
    def post(self, request, pk):
        execucao, ordem = self.get_execucao_em_andamento(request, pk)
        if execucao is None:
            return redirect("producao:painel", pk=ordem.pk)

        form = OcorrenciaForm(request.POST)
        if form.is_valid():
            ocorrencia = form.save(commit=False)
            ocorrencia.execucao = execucao
            ocorrencia.registrado_por = request.user
            ocorrencia.save()
            messages.success(request, "Ocorrência registrada.")
        else:
            messages.error(request, "Descreva a ocorrência.")
        return redirect("producao:painel", pk=ordem.pk)


class FotoView(_ExecucaoActionView):
    def post(self, request, pk):
        execucao, ordem = self.get_execucao_em_andamento(request, pk)
        if execucao is None:
            return redirect("producao:painel", pk=ordem.pk)

        form = FotoProducaoForm(request.POST, request.FILES)
        if form.is_valid():
            foto = form.save(commit=False)
            foto.execucao = execucao
            foto.criado_por = request.user
            foto.atualizado_por = request.user
            foto.save()
            messages.success(request, "Foto anexada.")
        else:
            erros = "; ".join(
                f"{', '.join(msgs)}" for msgs in form.errors.values()
            )
            messages.error(request, f"Não foi possível anexar a foto. {erros}")
        return redirect("producao:painel", pk=ordem.pk)


class ConsumosView(_ExecucaoActionView):
    """
    Apontamento dos lotes consumidos (Etapa 4/5): o operador confirma a
    sugestão FEFO ou escolhe outros lotes/quantidades por material.
    Lotes bloqueados (vencido/reprovado…) só entram com exceção
    justificada de um usuário autorizado (Etapa 5).
    """

    def get(self, request, pk):
        execucao, ordem = self.get_execucao_em_andamento(request, pk)
        if execucao is None:
            return redirect("producao:painel", pk=ordem.pk)
        return self._render_tela(request, ordem)

    def post(self, request, pk):
        execucao, ordem = self.get_execucao_em_andamento(request, pk)
        if execucao is None:
            return redirect("producao:painel", pk=ordem.pk)

        materiais = {material.pk: material for material in ordem.materiais.all()}
        linhas = []
        for nome, valor in request.POST.items():
            if not nome.startswith("qtd-"):
                continue
            valor = (valor or "").strip().replace(",", ".")
            partes = nome.split("-")
            if len(partes) != 4 or not valor:
                continue
            try:
                material = materiais[int(partes[1])]
                lote = Lote.objects.get(pk=int(partes[2]))
                local = LocalEstoque.objects.get(pk=int(partes[3]))
                quantidade = Decimal(valor)
            except (KeyError, ValueError, InvalidOperation, Lote.DoesNotExist,
                    LocalEstoque.DoesNotExist):
                messages.error(request, "Apontamento inválido — tente novamente.")
                return redirect("producao:consumos", pk=ordem.pk)
            if quantidade > 0:
                linhas.append((material, lote, local, quantidade))

        # Exceções de bloqueio: só valem se o usuário pode autorizar.
        excecoes = {}
        if pode_autorizar_excecao(request.user):
            for nome, valor in request.POST.items():
                if nome.startswith("excecao-") and (valor or "").strip():
                    try:
                        excecoes[int(nome.split("-")[1])] = valor.strip()
                    except ValueError:
                        continue

        try:
            with transaction.atomic():
                apontar_consumos(ordem, request.user, linhas, excecoes=excecoes)
        except ValidationError as erro:
            messages.error(request, " ".join(erro.messages))
            return redirect("producao:consumos", pk=ordem.pk)

        sufixo = (
            f" ({len(excecoes)} com exceção autorizada)" if excecoes else ""
        )
        messages.success(
            request,
            f"Apontamento salvo: {len(linhas)} lote(s) para {ordem.numero}{sufixo}.",
        )
        logger.info(
            "Consumos apontados na %s por %s", ordem.numero, request.user
        )
        return redirect("producao:painel", pk=ordem.pk)

    def _render_tela(self, request, ordem):
        sugestoes = {
            material_id: {s["lote"].pk: s["quantidade"] for s in linhas}
            for material_id, linhas in sugerir_consumos_fefo(ordem).items()
        }
        apontamentos = {
            (consumo.material_id, consumo.lote_id, consumo.local_id): consumo.quantidade
            for consumo in ConsumoMaterialOP.objects.filter(
                material__ordem=ordem, movimentacao__isnull=True
            )
        }
        materiais_apontados = {chave[0] for chave in apontamentos}

        blocos = []
        for material in ordem.materiais.select_related("materia_prima", "embalagem"):
            linhas = []
            for posicao in posicoes_para_apontamento(material.item):
                chave = (material.pk, posicao["lote"].pk, posicao["local"].pk)
                if material.pk in materiais_apontados:
                    quantidade = apontamentos.get(chave, Decimal("0"))
                elif posicao["bloqueio"]:
                    quantidade = Decimal("0")  # bloqueado não entra na sugestão
                else:
                    quantidade = sugestoes[material.pk].get(
                        posicao["lote"].pk, Decimal("0")
                    )
                linhas.append({**posicao, "apontado": quantidade})
            blocos.append(
                {
                    "material": material,
                    "linhas": linhas,
                    "total_apontado": sum(
                        (linha["apontado"] for linha in linhas), Decimal("0")
                    ),
                }
            )
        return render(
            request,
            "producao/consumos.html",
            {
                "ordem": ordem,
                "blocos": blocos,
                "pode_excecao": pode_autorizar_excecao(request.user),
            },
        )


class AtividadeView(_ExecucaoActionView):
    """Registro manual de "quem fez o quê" durante a produção."""

    def post(self, request, pk):
        execucao, ordem = self.get_execucao_em_andamento(request, pk)
        if execucao is None:
            return redirect("producao:painel", pk=ordem.pk)

        form = AtividadeOPForm(request.POST)
        if form.is_valid():
            atividade = AtividadeOP.registrar(
                ordem,
                form.cleaned_data["atividade"],
                request.user,
                form.cleaned_data["observacao"],
            )
            messages.success(
                request,
                f"Atividade “{atividade.get_atividade_display()}” registrada.",
            )
        else:
            messages.error(request, "Selecione uma atividade válida.")
        return redirect("producao:painel", pk=ordem.pk)


class ConcluirView(_ExecucaoActionView):
    def post(self, request, pk):
        from apps.recebimento.models import local_quarentena

        execucao, ordem = self.get_execucao_em_andamento(request, pk)
        if execucao is None:
            return redirect("producao:painel", pk=ordem.pk)

        if execucao.tem_parada_aberta:
            messages.error(
                request, "Encerre a parada em aberto antes de concluir a produção."
            )
            return redirect("producao:painel", pk=ordem.pk)

        form = ConcluirProducaoForm(request.POST, excluir_local=local_quarentena())
        if not form.is_valid():
            erros = "; ".join(
                f"{', '.join(msgs)}" for msgs in form.errors.values()
            )
            messages.error(request, f"Confira os dados da conclusão. {erros}")
            return redirect("producao:painel", pk=ordem.pk)

        try:
            with transaction.atomic():
                execucao.concluir(
                    usuario=request.user,
                    quantidade_produzida=form.cleaned_data["quantidade_produzida"],
                    perdas=form.cleaned_data["perdas"],
                    validade=form.cleaned_data["lote_validade"],
                    local_destino=form.cleaned_data["local_destino"],
                    justificativa_divergencia=form.cleaned_data[
                        "justificativa_divergencia"
                    ],
                )
        except ValidationError as erro:
            messages.error(request, "; ".join(erro.messages))
        else:
            messages.success(
                request,
                f"Produção da OP {ordem.numero} concluída e produto acabado "
                "em estoque.",
            )
            logger.info("Produção %s concluída por %s", ordem.numero, request.user)
        return redirect("producao:painel", pk=ordem.pk)
