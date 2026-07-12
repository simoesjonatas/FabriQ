from django.contrib import admin

from .models import AnexoRecebimento, DecisaoQuarentena, ItemRecebimento, Recebimento


class ItemRecebimentoInline(admin.TabularInline):
    model = ItemRecebimento
    extra = 0


class AnexoRecebimentoInline(admin.TabularInline):
    model = AnexoRecebimento
    extra = 0
    readonly_fields = ("criado_em", "criado_por")


@admin.register(Recebimento)
class RecebimentoAdmin(admin.ModelAdmin):
    list_display = ("numero", "fornecedor", "nota_fiscal", "data_recebimento", "criado_por")
    search_fields = ("nota_fiscal", "fornecedor__razao_social")
    readonly_fields = ("criado_em", "criado_por", "atualizado_em", "atualizado_por")
    inlines = [ItemRecebimentoInline, AnexoRecebimentoInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.criado_por = request.user
        obj.atualizado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(DecisaoQuarentena)
class DecisaoQuarentenaAdmin(admin.ModelAdmin):
    """Histórico de decisões: somente consulta."""

    list_display = ("item", "decisao", "responsavel", "data", "local_destino")
    list_filter = ("decisao",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
