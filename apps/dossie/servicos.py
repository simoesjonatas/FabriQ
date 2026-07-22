"""
Montagem do dossiê do lote (Etapa 12 do plano, PDF 2.2 e 4).

O dossiê é a visão única e completa de um lote de **produto acabado**,
montada automaticamente pelos vínculos já gravados no banco — nada é
digitado à mão. O banco continua sendo a fonte oficial; o PDF gerado a
partir daqui é evidência consolidada de um instante.

`montar_dossie(lote)` devolve os blocos na ordem do PDF do cliente:
identificação, fórmula congelada, materiais e documentos, pesagens,
equipamentos, etapas, controles em processo, envase, perdas, desvios,
CQ/assinaturas, expedições e trilha de auditoria.
"""

from decimal import Decimal

from apps.estoque.models import saldo


def _origem_do_lote(lote) -> dict | None:
    """Recebimento/fornecedor do lote de material (None se produzido)."""
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
    }


def _identificacao(lote, ordens) -> dict:
    """Bloco 1 (PDF 4.1): identificação e situação do lote."""
    primeira = ordens[0]["ordem"] if ordens else None
    execucoes = [no["execucao"] for no in ordens if no["execucao"] is not None]

    prevista = sum(
        (no["ordem"].quantidade for no in ordens), Decimal("0")
    )
    produzida = sum(
        (e.quantidade_produzida or Decimal("0") for e in execucoes), Decimal("0")
    )
    perdas = sum((e.perdas or Decimal("0") for e in execucoes), Decimal("0"))

    return {
        "produto": lote.produto,
        "cliente": (
            primeira.item_pedido.pedido.cliente if primeira is not None else None
        ),
        "pedido": primeira.item_pedido.pedido if primeira is not None else None,
        "fabricacao": (
            min(
                (e.concluido_em for e in execucoes if e.concluido_em), default=None
            )
        ),
        "validade": lote.validade,
        "quantidade_prevista": prevista,
        "quantidade_produzida": produzida,
        "perdas": perdas,
        "rendimento": (
            execucoes[0].rendimento_percentual if execucoes else None
        ),
        "situacao": lote.get_situacao_display(),
        "saldo": saldo(lote.produto, lote=lote),
    }


def _materiais_da_ordem(ordem) -> list[dict]:
    """
    Bloco 3 (PDF 4.3): materiais consumidos, com lote, fornecedor,
    recebimento/NF e análise — cada linha rastreável até a origem.
    """
    linhas = []
    materiais = ordem.materiais.select_related(
        "materia_prima", "embalagem"
    ).prefetch_related("consumos__lote", "consumos__local")
    for material in materiais:
        item = material.item
        for consumo in material.consumos.all():
            linhas.append(
                {
                    "item": item,
                    "tipo": item._meta.verbose_name,
                    "lote": consumo.lote,
                    "quantidade": consumo.quantidade,
                    "local": consumo.local,
                    "confirmado": consumo.confirmado,
                    "origem": _origem_do_lote(consumo.lote),
                    "analises": list(consumo.lote.analises.all()),
                }
            )
        if not material.consumos.all():
            linhas.append(
                {
                    "item": item,
                    "tipo": item._meta.verbose_name,
                    "lote": None,
                    "quantidade": material.quantidade_necessaria,
                    "local": None,
                    "confirmado": False,
                    "origem": None,
                    "analises": [],
                }
            )
    return linhas


def _bloco_da_ordem(ordem) -> dict:
    """Blocos 2 e 4–10: tudo o que a OP registrou."""
    from apps.producao.models import PesagemOP

    return {
        "ordem": ordem,
        "pedido": ordem.item_pedido.pedido,
        "cliente": ordem.item_pedido.pedido.cliente,
        "execucao": getattr(ordem, "execucao", None),
        "snapshot": getattr(ordem, "snapshot_formula", None),
        "materiais": _materiais_da_ordem(ordem),
        "pesagens": list(
            PesagemOP.objects.filter(material__ordem=ordem)
            .select_related("material", "lote", "balanca", "operador", "conferente")
            .order_by("id")
        ),
        "equipamento": ordem.equipamento,
        "checklists": list(
            ordem.checklists_equipamento.select_related(
                "equipamento", "responsavel"
            ).order_by("id")
        ),
        "etapas": list(
            ordem.etapas_execucao.select_related(
                "etapa", "operador", "conferente"
            ).order_by("id")
        ),
        "controles": list(
            ordem.controles_processo.select_related(
                "tipo", "etapa", "equipamento", "analista"
            ).order_by("id")
        ),
        "envases": list(
            ordem.envases.select_related(
                "versao_arte", "lote_granel", "linha", "operador", "conferente"
            ).order_by("id")
        ),
        "desvios": list(
            ordem.desvios.select_related("responsavel", "avaliador").order_by("id")
        ),
        "liberacoes": list(
            ordem.liberacoes_fase.select_related("responsavel").order_by("id")
        ),
        "atividades": list(
            ordem.atividades.select_related("funcionario").order_by("id")
        ),
    }


def montar_dossie(lote) -> dict:
    """
    Dossiê completo do lote de produto acabado, na ordem do PDF.
    Levanta ValueError se o lote não for de produto acabado.
    """
    from apps.auditoria.servicos import trilha_de
    from apps.ordens.models import OrdemProducao

    if lote.produto_id is None:
        raise ValueError(
            "O dossiê é emitido por lote de produto acabado; "
            f"{lote.codigo} é de {lote.item._meta.verbose_name}."
        )

    ordens = [
        _bloco_da_ordem(ordem)
        for ordem in (
            OrdemProducao.objects.filter(lote_produto=lote)
            .select_related(
                "item_pedido__pedido__cliente",
                "item_pedido__produto",
                "formula",
                "equipamento",
                "linha",
                "operador",
                "supervisor",
            )
            .order_by("id")
        )
    ]

    return {
        "lote": lote,
        "identificacao": _identificacao(lote, ordens),
        "ordens": ordens,
        "analises": list(
            lote.analises.select_related("decidido_por", "analista")
            .prefetch_related("resultados__tipo")
            .order_by("id")
        ),
        "expedicoes": list(
            lote.expedicoes.select_related(
                "expedicao__pedido__cliente", "item_pedido__produto"
            ).order_by("id")
        ),
        "trilha": list(trilha_de(lote)),
    }
