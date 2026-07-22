from django.contrib import messages
from django.forms import inlineformset_factory
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DetailView, TemplateView

from apps.accounts.mixins import AcessoModuloMixin, AcessoQualquerModuloMixin
from apps.accounts.perfis import usuario_acessa_modulo
from apps.core.views import CadastroCreateView, CadastroListView, CadastroUpdateView

from .forms import (
    BalancaForm,
    ClienteEnderecoForm,
    ClienteForm,
    ClienteTelefoneForm,
    DocumentoClienteForm,
    EmbalagemForm,
    EnderecoFormSet,
    EquipamentoForm,
    FornecedorEnderecoForm,
    FornecedorForm,
    FornecedorTelefoneForm,
    MateriaPrimaForm,
    ProdutoForm,
    SetorForm,
    TelefoneFormSet,
    VersaoArteForm,
)
from .models import (
    Balanca,
    Cliente,
    ClienteEndereco,
    ClienteTelefone,
    DocumentoCliente,
    Embalagem,
    Equipamento,
    Fornecedor,
    FornecedorEndereco,
    FornecedorTelefone,
    MateriaPrima,
    Produto,
    Setor,
    VersaoArte,
)

MODULO = "cadastros"

# Cards da página inicial do módulo (e referência única de rotas/ícones)
CADASTROS = [
    {
        "titulo": "Clientes",
        "descricao": "Quem compra os produtos da fábrica",
        "icone": "bi-building",
        "url_name": "cadastros:cliente_lista",
    },
    {
        "titulo": "Fornecedores",
        "descricao": "De quem compramos matérias-primas e embalagens",
        "icone": "bi-truck",
        "url_name": "cadastros:fornecedor_lista",
    },
    {
        "titulo": "Produtos",
        "descricao": "Produtos acabados que a fábrica produz",
        "icone": "bi-box-seam",
        "url_name": "cadastros:produto_lista",
    },
    {
        "titulo": "Matérias-primas",
        "descricao": "Insumos usados na produção",
        "icone": "bi-droplet",
        "url_name": "cadastros:materiaprima_lista",
    },
    {
        "titulo": "Embalagens",
        "descricao": "Frascos, tampas, válvulas, rótulos e caixas",
        "icone": "bi-bag",
        "url_name": "cadastros:embalagem_lista",
    },
    {
        "titulo": "Equipamentos",
        "descricao": "Máquinas e equipamentos da produção",
        "icone": "bi-gear-wide-connected",
        "url_name": "cadastros:equipamento_lista",
    },
    {
        "titulo": "Setores",
        "descricao": "Setores da fábrica",
        "icone": "bi-diagram-3",
        "url_name": "cadastros:setor_lista",
    },
    {
        "titulo": "Balanças",
        "descricao": "Balanças de pesagem e validade da calibração",
        "icone": "bi-speedometer2",
        "url_name": "cadastros:balanca_lista",
    },
    {
        "titulo": "Versões de arte",
        "descricao": "Artes de rótulo/embalagem aprovadas por produto",
        "icone": "bi-palette",
        "url_name": "cadastros:versaoarte_lista",
    },
]


class CadastrosHomeView(AcessoModuloMixin, TemplateView):
    modulo = MODULO
    template_name = "cadastros/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cadastros"] = CADASTROS
        return context


class ListaBase(CadastroListView):
    modulo = MODULO


class CriarBase(CadastroCreateView):
    modulo = MODULO


class EditarBase(CadastroUpdateView):
    modulo = MODULO


