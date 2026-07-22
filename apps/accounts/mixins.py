from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied

from .perfis import usuario_acessa_modulo


class AcessoModuloMixin(LoginRequiredMixin):
    """
    Protege uma view por módulo do sistema.

    Uso:
        class UsuarioListView(AcessoModuloMixin, ListView):
            modulo = "usuarios"

    Anônimo é redirecionado ao login; autenticado sem o perfil
    necessário recebe 403.
    """

    modulo: str | None = None

    def dispatch(self, request, *args, **kwargs):
        if self.modulo is None:
            raise ImproperlyConfigured(
                f"{type(self).__name__} usa AcessoModuloMixin mas não define 'modulo'."
            )
        if request.user.is_authenticated and not usuario_acessa_modulo(
            request.user, self.modulo
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AcessoQualquerModuloMixin(LoginRequiredMixin):
    """
    Protege uma view liberando o acesso quando o usuário acessa QUALQUER
    um dos módulos em `modulos`. Útil para fichas consolidadas (Etapa 10)
    que são abertas a partir de telas de vários módulos.
    """

    modulos: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        if not self.modulos:
            raise ImproperlyConfigured(
                f"{type(self).__name__} usa AcessoQualquerModuloMixin mas não "
                "define 'modulos'."
            )
        if request.user.is_authenticated and not any(
            usuario_acessa_modulo(request.user, modulo) for modulo in self.modulos
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
