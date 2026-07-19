import logging

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.accounts.mixins import AcessoModuloMixin
from apps.auditoria import servicos as auditoria
from apps.auditoria.models import AcaoAuditoria
from apps.auditoria.views import TrilhaAuditoriaMixin
from apps.core.views import (
    CadastroCreateView,
    CadastroListView,
    CadastroUpdateView,
    SalvarComUsuarioMixin,
)
from apps.estoque.models import Lote

from .forms import (
    AnaliseForm,
    AnexoAnaliseFormSet,
    ResultadoAnaliseFormSet,
    TipoAnaliseForm,
)
from .models import Analise, StatusAnalise, TipoAnalise

logger = logging.getLogger("fabriq")

MODULO = "qualidade"


class AnaliseListView(AcessoModuloMixin, ListView):
    modulo = MODULO
    model = Analise
    template_name = "qualidade/lista.html"
    context_object_name = "analises"
    paginate_by = 20

    def get_queryset(self):
        queryset = Analise.objects.select_related(
            "lote__produto",
            "lote__materia_prima",
            "lote__embalagem",
            "criado_por",
            "decidido_por",
        )

        filtros = self.request.GET
        if filtros.get("status") in StatusAnalise.values:
            queryset = queryset.filter(status=filtros["status"])
        if filtros.get("de"):
            queryset = queryset.filter(criado_em__date__gte=filtros["de"])
        if filtros.get("ate"):
            queryset = queryset.filter(criado_em__date__lte=filtros["ate"])

        termo = filtros.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                Q(lote__codigo__icontains=termo)
                | Q(lote__produto__nome__icontains=termo)
                | Q(lote__produto__codigo__icontains=termo)
                | Q(lote__materia_prima__nome__icontains=termo)
                | Q(lote__materia_prima__codigo__icontains=termo)
                | Q(lote__embalagem__nome__icontains=termo)
                | Q(lote__embalagem__codigo__icontains=termo)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.request.GET
        context.update(
            {
                "status_choices": StatusAnalise.choices,
                "filtro_status": filtros.get("status", ""),
                "filtro_q": filtros.get("q", "").strip(),
                "filtro_de": filtros.get("de", ""),
                "filtro_ate": filtros.get("ate", ""),
            }
        )
        return context


class AnaliseFormBase(AcessoModuloMixin, SalvarComUsuarioMixin):
    modulo = MODULO
    model = Analise
    form_class = AnaliseForm
    template_name = "qualidade/form.html"

    def get_formsets(self, instance=None):
        kwargs = {"instance": instance or getattr(self, "object", None)}
        if self.request.method in {"POST", "PUT"}:
            kwargs["data"] = self.request.POST
        anexos_kwargs = dict(kwargs)
        if self.request.method in {"POST", "PUT"}:
            anexos_kwargs["files"] = self.request.FILES
        return (
            ResultadoAnaliseFormSet(prefix="resultados", **kwargs),
            AnexoAnaliseFormSet(prefix="anexos", **anexos_kwargs),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "resultados_formset" in kwargs and "anexos_formset" in kwargs:
            context["resultados_formset"] = kwargs["resultados_formset"]
            context["anexos_formset"] = kwargs["anexos_formset"]
        else:
            resultados, anexos = self.get_formsets()
            context.setdefault("resultados_formset", resultados)
            context.setdefault("anexos_formset", anexos)
        return context

    def form_valid(self, form):
        criando = form.instance.pk is None
        if criando:
            form.instance.criado_por = self.request.user
        form.instance.atualizado_por = self.request.user
        self.object = form.save(commit=False)

        resultados_formset, anexos_formset = self.get_formsets(instance=self.object)
        if not resultados_formset.is_valid() or not anexos_formset.is_valid():
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    resultados_formset=resultados_formset,
                    anexos_formset=anexos_formset,
                )
            )

        with transaction.atomic():
            self.object.save()
            resultados_formset.save()

            for anexo_form in anexos_formset.forms:
                if not anexo_form.cleaned_data or anexo_form.cleaned_data.get("DELETE"):
                    continue
                if not anexo_form.cleaned_data.get("arquivo"):
                    continue
                anexo = anexo_form.save(commit=False)
                anexo.analise = self.object
                if anexo.pk is None:
                    anexo.criado_por = self.request.user
                anexo.atualizado_por = self.request.user
                anexo.save()
            for anexo_form in anexos_formset.deleted_forms:
                if anexo_form.instance.pk:
                    anexo_form.instance.delete()

        messages.success(
            self.request,
            f"Análise {self.object.numero} salva"
            + (" — registre a decisão quando concluir." if criando else "."),
        )
        logger.info(
            "Análise %s %s por %s",
            self.object.numero,
            "criada" if criando else "atualizada",
            self.request.user,
        )
        return redirect(self.object.get_absolute_url())


