from django.urls import path

from . import views

app_name = "pedidos"

urlpatterns = [
    path("", views.PedidoListView.as_view(), name="lista"),
    path("novo/", views.PedidoCriarView.as_view(), name="criar"),
    path("<int:pk>/", views.PedidoDetalheView.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.PedidoEditarView.as_view(), name="editar"),
    path("<int:pk>/status/", views.PedidoTransicaoView.as_view(), name="transicao"),
]