class PessoaComContatosMixin:
    telefone_model = None
    telefone_form_class = None
    telefone_fk_name = None
    endereco_model = None
    endereco_form_class = None
    endereco_fk_name = None

    def get_telefone_formset_class(self):
        return inlineformset_factory(
            self.model,
            self.telefone_model,
            form=self.telefone_form_class,
            formset=TelefoneFormSet,
            fk_name=self.telefone_fk_name,
            extra=1,
            can_delete=True,
        )

    def get_endereco_formset_class(self):
        return inlineformset_factory(
            self.model,
            self.endereco_model,
            form=self.endereco_form_class,
            formset=EnderecoFormSet,
            fk_name=self.endereco_fk_name,
            extra=1,
            can_delete=True,
        )

    def get_telefone_formset(self, instance=None):
        kwargs = {
            "instance": instance if instance is not None else getattr(self, "object", None),
            "prefix": "telefones",
            "queryset": self.telefone_model.objects.filter(ativo=True),
        }
        if self.request.method in {"POST", "PUT"}:
            kwargs["data"] = self.request.POST
        return self.get_telefone_formset_class()(**kwargs)

    def get_endereco_formset(self, instance=None):
        kwargs = {
            "instance": instance if instance is not None else getattr(self, "object", None),
            "prefix": "enderecos",
            "queryset": self.endereco_model.objects.filter(ativo=True),
        }
        if self.request.method in {"POST", "PUT"}:
            kwargs["data"] = self.request.POST
        return self.get_endereco_formset_class()(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        telefone_formset = kwargs.get("telefone_formset") or self.get_telefone_formset()
        endereco_formset = kwargs.get("endereco_formset") or self.get_endereco_formset()
        telefone_tem_erros = self._formset_tem_erros(telefone_formset)
        endereco_tem_erros = self._formset_tem_erros(endereco_formset)

        context["usa_contatos_multiplos"] = True
        context["telefone_formset"] = telefone_formset
        context["endereco_formset"] = endereco_formset
        context["telefone_formset_tem_erros"] = telefone_tem_erros
        context["endereco_formset_tem_erros"] = endereco_tem_erros
        context["aba_contato_ativa"] = self._aba_contato_ativa(
            context.get("form"), telefone_tem_erros, endereco_tem_erros
        )
        return context

    def _formset_tem_erros(self, formset):
        return formset.is_bound and (
            formset.total_error_count() > 0 or bool(formset.non_form_errors())
        )

    def _aba_contato_ativa(self, form, telefone_tem_erros, endereco_tem_erros):
        if form and form.errors:
            return "dados"
        if telefone_tem_erros:
            return "telefones"
        if endereco_tem_erros:
            return "enderecos"
        return "dados"

    def form_valid(self, form):
        self.object = form.save(commit=False)
        if self.object.pk is None:
            self.object.criado_por = self.request.user
        self.object.atualizado_por = self.request.user

        telefone_formset = self.get_telefone_formset(instance=self.object)
        endereco_formset = self.get_endereco_formset(instance=self.object)

        if not telefone_formset.is_valid() or not endereco_formset.is_valid():
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    telefone_formset=telefone_formset,
                    endereco_formset=endereco_formset,
                )
            )

        self.object.save()
        form.save_m2m()
        self._salvar_formset(telefone_formset)
        self._salvar_formset(endereco_formset)

        success_message = self.get_success_message(form.cleaned_data)
        if success_message:
            messages.success(self.request, success_message)
        return HttpResponseRedirect(self.get_success_url())

    def _salvar_formset(self, formset):
        instancias = formset.save(commit=False)

        for objeto in formset.deleted_objects:
            objeto.ativo = False
            objeto.atualizado_por = self.request.user
            objeto.save()

        for objeto in instancias:
            if objeto.pk is None:
                objeto.criado_por = self.request.user
            objeto.atualizado_por = self.request.user
            objeto.ativo = True
            objeto.save()

        formset.save_m2m()


# Setores


class SetorConfig:
    model = Setor
    form_class = SetorForm
    titulo = "Setores"
    url_lista = "cadastros:setor_lista"
    success_url = reverse_lazy("cadastros:setor_lista")


class SetorListView(SetorConfig, ListaBase):
    template_name = "cadastros/setor_lista.html"
    campos_pesquisa = ["nome", "descricao"]
    colunas = ["Nome", "Descrição"]
    url_criar = "cadastros:setor_criar"
    url_detalhe = "cadastros:setor_detalhe"
    url_editar = "cadastros:setor_editar"


