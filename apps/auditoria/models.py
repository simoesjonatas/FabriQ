"""
Trilha de auditoria (correções — Etapa 1).

Histórico técnico NÃO APAGÁVEL de todas as ações e alterações do
sistema: o que mudou (campo, valor anterior, valor novo), quem mudou,
quando e por quê. Exigência do PDF de complementação funcional
(seções 2.3 e 7.1).

Imutabilidade: registros só podem ser criados — qualquer tentativa de
alterar ou excluir (pelo modelo ou pelo queryset) levanta
`TrilhaImutavelError`. Não há telas de edição e o admin é somente
leitura.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class TrilhaImutavelError(Exception):
    """Tentativa de alterar ou excluir um registro da trilha de auditoria."""


class AcaoAuditoria(models.TextChoices):
    CRIACAO = "CRIACAO", "Criação"
    ALTERACAO = "ALTERACAO", "Alteração"
    CANCELAMENTO = "CANCELAMENTO", "Cancelamento"
    INATIVACAO = "INATIVACAO", "Inativação"
    APROVACAO = "APROVACAO", "Aprovação"
    LIBERACAO = "LIBERACAO", "Liberação"
    EXCECAO_BLOQUEIO = "EXCECAO_BLOQUEIO", "Exceção de bloqueio"
    IMPRESSAO = "IMPRESSAO", "Impressão"


BADGE_POR_ACAO = {
    AcaoAuditoria.CRIACAO: "text-bg-success",
    AcaoAuditoria.ALTERACAO: "text-bg-secondary",
    AcaoAuditoria.CANCELAMENTO: "text-bg-danger",
    AcaoAuditoria.INATIVACAO: "text-bg-warning",
    AcaoAuditoria.APROVACAO: "text-bg-success",
    AcaoAuditoria.LIBERACAO: "text-bg-primary",
    AcaoAuditoria.EXCECAO_BLOQUEIO: "text-bg-dark",
    AcaoAuditoria.IMPRESSAO: "text-bg-info",
}


class RegistroAuditoriaQuerySet(models.QuerySet):
    """Bloqueia alteração/exclusão em massa — a trilha é imutável."""

    def update(self, **kwargs):
        raise TrilhaImutavelError(
            "Registros de auditoria não podem ser alterados."
        )

    def delete(self):
        raise TrilhaImutavelError(
            "Registros de auditoria não podem ser excluídos."
        )


class RegistroAuditoria(models.Model):
    content_type = models.ForeignKey(
        ContentType,
        verbose_name="tipo do registro",
        on_delete=models.PROTECT,
        related_name="+",
    )
    object_id = models.PositiveBigIntegerField("id do registro")
    objeto = GenericForeignKey("content_type", "object_id")
    objeto_repr = models.CharField(
        "identificação do registro",
        max_length=200,
        blank=True,
        help_text="Texto do registro no momento da ação (ex.: “OP-00012 · Shampoo”).",
    )

    acao = models.CharField("ação", max_length=20, choices=AcaoAuditoria.choices)
    campo = models.CharField("campo", max_length=100, blank=True)
    valor_anterior = models.TextField("valor anterior", blank=True)
    valor_novo = models.TextField("valor novo", blank=True)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        help_text="Vazio apenas em ações do próprio sistema (carga de dados).",
    )
    data = models.DateTimeField("data", auto_now_add=True)
    justificativa = models.TextField("justificativa", blank=True)

    objects = RegistroAuditoriaQuerySet.as_manager()

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-data", "-id"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        alvo = self.objeto_repr or f"{self.content_type} #{self.object_id}"
        return f"{self.get_acao_display()} · {alvo}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TrilhaImutavelError(
                "Registros de auditoria não podem ser alterados."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TrilhaImutavelError(
            "Registros de auditoria não podem ser excluídos."
        )

    @property
    def badge_acao(self) -> str:
        return BADGE_POR_ACAO.get(self.acao, "text-bg-secondary")
