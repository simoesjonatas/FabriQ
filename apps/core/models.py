"""
Modelos abstratos compartilhados por todas as apps do FabriQ.

Regras obrigatórias do sistema atendidas aqui:
- Toda alteração registra usuário, data e hora.
- Toda criação/alteração alimenta a trilha de auditoria imutável
  (apps/auditoria): um registro por campo alterado, com valor anterior,
  valor novo, usuário e justificativa.
- Registros não são excluídos definitivamente: usa-se o campo `ativo`
  (inativação) em vez de DELETE.
"""

from django.conf import settings
from django.db import models


class ModeloAuditado(models.Model):
    """Rastreia quem criou/alterou o registro e quando."""

    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criado por",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        editable=False,
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="atualizado por",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Salva e alimenta a trilha de auditoria (apps/auditoria).

        Todos os fluxos do sistema atribuem `atualizado_por` antes de
        salvar — esse usuário assina o registro da trilha. A comparação
        usa a versão ainda gravada no banco, campo a campo.
        """
        criando = self._state.adding
        versao_no_banco = None
        if not criando and self.pk is not None:
            versao_no_banco = type(self).objects.filter(pk=self.pk).first()

        super().save(*args, **kwargs)

        from apps.auditoria import servicos

        justificativa = getattr(self, "_justificativa_auditoria", "")
        usuario = self.atualizado_por or self.criado_por
        if criando:
            servicos.registrar_criacao(self, usuario, justificativa)
        elif versao_no_banco is not None:
            servicos.registrar_alteracoes(
                versao_no_banco, self, usuario, justificativa
            )
        self._justificativa_auditoria = ""

    def salvar_com_usuario(self, usuario, justificativa="", **kwargs):
        """Salva o registro atribuindo o usuário responsável pela alteração."""
        if self._state.adding and self.criado_por is None:
            self.criado_por = usuario
        self.atualizado_por = usuario
        if justificativa:
            self._justificativa_auditoria = justificativa
        self.save(**kwargs)


class ModeloBase(ModeloAuditado):
    """
    Base padrão dos cadastros do sistema.

    Além da auditoria, acrescenta o controle de ativação/inativação,
    usado no lugar de exclusão definitiva.
    """

    ativo = models.BooleanField(
        "ativo",
        default=True,
        help_text="Desmarque para inativar o registro em vez de excluí-lo.",
    )

    class Meta:
        abstract = True
