"""
Expedição vinculada a lotes (Etapa 9 do plano de correções).

O pedido só é expedido com vínculo a lote **aprovado** pelo CQ: cada
`ItemExpedicao` aponta o lote acabado (situação `APROVADO`) e a
quantidade, gerando uma `Movimentacao` de SAÍDA do estoque de produto
acabado. Expedição parcial mantém saldo pendente por item; o lote
expedido passa à situação `EXPEDIDO`.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

from apps.core import formatos
from apps.core.models import ModeloAuditado
from apps.estoque.models import (
    Lote,
    Movimentacao,
    SituacaoLote,
    TipoMovimentacao,
    locais_do_lote,
)
from apps.pedidos.models import ItemPedido, Pedido


class Expedicao(ModeloAuditado):
    pedido = models.ForeignKey(
        Pedido,
        verbose_name="pedido",
        on_delete=models.PROTECT,
        related_name="expedicoes",
    )
    data = models.DateField("data da expedição")
    nota_fiscal = models.CharField("nota fiscal", max_length=60, blank=True)
    transportadora = models.CharField("transportadora", max_length=120, blank=True)
    conferente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="conferente",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="responsável",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "expedição"
        verbose_name_plural = "expedições"
        ordering = ["-data", "-id"]

    def __str__(self) -> str:
        return f"{self.numero} · {self.pedido.numero}"

    def get_absolute_url(self) -> str:
        return reverse("expedicao:detalhe", args=[self.pk])

    @property
    def numero(self) -> str:
        return f"EXP-{self.pk:05d}" if self.pk else "EXP-nova"


class ItemExpedicao(models.Model):
    expedicao = models.ForeignKey(
        Expedicao,
        verbose_name="expedição",
        on_delete=models.CASCADE,
        related_name="itens",
    )
    item_pedido = models.ForeignKey(
        ItemPedido,
        verbose_name="item do pedido",
        on_delete=models.PROTECT,
        related_name="expedicoes",
    )
    lote = models.ForeignKey(
        Lote,
        verbose_name="lote acabado",
        on_delete=models.PROTECT,
        related_name="expedicoes",
    )
    quantidade = models.DecimalField(
        "quantidade",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    movimentacao = models.ForeignKey(
        Movimentacao,
        verbose_name="movimentação de saída",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "item da expedição"
        verbose_name_plural = "itens da expedição"
        ordering = ["id"]

    def __str__(self) -> str:
        return (
            f"{self.item_pedido.produto.codigo} · lote {self.lote.codigo} × "
            f"{formatos.quantidade(self.quantidade)}"
        )


def registrar_expedicao(
    *, pedido, data, usuario, linhas, nota_fiscal="", transportadora="",
    conferente=None, responsavel=None, observacoes="",
) -> Expedicao:
    """
    Cria uma expedição do pedido baixando o produto acabado por lote.

    `linhas`: [(item_pedido, lote, quantidade)]. Cada lote precisa estar
    APROVADO (Etapa 5/8), ser do produto do item e ter saldo. Gera uma
    SAÍDA de estoque por item e passa o lote a EXPEDIDO. Deve rodar em
    transaction.atomic.
    """
    if not linhas:
        raise ValidationError("Informe ao menos um item para expedir.")

    erros = []
    posicoes_por_lote = {}
    for item_pedido, lote, quantidade in linhas:
        if lote.produto_id != item_pedido.produto_id:
            erros.append(
                f"Lote {lote.codigo} não é do produto {item_pedido.produto.codigo}."
            )
            continue
        if not lote.pode_ser_expedido():
            erros.append(
                f"Lote {lote.codigo} não está liberado para expedição "
                f"(situação: {lote.get_situacao_display()})."
            )
            continue
        posicoes = locais_do_lote(lote)
        disponivel = sum((p["saldo"] for p in posicoes), Decimal("0"))
        if quantidade > disponivel:
            erros.append(
                f"Lote {lote.codigo}: expedido {formatos.quantidade(quantidade)}, "
                f"disponível {formatos.quantidade(disponivel)}."
            )
            continue
        posicoes_por_lote[lote.pk] = posicoes
    if erros:
        raise ValidationError(erros)

    expedicao = Expedicao.objects.create(
        pedido=pedido,
        data=data,
        nota_fiscal=nota_fiscal.strip(),
        transportadora=transportadora.strip(),
        conferente=conferente,
        responsavel=responsavel or usuario,
        observacoes=observacoes,
        criado_por=usuario,
        atualizado_por=usuario,
    )
    for item_pedido, lote, quantidade in linhas:
        local = posicoes_por_lote[lote.pk][0]["local"]
        movimentacao = Movimentacao(
            tipo=TipoMovimentacao.SAIDA,
            produto=lote.produto,
            lote=lote,
            quantidade=quantidade,
            local_origem=local,
            motivo=f"Expedição {expedicao.numero} — {pedido.numero}",
            documento=f"NF {nota_fiscal}".strip(),
            criado_por=usuario,
            atualizado_por=usuario,
        )
        movimentacao.full_clean()
        movimentacao.save()

        ItemExpedicao.objects.create(
            expedicao=expedicao,
            item_pedido=item_pedido,
            lote=lote,
            quantidade=quantidade,
            movimentacao=movimentacao,
        )

        if lote.situacao != SituacaoLote.EXPEDIDO:
            lote.situacao = SituacaoLote.EXPEDIDO
            lote.salvar_com_usuario(usuario)

    return expedicao
