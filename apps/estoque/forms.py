from django import forms

from apps.cadastros.itens import atribuir_item, campo_do_item, opcoes_de_itens, resolver_item
from apps.core.forms import BootstrapFormMixin

from .models import LocalEstoque, Lote, Movimentacao


class LocalEstoqueForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LocalEstoque
        fields = ["nome", "descricao", "ativo"]
        widgets = {"descricao": forms.Textarea(attrs={"rows": 3})}


class MovimentacaoForm(BootstrapFormMixin, forms.ModelForm):
    item = forms.ChoiceField(label="Item")
    lote_codigo = forms.CharField(
        label="Lote",
        required=False,
        max_length=50,
        help_text="Se o lote não existir para este item, será criado.",
    )
    lote_validade = forms.DateField(
        label="Validade do lote",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    class Meta:
        model = Movimentacao
        fields = [
            "tipo",
            "quantidade",
            "local_origem",
            "local_destino",
            "motivo",
            "documento",
        ]
        widgets = {
            "quantidade": forms.NumberInput(attrs={"step": "any", "min": "0.001"}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self._lote_novo = None
        self.fields["item"].choices = opcoes_de_itens()

        locais = LocalEstoque.objects.filter(ativo=True)
        self.fields["local_origem"].queryset = locais
        self.fields["local_destino"].queryset = locais

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
        codigo = (cleaned.get("lote_codigo") or "").strip()
        validade = cleaned.get("lote_validade")
        item = self.instance.item

        if not codigo:
            if validade:
                self.add_error("lote_codigo", "Informe o código do lote da validade.")
            return cleaned

        if item is None:
            return cleaned

        campo = campo_do_item(item)
        existente = Lote.objects.filter(**{campo: item}, codigo=codigo).first()
        if existente:
            if validade and existente.validade and validade != existente.validade:
                self.add_error(
                    "lote_validade",
                    f"O lote {codigo} já existe com validade "
                    f"{existente.validade:%d/%m/%Y}.",
                )
                return cleaned
            self.instance.lote = existente
        else:
            # Criado apenas no save(), depois de tudo validado
            self._lote_novo = Lote(codigo=codigo, validade=validade, **{campo: item})
        return cleaned

    def save(self, commit=True):
        if self._lote_novo is not None:
            self._lote_novo.criado_por = self.usuario
            self._lote_novo.atualizado_por = self.usuario
            self._lote_novo.save()
            self.instance.lote = self._lote_novo
        return super().save(commit=commit)
