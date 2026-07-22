from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import Expedicao


class ExpedicaoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Expedicao
        fields = [
            "data",
            "nota_fiscal",
            "transportadora",
            "conferente",
            "observacoes",
        ]
        widgets = {
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        conferentes = self.fields["conferente"].queryset.filter(is_active=True)
        self.fields["conferente"].queryset = conferentes.order_by(
            "first_name", "username"
        )
        self.fields["conferente"].required = False
