from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.cadastros.itens import atribuir_item, campo_do_item, opcoes_de_itens, resolver_item
from apps.cadastros.models import Fornecedor
from apps.core.forms import BootstrapFormMixin
from apps.estoque.models import Lote

from .models import AnexoRecebimento, ItemRecebimento, Recebimento

TAMANHO_MAXIMO_ANEXO_MB = 10


class RecebimentoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Recebimento
        fields = ["fornecedor", "nota_fiscal", "data_recebimento", "observacoes"]
        widgets = {
            "data_recebimento": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fornecedor"].queryset = Fornecedor.objects.filter(ativo=True)


def obter_ou_criar_lote(item, codigo, validade, usuario) -> Lote:
    """Reutiliza o lote do item se existir; senão cria com auditoria."""
    campo = campo_do_item(item)
    lote = Lote.objects.filter(**{campo: item}, codigo=codigo).first()
    if lote is None:
        lote = Lote(codigo=codigo, validade=validade, criado_por=usuario)
        setattr(lote, campo, item)
        lote.atualizado_por = usuario
        lote.save()
    return lote


class ItemRecebimentoForm(BootstrapFormMixin, forms.ModelForm):
    item = forms.ChoiceField(label="Item")
    lote_codigo = forms.CharField(label="Lote", max_length=50)
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

    def clean(self):
        cleaned = super().clean()
        item = self.instance.item
        codigo = (cleaned.get("lote_codigo") or "").strip()
        validade = cleaned.get("lote_validade")
        cleaned["lote_codigo"] = codigo

        if item is not None and codigo:
            existente = Lote.objects.filter(
                **{campo_do_item(item): item}, codigo=codigo
            ).first()
            if (
                existente
                and validade
                and existente.validade
                and validade != existente.validade
            ):
                self.add_error(
                    "lote_validade",
                    f"O lote {codigo} já existe com validade "
                    f"{existente.validade:%d/%m/%Y}.",
                )
        return cleaned


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
