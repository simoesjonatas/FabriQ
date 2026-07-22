from django.urls import path

from . import views

app_name = "estoque"

urlpatterns = [
    path("", views.SaldoView.as_view(), name="saldo"),
    path("movimentacoes/", views.MovimentacaoListView.as_view(), name="movimentacoes"),
    path("movimentar/", views.MovimentarView.as_view(), name="movimentar"),
    path("lotes/<int:pk>/", views.LoteDetalheView.as_view(), name="lote_detalhe"),
    path("locais/", views.LocalListView.as_view(), name="local_lista"),
    path("locais/novo/", views.LocalCriarView.as_view(), name="local_criar"),
    path("locais/<int:pk>/editar/", views.LocalEditarView.as_view(), name="local_editar"),
]
