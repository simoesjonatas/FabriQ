import calendar
import logging
from datetime import date, timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.accounts.mixins import AcessoModuloMixin
from apps.cadastros.models import Equipamento, Produto
from apps.core import formatos
from apps.core.views import SalvarComUsuarioMixin
from apps.pedidos.models import HistoricoPedido, ItemPedido, StatusPedido

from .forms import ProgramacaoForm
from .models import (
    STATUS_PROGRAMAVEIS,
    Programacao,
    itens_pendentes_de_programacao,
    ocupacao_por_equipamento_dia,
)

logger = logging.getLogger("fabriq")

MODULO = "pcp"


def _parse_mes(texto: str) -> date:
    """Converte "YYYY-MM" no primeiro dia do mês; inválido cai no mês atual."""
    try:
        ano, mes = texto.split("-")
        return date(int(ano), int(mes), 1)
    except (AttributeError, TypeError, ValueError):
        return timezone.localdate().replace(day=1)


class CalendarioView(AcessoModuloMixin, TemplateView):
    modulo = MODULO
    template_name = "pcp/calendario.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        mes_atual = _parse_mes(self.request.GET.get("mes", ""))
        hoje = timezone.localdate()

        equipamento_id = self.request.GET.get("equipamento", "")
        produto_id = self.request.GET.get("produto", "")

        semanas_do_mes = calendar.Calendar(firstweekday=6).monthdatescalendar(
            mes_atual.year, mes_atual.month
        )
        inicio, fim = semanas_do_mes[0][0], semanas_do_mes[-1][-1]

        programacoes = (
            Programacao.objects.filter(ativo=True, data__range=(inicio, fim))
            .select_related(
                "item__produto", "item__pedido__cliente", "equipamento", "operador"
            )
            .order_by("equipamento__nome", "id")
        )
        if equipamento_id.isdigit():
            programacoes = programacoes.filter(equipamento_id=equipamento_id)
        if produto_id.isdigit():
            programacoes = programacoes.filter(item__produto_id=produto_id)

        ocupacao = ocupacao_por_equipamento_dia(inicio, fim)
        sobrecargas = {
            chave
            for chave, dados in ocupacao.items()
            if dados["capacidade"] and dados["total"] > dados["capacidade"]
        }

        por_dia: dict[date, list[Programacao]] = {}
        for programacao in programacoes:
            programacao.sobrecarga = (
                programacao.equipamento_id,
                programacao.data,
            ) in sobrecargas
            por_dia.setdefault(programacao.data, []).append(programacao)

        semanas = [
            [
                {
                    "data": dia,
                    "fora_do_mes": dia.month != mes_atual.month,
                    "hoje": dia == hoje,
                    "programacoes": por_dia.get(dia, []),
                }
                for dia in semana
            ]
            for semana in semanas_do_mes
        ]

        context.update(
            {
                "semanas": semanas,
                "mes_atual": mes_atual,
                "mes_anterior": (mes_atual - timedelta(days=1)).replace(day=1),
                "mes_proximo": (
                    mes_atual.replace(day=28) + timedelta(days=7)
                ).replace(day=1),
                "equipamentos": Equipamento.objects.filter(ativo=True),
                "produtos": Produto.objects.filter(ativo=True),
                "equipamento_selecionado": equipamento_id,
                "produto_selecionado": produto_id,
                "total_no_mes": sum(
                    len(dia["programacoes"])
                    for semana in semanas
                    for dia in semana
                    if not dia["fora_do_mes"]
                ),
            }
        )
        return context


class ProgramacaoListView(AcessoModuloMixin, ListView):
    modulo = MODULO
    model = Programacao
    template_name = "pcp/lista.html"
    context_object_name = "programacoes"
    paginate_by = 30

    def get_queryset(self):
        queryset = (
            Programacao.objects.filter(ativo=True)
            .select_related(
                "item__produto", "item__pedido__cliente", "equipamento", "operador"
            )
            .order_by("data", "equipamento__nome", "id")
        )

        filtros = self.request.GET
        if filtros.get("de"):
            queryset = queryset.filter(data__gte=filtros["de"])
        if filtros.get("ate"):
            queryset = queryset.filter(data__lte=filtros["ate"])
        if filtros.get("equipamento", "").isdigit():
            queryset = queryset.filter(equipamento_id=filtros["equipamento"])
        if filtros.get("produto", "").isdigit():
            queryset = queryset.filter(item__produto_id=filtros["produto"])
        if filtros.get("status") in StatusPedido.values:
            queryset = queryset.filter(item__pedido__status=filtros["status"])

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.request.GET
        context.update(
            {
                "equipamentos": Equipamento.objects.filter(ativo=True),
                "produtos": Produto.objects.filter(ativo=True),
                "status_choices": StatusPedido.choices,
                "filtro_de": filtros.get("de", ""),
                "filtro_ate": filtros.get("ate", ""),
                "filtro_equipamento": filtros.get("equipamento", ""),
                "filtro_produto": filtros.get("produto", ""),
                "filtro_status": filtros.get("status", ""),
            }
        )
        return context


