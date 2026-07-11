import logging

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.accounts.mixins import AcessoModuloMixin

from .forms import ItemPedidoFormSet, PedidoForm
from .models import HistoricoPedido, Pedido, StatusPedido, TransicaoInvalida

logger = logging.getLogger("fabriq")

MODULO = "pedidos"

ROTULOS_CAMPOS = {
    "cliente": "cliente",
    "prazo": "prazo de entrega",
    "observacoes": "observações",
}


class PedidoListView(AcessoModuloMixin, ListView):
    modulo = MODULO
    model = Pedido
    template_name = "pedidos/pedido_lista.html"
    context_object_name = "pedidos"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            Pedido.objects.select_related("cliente")
            .annotate(total_itens=Count("itens"))
        )

        termo = self.request.GET.get("q", "").strip()
        if termo:
            filtro = Q(cliente__razao_social__icontains=termo) | Q(
                cliente__nome_fantasia__icontains=termo
            )
            somente_digitos = "".join(c for c in termo if c.isdigit())
            if somente_digitos:
                filtro |= Q(pk=int(somente_digitos))
            queryset = queryset.filter(filtro)

        status = self.request.GET.get("status", "")
        if status in StatusPedido.values:
            queryset = queryset.filter(status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "termo": self.request.GET.get("q", "").strip(),
                "status": self.request.GET.get("status", ""),
                "status_choices": StatusPedido.choices,
            }
        )
        return context


class PedidoFormBase(AcessoModuloMixin):
    modulo = MODULO
    model = Pedido
    form_class = PedidoForm
    template_name = "pedidos/pedido_form.html"

    def get_itens_formset(self, instance=None):
        kwargs = {
            "instance": instance if instance is not None else getattr(self, "object", None),
            "prefix": "itens",
        }
        if self.request.method in {"POST", "PUT"}:
            kwargs["data"] = self.request.POST
        return ItemPedidoFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["itens_formset"] = kwargs.get("itens_formset") or self.get_itens_formset()
        return context

    def form_valid(self, form):
        criando = form.instance.pk is None
        if criando:
            form.instance.criado_por = self.request.user
        form.instance.atualizado_por = self.request.user

        self.object = form.save(commit=False)
        itens_formset = self.get_itens_formset(instance=self.object)

        if not itens_formset.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form, itens_formset=itens_formset)
            )

        self.object.save()
        itens_alterados = itens_formset.has_changed()
        itens_formset.save()

        self.registrar_historico(form, criando, itens_alterados)
        messages.success(self.request, self.mensagem_sucesso())
        return redirect(self.object.get_absolute_url())

    def mensagem_sucesso(self) -> str:
        raise NotImplementedError

    def registrar_historico(self, form, criando, itens_alterados) -> None:
        if criando:
            HistoricoPedido.registrar(
                pedido=self.object,
                usuario=self.request.user,
                descricao="Pedido criado",
                status_novo=self.object.status,
            )
            logger.info(
                "Pedido %s criado por %s", self.object.numero, self.request.user
            )
            return

        alteracoes = [
            ROTULOS_CAMPOS.get(campo, campo)
            for campo in form.changed_data
        ]
        if itens_alterados:
            alteracoes.append("itens")
        if alteracoes:
            HistoricoPedido.registrar(
                pedido=self.object,
                usuario=self.request.user,
                descricao=f"Pedido alterado: {', '.join(alteracoes)}",
            )
            logger.info(
                "Pedido %s alterado por %s (%s)",
                self.object.numero,
                self.request.user,
                ", ".join(alteracoes),
            )


class PedidoCriarView(PedidoFormBase, CreateView):
    def mensagem_sucesso(self) -> str:
        return f"Pedido {self.object.numero} cadastrado com sucesso."


class PedidoEditarView(PedidoFormBase, UpdateView):
    def dispatch(self, request, *args, **kwargs):
        pedido = self.get_object()
        if request.user.is_authenticated and not pedido.editavel:
            messages.warning(
                request,
                f"O pedido {pedido.numero} está “{pedido.get_status_display()}” "
                "e não pode mais ser editado — apenas o status pode avançar.",
            )
            return redirect("pedidos:detalhe", pk=pedido.pk)
        return super().dispatch(request, *args, **kwargs)

    def mensagem_sucesso(self) -> str:
        return f"Pedido {self.object.numero} atualizado com sucesso."


class PedidoDetalheView(AcessoModuloMixin, DetailView):
    modulo = MODULO
    model = Pedido
    template_name = "pedidos/pedido_detalhe.html"
    context_object_name = "pedido"

    def get_queryset(self):
        return Pedido.objects.select_related(
            "cliente", "criado_por", "atualizado_por"
        ).prefetch_related("itens__produto", "historico__usuario")


class PedidoTransicaoView(AcessoModuloMixin, View):
    modulo = MODULO

    def post(self, request, pk):
        pedido = get_object_or_404(Pedido, pk=pk)
        novo_status = request.POST.get("novo_status", "")
        motivo = request.POST.get("motivo", "")

        try:
            pedido.transicionar(novo_status, request.user, motivo)
        except TransicaoInvalida as erro:
            messages.error(request, str(erro))
        else:
            messages.success(
                request,
                f"Pedido {pedido.numero} atualizado para "
                f"“{pedido.get_status_display()}”.",
            )
            logger.info(
                "Pedido %s mudou para %s por %s",
                pedido.numero,
                pedido.status,
                request.user,
            )
        return redirect("pedidos:detalhe", pk=pedido.pk)
