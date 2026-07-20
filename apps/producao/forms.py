from django import forms

from apps.cadastros.models import Balanca
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


class PesagemForm(BootstrapFormMixin, forms.Form):
    """Pesagem de um material da OP (Etapa 6b)."""

    material = forms.ModelChoiceField(
        label="Material", queryset=None, widget=forms.Select
    )
    lote = forms.ModelChoiceField(label="Lote pesado", queryset=None)
    balanca = forms.ModelChoiceField(
        label="Balança", queryset=Balanca.objects.none()
    )
    quantidade_pesada = forms.DecimalField(
        label="Quantidade pesada",
        max_digits=12,
        decimal_places=3,
        min_value=0,
        widget=forms.NumberInput(attrs={"step": "any", "min": "0"}),
    )
    tolerancia_percentual = forms.DecimalField(
        label="Tolerância (%)",
        max_digits=6,
        decimal_places=3,
        min_value=0,
        initial=1,
        widget=forms.NumberInput(attrs={"step": "any", "min": "0"}),
    )
    conferente = forms.ModelChoiceField(
        label="Conferente (dupla conferência)",
        queryset=None,
        required=False,
        help_text="Obrigatório para material crítico; deve ser diferente do operador.",
    )
    etiqueta = forms.CharField(
        label="Identificação da etiqueta", max_length=60, required=False
    )

    def __init__(self, *args, ordem=None, usuarios=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.estoque.models import Lote

        self.fields["material"].queryset = ordem.materiais.all()
        self.fields["lote"].queryset = Lote.objects.all()
        self.fields["balanca"].queryset = Balanca.objects.filter(ativo=True)
        self.fields["conferente"].queryset = usuarios


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
    justificativa_divergencia = forms.CharField(
        label="Justificativa da divergência de consumo",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=(
            "Obrigatória quando a soma dos lotes apontados difere do "
            "necessário (fica na trilha de auditoria)."
        ),
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


class EtapaOPForm(BootstrapFormMixin, forms.Form):
    """Registro da execução de uma etapa do processo (Etapa 6d)."""

    etapa = forms.ModelChoiceField(label="Etapa", queryset=None)
    temperatura_real = forms.DecimalField(
        label="Temperatura real (°C)", required=False,
        widget=forms.NumberInput(attrs={"step": "any"}),
    )
    tempo_real_min = forms.DecimalField(
        label="Tempo real (min)", required=False,
        widget=forms.NumberInput(attrs={"step": "any"}),
    )
    velocidade_real = forms.DecimalField(
        label="Velocidade real (rpm)", required=False,
        widget=forms.NumberInput(attrs={"step": "any"}),
    )
    conferente = forms.ModelChoiceField(
        label="Conferente", queryset=None, required=False
    )
    pulada = forms.BooleanField(label="Etapa pulada", required=False)
    justificativa = forms.CharField(
        label="Justificativa (pular/ fora de ordem)", required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    observacoes = forms.CharField(
        label="Observações", required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, snapshot=None, usuarios=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["etapa"].queryset = (
            snapshot.etapas.all() if snapshot else self.fields["etapa"].queryset
        )
        self.fields["conferente"].queryset = usuarios


class ControleProcessoForm(BootstrapFormMixin, forms.Form):
    """Controle em processo de um parâmetro (Etapa 6e)."""

    tipo = forms.ModelChoiceField(label="Parâmetro", queryset=None)
    resultado = forms.DecimalField(
        label="Resultado (numérico)", required=False,
        widget=forms.NumberInput(attrs={"step": "any"}),
    )
    resultado_texto = forms.CharField(label="Resultado (descritivo)", required=False)
    metodo = forms.CharField(label="Método", max_length=120, required=False)
    equipamento = forms.ModelChoiceField(
        label="Equipamento", queryset=None, required=False
    )

    def __init__(self, *args, **kwargs):
        from apps.cadastros.models import Equipamento
        from apps.qualidade.models import TipoAnalise

        super().__init__(*args, **kwargs)
        self.fields["tipo"].queryset = TipoAnalise.objects.filter(ativo=True)
        self.fields["equipamento"].queryset = Equipamento.objects.filter(ativo=True)


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
