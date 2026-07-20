from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet

from apps.core.forms import BootstrapFormMixin

from .models import (
    Balanca,
    Cliente,
    ClienteEndereco,
    ClienteTelefone,
    Embalagem,
    Equipamento,
    Fornecedor,
    FornecedorEndereco,
    FornecedorTelefone,
    MateriaPrima,
    Produto,
    Setor,
)

_TEXTAREA_CURTA = forms.Textarea(attrs={"rows": 3})


def somente_digitos(valor: str) -> str:
    return "".join(caractere for caractere in valor or "" if caractere.isdigit())


def _todos_digitos_iguais(valor: str) -> bool:
    return len(set(valor)) == 1


def cpf_valido(cpf: str) -> bool:
    if len(cpf) != 11 or _todos_digitos_iguais(cpf):
        return False

    for tamanho in (9, 10):
        soma = sum(int(cpf[indice]) * (tamanho + 1 - indice) for indice in range(tamanho))
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if digito != int(cpf[tamanho]):
            return False
    return True


def cnpj_valido(cnpj: str) -> bool:
    if len(cnpj) != 14 or _todos_digitos_iguais(cnpj):
        return False

    pesos_primeiro = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_segundo = [6, *pesos_primeiro]

    for tamanho, pesos in ((12, pesos_primeiro), (13, pesos_segundo)):
        soma = sum(int(cnpj[indice]) * pesos[indice] for indice in range(tamanho))
        digito = 11 - (soma % 11)
        if digito >= 10:
            digito = 0
        if digito != int(cnpj[tamanho]):
            return False
    return True


def validar_cpf_cnpj(documento: str) -> str:
    if not documento:
        return ""
    if len(documento) == 11 and cpf_valido(documento):
        return documento
    if len(documento) == 14 and cnpj_valido(documento):
        return documento
    raise ValidationError("Informe um CPF ou CNPJ válido.")


def formatar_telefone(telefone: str) -> str:
    if len(telefone) == 11:
        return f"({telefone[:2]}) {telefone[2:7]}-{telefone[7:]}"
    if len(telefone) == 10:
        return f"({telefone[:2]}) {telefone[2:6]}-{telefone[6:]}"
    return telefone


def formatar_cep(cep: str) -> str:
    if len(cep) == 8:
        return f"{cep[:5]}-{cep[5:]}"
    return cep


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
            "status",
            "ultima_limpeza",
            "ultima_sanitizacao",
            "manutencao_validade",
            "calibracao_validade",
            "localizacao",
            "capacidade",
            "unidade_capacidade",
            "observacoes",
            "ativo",
        ]
        widgets = {
            "observacoes": _TEXTAREA_CURTA,
            "ultima_limpeza": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "ultima_sanitizacao": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "manutencao_validade": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "calibracao_validade": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
        }

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
            "observacoes",
            "ativo",
        ]
        widgets = {
            "documento": forms.TextInput(
                attrs={
                    "data-mask": "cpf-cnpj",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                    "placeholder": "CPF ou CNPJ",
                }
            ),
            "observacoes": _TEXTAREA_CURTA,
        }

    def clean_documento(self):
        documento = somente_digitos(self.cleaned_data.get("documento", ""))
        return validar_cpf_cnpj(documento)


class ClienteForm(PessoaFormBase):
    class Meta(PessoaFormBase.Meta):
        model = Cliente


class FornecedorForm(PessoaFormBase):
    class Meta(PessoaFormBase.Meta):
        model = Fornecedor


class PrincipalUnicoFormSet(BaseInlineFormSet):
    deletion_widget = forms.HiddenInput
    item_label = "registro"

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        principais = 0
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            if form.cleaned_data.get("principal"):
                principais += 1

        if principais > 1:
            raise ValidationError(f"Marque apenas um {self.item_label} principal.")


class TelefoneFormSet(PrincipalUnicoFormSet):
    item_label = "telefone"


class EnderecoFormSet(PrincipalUnicoFormSet):
    item_label = "endereço"


class TelefoneFormBase(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        fields = ("tipo", "telefone", "contato", "principal", "observacoes")
        widgets = {
            "telefone": forms.TextInput(
                attrs={
                    "data-mask": "telefone",
                    "inputmode": "tel",
                    "autocomplete": "tel",
                    "placeholder": "(00) 00000-0000",
                }
            ),
            "observacoes": forms.TextInput(attrs={"placeholder": "Ramal, horário, recado..."}),
        }

    def clean_telefone(self):
        telefone = somente_digitos(self.cleaned_data.get("telefone", ""))
        if not telefone:
            return ""
        if len(telefone) not in (10, 11):
            raise ValidationError("Informe um telefone com DDD válido.")
        return formatar_telefone(telefone)


class ClienteTelefoneForm(TelefoneFormBase):
    class Meta(TelefoneFormBase.Meta):
        model = ClienteTelefone
        fields = TelefoneFormBase.Meta.fields


class FornecedorTelefoneForm(TelefoneFormBase):
    class Meta(TelefoneFormBase.Meta):
        model = FornecedorTelefone
        fields = TelefoneFormBase.Meta.fields


class EnderecoFormBase(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        fields = (
            "tipo",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "uf",
            "principal",
            "observacoes",
        )
        widgets = {
            "cep": forms.TextInput(
                attrs={
                    "data-mask": "cep",
                    "inputmode": "numeric",
                    "autocomplete": "postal-code",
                    "placeholder": "00000-000",
                }
            ),
            "observacoes": forms.TextInput(attrs={"placeholder": "Referência, doca, portaria..."}),
        }

    def clean_cep(self):
        cep = somente_digitos(self.cleaned_data.get("cep", ""))
        if not cep:
            return ""
        if len(cep) != 8:
            raise ValidationError("Informe um CEP válido.")
        return formatar_cep(cep)

    def clean_uf(self):
        return (self.cleaned_data.get("uf") or "").upper()


class ClienteEnderecoForm(EnderecoFormBase):
    class Meta(EnderecoFormBase.Meta):
        model = ClienteEndereco
        fields = EnderecoFormBase.Meta.fields


class FornecedorEnderecoForm(EnderecoFormBase):
    class Meta(EnderecoFormBase.Meta):
        model = FornecedorEndereco
        fields = EnderecoFormBase.Meta.fields


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
        fields = [
            "codigo",
            "nome",
            "unidade",
            "estoque_minimo",
            "critico",
            "observacoes",
            "ativo",
        ]
        widgets = {"observacoes": _TEXTAREA_CURTA}


class BalancaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Balanca
        fields = [
            "codigo",
            "descricao",
            "capacidade",
            "unidade_capacidade",
            "calibracao_validade",
            "localizacao",
            "ativo",
        ]
        widgets = {
            "capacidade": forms.NumberInput(attrs={"step": "any"}),
            "calibracao_validade": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
        }


class EmbalagemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Embalagem
        fields = ["codigo", "nome", "tipo", "unidade", "estoque_minimo", "observacoes", "ativo"]
        widgets = {"observacoes": _TEXTAREA_CURTA}
