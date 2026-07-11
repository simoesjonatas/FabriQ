"""
Perfis de acesso do FabriQ e mapa de módulos do sistema.

Os perfis são Groups do Django (criados na migração 0002). O acesso de
cada perfil aos módulos é definido aqui, em um único lugar: quando uma
nova fase entregar um módulo, basta acrescentá-lo em MODULOS.
"""

ADMINISTRADOR = "Administrador"
DIRETORIA = "Diretoria"
PRODUCAO = "Produção"
QUALIDADE = "Qualidade"
ALMOXARIFADO = "Almoxarifado"
PCP = "PCP"
COMPRAS = "Compras"
EXPEDICAO = "Expedição"

PERFIS = [
    ADMINISTRADOR,
    DIRETORIA,
    PRODUCAO,
    QUALIDADE,
    ALMOXARIFADO,
    PCP,
    COMPRAS,
    EXPEDICAO,
]

# Módulos do sistema: slug -> dados para menu e controle de acesso.
# "perfis" lista quem enxerga o módulo (Administrador e superusuário
# acessam todos, sempre).
MODULOS = {
    "pedidos": {
        "titulo": "Pedidos",
        "descricao": "Pedidos dos clientes, do recebimento à expedição",
        "icone": "bi-receipt",
        "url_name": "pedidos:lista",
        "perfis": {DIRETORIA, PCP, COMPRAS, EXPEDICAO},
    },
    "pcp": {
        "titulo": "PCP",
        "descricao": "Programação da produção e ocupação dos equipamentos",
        "icone": "bi-calendar3",
        "url_name": "pcp:calendario",
        "perfis": {DIRETORIA, PCP},
    },
    "cadastros": {
        "titulo": "Cadastros",
        "descricao": (
            "Clientes, fornecedores, produtos, matérias-primas, "
            "embalagens, equipamentos e setores"
        ),
        "icone": "bi-folder2-open",
        "url_name": "cadastros:home",
        "perfis": {DIRETORIA, QUALIDADE, ALMOXARIFADO, PCP, COMPRAS},
    },
    "usuarios": {
        "titulo": "Usuários",
        "descricao": "Cadastro de usuários e perfis de acesso",
        "icone": "bi-people",
        "url_name": "accounts:usuario_lista",
        "perfis": set(),  # somente Administrador
    },
    # Fases futuras acrescentam aqui: pcp, estoque, recebimento,
    # qualidade, ordens de produção, produção, dashboard...
}


def perfis_do_usuario(user) -> set[str]:
    """Nomes dos perfis (grupos) do usuário. Uma consulta ao banco."""
    if not user.is_authenticated:
        return set()
    return set(user.groups.values_list("name", flat=True))


def _acessa(user, modulo: str, perfis: set[str]) -> bool:
    if modulo not in MODULOS:
        # Módulo inexistente nega para todos — um erro de digitação no
        # slug aparece já nos testes, em vez de passar para admins.
        return False
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser or ADMINISTRADOR in perfis:
        return True
    return bool(perfis & MODULOS[modulo]["perfis"])


def usuario_acessa_modulo(user, modulo: str) -> bool:
    """Diz se o usuário pode ver/usar o módulo informado."""
    return _acessa(user, modulo, perfis_do_usuario(user))


def modulos_do_usuario(user):
    """
    Módulos que o usuário pode acessar, para montar o menu.

    Busca os perfis uma única vez, independentemente da quantidade de
    módulos — esta função roda em todas as páginas (context processor).
    """
    perfis = perfis_do_usuario(user)
    return [
        {"slug": slug, **dados}
        for slug, dados in MODULOS.items()
        if _acessa(user, slug, perfis)
    ]
