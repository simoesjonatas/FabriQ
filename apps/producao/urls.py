from django.urls import path

from . import views

app_name = "producao"

urlpatterns = [
    path("", views.FilaView.as_view(), name="fila"),
    path("<int:pk>/", views.PainelView.as_view(), name="painel"),
    path("<int:pk>/iniciar/", views.IniciarView.as_view(), name="iniciar"),
    path("<int:pk>/parada/abrir/", views.AbrirParadaView.as_view(), name="abrir_parada"),
    path(
        "<int:pk>/parada/encerrar/",
        views.EncerrarParadaView.as_view(),
        name="encerrar_parada",
    ),
    path("<int:pk>/ocorrencia/", views.OcorrenciaView.as_view(), name="ocorrencia"),
    path("<int:pk>/foto/", views.FotoView.as_view(), name="foto"),
    path("<int:pk>/lotes/", views.ConsumosView.as_view(), name="consumos"),
    path("<int:pk>/pesagem/", views.PesagemView.as_view(), name="pesagem"),
    path("<int:pk>/etapas/", views.EtapasView.as_view(), name="etapas"),
    path("<int:pk>/controles/", views.ControlesView.as_view(), name="controles"),
    path("<int:pk>/desvios/", views.DesviosView.as_view(), name="desvios"),
    path("<int:pk>/envase/", views.EnvaseView.as_view(), name="envase"),
    path("<int:pk>/atividade/", views.AtividadeView.as_view(), name="atividade"),
    path("<int:pk>/concluir/", views.ConcluirView.as_view(), name="concluir"),
]
