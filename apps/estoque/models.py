"""
Estoque (Fase 5).

Princípios:
- Movimentações são IMUTÁVEIS: não há edição nem exclusão; corrige-se
  lançando a movimentação inversa (ajuste). Isso garante o histórico
  exigido pelo cronograma (usuário, data, hora, tipo, quantidade,
  motivo, lote, origem e destino).
- O saldo nunca é um campo: é sempre calculado das movimentações,
  por item, lote e local.
- Um movimento se refere a exatamente UM item: produto, matéria-prima
  ou embalagem.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.cadastros.itens import campo_do_item
from apps.cadastros.models import Embalagem, MateriaPrima, Produto
from apps.core.models import ModeloAuditado, ModeloBase

DIAS_ALERTA_VALIDADE = 30


class LocalEstoque(ModeloBase):
    """Localização física: almoxarifado, quarentena, produção, expedição..."""

    nome = models.CharField("nome", max_length=100, unique=True)
    descricao = models.TextField("descrição", blank=True)

    class Meta:
        verbose_name = "local de estoque"
        verbose_name_plural = "locais de estoque"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class SituacaoValidade(models.TextChoices):
    SEM_VALIDADE = "SEM_VALIDADE", "Sem validade"
    OK = "OK", "Dentro da validade"
    VENCE_EM_BREVE = "VENCE_EM_BREVE", "Vence em breve"
    VENCIDO = "VENCIDO", "Vencido"


class SituacaoLote(models.TextChoices):
    """
    Situação controlada do lote (Etapa 5 do plano de correções, PDF 4.1).
    Complementa a validade e o local físico: é o estado que o sistema
    consulta para IMPEDIR a ação irregular (consumo/expedição).
    """

    EM_PRODUCAO = "EM_PRODUCAO", "Em produção"
    AGUARDANDO_CQ = "AGUARDANDO_CQ", "Aguardando CQ"
    EM_ANALISE = "EM_ANALISE", "Em análise"
    APROVADO = "APROVADO", "Aprovado"
    REPROVADO = "REPROVADO", "Reprovado"
    BLOQUEADO = "BLOQUEADO", "Bloqueado"
    EXPEDIDO = "EXPEDIDO", "Expedido"
    RECOLHIDO = "RECOLHIDO", "Recolhido"
    DEVOLVIDO = "DEVOLVIDO", "Devolvido"


BADGE_POR_SITUACAO_LOTE = {
    SituacaoLote.EM_PRODUCAO: "text-bg-info",
    SituacaoLote.AGUARDANDO_CQ: "text-bg-warning",
    SituacaoLote.EM_ANALISE: "text-bg-info",
    SituacaoLote.APROVADO: "text-bg-success",
    SituacaoLote.REPROVADO: "text-bg-danger",
    SituacaoLote.BLOQUEADO: "text-bg-dark",
    SituacaoLote.EXPEDIDO: "text-bg-primary",
    SituacaoLote.RECOLHIDO: "text-bg-danger",
    SituacaoLote.DEVOLVIDO: "text-bg-secondary",
}

# Situações que impedem consumo na produção (além de vencido).
SITUACOES_BLOQUEIAM_CONSUMO = {
    SituacaoLote.REPROVADO: "reprovado no controle de qualidade",
    SituacaoLote.BLOQUEADO: "bloqueado",
    SituacaoLote.EXPEDIDO: "já expedido",
    SituacaoLote.RECOLHIDO: "recolhido",
    SituacaoLote.DEVOLVIDO: "devolvido ao fornecedor",
}


class Lote(ModeloAuditado):
    """
    Lote de um item, com validade opcional. O vínculo é com exatamente
    um item (produto, matéria-prima ou embalagem).

    `codigo` é o LOTE INTERNO — para lotes novos ele é gerado
    automaticamente pela sequência (`criar_lote_interno`); o lote
    impresso pelo fornecedor fica em `lote_fornecedor`.

    `situacao` é o estado controlado (Etapa 5): recebidos nascem
    AGUARDANDO_CQ e a decisão da quarentena os move para APROVADO/
    REPROVADO/BLOQUEADO; produzidos nascem EM_PRODUCAO.
    """

    codigo = models.CharField("lote interno", max_length=50)
    lote_fornecedor = models.CharField(
        "lote do fornecedor",
        max_length=60,
        blank=True,
        help_text="Código impresso pelo fornecedor na embalagem/laudo.",
    )
    validade = models.DateField("validade", null=True, blank=True)
    situacao = models.CharField(
        "situação",
        max_length=20,
        choices=SituacaoLote.choices,
        default=SituacaoLote.AGUARDANDO_CQ,
    )
    produto = models.ForeignKey(
        Produto,
        verbose_name="produto",
        on_delete=models.PROTECT,
        related_name="lotes",
        null=True,
        blank=True,
    )
    materia_prima = models.ForeignKey(
        MateriaPrima,
        verbose_name="matéria-prima",
        on_delete=models.PROTECT,
        related_name="lotes",
        null=True,
        blank=True,
    )
    embalagem = models.ForeignKey(
        Embalagem,
        verbose_name="embalagem",
        on_delete=models.PROTECT,
        related_name="lotes",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "lote"
        verbose_name_plural = "lotes"
        ordering = ["validade", "codigo"]
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
                name="lote_exatamente_um_item",
            ),
            models.UniqueConstraint(
                fields=["produto", "codigo"],
                condition=Q(produto__isnull=False),
                name="lote_unico_por_produto",
            ),
            models.UniqueConstraint(
                fields=["materia_prima", "codigo"],
                condition=Q(materia_prima__isnull=False),
                name="lote_unico_por_materia_prima",
            ),
            models.UniqueConstraint(
                fields=["embalagem", "codigo"],
                condition=Q(embalagem__isnull=False),
                name="lote_unico_por_embalagem",
            ),
        ]

    def __str__(self) -> str:
        return self.codigo

    @property
    def item(self):
        return self.produto or self.materia_prima or self.embalagem

    @property
    def situacao_validade(self) -> str:
        if self.validade is None:
            return SituacaoValidade.SEM_VALIDADE
        hoje = timezone.localdate()
        if self.validade < hoje:
            return SituacaoValidade.VENCIDO
        if self.validade <= hoje + timedelta(days=DIAS_ALERTA_VALIDADE):
            return SituacaoValidade.VENCE_EM_BREVE
        return SituacaoValidade.OK

    @property
    def vencido(self) -> bool:
        return self.situacao_validade == SituacaoValidade.VENCIDO

    @property
    def badge_situacao(self) -> str:
        return BADGE_POR_SITUACAO_LOTE.get(self.situacao, "text-bg-secondary")

    @property
    def fornecedor(self):
        """Fornecedor do recebimento que originou o lote (None se produzido)."""
        item = self.itens_de_recebimento.select_related(
            "recebimento__fornecedor"
        ).first()
        return item.recebimento.fornecedor if item else None

    def motivo_bloqueio_consumo(self) -> str:
        """
        Motivo pelo qual o lote NÃO pode ser consumido, ou "" se pode.
        Mensagem já pronta para a tela, com a causa e o que corrigir.
        """
        if self.vencido:
            return (
                f"lote {self.codigo} vencido em "
                f"{self.validade:%d/%m/%Y} — selecione outro lote"
            )
        motivo = SITUACOES_BLOQUEIAM_CONSUMO.get(self.situacao)
        if motivo:
            return f"lote {self.codigo} {motivo} — selecione outro lote"
        return ""

    def pode_ser_consumido(self) -> bool:
        return self.motivo_bloqueio_consumo() == ""

    def pode_ser_expedido(self) -> bool:
        """Só lote APROVADO e dentro da validade vai para expedição (Etapa 9)."""
        return self.situacao == SituacaoLote.APROVADO and not self.vencido


class SequenciaLote(models.Model):
    """
    Sequência do lote interno por tipo de item e ano (Etapa 2a do plano
    de correções). O próximo número é obtido com `select_for_update`
    dentro da transação — dois recebimentos simultâneos nunca geram o
    mesmo lote interno.
    """

    tipo = models.CharField("tipo", max_length=3)
    ano = models.PositiveIntegerField("ano")
    ultimo_numero = models.PositiveIntegerField("último número", default=0)

    class Meta:
        verbose_name = "sequência de lote interno"
        verbose_name_plural = "sequências de lote interno"
        constraints = [
            models.UniqueConstraint(
                fields=["tipo", "ano"], name="sequencia_lote_unica_por_tipo_ano"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tipo}-{self.ano} → {self.ultimo_numero}"


# Prefixo do lote interno por tipo de item
PREFIXO_LOTE_POR_MODELO = {
    Produto: "PA",
    MateriaPrima: "MP",
    Embalagem: "EMB",
}


def gerar_lote_interno(item) -> str:
    """
    Próximo código de lote interno para o tipo do item — alfanumérico e
    sequencial, ex.: MP-2026-00001, EMB-2026-00001, PA-2026-00001.
    """
    prefixo = PREFIXO_LOTE_POR_MODELO[type(item)]
    ano = timezone.localdate().year
    with transaction.atomic():
        sequencia, _ = SequenciaLote.objects.select_for_update().get_or_create(
            tipo=prefixo, ano=ano
        )
        sequencia.ultimo_numero += 1
        sequencia.save(update_fields=["ultimo_numero"])
        return f"{prefixo}-{ano}-{sequencia.ultimo_numero:05d}"


def criar_lote_interno(
    item, usuario, validade=None, lote_fornecedor="", situacao=None
) -> Lote:
    """
    Cria um Lote com o código interno gerado pela sequência.

    Se um lote antigo (código digitado antes da automação) coincidir com
    o número gerado, avança a sequência até um código livre.
    """
    campo = campo_do_item(item)
    codigo = gerar_lote_interno(item)
    while Lote.objects.filter(**{campo: item}, codigo=codigo).exists():
        codigo = gerar_lote_interno(item)

    lote = Lote(
        codigo=codigo,
        lote_fornecedor=lote_fornecedor.strip(),
        validade=validade,
        situacao=situacao or SituacaoLote.AGUARDANDO_CQ,
        criado_por=usuario,
        atualizado_por=usuario,
    )
    setattr(lote, campo, item)
    lote.save()
    return lote


class TipoMovimentacao(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada"
    SAIDA = "SAIDA", "Saída"
    TRANSFERENCIA = "TRANSFERENCIA", "Transferência"
    AJUSTE_ENTRADA = "AJUSTE_ENTRADA", "Ajuste de inventário (+)"
    AJUSTE_SAIDA = "AJUSTE_SAIDA", "Ajuste de inventário (−)"


# Tipos que somam no local de destino / subtraem no local de origem
TIPOS_COM_DESTINO = {
    TipoMovimentacao.ENTRADA,
    TipoMovimentacao.TRANSFERENCIA,
    TipoMovimentacao.AJUSTE_ENTRADA,
}
TIPOS_COM_ORIGEM = {
    TipoMovimentacao.SAIDA,
    TipoMovimentacao.TRANSFERENCIA,
    TipoMovimentacao.AJUSTE_SAIDA,
}


class Movimentacao(ModeloAuditado):
    tipo = models.CharField(
        "tipo", max_length=20, choices=TipoMovimentacao.choices
    )
    produto = models.ForeignKey(
        Produto,
        verbose_name="produto",
        on_delete=models.PROTECT,
        related_name="movimentacoes",
        null=True,
        blank=True,
    )
    materia_prima = models.ForeignKey(
        MateriaPrima,
        verbose_name="matéria-prima",
        on_delete=models.PROTECT,
        related_name="movimentacoes",
        null=True,
        blank=True,
    )
    embalagem = models.ForeignKey(
        Embalagem,
        verbose_name="embalagem",
        on_delete=models.PROTECT,
        related_name="movimentacoes",
        null=True,
        blank=True,
    )
    lote = models.ForeignKey(
        Lote,
        verbose_name="lote",
        on_delete=models.PROTECT,
        related_name="movimentacoes",
        null=True,
        blank=True,
    )
    quantidade = models.DecimalField(
        "quantidade",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    local_origem = models.ForeignKey(
        LocalEstoque,
        verbose_name="local de origem",
        on_delete=models.PROTECT,
        related_name="movimentacoes_de_saida",
        null=True,
        blank=True,
    )
    local_destino = models.ForeignKey(
        LocalEstoque,
        verbose_name="local de destino",
        on_delete=models.PROTECT,
        related_name="movimentacoes_de_entrada",
        null=True,
        blank=True,
    )
    motivo = models.CharField("motivo", max_length=200)
    documento = models.CharField(
        "documento de referência",
        max_length=60,
        blank=True,
        help_text="Ex.: número da NF, da OP ou do inventário.",
    )

    class Meta:
        verbose_name = "movimentação"
        verbose_name_plural = "movimentações"
        ordering = ["-criado_em", "-id"]
        indexes = [
            models.Index(fields=["tipo"]),
            models.Index(fields=["criado_em"]),
        ]
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
                name="movimentacao_exatamente_um_item",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} · {self.item} · {self.quantidade}"

    @property
    def item(self):
        return self.produto or self.materia_prima or self.embalagem

    def clean(self):
        super().clean()

        itens_definidos = [
            campo
            for campo in ("produto", "materia_prima", "embalagem")
            if getattr(self, f"{campo}_id")
        ]
        if len(itens_definidos) != 1:
            raise ValidationError(
                "Informe exatamente um item: produto, matéria-prima ou embalagem."
            )

        if self.lote_id and self.lote.item != self.item:
            raise ValidationError({"lote": "Este lote pertence a outro item."})

        if self.tipo in TIPOS_COM_ORIGEM and not self.local_origem_id:
            raise ValidationError(
                {"local_origem": "Informe o local de origem para este tipo."}
            )
        if self.tipo in TIPOS_COM_DESTINO and not self.local_destino_id:
            raise ValidationError(
                {"local_destino": "Informe o local de destino para este tipo."}
            )
        if self.tipo not in TIPOS_COM_ORIGEM and self.local_origem_id:
            raise ValidationError(
                {"local_origem": "Este tipo de movimentação não tem origem."}
            )
        if self.tipo not in TIPOS_COM_DESTINO and self.local_destino_id:
            raise ValidationError(
                {"local_destino": "Este tipo de movimentação não tem destino."}
            )
        if (
            self.tipo == TipoMovimentacao.TRANSFERENCIA
            and self.local_origem_id
            and self.local_origem_id == self.local_destino_id
        ):
            raise ValidationError(
                {"local_destino": "Origem e destino devem ser locais diferentes."}
            )

        # Saídas não podem deixar o saldo negativo
        if (
            self.pk is None
            and self.tipo in TIPOS_COM_ORIGEM
            and self.local_origem_id
            and self.quantidade is not None
        ):
            disponivel = saldo(
                self.item, lote=self.lote, local=self.local_origem
            )
            if self.quantidade > disponivel:
                from apps.core import formatos

                raise ValidationError(
                    {
                        "quantidade": (
                            "Saldo insuficiente no local de origem "
                            f"(disponível: {formatos.quantidade(disponivel)})."
                        )
                    }
                )


# Sentinela: "não filtrar por lote" (diferente de lote=None, que é o
# bucket de movimentações sem lote informado)
TODOS_OS_LOTES = object()


def saldo(item, lote=TODOS_OS_LOTES, local=None) -> Decimal:
    """
    Saldo atual de um item.

    - lote: um Lote, None (somente movimentações sem lote) ou
      TODOS_OS_LOTES (padrão, não filtra).
    - local: um LocalEstoque ou None (todos os locais).
    """
    filtro_item = {campo_do_item(item): item}
    movimentacoes = Movimentacao.objects.filter(**filtro_item)
    if lote is not TODOS_OS_LOTES:
        movimentacoes = movimentacoes.filter(lote=lote)

    entradas = movimentacoes.filter(tipo__in=TIPOS_COM_DESTINO)
    saidas = movimentacoes.filter(tipo__in=TIPOS_COM_ORIGEM)
    if local is not None:
        entradas = entradas.filter(local_destino=local)
        saidas = saidas.filter(local_origem=local)

    total_entradas = entradas.aggregate(total=Sum("quantidade"))["total"] or Decimal("0")
    total_saidas = saidas.aggregate(total=Sum("quantidade"))["total"] or Decimal("0")
    return total_entradas - total_saidas


def saldos_detalhados():
    """
    Linhas de saldo por (item, lote, local), prontas para a tela de
    consulta: [{"item", "tipo_item", "lote", "local", "saldo"}, ...].
    """
    acumulado: dict[tuple, Decimal] = {}

    def acumular(valores, campo_local, sinal):
        for linha in valores:
            for campo_item in ("produto_id", "materia_prima_id", "embalagem_id"):
                if linha[campo_item]:
                    chave = (
                        campo_item,
                        linha[campo_item],
                        linha["lote_id"],
                        linha[campo_local],
                    )
                    acumulado[chave] = (
                        acumulado.get(chave, Decimal("0"))
                        + sinal * linha["total"]
                    )
                    break

    campos_item = ["produto_id", "materia_prima_id", "embalagem_id", "lote_id"]
    entradas = (
        Movimentacao.objects.filter(tipo__in=TIPOS_COM_DESTINO)
        .values(*campos_item, "local_destino_id")
        .annotate(total=Sum("quantidade"))
    )
    saidas = (
        Movimentacao.objects.filter(tipo__in=TIPOS_COM_ORIGEM)
        .values(*campos_item, "local_origem_id")
        .annotate(total=Sum("quantidade"))
    )
    acumular(entradas, "local_destino_id", Decimal("1"))
    acumular(saidas, "local_origem_id", Decimal("-1"))

    modelos = {
        "produto_id": Produto,
        "materia_prima_id": MateriaPrima,
        "embalagem_id": Embalagem,
    }
    itens_por_campo = {
        campo: modelo.objects.in_bulk(
            {chave[1] for chave in acumulado if chave[0] == campo}
        )
        for campo, modelo in modelos.items()
    }
    lotes = Lote.objects.in_bulk(
        {chave[2] for chave in acumulado if chave[2] is not None}
    )
    locais = LocalEstoque.objects.in_bulk(
        {chave[3] for chave in acumulado if chave[3] is not None}
    )

    rotulos = {
        "produto_id": "Produto",
        "materia_prima_id": "Matéria-prima",
        "embalagem_id": "Embalagem",
    }
    linhas = []
    for (campo_item, item_id, lote_id, local_id), total in acumulado.items():
        linhas.append(
            {
                "item": itens_por_campo[campo_item].get(item_id),
                "tipo_item": rotulos[campo_item],
                "lote": lotes.get(lote_id),
                "local": locais.get(local_id),
                "saldo": total,
            }
        )

    linhas.sort(
        key=lambda linha: (
            linha["tipo_item"],
            linha["item"].nome if linha["item"] else "",
            linha["lote"].codigo if linha["lote"] else "",
            linha["local"].nome if linha["local"] else "",
        )
    )
    return linhas


def locais_do_lote(lote) -> list[dict]:
    """
    Locais onde o lote tem saldo positivo: [{"local", "saldo"}, ...].
    Usado na etiqueta de identificação (localização atual do material).
    """
    entradas = (
        Movimentacao.objects.filter(lote=lote, tipo__in=TIPOS_COM_DESTINO)
        .values("local_destino_id")
        .annotate(total=Sum("quantidade"))
    )
    saidas = (
        Movimentacao.objects.filter(lote=lote, tipo__in=TIPOS_COM_ORIGEM)
        .values("local_origem_id")
        .annotate(total=Sum("quantidade"))
    )

    acumulado: dict[int, Decimal] = {}
    for linha in entradas:
        chave = linha["local_destino_id"]
        acumulado[chave] = acumulado.get(chave, Decimal("0")) + linha["total"]
    for linha in saidas:
        chave = linha["local_origem_id"]
        acumulado[chave] = acumulado.get(chave, Decimal("0")) - linha["total"]

    locais = LocalEstoque.objects.in_bulk(
        {chave for chave in acumulado if chave is not None}
    )
    posicoes = [
        {"local": locais[local_id], "saldo": saldo_local}
        for local_id, saldo_local in acumulado.items()
        if saldo_local > 0 and local_id is not None
    ]
    posicoes.sort(key=lambda posicao: posicao["local"].nome)
    return posicoes


def posicoes_para_consumo(item, excluir_local=None) -> list[dict]:
    """
    Posições de estoque disponíveis para consumo, por (lote, local),
    ordenadas em FEFO — First Expired, First Out: o lote que vence
    primeiro sai primeiro; lotes sem validade e itens sem lote vão por
    último. Só retorna posições com saldo positivo.

    `excluir_local` remove um local do consumo (ex.: a Quarentena, cujo
    material ainda não foi liberado pela Qualidade).

    Retorna: [{"lote", "local", "saldo"}, ...].
    """
    campo = campo_do_item(item)
    movimentacoes = Movimentacao.objects.filter(**{campo: item})

    entradas = (
        movimentacoes.filter(tipo__in=TIPOS_COM_DESTINO)
        .values("lote_id", "local_destino_id")
        .annotate(total=Sum("quantidade"))
    )
    saidas = (
        movimentacoes.filter(tipo__in=TIPOS_COM_ORIGEM)
        .values("lote_id", "local_origem_id")
        .annotate(total=Sum("quantidade"))
    )

    acumulado: dict[tuple, Decimal] = {}
    for linha in entradas:
        chave = (linha["lote_id"], linha["local_destino_id"])
        acumulado[chave] = acumulado.get(chave, Decimal("0")) + linha["total"]
    for linha in saidas:
        chave = (linha["lote_id"], linha["local_origem_id"])
        acumulado[chave] = acumulado.get(chave, Decimal("0")) - linha["total"]

    excluir_id = excluir_local.pk if excluir_local is not None else None
    lotes = Lote.objects.in_bulk(
        {chave[0] for chave in acumulado if chave[0] is not None}
    )
    locais = LocalEstoque.objects.in_bulk(
        {chave[1] for chave in acumulado if chave[1] is not None}
    )

    posicoes = []
    for (lote_id, local_id), saldo_pos in acumulado.items():
        if saldo_pos <= 0 or local_id == excluir_id:
            continue
        posicoes.append(
            {
                "lote": lotes.get(lote_id),
                "local": locais.get(local_id),
                "saldo": saldo_pos,
            }
        )

    def chave_fefo(posicao):
        lote = posicao["lote"]
        sem_validade = lote is None or lote.validade is None
        return (
            sem_validade,
            lote.validade if lote and lote.validade else None,
            lote.id if lote else 0,
        )

    posicoes.sort(key=chave_fefo)
    return posicoes
