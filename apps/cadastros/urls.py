from django.urls import path

from . import views

app_name = "cadastros"

urlpatterns = [
    path("", views.CadastrosHomeView.as_view(), name="home"),
    # Setores
    path("setores/", views.SetorListView.as_view(), name="setor_lista"),
    path("setores/novo/", views.SetorCriarView.as_view(), name="setor_criar"),
    path("setores/<int:pk>/editar/", views.SetorEditarView.as_view(), name="setor_editar"),
    # Balanças
    path("balancas/", views.BalancaListView.as_view(), name="balanca_lista"),
    path("balancas/nova/", views.BalancaCriarView.as_view(), name="balanca_criar"),
    path(
        "balancas/<int:pk>/editar/",
        views.BalancaEditarView.as_view(),
        name="balanca_editar",
    ),
    # Versões de arte
    path("artes/", views.VersaoArteListView.as_view(), name="versaoarte_lista"),
    path("artes/nova/", views.VersaoArteCriarView.as_view(), name="versaoarte_criar"),
    path(
        "artes/<int:pk>/editar/",
        views.VersaoArteEditarView.as_view(),
        name="versaoarte_editar",
    ),
    # Equipamentos
    path("equipamentos/", views.EquipamentoListView.as_view(), name="equipamento_lista"),
    path("equipamentos/novo/", views.EquipamentoCriarView.as_view(), name="equipamento_criar"),
    path(
        "equipamentos/<int:pk>/editar/",
        views.EquipamentoEditarView.as_view(),
        name="equipamento_editar",
    ),
    # Clientes
    path("clientes/", views.ClienteListView.as_view(), name="cliente_lista"),
    path("clientes/novo/", views.ClienteCriarView.as_view(), name="cliente_criar"),
    path("clientes/<int:pk>/editar/", views.ClienteEditarView.as_view(), name="cliente_editar"),
    # Fornecedores
    path("fornecedores/", views.FornecedorListView.as_view(), name="fornecedor_lista"),
    path("fornecedores/novo/", views.FornecedorCriarView.as_view(), name="fornecedor_criar"),
    path(
        "fornecedores/<int:pk>/editar/",
        views.FornecedorEditarView.as_view(),
        name="fornecedor_editar",
    ),
    # Produtos
    path("produtos/", views.ProdutoListView.as_view(), name="produto_lista"),
    path("produtos/novo/", views.ProdutoCriarView.as_view(), name="produto_criar"),
    path("produtos/<int:pk>/editar/", views.ProdutoEditarView.as_view(), name="produto_editar"),
    # Matérias-primas
    path("materias-primas/", views.MateriaPrimaListView.as_view(), name="materiaprima_lista"),
    path(
        "materias-primas/novo/",
        views.MateriaPrimaCriarView.as_view(),
        name="materiaprima_criar",
    ),
    path(
        "materias-primas/<int:pk>/editar/",
        views.MateriaPrimaEditarView.as_view(),
        name="materiaprima_editar",
    ),
    # Embalagens
    path("embalagens/", views.EmbalagemListView.as_view(), name="embalagem_lista"),
    path("embalagens/novo/", views.EmbalagemCriarView.as_view(), name="embalagem_criar"),
    path(
        "embalagens/<int:pk>/editar/",
        views.EmbalagemEditarView.as_view(),
        name="embalagem_editar",
    ),
]
