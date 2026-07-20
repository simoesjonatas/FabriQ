"""
Controle de Qualidade (Fase 7).

A análise é feita sobre um LOTE — o mesmo objeto rastreado pelo estoque
e pela quarentena. Cada análise agrupa resultados (um por tipo de
análise), compara automaticamente com os valores de referência do tipo
e termina Aprovada ou Reprovada, com responsável, data e parecer.
Depois de decidida, a análise não pode mais ser alterada.
"""

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse

from apps.cadastros.models import Produto
from apps.core import formatos
from apps.core.models import ModeloAuditado, ModeloBase
from apps.estoque.models import Lote


class TipoAnalise(ModeloBase):
    nome = models.CharField("nome", max_length=100, unique=True)
    unidade = models.CharField(
        "unidade",
        max_length=20,
        blank=True,
        help_text="Ex.: pH, g/mL, cP. Vazio para análises visuais/sensoriais.",
    )
    valor_minimo = models.DecimalField(
        "valor mínimo de referência",
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    valor_maximo = models.DecimalField(
        "valor máximo de referência",
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    referencia_texto = models.CharField(
        "referência descritiva",
        max_length=200,
        blank=True,
        help_text="Para análises qualitativas. Ex.: “Límpido, sem partículas”.",
    )

    class Meta:
        verbose_name = "tipo de análise"
        verbose_name_plural = "tipos de análise"
        ordering = ["nome"]

    def __str__(self) -> str:
        if self.unidade:
            return f"{self.nome} ({self.unidade})"
        return self.nome

    @property
    def referencia(self) -> str:
        """Texto amigável da faixa de referência."""
        minimo = formatos.quantidade(self.valor_minimo)
        maximo = formatos.quantidade(self.valor_maximo)
        if minimo and maximo:
            return f"{minimo} a {maximo} {self.unidade}".strip()
        if minimo:
            return f"≥ {minimo} {self.unidade}".strip()
        if maximo:
            return f"≤ {maximo} {self.unidade}".strip()
        return self.referencia_texto


class EspecificacaoProduto(ModeloBase):
    """
    Limite de um parâmetro na especificação DO PRODUTO (Etapa 6e, PDF 5.6).
    Os limites vêm daqui — não do tipo genérico — e valem para o controle
    em processo e o CQ final.
    """

    produto = models.ForeignKey(
        Produto,
        verbose_name="produto",
        on_delete=models.PROTECT,
        related_name="especificacoes",
    )
    tipo = models.ForeignKey(
        "TipoAnalise",
        verbose_name="parâmetro",
        on_delete=models.PROTECT,
        related_name="especificacoes",
    )
    valor_minimo = models.DecimalField(
        "valor mínimo", max_digits=12, decimal_places=4, null=True, blank=True
    )
    valor_maximo = models.DecimalField(
        "valor máximo", max_digits=12, decimal_places=4, null=True, blank=True
    )
    referencia_texto = models.CharField(
        "referência descritiva", max_length=200, blank=True
    )

    class Meta:
        verbose_name = "especificação do produto"
        verbose_name_plural = "especificações do produto"
        ordering = ["produto__nome", "tipo__nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["produto", "tipo"],
                name="especificacao_unica_por_produto_tipo",
                violation_error_message="Este produto já tem limite para este parâmetro.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.produto.codigo} · {self.tipo.nome}"

    def fora_do_limite(self, valor) -> bool:
        if valor is None:
            return False
        if self.valor_minimo is not None and valor < self.valor_minimo:
            return True
        if self.valor_maximo is not None and valor > self.valor_maximo:
            return True
        return False


class StatusAnalise(models.TextChoices):
    EM_ANALISE = "EM_ANALISE", "Em análise"
    APROVADA = "APROVADA", "Aprovada"
    REPROVADA = "REPROVADA", "Reprovada"


BADGE_POR_STATUS_ANALISE = {
    StatusAnalise.EM_ANALISE: "text-bg-warning",
    StatusAnalise.APROVADA: "text-bg-success",
    StatusAnalise.REPROVADA: "text-bg-danger",
}


class Analise(ModeloAuditado):
    lote = models.ForeignKey(
        Lote,
        verbose_name="lote",
        on_delete=models.PROTECT,
        related_name="analises",
    )
    status = models.CharField(
        "situação",
        max_length=20,
        choices=StatusAnalise.choices,
        default=StatusAnalise.EM_ANALISE,
    )
    observacoes = models.TextField("observações", blank=True)

    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="decidido por",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    decidido_em = models.DateTimeField("decidido em", null=True, blank=True)
    parecer = models.TextField("parecer", blank=True)

    class Meta:
        verbose_name = "análise"
        verbose_name_plural = "análises"
        ordering = ["-criado_em", "-id"]

    def __str__(self) -> str:
        return f"{self.numero} · lote {self.lote.codigo}"

    def get_absolute_url(self) -> str:
        return reverse("qualidade:detalhe", args=[self.pk])

    @property
    def numero(self) -> str:
        return f"AN-{self.pk:05d}" if self.pk else "AN-nova"

    @property
    def badge_status(self) -> str:
        return BADGE_POR_STATUS_ANALISE.get(self.status, "text-bg-secondary")

    @property
    def editavel(self) -> bool:
        return self.status == StatusAnalise.EM_ANALISE

    @property
    def tem_resultado_fora_da_referencia(self) -> bool:
        return any(
            resultado.fora_da_referencia for resultado in self.resultados.all()
        )


class ResultadoAnalise(models.Model):
    analise = models.ForeignKey(
        Analise,
        verbose_name="análise",
        on_delete=models.CASCADE,
        related_name="resultados",
    )
    tipo = models.ForeignKey(
        TipoAnalise,
        verbose_name="tipo de análise",
        on_delete=models.PROTECT,
        related_name="resultados",
    )
    valor_numerico = models.DecimalField(
        "valor numérico",
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    valor_texto = models.CharField(
        "resultado descritivo",
        max_length=200,
        blank=True,
        help_text="Para análises qualitativas (aparência, odor...).",
    )

    class Meta:
        verbose_name = "resultado"
        verbose_name_plural = "resultados"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["analise", "tipo"],
                name="resultado_tipo_unico_por_analise",
                violation_error_message="Este tipo de análise já foi registrado.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tipo} = {self.valor}"

    @property
    def valor(self) -> str:
        if self.valor_numerico is not None:
            numero = formatos.quantidade(self.valor_numerico)
            return f"{numero} {self.tipo.unidade}".strip()
        return self.valor_texto

    @property
    def fora_da_referencia(self) -> bool:
        """True apenas quando há valor numérico fora da faixa do tipo."""
        if self.valor_numerico is None:
            return False
        minimo = self.tipo.valor_minimo
        maximo = self.tipo.valor_maximo
        if minimo is not None and self.valor_numerico < minimo:
            return True
        if maximo is not None and self.valor_numerico > maximo:
            return True
        return False


class AnexoAnalise(ModeloAuditado):
    analise = models.ForeignKey(
        Analise,
        verbose_name="análise",
        on_delete=models.CASCADE,
        related_name="anexos",
    )
    arquivo = models.FileField(
        "arquivo",
        upload_to="analises/%Y/%m/",
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png", "webp"])],
        help_text="PDF ou imagem (JPG, PNG, WEBP).",
    )
    descricao = models.CharField("descrição", max_length=120, blank=True)

    class Meta:
        verbose_name = "anexo da análise"
        verbose_name_plural = "anexos da análise"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.descricao or self.arquivo.name
