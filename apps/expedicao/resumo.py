"""
Resumo de expedição por item do pedido (Etapa 9): quantidades pedida,
produzida, aprovada e expedida, com as OPs e os lotes acabados que
atendem cada item. Usado no detalhe do pedido e na tela de expedição.
"""

from decimal import Decimal

from apps.estoque.models import SituacaoLote, saldo


def _quantidade_produzida(ordem) -> Decimal:
    execucao = getattr(ordem, "execucao", None)
    if execucao is None or execucao.quantidade_produzida is None:
        return Decimal("0")
    return execucao.quantidade_produzida


def resumo_item(item_pedido) -> dict:
    """Resumo de um item: pedida/produzida/aprovada/expedida + OPs e lotes."""
    ordens = list(
        item_pedido.ordens.select_related("execucao", "lote_produto")
    )
    produzida = sum((_quantidade_produzida(o) for o in ordens), Decimal("0"))

    aprovada = Decimal("0")
    lotes = []
    for ordem in ordens:
        lote = ordem.lote_produto
        if lote is None:
            continue
        if lote.situacao in {SituacaoLote.APROVADO, SituacaoLote.EXPEDIDO}:
            aprovada += _quantidade_produzida(ordem)
        lotes.append({"ordem": ordem, "lote": lote})

    expedicoes = list(
        item_pedido.expedicoes.select_related(
            "lote", "expedicao"
        )
    )
    expedida = sum((e.quantidade for e in expedicoes), Decimal("0"))

    return {
        "item": item_pedido,
        "pedida": item_pedido.quantidade,
        "produzida": produzida,
        "aprovada": aprovada,
        "expedida": expedida,
        "saldo": item_pedido.quantidade - expedida,
        "lotes": lotes,
        "expedicoes": expedicoes,
    }


def resumo_pedido(pedido) -> list[dict]:
    return [resumo_item(item) for item in pedido.itens.select_related("produto")]


def lotes_aprovados_do_item(item_pedido) -> list:
    """
    Lotes acabados APROVADOS das OPs do item, aptos à expedição. Cada lote
    recebe `saldo_disponivel` (saldo total em estoque) para a tela.
    """
    lotes = []
    vistos = set()
    for ordem in item_pedido.ordens.select_related("lote_produto"):
        lote = ordem.lote_produto
        if (
            lote is not None
            and lote.pk not in vistos
            and lote.situacao == SituacaoLote.APROVADO
        ):
            lote.saldo_disponivel = saldo(lote.produto, lote=lote)
            lotes.append(lote)
            vistos.add(lote.pk)
    return lotes
