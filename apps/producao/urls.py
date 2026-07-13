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
    path("<int:pk>/concluir/", views.ConcluirView.as_view(), name="concluir"),
]
