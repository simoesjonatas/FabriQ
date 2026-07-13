"""
Ordens de Produção (Fase 8).

Regras obrigatórias do cronograma implementadas aqui:
a OP só pode ser LIBERADA quando houver
  1. pedido apto (programado/em produção — analisado e não cancelado),
  2. equipamento definido,
  3. operador definido,
  4. matéria-prima liberada + estoque suficiente — para cada material do
     snapshot, o saldo DISPONÍVEL (fora do local Quarentena) precisa
     cobrir o necessário. Material só sai da quarentena pela decisão
     da Qualidade (Fase 6), então "disponível" já significa "liberado".

Os materiais necessários são um SNAPSHOT da fórmula no momento em que a
OP é salva (escalados por quantidade ÷ rendimento): mudar a fórmula
depois não altera OPs existentes.
"""

from decimal import ROUND_UP, Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse

from apps.cadastros.models import Embalagem, Equipamento, MateriaPrima, Produto
from apps.core import formatos
from apps.core.models import ModeloAuditado, ModeloBase
from apps.estoque.models import saldo
from apps.pedidos.models import ItemPedido, StatusPedido

# Pedido "aprovado" para fins de OP: já analisado/programado e não encerrado
STATUS_PEDIDO_APTO_PARA_OP = {StatusPedido.PROGRAMADO, StatusPedido.EM_PRODUCAO}


def saldo_disponivel(item) -> Decimal:
    """
    Saldo fora da quarentena — o que pode ser consumido pela produção.
    """
    from apps.recebimento.models import local_quarentena

    return saldo(item) - saldo(item, local=local_quarentena())


class Formula(ModeloBase):
    produto = models.ForeignKey(
        Produto,
        verbose_name="produto",
        on_delete=models.PROTECT,
        related_name="formulas",
    )
    nome = models.CharField(
        "nome",
        max_length=60,
        help_text="Identificação da versão. Ex.: “Padrão”, “v2 sem parabenos”.",
    )
    rendimento = models.DecimalField(
        "rendimento",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Quantidade de produto que esta fórmula produz (na unidade do produto).",
    )
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "fórmula"
        verbose_name_plural = "fórmulas"
        ordering = ["produto__nome", "nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["produto", "nome"],
                name="formula_nome_unico_por_produto",
                violation_error_message="Este produto já tem uma fórmula com esse nome.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.produto.codigo} · {self.nome}"


class ComponenteFormula(models.Model):
    formula = models.ForeignKey(
        Formula,
        verbose_name="fórmula",
        on_delete=models.CASCADE,
        related_name="componentes",
    )
    materia_prima = models.ForeignKey(
        MateriaPrima,
        verbose_name="matéria-prima",
        on_delete=models.PROTECT,
        related_name="usos_em_formulas",
        null=True,
        blank=True,
    )
    embalagem = models.ForeignKey(
        Embalagem,
        verbose_name="embalagem",
        on_delete=models.PROTECT,
        related_name="usos_em_formulas",
        null=True,
        blank=True,
    )
    quantidade = models.DecimalField(
        "quantidade",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Quantidade para o rendimento base da fórmula.",
    )

    class Meta:
        verbose_name = "componente da fórmula"
        verbose_name_plural = "componentes da fórmula"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(materia_prima__isnull=False) & Q(embalagem__isnull=True))
                    | (Q(materia_prima__isnull=True) & Q(embalagem__isnull=False))
                ),
                name="componente_exatamente_um_item",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item} × {formatos.quantidade(self.quantidade)}"

    @property
    def item(self):
        return self.materia_prima or self.embalagem


