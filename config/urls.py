"""Rotas principais do FabriQ."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("cadastros/", include("apps.cadastros.urls")),
    path("pedidos/", include("apps.pedidos.urls")),
    path("pcp/", include("apps.pcp.urls")),
]

if settings.DEBUG:
    # Em produção o Nginx serve os arquivos de mídia
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "FabriQ · Administração"
admin.site.site_title = "FabriQ"
admin.site.index_title = "Administração do sistema"
