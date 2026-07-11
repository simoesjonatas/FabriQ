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