class SetorCriarView(SetorConfig, CriarBase):
    pass


class SetorEditarView(SetorConfig, EditarBase):
    pass


class SetorDetalheView(AcessoQualquerModuloMixin, DetailView):
    """Ficha do setor/linha de produção."""

    modulos = ("cadastros", "pcp", "ordens", "producao")
    model = Setor
    template_name = "cadastros/setor_detalhe.html"
    context_object_name = "setor"

    def get_context_data(self, **kwargs):
        from apps.producao.models import EnvaseOP

        context = super().get_context_data(**kwargs)
        setor = self.object
        context["equipamentos"] = setor.equipamentos.order_by("nome")
        context["ordens"] = (
            setor.ordens.select_related(
                "item_pedido__produto",
                "item_pedido__pedido__cliente",
                "equipamento",
            )
            .order_by("-criado_em")[:8]
        )
        context["envases"] = (
            EnvaseOP.objects.filter(linha=setor)
            .select_related("ordem", "versao_arte__produto", "operador")
            .order_by("-registrado_em")[:8]
        )
        context["pode_editar"] = usuario_acessa_modulo(
            self.request.user, "cadastros"
        )
        return context


# Balanças


class BalancaConfig:
    model = Balanca
    form_class = BalancaForm
    titulo = "Balanças"
    url_lista = "cadastros:balanca_lista"
    success_url = reverse_lazy("cadastros:balanca_lista")


class BalancaListView(BalancaConfig, ListaBase):
    template_name = "cadastros/balanca_lista.html"
    campos_pesquisa = ["codigo", "descricao", "localizacao"]
    colunas = ["Código", "Descrição", "Calibração", "Situação"]
    url_criar = "cadastros:balanca_criar"
    url_detalhe = "cadastros:balanca_detalhe"
    url_editar = "cadastros:balanca_editar"


class BalancaCriarView(BalancaConfig, CriarBase):
    pass


class BalancaEditarView(BalancaConfig, EditarBase):
    pass


class BalancaDetalheView(AcessoQualquerModuloMixin, DetailView):
    """Ficha da balança de pesagem."""

    modulos = ("cadastros", "producao")
    model = Balanca
    template_name = "cadastros/balanca_detalhe.html"
    context_object_name = "balanca"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        balanca = self.object
        context["pesagens"] = (
            balanca.pesagens.select_related(
                "material__ordem",
                "material__materia_prima",
                "material__embalagem",
                "lote",
                "operador",
                "conferente",
            )
            .order_by("-data")[:10]
        )
        context["pode_editar"] = usuario_acessa_modulo(
            self.request.user, "cadastros"
        )
        return context


# Versões de arte


class VersaoArteConfig:
    model = VersaoArte
    form_class = VersaoArteForm
    titulo = "Versões de arte"
    url_lista = "cadastros:versaoarte_lista"
    success_url = reverse_lazy("cadastros:versaoarte_lista")


class VersaoArteListView(VersaoArteConfig, ListaBase):
    template_name = "cadastros/versaoarte_lista.html"
    campos_pesquisa = ["produto__codigo", "produto__nome", "versao"]
    colunas = ["Produto", "Versão", "Aprovação", "Situação"]
    url_criar = "cadastros:versaoarte_criar"
    url_detalhe = "cadastros:versaoarte_detalhe"
    url_editar = "cadastros:versaoarte_editar"

    def get_queryset(self):
        return super().get_queryset().select_related("produto")


class VersaoArteCriarView(VersaoArteConfig, CriarBase):
    pass


class VersaoArteEditarView(VersaoArteConfig, EditarBase):
    pass


