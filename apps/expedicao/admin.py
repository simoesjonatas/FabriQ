from django.contrib import admin

from .models import Expedicao, ItemExpedicao


class ItemExpedicaoInline(admin.TabularInline):
    model = ItemExpedicao
    extra = 0


@admin.register(Expedicao)
class ExpedicaoAdmin(admin.ModelAdmin):
    list_display = ["numero", "pedido", "data", "nota_fiscal", "transportadora"]
    inlines = [ItemExpedicaoInline]
