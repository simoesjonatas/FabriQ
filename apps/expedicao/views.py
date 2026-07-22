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
from apps.auditoria.views import TrilhaAuditoriaMixin
from apps.estoque.models import Lote
from apps.pedidos.models import Pedido, StatusPedido

from .forms import ExpedicaoForm
from .models import Expedicao, registrar_expedicao
from .resumo import lotes_aprovados_do_item, resumo_pedido

logger = logging.getLogger("fabriq")

MODULO = "expedicao"


class ExpedicaoListView(AcessoModuloMixin, ListView):
    modulo = MODULO
    model = Expedicao
    template_name = "expedicao/lista.html"
    context_object_name = "expedicoes"
    paginate_by = 20

    def get_queryset(self):
        queryset = Expedicao.objects.select_related(
            "pedido__cliente", "responsavel"
        ).prefetch_related("itens")
        termo = self.request.GET.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                Q(nota_fiscal__icontains=termo)
                | Q(transportadora__icontains=termo)
                | Q(pedido__cliente__razao_social__icontains=termo)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["termo"] = self.request.GET.get("q", "").strip()
        context["pedidos_a_expedir"] = (
            Pedido.objects.filter(status=StatusPedido.FINALIZADO)
            .select_related("cliente")
            .order_by("prazo")
        )
        return context


class ExpedicaoDetalheView(AcessoModuloMixin, TrilhaAuditoriaMixin, DetailView):
    modulo = MODULO
    model = Expedicao
    template_name = "expedicao/detalhe.html"
    context_object_name = "expedicao"

    def get_queryset(self):
        return Expedicao.objects.select_related(
            "pedido__cliente", "conferente", "responsavel", "criado_por"
        ).prefetch_related("itens__lote", "itens__item_pedido__produto")


class ExpedicaoCriarView(AcessoModuloMixin, View):
    """Nova expedição de um pedido finalizado, por lote aprovado."""

    modulo = MODULO

    def get(self, request, pedido_pk):
        pedido = self._pedido(pedido_pk)
        return self._render_tela(request, pedido, ExpedicaoForm())

    def post(self, request, pedido_pk):
        pedido = self._pedido(pedido_pk)
        form = ExpedicaoForm(request.POST)

        linhas = []
        for nome, valor in request.POST.items():
            if not nome.startswith("qtd-"):
                continue
            valor = (valor or "").strip().replace(",", ".")
            if not valor:
                continue
            partes = nome.split("-")
            try:
                item = pedido.itens.get(pk=int(partes[1]))
                lote = Lote.objects.get(pk=int(partes[2]))
                quantidade = Decimal(valor)
            except (ValueError, InvalidOperation, Lote.DoesNotExist,
                    pedido.itens.model.DoesNotExist):
                messages.error(request, "Expedição inválida — revise os lotes.")
                return redirect("expedicao:criar", pedido_pk=pedido.pk)
            if quantidade > 0:
                linhas.append((item, lote, quantidade))

        if not form.is_valid():
            return self._render_tela(request, pedido, form)

        try:
            with transaction.atomic():
                expedicao = registrar_expedicao(
                    pedido=pedido,
                    data=form.cleaned_data["data"],
                    usuario=request.user,
                    linhas=linhas,
                    nota_fiscal=form.cleaned_data["nota_fiscal"],
                    transportadora=form.cleaned_data["transportadora"],
                    conferente=form.cleaned_data["conferente"],
                    observacoes=form.cleaned_data["observacoes"],
                )
        except ValidationError as erro:
            for mensagem in erro.messages:
                form.add_error(None, mensagem)
            return self._render_tela(request, pedido, form)

        messages.success(
            request,
            f"Expedição {expedicao.numero} registrada — "
            f"{len(linhas)} lote(s) baixado(s).",
        )
        logger.info(
            "Expedição %s do pedido %s por %s",
            expedicao.numero, pedido.numero, request.user,
        )
        return redirect(expedicao.get_absolute_url())

    def _pedido(self, pk):
        return get_object_or_404(
            Pedido.objects.select_related("cliente"), pk=pk
        )

    def _render_tela(self, request, pedido, form):
        blocos = []
        for resumo in resumo_pedido(pedido):
            blocos.append(
                {**resumo, "lotes_aprovados": lotes_aprovados_do_item(resumo["item"])}
            )
        if form.data.get("data") is None and not form.is_bound:
            form.initial.setdefault("data", timezone.localdate())
        return render(
            request,
            "expedicao/form.html",
            {"pedido": pedido, "form": form, "blocos": blocos},
        )
