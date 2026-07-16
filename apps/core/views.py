from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.accounts.mixins import AcessoModuloMixin


@require_GET
def healthcheck(request):
    return JsonResponse({"status": "ok"})


class HomeView(LoginRequiredMixin, TemplateView):
    """
    Hub de módulos: mostra ao usuário apenas o que o perfil dele permite.
    Na Fase 10 dará lugar ao dashboard com indicadores.
    """

    template_name = "core/home.html"


class SalvarComUsuarioMixin:
    """Preenche criado_por/atualizado_por ao salvar em Create/UpdateView."""

    def form_valid(self, form):
        if form.instance.pk is None:
            form.instance.criado_por = self.request.user
        form.instance.atualizado_por = self.request.user
        return super().form_valid(form)


class CadastroListView(AcessoModuloMixin, ListView):
    """
    Lista padrão dos cadastros: pesquisa (?q=), filtro por situação
    (?status=ativos|inativos) e paginação.

    Subclasses definem: model, modulo, campos_pesquisa, titulo,
    url_criar/url_editar (nomes de rota) e template_name.
    """

    paginate_by = 20
    campos_pesquisa: list[str] = []
    colunas: list[str] = []
    titulo = ""
    url_criar = ""
    url_editar = ""

    def get_queryset(self):
        queryset = super().get_queryset()

        termo = self.request.GET.get("q", "").strip()
        if termo and self.campos_pesquisa:
            filtro = Q()
            for campo in self.campos_pesquisa:
                filtro |= Q(**{f"{campo}__icontains": termo})
            queryset = queryset.filter(filtro)

        status = self.request.GET.get("status", "")
        if status == "ativos":
            queryset = queryset.filter(ativo=True)
        elif status == "inativos":
            queryset = queryset.filter(ativo=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "termo": self.request.GET.get("q", "").strip(),
                "status": self.request.GET.get("status", ""),
                "titulo": self.titulo,
                "colunas": self.colunas,
                "url_criar": self.url_criar,
                "url_editar": self.url_editar,
            }
        )
        return context


class CadastroFormMixin(AcessoModuloMixin, SalvarComUsuarioMixin, SuccessMessageMixin):
    """Comportamento comum de criação/edição dos cadastros."""

    template_name = "cadastros/form.html"
    titulo = ""
    url_lista = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = self.titulo
        context["url_lista"] = self.url_lista
        return context


class CadastroCreateView(CadastroFormMixin, CreateView):
    success_message = "Registro cadastrado com sucesso."


class CadastroUpdateView(CadastroFormMixin, UpdateView):
    success_message = "Registro atualizado com sucesso."
