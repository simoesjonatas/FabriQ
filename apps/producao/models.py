"""
Produção (Fase 9).

A execução de uma Ordem de Produção liberada é registrada aqui:
início, paradas (com motivo), ocorrências, fotos e conclusão.

Ao CONCLUIR, o sistema fecha o ciclo produtivo em transação atômica:
- consome os materiais do snapshot da OP baixando o estoque em FEFO
  (o lote que vence primeiro sai primeiro), sempre fora da Quarentena
  — material só é consumido depois de liberado pela Qualidade;
- dá entrada do produto acabado com o lote produzido no local escolhido.

Movimentações de estoque são imutáveis (Fase 5): uma vez concluída, a
execução não é editada — eventuais correções são novas movimentações.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from apps.cadastros.itens import campo_do_item
from apps.core import formatos
from apps.core.models import ModeloAuditado
from apps.estoque.models import (
    Lote,
    Movimentacao,
    TipoMovimentacao,
    posicoes_para_consumo,
)
from apps.ordens.models import OrdemProducao, StatusOP
from apps.pedidos.models import HistoricoPedido, StatusPedido


class ProducaoInsuficiente(Exception):
    """Estoque disponível não cobre um material necessário à conclusão."""


def consumir_material_fefo(item, quantidade, *, usuario, motivo, documento, excluir_local):
    """
    Baixa `quantidade` de `item` do estoque em FEFO, criando SAÍDAs por
    (lote, local). Ignora o local `excluir_local` (a Quarentena).
    Levanta ProducaoInsuficiente se o disponível não cobrir o necessário.
    """
    posicoes = posicoes_para_consumo(item, excluir_local=excluir_local)
    disponivel = sum((p["saldo"] for p in posicoes), Decimal("0"))
    if disponivel < quantidade:
        raise ProducaoInsuficiente(
            f"Estoque insuficiente de {item.codigo} · {item.nome}: "
            f"necessário {formatos.quantidade(quantidade)}, "
            f"disponível {formatos.quantidade(disponivel)}."
        )

    restante = quantidade
    campo = campo_do_item(item)
    for posicao in posicoes:
        if restante <= 0:
            break
        usar = min(restante, posicao["saldo"])
        movimentacao = Movimentacao(
            tipo=TipoMovimentacao.SAIDA,
            lote=posicao["lote"],
            quantidade=usar,
            local_origem=posicao["local"],
            motivo=motivo,
            documento=documento,
            criado_por=usuario,
            atualizado_por=usuario,
            **{campo: item},
        )
        movimentacao.full_clean()
        movimentacao.save()
        restante -= usar


class ExecucaoOP(ModeloAuditado):
    ordem = models.OneToOneField(
        OrdemProducao,
        verbose_name="ordem de produção",
        on_delete=models.PROTECT,
        related_name="execucao",
    )
    iniciado_em = models.DateTimeField("início da produção", default=timezone.now)
    iniciado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="iniciada por",
        on_delete=models.PROTECT,
        related_name="+",
    )
    concluido_em = models.DateTimeField("fim da produção", null=True, blank=True)
    concluido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="concluída por",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    quantidade_produzida = models.DecimalField(
        "quantidade produzida",
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
    )
    perdas = models.DecimalField(
        "perdas", max_digits=12, decimal_places=3, default=Decimal("0")
    )
    lote_produzido = models.ForeignKey(
        Lote,
        verbose_name="lote do produto acabado",
        on_delete=models.PROTECT,
        related_name="execucoes",
        null=True,
        blank=True,
    )
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "execução da produção"
        verbose_name_plural = "execuções da produção"
        ordering = ["-iniciado_em", "-id"]

    def __str__(self) -> str:
        return f"Execução de {self.ordem.numero}"

    @property
    def concluida(self) -> bool:
        return self.concluido_em is not None

    @property
    def tempo_paradas(self) -> timedelta:
        total = timedelta()
        for parada in self.paradas.all():
            total += parada.duracao
        return total

    @property
    def tempo_total(self) -> timedelta:
        fim = self.concluido_em or timezone.now()
        return fim - self.iniciado_em

    @property
    def tempo_produtivo(self) -> timedelta:
        produtivo = self.tempo_total - self.tempo_paradas
        return produtivo if produtivo > timedelta() else timedelta()

    @property
    def tem_parada_aberta(self) -> bool:
        return self.paradas.filter(fim__isnull=True).exists()

    @classmethod
    def iniciar(cls, ordem, usuario) -> ExecucaoOP:
        """Inicia a produção de uma OP liberada e move o pedido."""
        if ordem.status != StatusOP.LIBERADA:
            raise ValidationError(
                f"A OP {ordem.numero} precisa estar “Liberada” para iniciar a produção."
            )

        execucao = cls.objects.create(
            ordem=ordem,
            iniciado_por=usuario,
            criado_por=usuario,
            atualizado_por=usuario,
        )
        ordem.status = StatusOP.EM_PRODUCAO
        ordem.atualizado_por = usuario
        ordem.save()

        pedido = ordem.pedido
        if pedido.status == StatusPedido.PROGRAMADO:
            pedido.transicionar(StatusPedido.EM_PRODUCAO, usuario)
        else:
            HistoricoPedido.registrar(
                pedido=pedido,
                usuario=usuario,
                descricao=f"Produção iniciada pela OP {ordem.numero}",
            )
        return execucao

    def concluir(
        self,
        *,
        usuario,
        quantidade_produzida,
        perdas,
        lote_codigo,
        validade,
        local_destino,
    ) -> None:
        """
        Conclui a produção: consome materiais (FEFO, fora da quarentena)
        e dá entrada do produto acabado. Deve rodar dentro de uma
        transação (a view garante transaction.atomic).
        """
        from apps.ordens.models import HistoricoOP
        from apps.recebimento.models import local_quarentena

        if self.ordem.status != StatusOP.EM_PRODUCAO:
            raise ValidationError("A produção não está em andamento.")

        quarentena = local_quarentena()
        documento = self.ordem.numero

        for material in self.ordem.materiais.all():
            consumir_material_fefo(
                material.item,
                material.quantidade_necessaria,
                usuario=usuario,
                motivo=f"Consumo na produção {self.ordem.numero}",
                documento=documento,
                excluir_local=quarentena,
            )

        produto = self.ordem.produto
        lote_produto, _criado = Lote.objects.get_or_create(
            produto=produto,
            codigo=lote_codigo,
            defaults={
                "validade": validade,
                "criado_por": usuario,
                "atualizado_por": usuario,
            },
        )

        entrada = Movimentacao(
            tipo=TipoMovimentacao.ENTRADA,
            produto=produto,
            lote=lote_produto,
            quantidade=quantidade_produzida,
            local_destino=local_destino,
            motivo=f"Produção concluída {self.ordem.numero}",
            documento=documento,
            criado_por=usuario,
            atualizado_por=usuario,
        )
        entrada.full_clean()
        entrada.save()

        self.quantidade_produzida = quantidade_produzida
        self.perdas = perdas
        self.lote_produzido = lote_produto
        self.concluido_em = timezone.now()
        self.concluido_por = usuario
        self.atualizado_por = usuario
        self.save()

        self.ordem.status = StatusOP.CONCLUIDA
        self.ordem.atualizado_por = usuario
        self.ordem.save()

        HistoricoOP.registrar(
            self.ordem,
            usuario,
            f"Produção concluída: {formatos.quantidade(quantidade_produzida)} "
            f"{produto.get_unidade_display().lower()} no lote {lote_codigo}"
            + (
                f", {formatos.quantidade(perdas)} de perdas"
                if perdas
                else ""
            ),
        )
        HistoricoPedido.registrar(
            pedido=self.ordem.pedido,
            usuario=usuario,
            descricao=(
                f"Produção da OP {self.ordem.numero} concluída "
                f"({formatos.quantidade(quantidade_produzida)} "
                f"{produto.get_unidade_display().lower()}, lote {lote_codigo})"
            ),
        )


class MotivoParada(models.TextChoices):
    MANUTENCAO = "MANUTENCAO", "Manutenção"
    FALTA_MATERIAL = "FALTA_MATERIAL", "Falta de material"
    SETUP = "SETUP", "Setup / troca"
    LIMPEZA = "LIMPEZA", "Limpeza"
    REFEICAO = "REFEICAO", "Refeição / intervalo"
    FALTA_OPERADOR = "FALTA_OPERADOR", "Falta de operador"
    OUTRO = "OUTRO", "Outro"


class Parada(models.Model):
    execucao = models.ForeignKey(
        ExecucaoOP,
        verbose_name="execução",
        on_delete=models.CASCADE,
        related_name="paradas",
    )
    motivo = models.CharField("motivo", max_length=20, choices=MotivoParada.choices)
    inicio = models.DateTimeField("início", default=timezone.now)
    fim = models.DateTimeField("fim", null=True, blank=True)
    observacoes = models.CharField("observações", max_length=200, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrada por",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = "parada"
        verbose_name_plural = "paradas"
        ordering = ["-inicio", "-id"]

    def __str__(self) -> str:
        return f"{self.get_motivo_display()} · {self.execucao.ordem.numero}"

    @property
    def em_aberto(self) -> bool:
        return self.fim is None

    @property
    def duracao(self) -> timedelta:
        fim = self.fim or timezone.now()
        return fim - self.inicio


class Ocorrencia(models.Model):
    execucao = models.ForeignKey(
        ExecucaoOP,
        verbose_name="execução",
        on_delete=models.CASCADE,
        related_name="ocorrencias",
    )
    descricao = models.TextField("descrição")
    data = models.DateTimeField("data", auto_now_add=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrada por",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = "ocorrência"
        verbose_name_plural = "ocorrências"
        ordering = ["-data", "-id"]

    def __str__(self) -> str:
        return self.descricao[:60]


class FotoProducao(ModeloAuditado):
    execucao = models.ForeignKey(
        ExecucaoOP,
        verbose_name="execução",
        on_delete=models.CASCADE,
        related_name="fotos",
    )
    arquivo = models.FileField(
        "arquivo",
        upload_to="producao/%Y/%m/",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
        help_text="Foto do processo (JPG, PNG ou WEBP).",
    )
    descricao = models.CharField("descrição", max_length=120, blank=True)

    class Meta:
        verbose_name = "foto da produção"
        verbose_name_plural = "fotos da produção"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.descricao or self.arquivo.name
