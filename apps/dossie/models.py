"""
Registro das gerações do dossiê (Etapa 12 do plano, PDF 8).

O banco é a fonte oficial; o PDF é evidência consolidada de um instante.
Por isso **cada geração vira um registro imutável**: quem gerou, quando,
qual versão, o hash do arquivo e o próprio PDF guardado.
"""

import hashlib

from django.conf import settings
from django.db import models


class GeracaoDossieQuerySet(models.QuerySet):
    def update(self, *args, **kwargs):
        from apps.auditoria.models import TrilhaImutavelError

        raise TrilhaImutavelError(
            "A geração do dossiê é imutável — não pode ser alterada."
        )

    def delete(self, *args, **kwargs):
        from apps.auditoria.models import TrilhaImutavelError

        raise TrilhaImutavelError(
            "A geração do dossiê é imutável — não pode ser excluída."
        )


class GeracaoDossie(models.Model):
    lote = models.ForeignKey(
        "estoque.Lote",
        verbose_name="lote",
        on_delete=models.PROTECT,
        related_name="dossies",
    )
    versao = models.PositiveIntegerField("versão")
    gerado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="gerado por",
        on_delete=models.PROTECT,
        related_name="+",
    )
    gerado_em = models.DateTimeField("gerado em", auto_now_add=True)
    hash_arquivo = models.CharField("hash SHA-256", max_length=64)
    arquivo = models.FileField(
        "PDF do dossiê", upload_to="dossies/%Y/%m/", null=True, blank=True
    )

    objects = GeracaoDossieQuerySet.as_manager()

    class Meta:
        verbose_name = "geração do dossiê"
        verbose_name_plural = "gerações do dossiê"
        ordering = ["-gerado_em", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["lote", "versao"], name="dossie_versao_unica_por_lote"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.codigo} · {self.lote.codigo}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            from apps.auditoria.models import TrilhaImutavelError

            raise TrilhaImutavelError(
                "A geração do dossiê é imutável — não pode ser alterada."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from apps.auditoria.models import TrilhaImutavelError

        raise TrilhaImutavelError(
            "A geração do dossiê é imutável — não pode ser excluída."
        )

    @property
    def codigo(self) -> str:
        """Código do dossiê que sai impresso no rodapé do PDF."""
        return f"DOS-{self.lote_id:05d}-{self.versao:02d}"


def proxima_versao(lote) -> int:
    ultima = (
        GeracaoDossie.objects.filter(lote=lote)
        .order_by("-versao")
        .values_list("versao", flat=True)
        .first()
    )
    return (ultima or 0) + 1


def hash_do_pdf(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()
