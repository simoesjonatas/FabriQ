from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.perfis import PCP, PRODUCAO

from .models import (
    Cliente,
    ClienteEndereco,
    ClienteTelefone,
    Equipamento,
    Fornecedor,
    FornecedorEndereco,
    FornecedorTelefone,
    Produto,
    Setor,
)

User = get_user_model()


def criar_usuario(username, perfil=None, senha="senha-forte-123"):
    usuario = User.objects.create_user(username=username, password=senha)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class ModelosTests(TestCase):
    def test_str_dos_itens_usa_codigo_e_nome(self):
        produto = Produto.objects.create(codigo="P001", nome="Perfume Lavanda 100ml")
        self.assertEqual(str(produto), "P001 · Perfume Lavanda 100ml")

    def test_equipamento_vinculado_ao_setor(self):
        setor = Setor.objects.create(nome="Envase")
        equipamento = Equipamento.objects.create(
            codigo="EQ01", nome="Envasadora 1", setor=setor
        )
        self.assertIn(equipamento, setor.equipamentos.all())

    def test_cliente_str_prefere_nome_fantasia(self):
        cliente = Cliente.objects.create(
            razao_social="Comércio de Cosméticos LTDA", nome_fantasia="Loja Bela Pele"
        )
        self.assertEqual(str(cliente), "Loja Bela Pele")


class PermissoesTests(TestCase):
    def setUp(self):
        criar_usuario("pcp", perfil=PCP)
        criar_usuario("operador", perfil=PRODUCAO)

    def test_anonimo_redireciona_para_login(self):
        response = self.client.get(reverse("cadastros:home"))
        self.assertEqual(response.status_code, 302)

    def test_producao_nao_acessa_cadastros(self):
        self.client.login(username="operador", password="senha-forte-123")
        response = self.client.get(reverse("cadastros:home"))
        self.assertEqual(response.status_code, 403)

    def test_pcp_acessa_cadastros(self):
        self.client.login(username="pcp", password="senha-forte-123")
        for rota in [
            "cadastros:home",
            "cadastros:setor_lista",
            "cadastros:equipamento_lista",
            "cadastros:cliente_lista",
            "cadastros:fornecedor_lista",
            "cadastros:produto_lista",
            "cadastros:materiaprima_lista",
            "cadastros:embalagem_lista",
        ]:
            with self.subTest(rota=rota):
                response = self.client.get(reverse(rota))
                self.assertEqual(response.status_code, 200)


