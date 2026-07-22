from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import PCP, PRODUCAO, QUALIDADE
from apps.auditoria.models import TrilhaImutavelError
from apps.cadastros.models import Cliente, Equipamento, Fornecedor, MateriaPrima, Produto
from apps.estoque.models import (
    LocalEstoque,
    Lote,
    Movimentacao,
    SituacaoLote,
    TipoMovimentacao,
)
from apps.expedicao.models import registrar_expedicao
from apps.ordens.models import ComponenteFormula, Formula, OrdemProducao, StatusOP
from apps.pedidos.models import ItemPedido, Pedido, StatusPedido
from apps.producao.models import ConsumoMaterialOP
from apps.qualidade.models import Analise, StatusAnalise
from apps.recebimento.models import ItemRecebimento, Recebimento

from .models import GeracaoDossie
from .servicos import montar_dossie

User = get_user_model()
SENHA = "senha-forte-123"


def criar_usuario(username, perfil=None):
    usuario = User.objects.create_user(username=username, password=SENHA)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class BaseDossie(TestCase):
    """Monta a cadeia completa: MP recebida → OP → lote acabado → expedido."""

    def setUp(self):
        self.usuario = criar_usuario("paula", perfil=QUALIDADE)
        self.fornecedor = Fornecedor.objects.create(razao_social="Aromas SA")
        self.cliente = Cliente.objects.create(razao_social="Loja Bela")
        self.produto = Produto.objects.create(codigo="PA-1", nome="Perfume")
        self.mp = MateriaPrima.objects.create(codigo="MP-1", nome="Essência")
        self.deposito = LocalEstoque.objects.create(nome="Almoxarifado MP")
        self.acabados = LocalEstoque.objects.create(nome="Produtos Acabados")

        self.lote_mp = Lote.objects.create(
            codigo="MP-2026-00001",
            materia_prima=self.mp,
            lote_fornecedor="ESS-77",
            situacao=SituacaoLote.APROVADO,
        )
        recebimento = Recebimento.objects.create(
            fornecedor=self.fornecedor, nota_fiscal="NF-555"
        )
        ItemRecebimento.objects.create(
            recebimento=recebimento,
            materia_prima=self.mp,
            lote=self.lote_mp,
            quantidade=Decimal("100"),
        )
        self._entrada({"materia_prima": self.mp}, "100", self.deposito, self.lote_mp)

        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            status=StatusPedido.FINALIZADO,
            prazo=timezone.localdate() + timedelta(days=10),
        )
        self.item_pedido = ItemPedido.objects.create(
            pedido=self.pedido, produto=self.produto, quantidade=Decimal("50")
        )
        formula = Formula.objects.create(
            produto=self.produto, nome="Padrão", rendimento=Decimal("100")
        )
        ComponenteFormula.objects.create(
            formula=formula, materia_prima=self.mp, quantidade=Decimal("40")
        )
        equipamento = Equipamento.objects.create(
            codigo="EQ-1", nome="Envasadora", ultima_limpeza=timezone.localdate()
        )
        self.ordem = OrdemProducao.objects.create(
            item_pedido=self.item_pedido,
            formula=formula,
            quantidade=Decimal("50"),
            equipamento=equipamento,
            data_programada=timezone.localdate(),
            status=StatusOP.LIBERADA,
        )
        self.ordem.gerar_materiais()
        ConsumoMaterialOP.objects.create(
            material=self.ordem.materiais.get(),
            lote=self.lote_mp,
            local=self.deposito,
            quantidade=Decimal("20"),
            registrado_por=self.usuario,
        )

        self.lote_pa = Lote.objects.create(
            codigo="PA-2026-00001",
            produto=self.produto,
            situacao=SituacaoLote.APROVADO,
            validade=timezone.localdate() + timedelta(days=540),
        )
        self.ordem.lote_produto = self.lote_pa
        self.ordem.save(update_fields=["lote_produto"])
        self._entrada({"produto": self.produto}, "50", self.acabados, self.lote_pa)

        Analise.objects.create(
            lote=self.lote_pa,
            status=StatusAnalise.APROVADA,
            decidido_por=self.usuario,
            decidido_em=timezone.now(),
            parecer="Lote aprovado.",
        )
        registrar_expedicao(
            pedido=self.pedido,
            data=timezone.localdate(),
            usuario=self.usuario,
            linhas=[(self.item_pedido, self.lote_pa, Decimal("50"))],
            nota_fiscal="NF-9001",
        )

    def _entrada(self, item_kwargs, quantidade, local, lote):
        movimentacao = Movimentacao(
            tipo=TipoMovimentacao.ENTRADA,
            quantidade=Decimal(quantidade),
            local_destino=local,
            lote=lote,
            motivo="carga de teste",
            **item_kwargs,
        )
        movimentacao.full_clean()
        movimentacao.save()


