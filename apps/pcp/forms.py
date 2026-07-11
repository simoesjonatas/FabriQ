from django import forms

from apps.cadastros.models import Equipamento
from apps.core import formatos
from apps.core.forms import BootstrapFormMixin
from apps.pedidos.models import ItemPedido

from .models import STATUS_PROGRAMAVEIS, Programacao, saldo_a_programar


class ItemPedidoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, item):
        saldo = formatos.quantidade(saldo_a_programar(item))
        total = formatos.quantidade(item.quantidade)
        return (
            f"{item.pedido.numero} · {item.produto.codigo} {item.produto.nome} "
            f"(saldo {saldo} de {total})"
        )


class ProgramacaoForm(BootstrapFormMixin, forms.ModelForm):
    item = ItemPedidoChoiceField(
        queryset=ItemPedido.objects.none(),
        label="Item do pedido",
        help_text="Somente itens de pedidos que podem ser programados.",
    )

    class Meta:
        model = Programacao
        fields = ["item", "equipamento", "operador", "data", "quantidade", "observacoes"]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "quantidade": forms.NumberInput(attrs={"step": "any", "min": "0.001"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        itens = (
            ItemPedido.objects.filter(pedido__status__in=STATUS_PROGRAMAVEIS)
            .select_related("pedido__cliente", "produto")
            .order_by("pedido__prazo", "pedido_id", "id")
        )
        if self.instance.pk:
            itens = itens | ItemPedido.objects.filter(pk=self.instance.item_id)
            # Reprogramação mantém o item: troca-se data, equipamento,
            # operador ou quantidade.
            self.fields["item"].disabled = True
        self.fields["item"].queryset = itens.distinct()

        equipamentos = Equipamento.objects.filter(ativo=True)
        if self.instance.pk and self.instance.equipamento_id:
            equipamentos = equipamentos | Equipamento.objects.filter(
                pk=self.instance.equipamento_id
            )
        self.fields["equipamento"].queryset = equipamentos.distinct()

        operadores = self.fields["operador"].queryset.filter(is_active=True)
        self.fields["operador"].queryset = operadores.order_by("first_name", "username")
