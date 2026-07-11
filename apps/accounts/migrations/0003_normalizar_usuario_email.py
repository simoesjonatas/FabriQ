from django.db import migrations, models


def normalizar_usuarios(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    vistos_username = set()
    vistos_email = set()

    for usuario in User.objects.order_by("pk"):
        username = (usuario.username or "").strip().upper()
        email = (usuario.email or "").strip().upper()

        if username in vistos_username:
            raise RuntimeError(f"Usuário duplicado após normalização: {username}")
        vistos_username.add(username)

        if email:
            if email in vistos_email:
                raise RuntimeError(f"E-mail duplicado após normalização: {email}")
            vistos_email.add(email)

        usuario.username = username
        usuario.email = email
        usuario.save(update_fields=["username", "email"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_criar_perfis"),
    ]

    operations = [
        migrations.RunPython(normalizar_usuarios, noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                fields=("email",),
                condition=~models.Q(("email", "")),
                name="usuario_email_unico_quando_informado",
                violation_error_message="Já existe um usuário com este e-mail.",
            ),
        ),
    ]
