from django.contrib.auth.models import AbstractUser
from django.db import models


def normalizar_identificador(valor: str | None) -> str:
    """Normaliza usuário/e-mail para comparação e armazenamento."""
    return (valor or "").strip().upper()


class User(AbstractUser):
    """
    Usuário do FabriQ.

    Definido como modelo customizado desde o início do projeto para
    permitir evolução (setor, perfil de acesso etc.) sem migrações
    destrutivas. Os campos de perfil serão adicionados na Fase 1.
    """

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        constraints = [
            models.UniqueConstraint(
                fields=["email"],
                condition=~models.Q(email=""),
                name="usuario_email_unico_quando_informado",
                violation_error_message="Já existe um usuário com este e-mail.",
            ),
        ]

    def clean(self):
        super().clean()
        self.username = normalizar_identificador(self.username)
        self.email = normalizar_identificador(self.email)

    def save(self, *args, **kwargs):
        self.username = normalizar_identificador(self.username)
        self.email = normalizar_identificador(self.email)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.get_full_name() or self.username
