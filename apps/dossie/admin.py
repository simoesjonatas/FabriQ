from django.contrib import admin

from .models import GeracaoDossie


@admin.register(GeracaoDossie)
class GeracaoDossieAdmin(admin.ModelAdmin):
    list_display = ("codigo", "lote", "versao", "gerado_por", "gerado_em")
    list_filter = ("gerado_em",)
    search_fields = ("lote__codigo", "hash_arquivo")
    readonly_fields = (
        "lote", "versao", "gerado_por", "gerado_em", "hash_arquivo", "arquivo",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