class VersaoArteDetalheView(AcessoQualquerModuloMixin, DetailView):
    """Ficha da versão de arte."""

    modulos = ("cadastros", "producao")
    model = VersaoArte
    template_name = "cadastros/versaoarte_detalhe.html"
    context_object_name = "versao_arte"

    def get_queryset(self):
        return VersaoArte.objects.select_related("produto")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        versao_arte = self.object
        context["embalagens"] = versao_arte.embalagens.order_by("nome")
        context["envases"] = (
            versao_arte.envases.select_related("ordem", "linha", "operador")
            .order_by("-registrado_em")[:10]
        )
        context["pode_editar"] = usuario_acessa_modulo(
            self.request.user, "cadastros"
        )
        return context


# Equipamentos


class EquipamentoConfig:
    model = Equipamento
    form_class = EquipamentoForm
    titulo = "Equipamentos"
    url_lista = "cadastros:equipamento_lista"
    success_url = reverse_lazy("cadastros:equipamento_lista")
    form_tabs = (
        {
            "id": "equipamento-dados",
            "label": "Dados",
            "icon": "bi-card-text",
            "description": "Código, nome, setor e situação operacional.",
            "fields": ("codigo", "nome", "setor", "status", "ativo"),
        },
        {
            "id": "equipamento-operacao",
            "label": "Operação",
            "icon": "bi-speedometer2",
            "description": "Localização e capacidade do equipamento.",
            "fields": ("localizacao", "capacidade", "unidade_capacidade"),
        },
        {
            "id": "equipamento-manutencao",
            "label": "Manutenção",
            "icon": "bi-tools",
            "description": "Limpeza, sanitização, manutenção e calibração.",
            "fields": (
                "ultima_limpeza",
                "ultima_sanitizacao",
                "manutencao_validade",
                "calibracao_validade",
            ),
        },
        {
            "id": "equipamento-observacoes",
            "label": "Observações",
            "icon": "bi-chat-left-text",
            "fields": ("observacoes",),
        },
    )


class EquipamentoListView(EquipamentoConfig, ListaBase):
    template_name = "cadastros/equipamento_lista.html"
    campos_pesquisa = ["codigo", "nome", "setor__nome"]
    colunas = ["Código", "Nome", "Setor", "Situação", "Capacidade"]
    url_criar = "cadastros:equipamento_criar"
    url_detalhe = "cadastros:equipamento_detalhe"
    url_editar = "cadastros:equipamento_editar"

    def get_queryset(self):
        return super().get_queryset().select_related("setor")


class EquipamentoCriarView(EquipamentoConfig, CriarBase):
    pass


class EquipamentoEditarView(EquipamentoConfig, EditarBase):
    pass


class EquipamentoDetalheView(AcessoQualquerModuloMixin, DetailView):
    """Ficha do equipamento."""

    modulos = ("cadastros", "pcp", "ordens", "producao", "qualidade")
    model = Equipamento
    template_name = "cadastros/equipamento_detalhe.html"
    context_object_name = "equipamento"

    def get_queryset(self):
        return Equipamento.objects.select_related("setor")

    def get_context_data(self, **kwargs):
        from apps.producao.models import ChecklistEquipamentoOP, ControleProcessoOP

        context = super().get_context_data(**kwargs)
        equipamento = self.object
        context["programacoes"] = (
            equipamento.programacoes.filter(ativo=True)
            .select_related("item__produto", "item__pedido__cliente", "operador")
            .order_by("data", "id")[:8]
        )
        context["ordens"] = (
            equipamento.ordens.select_related(
                "item_pedido__produto",
                "item_pedido__pedido__cliente",
                "linha",
                "operador",
            )
            .order_by("-criado_em")[:8]
        )
        context["checklists"] = (
            ChecklistEquipamentoOP.objects.filter(equipamento=equipamento)
            .select_related("ordem", "responsavel")
            .order_by("-data")[:8]
        )
        context["controles"] = (
            ControleProcessoOP.objects.filter(equipamento=equipamento)
            .select_related("ordem", "tipo", "analista")
            .order_by("-data")[:8]
        )
        context["pode_editar"] = usuario_acessa_modulo(
            self.request.user, "cadastros"
        )
        return context


# Clientes