class StatusOP(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    LIBERADA = "LIBERADA", "Liberada"
    EM_PRODUCAO = "EM_PRODUCAO", "Em produção"
    CONCLUIDA = "CONCLUIDA", "Concluída"
    CANCELADA = "CANCELADA", "Cancelada"


BADGE_POR_STATUS_OP = {
    StatusOP.RASCUNHO: "text-bg-secondary",
    StatusOP.LIBERADA: "text-bg-primary",
    StatusOP.EM_PRODUCAO: "text-bg-warning",
    StatusOP.CONCLUIDA: "text-bg-success",
    StatusOP.CANCELADA: "text-bg-danger",
}


class OrdemProducao(ModeloAuditado):
    item_pedido = models.ForeignKey(
        ItemPedido,
        verbose_name="item do pedido",
        on_delete=models.PROTECT,
        related_name="ordens",
    )
    formula = models.ForeignKey(
        Formula,
        verbose_name="fórmula",
        on_delete=models.PROTECT,
        related_name="ordens",
    )
    quantidade = models.DecimalField(
        "quantidade prevista",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    equipamento = models.ForeignKey(
        Equipamento,
        verbose_name="equipamento",
        on_delete=models.PROTECT,
        related_name="ordens",
        null=True,
        blank=True,
        help_text="Obrigatório para liberar a OP.",
    )
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="operador",
        on_delete=models.PROTECT,
        related_name="ordens_como_operador",
        null=True,
        blank=True,
        help_text="Obrigatório para liberar a OP.",
    )
    data_programada = models.DateField("data programada")
    status = models.CharField(
        "status",
        max_length=20,
        choices=StatusOP.choices,
        default=StatusOP.RASCUNHO,
    )
    observacoes = models.TextField("observações", blank=True)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)

    liberado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="liberada por",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    liberado_em = models.DateTimeField("liberada em", null=True, blank=True)

    class Meta:
        verbose_name = "ordem de produção"
        verbose_name_plural = "ordens de produção"
        ordering = ["-criado_em", "-id"]

    def __str__(self) -> str:
        return f"{self.numero} · {self.produto}"

    def get_absolute_url(self) -> str:
        return reverse("ordens:detalhe", args=[self.pk])

    @property
    def numero(self) -> str:
        return f"OP-{self.pk:05d}" if self.pk else "OP-nova"

    @property
    def produto(self) -> Produto:
        return self.item_pedido.produto

    @property
    def pedido(self):
        return self.item_pedido.pedido

    @property
    def badge_status(self) -> str:
        return BADGE_POR_STATUS_OP.get(self.status, "text-bg-secondary")

    @property
    def editavel(self) -> bool:
        return self.status == StatusOP.RASCUNHO

    @property
    def pode_cancelar(self) -> bool:
        return self.status in {
            StatusOP.RASCUNHO,
            StatusOP.LIBERADA,
            StatusOP.EM_PRODUCAO,
        }

    def gerar_materiais(self) -> None:
        """(Re)cria o snapshot de materiais a partir da fórmula."""
        self.materiais.all().delete()
        fator = self.quantidade / self.formula.rendimento
        for componente in self.formula.componentes.all():
            necessario = (componente.quantidade * fator).quantize(
                Decimal("0.001"), rounding=ROUND_UP
            )
            MaterialOP.objects.create(
                ordem=self,
                materia_prima=componente.materia_prima,
                embalagem=componente.embalagem,
                quantidade_necessaria=necessario,
            )

    def condicoes_liberacao(self) -> list[dict]:
        """
        Checklist das regras obrigatórias. Cada condição:
        {"rotulo", "ok", "detalhe"}.
        """
        condicoes = []

        pedido = self.pedido
        pedido_ok = pedido.status in STATUS_PEDIDO_APTO_PARA_OP
        condicoes.append(
            {
                "rotulo": "Pedido aprovado e programado",
                "ok": pedido_ok,
                "detalhe": f"{pedido.numero} está “{pedido.get_status_display()}”",
            }
        )

        condicoes.append(
            {
                "rotulo": "Equipamento definido",
                "ok": self.equipamento_id is not None,
                "detalhe": str(self.equipamento) if self.equipamento_id else "—",
            }
        )
        condicoes.append(
            {
                "rotulo": "Operador definido",
                "ok": self.operador_id is not None,
                "detalhe": str(self.operador) if self.operador_id else "—",
            }
        )

        for material in self.materiais.all():
            disponivel = material.disponivel
            ok = disponivel >= material.quantidade_necessaria
            unidade = material.item.get_unidade_display().lower()
            condicoes.append(
                {
                    "rotulo": f"Estoque liberado de {material.item.codigo}",
                    "ok": ok,
                    "detalhe": (
                        f"necessário {formatos.quantidade(material.quantidade_necessaria)}, "
                        f"disponível {formatos.quantidade(disponivel)} {unidade}"
                    ),
                }
            )

        return condicoes

    @property
    def pode_liberar(self) -> bool:
        return self.editavel and all(
            condicao["ok"] for condicao in self.condicoes_liberacao()
        )


class MaterialOP(models.Model):
    """Snapshot dos materiais necessários no momento da emissão da OP."""

    ordem = models.ForeignKey(
        OrdemProducao,
        verbose_name="ordem de produção",
        on_delete=models.CASCADE,
        related_name="materiais",
    )
    materia_prima = models.ForeignKey(
        MateriaPrima,
        verbose_name="matéria-prima",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    embalagem = models.ForeignKey(
        Embalagem,
        verbose_name="embalagem",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    quantidade_necessaria = models.DecimalField(
        "quantidade necessária", max_digits=12, decimal_places=3
    )

    class Meta:
        verbose_name = "material da OP"
        verbose_name_plural = "materiais da OP"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(materia_prima__isnull=False) & Q(embalagem__isnull=True))
                    | (Q(materia_prima__isnull=True) & Q(embalagem__isnull=False))
                ),
                name="material_op_exatamente_um_item",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item} × {formatos.quantidade(self.quantidade_necessaria)}"

    @property
    def item(self):
        return self.materia_prima or self.embalagem

    @property
    def disponivel(self) -> Decimal:
        return saldo_disponivel(self.item)


class HistoricoOP(models.Model):
    ordem = models.ForeignKey(
        OrdemProducao,
        verbose_name="ordem de produção",
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

    class Meta:
        verbose_name = "histórico da OP"
        verbose_name_plural = "históricos da OP"
        ordering = ["-data", "-id"]

    def __str__(self) -> str:
        return f"{self.ordem.numero} · {self.descricao[:60]}"

    @classmethod
    def registrar(cls, ordem, usuario, descricao):
        return cls.objects.create(ordem=ordem, usuario=usuario, descricao=descricao)
