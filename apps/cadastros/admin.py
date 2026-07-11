from django.contrib import admin

from .models import (
    Cliente,
    Embalagem,
    Equipamento,
    Fornecedor,
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
    list_display = ("razao_social", "nome_fantasia", "documento", "cidade", "uf", "ativo")
    list_filter = ("ativo", "uf")
    search_fields = ("razao_social", "nome_fantasia", "documento")


@admin.register(Fornecedor)
class FornecedorAdmin(CadastroAdminBase):
    list_display = ("razao_social", "nome_fantasia", "documento", "cidade", "uf", "ativo")
    list_filter = ("ativo", "uf")
    search_fields = ("razao_social", "nome_fantasia", "documento")


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