class ClienteConfig:
    model = Cliente
    form_class = ClienteForm
    telefone_model = ClienteTelefone
    telefone_form_class = ClienteTelefoneForm
    telefone_fk_name = "cliente"
    endereco_model = ClienteEndereco
    endereco_form_class = ClienteEnderecoForm
    endereco_fk_name = "cliente"
    titulo = "Clientes"
    url_lista = "cadastros:cliente_lista"
    success_url = reverse_lazy("cadastros:cliente_lista")


class ClienteListView(ClienteConfig, ListaBase):
    template_name = "cadastros/cliente_lista.html"
    campos_pesquisa = [
        "razao_social",
        "nome_fantasia",
        "documento",
        "enderecos__cidade",
        "enderecos__uf",
        "telefones__telefone",
    ]
    colunas = ["Razão social / Nome", "CNPJ/CPF", "Cidade/UF", "Telefone principal"]
    url_criar = "cadastros:cliente_criar"
    url_detalhe = "cadastros:cliente_detalhe"
    url_editar = "cadastros:cliente_editar"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("telefones", "enderecos").distinct()


class ClienteCriarView(ClienteConfig, PessoaComContatosMixin, CriarBase):
    pass


class ClienteEditarView(ClienteConfig, PessoaComContatosMixin, EditarBase):
    pass


class ClienteDetalheView(AcessoQualquerModuloMixin, DetailView):
    """Ficha consolidada do cliente (Etapa 10, PDF 3.1)."""

    modulos = ("cadastros", "pedidos", "expedicao")
    model = Cliente
    template_name = "cadastros/cliente_detalhe.html"
    context_object_name = "cliente"

    def get_queryset(self):
        return Cliente.objects.prefetch_related("telefones", "enderecos")

    def get_context_data(self, **kwargs):
        from apps.estoque.models import Lote

        context = super().get_context_data(**kwargs)
        cliente = self.object
        context["documentos"] = cliente.documentos.filter(ativo=True)
        context["pedidos"] = cliente.pedidos.order_by("-criado_em")
        context["produtos"] = (
            Produto.objects.filter(itens_de_pedido__pedido__cliente=cliente)
            .distinct()
            .order_by("nome")
        )
        context["lotes"] = (
            Lote.objects.filter(
                ordens_de_producao__item_pedido__pedido__cliente=cliente
            )
            .select_related("produto")
            .distinct()
            .order_by("-id")
        )
        context["pode_editar"] = usuario_acessa_modulo(
            self.request.user, "cadastros"
        )
        context["documento_form"] = DocumentoClienteForm()
        return context


class DocumentoClienteCriarView(AcessoModuloMixin, View):
    modulo = MODULO

    def post(self, request, cliente_pk):
        cliente = get_object_or_404(Cliente, pk=cliente_pk)
        form = DocumentoClienteForm(request.POST, request.FILES)
        if form.is_valid():
            documento = form.save(commit=False)
            documento.cliente = cliente
            documento.criado_por = request.user
            documento.atualizado_por = request.user
            documento.save()
            messages.success(request, "Documento adicionado à ficha do cliente.")
        else:
            messages.error(request, "Revise os dados do documento e tente de novo.")
        return redirect("cadastros:cliente_detalhe", pk=cliente.pk)


class DocumentoClienteRemoverView(AcessoModuloMixin, View):
    modulo = MODULO

    def post(self, request, pk):
        documento = get_object_or_404(DocumentoCliente, pk=pk)
        documento.ativo = False
        documento.atualizado_por = request.user
        documento.save()
        messages.success(request, "Documento removido da ficha.")
        return redirect("cadastros:cliente_detalhe", pk=documento.cliente_id)


# Fornecedores


class FornecedorConfig:
    model = Fornecedor
    form_class = FornecedorForm
    telefone_model = FornecedorTelefone
    telefone_form_class = FornecedorTelefoneForm
    telefone_fk_name = "fornecedor"
    endereco_model = FornecedorEndereco
    endereco_form_class = FornecedorEnderecoForm
    endereco_fk_name = "fornecedor"
    titulo = "Fornecedores"
    url_lista = "cadastros:fornecedor_lista"
    success_url = reverse_lazy("cadastros:fornecedor_lista")


