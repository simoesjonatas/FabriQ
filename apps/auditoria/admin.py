from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    """Consulta apenas: a trilha não pode ser criada, alterada nem apagada à mão."""

    list_display = ["data", "acao", "objeto_repr", "campo", "usuario"]
    list_filter = ["acao", "content_type"]
    search_fields = ["objeto_repr", "campo", "valor_anterior", "valor_novo", "justificativa"]
    date_hierarchy = "data"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