class AnaliseCriarView(AnaliseFormBase, CreateView):
    def get_initial(self):
        initial = super().get_initial()
        lote_id = self.request.GET.get("lote", "")
        if lote_id.isdigit():
            lote = Lote.objects.filter(pk=lote_id).first()
            if lote:
                initial["lote"] = lote
        return initial


class AnaliseEditarView(AnaliseFormBase, UpdateView):
    def dispatch(self, request, *args, **kwargs):
        analise = self.get_object()
        if request.user.is_authenticated and not analise.editavel:
            messages.warning(
                request,
                f"A análise {analise.numero} já foi "
                f"“{analise.get_status_display()}” e não pode ser alterada.",
            )
            return redirect(analise.get_absolute_url())
        return super().dispatch(request, *args, **kwargs)


class AnaliseDetalheView(AcessoModuloMixin, TrilhaAuditoriaMixin, DetailView):
    modulo = MODULO
    model = Analise
    template_name = "qualidade/detalhe.html"
    context_object_name = "analise"

    def get_queryset(self):
        return Analise.objects.select_related(
            "lote__produto",
            "lote__materia_prima",
            "lote__embalagem",
            "criado_por",
            "decidido_por",
        ).prefetch_related("resultados__tipo", "anexos")


class DecidirAnaliseView(AcessoModuloMixin, View):
    modulo = MODULO

    def post(self, request, pk):
        analise = get_object_or_404(
            Analise.objects.select_related("lote"), pk=pk
        )
        decisao = request.POST.get("decisao", "")
        parecer = request.POST.get("parecer", "").strip()

        if not analise.editavel:
            messages.error(
                request,
                f"A análise {analise.numero} já foi decidida.",
            )
            return redirect(analise.get_absolute_url())

        if decisao not in {StatusAnalise.APROVADA, StatusAnalise.REPROVADA}:
            messages.error(request, "Decisão inválida.")
            return redirect(analise.get_absolute_url())

        if not analise.resultados.exists():
            messages.error(
                request,
                "Registre pelo menos um resultado antes de decidir a análise.",
            )
            return redirect(analise.get_absolute_url())

        if decisao == StatusAnalise.REPROVADA and not parecer:
            messages.error(request, "Informe o parecer da reprovação.")
            return redirect(analise.get_absolute_url())

        analise.status = decisao
        analise.decidido_por = request.user
        analise.decidido_em = timezone.now()
        analise.parecer = parecer
        analise.atualizado_por = request.user
        analise._justificativa_auditoria = parecer
        analise.save()

        if decisao == StatusAnalise.APROVADA:
            auditoria.registrar_evento(
                analise,
                AcaoAuditoria.APROVACAO,
                request.user,
                justificativa=parecer,
                valor_novo=f"Lote {analise.lote.codigo} aprovado na análise",
            )

        rotulo = dict(StatusAnalise.choices)[decisao]
        messages.success(
            request,
            f"Análise {analise.numero} {rotulo.lower()} — lote {analise.lote.codigo}.",
        )
        logger.info(
            "Análise %s %s por %s", analise.numero, decisao, request.user
        )
        return redirect(analise.get_absolute_url())


# Tipos de análise — CRUD genérico


class TipoAnaliseListView(CadastroListView):
    modulo = MODULO
    model = TipoAnalise
    template_name = "qualidade/tipo_lista.html"
    campos_pesquisa = ["nome", "unidade"]
    colunas = ["Nome", "Unidade", "Referência"]
    titulo = "Tipos de análise"
    url_criar = "qualidade:tipo_criar"
    url_editar = "qualidade:tipo_editar"


class TipoAnaliseConfig:
    model = TipoAnalise
    form_class = TipoAnaliseForm
    titulo = "Tipos de análise"
    url_lista = "qualidade:tipo_lista"
    success_url = reverse_lazy("qualidade:tipo_lista")


class TipoAnaliseCriarView(TipoAnaliseConfig, CadastroCreateView):
    modulo = MODULO


class TipoAnaliseEditarView(TipoAnaliseConfig, CadastroUpdateView):
    modulo = MODULO