class FornecedorListView(FornecedorConfig, ListaBase):
    template_name = "cadastros/fornecedor_lista.html"
    campos_pesquisa = [
        "razao_social",
        "nome_fantasia",
        "documento",
        "enderecos__cidade",
        "enderecos__uf",
        "telefones__telefone",
    ]
    colunas = ["Razão social / Nome", "CNPJ/CPF", "Cidade/UF", "Telefone principal"]
    url_criar = "cadastros:fornecedor_criar"
    url_detalhe = "cadastros:fornecedor_detalhe"
    url_editar = "cadastros:fornecedor_editar"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("telefones", "enderecos").distinct()


class FornecedorCriarView(FornecedorConfig, PessoaComContatosMixin, CriarBase):
    pass


class FornecedorEditarView(FornecedorConfig, PessoaComContatosMixin, EditarBase):
    pass


class FornecedorDetalheView(AcessoQualquerModuloMixin, DetailView):
    """Ficha consolidada do fornecedor."""

    modulos = ("cadastros", "estoque", "recebimento", "qualidade", "producao")
    model = Fornecedor
    template_name = "cadastros/fornecedor_detalhe.html"
    context_object_name = "fornecedor"

    def get_queryset(self):
        return Fornecedor.objects.prefetch_related(
            "telefones",
            "enderecos",
            "materias_primas_aprovadas",
            "embalagens_aprovadas",
        )

    def get_context_data(self, **kwargs):
        from django.db.models import Count

        from apps.recebimento.models import ItemRecebimento

        context = super().get_context_data(**kwargs)
        fornecedor = self.object
        context["recebimentos"] = (
            fornecedor.recebimentos.annotate(total_itens=Count("itens"))
            .order_by("-data_recebimento", "-id")[:8]
        )
        context["itens_recebidos"] = (
            ItemRecebimento.objects.filter(recebimento__fornecedor=fornecedor)
            .select_related(
                "recebimento",
                "lote",
                "produto",
                "materia_prima",
                "embalagem",
            )
            .order_by("-recebimento__data_recebimento", "-id")[:10]
        )
        context["materias_primas_aprovadas"] = (
            fornecedor.materias_primas_aprovadas.order_by("nome")
        )
        context["embalagens_aprovadas"] = fornecedor.embalagens_aprovadas.order_by(
            "nome"
        )
        context["pode_editar"] = usuario_acessa_modulo(
            self.request.user, "cadastros"
        )
        return context


# Produtos


class ProdutoConfig:
    model = Produto
    form_class = ProdutoForm
    titulo = "Produtos"
    url_lista = "cadastros:produto_lista"
    success_url = reverse_lazy("cadastros:produto_lista")
    form_tabs = (
        {
            "id": "produto-dados",
            "label": "Dados",
            "icon": "bi-card-text",
            "description": "Identificação comercial e unidade de estoque.",
            "fields": (
                "codigo",
                "nome",
                "descricao",
                "unidade",
                "estoque_minimo",
                "categoria",
                "apresentacao",
            ),
        },
        {
            "id": "produto-regulatorio",
            "label": "Regulatório",
            "icon": "bi-shield-check",
            "description": "Grau, registro e situação regulatória.",
            "fields": ("grau", "registro_anvisa", "situacao_regulatoria"),
        },
        {
            "id": "produto-producao",
            "label": "Produção",
            "icon": "bi-gear-wide-connected",
            "description": "Perdas permitidas, bloqueio e situação do cadastro.",
            "fields": (
                "limite_perda_percentual",
                "bloqueado",
                "motivo_bloqueio",
                "ativo",
            ),
        },
        {
            "id": "produto-observacoes",
            "label": "Observações",
            "icon": "bi-chat-left-text",
            "fields": ("observacoes",),
        },
    )


