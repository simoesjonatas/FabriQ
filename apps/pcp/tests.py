from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import PCP, PRODUCAO
from apps.cadastros.models import Cliente, Equipamento, Produto
from apps.pedidos.models import ItemPedido, Pedido, StatusPedido

from .models import Programacao, itens_pendentes_de_programacao, saldo_a_programar

User = get_user_model()


def criar_usuario(username, perfil=None, senha="senha-forte-123"):
    usuario = User.objects.create_user(username=username, password=senha)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class BaseComDados(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("pcp", perfil=PCP)
        self.client.login(username="pcp", password="senha-forte-123")

        self.cliente = Cliente.objects.create(razao_social="Loja Bela Pele LTDA")
        self.produto = Produto.objects.create(codigo="PA-1", nome="Perfume Lavanda")
        self.equipamento = Equipamento.objects.create(
            codigo="EQ-01", nome="Envasadora 1", capacidade=Decimal("100")
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            status=StatusPedido.EM_ANALISE,
            prazo=timezone.localdate() + timedelta(days=15),
        )
        self.item = ItemPedido.objects.create(
            pedido=self.pedido, produto=self.produto, quantidade=Decimal("100")
        )
        self.amanha = timezone.localdate() + timedelta(days=1)

    def dados_programacao(self, **kwargs):
        dados = {
            "item": self.item.pk,
            "equipamento": self.equipamento.pk,
            "operador": "",
            "data": self.amanha.isoformat(),
            "quantidade": "60",
            "observacoes": "",
        }
        dados.update(kwargs)
        return dados


class ProgramarTests(BaseComDados):
    def test_programar_item_avanca_pedido_e_registra_historico(self):
        response = self.client.post(
            reverse("pcp:criar"), self.dados_programacao()
        )
        programacao = Programacao.objects.get()
        self.assertRedirects(
            response,
            f"{reverse('pcp:calendario')}?mes={self.amanha:%Y-%m}",
        )
        self.assertEqual(programacao.criado_por, self.usuario)

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, StatusPedido.PROGRAMADO)

        descricoes = list(
            self.pedido.historico.values_list("descricao", flat=True)
        )
        self.assertTrue(any("programado" in d for d in descricoes))
        self.assertTrue(any("Status alterado" in d for d in descricoes))

    def test_pedido_ja_programado_nao_transiciona_de_novo(self):
        self.pedido.status = StatusPedido.PROGRAMADO
        self.pedido.save()
        self.client.post(reverse("pcp:criar"), self.dados_programacao())
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, StatusPedido.PROGRAMADO)

    def test_quantidade_acima_do_saldo_e_rejeitada(self):
        Programacao.objects.create(
            item=self.item,
            equipamento=self.equipamento,
            data=self.amanha,
            quantidade=Decimal("80"),
        )
        response = self.client.post(
            reverse("pcp:criar"), self.dados_programacao(quantidade="30")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "acima do saldo a programar")
        self.assertEqual(Programacao.objects.count(), 1)

    def test_pedido_recebido_nao_pode_ser_programado(self):
        self.pedido.status = StatusPedido.RECEBIDO
        self.pedido.save()
        response = self.client.post(
            reverse("pcp:criar"), self.dados_programacao()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Programacao.objects.count(), 0)

    def test_saldo_a_programar_ignora_inativas(self):
        Programacao.objects.create(
            item=self.item,
            equipamento=self.equipamento,
            data=self.amanha,
            quantidade=Decimal("80"),
            ativo=False,
        )
        self.assertEqual(saldo_a_programar(self.item), Decimal("100"))


class ReprogramarTests(BaseComDados):
    def setUp(self):
        super().setUp()
        self.programacao = Programacao.objects.create(
            item=self.item,
            equipamento=self.equipamento,
            data=self.amanha,
            quantidade=Decimal("60"),
        )

    def test_reprogramar_registra_historico(self):
        nova_data = self.amanha + timedelta(days=3)
        response = self.client.post(
            reverse("pcp:editar", args=[self.programacao.pk]),
            self.dados_programacao(data=nova_data.isoformat()),
        )
        self.assertEqual(response.status_code, 302)
        self.programacao.refresh_from_db()
        self.assertEqual(self.programacao.data, nova_data)

        evento = self.pedido.historico.first()
        self.assertIn("reprogramado", evento.descricao)
        self.assertIn(f"{nova_data:%d/%m/%Y}", evento.descricao)

    def test_remover_exige_motivo_e_inativa(self):
        url = reverse("pcp:remover", args=[self.programacao.pk])

        self.client.post(url, {"motivo": ""})
        self.programacao.refresh_from_db()
        self.assertTrue(self.programacao.ativo)

        self.client.post(url, {"motivo": "Equipamento em manutenção"})
        self.programacao.refresh_from_db()
        self.assertFalse(self.programacao.ativo)
        self.assertEqual(self.programacao.motivo_remocao, "Equipamento em manutenção")
        self.assertIn("removida", self.pedido.historico.first().descricao)
        # O registro continua existindo
        self.assertTrue(Programacao.objects.filter(pk=self.programacao.pk).exists())

    def test_apos_remocao_item_volta_para_pendentes(self):
        self.client.post(
            reverse("pcp:remover", args=[self.programacao.pk]),
            {"motivo": "Reprogramação geral"},
        )
        pendentes = itens_pendentes_de_programacao()
        self.assertIn(self.item, pendentes)


