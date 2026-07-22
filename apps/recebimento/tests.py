from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import ALMOXARIFADO, PRODUCAO, QUALIDADE
from apps.cadastros.models import Fornecedor, MateriaPrima
from apps.estoque.models import (
    LocalEstoque,
    Movimentacao,
    TipoMovimentacao,
    saldo,
)

from .models import (
    DecisaoQuarentena,
    ItemRecebimento,
    Recebimento,
    StatusQuarentena,
    local_quarentena,
)

User = get_user_model()

PDF_MINIMO = b"%PDF-1.4 conteudo de teste"


def criar_usuario(username, perfil=None, senha="senha-forte-123"):
    usuario = User.objects.create_user(username=username, password=senha)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class BaseRecebimento(TestCase):
    def setUp(self):
        self.almoxarife = criar_usuario("almoxarife", perfil=ALMOXARIFADO)
        self.analista = criar_usuario("analista", perfil=QUALIDADE)
        self.fornecedor = Fornecedor.objects.create(razao_social="Química Vale LTDA")
        self.mp = MateriaPrima.objects.create(codigo="MP-1", nome="Essência de lavanda")
        self.deposito = LocalEstoque.objects.create(nome="Almoxarifado MP")

    def dados_recebimento(self, **kwargs):
        dados = {
            "fornecedor": self.fornecedor.pk,
            "nota_fiscal": "4581",
            "data_recebimento": timezone.localdate().isoformat(),
            "observacoes": "",
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-item": f"MP-{self.mp.pk}",
            "itens-0-quantidade": "100",
            "itens-0-lote_fornecedor": "LOTE-001",
            "itens-0-lote_validade": "",
            "anexos-TOTAL_FORMS": "0",
            "anexos-INITIAL_FORMS": "0",
            "anexos-MIN_NUM_FORMS": "0",
            "anexos-MAX_NUM_FORMS": "1000",
        }
        dados.update(kwargs)
        return dados

    def registrar(self, **kwargs):
        self.client.login(username="almoxarife", password="senha-forte-123")
        return self.client.post(
            reverse("recebimento:criar"), self.dados_recebimento(**kwargs)
        )


