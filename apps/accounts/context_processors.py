from .perfis import modulos_do_usuario

MODULOS_PRINCIPAIS = {"pedidos", "pcp", "estoque"}


def _modulo_ativo(modulo, request):
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match is None:
        return False

    view_name = resolver_match.view_name or ""
    namespace = resolver_match.namespace or ""
    slug = modulo["slug"]

    if view_name == modulo["url_name"]:
        return True
    if slug == "usuarios":
        return view_name.startswith("accounts:usuario_")
    if slug == "quarentena":
        return view_name in {"recebimento:quarentena", "recebimento:decidir"}
    if slug == "recebimento":
        return namespace == "recebimento" and view_name not in {
            "recebimento:quarentena",
            "recebimento:decidir",
        }
    return namespace == slug


def modulos_menu(request):
    """Módulos visíveis para o usuário logado (menu e home)."""
    modulos = [
        {**modulo, "ativo": _modulo_ativo(modulo, request)}
        for modulo in modulos_do_usuario(request.user)
    ]
    modulos_principais = [
        modulo for modulo in modulos if modulo["slug"] in MODULOS_PRINCIPAIS
    ]
    modulos_mais = [
        modulo for modulo in modulos if modulo["slug"] not in MODULOS_PRINCIPAIS
    ]
    return {
        "modulos_menu": modulos,
        "modulos_menu_principais": modulos_principais,
        "modulos_menu_mais": modulos_mais,
        "modulos_menu_mais_ativo": any(modulo["ativo"] for modulo in modulos_mais),
    }
