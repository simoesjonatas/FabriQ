from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.core.forms import BootstrapFormMixin
from apps.estoque.models import Lote

from .models import Analise, AnexoAnalise, ResultadoAnalise, TipoAnalise

TAMANHO_MAXIMO_ANEXO_MB = 10


class TipoAnaliseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = TipoAnalise
        fields = [
            "nome",
            "unidade",
            "valor_minimo",
            "valor_maximo",
            "referencia_texto",
            "ativo",
        ]
        widgets = {
            "valor_minimo": forms.NumberInput(attrs={"step": "any"}),
            "valor_maximo": forms.NumberInput(attrs={"step": "any"}),
        }

    def clean(self):
        cleaned = super().clean()
        minimo = cleaned.get("valor_minimo")
        maximo = cleaned.get("valor_maximo")
        if minimo is not None and maximo is not None and minimo > maximo:
            self.add_error(
                "valor_maximo", "O valor máximo deve ser maior que o mínimo."
            )
        return cleaned


class LoteChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, lote):
        return f"{lote.codigo} · {lote.item}"


class AnaliseForm(BootstrapFormMixin, forms.ModelForm):
    lote = LoteChoiceField(
        queryset=Lote.objects.none(),
        label="Lote",
        help_text="Lote do material analisado (recebido ou produzido).",
    )

    class Meta:
        model = Analise
        fields = [
            "lote",
            "amostra",
            "data_coleta",
            "analista",
            "laudo",
            "observacoes",
        ]
        widgets = {
            "observacoes": forms.Textarea(attrs={"rows": 3}),
            "data_coleta": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lote"].queryset = Lote.objects.select_related(
            "produto", "materia_prima", "embalagem"
        ).order_by("-id")
        analistas = self.fields["analista"].queryset.filter(is_active=True)
        self.fields["analista"].queryset = analistas.order_by(
            "first_name", "username"
        )
        self.fields["analista"].required = False
        for campo in ("amostra", "data_coleta", "laudo"):
            self.fields[campo].required = False
        if self.instance.pk:
            # A análise pertence ao lote: para outro lote, cria-se outra análise
            self.fields["lote"].disabled = True


class ResultadoAnaliseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ResultadoAnalise
        fields = ["tipo", "valor_numerico", "valor_texto"]
        widgets = {
            "valor_numerico": forms.NumberInput(attrs={"step": "any"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tipos = TipoAnalise.objects.filter(ativo=True)
        if self.instance.pk and self.instance.tipo_id:
            tipos = tipos | TipoAnalise.objects.filter(pk=self.instance.tipo_id)
        self.fields["tipo"].queryset = tipos.distinct()

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("tipo")
        numerico = cleaned.get("valor_numerico")
        texto = (cleaned.get("valor_texto") or "").strip()

        if tipo is None:
            return cleaned

        tipo_numerico = tipo.valor_minimo is not None or tipo.valor_maximo is not None
        if tipo_numerico and numerico is None:
            self.add_error(
                "valor_numerico",
                f"“{tipo.nome}” tem referência numérica ({tipo.referencia}): "
                "informe o valor medido.",
            )
        elif numerico is None and not texto:
            self.add_error("valor_texto", "Informe o resultado da análise.")
        return cleaned


class ResultadosFormSet(BaseInlineFormSet):
    def validate_unique(self):
        # Duplicidade tratada em clean(), com mensagem mais clara
        pass

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        tipos_vistos = set()
        validos = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            tipo = form.cleaned_data.get("tipo")
            if tipo is None:
                continue
            validos += 1
            if tipo.pk in tipos_vistos:
                form.add_error("tipo", "Este tipo de análise já foi registrado.")
            tipos_vistos.add(tipo.pk)

        if validos == 0:
            raise forms.ValidationError(
                "Registre pelo menos um resultado de análise."
            )


ResultadoAnaliseFormSet = inlineformset_factory(
    Analise,
    ResultadoAnalise,
    form=ResultadoAnaliseForm,
    formset=ResultadosFormSet,
    extra=1,
    can_delete=True,
)


class AnexoAnaliseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AnexoAnalise
        fields = ["arquivo", "descricao"]

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get("arquivo")
        if arquivo and arquivo.size > TAMANHO_MAXIMO_ANEXO_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"Arquivo muito grande (máximo {TAMANHO_MAXIMO_ANEXO_MB} MB)."
            )
        return arquivo


AnexoAnaliseFormSet = inlineformset_factory(
    Analise,
    AnexoAnalise,
    form=AnexoAnaliseForm,
    extra=1,
    can_delete=True,
)