class RegistroTests(BaseRecebimento):
    def test_formulario_de_recebimento_usa_abas(self):
        self.client.login(username="almoxarife", password="senha-forte-123")
        response = self.client.get(reverse("recebimento:criar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="tab-nota-tab"')
        self.assertContains(response, 'id="tab-itens-tab"')
        self.assertContains(response, 'id="tab-anexos-tab"')
        self.assertEqual(response.context["aba_recebimento_ativa"], "nota")

    def test_registro_cria_lote_item_e_entrada_na_quarentena(self):
        response = self.registrar()
        recebimento = Recebimento.objects.get()
        self.assertRedirects(
            response, reverse("recebimento:detalhe", args=[recebimento.pk])
        )

        item = recebimento.itens.get()
        self.assertEqual(item.status, StatusQuarentena.EM_QUARENTENA)
        # Lote interno gerado automaticamente; o código do fornecedor fica à parte
        self.assertRegex(item.lote.codigo, r"^MP-\d{4}-00001$")
        self.assertEqual(item.lote.lote_fornecedor, "LOTE-001")
        self.assertEqual(item.lote.materia_prima, self.mp)

        movimentacao = Movimentacao.objects.get()
        self.assertEqual(movimentacao.tipo, TipoMovimentacao.ENTRADA)
        self.assertEqual(movimentacao.local_destino, local_quarentena())
        self.assertEqual(movimentacao.criado_por, self.almoxarife)
        self.assertIn(recebimento.numero, movimentacao.motivo)

        self.assertEqual(
            saldo(self.mp, lote=item.lote, local=local_quarentena()),
            Decimal("100"),
        )

    def test_recebimento_sem_itens_e_rejeitado(self):
        response = self.registrar(**{"itens-0-item": "", "itens-0-quantidade": "",
                                     "itens-0-lote_fornecedor": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pelo menos um item")
        self.assertEqual(response.context["aba_recebimento_ativa"], "itens")
        self.assertTrue(response.context["itens_formset_tem_erros"])
        self.assertEqual(Recebimento.objects.count(), 0)

    def test_lote_do_fornecedor_e_obrigatorio(self):
        response = self.registrar(**{"itens-0-lote_fornecedor": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Recebimento.objects.count(), 0)

    def test_registro_com_anexo(self):
        self.client.login(username="almoxarife", password="senha-forte-123")
        dados = self.dados_recebimento(
            **{
                "anexos-TOTAL_FORMS": "1",
                "anexos-0-tipo": "COA",
                "anexos-0-descricao": "Certificado do lote",
            }
        )
        arquivo = SimpleUploadedFile(
            "coa.pdf", PDF_MINIMO, content_type="application/pdf"
        )
        with override_settings(MEDIA_ROOT="/tmp/fabriq-test-media"):
            response = self.client.post(
                reverse("recebimento:criar"), {**dados, "anexos-0-arquivo": arquivo}
            )
            recebimento = Recebimento.objects.get()
            self.assertRedirects(
                response, reverse("recebimento:detalhe", args=[recebimento.pk])
            )
            anexo = recebimento.anexos.get()
            self.assertEqual(anexo.tipo, "COA")
            self.assertEqual(anexo.criado_por, self.almoxarife)

    def test_anexo_com_extensao_invalida_e_rejeitado(self):
        self.client.login(username="almoxarife", password="senha-forte-123")
        dados = self.dados_recebimento(
            **{"anexos-TOTAL_FORMS": "1", "anexos-0-tipo": "OUTRO"}
        )
        arquivo = SimpleUploadedFile(
            "virus.exe", b"MZ...", content_type="application/octet-stream"
        )
        response = self.client.post(
            reverse("recebimento:criar"), {**dados, "anexos-0-arquivo": arquivo}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["aba_recebimento_ativa"], "anexos")
        self.assertTrue(response.context["anexos_formset_tem_erros"])
        self.assertEqual(Recebimento.objects.count(), 0)


class QuarentenaTests(BaseRecebimento):
    def setUp(self):
        super().setUp()
        self.registrar()
        self.client.logout()
        self.item = ItemRecebimento.objects.get()

    def decidir(self, decisao, observacoes="", local_destino=""):
        return self.client.post(
            reverse("recebimento:decidir", args=[self.item.pk]),
            {
                "decisao": decisao,
                "observacoes": observacoes,
                "local_destino": local_destino,
            },
        )

    def entrar_como_qualidade(self):
        self.client.login(username="analista", password="senha-forte-123")

    def test_liberar_transfere_para_o_destino(self):
        self.entrar_como_qualidade()
        self.decidir(StatusQuarentena.LIBERADO, local_destino=str(self.deposito.pk))

        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.LIBERADO)

        self.assertEqual(
            saldo(self.mp, lote=self.item.lote, local=local_quarentena()),
            Decimal("0"),
        )
        self.assertEqual(
            saldo(self.mp, lote=self.item.lote, local=self.deposito),
            Decimal("100"),
        )

        decisao = self.item.decisoes.get()
        self.assertEqual(decisao.responsavel, self.analista)
        self.assertEqual(decisao.local_destino, self.deposito)

    def test_decisao_reflete_na_situacao_do_lote(self):
        """Etapa 5: a decisão da quarentena move a situação controlada do lote."""
        from apps.auditoria.models import AcaoAuditoria
        from apps.auditoria.servicos import trilha_de
        from apps.estoque.models import SituacaoLote

        self.entrar_como_qualidade()
        # Nasce aguardando CQ
        self.assertEqual(self.item.lote.situacao, SituacaoLote.AGUARDANDO_CQ)

        self.decidir(StatusQuarentena.LIBERADO, local_destino=str(self.deposito.pk))
        self.item.lote.refresh_from_db()
        self.assertEqual(self.item.lote.situacao, SituacaoLote.APROVADO)

        # A mudança de situação entrou na trilha do lote
        campos = list(
            trilha_de(self.item.lote)
            .filter(acao=AcaoAuditoria.ALTERACAO)
            .values_list("campo", flat=True)
        )
        self.assertIn("situação", campos)

    def test_reprovar_marca_lote_reprovado(self):
        from apps.estoque.models import SituacaoLote

        self.entrar_como_qualidade()
        self.decidir(StatusQuarentena.REPROVADO, observacoes="Fora de especificação")
        self.item.lote.refresh_from_db()
        self.assertEqual(self.item.lote.situacao, SituacaoLote.REPROVADO)

    def test_liberar_exige_local_de_destino(self):
        self.entrar_como_qualidade()
        self.decidir(StatusQuarentena.LIBERADO)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.EM_QUARENTENA)
        self.assertEqual(DecisaoQuarentena.objects.count(), 0)

    def test_reprovar_exige_observacoes(self):
        self.entrar_como_qualidade()
        self.decidir(StatusQuarentena.REPROVADO)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.EM_QUARENTENA)

        self.decidir(StatusQuarentena.REPROVADO, observacoes="Fora de especificação")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.REPROVADO)
        # Material reprovado permanece fisicamente na quarentena
        self.assertEqual(
            saldo(self.mp, lote=self.item.lote, local=local_quarentena()),
            Decimal("100"),
        )

    def test_bloquear_depois_liberar(self):
        self.entrar_como_qualidade()
        self.decidir(StatusQuarentena.BLOQUEADO, observacoes="Aguardando reanálise")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.BLOQUEADO)

        self.decidir(StatusQuarentena.LIBERADO, local_destino=str(self.deposito.pk))
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.LIBERADO)
        self.assertEqual(self.item.decisoes.count(), 2)

    def test_item_liberado_nao_aceita_nova_decisao(self):
        self.entrar_como_qualidade()
        self.decidir(StatusQuarentena.LIBERADO, local_destino=str(self.deposito.pk))
        self.decidir(StatusQuarentena.REPROVADO, observacoes="tarde demais")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.LIBERADO)
        self.assertEqual(self.item.decisoes.count(), 1)

    def test_fila_mostra_itens_pendentes(self):
        self.entrar_como_qualidade()
        response = self.client.get(reverse("recebimento:quarentena"))
        self.assertContains(response, "MP-1")
        self.assertContains(response, "LOTE-001")

        self.decidir(StatusQuarentena.LIBERADO, local_destino=str(self.deposito.pk))
        response = self.client.get(reverse("recebimento:quarentena"))
        self.assertContains(response, "Nenhum material aguardando decisão")

    def test_em_analise_dispensa_observacao_e_permanece_na_fila(self):
        self.entrar_como_qualidade()
        self.decidir(StatusQuarentena.EM_ANALISE)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.EM_ANALISE)

        response = self.client.get(reverse("recebimento:quarentena"))
        self.assertContains(response, "Em análise")

        # Da análise ainda é possível liberar
        self.decidir(StatusQuarentena.LIBERADO, local_destino=str(self.deposito.pk))
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.LIBERADO)

    def test_devolucao_so_apos_reprovacao_e_com_observacao(self):
        self.entrar_como_qualidade()
        # Direto da quarentena não é permitido
        self.decidir(StatusQuarentena.DEVOLVIDO, observacoes="Devolver ao fornecedor")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.EM_QUARENTENA)

        self.decidir(StatusQuarentena.REPROVADO, observacoes="Fora de especificação")
        # Sem observação a devolução é recusada
        self.decidir(StatusQuarentena.DEVOLVIDO)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.REPROVADO)

        self.decidir(StatusQuarentena.DEVOLVIDO, observacoes="Devolvido na NF 981")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.DEVOLVIDO)
        self.assertEqual(self.item.decisoes.count(), 2)


