"""
Consultas de rastreabilidade (Etapa 11 do plano de correções, PDF 2.5).

Reconstroem a cadeia nos dois sentidos, com quantidade e saldo em cada nó:

- `rastrear_para_tras(lote)` — de um lote de **produto acabado** até os
  fornecedores: OP(s), fórmula congelada, consumos apontados, lotes de
  matéria-prima/embalagem, recebimentos e fornecedores.
  Responde "de onde veio este lote?".
- `rastrear_para_frente(lote)` — de um lote de **matéria-prima ou
  embalagem** até os clientes: consumos, OPs, lotes acabados, expedições
  e pedidos. Responde "quais lotes usaram a MP X?" e, no recolhimento,
  "quais clientes receberam?".

As duas consultas partem dos vínculos já gravados (`ConsumoMaterialOP`,
`OrdemProducao.lote_produto`, `ItemExpedicao`) — nada é digitado à mão.
"""

from django.db.models import Q

from .models import Lote, saldo


def _origem_do_lote(lote) -> dict | None:
    """Recebimento e fornecedor que originaram o lote (None se produzido)."""
    item = lote.itens_de_recebimento.select_related(
        "recebimento__fornecedor"
    ).first()
    if item is None:
        return None
    return {
        "recebimento": item.recebimento,
        "fornecedor": item.recebimento.fornecedor,
        "nota_fiscal": item.recebimento.nota_fiscal,
        "data": item.recebimento.data_recebimento,
        "quantidade": item.quantidade,
    }


def buscar_lotes(termo: str):
    """Lotes por lote interno ou lote do fornecedor (tela de busca)."""
    termo = (termo or "").strip()
    if not termo:
        return Lote.objects.none()
    return (
        Lote.objects.filter(
            Q(codigo__icontains=termo) | Q(lote_fornecedor__icontains=termo)
        )
        .select_related("produto", "materia_prima", "embalagem")
        .order_by("-id")
    )


def rastrear_para_tras(lote) -> dict:
    """
    Para trás: lote acabado → OP(s) → fórmula congelada → consumos →
    lotes de MP/embalagem → recebimento → fornecedor.
    """
    from apps.ordens.models import OrdemProducao
    from apps.producao.models import ConsumoMaterialOP

    ordens = []
    queryset = (
        OrdemProducao.objects.filter(lote_produto=lote)
        .select_related(
            "item_pedido__pedido__cliente",
            "item_pedido__produto",
            "formula",
        )
        .order_by("id")
    )
    for ordem in queryset:
        consumos = (
            ConsumoMaterialOP.objects.filter(material__ordem=ordem)
            .select_related("material", "lote", "local")
            .order_by("id")
        )
        materiais = []
        for consumo in consumos:
            item = consumo.material.item
            materiais.append(
                {
                    "item": item,
                    "lote": consumo.lote,
                    "quantidade": consumo.quantidade,
                    "local": consumo.local,
                    "confirmado": consumo.confirmado,
                    "origem": _origem_do_lote(consumo.lote),
                    "saldo": saldo(item, lote=consumo.lote),
                }
            )
        ordens.append(
            {
                "ordem": ordem,
                "pedido": ordem.item_pedido.pedido,
                "cliente": ordem.item_pedido.pedido.cliente,
                "snapshot": getattr(ordem, "snapshot_formula", None),
                "execucao": getattr(ordem, "execucao", None),
                "materiais": materiais,
            }
        )

    # Para quem este lote foi (fecha o caso de recolhimento na mesma tela)
    expedicoes = []
    atendidos: dict[int, object] = {}
    for item in lote.expedicoes.select_related(
        "expedicao__pedido__cliente"
    ).order_by("id"):
        cliente = item.expedicao.pedido.cliente
        atendidos[cliente.pk] = cliente
        expedicoes.append(
            {
                "expedicao": item.expedicao,
                "pedido": item.expedicao.pedido,
                "cliente": cliente,
                "quantidade": item.quantidade,
            }
        )

    return {
        "sentido": "tras",
        "lote": lote,
        "item": lote.item,
        "saldo": saldo(lote.item, lote=lote),
        "origem": _origem_do_lote(lote),
        "ordens": ordens,
        "expedicoes": expedicoes,
        "clientes_atendidos": list(atendidos.values()),
    }


def rastrear_para_frente(lote) -> dict:
    """
    Para frente: lote de MP/embalagem → consumos → OP(s) → lote acabado →
    expedições → pedidos → clientes.
    """
    consumos = (
        lote.consumos_em_op.select_related(
            "material__ordem__item_pedido__pedido__cliente",
            "material__ordem__item_pedido__produto",
            "material__ordem__lote_produto",
        )
        .order_by("id")
    )

    ordens = []
    afetados: dict[int, object] = {}
    atendidos: dict[int, object] = {}
    for consumo in consumos:
        ordem = consumo.material.ordem
        lote_produzido = ordem.lote_produto

        expedicoes = []
        if lote_produzido is not None:
            itens = lote_produzido.expedicoes.select_related(
                "expedicao__pedido__cliente"
            ).order_by("id")
            for item in itens:
                cliente = item.expedicao.pedido.cliente
                atendidos[cliente.pk] = cliente
                expedicoes.append(
                    {
                        "expedicao": item.expedicao,
                        "pedido": item.expedicao.pedido,
                        "cliente": cliente,
                        "quantidade": item.quantidade,
                    }
                )

        cliente_pedido = ordem.item_pedido.pedido.cliente
        afetados[cliente_pedido.pk] = cliente_pedido
        ordens.append(
            {
                "ordem": ordem,
                "quantidade_consumida": consumo.quantidade,
                "confirmado": consumo.confirmado,
                "lote_produzido": lote_produzido,
                "saldo_produzido": (
                    saldo(lote_produzido.item, lote=lote_produzido)
                    if lote_produzido is not None
                    else None
                ),
                "pedido": ordem.item_pedido.pedido,
                "cliente": cliente_pedido,
                "expedicoes": expedicoes,
            }
        )

    return {
        "sentido": "frente",
        "lote": lote,
        "item": lote.item,
        "saldo": saldo(lote.item, lote=lote),
        "origem": _origem_do_lote(lote),
        "ordens": ordens,
        "clientes_afetados": list(afetados.values()),
        "clientes_atendidos": list(atendidos.values()),
    }


def rastrear(lote) -> dict:
    """
    Escolhe o sentido pelo tipo do lote: produto acabado rastreia para
    trás (de onde veio); matéria-prima/embalagem, para frente (onde foi).
    """
    if lote.produto_id is not None:
        return rastrear_para_tras(lote)
    return rastrear_para_frente(lote)
