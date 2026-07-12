from django.contrib import admin

from .models import Analise, AnexoAnalise, ResultadoAnalise, TipoAnalise


@admin.register(TipoAnalise)
class TipoAnaliseAdmin(admin.ModelAdmin):
    list_display = ("nome", "unidade", "referencia", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome",)


class ResultadoInline(admin.TabularInline):
    model = ResultadoAnalise
    extra = 0


class AnexoInline(admin.TabularInline):
    model = AnexoAnalise
    extra = 0


@admin.register(Analise)
class AnaliseAdmin(admin.ModelAdmin):
    list_display = ("numero", "lote", "status", "decidido_por", "decidido_em")
    list_filter = ("status",)
    search_fields = ("lote__codigo",)
    readonly_fields = ("criado_em", "criado_por", "atualizado_em", "atualizado_por")
    inlines = [ResultadoInline, AnexoInline]
