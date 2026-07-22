import logging

from django.contrib import messages
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from apps.accounts.mixins import AcessoModuloMixin, AcessoQualquerModuloMixin
from apps.core.views import (
    CadastroCreateView,
    CadastroListView,
    CadastroUpdateView,
    SalvarComUsuarioMixin,
)

from .forms import LocalEstoqueForm, MovimentacaoForm
from .models import (
    LocalEstoque,
    Lote,
    Movimentacao,
    TipoMovimentacao,
    locais_do_lote,
    saldo,
    saldos_detalhados,
)

logger = logging.getLogger("fabriq")

MODULO = "estoque"

FILTROS_TIPO_ITEM = [
    ("produto", "Produtos"),
    ("materia_prima", "Matérias-primas"),
    ("embalagem", "Embalagens"),
]
ROTULO_POR_FILTRO = {
    "produto": "Produto",
    "materia_prima": "Matéria-prima",
    "embalagem": "Embalagem",
}


class SaldoView(AcessoModuloMixin, TemplateView):
    modulo = MODULO
    template_name = "estoque/saldo.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        tipo_item = self.request.GET.get("tipo_item", "")
        termo = self.request.GET.get("q", "").strip().lower()
        local_id = self.request.GET.get("local", "")
        mostrar_zerados = self.request.GET.get("zerados", "") == "1"

        linhas = saldos_detalhados()

        if tipo_item in ROTULO_POR_FILTRO:
            linhas = [
                linha
                for linha in linhas
                if linha["tipo_item"] == ROTULO_POR_FILTRO[tipo_item]
            ]
        if termo:
            linhas = [
                linha
                for linha in linhas
                if linha["item"]
                and (
                    termo in linha["item"].nome.lower()
                    or termo in linha["item"].codigo.lower()
                )
            ]
        if local_id.isdigit():
            linhas = [
                linha
                for linha in linhas
                if linha["local"] and linha["local"].pk == int(local_id)
            ]
        if not mostrar_zerados:
            linhas = [linha for linha in linhas if linha["saldo"] != 0]

        context.update(
            {
                "linhas": linhas,
                "locais": LocalEstoque.objects.filter(ativo=True),
                "tipos_item": FILTROS_TIPO_ITEM,
                "filtro_tipo_item": tipo_item,
                "filtro_q": self.request.GET.get("q", "").strip(),
                "filtro_local": local_id,
                "mostrar_zerados": mostrar_zerados,
            }
        )
        return context


class MovimentacaoListView(AcessoModuloMixin, ListView):
    modulo = MODULO
    model = Movimentacao
    template_name = "estoque/movimentacoes.html"
    context_object_name = "movimentacoes"
    paginate_by = 30

    def get_queryset(self):
        queryset = Movimentacao.objects.select_related(
            "produto",
            "materia_prima",
            "embalagem",
            "lote",
            "local_origem",
            "local_destino",
            "criado_por",
        )

        filtros = self.request.GET
        if filtros.get("de"):
            queryset = queryset.filter(criado_em__date__gte=filtros["de"])
        if filtros.get("ate"):
            queryset = queryset.filter(criado_em__date__lte=filtros["ate"])
        if filtros.get("tipo") in TipoMovimentacao.values:
            queryset = queryset.filter(tipo=filtros["tipo"])

        termo = filtros.get("q", "").strip()
        if termo:
            queryset = queryset.filter(
                Q(motivo__icontains=termo)
                | Q(documento__icontains=termo)
                | Q(lote__codigo__icontains=termo)
                | Q(produto__nome__icontains=termo)
                | Q(produto__codigo__icontains=termo)
                | Q(materia_prima__nome__icontains=termo)
                | Q(materia_prima__codigo__icontains=termo)
                | Q(embalagem__nome__icontains=termo)
                | Q(embalagem__codigo__icontains=termo)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.request.GET
        context.update(
            {
                "tipo_choices": TipoMovimentacao.choices,
                "filtro_de": filtros.get("de", ""),
                "filtro_ate": filtros.get("ate", ""),
                "filtro_tipo": filtros.get("tipo", ""),
                "filtro_q": filtros.get("q", "").strip(),
            }
        )
        return context


class MovimentarView(AcessoModuloMixin, SalvarComUsuarioMixin, CreateView):
    modulo = MODULO
    model = Movimentacao
    form_class = MovimentacaoForm
    template_name = "estoque/movimentar_form.html"
    success_url = reverse_lazy("estoque:saldo")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        movimentacao = self.object
        messages.success(
            self.request,
            f"{movimentacao.get_tipo_display()} de {movimentacao.item} "
            "registrada com sucesso.",
        )
        logger.info(
            "Movimentação %s (%s) registrada por %s",
            movimentacao.pk,
            movimentacao.tipo,
            self.request.user,
        )
        return response


# Locais de estoque — reutilizam o CRUD genérico dos cadastros


class LocalListView(CadastroListView):
    modulo = MODULO
    model = LocalEstoque
    template_name = "estoque/local_lista.html"
    campos_pesquisa = ["nome", "descricao"]
    colunas = ["Nome", "Descrição"]
    titulo = "Locais de estoque"
    url_criar = "estoque:local_criar"
    url_editar = "estoque:local_editar"


class LocalConfig:
    model = LocalEstoque
    form_class = LocalEstoqueForm
    titulo = "Locais de estoque"
    url_lista = "estoque:local_lista"
    success_url = reverse_lazy("estoque:local_lista")


class LocalCriarView(LocalConfig, CadastroCreateView):
    modulo = MODULO


class LocalEditarView(LocalConfig, CadastroUpdateView):
    modulo = MODULO


class LoteDetalheView(AcessoQualquerModuloMixin, DetailView):
    """
    Ficha do lote (Etapa 10, PDF 6.1): origem (fornecedor/recebimento),
    validade, situação, análises, saldo por local, consumo em OPs e
    expedições. É o nó que liga material, fornecedor e produção.
    """

    modulos = (
        "estoque", "cadastros", "producao", "recebimento", "qualidade", "expedicao",
    )
    model = Lote
    template_name = "estoque/lote_detalhe.html"
    context_object_name = "lote"

    def get_queryset(self):
        return Lote.objects.select_related("produto", "materia_prima", "embalagem")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lote = self.object

        context["posicoes"] = locais_do_lote(lote)
        context["saldo_total"] = saldo(lote.item, lote=lote)
        context["item_recebido"] = (
            lote.itens_de_recebimento.select_related(
                "recebimento__fornecedor"
            ).first()
        )
        context["analises"] = lote.analises.select_related("decidido_por").order_by(
            "-id"
        )
        context["consumos"] = (
            lote.consumos_em_op.select_related(
                "material__ordem__item_pedido__produto", "local"
            ).order_by("-id")
        )
        context["movimentacoes"] = lote.movimentacoes.select_related(
            "local_origem", "local_destino"
        ).order_by("-id")
        context["ordens_do_lote"] = lote.ordens_de_producao.select_related(
            "item_pedido__pedido__cliente"
        )
        context["expedicoes"] = lote.expedicoes.select_related(
            "expedicao__pedido__cliente", "item_pedido__produto"
        )
        return context
