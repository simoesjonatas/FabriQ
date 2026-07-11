from django.contrib.auth.models import AbstractUser


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

    def __str__(self) -> str:
        return self.get_full_name() or self.username
