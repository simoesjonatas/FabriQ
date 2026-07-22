from django.apps import AppConfig


class DossieConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dossie"
    label = "dossie"
    verbose_name = "dossiê do lote"
