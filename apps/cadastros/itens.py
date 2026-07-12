"""
Item unificado de estoque: produto, matéria-prima ou embalagem.

Vários módulos (estoque, recebimento) precisam apontar para "um item"
que pode ser qualquer um dos três cadastros. O padrão do projeto são
três FKs anuláveis com constraint de exatamente-um; estes helpers
centralizam o select unificado ("P-1", "MP-2", "E-3") e a resolução.
"""

from .models import Embalagem, MateriaPrima, Produto

MODELOS_POR_PREFIXO = {
    "P": ("produto", Produto),
    "MP": ("materia_prima", MateriaPrima),
    "E": ("embalagem", Embalagem),
}

GRUPOS_DE_ITENS = [
    ("Produtos", "P", Produto),
    ("Matérias-primas", "MP", MateriaPrima),
    ("Embalagens", "E", Embalagem),
]


def opcoes_de_itens():
    """Choices com optgroups para um select unificado de itens ativos."""
    opcoes: list = [("", "---------")]
    for rotulo, prefixo, modelo in GRUPOS_DE_ITENS:
        itens = [
            (f"{prefixo}-{objeto.pk}", f"{objeto.codigo} · {objeto.nome}")
            for objeto in modelo.objects.filter(ativo=True)
        ]
        if itens:
            opcoes.append((rotulo, itens))
    return opcoes


def resolver_item(valor: str):
    """
    Converte "MP-4" em ("materia_prima", <MateriaPrima>).
    Levanta ValueError para valores inválidos ou item inexistente.
    """
    prefixo, _, pk = (valor or "").partition("-")
    entrada = MODELOS_POR_PREFIXO.get(prefixo)
    if entrada is None or not pk.isdigit():
        raise ValueError(f"Item inválido: {valor!r}")
    campo, modelo = entrada
    item = modelo.objects.filter(pk=int(pk)).first()
    if item is None:
        raise ValueError(f"Item inexistente: {valor!r}")
    return campo, item


def campo_do_item(item) -> str:
    """Nome do campo FK correspondente à classe do item."""
    if isinstance(item, Produto):
        return "produto"
    if isinstance(item, MateriaPrima):
        return "materia_prima"
    if isinstance(item, Embalagem):
        return "embalagem"
    raise TypeError(f"Item de estoque inválido: {item!r}")


def atribuir_item(instancia, item) -> None:
    """Zera os três FKs da instância e define apenas o do item dado."""
    for campo, _modelo in MODELOS_POR_PREFIXO.values():
        setattr(instancia, campo, None)
    setattr(instancia, campo_do_item(item), item)
