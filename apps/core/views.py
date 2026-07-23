from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.accounts.mixins import AcessoModuloMixin
from apps.auditoria.views import TrilhaAuditoriaMixin


@require_GET
def healthcheck(request):
    return JsonResponse({"status": "ok"})


class HomeView(LoginRequiredMixin, TemplateView):
    """
    Dashboard inicial (Fase 10): indicadores, alertas e produção recente,
    seguidos do hub de módulos. Mostra só o que o perfil do usuário vê.
    """

    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        from .dashboard import montar_dashboard

        context = super().get_context_data(**kwargs)
        context["dashboard"] = montar_dashboard(self.request.user)
        return context


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
    url_criar/url_editar (nomes de rota), url_detalhe opcional e template_name.
    """

    paginate_by = 20
    campos_pesquisa: list[str] = []
    colunas: list[str] = []
    titulo = ""
    url_criar = ""
    url_editar = ""
    url_detalhe = ""

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
                "url_detalhe": self.url_detalhe,
            }
        )
        return context


class CadastroFormMixin(AcessoModuloMixin, SalvarComUsuarioMixin, SuccessMessageMixin):
    """Comportamento comum de criação/edição dos cadastros."""

    template_name = "cadastros/form.html"
    titulo = ""
    url_lista = ""
    form_tabs = ()
    form_tab_full_width_fields = {
        "descricao",
        "especificacao",
        "fornecedores_aprovados",
        "inspecao",
        "motivo_bloqueio",
        "observacoes",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        form_tabs = self._form_tabs_para_template(form)
        context["titulo"] = self.titulo
        context["url_lista"] = self.url_lista
        context["form_tem_arquivo"] = self._form_tem_arquivo(form)
        context["form_tabs"] = form_tabs
        context["aba_form_ativa"] = self._aba_form_ativa(form, form_tabs)
        return context

    def _form_tem_arquivo(self, form) -> bool:
        if not form:
            return False
        return any(
            isinstance(campo.widget, forms.FileInput)
            for campo in form.fields.values()
        )

    def _form_tabs_para_template(self, form) -> list[dict]:
        if not form or not self.form_tabs:
            return []

        campos_por_nome = {campo.name: campo for campo in form.visible_fields()}
        nomes_usados = set()
        abas = []

        for indice, aba in enumerate(self.form_tabs, start=1):
            campos = [
                campos_por_nome[nome]
                for nome in aba.get("fields", ())
                if nome in campos_por_nome
            ]
            if not campos:
                continue

            nomes_usados.update(campo.name for campo in campos)
            campos_largos = set(self.form_tab_full_width_fields)
            campos_largos.update(aba.get("full_width_fields", ()))
            abas.append(
                {
                    "id": f"form-tab-{aba.get('id', indice)}",
                    "label": aba["label"],
                    "icon": aba.get("icon", "bi-card-text"),
                    "description": aba.get("description", ""),
                    "fields": campos,
                    "full_width_fields": campos_largos,
                    "has_errors": any(campo.errors for campo in campos),
                }
            )

        campos_restantes = [
            campo for campo in form.visible_fields() if campo.name not in nomes_usados
        ]
        if campos_restantes:
            if not abas:
                abas.append(
                    {
                        "id": "form-tab-dados",
                        "label": "Dados",
                        "icon": "bi-card-text",
                        "description": "",
                        "fields": [],
                        "full_width_fields": set(self.form_tab_full_width_fields),
                        "has_errors": False,
                    }
                )
            abas[-1]["fields"].extend(campos_restantes)
            abas[-1]["has_errors"] = abas[-1]["has_errors"] or any(
                campo.errors for campo in campos_restantes
            )

        return abas

    def _aba_form_ativa(self, form, form_tabs) -> str:
        if not form_tabs:
            return ""
        if form and form.is_bound:
            for aba in form_tabs:
                if aba["has_errors"]:
                    return aba["id"]
        return form_tabs[0]["id"]


class CadastroCreateView(CadastroFormMixin, CreateView):
    success_message = "Registro cadastrado com sucesso."


class CadastroUpdateView(CadastroFormMixin, TrilhaAuditoriaMixin, UpdateView):
    success_message = "Registro atualizado com sucesso."
