from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import PCP, PRODUCAO
from apps.cadastros.models import Cliente, Produto

from .models import (
    HistoricoPedido,
    ItemPedido,
    Pedido,
    StatusPedido,
    TransicaoInvalida,
)

User = get_user_model()


def criar_usuario(username, perfil=None, senha="senha-forte-123"):
    usuario = User.objects.create_user(username=username, password=senha)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


def criar_pedido(cliente=None, status=StatusPedido.RECEBIDO, prazo=None, com_item=True):
    cliente = cliente or Cliente.objects.create(razao_social="Loja Bela Pele LTDA")
    pedido = Pedido.objects.create(
        cliente=cliente,
        status=status,
        prazo=prazo or timezone.localdate() + timedelta(days=15),
    )
    if com_item:
        produto = Produto.objects.create(
            codigo=f"P{pedido.pk:03d}", nome=f"Produto {pedido.pk}"
        )
        ItemPedido.objects.create(pedido=pedido, produto=produto, quantidade=10)
    return pedido


class PedidoModelTests(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("pcp", perfil=PCP)

    def test_numero_formatado(self):
        pedido = criar_pedido()
        self.assertEqual(pedido.numero, f"PED-{pedido.pk:05d}")

    def test_transicao_valida_avanca_e_registra_historico(self):
        pedido = criar_pedido()
        pedido.transicionar(StatusPedido.EM_ANALISE, self.usuario)

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, StatusPedido.EM_ANALISE)

        evento = pedido.historico.first()
        self.assertIn("Recebido", evento.descricao)
        self.assertIn("Em análise", evento.descricao)
        self.assertEqual(evento.usuario, self.usuario)
        self.assertEqual(evento.status_anterior, StatusPedido.RECEBIDO)
        self.assertEqual(evento.status_novo, StatusPedido.EM_ANALISE)

    def test_transicao_invalida_e_bloqueada(self):
        pedido = criar_pedido()  # Recebido
        with self.assertRaises(TransicaoInvalida):
            pedido.transicionar(StatusPedido.EXPEDIDO, self.usuario)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, StatusPedido.RECEBIDO)

    def test_em_analise_pode_pular_aguardando_mp(self):
        pedido = criar_pedido(status=StatusPedido.EM_ANALISE)
        pedido.transicionar(StatusPedido.PROGRAMADO, self.usuario)
        self.assertEqual(pedido.status, StatusPedido.PROGRAMADO)

    def test_cancelamento_exige_motivo(self):
        pedido = criar_pedido()
        with self.assertRaises(TransicaoInvalida):
            pedido.transicionar(StatusPedido.CANCELADO, self.usuario, motivo="  ")

        pedido.transicionar(
            StatusPedido.CANCELADO, self.usuario, motivo="Cliente desistiu"
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, StatusPedido.CANCELADO)
        self.assertEqual(pedido.motivo_cancelamento, "Cliente desistiu")
        self.assertIn("Cliente desistiu", pedido.historico.first().descricao)

    def test_pedido_expedido_nao_transiciona(self):
        pedido = criar_pedido(status=StatusPedido.EXPEDIDO)
        self.assertEqual(pedido.proximos_status, [])
        self.assertFalse(pedido.pode_cancelar)

    def test_atrasado_considera_status(self):
        ontem = timezone.localdate() - timedelta(days=1)
        atrasado = criar_pedido(prazo=ontem)
        self.assertTrue(atrasado.atrasado)

        expedido = criar_pedido(status=StatusPedido.EXPEDIDO, prazo=ontem)
        self.assertFalse(expedido.atrasado)

    def test_editavel_por_status(self):
        self.assertTrue(criar_pedido(status=StatusPedido.RECEBIDO).editavel)
        self.assertTrue(criar_pedido(status=StatusPedido.AGUARDANDO_MP).editavel)
        self.assertFalse(criar_pedido(status=StatusPedido.PROGRAMADO).editavel)
        self.assertFalse(criar_pedido(status=StatusPedido.CANCELADO).editavel)


