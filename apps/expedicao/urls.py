from django.urls import path

from . import views

app_name = "expedicao"

urlpatterns = [
    path("", views.ExpedicaoListView.as_view(), name="lista"),
    path("<int:pk>/", views.ExpedicaoDetalheView.as_view(), name="detalhe"),
    path(
        "pedido/<int:pedido_pk>/nova/",
        views.ExpedicaoCriarView.as_view(),
        name="criar",
    ),
]
