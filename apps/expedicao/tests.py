from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import EXPEDICAO, PCP
from apps.cadastros.models import Produto
from apps.estoque.models import (
    LocalEstoque,
    Lote,
    Movimentacao,
    SituacaoLote,
    TipoMovimentacao,
    saldo,
)
from apps.pedidos.models import (
    ItemPedido,
    Pedido,
    StatusPedido,
    TransicaoInvalida,
)

from .models import Expedicao, registrar_expedicao

User = get_user_model()
SENHA = "senha-forte-123"


def criar_usuario(username, perfil=None):
    usuario = User.objects.create_user(username=username, password=SENHA)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class BaseExpedicao(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("rita", perfil=EXPEDICAO)
        self.client.login(username="rita", password=SENHA)

        self.produto = Produto.objects.create(codigo="PA-1", nome="Perfume")
        self.cliente_pedido = Pedido.objects.create(
            cliente=self._cliente(),
            status=StatusPedido.FINALIZADO,
            prazo=timezone.localdate() + timedelta(days=10),
        )
        self.item = ItemPedido.objects.create(
            pedido=self.cliente_pedido, produto=self.produto,
            quantidade=Decimal("100"),
        )
        self.acabados = LocalEstoque.objects.create(nome="Produtos Acabados")
        self.lote = Lote.objects.create(
            codigo="PA-2026-00001", produto=self.produto,
            situacao=SituacaoLote.APROVADO,
        )
        self._entrada(self.lote, "100")

    def _cliente(self):
        from apps.cadastros.models import Cliente

        return Cliente.objects.create(razao_social="Loja Bela")

    def _entrada(self, lote, quantidade):
        mov = Movimentacao(
            tipo=TipoMovimentacao.ENTRADA, produto=self.produto, lote=lote,
            quantidade=Decimal(quantidade), local_destino=self.acabados,
            motivo="produção",
        )
        mov.full_clean()
        mov.save()


class RegistrarExpedicaoTests(BaseExpedicao):
    def test_expedicao_baixa_estoque_e_marca_lote(self):
        expedicao = registrar_expedicao(
            pedido=self.cliente_pedido,
            data=timezone.localdate(),
            usuario=self.usuario,
            linhas=[(self.item, self.lote, Decimal("100"))],
            nota_fiscal="12345",
        )
        self.assertEqual(expedicao.itens.count(), 1)
        self.assertEqual(saldo(self.produto, local=self.acabados), Decimal("0"))
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.situacao, SituacaoLote.EXPEDIDO)
        item_exp = expedicao.itens.get()
        self.assertEqual(item_exp.movimentacao.tipo, TipoMovimentacao.SAIDA)

    def test_lote_nao_aprovado_bloqueia(self):
        self.lote.situacao = SituacaoLote.AGUARDANDO_CQ
        self.lote.save()
        with self.assertRaises(ValidationError):
            registrar_expedicao(
                pedido=self.cliente_pedido,
                data=timezone.localdate(),
                usuario=self.usuario,
                linhas=[(self.item, self.lote, Decimal("50"))],
            )
        self.assertEqual(Expedicao.objects.count(), 0)

    def test_expedicao_parcial_mantem_saldo(self):
        registrar_expedicao(
            pedido=self.cliente_pedido,
            data=timezone.localdate(),
            usuario=self.usuario,
            linhas=[(self.item, self.lote, Decimal("60"))],
        )
        from .resumo import resumo_item

        resumo = resumo_item(self.item)
        self.assertEqual(resumo["expedida"], Decimal("60"))
        self.assertEqual(resumo["saldo"], Decimal("40"))


class TransicaoExpedidoTests(BaseExpedicao):
    def test_pedido_nao_expede_sem_expedicao(self):
        with self.assertRaises(TransicaoInvalida):
            self.cliente_pedido.transicionar(
                StatusPedido.EXPEDIDO, self.usuario
            )

    def test_pedido_expede_com_expedicao(self):
        registrar_expedicao(
            pedido=self.cliente_pedido,
            data=timezone.localdate(),
            usuario=self.usuario,
            linhas=[(self.item, self.lote, Decimal("100"))],
        )
        self.cliente_pedido.transicionar(StatusPedido.EXPEDIDO, self.usuario)
        self.cliente_pedido.refresh_from_db()
        self.assertEqual(self.cliente_pedido.status, StatusPedido.EXPEDIDO)


class TelaExpedicaoTests(BaseExpedicao):
    def test_criar_expedicao_pela_tela(self):
        response = self.client.post(
            reverse("expedicao:criar", args=[self.cliente_pedido.pk]),
            {
                "data": timezone.localdate().isoformat(),
                "nota_fiscal": "9988",
                "transportadora": "Expresso Sul",
                "conferente": "",
                "observacoes": "",
                f"qtd-{self.item.pk}-{self.lote.pk}": "100",
            },
        )
        expedicao = Expedicao.objects.get()
        self.assertRedirects(response, expedicao.get_absolute_url())
        self.assertEqual(expedicao.nota_fiscal, "9988")

    def test_producao_nao_acessa_expedicao(self):
        criar_usuario("op", perfil=PCP)  # PCP acessa; usa outro sem perfil
        semperfil = User.objects.create_user("nobody", password=SENHA)
        self.client.force_login(semperfil)
        self.assertEqual(
            self.client.get(reverse("expedicao:lista")).status_code, 403
        )
