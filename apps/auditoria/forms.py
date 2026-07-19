"""Integração da trilha de auditoria com os formulários."""

from django import forms

from .campos_criticos import campos_criticos_do_modelo


class JustificativaAuditoriaMixin:
    """
    Acrescenta o campo "Justificativa da alteração" aos ModelForms de
    modelos com campos críticos (apps/auditoria/campos_criticos.py).

    Na edição, alterar um campo crítico sem justificar bloqueia o
    formulário (exigência do PDF 2.3); a justificativa informada segue
    para a trilha junto com cada campo alterado. Na criação o campo não
    aparece — o registro de criação já identifica usuário e data.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["justificativa_alteracao"] = forms.CharField(
                label="Justificativa da alteração",
                required=False,
                widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
                help_text=(
                    "Obrigatória ao alterar campos críticos "
                    "(fica gravada na trilha de auditoria)."
                ),
            )

    @property
    def campos_criticos_alterados(self) -> list[str]:
        criticos = campos_criticos_do_modelo(self._meta.model)
        return [campo for campo in self.changed_data if campo in criticos]

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and self.campos_criticos_alterados:
            justificativa = (cleaned.get("justificativa_alteracao") or "").strip()
            if not justificativa:
                rotulos = [
                    str(self.fields[campo].label or campo)
                    for campo in self.campos_criticos_alterados
                ]
                self.add_error(
                    "justificativa_alteracao",
                    "Informe a justificativa para alterar: "
                    + ", ".join(rotulos)
                    + ".",
                )
        return cleaned

    def save(self, commit=True):
        justificativa = (self.cleaned_data.get("justificativa_alteracao") or "").strip()
        if justificativa:
            self.instance._justificativa_auditoria = justificativa
        return super().save(commit)
