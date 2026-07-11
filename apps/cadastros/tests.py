from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.perfis import PCP, PRODUCAO

from .models import Cliente, Equipamento, Produto, Setor

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
            "documento": "12.345.678/0001-90",
            "email": "",
            "telefone": "",
            "endereco": "",
            "cidade": "",
            "uf": "",
            "cep": "",
            "observacoes": "",
            "ativo": "on",
        }
        dados.update(kwargs)
        return dados

    def test_documento_normalizado_para_somente_numeros(self):
        self.client.post(reverse("cadastros:cliente_criar"), self.dados_cliente())
        cliente = Cliente.objects.get()
        self.assertEqual(cliente.documento, "12345678000190")

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
