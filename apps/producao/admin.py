from django.contrib import admin

from .models import ExecucaoOP, FotoProducao, Ocorrencia, Parada


class ParadaInline(admin.TabularInline):
    model = Parada
    extra = 0


class OcorrenciaInline(admin.TabularInline):
    model = Ocorrencia
    extra = 0


class FotoInline(admin.TabularInline):
    model = FotoProducao
    extra = 0


@admin.register(ExecucaoOP)
class ExecucaoOPAdmin(admin.ModelAdmin):
    list_display = (
        "ordem",
        "iniciado_em",
        "iniciado_por",
        "concluido_em",
        "quantidade_produzida",
        "lote_produzido",
    )
    list_filter = ("concluido_em",)
    search_fields = ("ordem__item_pedido__produto__codigo",)
    readonly_fields = ("criado_em", "criado_por", "atualizado_em", "atualizado_por")
    inlines = [ParadaInline, OcorrenciaInline, FotoInline]
