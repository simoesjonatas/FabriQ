from django.urls import path

from . import views

app_name = "pcp"

urlpatterns = [
    path("", views.CalendarioView.as_view(), name="calendario"),
    path("lista/", views.ProgramacaoListView.as_view(), name="lista"),
    path("pendentes/", views.PendentesView.as_view(), name="pendentes"),
    path("nova/", views.ProgramacaoCriarView.as_view(), name="criar"),
    path("<int:pk>/editar/", views.ProgramacaoEditarView.as_view(), name="editar"),
    path("<int:pk>/remover/", views.ProgramacaoRemoverView.as_view(), name="remover"),
]
