from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import (
    Cliente,
    Embalagem,
    Equipamento,
    Fornecedor,
    MateriaPrima,
    Produto,
    Setor,
)

_TEXTAREA_CURTA = forms.Textarea(attrs={"rows": 3})


class SetorForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Setor
        fields = ["nome", "descricao", "ativo"]
        widgets = {"descricao": _TEXTAREA_CURTA}


class EquipamentoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Equipamento
        fields = [
            "codigo",
            "nome",
            "setor",
            "capacidade",
            "unidade_capacidade",
            "observacoes",
            "ativo",
        ]
        widgets = {"observacoes": _TEXTAREA_CURTA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Só oferece setores ativos, mas preserva um inativo já vinculado
        queryset = Setor.objects.filter(ativo=True)
        if self.instance.pk and self.instance.setor_id:
            queryset = queryset | Setor.objects.filter(pk=self.instance.setor_id)
        self.fields["setor"].queryset = queryset.distinct()


class PessoaFormBase(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        fields = [
            "razao_social",
            "nome_fantasia",
            "documento",
            "email",
            "telefone",
            "endereco",
            "cidade",
            "uf",
            "cep",
            "observacoes",
            "ativo",
        ]
        widgets = {"observacoes": _TEXTAREA_CURTA}

    def clean_documento(self):
        # Normaliza para só números: evita duplicidade por causa de máscara
        documento = self.cleaned_data.get("documento", "")
        return "".join(caractere for caractere in documento if caractere.isdigit())


class ClienteForm(PessoaFormBase):
    class Meta(PessoaFormBase.Meta):
        model = Cliente


class FornecedorForm(PessoaFormBase):
    class Meta(PessoaFormBase.Meta):
        model = Fornecedor


class ProdutoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Produto
        fields = [
            "codigo", "nome", "descricao", "unidade",
            "estoque_minimo", "observacoes", "ativo",
        ]
        widgets = {"descricao": _TEXTAREA_CURTA, "observacoes": _TEXTAREA_CURTA}


class MateriaPrimaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MateriaPrima
        fields = ["codigo", "nome", "unidade", "estoque_minimo", "observacoes", "ativo"]
        widgets = {"observacoes": _TEXTAREA_CURTA}


class EmbalagemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Embalagem
        fields = ["codigo", "nome", "tipo", "unidade", "estoque_minimo", "observacoes", "ativo"]
        widgets = {"observacoes": _TEXTAREA_CURTA}
