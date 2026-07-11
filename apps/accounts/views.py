import logging

from django.contrib.auth import views as auth_views
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import (
    DefinirSenhaForm,
    LoginForm,
    RecuperarSenhaForm,
    TrocarSenhaForm,
    UsuarioCriarForm,
    UsuarioEditarForm,
)
from .mixins import AcessoModuloMixin
from .models import User

logger = logging.getLogger("fabriq")


# Autenticação


class LoginUsuarioView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class TrocarSenhaView(SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = "accounts/trocar_senha.html"
    form_class = TrocarSenhaForm
    success_url = reverse_lazy("core:home")
    success_message = "Senha alterada com sucesso."


class RecuperarSenhaView(auth_views.PasswordResetView):
    template_name = "accounts/recuperar_senha.html"
    form_class = RecuperarSenhaForm
    email_template_name = "accounts/recuperar_senha_email.html"
    subject_template_name = "accounts/recuperar_senha_assunto.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class RecuperarSenhaEnviadoView(auth_views.PasswordResetDoneView):
    template_name = "accounts/recuperar_senha_enviado.html"


class RedefinirSenhaView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/redefinir_senha.html"
    form_class = DefinirSenhaForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class RedefinirSenhaConcluidoView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/redefinir_senha_concluido.html"


# Cadastro de usuários (módulo restrito ao Administrador)


class UsuarioListView(AcessoModuloMixin, ListView):
    modulo = "usuarios"
    model = User
    template_name = "accounts/usuario_lista.html"
    context_object_name = "usuarios"
    paginate_by = 20

    def get_queryset(self):
        queryset = User.objects.order_by("first_name", "username").prefetch_related("groups")

        termo = self.request.GET.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                Q(username__icontains=termo)
                | Q(first_name__icontains=termo)
                | Q(last_name__icontains=termo)
                | Q(email__icontains=termo)
            )

        status = self.request.GET.get("status", "")
        if status == "ativos":
            queryset = queryset.filter(is_active=True)
        elif status == "inativos":
            queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["termo"] = self.request.GET.get("q", "").strip()
        context["status"] = self.request.GET.get("status", "")
        return context


class UsuarioCriarView(AcessoModuloMixin, SuccessMessageMixin, CreateView):
    modulo = "usuarios"
    model = User
    form_class = UsuarioCriarForm
    template_name = "accounts/usuario_form.html"
    success_url = reverse_lazy("accounts:usuario_lista")
    success_message = "Usuário %(username)s cadastrado com sucesso."

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info(
            "Usuário %s cadastrado por %s", self.object.username, self.request.user
        )
        return response


class UsuarioEditarView(AcessoModuloMixin, SuccessMessageMixin, UpdateView):
    modulo = "usuarios"
    model = User
    form_class = UsuarioEditarForm
    template_name = "accounts/usuario_form.html"
    success_url = reverse_lazy("accounts:usuario_lista")
    success_message = "Usuário %(username)s atualizado com sucesso."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario_logado"] = self.request.user
        return kwargs

    def get_success_message(self, cleaned_data):
        return self.success_message % {"username": self.object.username}

    def form_valid(self, form):
        response = super().form_valid(form)
        logger.info(
            "Usuário %s atualizado por %s", self.object.username, self.request.user
        )
        return response