class EtiquetaTests(BaseRecebimento):
    """Etapa 2b: etiqueta de identificação da MP (Anexo A do plano)."""

    def setUp(self):
        super().setUp()
        self.registrar()
        self.item = ItemRecebimento.objects.get()

    def etiqueta(self):
        return self.client.get(reverse("recebimento:etiqueta", args=[self.item.pk]))

    def test_etiqueta_em_quarentena_sem_dados_de_liberacao(self):
        response = self.etiqueta()
        self.assertContains(response, "Essência de lavanda")
        self.assertContains(response, self.item.lote.codigo)
        self.assertContains(response, "LOTE-001")
        self.assertContains(response, "EM QUARENTENA")
        # Sem liberação do CQ: data em branco
        self.assertContains(response, "___/___/______")

    def test_etiqueta_de_lote_liberado_mostra_responsavel_e_localizacao(self):
        self.client.login(username="analista", password="senha-forte-123")
        self.client.post(
            reverse("recebimento:decidir", args=[self.item.pk]),
            {
                "decisao": StatusQuarentena.LIBERADO,
                "observacoes": "",
                "local_destino": str(self.deposito.pk),
            },
        )
        self.client.login(username="almoxarife", password="senha-forte-123")

        response = self.etiqueta()
        self.assertContains(response, "ANALISTA")
        self.assertContains(response, "Almoxarifado MP")
        self.assertNotContains(response, "___/___/______")

    def test_impressao_registra_na_trilha_do_lote(self):
        from apps.auditoria.models import AcaoAuditoria
        from apps.auditoria.servicos import trilha_de

        self.etiqueta()
        self.etiqueta()
        impressoes = trilha_de(self.item.lote).filter(acao=AcaoAuditoria.IMPRESSAO)
        self.assertEqual(impressoes.count(), 2)
        self.assertEqual(impressoes.first().usuario, self.almoxarife)

    def test_etiqueta_mostra_cliente_da_terceirizacao(self):
        from apps.cadastros.models import Cliente

        cliente = Cliente.objects.create(razao_social="Corpo & Cheiro")
        recebimento = self.item.recebimento
        recebimento.cliente = cliente
        recebimento.salvar_com_usuario(self.almoxarife)

        response = self.etiqueta()
        self.assertContains(response, "Corpo &amp; Cheiro")


class PermissoesTests(BaseRecebimento):
    def setUp(self):
        super().setUp()
        criar_usuario("operador", perfil=PRODUCAO)
        self.registrar()
        self.client.logout()
        self.item = ItemRecebimento.objects.get()

    def test_almoxarifado_nao_decide_quarentena(self):
        self.client.login(username="almoxarife", password="senha-forte-123")
        response = self.client.get(reverse("recebimento:quarentena"))
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("recebimento:decidir", args=[self.item.pk]),
            {"decisao": StatusQuarentena.LIBERADO, "local_destino": self.deposito.pk},
        )
        self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, StatusQuarentena.EM_QUARENTENA)

    def test_qualidade_nao_registra_recebimento(self):
        self.client.login(username="analista", password="senha-forte-123")
        for rota in ["recebimento:lista", "recebimento:criar"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 403)

    def test_producao_nao_acessa_nada(self):
        self.client.login(username="operador", password="senha-forte-123")
        for rota in ["recebimento:lista", "recebimento:quarentena"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 403)
