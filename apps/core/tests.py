from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import ADMINISTRADOR, ALMOXARIFADO, PCP, PRODUCAO

User = get_user_model()


def _usuario(username, perfil=None):
    usuario = User.objects.create_user(username=username, password="senha-forte-123")
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class HealthcheckTests(TestCase):
    def test_healthcheck_nao_exige_login(self):
        response = self.client.get(reverse("core:healthcheck"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class HomePageTests(TestCase):
    def test_anonimo_e_redirecionado_para_login(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_logado_ve_a_home(self):
        User.objects.create_user(username="maria", password="senha-forte-123")
        self.client.login(username="maria", password="senha-forte-123")
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")

    def test_administrador_ve_o_modulo_usuarios(self):
        usuario = User.objects.create_user(username="admin", password="senha-forte-123")
        usuario.groups.add(Group.objects.get(name=ADMINISTRADOR))
        self.client.login(username="admin", password="senha-forte-123")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Usuários")

    def test_producao_ve_so_seus_modulos(self):
        usuario = User.objects.create_user(username="operador", password="senha-forte-123")
        usuario.groups.add(Group.objects.get(name=PRODUCAO))
        self.client.login(username="operador", password="senha-forte-123")
        response = self.client.get(reverse("core:home"))
        # Vê o módulo de Produção, mas não o de Usuários (só Administrador)
        self.assertContains(response, "Produção")
        self.assertNotContains(response, "Usuários")

    def test_usuario_sem_perfil_ve_mensagem_vazia(self):
        User.objects.create_user(username="sem_perfil", password="senha-forte-123")
        self.client.login(username="sem_perfil", password="senha-forte-123")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Nenhum módulo disponível para o seu perfil")


class DashboardIndicadoresTests(TestCase):
    """Fase 10: os indicadores contam o que está no banco."""

    def setUp(self):
        from apps.cadastros.models import Cliente, Produto
        from apps.pedidos.models import ItemPedido, Pedido, StatusPedido

        self.hoje = timezone.localdate()
        self.cliente = Cliente.objects.create(razao_social="Loja Bela")
        self.produto = Produto.objects.create(codigo="PA-1", nome="Perfume")

        # Um pedido em andamento no prazo e outro atrasado
        self.pedido_ok = Pedido.objects.create(
            cliente=self.cliente, status=StatusPedido.EM_ANALISE,
            prazo=self.hoje + timedelta(days=5),
        )
        self.pedido_atrasado = Pedido.objects.create(
            cliente=self.cliente, status=StatusPedido.PROGRAMADO,
            prazo=self.hoje - timedelta(days=2),
        )
        # Um expedido não conta como "em andamento"
        Pedido.objects.create(
            cliente=self.cliente, status=StatusPedido.EXPEDIDO,
            prazo=self.hoje - timedelta(days=10),
        )
        ItemPedido.objects.create(
            pedido=self.pedido_ok, produto=self.produto, quantidade=Decimal("10")
        )

    def test_conta_pedidos_em_andamento_e_atrasados(self):
        from apps.core.dashboard import montar_dashboard

        dados = montar_dashboard(_usuario("ana", PCP))
        indicadores = {i["chave"]: i["valor"] for i in dados["indicadores"]}
        self.assertEqual(indicadores["pedidos_andamento"], 2)
        self.assertEqual(indicadores["pedidos_atrasados"], 1)

    def test_estoque_critico_pega_item_abaixo_do_minimo(self):
        from apps.cadastros.models import MateriaPrima
        from apps.core.dashboard import estoque_critico

        MateriaPrima.objects.create(
            codigo="MP-1", nome="Essência", estoque_minimo=Decimal("50")
        )
        criticos = estoque_critico()
        codigos = {c["item"].codigo for c in criticos}
        self.assertIn("MP-1", codigos)  # sem estoque, abaixo do mínimo

    def test_indicadores_respeitam_o_perfil(self):
        from apps.core.dashboard import montar_dashboard

        # Almoxarifado vê estoque/quarentena, não vê "pedidos em andamento"
        dados = montar_dashboard(_usuario("jose", ALMOXARIFADO))
        chaves = {i["chave"] for i in dados["indicadores"]}
        self.assertIn("estoque_critico", chaves)
        self.assertNotIn("pedidos_andamento", chaves)

    def test_home_renderiza_o_painel(self):
        self.client.force_login(_usuario("pcp", PCP))
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Painel operacional")
        self.assertContains(response, "Pedidos em andamento")


class DashboardAlertasTests(TestCase):
    def test_equipamento_impedido_e_lote_vencido_viram_alerta(self):
        from apps.cadastros.models import Equipamento, Produto
        from apps.core.dashboard import alertas_operacionais
        from apps.estoque.models import Lote, SituacaoLote

        hoje = timezone.localdate()
        Equipamento.objects.create(codigo="EQ-1", nome="Reator")  # sem limpeza
        produto = Produto.objects.create(codigo="PA-9", nome="Creme")
        Lote.objects.create(
            codigo="PA-2026-0001", produto=produto,
            situacao=SituacaoLote.APROVADO, validade=hoje - timedelta(days=1),
        )
        textos = " ".join(a["texto"] for a in alertas_operacionais())
        self.assertIn("equipamento", textos.lower())
        self.assertIn("vencido", textos.lower())

    def test_sem_pendencias_nao_gera_alerta(self):
        from apps.core.dashboard import alertas_operacionais

        self.assertEqual(alertas_operacionais(), [])
