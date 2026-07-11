"""Utilitários de formulário compartilhados pelas apps."""

from django import forms


class BootstrapFormMixin:
    """
    Aplica as classes do Bootstrap aos widgets do formulário.

    Evita repetir attrs em todos os forms do sistema; campos com erro
    recebem is-invalid para o destaque visual padrão.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        widgets_de_marcacao = (
            forms.CheckboxInput | forms.CheckboxSelectMultiple | forms.RadioSelect
        )
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, widgets_de_marcacao):
                classe = "form-check-input"
            elif isinstance(widget, forms.Select | forms.SelectMultiple):
                classe = "form-select"
            else:
                classe = "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {classe}".strip()

    def is_valid(self):
        valido = super().is_valid()
        if not valido:
            for nome in self.errors:
                if nome in self.fields:
                    widget = self.fields[nome].widget
                    widget.attrs["class"] = f"{widget.attrs.get('class', '')} is-invalid".strip()
        return valido
