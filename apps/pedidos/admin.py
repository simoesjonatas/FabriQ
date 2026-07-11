from django.contrib import admin

from .models import HistoricoPedido, ItemPedido, Pedido


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0


class HistoricoPedidoInline(admin.TabularInline):
    model = HistoricoPedido
    extra = 0
    can_delete = False
    readonly_fields = ("usuario", "data", "descricao", "status_anterior", "status_novo")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ("numero", "cliente", "status", "prazo", "criado_em")
    list_filter = ("status",)
    search_fields = ("cliente__razao_social", "cliente__nome_fantasia")
    readonly_fields = ("criado_em", "criado_por", "atualizado_em", "atualizado_por")
    inlines = [ItemPedidoInline, HistoricoPedidoInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.criado_por = request.user
        obj.atualizado_por = request.user
        super().save_model(request, obj, form, change)
