from django.contrib import admin

from .models import (
    ComponenteFormula,
    Formula,
    HistoricoOP,
    MaterialOP,
    OrdemProducao,
)


class ComponenteInline(admin.TabularInline):
    model = ComponenteFormula
    extra = 0


@admin.register(Formula)
class FormulaAdmin(admin.ModelAdmin):
    list_display = ("produto", "nome", "rendimento", "ativo")
    list_filter = ("ativo",)
    search_fields = ("produto__codigo", "produto__nome", "nome")
    inlines = [ComponenteInline]


class MaterialInline(admin.TabularInline):
    model = MaterialOP
    extra = 0


class HistoricoInline(admin.TabularInline):
    model = HistoricoOP
    extra = 0
    can_delete = False
    readonly_fields = ("usuario", "data", "descricao")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrdemProducao)
class OrdemProducaoAdmin(admin.ModelAdmin):
    list_display = (
        "numero",
        "item_pedido",
        "quantidade",
        "status",
        "data_programada",
        "equipamento",
        "operador",
    )
    list_filter = ("status",)
    search_fields = ("item_pedido__produto__codigo", "item_pedido__produto__nome")
    readonly_fields = ("criado_em", "criado_por", "atualizado_em", "atualizado_por")
    inlines = [MaterialInline, HistoricoInline]
