from django import forms

from apps.core.forms import BootstrapFormMixin
from apps.estoque.models import LocalEstoque

from .models import (
    ATIVIDADES_MANUAIS,
    FotoProducao,
    MotivoParada,
    Ocorrencia,
    TipoAtividadeOP,
)

TAMANHO_MAXIMO_FOTO_MB = 10


class AtividadeOPForm(BootstrapFormMixin, forms.Form):
    """Registro manual de "quem fez o quê" (envase, separação, conferência...)."""

    atividade = forms.ChoiceField(
        label="Atividade",
        choices=[
            (valor, dict(TipoAtividadeOP.choices)[valor])
            for valor in ATIVIDADES_MANUAIS
        ],
    )
    observacao = forms.CharField(
        label="Observação", max_length=200, required=False
    )


class ConcluirProducaoForm(BootstrapFormMixin, forms.Form):
    quantidade_produzida = forms.DecimalField(
        label="Quantidade produzida",
        max_digits=12,
        decimal_places=3,
        min_value=0,
        widget=forms.NumberInput(attrs={"step": "any", "min": "0"}),
    )
    perdas = forms.DecimalField(
        label="Perdas",
        max_digits=12,
        decimal_places=3,
        min_value=0,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={"step": "any", "min": "0"}),
    )
    lote_validade = forms.DateField(
        label="Validade do lote",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    local_destino = forms.ModelChoiceField(
        label="Local de destino",
        queryset=LocalEstoque.objects.none(),
        help_text="Onde o produto acabado será estocado.",
    )

    def __init__(self, *args, excluir_local=None, **kwargs):
        super().__init__(*args, **kwargs)
        locais = LocalEstoque.objects.filter(ativo=True)
        if excluir_local is not None:
            locais = locais.exclude(pk=excluir_local.pk)
        self.fields["local_destino"].queryset = locais

    def clean_quantidade_produzida(self):
        quantidade = self.cleaned_data["quantidade_produzida"]
        if quantidade <= 0:
            raise forms.ValidationError("Informe a quantidade efetivamente produzida.")
        return quantidade

    def clean_perdas(self):
        return self.cleaned_data.get("perdas") or 0


class ParadaForm(BootstrapFormMixin, forms.Form):
    motivo = forms.ChoiceField(label="Motivo", choices=MotivoParada.choices)
    observacoes = forms.CharField(
        label="Observações", max_length=200, required=False
    )


class OcorrenciaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Ocorrencia
        fields = ["descricao"]
        widgets = {"descricao": forms.Textarea(attrs={"rows": 2})}


class FotoProducaoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = FotoProducao
        fields = ["arquivo", "descricao"]

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get("arquivo")
        if arquivo and arquivo.size > TAMANHO_MAXIMO_FOTO_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"Arquivo muito grande (máximo {TAMANHO_MAXIMO_FOTO_MB} MB)."
            )
        return arquivo
