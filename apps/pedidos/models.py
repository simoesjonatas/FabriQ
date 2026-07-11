"""
Pedidos (Fase 3).

Regras do cronograma implementadas aqui:
- O pedido deve possuir cliente e pelo menos um produto (validado no formset).
- Um pedido não avança sem cumprir as regras da etapa atual (TRANSICOES).
- Alterações importantes ficam registradas em HistoricoPedido.
- Cancelamento exige motivo — nada é excluído definitivamente.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.cadastros.models import Cliente, Produto
from apps.core.models import ModeloAuditado


class StatusPedido(models.TextChoices):
    RECEBIDO = "RECEBIDO", "Recebido"
    EM_ANALISE = "EM_ANALISE", "Em análise"
    AGUARDANDO_MP = "AGUARDANDO_MP", "Aguardando MP"
    PROGRAMADO = "PROGRAMADO", "Programado"
    EM_PRODUCAO = "EM_PRODUCAO", "Em produção"
    CQ = "CQ", "Controle de qualidade"
    FINALIZADO = "FINALIZADO", "Finalizado"
    EXPEDIDO = "EXPEDIDO", "Expedido"
    CANCELADO = "CANCELADO", "Cancelado"


# Fluxo do cronograma (listas: a ordem define os botões na tela).
# De "Em análise" pode-se pular "Aguardando MP" quando a matéria-prima
# já está disponível. Cancelar é possível em qualquer etapa antes da
# expedição, sempre com motivo.
TRANSICOES: dict[str, list[str]] = {
    StatusPedido.RECEBIDO: [StatusPedido.EM_ANALISE, StatusPedido.CANCELADO],
    StatusPedido.EM_ANALISE: [
        StatusPedido.AGUARDANDO_MP,
        StatusPedido.PROGRAMADO,
        StatusPedido.CANCELADO,
    ],
    StatusPedido.AGUARDANDO_MP: [StatusPedido.PROGRAMADO, StatusPedido.CANCELADO],
    StatusPedido.PROGRAMADO: [StatusPedido.EM_PRODUCAO, StatusPedido.CANCELADO],
    StatusPedido.EM_PRODUCAO: [StatusPedido.CQ, StatusPedido.CANCELADO],
    StatusPedido.CQ: [StatusPedido.FINALIZADO, StatusPedido.CANCELADO],
    StatusPedido.FINALIZADO: [StatusPedido.EXPEDIDO, StatusPedido.CANCELADO],
    StatusPedido.EXPEDIDO: [],
    StatusPedido.CANCELADO: [],
}

# Enquanto o pedido está nestas etapas, cliente/itens ainda podem ser editados.
# A partir de "Programado" o PCP já se baseou nos dados: só status muda.
STATUS_EDITAVEIS = {
    StatusPedido.RECEBIDO,
    StatusPedido.EM_ANALISE,
    StatusPedido.AGUARDANDO_MP,
}

BADGE_POR_STATUS = {
    StatusPedido.RECEBIDO: "text-bg-secondary status-badge status-badge--recebido",
    StatusPedido.EM_ANALISE: "text-bg-info status-badge status-badge--analise",
    StatusPedido.AGUARDANDO_MP: "text-bg-warning status-badge status-badge--aguardando",
    StatusPedido.PROGRAMADO: "text-bg-primary status-badge status-badge--programado",
    StatusPedido.EM_PRODUCAO: "text-bg-primary status-badge status-badge--producao",
    StatusPedido.CQ: "text-bg-warning status-badge status-badge--qualidade",
    StatusPedido.FINALIZADO: "text-bg-success status-badge status-badge--finalizado",
    StatusPedido.EXPEDIDO: "text-bg-success status-badge status-badge--expedido",
    StatusPedido.CANCELADO: "text-bg-danger status-badge status-badge--cancelado",
}


class TransicaoInvalida(Exception):
    """Transição de status fora do fluxo permitido."""


class Pedido(ModeloAuditado):
    cliente = models.ForeignKey(
        Cliente,
        verbose_name="cliente",
        on_delete=models.PROTECT,
        related_name="pedidos",
    )
    status = models.CharField(
        "status",
        max_length=20,
        choices=StatusPedido.choices,
        default=StatusPedido.RECEBIDO,
    )
    prazo = models.DateField(
        "prazo de entrega",
        help_text="Data combinada com o cliente para a entrega.",
    )
    observacoes = models.TextField("observações", blank=True)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        return f"{self.numero} · {self.cliente}"

    def get_absolute_url(self) -> str:
        return reverse("pedidos:detalhe", args=[self.pk])

    @property
    def numero(self) -> str:
        return f"PED-{self.pk:05d}" if self.pk else "PED-novo"

    @property
    def editavel(self) -> bool:
        return self.status in STATUS_EDITAVEIS

    @property
    def atrasado(self) -> bool:
        if self.status in {StatusPedido.EXPEDIDO, StatusPedido.CANCELADO}:
            return False
        return self.prazo < timezone.localdate()

    @property
    def badge_status(self) -> str:
        return BADGE_POR_STATUS.get(
            self.status, "text-bg-secondary status-badge status-badge--recebido"
        )

    @property
    def proximos_status(self) -> list[tuple[str, str]]:
        """Avanços possíveis (sem o cancelamento, que tem botão próprio)."""
        rotulos = dict(StatusPedido.choices)
        return [
            (status, rotulos[status])
            for status in TRANSICOES[self.status]
            if status != StatusPedido.CANCELADO
        ]

    @property
    def pode_cancelar(self) -> bool:
        return self.pode_transicionar(StatusPedido.CANCELADO)

    def pode_transicionar(self, novo_status: str) -> bool:
        return novo_status in TRANSICOES.get(self.status, [])

    def transicionar(self, novo_status: str, usuario, motivo: str = "") -> None:
        """
        Muda o status validando o fluxo e registra no histórico.
        Cancelamento exige motivo.
        """
        if not self.pode_transicionar(novo_status):
            atual = self.get_status_display()
            novo = dict(StatusPedido.choices).get(novo_status, novo_status)
            raise TransicaoInvalida(
                f"O pedido não pode ir de “{atual}” para “{novo}”."
            )

        if novo_status == StatusPedido.CANCELADO and not motivo.strip():
            raise TransicaoInvalida("Informe o motivo do cancelamento.")

        status_anterior = self.status
        self.status = novo_status
        if novo_status == StatusPedido.CANCELADO:
            self.motivo_cancelamento = motivo.strip()
        self.atualizado_por = usuario
        self.save()

        descricao = (
            f"Status alterado de {dict(StatusPedido.choices)[status_anterior]} "
            f"para {dict(StatusPedido.choices)[novo_status]}"
        )
        if novo_status == StatusPedido.CANCELADO:
            descricao = f"Pedido cancelado. Motivo: {motivo.strip()}"

        HistoricoPedido.registrar(
            pedido=self,
            usuario=usuario,
            descricao=descricao,
            status_anterior=status_anterior,
            status_novo=novo_status,
        )


class ItemPedido(models.Model):
    pedido = models.ForeignKey(
        Pedido,
        verbose_name="pedido",
        on_delete=models.CASCADE,
        related_name="itens",
    )
    produto = models.ForeignKey(
        Produto,
        verbose_name="produto",
        on_delete=models.PROTECT,
        related_name="itens_de_pedido",
    )
    quantidade = models.DecimalField(
        "quantidade",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )

    class Meta:
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["pedido", "produto"],
                name="item_produto_unico_por_pedido",
                violation_error_message="Este produto já está no pedido.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.produto} × {self.quantidade}"


class HistoricoPedido(models.Model):
    pedido = models.ForeignKey(
        Pedido,
        verbose_name="pedido",
        on_delete=models.CASCADE,
        related_name="historico",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    data = models.DateTimeField("data", auto_now_add=True)
    descricao = models.TextField("descrição")
    status_anterior = models.CharField(
        "status anterior", max_length=20, choices=StatusPedido.choices, blank=True
    )
    status_novo = models.CharField(
        "status novo", max_length=20, choices=StatusPedido.choices, blank=True
    )

    class Meta:
        verbose_name = "histórico do pedido"
        verbose_name_plural = "históricos do pedido"
        ordering = ["-data", "-id"]

    def __str__(self) -> str:
        return f"{self.pedido.numero} · {self.descricao[:60]}"

    @classmethod
    def registrar(cls, pedido, usuario, descricao, status_anterior="", status_novo=""):
        return cls.objects.create(
            pedido=pedido,
            usuario=usuario,
            descricao=descricao,
            status_anterior=status_anterior,
            status_novo=status_novo,
        )