class CalendarioTests(BaseComDados):
    def setUp(self):
        super().setUp()
        self.programacao = Programacao.objects.create(
            item=self.item,
            equipamento=self.equipamento,
            data=self.amanha,
            quantidade=Decimal("60"),
        )

    def test_calendario_mostra_programacao_do_mes(self):
        response = self.client.get(
            reverse("pcp:calendario"), {"mes": f"{self.amanha:%Y-%m}"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PA-1")
        self.assertContains(response, "EQ-01")

    def test_filtro_por_equipamento_esconde_outros(self):
        outro = Equipamento.objects.create(codigo="EQ-02", nome="Misturador")
        response = self.client.get(
            reverse("pcp:calendario"),
            {"mes": f"{self.amanha:%Y-%m}", "equipamento": outro.pk},
        )
        self.assertNotContains(response, "PA-1 ×")

    def test_sobrecarga_marcada_quando_passa_capacidade(self):
        outro_pedido = Pedido.objects.create(
            cliente=self.cliente,
            status=StatusPedido.PROGRAMADO,
            prazo=timezone.localdate() + timedelta(days=20),
        )
        outro_item = ItemPedido.objects.create(
            pedido=outro_pedido, produto=self.produto, quantidade=Decimal("90")
        )
        # 60 + 90 = 150 > capacidade 100 do EQ-01 no mesmo dia
        Programacao.objects.create(
            item=outro_item,
            equipamento=self.equipamento,
            data=self.amanha,
            quantidade=Decimal("90"),
        )
        response = self.client.get(
            reverse("pcp:calendario"), {"mes": f"{self.amanha:%Y-%m}"}
        )
        self.assertContains(response, "pcp-chip-sobrecarga")
        self.assertContains(response, "ACIMA DA CAPACIDADE")

    def test_mes_invalido_cai_no_mes_atual(self):
        response = self.client.get(reverse("pcp:calendario"), {"mes": "banana"})
        self.assertEqual(response.status_code, 200)


class ListaEPendentesTests(BaseComDados):
    def test_lista_filtra_por_periodo(self):
        Programacao.objects.create(
            item=self.item,
            equipamento=self.equipamento,
            data=self.amanha,
            quantidade=Decimal("30"),
        )
        depois = self.amanha + timedelta(days=10)
        response = self.client.get(
            reverse("pcp:lista"),
            {"de": depois.isoformat(), "ate": (depois + timedelta(days=1)).isoformat()},
        )
        self.assertContains(response, "Nenhuma programação encontrada.")

    def test_pendentes_mostra_saldo(self):
        Programacao.objects.create(
            item=self.item,
            equipamento=self.equipamento,
            data=self.amanha,
            quantidade=Decimal("60"),
        )
        response = self.client.get(reverse("pcp:pendentes"))
        self.assertContains(response, self.pedido.numero)
        self.assertContains(response, "40")  # saldo restante

    def test_item_totalmente_programado_sai_dos_pendentes(self):
        Programacao.objects.create(
            item=self.item,
            equipamento=self.equipamento,
            data=self.amanha,
            quantidade=Decimal("100"),
        )
        self.assertEqual(itens_pendentes_de_programacao(), [])


class PermissoesTests(TestCase):
    def setUp(self):
        criar_usuario("pcp", perfil=PCP)
        criar_usuario("operador", perfil=PRODUCAO)

    def test_producao_nao_acessa_pcp(self):
        self.client.login(username="operador", password="senha-forte-123")
        for rota in ["pcp:calendario", "pcp:lista", "pcp:pendentes", "pcp:criar"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 403)

    def test_pcp_acessa_todas_as_visoes(self):
        self.client.login(username="pcp", password="senha-forte-123")
        for rota in ["pcp:calendario", "pcp:lista", "pcp:pendentes", "pcp:criar"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 200)
