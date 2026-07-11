"""Cria os perfis de acesso (Groups) definidos no briefing do cliente."""

from django.db import migrations

PERFIS = [
    "Administrador",
    "Diretoria",
    "Produção",
    "Qualidade",
    "Almoxarifado",
    "PCP",
    "Compras",
    "Expedição",
]


def criar_perfis(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for nome in PERFIS:
        Group.objects.get_or_create(name=nome)


def noop(apps, schema_editor):
    # Não removemos os grupos ao reverter: podem já ter usuários vinculados.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(criar_perfis, noop),
    ]
