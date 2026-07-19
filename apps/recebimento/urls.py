from django.urls import path

from . import views

app_name = "recebimento"

urlpatterns = [
    path("recebimento/", views.RecebimentoListView.as_view(), name="lista"),
    path("recebimento/novo/", views.RecebimentoCriarView.as_view(), name="criar"),
    path(
        "recebimento/<int:pk>/",
        views.RecebimentoDetalheView.as_view(),
        name="detalhe",
    ),
    path("quarentena/", views.QuarentenaFilaView.as_view(), name="quarentena"),
    path(
        "quarentena/itens/<int:pk>/decidir/",
        views.DecidirItemView.as_view(),
        name="decidir",
    ),
    path(
        "recebimento/itens/<int:pk>/etiqueta/",
        views.EtiquetaItemView.as_view(),
        name="etiqueta",
    ),
]
