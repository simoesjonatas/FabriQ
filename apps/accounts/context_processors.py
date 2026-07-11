from .perfis import modulos_do_usuario


def modulos_menu(request):
    """Módulos visíveis para o usuário logado (menu e home)."""
    return {"modulos_menu": modulos_do_usuario(request.user)}
