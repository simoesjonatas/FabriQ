from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class HomeView(LoginRequiredMixin, TemplateView):
    """
    Hub de módulos: mostra ao usuário apenas o que o perfil dele permite.
    Na Fase 10 dará lugar ao dashboard com indicadores.
    """

    template_name = "core/home.html"
