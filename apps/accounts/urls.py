from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Autenticação
    path("entrar/", views.LoginUsuarioView.as_view(), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("senha/trocar/", views.TrocarSenhaView.as_view(), name="password_change"),
    path("senha/recuperar/", views.RecuperarSenhaView.as_view(), name="password_reset"),
    path(
        "senha/recuperar/enviado/",
        views.RecuperarSenhaEnviadoView.as_view(),
        name="password_reset_done",
    ),
    path(
        "senha/redefinir/<uidb64>/<token>/",
        views.RedefinirSenhaView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "senha/redefinir/concluido/",
        views.RedefinirSenhaConcluidoView.as_view(),
        name="password_reset_complete",
    ),
    # Cadastro de usuários
    path("usuarios/", views.UsuarioListView.as_view(), name="usuario_lista"),
    path("usuarios/novo/", views.UsuarioCriarView.as_view(), name="usuario_criar"),
    path("usuarios/<int:pk>/editar/", views.UsuarioEditarView.as_view(), name="usuario_editar"),
]
