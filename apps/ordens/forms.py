from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.auditoria.forms import JustificativaAuditoriaMixin
from apps.cadastros.itens import atribuir_item, opcoes_de_itens, resolver_item
from apps.cadastros.models import Equipamento, Produto
from apps.core.forms import BootstrapFormMixin
from apps.pedidos.models import ItemPedido

from .models import (
    STATUS_PEDIDO_APTO_PARA_OP,
    ComponenteFormula,
    Formula,
    OrdemProducao,
    StatusFormula,
)


class FormulaForm(JustificativaAuditoriaMixin, BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Formula
        fields = ["produto", "nome", "rendimento", "observacoes", "ativo"]
        widgets = {
            "rendimento": forms.NumberInput(attrs={"step": "any", "min": "0.001"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        produtos = Produto.objects.filter(ativo=True)
        if self.instance.pk and self.instance.produto_id:
            produtos = produtos | Produto.objects.filter(pk=self.instance.produto_id)
        self.fields["produto"].queryset = produtos.distinct()

    def clean_produto(self):
        produto = self.cleaned_data["produto"]
        if (
            self.instance.pk
            and self.instance.produto_id
            and produto.pk != self.instance.produto_id
            and self.instance.tem_op_emitida
        ):
            raise forms.ValidationError(
                "Esta fórmula já tem OP emitida — o produto não pode ser "
                "trocado. Cadastre uma nova fórmula para o outro produto."
            )
        return produto


class ComponenteForm(BootstrapFormMixin, forms.ModelForm):
    item = forms.ChoiceField(label="Material")

    class Meta:
        model = ComponenteFormula
        fields = ["quantidade"]
        widgets = {
            "quantidade": forms.NumberInput(attrs={"step": "any", "min": "0.001"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Componentes são matérias-primas ou embalagens — nunca produtos
        self.fields["item"].choices = opcoes_de_itens(prefixos=("MP", "E"))
        if self.instance.pk:
            item = self.instance.item
            prefixo = "MP" if self.instance.materia_prima_id else "E"
            self.fields["item"].initial = f"{prefixo}-{item.pk}"

    def clean_item(self):
        valor = self.cleaned_data["item"]
        try:
            _campo, item = resolver_item(valor)
        except ValueError as erro:
            raise forms.ValidationError("Escolha um material válido.") from erro
        atribuir_item(self.instance, item)
        return valor


class ComponentesFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        itens_vistos = set()
        validos = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            valor = form.cleaned_data.get("item")
            if not valor:
                continue
            validos += 1
            if valor in itens_vistos:
                form.add_error("item", "Este material já está na fórmula.")
            itens_vistos.add(valor)

        if validos == 0:
            raise forms.ValidationError("A fórmula deve ter pelo menos um material.")


ComponenteFormSet = inlineformset_factory(
    Formula,
    ComponenteFormula,
    form=ComponenteForm,
    formset=ComponentesFormSet,
    extra=1,
    can_delete=True,
)


class ItemPedidoOPChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, item):
        return (
            f"{item.pedido.numero} · {item.produto.codigo} {item.produto.nome} "
            f"({item.pedido.cliente})"
        )


class OrdemProducaoForm(JustificativaAuditoriaMixin, BootstrapFormMixin, forms.ModelForm):
    item_pedido = ItemPedidoOPChoiceField(
        queryset=ItemPedido.objects.none(),
        label="Item do pedido",
        help_text="Somente pedidos programados ou em produção.",
    )

    class Meta:
        model = OrdemProducao
        fields = [
            "item_pedido",
            "formula",
            "quantidade",
            "equipamento",
            "operador",
            "data_programada",
            "observacoes",
        ]
        widgets = {
            "quantidade": forms.NumberInput(attrs={"step": "any", "min": "0.001"}),
            "data_programada": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        itens = (
            ItemPedido.objects.filter(pedido__status__in=STATUS_PEDIDO_APTO_PARA_OP)
            .select_related("pedido__cliente", "produto")
            .order_by("pedido__prazo", "pedido_id", "id")
        )
        if self.instance.pk:
            itens = itens | ItemPedido.objects.filter(pk=self.instance.item_pedido_id)
            self.fields["item_pedido"].disabled = True
        self.fields["item_pedido"].queryset = itens.distinct()

        # Só versões vigentes entram em OP nova (Etapa 3)
        formulas = Formula.objects.filter(
            ativo=True, status=StatusFormula.VIGENTE
        ).select_related("produto")
        if self.instance.pk and self.instance.formula_id:
            formulas = formulas | Formula.objects.filter(pk=self.instance.formula_id)
        self.fields["formula"].queryset = formulas.distinct()

        equipamentos = Equipamento.objects.filter(ativo=True)
        if self.instance.pk and self.instance.equipamento_id:
            equipamentos = equipamentos | Equipamento.objects.filter(
                pk=self.instance.equipamento_id
            )
        self.fields["equipamento"].queryset = equipamentos.distinct()

        operadores = self.fields["operador"].queryset.filter(is_active=True)
        self.fields["operador"].queryset = operadores.order_by(
            "first_name", "username"
        )

    def clean(self):
        cleaned = super().clean()
        item_pedido = cleaned.get("item_pedido") or (
            self.instance.item_pedido if self.instance.pk else None
        )
        formula = cleaned.get("formula")

        if item_pedido and formula and formula.produto_id != item_pedido.produto_id:
            self.add_error(
                "formula",
                f"A fórmula é de “{formula.produto}”, mas o item do pedido é "
                f"“{item_pedido.produto}”.",
            )
        return cleaned
