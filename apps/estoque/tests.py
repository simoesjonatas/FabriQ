from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import ALMOXARIFADO, PRODUCAO
from apps.cadastros.models import MateriaPrima, Produto

from .models import (
    LocalEstoque,
    Lote,
    Movimentacao,
    SequenciaLote,
    SituacaoValidade,
    TipoMovimentacao,
    criar_lote_interno,
    gerar_lote_interno,
    saldo,
)

User = get_user_model()


def criar_usuario(username, perfil=None, senha="senha-forte-123"):
    usuario = User.objects.create_user(username=username, password=senha)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


def movimentar(tipo, item_kwargs, quantidade, origem=None, destino=None, lote=None):
    movimentacao = Movimentacao(
        tipo=tipo,
        quantidade=Decimal(quantidade),
        local_origem=origem,
        local_destino=destino,
        lote=lote,
        motivo="teste",
        **item_kwargs,
    )
    movimentacao.full_clean()
    movimentacao.save()
    return movimentacao


class BaseEstoque(TestCase):
    def setUp(self):
        self.mp = MateriaPrima.objects.create(codigo="MP-1", nome="Essência de lavanda")
        self.produto = Produto.objects.create(codigo="PA-1", nome="Perfume Lavanda")
        self.almoxarifado = LocalEstoque.objects.create(nome="Almoxarifado")
        self.producao = LocalEstoque.objects.create(nome="Produção")


class SaldoTests(BaseEstoque):
    def test_entrada_soma_no_destino(self):
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"materia_prima": self.mp},
            "100",
            destino=self.almoxarifado,
        )
        self.assertEqual(saldo(self.mp), Decimal("100"))
        self.assertEqual(saldo(self.mp, local=self.almoxarifado), Decimal("100"))
        self.assertEqual(saldo(self.mp, local=self.producao), Decimal("0"))

    def test_saida_subtrai_da_origem(self):
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"materia_prima": self.mp},
            "100",
            destino=self.almoxarifado,
        )
        movimentar(
            TipoMovimentacao.SAIDA,
            {"materia_prima": self.mp},
            "30",
            origem=self.almoxarifado,
        )
        self.assertEqual(saldo(self.mp), Decimal("70"))

    def test_transferencia_muda_local_sem_alterar_total(self):
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"materia_prima": self.mp},
            "100",
            destino=self.almoxarifado,
        )
        movimentar(
            TipoMovimentacao.TRANSFERENCIA,
            {"materia_prima": self.mp},
            "40",
            origem=self.almoxarifado,
            destino=self.producao,
        )
        self.assertEqual(saldo(self.mp), Decimal("100"))
        self.assertEqual(saldo(self.mp, local=self.almoxarifado), Decimal("60"))
        self.assertEqual(saldo(self.mp, local=self.producao), Decimal("40"))

    def test_ajustes_de_inventario(self):
        movimentar(
            TipoMovimentacao.AJUSTE_ENTRADA,
            {"materia_prima": self.mp},
            "10",
            destino=self.almoxarifado,
        )
        movimentar(
            TipoMovimentacao.AJUSTE_SAIDA,
            {"materia_prima": self.mp},
            "4",
            origem=self.almoxarifado,
        )
        self.assertEqual(saldo(self.mp), Decimal("6"))

    def test_saldo_por_lote(self):
        lote_a = Lote.objects.create(codigo="L-A", materia_prima=self.mp)
        lote_b = Lote.objects.create(codigo="L-B", materia_prima=self.mp)
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"materia_prima": self.mp},
            "50",
            destino=self.almoxarifado,
            lote=lote_a,
        )
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"materia_prima": self.mp},
            "20",
            destino=self.almoxarifado,
            lote=lote_b,
        )
        self.assertEqual(saldo(self.mp), Decimal("70"))
        self.assertEqual(saldo(self.mp, lote=lote_a), Decimal("50"))
        self.assertEqual(saldo(self.mp, lote=lote_b), Decimal("20"))


