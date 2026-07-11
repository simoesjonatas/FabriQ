"""
PCP — Programação da produção (Fase 4).

A programação é feita por item do pedido: produtos diferentes do mesmo
pedido podem ir para equipamentos e dias diferentes. Programar um item
de um pedido "Em análise" ou "Aguardando MP" avança o pedido para
"Programado" automaticamente (registrado no histórico do pedido).

Remover uma programação nunca exclui o registro: inativa com motivo.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce

from apps.cadastros.models import Equipamento
from apps.core import formatos
from apps.core.models import ModeloBase
from apps.pedidos.models import ItemPedido, StatusPedido

# Pedidos nestes status podem receber (re)programação
STATUS_PROGRAMAVEIS = {
    StatusPedido.EM_ANALISE,
    StatusPedido.AGUARDANDO_MP,
    StatusPedido.PROGRAMADO,
    StatusPedido.EM_PRODUCAO,
}


def saldo_a_programar(item: ItemPedido, ignorar: Programacao | None = None) -> Decimal:
    """Quantidade do item ainda sem programação ativa."""
    programacoes = item.programacoes.filter(ativo=True)
    if ignorar is not None and ignorar.pk:
        programacoes = programacoes.exclude(pk=ignorar.pk)
    total = programacoes.aggregate(total=Sum("quantidade"))["total"] or Decimal("0")
    return item.quantidade - total


class Programacao(ModeloBase):
    item = models.ForeignKey(
        ItemPedido,
        verbose_name="item do pedido",
        on_delete=models.PROTECT,
        related_name="programacoes",
    )
    equipamento = models.ForeignKey(
        Equipamento,
        verbose_name="equipamento",
        on_delete=models.PROTECT,
        related_name="programacoes",
    )
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="operador",
        on_delete=models.PROTECT,
        related_name="programacoes",
        null=True,
        blank=True,
        help_text="Pode ser definido depois, antes da produção.",
    )
    data = models.DateField("data programada")
    quantidade = models.DecimalField(
        "quantidade",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    observacoes = models.TextField("observações", blank=True)
    motivo_remocao = models.TextField("motivo da remoção", blank=True)

    class Meta:
        verbose_name = "programação"
        verbose_name_plural = "programações"
        ordering = ["data", "equipamento__nome", "id"]
        indexes = [models.Index(fields=["data", "ativo"])]

    def __str__(self) -> str:
        return (
            f"{self.item.produto.codigo} · {self.quantidade} em "
            f"{self.data:%d/%m/%Y} ({self.equipamento.codigo})"
        )

    def clean(self):
        super().clean()
        if not self.item_id:
            return

        pedido = self.item.pedido
        if self.ativo and pedido.status not in STATUS_PROGRAMAVEIS:
            raise ValidationError(
                {
                    "item": (
                        f"O pedido {pedido.numero} está "
                        f"“{pedido.get_status_display()}” e não pode ser programado."
                    )
                }
            )

        if self.ativo and self.quantidade is not None:
            saldo = saldo_a_programar(self.item, ignorar=self)
            if self.quantidade > saldo:
                raise ValidationError(
                    {
                        "quantidade": (
                            f"Quantidade acima do saldo a programar deste item "
                            f"({formatos.quantidade(saldo)} de "
                            f"{formatos.quantidade(self.item.quantidade)})."
                        )
                    }
                )

    @property
    def sobrecarga_equipamento(self) -> bool:
        """Diz se o total programado no dia passa a capacidade do equipamento."""
        capacidade = self.equipamento.capacidade
        if not capacidade:
            return False
        total = (
            Programacao.objects.filter(
                equipamento=self.equipamento, data=self.data, ativo=True
            ).aggregate(total=Sum("quantidade"))["total"]
            or 0
        )
        return total > capacidade


def ocupacao_por_equipamento_dia(inicio, fim, equipamento=None):
    """
    Totais programados por (equipamento, dia) no período, com a
    capacidade, para montar os alertas de ocupação do calendário.
    Retorna dict {(equipamento_id, data): {"total": ..., "capacidade": ...}}.
    """
    programacoes = Programacao.objects.filter(
        ativo=True, data__range=(inicio, fim)
    )
    if equipamento is not None:
        programacoes = programacoes.filter(equipamento=equipamento)

    agregado = programacoes.values(
        "equipamento_id", "data", "equipamento__capacidade"
    ).annotate(total=Sum("quantidade"))

    return {
        (linha["equipamento_id"], linha["data"]): {
            "total": linha["total"],
            "capacidade": linha["equipamento__capacidade"],
        }
        for linha in agregado
    }


def itens_pendentes_de_programacao():
    """
    Itens de pedidos programáveis com saldo ainda não programado,
    ordenados pelo prazo do pedido (mais urgente primeiro).
    """
    itens = (
        ItemPedido.objects.filter(pedido__status__in=STATUS_PROGRAMAVEIS)
        .select_related("pedido__cliente", "produto")
        .annotate(
            programado=Coalesce(
                Sum("programacoes__quantidade", filter=Q(programacoes__ativo=True)),
                Decimal("0"),
                output_field=DecimalField(max_digits=12, decimal_places=3),
            )
        )
        .order_by("pedido__prazo", "pedido_id", "id")
    )
    pendentes = []
    for item in itens:
        item.saldo = item.quantidade - item.programado
        if item.saldo > 0:
            pendentes.append(item)
    return pendentes
