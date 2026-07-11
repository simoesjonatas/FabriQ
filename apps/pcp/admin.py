from django.contrib import admin

from .models import Programacao


@admin.register(Programacao)
class ProgramacaoAdmin(admin.ModelAdmin):
    list_display = ("item", "equipamento", "operador", "data", "quantidade", "ativo")
    list_filter = ("ativo", "equipamento", "data")
    search_fields = (
        "item__produto__codigo",
        "item__produto__nome",
        "item__pedido__cliente__razao_social",
    )
    readonly_fields = ("criado_em", "criado_por", "atualizado_em", "atualizado_por")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.criado_por = request.user
        obj.atualizado_por = request.user
        super().save_model(request, obj, form, change)
