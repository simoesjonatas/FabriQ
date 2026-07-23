"""
Indicadores do dashboard inicial (Fase 10 do cronograma).

Tudo é calculado a partir dos vínculos já gravados no banco. Cada
indicador declara os módulos que dão visibilidade a ele — o dashboard
mostra ao usuário só o que o perfil dele pode ver, reusando
`usuario_acessa_modulo` (mesma regra do menu).
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.accounts.perfis import usuario_acessa_modulo


def _saldo_por_item() -> dict:
    """Saldo total por item (item._meta.label, pk) -> Decimal."""
    from apps.estoque.models import saldos_detalhados

    totais: dict[tuple, Decimal] = {}
    for linha in saldos_detalhados():
        item = linha["item"]
        if item is None:
            continue
        chave = (item._meta.label, item.pk)
        totais[chave] = totais.get(chave, Decimal("0")) + linha["saldo"]
    return totais


def estoque_critico() -> list[dict]:
    """Itens ativos com saldo total abaixo do estoque mínimo."""
    from apps.cadastros.models import Embalagem, MateriaPrima, Produto

    saldos = _saldo_por_item()
    criticos = []
    for modelo in (Produto, MateriaPrima, Embalagem):
        for item in modelo.objects.filter(ativo=True, estoque_minimo__gt=0):
            total = saldos.get((item._meta.label, item.pk), Decimal("0"))
            if total < item.estoque_minimo:
                criticos.append(
                    {"item": item, "saldo": total, "minimo": item.estoque_minimo}
                )
    return criticos


def _producao_do_dia(hoje) -> dict:
    from apps.producao.models import ExecucaoOP

    do_dia = ExecucaoOP.objects.filter(concluido_em__date=hoje)
    total = do_dia.aggregate(total=Sum("quantidade_produzida"))["total"]
    return {"ordens": do_dia.count(), "quantidade": total or Decimal("0")}


def producao_ultimos_dias(dias: int = 7) -> list[dict]:
    """Quantidade produzida por dia, para o gráfico de barras."""
    from apps.producao.models import ExecucaoOP

    hoje = timezone.localdate()
    inicio = hoje - timedelta(days=dias - 1)
    por_dia = {
        linha["dia"]: linha["total"] or Decimal("0")
        for linha in (
            ExecucaoOP.objects.filter(concluido_em__date__gte=inicio)
            .annotate(dia=TruncDate("concluido_em"))
            .values("dia")
            .annotate(total=Sum("quantidade_produzida"))
        )
    }
    serie = []
    for passo in range(dias):
        dia = inicio + timedelta(days=passo)
        serie.append({"dia": dia, "quantidade": por_dia.get(dia, Decimal("0"))})
    return serie


def alertas_operacionais() -> list[dict]:
    """
    Pendências que pedem ação: equipamento/balança impedidos, lote
    vencido ainda ativo, desvio sem decisão e documento de cliente
    vencido. Cada alerta leva à tela onde se resolve.
    """
    from apps.cadastros.models import (
        Balanca,
        DocumentoCliente,
        Equipamento,
    )
    from apps.estoque.models import Lote, SituacaoLote
    from apps.producao.models import Desvio, StatusDesvio

    hoje = timezone.localdate()
    alertas = []

    impedidos = [
        e for e in Equipamento.objects.filter(ativo=True) if not e.pode_ser_usado()
    ]
    if impedidos:
        alertas.append(
            {
                "nivel": "danger",
                "icone": "bi-gear",
                "texto": f"{len(impedidos)} equipamento(s) impedido(s) de uso",
                "url_name": "cadastros:equipamento_lista",
            }
        )

    balancas = Balanca.objects.filter(
        ativo=True, calibracao_validade__lt=hoje
    ).count()
    if balancas:
        alertas.append(
            {
                "nivel": "danger",
                "icone": "bi-speedometer2",
                "texto": f"{balancas} balança(s) com calibração vencida",
                "url_name": "cadastros:balanca_lista",
            }
        )

    lotes_vencidos = Lote.objects.filter(
        validade__lt=hoje,
        situacao__in=[
            SituacaoLote.APROVADO,
            SituacaoLote.AGUARDANDO_CQ,
            SituacaoLote.EM_ANALISE,
            SituacaoLote.EM_PRODUCAO,
        ],
    ).count()
    if lotes_vencidos:
        alertas.append(
            {
                "nivel": "warning",
                "icone": "bi-calendar-x",
                "texto": f"{lotes_vencidos} lote(s) vencido(s) ainda ativo(s)",
                "url_name": "estoque:saldo",
            }
        )

    desvios = Desvio.objects.exclude(status=StatusDesvio.ENCERRADO).count()
    if desvios:
        alertas.append(
            {
                "nivel": "warning",
                "icone": "bi-exclamation-triangle",
                "texto": f"{desvios} desvio(s) aguardando decisão da Qualidade",
                "url_name": "qualidade:lista",
            }
        )

    documentos = [
        doc for doc in DocumentoCliente.objects.filter(ativo=True) if doc.vencido
    ]
    if documentos:
        alertas.append(
            {
                "nivel": "warning",
                "icone": "bi-file-earmark-x",
                "texto": f"{len(documentos)} documento(s) de cliente vencido(s)",
                "url_name": "cadastros:cliente_lista",
            }
        )

    return alertas


def _indicadores(hoje) -> list[dict]:
    from apps.ordens.models import OrdemProducao, StatusOP
    from apps.pedidos.models import Pedido, StatusPedido
    from apps.recebimento.models import ItemRecebimento, StatusQuarentena

    encerrados_pedido = {StatusPedido.EXPEDIDO, StatusPedido.CANCELADO}
    em_andamento = Pedido.objects.exclude(status__in=encerrados_pedido)
    atrasados = em_andamento.filter(prazo__lt=hoje)

    ops_abertas = OrdemProducao.objects.exclude(
        status__in=[StatusOP.CONCLUIDA, StatusOP.CANCELADA]
    )
    quarentena = ItemRecebimento.objects.filter(
        status__in=[StatusQuarentena.EM_QUARENTENA, StatusQuarentena.EM_ANALISE]
    )
    producao = _producao_do_dia(hoje)
    criticos = estoque_critico()

    return [
        {
            "chave": "pedidos_andamento",
            "titulo": "Pedidos em andamento",
            "valor": em_andamento.count(),
            "detalhe": "Do recebimento à expedição",
            "icone": "bi-receipt",
            "cor": "primary",
            "url_name": "pedidos:lista",
            "modulos": ("pedidos",),
        },
        {
            "chave": "pedidos_atrasados",
            "titulo": "Pedidos atrasados",
            "valor": atrasados.count(),
            "detalhe": "Prazo de entrega vencido",
            "icone": "bi-alarm",
            "cor": "danger",
            "url_name": "pedidos:lista",
            "modulos": ("pedidos",),
        },
        {
            "chave": "producao_dia",
            "titulo": "Produção do dia",
            "valor": producao["ordens"],
            "detalhe": f"{producao['quantidade']:.0f} unidade(s) produzida(s) hoje",
            "icone": "bi-gear-wide-connected",
            "cor": "success",
            "url_name": "producao:fila",
            "modulos": ("producao", "ordens"),
        },
        {
            "chave": "ops_abertas",
            "titulo": "OPs abertas",
            "valor": ops_abertas.count(),
            "detalhe": "Rascunho, liberadas ou em produção",
            "icone": "bi-journal-check",
            "cor": "primary",
            "url_name": "ordens:lista",
            "modulos": ("ordens", "producao"),
        },
        {
            "chave": "quarentena",
            "titulo": "Materiais em quarentena",
            "valor": quarentena.count(),
            "detalhe": "Aguardando decisão do CQ",
            "icone": "bi-shield-exclamation",
            "cor": "warning",
            "url_name": "recebimento:quarentena",
            "modulos": ("quarentena", "recebimento"),
        },
        {
            "chave": "estoque_critico",
            "titulo": "Estoque crítico",
            "valor": len(criticos),
            "detalhe": "Itens abaixo do estoque mínimo",
            "icone": "bi-box2",
            "cor": "danger",
            "url_name": "estoque:saldo",
            "modulos": ("estoque",),
        },
    ]


def montar_dashboard(user) -> dict:
    """Indicadores, alertas e série de produção visíveis para o usuário."""
    hoje = timezone.localdate()
    indicadores = [
        indicador
        for indicador in _indicadores(hoje)
        if any(usuario_acessa_modulo(user, modulo) for modulo in indicador["modulos"])
    ]
    serie = producao_ultimos_dias()
    maximo = max((linha["quantidade"] for linha in serie), default=Decimal("0"))
    for linha in serie:
        linha["percentual"] = (
            int(linha["quantidade"] / maximo * 100) if maximo else 0
        )

    tem_producao = usuario_acessa_modulo(user, "producao") or usuario_acessa_modulo(
        user, "ordens"
    )
    return {
        "indicadores": indicadores,
        "alertas": alertas_operacionais(),
        "producao_serie": serie,
        "producao_maximo": maximo,
        "tem_producao": tem_producao,
    }
