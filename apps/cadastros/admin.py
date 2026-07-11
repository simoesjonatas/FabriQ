from django.contrib import admin

from .models import (
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


class CadastroAdminBase(admin.ModelAdmin):
    """Auditoria visível e somente leitura no admin."""

    readonly_fields = ("criado_em", "criado_por", "atualizado_em", "atualizado_por")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.criado_por = request.user
        obj.atualizado_por = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instancias = formset.save(commit=False)
        for objeto in formset.deleted_objects:
            objeto.delete()
        for objeto in instancias:
            if objeto.pk is None:
                objeto.criado_por = request.user
            objeto.atualizado_por = request.user
            objeto.save()
        formset.save_m2m()


class TelefoneInlineBase(admin.TabularInline):
    extra = 1
    fields = ("tipo", "telefone", "contato", "principal", "observacoes", "ativo")


class EnderecoInlineBase(admin.TabularInline):
    extra = 1
    fields = (
        "tipo",
        "cep",
        "logradouro",
        "numero",
        "bairro",
        "cidade",
        "uf",
        "principal",
        "ativo",
    )


class ClienteTelefoneInline(TelefoneInlineBase):
    model = ClienteTelefone


class ClienteEnderecoInline(EnderecoInlineBase):
    model = ClienteEndereco


class FornecedorTelefoneInline(TelefoneInlineBase):
    model = FornecedorTelefone


class FornecedorEnderecoInline(EnderecoInlineBase):
    model = FornecedorEndereco


@admin.register(Setor)
class SetorAdmin(CadastroAdminBase):
    list_display = ("nome", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(Equipamento)
class EquipamentoAdmin(CadastroAdminBase):
    list_display = ("codigo", "nome", "setor", "ativo", "atualizado_em")
    list_filter = ("ativo", "setor")
    search_fields = ("codigo", "nome")


@admin.register(Cliente)
class ClienteAdmin(CadastroAdminBase):
    list_display = (
        "razao_social",
        "nome_fantasia",
        "documento",
        "cidade_uf_principal",
        "telefone_principal",
        "ativo",
    )
    list_filter = ("ativo",)
    search_fields = ("razao_social", "nome_fantasia", "documento")
    inlines = (ClienteTelefoneInline, ClienteEnderecoInline)


@admin.register(Fornecedor)
class FornecedorAdmin(CadastroAdminBase):
    list_display = (
        "razao_social",
        "nome_fantasia",
        "documento",
        "cidade_uf_principal",
        "telefone_principal",
        "ativo",
    )
    list_filter = ("ativo",)
    search_fields = ("razao_social", "nome_fantasia", "documento")
    inlines = (FornecedorTelefoneInline, FornecedorEnderecoInline)


@admin.register(Produto)
class ProdutoAdmin(CadastroAdminBase):
    list_display = ("codigo", "nome", "unidade", "estoque_minimo", "ativo")
    list_filter = ("ativo", "unidade")
    search_fields = ("codigo", "nome")


@admin.register(MateriaPrima)
class MateriaPrimaAdmin(CadastroAdminBase):
    list_display = ("codigo", "nome", "unidade", "estoque_minimo", "ativo")
    list_filter = ("ativo", "unidade")
    search_fields = ("codigo", "nome")


@admin.register(Embalagem)
class EmbalagemAdmin(CadastroAdminBase):
    list_display = ("codigo", "nome", "tipo", "unidade", "estoque_minimo", "ativo")
    list_filter = ("ativo", "tipo")
    search_fields = ("codigo", "nome")