class ValidacoesTests(BaseEstoque):
    def test_saida_nao_pode_deixar_saldo_negativo(self):
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"materia_prima": self.mp},
            "10",
            destino=self.almoxarifado,
        )
        with self.assertRaises(ValidationError):
            movimentar(
                TipoMovimentacao.SAIDA,
                {"materia_prima": self.mp},
                "11",
                origem=self.almoxarifado,
            )

    def test_transferencia_exige_origem_e_destino_diferentes(self):
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"materia_prima": self.mp},
            "10",
            destino=self.almoxarifado,
        )
        with self.assertRaises(ValidationError):
            movimentar(
                TipoMovimentacao.TRANSFERENCIA,
                {"materia_prima": self.mp},
                "5",
                origem=self.almoxarifado,
                destino=self.almoxarifado,
            )

    def test_entrada_nao_aceita_origem(self):
        with self.assertRaises(ValidationError):
            movimentar(
                TipoMovimentacao.ENTRADA,
                {"materia_prima": self.mp},
                "5",
                origem=self.almoxarifado,
                destino=self.producao,
            )

    def test_movimentacao_exige_exatamente_um_item(self):
        with self.assertRaises(ValidationError):
            movimentar(
                TipoMovimentacao.ENTRADA,
                {"materia_prima": self.mp, "produto": self.produto},
                "5",
                destino=self.almoxarifado,
            )
        with self.assertRaises(ValidationError):
            movimentar(TipoMovimentacao.ENTRADA, {}, "5", destino=self.almoxarifado)

    def test_lote_de_outro_item_e_rejeitado(self):
        lote_do_produto = Lote.objects.create(codigo="L-P", produto=self.produto)
        with self.assertRaises(ValidationError):
            movimentar(
                TipoMovimentacao.ENTRADA,
                {"materia_prima": self.mp},
                "5",
                destino=self.almoxarifado,
                lote=lote_do_produto,
            )


class LoteTests(BaseEstoque):
    def test_situacao_validade(self):
        hoje = timezone.localdate()
        sem_validade = Lote.objects.create(codigo="L-1", materia_prima=self.mp)
        vencido = Lote.objects.create(
            codigo="L-2", materia_prima=self.mp, validade=hoje - timedelta(days=1)
        )
        vence_breve = Lote.objects.create(
            codigo="L-3", materia_prima=self.mp, validade=hoje + timedelta(days=10)
        )
        ok = Lote.objects.create(
            codigo="L-4", materia_prima=self.mp, validade=hoje + timedelta(days=90)
        )
        self.assertEqual(sem_validade.situacao_validade, SituacaoValidade.SEM_VALIDADE)
        self.assertEqual(vencido.situacao_validade, SituacaoValidade.VENCIDO)
        self.assertEqual(vence_breve.situacao_validade, SituacaoValidade.VENCE_EM_BREVE)
        self.assertEqual(ok.situacao_validade, SituacaoValidade.OK)


class LoteInternoTests(BaseEstoque):
    """Etapa 2a do plano de correções: lote interno automático e sequencial."""

    def test_codigos_sequenciais_por_tipo_sem_repeticao(self):
        ano = timezone.localdate().year
        produto = Produto.objects.create(codigo="PA-9", nome="Produto teste")

        self.assertEqual(gerar_lote_interno(self.mp), f"MP-{ano}-00001")
        self.assertEqual(gerar_lote_interno(self.mp), f"MP-{ano}-00002")
        # A sequência do produto acabado é independente da sequência de MP
        self.assertEqual(gerar_lote_interno(produto), f"PA-{ano}-00001")

    def test_criar_lote_interno_grava_fornecedor_validade_e_auditoria(self):
        usuario = criar_usuario("almoxarife.lote", perfil=ALMOXARIFADO)
        validade = timezone.localdate() + timedelta(days=180)
        lote = criar_lote_interno(
            self.mp, usuario, validade=validade, lote_fornecedor="  FAB-778 "
        )
        self.assertRegex(lote.codigo, r"^MP-\d{4}-00001$")
        self.assertEqual(lote.lote_fornecedor, "FAB-778")
        self.assertEqual(lote.validade, validade)
        self.assertEqual(lote.materia_prima, self.mp)
        self.assertEqual(lote.criado_por, usuario)

    def test_colisao_com_lote_antigo_avanca_a_sequencia(self):
        usuario = criar_usuario("almoxarife.lote", perfil=ALMOXARIFADO)
        ano = timezone.localdate().year
        # Lote antigo digitado à mão com o mesmo formato do gerador
        Lote.objects.create(codigo=f"MP-{ano}-00001", materia_prima=self.mp)

        lote = criar_lote_interno(self.mp, usuario)
        self.assertEqual(lote.codigo, f"MP-{ano}-00002")

    def test_sequencia_reinicia_por_ano(self):
        ano = timezone.localdate().year
        SequenciaLote.objects.create(tipo="MP", ano=ano - 1, ultimo_numero=42)
        self.assertEqual(gerar_lote_interno(self.mp), f"MP-{ano}-00001")


