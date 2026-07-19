from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.cadastros.itens import atribuir_item, opcoes_de_itens, resolver_item
from apps.cadastros.models import Cliente, Fornecedor
from apps.core.forms import BootstrapFormMixin

from .models import AnexoRecebimento, ItemRecebimento, Recebimento

TAMANHO_MAXIMO_ANEXO_MB = 10


class RecebimentoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Recebimento
        fields = [
            "fornecedor",
            "cliente",
            "nota_fiscal",
            "data_recebimento",
            "observacoes",
        ]
        widgets = {
            "data_recebimento": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fornecedor"].queryset = Fornecedor.objects.filter(ativo=True)
        self.fields["cliente"].queryset = Cliente.objects.filter(ativo=True)


class ItemRecebimentoForm(BootstrapFormMixin, forms.ModelForm):
    item = forms.ChoiceField(label="Item")
    lote_fornecedor = forms.CharField(
        label="Lote do fornecedor",
        max_length=60,
        help_text="O lote interno é gerado automaticamente pelo sistema.",
    )
    lote_validade = forms.DateField(
        label="Validade",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    class Meta:
        model = ItemRecebimento
        fields = ["quantidade"]
        widgets = {
            "quantidade": forms.NumberInput(attrs={"step": "any", "min": "0.001"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].choices = opcoes_de_itens()

    def clean_item(self):
        valor = self.cleaned_data["item"]
        try:
            _campo, item = resolver_item(valor)
        except ValueError as erro:
            raise forms.ValidationError("Escolha um item válido.") from erro
        atribuir_item(self.instance, item)
        return valor

    def clean_lote_fornecedor(self):
        return (self.cleaned_data.get("lote_fornecedor") or "").strip()


class ItensRecebimentoFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        itens_validos = sum(
            1
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        )
        if itens_validos == 0:
            raise forms.ValidationError("O recebimento deve ter pelo menos um item.")


ItemRecebimentoFormSet = inlineformset_factory(
    Recebimento,
    ItemRecebimento,
    form=ItemRecebimentoForm,
    formset=ItensRecebimentoFormSet,
    extra=1,
    can_delete=True,
)


class AnexoRecebimentoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AnexoRecebimento
        fields = ["tipo", "arquivo", "descricao"]

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get("arquivo")
        if arquivo and arquivo.size > TAMANHO_MAXIMO_ANEXO_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"Arquivo muito grande (máximo {TAMANHO_MAXIMO_ANEXO_MB} MB)."
            )
        return arquivo


AnexoRecebimentoFormSet = inlineformset_factory(
    Recebimento,
    AnexoRecebimento,
    form=AnexoRecebimentoForm,
    extra=1,
    can_delete=True,
)