class PendentesView(AcessoModuloMixin, TemplateView):
    modulo = MODULO
    template_name = "pcp/pendentes.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["itens"] = itens_pendentes_de_programacao()
        context["hoje"] = timezone.localdate()
        return context


class ProgramacaoFormBase(AcessoModuloMixin, SalvarComUsuarioMixin):
    modulo = MODULO
    model = Programacao
    form_class = ProgramacaoForm
    template_name = "pcp/programacao_form.html"

    def get_success_url(self):
        return f"{reverse('pcp:calendario')}?mes={self.object.data:%Y-%m}"


class ProgramacaoCriarView(ProgramacaoFormBase, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        item_id = self.request.GET.get("item", "")
        if item_id.isdigit():
            item = ItemPedido.objects.filter(
                pk=item_id, pedido__status__in=STATUS_PROGRAMAVEIS
            ).first()
            if item:
                initial["item"] = item
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        programacao = self.object
        pedido = programacao.item.pedido

        HistoricoPedido.registrar(
            pedido=pedido,
            usuario=self.request.user,
            descricao=(
                f"Item {programacao.item.produto.codigo} programado: "
                f"{formatos.quantidade(programacao.quantidade)} "
                f"{programacao.item.produto.get_unidade_display().lower()} para "
                f"{programacao.data:%d/%m/%Y} no equipamento "
                f"{programacao.equipamento.codigo}"
            ),
        )

        # Programar um pedido em análise/aguardando MP avança o status
        if pedido.status in {StatusPedido.EM_ANALISE, StatusPedido.AGUARDANDO_MP}:
            pedido.transicionar(StatusPedido.PROGRAMADO, self.request.user)
            messages.info(
                self.request,
                f"O pedido {pedido.numero} avançou para “Programado”.",
            )

        messages.success(
            self.request,
            f"Item programado para {programacao.data:%d/%m/%Y} "
            f"no {programacao.equipamento.codigo}.",
        )
        logger.info(
            "Programação %s criada por %s", programacao.pk, self.request.user
        )
        return response


def _descrever_mudanca(campo, valor):
    if campo == "data":
        return f"nova data {valor:%d/%m/%Y}"
    if campo == "quantidade":
        return f"quantidade {formatos.quantidade(valor)}"
    if campo in {"equipamento", "operador"} and valor:
        return f"{campo} {valor}"
    return campo


class ProgramacaoEditarView(ProgramacaoFormBase, UpdateView):
    def form_valid(self, form):
        campos_alterados = list(form.changed_data)
        response = super().form_valid(form)
        programacao = self.object

        if campos_alterados:
            partes = [
                _descrever_mudanca(campo, form.cleaned_data.get(campo))
                for campo in campos_alterados
            ]

            HistoricoPedido.registrar(
                pedido=programacao.item.pedido,
                usuario=self.request.user,
                descricao=(
                    f"Item {programacao.item.produto.codigo} reprogramado: "
                    f"{', '.join(partes)}"
                ),
            )
            messages.success(self.request, "Programação atualizada.")
            logger.info(
                "Programação %s reprogramada por %s (%s)",
                programacao.pk,
                self.request.user,
                ", ".join(campos_alterados),
            )
        return response


class ProgramacaoRemoverView(AcessoModuloMixin, View):
    modulo = MODULO

    def post(self, request, pk):
        programacao = get_object_or_404(Programacao, pk=pk, ativo=True)
        motivo = request.POST.get("motivo", "").strip()

        if not motivo:
            messages.error(request, "Informe o motivo da remoção da programação.")
            return redirect("pcp:lista")

        programacao.ativo = False
        programacao.motivo_remocao = motivo
        programacao.atualizado_por = request.user
        programacao.save()

        HistoricoPedido.registrar(
            pedido=programacao.item.pedido,
            usuario=request.user,
            descricao=(
                f"Programação do item {programacao.item.produto.codigo} "
                f"({formatos.quantidade(programacao.quantidade)} em "
                f"{programacao.data:%d/%m/%Y}) removida. Motivo: {motivo}"
            ),
        )
        messages.success(request, "Programação removida (mantida no histórico).")
        logger.info(
            "Programação %s removida por %s", programacao.pk, request.user
        )
        return redirect("pcp:lista")
