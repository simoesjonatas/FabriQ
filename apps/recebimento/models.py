"""
Recebimento e Quarentena (Fase 6).

Fluxo:
1. O almoxarifado registra a NF com um ou mais itens (lote obrigatório).
2. Cada item gera uma ENTRADA automática de estoque no local "Quarentena".
3. A Qualidade decide item a item: Liberar (transfere para o destino),
   Reprovar ou Bloquear — sempre com responsável e histórico.

Critério de aceite do cronograma: nenhum material fica disponível para
produção antes da liberação — enquanto o saldo está no local Quarentena
e o item não foi liberado, ele não conta como disponível.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.cadastros.models import Embalagem, Fornecedor, MateriaPrima, Produto
from apps.core.models import ModeloAuditado
from apps.estoque.models import LocalEstoque, Lote

NOME_LOCAL_QUARENTENA = "Quarentena"


def local_quarentena() -> LocalEstoque:
    """Local padrão da quarentena (criado na primeira utilização)."""
    local, _criado = LocalEstoque.objects.get_or_create(
        nome=NOME_LOCAL_QUARENTENA,
        defaults={"descricao": "Materiais recebidos aguardando decisão da Qualidade."},
    )
    return local


class Recebimento(ModeloAuditado):
    fornecedor = models.ForeignKey(
        Fornecedor,
        verbose_name="fornecedor",
        on_delete=models.PROTECT,
        related_name="recebimentos",
    )
    nota_fiscal = models.CharField("nota fiscal", max_length=60)
    data_recebimento = models.DateField("data do recebimento", default=timezone.localdate)
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "recebimento"
        verbose_name_plural = "recebimentos"
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        return f"{self.numero} · NF {self.nota_fiscal} · {self.fornecedor}"

    def get_absolute_url(self) -> str:
        return reverse("recebimento:detalhe", args=[self.pk])

    @property
    def numero(self) -> str:
        return f"REC-{self.pk:05d}" if self.pk else "REC-novo"


class StatusQuarentena(models.TextChoices):
    EM_QUARENTENA = "EM_QUARENTENA", "Em quarentena"
    LIBERADO = "LIBERADO", "Liberado"
    REPROVADO = "REPROVADO", "Reprovado"
    BLOQUEADO = "BLOQUEADO", "Bloqueado"


# Decisões possíveis a partir de cada status
DECISOES_POSSIVEIS = {
    StatusQuarentena.EM_QUARENTENA: [
        StatusQuarentena.LIBERADO,
        StatusQuarentena.BLOQUEADO,
        StatusQuarentena.REPROVADO,
    ],
    StatusQuarentena.BLOQUEADO: [
        StatusQuarentena.LIBERADO,
        StatusQuarentena.REPROVADO,
    ],
    StatusQuarentena.LIBERADO: [],
    StatusQuarentena.REPROVADO: [],
}

BADGE_POR_STATUS_QUARENTENA = {
    StatusQuarentena.EM_QUARENTENA: "text-bg-warning",
    StatusQuarentena.LIBERADO: "text-bg-success",
    StatusQuarentena.REPROVADO: "text-bg-danger",
    StatusQuarentena.BLOQUEADO: "text-bg-dark",
}


class ItemRecebimento(models.Model):
    recebimento = models.ForeignKey(
        Recebimento,
        verbose_name="recebimento",
        on_delete=models.CASCADE,
        related_name="itens",
    )
    produto = models.ForeignKey(
        Produto,
        verbose_name="produto",
        on_delete=models.PROTECT,
        related_name="itens_de_recebimento",
        null=True,
        blank=True,
    )
    materia_prima = models.ForeignKey(
        MateriaPrima,
        verbose_name="matéria-prima",
        on_delete=models.PROTECT,
        related_name="itens_de_recebimento",
        null=True,
        blank=True,
    )
    embalagem = models.ForeignKey(
        Embalagem,
        verbose_name="embalagem",
        on_delete=models.PROTECT,
        related_name="itens_de_recebimento",
        null=True,
        blank=True,
    )
    lote = models.ForeignKey(
        Lote,
        verbose_name="lote",
        on_delete=models.PROTECT,
        related_name="itens_de_recebimento",
    )
    quantidade = models.DecimalField(
        "quantidade",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    status = models.CharField(
        "situação",
        max_length=20,
        choices=StatusQuarentena.choices,
        default=StatusQuarentena.EM_QUARENTENA,
    )

    class Meta:
        verbose_name = "item do recebimento"
        verbose_name_plural = "itens do recebimento"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        Q(produto__isnull=False)
                        & Q(materia_prima__isnull=True)
                        & Q(embalagem__isnull=True)
                    )
                    | (
                        Q(produto__isnull=True)
                        & Q(materia_prima__isnull=False)
                        & Q(embalagem__isnull=True)
                    )
                    | (
                        Q(produto__isnull=True)
                        & Q(materia_prima__isnull=True)
                        & Q(embalagem__isnull=False)
                    )
                ),
                name="item_recebimento_exatamente_um_item",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item} · lote {self.lote.codigo}"

    @property
    def item(self):
        return self.produto or self.materia_prima or self.embalagem

    @property
    def badge_status(self) -> str:
        return BADGE_POR_STATUS_QUARENTENA.get(self.status, "text-bg-secondary")

    @property
    def decisoes_possiveis(self) -> list[tuple[str, str]]:
        rotulos = dict(StatusQuarentena.choices)
        return [
            (status, rotulos[status])
            for status in DECISOES_POSSIVEIS[self.status]
        ]

    @property
    def dias_em_quarentena(self) -> int:
        return (timezone.localdate() - self.recebimento.data_recebimento).days


class TipoAnexo(models.TextChoices):
    COA = "COA", "COA (Certificado de Análise)"
    FISPQ = "FISPQ", "FISPQ"
    FOTO = "FOTO", "Foto"
    OUTRO = "OUTRO", "Outro"


class AnexoRecebimento(ModeloAuditado):
    recebimento = models.ForeignKey(
        Recebimento,
        verbose_name="recebimento",
        on_delete=models.CASCADE,
        related_name="anexos",
    )
    tipo = models.CharField(
        "tipo", max_length=10, choices=TipoAnexo.choices, default=TipoAnexo.OUTRO
    )
    arquivo = models.FileField(
        "arquivo",
        upload_to="recebimentos/%Y/%m/",
        validators=[
            FileExtensionValidator(["pdf", "jpg", "jpeg", "png", "webp"]),
        ],
        help_text="PDF ou imagem (JPG, PNG, WEBP).",
    )
    descricao = models.CharField("descrição", max_length=120, blank=True)

    class Meta:
        verbose_name = "anexo do recebimento"
        verbose_name_plural = "anexos do recebimento"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} · {self.arquivo.name}"


class DecisaoQuarentena(models.Model):
    """Histórico das decisões da Qualidade sobre um item recebido."""

    item = models.ForeignKey(
        ItemRecebimento,
        verbose_name="item",
        on_delete=models.CASCADE,
        related_name="decisoes",
    )
    decisao = models.CharField(
        "decisão", max_length=20, choices=StatusQuarentena.choices
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="responsável",
        on_delete=models.PROTECT,
        related_name="+",
    )
    data = models.DateTimeField("data", auto_now_add=True)
    observacoes = models.TextField("observações", blank=True)
    local_destino = models.ForeignKey(
        LocalEstoque,
        verbose_name="local de destino",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        help_text="Para onde o material foi na liberação.",
    )

    class Meta:
        verbose_name = "decisão de quarentena"
        verbose_name_plural = "decisões de quarentena"
        ordering = ["-data", "-id"]

    def __str__(self) -> str:
        return f"{self.get_decisao_display()} · {self.item}"
