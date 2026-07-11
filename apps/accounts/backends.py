from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import normalizar_identificador


class UsuarioOuEmailBackend(ModelBackend):
    """Autentica com usuário ou e-mail, sempre comparando em maiúsculas."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        identificador = username or kwargs.get(UserModel.USERNAME_FIELD)
        identificador = normalizar_identificador(identificador)

        if not identificador or password is None:
            return None

        try:
            user = UserModel._default_manager.get(
                Q(username=identificador) | Q(email=identificador)
            )
        except UserModel.DoesNotExist:
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
