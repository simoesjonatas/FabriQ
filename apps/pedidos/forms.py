from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.auditoria.forms import JustificativaAuditoriaMixin
from apps.cadastros.models import Cliente, Produto
from apps.core.forms import BootstrapFormMixin

from .models import ItemPedido, Pedido


class PedidoForm(JustificativaAuditoriaMixin, BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ["cliente", "prazo", "observacoes"]
        widgets = {
            "prazo": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Só oferece clientes ativos, preservando um inativo já vinculado
        queryset = Cliente.objects.filter(ativo=True)
        if self.instance.pk and self.instance.cliente_id:
            queryset = queryset | Cliente.objects.filter(pk=self.instance.cliente_id)
        self.fields["cliente"].queryset = queryset.distinct()


class ItemPedidoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ItemPedido
        fields = ["produto", "quantidade"]
        widgets = {
            "quantidade": forms.NumberInput(attrs={"step": "any", "min": "0.001"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Produto.objects.filter(ativo=True)
        if self.instance.pk and self.instance.produto_id:
            queryset = queryset | Produto.objects.filter(pk=self.instance.produto_id)
        self.fields["produto"].queryset = queryset.distinct()


class ItensPedidoFormSet(BaseInlineFormSet):
    """Regras do cronograma: pelo menos um produto e sem produto repetido."""

    def validate_unique(self):
        # A checagem de duplicidade é feita em clean(), com mensagem
        # mais clara que a padrão do Django para o mesmo caso.
        pass

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        produtos_vistos = set()
        itens_validos = 0

        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            produto = form.cleaned_data.get("produto")
            if produto is None:
                continue
            itens_validos += 1
            if produto.pk in produtos_vistos:
                form.add_error("produto", "Este produto já está no pedido.")
            produtos_vistos.add(produto.pk)

        if itens_validos == 0:
            raise forms.ValidationError("O pedido deve ter pelo menos um produto.")


ItemPedidoFormSet = inlineformset_factory(
    Pedido,
    ItemPedido,
    form=ItemPedidoForm,
    formset=ItensPedidoFormSet,
    extra=1,
    can_delete=True,
)
