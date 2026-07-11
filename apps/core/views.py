from django.views.generic import TemplateView


class HomeView(TemplateView):
    """Página inicial. Na Fase 10 dará lugar ao dashboard."""

    template_name = "core/home.html"
