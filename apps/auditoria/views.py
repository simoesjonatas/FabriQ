"""Apoio às telas: contexto da trilha de auditoria.

A trilha não tem telas próprias de edição — apenas o partial
`templates/includes/trilha_auditoria.html`, alimentado por este mixin
nas telas de detalhe/edição dos registros críticos.
"""

from . import servicos


class TrilhaAuditoriaMixin:
    """Adiciona `registros_auditoria` ao contexto de Detail/UpdateViews."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        objeto = getattr(self, "object", None)
        if objeto is not None and objeto.pk:
            context["registros_auditoria"] = servicos.trilha_de(objeto)
        return context
