from django.urls import path

from . import views

app_name = "ordens"

urlpatterns = [
    path("", views.OrdemListView.as_view(), name="lista"),
    path("nova/", views.OrdemCriarView.as_view(), name="criar"),
    path("<int:pk>/", views.OrdemDetalheView.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.OrdemEditarView.as_view(), name="editar"),
    path("<int:pk>/liberar/", views.OrdemLiberarView.as_view(), name="liberar"),
    path("<int:pk>/cancelar/", views.OrdemCancelarView.as_view(), name="cancelar"),
    path(
        "<int:pk>/liberacao-tecnica/",
        views.OrdemLiberacaoTecnicaView.as_view(),
        name="liberacao_tecnica",
    ),
    path("<int:pk>/imprimir/", views.OrdemImprimirView.as_view(), name="imprimir"),
    path("formulas/", views.FormulaListView.as_view(), name="formula_lista"),
    path("formulas/nova/", views.FormulaCriarView.as_view(), name="formula_criar"),
    path(
        "formulas/<int:pk>/editar/",
        views.FormulaEditarView.as_view(),
        name="formula_editar",
    ),
]