class ProdutoListView(ProdutoConfig, ListaBase):
    template_name = "cadastros/produto_lista.html"
    campos_pesquisa = ["codigo", "nome"]
    colunas = ["Código", "Nome", "Unidade", "Estoque mínimo"]
    url_criar = "cadastros:produto_criar"
    url_editar = "cadastros:produto_editar"


class ProdutoCriarView(ProdutoConfig, CriarBase):
    pass


class ProdutoEditarView(ProdutoConfig, EditarBase):
    pass


class ProdutoDetalheView(AcessoQualquerModuloMixin, DetailView):
    """Ficha consolidada do produto (Etapa 10, PDF 3.3)."""

    modulos = ("cadastros", "pcp", "ordens", "producao", "pedidos")
    model = Produto
    template_name = "cadastros/produto_detalhe.html"
    context_object_name = "produto"

    def get_context_data(self, **kwargs):
        from apps.ordens.models import OrdemProducao, StatusFormula

        context = super().get_context_data(**kwargs)
        produto = self.object
        formulas = produto.formulas.order_by("nome", "-versao")
        context["formulas"] = formulas
        context["formula_vigente"] = formulas.filter(
            ativo=True, status=StatusFormula.VIGENTE
        ).first()
        context["versoes_arte"] = produto.versoes_arte.all()
        context["especificacoes"] = produto.especificacoes.filter(
            ativo=True
        ).select_related("tipo")
        context["ordens"] = (
            OrdemProducao.objects.filter(item_pedido__produto=produto)
            .select_related("item_pedido__pedido__cliente", "lote_produto")
            .order_by("-criado_em")
        )
        context["lotes"] = produto.lotes.order_by("-id")
        context["clientes"] = (
            Cliente.objects.filter(pedidos__itens__produto=produto)
            .distinct()
            .order_by("razao_social")
        )
        context["pode_editar"] = usuario_acessa_modulo(
            self.request.user, "cadastros"
        )
        return context


# Matérias-primas


class MateriaPrimaConfig:
    model = MateriaPrima
    form_class = MateriaPrimaForm
    titulo = "Matérias-primas"
    url_lista = "cadastros:materiaprima_lista"
    success_url = reverse_lazy("cadastros:materiaprima_lista")
    form_tabs = (
        {
            "id": "materiaprima-dados",
            "label": "Dados",
            "icon": "bi-card-text",
            "description": "Código, nome, unidade, estoque mínimo e criticidade.",
            "fields": (
                "codigo",
                "nome",
                "unidade",
                "estoque_minimo",
                "critico",
                "ativo",
            ),
        },
        {
            "id": "materiaprima-tecnica",
            "label": "Técnica",
            "icon": "bi-droplet",
            "description": "INCI, CAS, especificação e armazenamento.",
            "fields": (
                "inci",
                "cas",
                "especificacao",
                "condicoes_armazenamento",
            ),
        },
        {
            "id": "materiaprima-documentos",
            "label": "Documentos",
            "icon": "bi-paperclip",
            "description": "Ficha técnica e FISPQ.",
            "fields": ("ficha_tecnica", "fispq"),
        },
        {
            "id": "materiaprima-fornecedores",
            "label": "Fornecedores",
            "icon": "bi-patch-check",
            "description": "Fornecedores aprovados para consumo.",
            "fields": ("fornecedores_aprovados",),
        },
        {
            "id": "materiaprima-observacoes",
            "label": "Observações",
            "icon": "bi-chat-left-text",
            "fields": ("observacoes",),
        },
    )


class MateriaPrimaListView(MateriaPrimaConfig, ListaBase):
    template_name = "cadastros/materiaprima_lista.html"
    campos_pesquisa = ["codigo", "nome"]
    colunas = ["Código", "Nome", "Unidade", "Estoque mínimo"]
    url_criar = "cadastros:materiaprima_criar"
    url_editar = "cadastros:materiaprima_editar"


class MateriaPrimaCriarView(MateriaPrimaConfig, CriarBase):
    pass


class MateriaPrimaEditarView(MateriaPrimaConfig, EditarBase):
    pass


