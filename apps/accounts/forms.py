from django import forms
from django.contrib.auth import forms as auth_forms
from django.contrib.auth.models import Group

from apps.core.forms import BootstrapFormMixin

from .models import User


class LoginForm(BootstrapFormMixin, auth_forms.AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"placeholder": "Usuário", "autofocus": True}
        )
        self.fields["password"].widget.attrs["placeholder"] = "Senha"


class RecuperarSenhaForm(BootstrapFormMixin, auth_forms.PasswordResetForm):
    pass


class DefinirSenhaForm(BootstrapFormMixin, auth_forms.SetPasswordForm):
    pass


class TrocarSenhaForm(BootstrapFormMixin, auth_forms.PasswordChangeForm):
    pass


class PerfisField(forms.ModelMultipleChoiceField):
    def __init__(self, **kwargs):
        super().__init__(
            queryset=Group.objects.order_by("name"),
            widget=forms.CheckboxSelectMultiple,
            required=False,
            label="Perfis de acesso",
            help_text="Define quais módulos o usuário enxerga no sistema.",
            **kwargs,
        )


class UsuarioCriarForm(BootstrapFormMixin, auth_forms.UserCreationForm):
    perfis = PerfisField()

    class Meta(auth_forms.UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": "Usuário",
            "first_name": "Nome",
            "last_name": "Sobrenome",
            "email": "E-mail",
        }

    def save(self, commit=True):
        usuario = super().save(commit=commit)
        if commit:
            usuario.groups.set(self.cleaned_data["perfis"])
        return usuario


class UsuarioEditarForm(BootstrapFormMixin, forms.ModelForm):
    perfis = PerfisField()

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "is_active")
        labels = {
            "first_name": "Nome",
            "last_name": "Sobrenome",
            "email": "E-mail",
            "is_active": "Usuário ativo",
        }
        help_texts = {
            "is_active": "Desmarque para inativar o acesso em vez de excluir o usuário.",
        }

    def __init__(self, *args, usuario_logado=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario_logado = usuario_logado
        if self.instance.pk:
            self.fields["perfis"].initial = self.instance.groups.all()

    def clean_is_active(self):
        ativo = self.cleaned_data["is_active"]
        if not ativo and self.usuario_logado == self.instance:
            raise forms.ValidationError(
                "Você não pode inativar o seu próprio usuário."
            )
        return ativo

    def save(self, commit=True):
        usuario = super().save(commit=commit)
        if commit:
            usuario.groups.set(self.cleaned_data["perfis"])
        return usuario
