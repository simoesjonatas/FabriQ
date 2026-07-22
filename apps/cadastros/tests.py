from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import COMPRAS, EXPEDICAO, PCP, PRODUCAO

from .models import (
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


class DocumentoClienteTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(razao_social="Loja Bela")

    def test_documento_vencido(self):
        doc = DocumentoCliente.objects.create(
            cliente=self.cliente,
            validade=timezone.localdate() - timedelta(days=1),
        )
        self.assertTrue(doc.vencido)
        self.assertFalse(doc.vence_em_breve)
        self.assertIn(doc, self.cliente.documentos_vencidos)

    def test_documento_vence_em_breve(self):
        doc = DocumentoCliente.objects.create(
            cliente=self.cliente,
            validade=timezone.localdate() + timedelta(days=10),
        )
        self.assertFalse(doc.vencido)
        self.assertTrue(doc.vence_em_breve)
        self.assertIn(doc, self.cliente.documentos_a_vencer)

    def test_documento_sem_validade_nao_alerta(self):
        doc = DocumentoCliente.objects.create(cliente=self.cliente)
        self.assertFalse(doc.vencido)
        self.assertFalse(doc.vence_em_breve)


class FichaClienteTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            razao_social="Primavera Farma", nome_fantasia="Primavera"
        )
        self.compras = criar_usuario("carla", perfil=COMPRAS)  # cadastros + pedidos
        self.expedicao = criar_usuario("rui", perfil=EXPEDICAO)  # pedidos, sem cadastros
        self.producao = criar_usuario("pedro", perfil=PRODUCAO)  # nenhum dos três

    def test_ficha_abre_para_perfil_de_cadastros_com_edicao(self):
        self.client.force_login(self.compras)
        response = self.client.get(
            reverse("cadastros:cliente_detalhe", args=[self.cliente.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Primavera Farma")
        self.assertTrue(response.context["pode_editar"])

    def test_ficha_abre_para_perfil_de_pedidos_sem_edicao(self):
        self.client.force_login(self.expedicao)
        response = self.client.get(
            reverse("cadastros:cliente_detalhe", args=[self.cliente.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["pode_editar"])

    def test_ficha_negada_sem_modulo_relacionado(self):
        self.client.force_login(self.producao)
        response = self.client.get(
            reverse("cadastros:cliente_detalhe", args=[self.cliente.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_adicionar_e_remover_documento(self):
        self.client.force_login(self.compras)
        response = self.client.post(
            reverse("cadastros:cliente_documento_criar", args=[self.cliente.pk]),
            {
                "tipo": "AFE",
                "numero": "123",
                "orgao_emissor": "ANVISA",
                "emissao": "",
                "validade": (timezone.localdate() + timedelta(days=365)).isoformat(),
                "observacoes": "",
            },
        )
        self.assertRedirects(
            response, reverse("cadastros:cliente_detalhe", args=[self.cliente.pk])
        )
        documento = self.cliente.documentos.get()
        self.assertEqual(documento.numero, "123")

        self.client.post(
            reverse("cadastros:cliente_documento_remover", args=[documento.pk])
        )
        documento.refresh_from_db()
        self.assertFalse(documento.ativo)


class ClienteBloqueadoTests(TestCase):
    def _dados_pedido(self, cliente):
        return {
            "cliente": cliente.pk,
            "prazo": (timezone.localdate() + timedelta(days=10)).isoformat(),
            "observacoes": "",
            "justificativa_auditoria": "",
        }

    def test_pedido_form_rejeita_cliente_bloqueado(self):
        from apps.pedidos.forms import PedidoForm

        cliente = Cliente.objects.create(
            razao_social="Bloqueada", bloqueado=True, motivo_bloqueio="Inadimplência"
        )
        form = PedidoForm(data=self._dados_pedido(cliente))
        self.assertFalse(form.is_valid())
        self.assertIn("cliente", form.errors)

    def test_pedido_form_aceita_cliente_liberado(self):
        from apps.pedidos.forms import PedidoForm

        cliente = Cliente.objects.create(razao_social="Liberada")
        form = PedidoForm(data=self._dados_pedido(cliente))
        self.assertTrue(form.is_valid(), form.errors)


class ProdutoRegulatorioTests(TestCase):
    def test_produto_regularizado_pode_gerar_op(self):
        produto = Produto.objects.create(codigo="P1", nome="Creme")
        self.assertTrue(produto.pode_gerar_op())
        self.assertEqual(produto.motivo_impedimento_op(), "")

    def test_produto_bloqueado_nao_gera_op(self):
        produto = Produto.objects.create(
            codigo="P2", nome="Creme", bloqueado=True, motivo_bloqueio="Recolhimento"
        )
        self.assertFalse(produto.pode_gerar_op())
        self.assertIn("bloqueado", produto.motivo_impedimento_op())

    def test_produto_sem_regularizacao_nao_gera_op(self):
        produto = Produto.objects.create(
            codigo="P3", nome="Creme", situacao_regulatoria="EM_ANALISE"
        )
        self.assertFalse(produto.pode_gerar_op())
        self.assertIn("regularização", produto.motivo_impedimento_op())


class FichaProdutoTests(TestCase):
    def setUp(self):
        self.produto = Produto.objects.create(codigo="PA-9", nome="Sabonete")
        self.compras = criar_usuario("cris", perfil=COMPRAS)  # cadastros
        self.producao = criar_usuario("paulo", perfil=PRODUCAO)  # producao

    def test_ficha_abre_para_cadastros(self):
        self.client.force_login(self.compras)
        response = self.client.get(
            reverse("cadastros:produto_detalhe", args=[self.produto.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sabonete")
        self.assertTrue(response.context["pode_editar"])

    def test_ficha_abre_para_producao_sem_editar(self):
        self.client.force_login(self.producao)
        response = self.client.get(
            reverse("cadastros:produto_detalhe", args=[self.produto.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["pode_editar"])


class LinksDeFichaTests(TestCase):
    """Etapa 10: get_absolute_url alimenta os links cruzados das telas."""

    def test_cada_ficha_tem_url_propria(self):
        cliente = Cliente.objects.create(razao_social="Loja")
        produto = Produto.objects.create(codigo="P-1", nome="Creme")
        mp = MateriaPrima.objects.create(codigo="M-1", nome="Óleo")
        embalagem = Embalagem.objects.create(codigo="E-1", nome="Frasco")

        self.assertEqual(
            cliente.get_absolute_url(),
            reverse("cadastros:cliente_detalhe", args=[cliente.pk]),
        )
        self.assertEqual(
            produto.get_absolute_url(),
            reverse("cadastros:produto_detalhe", args=[produto.pk]),
        )
        self.assertEqual(
            mp.get_absolute_url(),
            reverse("cadastros:materiaprima_detalhe", args=[mp.pk]),
        )
        self.assertEqual(
            embalagem.get_absolute_url(),
            reverse("cadastros:embalagem_detalhe", args=[embalagem.pk]),
        )


class FornecedorAprovadoTests(TestCase):
    def setUp(self):
        self.mp = MateriaPrima.objects.create(codigo="MP-1", nome="Essência")
        self.fornecedor = Fornecedor.objects.create(razao_social="Aromas SA")
        self.outro = Fornecedor.objects.create(razao_social="Outro Forn")

    def test_sem_lista_nao_restringe(self):
        self.assertTrue(self.mp.fornecedor_aprovado(self.outro))
        self.assertTrue(self.mp.fornecedor_aprovado(None))

    def test_com_lista_aceita_aprovado(self):
        self.mp.fornecedores_aprovados.add(self.fornecedor)
        self.assertTrue(self.mp.fornecedor_aprovado(self.fornecedor))

    def test_com_lista_recusa_nao_aprovado(self):
        self.mp.fornecedores_aprovados.add(self.fornecedor)
        self.assertFalse(self.mp.fornecedor_aprovado(self.outro))

    def test_com_lista_recusa_lote_sem_fornecedor(self):
        self.mp.fornecedores_aprovados.add(self.fornecedor)
        self.assertFalse(self.mp.fornecedor_aprovado(None))


class EmbalagemArteTests(TestCase):
    """Etapa 10: rótulo com arte obsoleta não pode ir para a OP."""

    def setUp(self):
        self.produto = Produto.objects.create(codigo="PA-1", nome="Sabonete")
        self.arte = VersaoArte.objects.create(
            produto=self.produto, versao="v1", status="APROVADA"
        )

    def test_rotulo_com_arte_aprovada_esta_apto(self):
        rotulo = Embalagem.objects.create(
            codigo="EMB-R1", nome="Rótulo sabonete", tipo="ROTULO",
            versao_arte=self.arte,
        )
        self.assertEqual(rotulo.motivo_arte_invalida(), "")

    def test_rotulo_com_arte_obsoleta_bloqueia(self):
        self.arte.status = "OBSOLETA"
        self.arte.save()
        rotulo = Embalagem.objects.create(
            codigo="EMB-R2", nome="Rótulo antigo", tipo="ROTULO",
            versao_arte=self.arte,
        )
        self.assertIn("obsoleta", rotulo.motivo_arte_invalida())

    def test_embalagem_que_nao_e_rotulo_nao_e_afetada(self):
        self.arte.status = "OBSOLETA"
        self.arte.save()
        frasco = Embalagem.objects.create(
            codigo="EMB-F1", nome="Frasco 100ml", tipo="FRASCO",
            versao_arte=self.arte,
        )
        self.assertEqual(frasco.motivo_arte_invalida(), "")

    def test_rotulo_sem_arte_vinculada_nao_bloqueia(self):
        rotulo = Embalagem.objects.create(
            codigo="EMB-R3", nome="Rótulo genérico", tipo="ROTULO"
        )
        self.assertEqual(rotulo.motivo_arte_invalida(), "")


class FichaEmbalagemTests(TestCase):
    def setUp(self):
        self.embalagem = Embalagem.objects.create(
            codigo="EMB-1", nome="Frasco âmbar", tipo="FRASCO",
            material="vidro", cor="âmbar",
        )
        self.compras = criar_usuario("bea", perfil=COMPRAS)

    def test_ficha_embalagem_abre(self):
        self.client.force_login(self.compras)
        response = self.client.get(
            reverse("cadastros:embalagem_detalhe", args=[self.embalagem.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Frasco âmbar")
        self.assertContains(response, "vidro")


class FichaMateriaPrimaTests(TestCase):
    def setUp(self):
        self.mp = MateriaPrima.objects.create(
            codigo="MP-9", nome="Óleo de argan", inci="Argania Spinosa"
        )
        self.compras = criar_usuario("ana2", perfil=COMPRAS)

    def test_ficha_mp_abre_e_mostra_dados_tecnicos(self):
        self.client.force_login(self.compras)
        response = self.client.get(
            reverse("cadastros:materiaprima_detalhe", args=[self.mp.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Óleo de argan")
        self.assertContains(response, "Argania Spinosa")
