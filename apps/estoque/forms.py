from django import forms

from apps.cadastros.models import Embalagem, MateriaPrima, Produto
from apps.core.forms import BootstrapFormMixin

from .models import LocalEstoque, Lote, Movimentacao

# Prefixos do select unificado de itens ("P-3" = Produto pk 3)
MODELOS_POR_PREFIXO = {
    "P": ("produto", Produto),
    "MP": ("materia_prima", MateriaPrima),
    "E": ("embalagem", Embalagem),
}


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

        grupos = [
            ("Produtos", "P", Produto),
            ("Matérias-primas", "MP", MateriaPrima),
            ("Embalagens", "E", Embalagem),
        ]
        opcoes: list = [("", "---------")]
        for rotulo, prefixo, modelo in grupos:
            itens = [
                (f"{prefixo}-{objeto.pk}", f"{objeto.codigo} · {objeto.nome}")
                for objeto in modelo.objects.filter(ativo=True)
            ]
            if itens:
                opcoes.append((rotulo, itens))
        self.fields["item"].choices = opcoes

        locais = LocalEstoque.objects.filter(ativo=True)
        self.fields["local_origem"].queryset = locais
        self.fields["local_destino"].queryset = locais

    def clean_item(self):
        valor = self.cleaned_data["item"]
        prefixo, _, pk = valor.partition("-")
        entrada = MODELOS_POR_PREFIXO.get(prefixo)
        if entrada is None or not pk.isdigit():
            raise forms.ValidationError("Escolha um item válido.")

        campo, modelo = entrada
        item = modelo.objects.filter(pk=int(pk)).first()
        if item is None:
            raise forms.ValidationError("Escolha um item válido.")

        # Zera os três e define só o escolhido
        for nome_campo, _modelo in MODELOS_POR_PREFIXO.values():
            setattr(self.instance, nome_campo, None)
        setattr(self.instance, campo, item)
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

        campo = {Produto: "produto", MateriaPrima: "materia_prima"}.get(
            type(item), "embalagem"
        )
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
