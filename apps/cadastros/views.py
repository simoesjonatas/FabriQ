from django.contrib import messages
from django.forms import inlineformset_factory
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from apps.accounts.mixins import AcessoModuloMixin
from apps.core.views import CadastroCreateView, CadastroListView, CadastroUpdateView

from .forms import (
    BalancaForm,
    ClienteEnderecoForm,
    ClienteForm,
    ClienteTelefoneForm,
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
    url_editar = "cadastros:setor_editar"


class SetorCriarView(SetorConfig, CriarBase):
    pass


class SetorEditarView(SetorConfig, EditarBase):
    pass


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
    url_editar = "cadastros:balanca_editar"


class BalancaCriarView(BalancaConfig, CriarBase):
    pass


class BalancaEditarView(BalancaConfig, EditarBase):
    pass


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
    url_editar = "cadastros:versaoarte_editar"

    def get_queryset(self):
        return super().get_queryset().select_related("produto")


class VersaoArteCriarView(VersaoArteConfig, CriarBase):
    pass


class VersaoArteEditarView(VersaoArteConfig, EditarBase):
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
    colunas = ["Código", "Nome", "Setor", "Situação", "Capacidade"]
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
    url_editar = "cadastros:cliente_editar"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("telefones", "enderecos").distinct()


class ClienteCriarView(ClienteConfig, PessoaComContatosMixin, CriarBase):
    pass


class ClienteEditarView(ClienteConfig, PessoaComContatosMixin, EditarBase):
    pass


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
    url_editar = "cadastros:fornecedor_editar"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("telefones", "enderecos").distinct()


class FornecedorCriarView(FornecedorConfig, PessoaComContatosMixin, CriarBase):
    pass


class FornecedorEditarView(FornecedorConfig, PessoaComContatosMixin, EditarBase):
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
