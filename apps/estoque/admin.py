from django.contrib import admin

from .models import LocalEstoque, Lote, Movimentacao


@admin.register(LocalEstoque)
class LocalEstoqueAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "atualizado_em")
    list_filter = ("ativo",)
    search_fields = ("nome",)


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ("codigo", "item", "validade")
    search_fields = ("codigo",)


@admin.register(Movimentacao)
class MovimentacaoAdmin(admin.ModelAdmin):
    """Movimentações são imutáveis: o admin só permite consulta."""

    list_display = (
        "criado_em",
        "tipo",
        "item",
        "lote",
        "quantidade",
        "local_origem",
        "local_destino",
        "criado_por",
    )
    list_filter = ("tipo",)
    search_fields = ("motivo", "documento", "lote__codigo")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