class MateriaPrimaDetalheView(AcessoQualquerModuloMixin, DetailView):
    """Ficha da matéria-prima (Etapa 10, PDF 6.1)."""

    modulos = ("cadastros", "estoque", "producao", "recebimento", "qualidade")
    model = MateriaPrima
    template_name = "cadastros/materiaprima_detalhe.html"
    context_object_name = "materia_prima"

    def get_context_data(self, **kwargs):
        from apps.estoque.models import saldo

        context = super().get_context_data(**kwargs)
        materia_prima = self.object

        lotes = list(materia_prima.lotes.order_by("-id"))
        for lote in lotes:
            lote.saldo_atual = saldo(materia_prima, lote=lote)
        context["lotes"] = lotes
        context["fornecedores_aprovados"] = (
            materia_prima.fornecedores_aprovados.order_by("razao_social")
        )
        context["saldo_total"] = saldo(materia_prima)
        context["pode_editar"] = usuario_acessa_modulo(
            self.request.user, "cadastros"
        )
        return context


# Embalagens


class EmbalagemConfig:
    model = Embalagem
    form_class = EmbalagemForm
    titulo = "Embalagens"
    url_lista = "cadastros:embalagem_lista"
    success_url = reverse_lazy("cadastros:embalagem_lista")
    form_tabs = (
        {
            "id": "embalagem-dados",
            "label": "Dados",
            "icon": "bi-card-text",
            "description": "Código, nome, tipo, unidade e estoque mínimo.",
            "fields": (
                "codigo",
                "nome",
                "tipo",
                "unidade",
                "estoque_minimo",
                "ativo",
            ),
        },
        {
            "id": "embalagem-caracteristicas",
            "label": "Características",
            "icon": "bi-bag",
            "description": "Capacidade, material, cor e fabricante.",
            "fields": ("capacidade", "material", "cor", "fabricante"),
        },
        {
            "id": "embalagem-arte",
            "label": "Arte e inspeção",
            "icon": "bi-palette",
            "description": "Versão de arte e critérios de recebimento.",
            "fields": ("versao_arte", "inspecao"),
        },
        {
            "id": "embalagem-fornecedores",
            "label": "Fornecedores",
            "icon": "bi-patch-check",
            "description": "Fornecedores aprovados e observações do cadastro.",
            "fields": ("fornecedores_aprovados", "observacoes"),
        },
    )


class EmbalagemListView(EmbalagemConfig, ListaBase):
    template_name = "cadastros/embalagem_lista.html"
    campos_pesquisa = ["codigo", "nome"]
    colunas = ["Código", "Nome", "Tipo", "Unidade", "Estoque mínimo"]
    url_criar = "cadastros:embalagem_criar"
    url_editar = "cadastros:embalagem_editar"


class EmbalagemCriarView(EmbalagemConfig, CriarBase):
    pass


class EmbalagemEditarView(EmbalagemConfig, EditarBase):
    pass


class EmbalagemDetalheView(AcessoQualquerModuloMixin, DetailView):
    """Ficha da embalagem (Etapa 10, PDF 6.2)."""

    modulos = ("cadastros", "estoque", "producao", "recebimento", "qualidade")
    model = Embalagem
    template_name = "cadastros/embalagem_detalhe.html"
    context_object_name = "embalagem"

    def get_queryset(self):
        return Embalagem.objects.select_related("versao_arte__produto")

    def get_context_data(self, **kwargs):
        from apps.estoque.models import saldo

        context = super().get_context_data(**kwargs)
        embalagem = self.object

        lotes = list(embalagem.lotes.order_by("-id"))
        for lote in lotes:
            lote.saldo_atual = saldo(embalagem, lote=lote)
        context["lotes"] = lotes
        context["fornecedores_aprovados"] = (
            embalagem.fornecedores_aprovados.order_by("razao_social")
        )
        context["saldo_total"] = saldo(embalagem)
        context["pode_editar"] = usuario_acessa_modulo(
            self.request.user, "cadastros"
        )
        return context
