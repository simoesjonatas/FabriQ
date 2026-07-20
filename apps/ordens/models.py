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

from apps.cadastros.models import (
    Embalagem,
    Equipamento,
    MateriaPrima,
    Produto,
    Setor,
)
from apps.core import formatos
from apps.core.models import ModeloAuditado, ModeloBase
from apps.estoque.models import (
    Lote,
    SituacaoLote,
    criar_lote_interno,
    saldo,
)
from apps.pedidos.models import ItemPedido, StatusPedido

# Pedido "aprovado" para fins de OP: já analisado/programado e não encerrado
STATUS_PEDIDO_APTO_PARA_OP = {StatusPedido.PROGRAMADO, StatusPedido.EM_PRODUCAO}


def saldo_disponivel(item) -> Decimal:
    """
    Saldo fora da quarentena — o que pode ser consumido pela produção.
    """
    from apps.recebimento.models import local_quarentena

    return saldo(item) - saldo(item, local=local_quarentena())


class StatusFormula(models.TextChoices):
    VIGENTE = "VIGENTE", "Vigente"
    HISTORICA = "HISTORICA", "Histórica"


class Formula(ModeloBase):
    """
    Fórmula VERSIONADA (Etapa 3 do plano de correções): editar uma
    fórmula que já tem OP emitida cria uma nova versão e marca a
    anterior como histórica — nunca há substituição retroativa.
    """

    produto = models.ForeignKey(
        Produto,
        verbose_name="produto",
        on_delete=models.PROTECT,
        related_name="formulas",
    )
    nome = models.CharField(
        "nome",
        max_length=60,
        help_text="Identificação da fórmula. Ex.: “Padrão”, “Sem parabenos”.",
    )
    versao = models.PositiveIntegerField("versão", default=1)
    status = models.CharField(
        "situação da versão",
        max_length=10,
        choices=StatusFormula.choices,
        default=StatusFormula.VIGENTE,
    )
    rendimento = models.DecimalField(
        "rendimento",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Quantidade de produto que esta fórmula produz (na unidade do produto).",
    )
    observacoes = models.TextField("observações", blank=True)

    aprovada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="aprovada por",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    aprovada_em = models.DateTimeField("aprovada em", null=True, blank=True)

    class Meta:
        verbose_name = "fórmula"
        verbose_name_plural = "fórmulas"
        ordering = ["produto__nome", "nome", "-versao"]
        constraints = [
            models.UniqueConstraint(
                fields=["produto", "nome", "versao"],
                name="formula_nome_versao_unicos_por_produto",
                violation_error_message=(
                    "Este produto já tem esta versão da fórmula."
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.produto.codigo} · {self.nome} · v{self.versao}"

    @property
    def vigente(self) -> bool:
        return self.status == StatusFormula.VIGENTE

    @property
    def badge_status(self) -> str:
        return (
            "text-bg-success" if self.vigente else "text-bg-secondary"
        )

    @property
    def tem_op_emitida(self) -> bool:
        """OPs (em qualquer status) já emitidas com esta versão."""
        return self.ordens.exists()


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


class EtapaFormula(models.Model):
    """
    Etapa do processo produtivo definida na fórmula (Etapa 6d, PDF 5.5):
    sequência, instrução e parâmetros previstos. Congelada no snapshot da
    OP (Etapa 3) para comparação previsto × real.
    """

    formula = models.ForeignKey(
        Formula,
        verbose_name="fórmula",
        on_delete=models.CASCADE,
        related_name="etapas",
    )
    sequencia = models.PositiveIntegerField("sequência")
    instrucao = models.TextField("instrução")
    materia_prima = models.ForeignKey(
        MateriaPrima,
        verbose_name="material adicionado",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        help_text="Opcional: material adicionado nesta etapa.",
    )
    temperatura_prevista = models.DecimalField(
        "temperatura prevista (°C)", max_digits=7, decimal_places=2,
        null=True, blank=True,
    )
    tempo_previsto_min = models.DecimalField(
        "tempo previsto (min)", max_digits=7, decimal_places=1,
        null=True, blank=True,
    )
    velocidade_prevista = models.DecimalField(
        "velocidade prevista (rpm)", max_digits=8, decimal_places=1,
        null=True, blank=True,
    )

    class Meta:
        verbose_name = "etapa da fórmula"
        verbose_name_plural = "etapas da fórmula"
        ordering = ["formula_id", "sequencia", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["formula", "sequencia"],
                name="etapa_sequencia_unica_por_formula",
                violation_error_message="Já existe uma etapa com essa sequência.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.formula} · etapa {self.sequencia}"


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
    linha = models.ForeignKey(
        Setor,
        verbose_name="linha de produção",
        on_delete=models.PROTECT,
        related_name="ordens",
        null=True,
        blank=True,
        help_text="Setor/linha onde a OP será executada.",
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
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="supervisor",
        on_delete=models.PROTECT,
        related_name="ordens_como_supervisor",
        null=True,
        blank=True,
    )
    data_programada = models.DateField("data programada")
    prazo = models.DateField(
        "prazo",
        null=True,
        blank=True,
        help_text="Data limite para concluir a produção.",
    )
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

    lote_produto = models.ForeignKey(
        Lote,
        verbose_name="lote do produto acabado",
        on_delete=models.PROTECT,
        related_name="ordens_de_producao",
        null=True,
        blank=True,
        help_text=(
            "Lote interno reservado automaticamente na liberação da OP "
            "e confirmado na conclusão da produção."
        ),
    )

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

    def reservar_lote_produto(self, usuario) -> Lote:
        """
        Reserva o lote interno do produto acabado (gerado pela sequência).

        Chamado na liberação da OP — o lote já sai na impressão e nas
        etiquetas; a entrada em estoque só acontece na conclusão.
        """
        if self.lote_produto_id is None:
            self.lote_produto = criar_lote_interno(
                self.produto, usuario, situacao=SituacaoLote.EM_PRODUCAO
            )
            self.atualizado_por = usuario
            self.save()
        return self.lote_produto

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
        # Bloqueio: equipamento apto — liberado, limpo e calibrado (Etapa 6c)
        if self.equipamento_id is not None:
            impedimento = self.equipamento.motivo_impedimento_uso()
            condicoes.append(
                {
                    "rotulo": "Equipamento em condição de uso",
                    "ok": impedimento == "",
                    "detalhe": impedimento or "liberado, limpo e calibrado",
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


class SnapshotQuerySet(models.QuerySet):
    def update(self, **kwargs):
        from apps.auditoria.models import TrilhaImutavelError

        raise TrilhaImutavelError(
            "O snapshot da fórmula é imutável — não pode ser alterado."
        )

    def delete(self):
        from apps.auditoria.models import TrilhaImutavelError

        raise TrilhaImutavelError(
            "O snapshot da fórmula é imutável — não pode ser excluído."
        )


class SnapshotImutavelMixin(models.Model):
    """save() só cria; update e delete levantam exceção (padrão da Etapa 1)."""

    objects = SnapshotQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            from apps.auditoria.models import TrilhaImutavelError

            raise TrilhaImutavelError(
                "O snapshot da fórmula é imutável — não pode ser alterado."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from apps.auditoria.models import TrilhaImutavelError

        raise TrilhaImutavelError(
            "O snapshot da fórmula é imutável — não pode ser excluído."
        )


class SnapshotFormulaOP(SnapshotImutavelMixin):
    """
    Cópia congelada da fórmula no momento da LIBERAÇÃO da OP
    (PDF 2.4/4.2): a OP comprova para sempre com qual versão, rendimento,
    instruções e composição foi produzida — mesmo que a fórmula mude.
    """

    ordem = models.OneToOneField(
        OrdemProducao,
        verbose_name="ordem de produção",
        on_delete=models.PROTECT,
        related_name="snapshot_formula",
    )
    formula = models.ForeignKey(
        Formula,
        verbose_name="fórmula de origem",
        on_delete=models.PROTECT,
        related_name="snapshots",
    )
    nome = models.CharField("nome da fórmula", max_length=60)
    versao = models.PositiveIntegerField("versão")
    data_versao = models.DateTimeField(
        "data da versão",
        null=True,
        blank=True,
        help_text="Quando esta versão da fórmula entrou em vigor.",
    )
    rendimento = models.DecimalField(
        "rendimento", max_digits=12, decimal_places=3
    )
    instrucoes = models.TextField("instruções de fabricação", blank=True)

    congelado_em = models.DateTimeField("congelado em", auto_now_add=True)
    congelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="congelado por",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "snapshot da fórmula da OP"
        verbose_name_plural = "snapshots da fórmula das OPs"
        ordering = ["-congelado_em"]

    def __str__(self) -> str:
        return f"{self.ordem.numero} · {self.nome} · v{self.versao}"

    @classmethod
    def congelar(cls, ordem, usuario) -> SnapshotFormulaOP:
        """Congela a fórmula da OP (idempotente: reusa se já congelada)."""
        existente = getattr(ordem, "snapshot_formula", None)
        if existente is not None:
            return existente

        formula = ordem.formula
        snapshot = cls.objects.create(
            ordem=ordem,
            formula=formula,
            nome=formula.nome,
            versao=formula.versao,
            data_versao=formula.aprovada_em or formula.criado_em,
            rendimento=formula.rendimento,
            instrucoes=formula.observacoes,
            congelado_por=usuario,
        )
        fator = ordem.quantidade / formula.rendimento
        for componente in formula.componentes.all():
            escalada = (componente.quantidade * fator).quantize(
                Decimal("0.001"), rounding=ROUND_UP
            )
            item = componente.item
            ItemSnapshotFormulaOP.objects.create(
                snapshot=snapshot,
                materia_prima=componente.materia_prima,
                embalagem=componente.embalagem,
                item_codigo=item.codigo,
                item_nome=item.nome,
                item_unidade=item.get_unidade_display(),
                quantidade_teorica=componente.quantidade,
                quantidade_escalada=escalada,
            )
        # Congela também as etapas do processo (Etapa 6d)
        for etapa in formula.etapas.all():
            EtapaSnapshotOP.objects.create(
                snapshot=snapshot,
                sequencia=etapa.sequencia,
                instrucao=etapa.instrucao,
                material_codigo=(
                    etapa.materia_prima.codigo if etapa.materia_prima_id else ""
                ),
                temperatura_prevista=etapa.temperatura_prevista,
                tempo_previsto_min=etapa.tempo_previsto_min,
                velocidade_prevista=etapa.velocidade_prevista,
            )
        return snapshot


class ItemSnapshotFormulaOP(SnapshotImutavelMixin):
    snapshot = models.ForeignKey(
        SnapshotFormulaOP,
        verbose_name="snapshot",
        on_delete=models.CASCADE,
        related_name="itens",
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
    # Cópia textual: o cadastro pode ser renomeado, o snapshot não muda
    item_codigo = models.CharField("código do item", max_length=30)
    item_nome = models.CharField("nome do item", max_length=150)
    item_unidade = models.CharField("unidade", max_length=20, blank=True)
    quantidade_teorica = models.DecimalField(
        "quantidade teórica",
        max_digits=12,
        decimal_places=3,
        help_text="Para o rendimento base da fórmula.",
    )
    quantidade_escalada = models.DecimalField(
        "quantidade escalada",
        max_digits=12,
        decimal_places=3,
        help_text="Para a quantidade prevista da OP.",
    )

    class Meta:
        verbose_name = "item do snapshot da fórmula"
        verbose_name_plural = "itens do snapshot da fórmula"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(materia_prima__isnull=False) & Q(embalagem__isnull=True))
                    | (Q(materia_prima__isnull=True) & Q(embalagem__isnull=False))
                ),
                name="item_snapshot_exatamente_um_item",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_codigo} × {formatos.quantidade(self.quantidade_escalada)}"

    @property
    def item(self):
        return self.materia_prima or self.embalagem


class EtapaSnapshotOP(SnapshotImutavelMixin):
    """Etapa da fórmula congelada na liberação da OP (Etapa 6d)."""

    snapshot = models.ForeignKey(
        SnapshotFormulaOP,
        verbose_name="snapshot",
        on_delete=models.CASCADE,
        related_name="etapas",
    )
    sequencia = models.PositiveIntegerField("sequência")
    instrucao = models.TextField("instrução")
    material_codigo = models.CharField("material adicionado", max_length=30, blank=True)
    temperatura_prevista = models.DecimalField(
        "temperatura prevista (°C)", max_digits=7, decimal_places=2,
        null=True, blank=True,
    )
    tempo_previsto_min = models.DecimalField(
        "tempo previsto (min)", max_digits=7, decimal_places=1,
        null=True, blank=True,
    )
    velocidade_prevista = models.DecimalField(
        "velocidade prevista (rpm)", max_digits=8, decimal_places=1,
        null=True, blank=True,
    )

    class Meta:
        verbose_name = "etapa do snapshot da OP"
        verbose_name_plural = "etapas do snapshot da OP"
        ordering = ["sequencia", "id"]

    def __str__(self) -> str:
        return f"{self.snapshot.ordem.numero} · etapa {self.sequencia}"


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