class MontarDossieTests(BaseDossie):
    def test_dossie_reune_os_blocos_do_lote(self):
        dossie = montar_dossie(self.lote_pa)

        identificacao = dossie["identificacao"]
        self.assertEqual(identificacao["produto"], self.produto)
        self.assertEqual(identificacao["cliente"], self.cliente)
        self.assertEqual(identificacao["pedido"], self.pedido)
        self.assertEqual(identificacao["quantidade_prevista"], Decimal("50"))

        self.assertEqual(len(dossie["ordens"]), 1)
        no = dossie["ordens"][0]
        self.assertEqual(no["ordem"], self.ordem)

        material = no["materiais"][0]
        self.assertEqual(material["item"], self.mp)
        self.assertEqual(material["lote"], self.lote_mp)
        self.assertEqual(material["quantidade"], Decimal("20"))
        self.assertEqual(material["origem"]["fornecedor"], self.fornecedor)

        self.assertEqual(len(dossie["analises"]), 1)
        self.assertEqual(len(dossie["expedicoes"]), 1)
        self.assertEqual(dossie["expedicoes"][0].expedicao.nota_fiscal, "NF-9001")
        self.assertEqual(dossie["expedicoes"][0].quantidade, Decimal("50"))

    def test_dossie_exige_lote_de_produto_acabado(self):
        with self.assertRaises(ValueError):
            montar_dossie(self.lote_mp)


class TelaDossieTests(BaseDossie):
    def test_tela_mostra_os_blocos(self):
        self.client.force_login(self.usuario)
        response = self.client.get(reverse("dossie:detalhe", args=[self.lote_pa.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Identificação e situação")
        self.assertContains(response, "Materiais, lotes e documentos")
        self.assertContains(response, "Expedições")
        self.assertContains(response, "Trilha de auditoria do lote")
        self.assertContains(response, "MP-2026-00001")
        self.assertContains(response, "Aromas SA")

    def test_lote_de_materia_prima_nao_tem_dossie(self):
        self.client.force_login(self.usuario)
        response = self.client.get(reverse("dossie:detalhe", args=[self.lote_mp.pk]))
        self.assertEqual(response.status_code, 404)

    def test_perfil_sem_modulo_relacionado_recebe_403(self):
        sem_perfil = User.objects.create_user("ninguem", password=SENHA)
        self.client.force_login(sem_perfil)
        response = self.client.get(reverse("dossie:detalhe", args=[self.lote_pa.pk]))
        self.assertEqual(response.status_code, 403)


class GerarPDFTests(BaseDossie):
    def test_pdf_e_gerado_e_a_geracao_fica_registrada(self):
        """Critério de aceite: PDF com os blocos e quem/quando gerou."""
        self.client.force_login(self.usuario)
        response = self.client.post(reverse("dossie:pdf", args=[self.lote_pa.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))

        geracao = GeracaoDossie.objects.get()
        self.assertEqual(geracao.lote, self.lote_pa)
        self.assertEqual(geracao.versao, 1)
        self.assertEqual(geracao.gerado_por, self.usuario)
        self.assertEqual(len(geracao.hash_arquivo), 64)
        self.assertTrue(geracao.arquivo.name.endswith(".pdf"))
        self.assertEqual(geracao.codigo, f"DOS-{self.lote_pa.pk:05d}-01")

    def test_cada_geracao_e_uma_versao_nova(self):
        self.client.force_login(self.usuario)
        self.client.post(reverse("dossie:pdf", args=[self.lote_pa.pk]))
        self.client.post(reverse("dossie:pdf", args=[self.lote_pa.pk]))

        versoes = list(
            GeracaoDossie.objects.filter(lote=self.lote_pa)
            .order_by("versao")
            .values_list("versao", flat=True)
        )
        self.assertEqual(versoes, [1, 2])

    def test_geracao_e_imutavel(self):
        self.client.force_login(self.usuario)
        self.client.post(reverse("dossie:pdf", args=[self.lote_pa.pk]))
        geracao = GeracaoDossie.objects.get()

        geracao.versao = 99
        with self.assertRaises(TrilhaImutavelError):
            geracao.save()
        with self.assertRaises(TrilhaImutavelError):
            geracao.delete()
        with self.assertRaises(TrilhaImutavelError):
            GeracaoDossie.objects.all().delete()

    def test_producao_tambem_gera_o_dossie(self):
        operador = criar_usuario("marcos", perfil=PRODUCAO)
        self.client.force_login(operador)
        response = self.client.post(reverse("dossie:pdf", args=[self.lote_pa.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GeracaoDossie.objects.get().gerado_por, operador)

    def test_pcp_abre_o_dossie_pelo_pedido(self):
        """Critério de aceite: do pedido expedido chegar ao dossiê do lote."""
        pcp = criar_usuario("ana", perfil=PCP)
        self.client.force_login(pcp)
        detalhe = self.client.get(reverse("pedidos:detalhe", args=[self.pedido.pk]))
        self.assertContains(
            detalhe, reverse("dossie:detalhe", args=[self.lote_pa.pk])
        )