class PermissoesTests(TestCase):
    def setUp(self):
        criar_usuario("pcp", perfil=PCP)
        criar_usuario("operador", perfil=PRODUCAO)
        self.pedido = criar_pedido()

    def test_anonimo_redireciona_para_login(self):
        response = self.client.get(reverse("pedidos:lista"))
        self.assertEqual(response.status_code, 302)

    def test_producao_nao_acessa_pedidos(self):
        self.client.login(username="operador", password="senha-forte-123")
        for rota in ["pedidos:lista", "pedidos:criar"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 403)
        response = self.client.get(reverse("pedidos:detalhe", args=[self.pedido.pk]))
        self.assertEqual(response.status_code, 403)

    def test_pcp_acessa_pedidos(self):
        self.client.login(username="pcp", password="senha-forte-123")
        for url in [
            reverse("pedidos:lista"),
            reverse("pedidos:criar"),
            reverse("pedidos:detalhe", args=[self.pedido.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class PedidoCriarViewTests(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("pcp", perfil=PCP)
        self.client.login(username="pcp", password="senha-forte-123")
        self.cliente = Cliente.objects.create(razao_social="Loja Bela Pele LTDA")
        self.produto = Produto.objects.create(codigo="PA-1", nome="Perfume Lavanda")
        self.produto2 = Produto.objects.create(codigo="PA-2", nome="Sabonete Erva-doce")

    def dados(self, itens, **kwargs):
        prazo = timezone.localdate() + timedelta(days=10)
        dados = {
            "cliente": self.cliente.pk,
            "prazo": prazo.isoformat(),
            "observacoes": "",
            "itens-TOTAL_FORMS": str(len(itens)),
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
        }
        for indice, (produto, quantidade) in enumerate(itens):
            dados[f"itens-{indice}-produto"] = str(produto.pk) if produto else ""
            dados[f"itens-{indice}-quantidade"] = str(quantidade) if quantidade else ""
        dados.update(kwargs)
        return dados

    def test_criar_pedido_com_itens_registra_historico_e_auditoria(self):
        response = self.client.post(
            reverse("pedidos:criar"),
            self.dados([(self.produto, 10), (self.produto2, 5)]),
        )
        pedido = Pedido.objects.get()
        self.assertRedirects(response, reverse("pedidos:detalhe", args=[pedido.pk]))
        self.assertEqual(pedido.itens.count(), 2)
        self.assertEqual(pedido.status, StatusPedido.RECEBIDO)
        self.assertEqual(pedido.criado_por, self.usuario)
        self.assertEqual(pedido.historico.first().descricao, "Pedido criado")

    def test_pedido_sem_itens_e_rejeitado(self):
        response = self.client.post(reverse("pedidos:criar"), self.dados([(None, None)]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "O pedido deve ter pelo menos um produto.")
        self.assertEqual(Pedido.objects.count(), 0)

    def test_produto_repetido_e_rejeitado(self):
        response = self.client.post(
            reverse("pedidos:criar"),
            self.dados([(self.produto, 10), (self.produto, 5)]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este produto já está no pedido.")
        self.assertEqual(Pedido.objects.count(), 0)


class PedidoEditarViewTests(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("pcp", perfil=PCP)
        self.client.login(username="pcp", password="senha-forte-123")
        self.pedido = criar_pedido()

    def test_editar_registra_historico_com_campos_alterados(self):
        item = self.pedido.itens.first()
        novo_prazo = timezone.localdate() + timedelta(days=30)
        response = self.client.post(
            reverse("pedidos:editar", args=[self.pedido.pk]),
            {
                "cliente": self.pedido.cliente.pk,
                "prazo": novo_prazo.isoformat(),
                "observacoes": "Urgente",
                "itens-TOTAL_FORMS": "1",
                "itens-INITIAL_FORMS": "1",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-id": str(item.pk),
                "itens-0-pedido": str(self.pedido.pk),
                "itens-0-produto": str(item.produto.pk),
                "itens-0-quantidade": "10",
            },
        )
        self.assertRedirects(
            response, reverse("pedidos:detalhe", args=[self.pedido.pk])
        )
        evento = self.pedido.historico.first()
        self.assertIn("Pedido alterado", evento.descricao)
        self.assertIn("prazo de entrega", evento.descricao)
        self.assertIn("observações", evento.descricao)

    def test_pedido_programado_nao_pode_ser_editado(self):
        self.pedido.status = StatusPedido.PROGRAMADO
        self.pedido.save()
        response = self.client.get(reverse("pedidos:editar", args=[self.pedido.pk]))
        self.assertRedirects(
            response, reverse("pedidos:detalhe", args=[self.pedido.pk])
        )


class TransicaoViewTests(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("pcp", perfil=PCP)
        self.client.login(username="pcp", password="senha-forte-123")
        self.pedido = criar_pedido()

    def transicionar(self, novo_status, motivo=""):
        return self.client.post(
            reverse("pedidos:transicao", args=[self.pedido.pk]),
            {"novo_status": novo_status, "motivo": motivo},
        )

    def test_avancar_status_pela_view(self):
        response = self.transicionar(StatusPedido.EM_ANALISE)
        self.assertRedirects(
            response, reverse("pedidos:detalhe", args=[self.pedido.pk])
        )
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, StatusPedido.EM_ANALISE)

    def test_transicao_invalida_mostra_erro_sem_mudar_status(self):
        response = self.transicionar(StatusPedido.EXPEDIDO)
        self.assertRedirects(
            response, reverse("pedidos:detalhe", args=[self.pedido.pk])
        )
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, StatusPedido.RECEBIDO)

    def test_cancelar_pela_view_exige_motivo(self):
        self.transicionar(StatusPedido.CANCELADO, motivo="")
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, StatusPedido.RECEBIDO)

        self.transicionar(StatusPedido.CANCELADO, motivo="Cliente desistiu")
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, StatusPedido.CANCELADO)


class ListaTests(TestCase):
    def setUp(self):
        criar_usuario("pcp", perfil=PCP)
        self.client.login(username="pcp", password="senha-forte-123")

    def test_filtro_por_status(self):
        criar_pedido(status=StatusPedido.RECEBIDO)
        programado = criar_pedido(status=StatusPedido.PROGRAMADO)
        response = self.client.get(
            reverse("pedidos:lista"), {"status": StatusPedido.PROGRAMADO}
        )
        self.assertContains(response, programado.numero)
        self.assertEqual(len(response.context["pedidos"]), 1)

    def test_pesquisa_por_cliente_e_numero(self):
        cliente_a = Cliente.objects.create(razao_social="Aromas do Vale LTDA")
        pedido_a = criar_pedido(cliente=cliente_a)
        pedido_b = criar_pedido()

        response = self.client.get(reverse("pedidos:lista"), {"q": "aromas"})
        self.assertContains(response, pedido_a.numero)
        self.assertNotContains(response, pedido_b.numero)

        response = self.client.get(reverse("pedidos:lista"), {"q": pedido_b.numero})
        self.assertContains(response, pedido_b.numero)

    def test_atrasado_destacado_na_lista(self):
        criar_pedido(prazo=timezone.localdate() - timedelta(days=2))
        response = self.client.get(reverse("pedidos:lista"))
        self.assertContains(response, "Pedido atrasado")


class HistoricoTests(TestCase):
    def test_registrar_helper(self):
        pedido = criar_pedido(com_item=False)
        HistoricoPedido.registrar(
            pedido=pedido, usuario=None, descricao="Teste manual"
        )
        self.assertEqual(pedido.historico.count(), 1)
        self.assertEqual(str(pedido.historico.first()).split(" · ")[0], pedido.numero)