class CrudEAuditoriaTests(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("pcp", perfil=PCP)
        self.client.login(username="pcp", password="senha-forte-123")

    def test_criar_registra_usuario_e_datas(self):
        response = self.client.post(
            reverse("cadastros:setor_criar"),
            {"nome": "Envase", "descricao": "", "ativo": "on"},
        )
        self.assertRedirects(response, reverse("cadastros:setor_lista"))
        setor = Setor.objects.get(nome="Envase")
        self.assertEqual(setor.criado_por, self.usuario)
        self.assertEqual(setor.atualizado_por, self.usuario)
        self.assertIsNotNone(setor.criado_em)

    def test_editar_atualiza_auditoria_sem_perder_criador(self):
        criador = criar_usuario("almoxarife")
        setor = Setor.objects.create(nome="Pesagem", criado_por=criador)

        response = self.client.post(
            reverse("cadastros:setor_editar", args=[setor.pk]),
            {"nome": "Pesagem Central", "descricao": "", "ativo": "on"},
        )
        self.assertRedirects(response, reverse("cadastros:setor_lista"))
        setor.refresh_from_db()
        self.assertEqual(setor.nome, "Pesagem Central")
        self.assertEqual(setor.criado_por, criador)
        self.assertEqual(setor.atualizado_por, self.usuario)

    def test_inativar_em_vez_de_excluir(self):
        setor = Setor.objects.create(nome="Rotulagem")
        self.client.post(
            reverse("cadastros:setor_editar", args=[setor.pk]),
            {"nome": "Rotulagem", "descricao": ""},  # ativo desmarcado
        )
        setor.refresh_from_db()
        self.assertFalse(setor.ativo)
        self.assertTrue(Setor.objects.filter(pk=setor.pk).exists())

    def test_auditoria_aparece_na_tela_de_edicao(self):
        setor = Setor.objects.create(nome="Almoxarifado", criado_por=self.usuario)
        response = self.client.get(reverse("cadastros:setor_editar", args=[setor.pk]))
        self.assertContains(response, "Criado em")
        self.assertContains(response, "Última alteração em")


class ListaTests(TestCase):
    def setUp(self):
        criar_usuario("pcp", perfil=PCP)
        self.client.login(username="pcp", password="senha-forte-123")

    def test_pesquisa_por_nome(self):
        Produto.objects.create(codigo="P001", nome="Perfume Lavanda")
        Produto.objects.create(codigo="P002", nome="Sabonete Erva-doce")
        response = self.client.get(reverse("cadastros:produto_lista"), {"q": "lavanda"})
        self.assertContains(response, "Perfume Lavanda")
        self.assertNotContains(response, "Sabonete Erva-doce")

    def test_filtro_por_situacao(self):
        Produto.objects.create(codigo="P001", nome="Perfume Ativo")
        Produto.objects.create(codigo="P002", nome="Perfume Antigo", ativo=False)
        response = self.client.get(
            reverse("cadastros:produto_lista"), {"status": "inativos"}
        )
        self.assertContains(response, "Perfume Antigo")
        self.assertNotContains(response, "Perfume Ativo")

    def test_paginacao(self):
        for indice in range(25):
            Produto.objects.create(codigo=f"P{indice:03d}", nome=f"Produto {indice:03d}")
        response = self.client.get(reverse("cadastros:produto_lista"))
        self.assertContains(response, "Página 1 de 2")
        response = self.client.get(reverse("cadastros:produto_lista"), {"page": 2})
        self.assertContains(response, "Página 2 de 2")


class DocumentoTests(TestCase):
    def setUp(self):
        criar_usuario("compras", perfil=PCP)
        self.client.login(username="compras", password="senha-forte-123")

    def dados_cliente(self, **kwargs):
        dados = {
            "razao_social": "Comércio de Cosméticos LTDA",
            "nome_fantasia": "",
            "documento": "18.745.233/0001-89",
            "email": "",
            "observacoes": "",
            "ativo": "on",
            "telefones-TOTAL_FORMS": "0",
            "telefones-INITIAL_FORMS": "0",
            "telefones-MIN_NUM_FORMS": "0",
            "telefones-MAX_NUM_FORMS": "1000",
            "enderecos-TOTAL_FORMS": "0",
            "enderecos-INITIAL_FORMS": "0",
            "enderecos-MIN_NUM_FORMS": "0",
            "enderecos-MAX_NUM_FORMS": "1000",
        }
        dados.update(kwargs)
        return dados

    def test_documento_normalizado_para_somente_numeros(self):
        self.client.post(reverse("cadastros:cliente_criar"), self.dados_cliente())
        cliente = Cliente.objects.get()
        self.assertEqual(cliente.documento, "18745233000189")

    def test_documento_invalido_mostra_erro_no_formulario(self):
        response = self.client.post(
            reverse("cadastros:cliente_criar"),
            self.dados_cliente(documento="11.111.111/1111-11"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informe um CPF ou CNPJ válido.")
        self.assertEqual(Cliente.objects.count(), 0)

    def test_documento_duplicado_mostra_erro_no_formulario(self):
        self.client.post(reverse("cadastros:cliente_criar"), self.dados_cliente())
        response = self.client.post(
            reverse("cadastros:cliente_criar"),
            self.dados_cliente(razao_social="Outra Empresa LTDA"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Já existe um cliente com este CNPJ/CPF.")
        self.assertEqual(Cliente.objects.count(), 1)

    def test_dois_clientes_sem_documento_sao_permitidos(self):
        self.client.post(
            reverse("cadastros:cliente_criar"),
            self.dados_cliente(documento="", razao_social="Empresa A"),
        )
        self.client.post(
            reverse("cadastros:cliente_criar"),
            self.dados_cliente(documento="", razao_social="Empresa B"),
        )
        self.assertEqual(Cliente.objects.count(), 2)

    def test_cliente_permite_multiplos_telefones_e_enderecos(self):
        dados = self.dados_cliente(
            **{
                "telefones-TOTAL_FORMS": "2",
                "telefones-0-tipo": "COMERCIAL",
                "telefones-0-telefone": "11999990000",
                "telefones-0-contato": "Compras",
                "telefones-0-principal": "on",
                "telefones-0-observacoes": "",
                "telefones-1-tipo": "FINANCEIRO",
                "telefones-1-telefone": "(11) 3333-4444",
                "telefones-1-contato": "Financeiro",
                "telefones-1-observacoes": "",
                "enderecos-TOTAL_FORMS": "2",
                "enderecos-0-tipo": "COMERCIAL",
                "enderecos-0-cep": "01001000",
                "enderecos-0-logradouro": "Praça da Sé",
                "enderecos-0-numero": "100",
                "enderecos-0-complemento": "",
                "enderecos-0-bairro": "Sé",
                "enderecos-0-cidade": "São Paulo",
                "enderecos-0-uf": "SP",
                "enderecos-0-principal": "on",
                "enderecos-0-observacoes": "",
                "enderecos-1-tipo": "ENTREGA",
                "enderecos-1-cep": "20040002",
                "enderecos-1-logradouro": "Rua da Assembleia",
                "enderecos-1-numero": "10",
                "enderecos-1-complemento": "",
                "enderecos-1-bairro": "Centro",
                "enderecos-1-cidade": "Rio de Janeiro",
                "enderecos-1-uf": "RJ",
                "enderecos-1-observacoes": "",
            }
        )

        response = self.client.post(reverse("cadastros:cliente_criar"), dados)

        self.assertRedirects(response, reverse("cadastros:cliente_lista"))
        cliente = Cliente.objects.get()
        self.assertEqual(ClienteTelefone.objects.filter(cliente=cliente).count(), 2)
        self.assertEqual(ClienteEndereco.objects.filter(cliente=cliente).count(), 2)
        self.assertEqual(cliente.telefone_principal, "(11) 99999-0000")
        self.assertEqual(cliente.cidade_uf_principal, "São Paulo/SP")

    def test_edicao_de_fornecedor_abre_com_telefones_e_enderecos(self):
        fornecedor = Fornecedor.objects.create(
            razao_social="Essência Brasil Ingredientes LTDA",
            documento="09012654000100",
        )
        FornecedorTelefone.objects.create(
            fornecedor=fornecedor,
            telefone="(11) 4602-7800",
            principal=True,
        )
        FornecedorEndereco.objects.create(
            fornecedor=fornecedor,
            logradouro="Alameda Madeira",
            cidade="Barueri",
            uf="SP",
            principal=True,
        )

        response = self.client.get(reverse("cadastros:fornecedor_editar", args=[fornecedor.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "(11) 4602-7800")
        self.assertContains(response, "Alameda Madeira")