class MovimentarViewTests(BaseEstoque):
    def setUp(self):
        super().setUp()
        self.usuario = criar_usuario("almoxarife", perfil=ALMOXARIFADO)
        self.client.login(username="almoxarife", password="senha-forte-123")

    def dados(self, **kwargs):
        dados = {
            "tipo": TipoMovimentacao.ENTRADA,
            "item": f"MP-{self.mp.pk}",
            "quantidade": "100",
            "lote_codigo": "LOTE-2026-001",
            "lote_validade": "",
            "local_origem": "",
            "local_destino": str(self.almoxarifado.pk),
            "motivo": "Recebimento inicial",
            "documento": "NF 123",
        }
        dados.update(kwargs)
        return dados

    def test_entrada_cria_lote_e_registra_auditoria(self):
        response = self.client.post(reverse("estoque:movimentar"), self.dados())
        self.assertRedirects(response, reverse("estoque:saldo"))

        movimentacao = Movimentacao.objects.get()
        self.assertEqual(movimentacao.criado_por, self.usuario)
        self.assertEqual(movimentacao.lote.codigo, "LOTE-2026-001")
        self.assertEqual(movimentacao.lote.criado_por, self.usuario)
        self.assertEqual(saldo(self.mp), Decimal("100"))

    def test_entrada_reutiliza_lote_existente(self):
        lote = Lote.objects.create(codigo="LOTE-2026-001", materia_prima=self.mp)
        self.client.post(reverse("estoque:movimentar"), self.dados())
        self.assertEqual(Lote.objects.count(), 1)
        self.assertEqual(Movimentacao.objects.get().lote, lote)

    def test_motivo_e_obrigatorio(self):
        response = self.client.post(
            reverse("estoque:movimentar"), self.dados(motivo="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Movimentacao.objects.count(), 0)

    def test_saida_com_saldo_insuficiente_mostra_erro(self):
        response = self.client.post(
            reverse("estoque:movimentar"),
            self.dados(
                tipo=TipoMovimentacao.SAIDA,
                lote_codigo="",
                local_origem=str(self.almoxarifado.pk),
                local_destino="",
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saldo insuficiente")

    def test_validade_divergente_de_lote_existente_e_rejeitada(self):
        hoje = timezone.localdate()
        Lote.objects.create(
            codigo="LOTE-2026-001",
            materia_prima=self.mp,
            validade=hoje + timedelta(days=30),
        )
        response = self.client.post(
            reverse("estoque:movimentar"),
            self.dados(lote_validade=(hoje + timedelta(days=60)).isoformat()),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "já existe com validade")


class TelasTests(BaseEstoque):
    def setUp(self):
        super().setUp()
        criar_usuario("almoxarife", perfil=ALMOXARIFADO)
        self.client.login(username="almoxarife", password="senha-forte-123")

    def test_saldo_esconde_zerados_por_padrao(self):
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"materia_prima": self.mp},
            "10",
            destino=self.almoxarifado,
        )
        movimentar(
            TipoMovimentacao.SAIDA,
            {"materia_prima": self.mp},
            "10",
            origem=self.almoxarifado,
        )
        response = self.client.get(reverse("estoque:saldo"))
        self.assertNotContains(response, "MP-1")

        response = self.client.get(reverse("estoque:saldo"), {"zerados": "1"})
        self.assertContains(response, "MP-1")

    def test_saldo_filtra_por_pesquisa(self):
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"materia_prima": self.mp},
            "10",
            destino=self.almoxarifado,
        )
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"produto": self.produto},
            "5",
            destino=self.almoxarifado,
        )
        response = self.client.get(reverse("estoque:saldo"), {"q": "lavanda"})
        self.assertContains(response, "Essência de lavanda")
        self.assertContains(response, "Perfume Lavanda")

        response = self.client.get(reverse("estoque:saldo"), {"tipo_item": "produto"})
        self.assertContains(response, "Perfume Lavanda")
        self.assertNotContains(response, "Essência de lavanda")

    def test_historico_filtra_por_tipo(self):
        movimentar(
            TipoMovimentacao.ENTRADA,
            {"materia_prima": self.mp},
            "10",
            destino=self.almoxarifado,
        )
        response = self.client.get(
            reverse("estoque:movimentacoes"), {"tipo": TipoMovimentacao.SAIDA}
        )
        self.assertContains(response, "Nenhuma movimentação encontrada.")

    def test_locais_crud_reutilizado(self):
        response = self.client.post(
            reverse("estoque:local_criar"),
            {"nome": "Quarentena", "descricao": "", "ativo": "on"},
        )
        self.assertRedirects(response, reverse("estoque:local_lista"))
        self.assertTrue(LocalEstoque.objects.filter(nome="Quarentena").exists())


class PermissoesTests(TestCase):
    def setUp(self):
        criar_usuario("almoxarife", perfil=ALMOXARIFADO)
        criar_usuario("operador", perfil=PRODUCAO)

    def test_producao_nao_acessa_estoque(self):
        self.client.login(username="operador", password="senha-forte-123")
        for rota in ["estoque:saldo", "estoque:movimentacoes", "estoque:movimentar"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 403)

    def test_almoxarifado_acessa_estoque(self):
        self.client.login(username="almoxarife", password="senha-forte-123")
        for rota in [
            "estoque:saldo",
            "estoque:movimentacoes",
            "estoque:movimentar",
            "estoque:local_lista",
        ]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 200)
