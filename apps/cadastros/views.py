from django.urls import reverse_lazy
from django.views.generic import TemplateView

from apps.accounts.mixins import AcessoModuloMixin
from apps.core.views import CadastroCreateView, CadastroListView, CadastroUpdateView

from .forms import (
    ClienteForm,
    EmbalagemForm,
    EquipamentoForm,
    FornecedorForm,
    MateriaPrimaForm,
    ProdutoForm,
    SetorForm,
)
from .models import (
    Cliente,
    Embalagem,
    Equipamento,
    Fornecedor,
    MateriaPrima,
    Produto,
    Setor,
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
    url_editar = "cadastros:setor_editar"


class SetorCriarView(SetorConfig, CriarBase):
    pass


class SetorEditarView(SetorConfig, EditarBase):
    pass


# Equipamentos


class EquipamentoConfig:
    model = Equipamento
    form_class = EquipamentoForm
    titulo = "Equipamentos"
    url_lista = "cadastros:equipamento_lista"
    success_url = reverse_lazy("cadastros:equipamento_lista")


class EquipamentoListView(EquipamentoConfig, ListaBase):
    template_name = "cadastros/equipamento_lista.html"
    campos_pesquisa = ["codigo", "nome", "setor__nome"]
    colunas = ["Código", "Nome", "Setor", "Capacidade"]
    url_criar = "cadastros:equipamento_criar"
    url_editar = "cadastros:equipamento_editar"

    def get_queryset(self):
        return super().get_queryset().select_related("setor")


class EquipamentoCriarView(EquipamentoConfig, CriarBase):
    pass


class EquipamentoEditarView(EquipamentoConfig, EditarBase):
    pass


# Clientes


class ClienteConfig:
    model = Cliente
    form_class = ClienteForm
    titulo = "Clientes"
    url_lista = "cadastros:cliente_lista"
    success_url = reverse_lazy("cadastros:cliente_lista")


class ClienteListView(ClienteConfig, ListaBase):
    template_name = "cadastros/cliente_lista.html"
    campos_pesquisa = ["razao_social", "nome_fantasia", "documento", "cidade"]
    colunas = ["Razão social / Nome", "CNPJ/CPF", "Cidade/UF", "Telefone"]
    url_criar = "cadastros:cliente_criar"
    url_editar = "cadastros:cliente_editar"


class ClienteCriarView(ClienteConfig, CriarBase):
    pass


class ClienteEditarView(ClienteConfig, EditarBase):
    pass


# Fornecedores


class FornecedorConfig:
    model = Fornecedor
    form_class = FornecedorForm
    titulo = "Fornecedores"
    url_lista = "cadastros:fornecedor_lista"
    success_url = reverse_lazy("cadastros:fornecedor_lista")


class FornecedorListView(FornecedorConfig, ListaBase):
    template_name = "cadastros/fornecedor_lista.html"
    campos_pesquisa = ["razao_social", "nome_fantasia", "documento", "cidade"]
    colunas = ["Razão social / Nome", "CNPJ/CPF", "Cidade/UF", "Telefone"]
    url_criar = "cadastros:fornecedor_criar"
    url_editar = "cadastros:fornecedor_editar"


class FornecedorCriarView(FornecedorConfig, CriarBase):
    pass


class FornecedorEditarView(FornecedorConfig, EditarBase):
    pass


# Produtos


class ProdutoConfig:
    model = Produto
    form_class = ProdutoForm
    titulo = "Produtos"
    url_lista = "cadastros:produto_lista"
    success_url = reverse_lazy("cadastros:produto_lista")


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


# Matérias-primas


class MateriaPrimaConfig:
    model = MateriaPrima
    form_class = MateriaPrimaForm
    titulo = "Matérias-primas"
    url_lista = "cadastros:materiaprima_lista"
    success_url = reverse_lazy("cadastros:materiaprima_lista")


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


# Embalagens


class EmbalagemConfig:
    model = Embalagem
    form_class = EmbalagemForm
    titulo = "Embalagens"
    url_lista = "cadastros:embalagem_lista"
    success_url = reverse_lazy("cadastros:embalagem_lista")


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
