from django.urls import path

from . import views

app_name = "qualidade"

urlpatterns = [
    path("", views.AnaliseListView.as_view(), name="lista"),
    path("nova/", views.AnaliseCriarView.as_view(), name="criar"),
    path("<int:pk>/", views.AnaliseDetalheView.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.AnaliseEditarView.as_view(), name="editar"),
    path("<int:pk>/decidir/", views.DecidirAnaliseView.as_view(), name="decidir"),
    path(
        "<int:pk>/contra-analise/",
        views.ContraAnaliseView.as_view(),
        name="contra_analise",
    ),
    path("tipos/", views.TipoAnaliseListView.as_view(), name="tipo_lista"),
    path("tipos/novo/", views.TipoAnaliseCriarView.as_view(), name="tipo_criar"),
    path(
        "tipos/<int:pk>/editar/",
        views.TipoAnaliseEditarView.as_view(),
        name="tipo_editar",
    ),
]
