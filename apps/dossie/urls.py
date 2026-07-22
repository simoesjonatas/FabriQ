from django.urls import path

from . import views

app_name = "dossie"

urlpatterns = [
    path("lote/<int:pk>/", views.DossieView.as_view(), name="detalhe"),
    path("lote/<int:pk>/pdf/", views.DossiePDFView.as_view(), name="pdf"),
]
