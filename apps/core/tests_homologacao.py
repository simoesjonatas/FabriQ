"""
Roteiro de aceite final (Etapa 13 do plano, PDF seção 9).

Percorre o ciclo completo com **dados fictícios**, na ordem do roteiro do
cliente, usando as mesmas telas e serviços que o operador usa:

    cadastros → recebimento (lote interno automático) → quarentena/CQ →
    pedido → OP liberada (fórmula congelada) → pesagem com dupla
    conferência → equipamento/etapas/controles → envase/perdas/desvio →
    lote acabado → CQ final → expedição → dossiê + PDF → rastreabilidade
    nos dois sentidos → trilha de auditoria.

O companheiro deste arquivo é `tests_violacoes.py`, que tenta furar cada
bloqueio obrigatório (PDF 7.2).
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import (
    ALMOXARIFADO,
    DIRETORIA,
    EXPEDICAO,
    PCP,
    PRODUCAO,
    QUALIDADE,
)
from apps.auditoria.servicos import trilha_de
from apps.cadastros.models import (
    Balanca,
    Cliente,
    Embalagem,
    Equipamento,
    Fornecedor,
    MateriaPrima,
    Produto,
    Setor,
    VersaoArte,
)
from apps.dossie.models import GeracaoDossie
from apps.estoque.models import LocalEstoque, SituacaoLote, saldo
from apps.estoque.rastreabilidade import rastrear_para_frente, rastrear_para_tras
from apps.expedicao.models import registrar_expedicao
from apps.ordens.models import (
    ComponenteFormula,
    EtapaFormula,
    Formula,
    OrdemProducao,
    StatusOP,
)
from apps.pedidos.models import ItemPedido, Pedido, StatusPedido
from apps.producao.models import (
    ChecklistEquipamentoOP,
    DecisaoDesvio,
    Desvio,
    ExecucaoOP,
    StatusDesvio,
    TipoChecklistEquipamento,
    TipoDesvio,
    apontar_consumos,
    decidir_desvio,
    registrar_controle,
    registrar_envase,
    registrar_etapa,
    registrar_pesagem,
)
from apps.qualidade.models import (
    Analise,
    EspecificacaoProduto,
    StatusAnalise,
    TipoAnalise,
)
from apps.recebimento.models import ItemRecebimento, StatusQuarentena

User = get_user_model()
SENHA = "senha-forte-123"


def criar_usuario(username, perfil):
    usuario = User.objects.create_user(username=username, password=SENHA)
    usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class RoteiroDeAceiteTests(TestCase):
    """PDF 9: um ciclo inteiro, do cadastro à rastreabilidade."""

    def setUp(self):
        self.hoje = timezone.localdate()

        # Cada papel tem seu usuário — o roteiro também valida os perfis
        self.almoxarife = criar_usuario("homolog.almox", ALMOXARIFADO)
        self.qualidade = criar_usuario("homolog.cq", QUALIDADE)
        self.pcp = criar_usuario("homolog.pcp", PCP)
        self.operador = criar_usuario("homolog.op", PRODUCAO)
        self.conferente = criar_usuario("homolog.conf", PRODUCAO)
        self.expedidor = criar_usuario("homolog.exp", EXPEDICAO)
        self.diretor = criar_usuario("homolog.dir", DIRETORIA)

    # ------------------------------------------------ 1. Cadastros básicos
    def _passo_1_cadastros(self):
        self.fornecedor = Fornecedor.objects.create(razao_social="Insumos Bela LTDA")
        self.cliente = Cliente.objects.create(razao_social="Farmácia Aurora LTDA")
        self.produto = Produto.objects.create(
            codigo="PA-H1", nome="Creme hidratante 100 g", unidade="UN"
        )
        self.mp = MateriaPrima.objects.create(
            codigo="MP-H1", nome="Base creme neutra", unidade="KG"
        )
        self.embalagem = Embalagem.objects.create(
            codigo="EMB-H1", nome="Bisnaga 100 g", tipo="FRASCO", unidade="UN"
        )
        self.deposito = LocalEstoque.objects.create(nome="Almoxarifado homologação")
        self.acabados = LocalEstoque.objects.create(nome="Acabados homologação")
        self.linha = Setor.objects.create(nome="Linha homologação")
        self.equipamento = Equipamento.objects.create(
            codigo="EQ-H1", nome="Misturador", ultima_limpeza=self.hoje
        )
        self.balanca = Balanca.objects.create(
            codigo="BAL-H1",
            descricao="Balança de bancada",
            calibracao_validade=self.hoje + timedelta(days=180),
        )
        self.ph = TipoAnalise.objects.create(nome="pH")
        EspecificacaoProduto.objects.create(
            produto=self.produto,
            tipo=self.ph,
            valor_minimo=Decimal("5.5"),
            valor_maximo=Decimal("7.0"),
        )
        self.arte = VersaoArte.objects.create(
            produto=self.produto, versao="v1", status="APROVADA",
            data_aprovacao=self.hoje,
        )
        self.formula = Formula.objects.create(
            produto=self.produto, nome="Padrão homologação",
            rendimento=Decimal("100"),
        )
        ComponenteFormula.objects.create(
            formula=self.formula, materia_prima=self.mp, quantidade=Decimal("50")
        )
        ComponenteFormula.objects.create(
            formula=self.formula, embalagem=self.embalagem, quantidade=Decimal("100")
        )
        EtapaFormula.objects.create(
            formula=self.formula, sequencia=1,
            instrucao="Aquecer a base a 60 °C.",
            temperatura_prevista=Decimal("60"),
            tempo_previsto_min=Decimal("15"),
        )

    # ------------------------------- 2. Recebimento com lote automático
    def _passo_2_recebimento(self):
        self.client.force_login(self.almoxarife)
        resposta = self.client.post(
            reverse("recebimento:criar"),
            {
                "fornecedor": self.fornecedor.pk,
                "cliente": "",
                "nota_fiscal": "NF-HOMOLOG-1",
                "data_recebimento": self.hoje.isoformat(),
                "observacoes": "",
                "itens-TOTAL_FORMS": "2",
                "itens-INITIAL_FORMS": "0",
                "itens-MIN_NUM_FORMS": "0",
                "itens-MAX_NUM_FORMS": "1000",
                "itens-0-item": f"MP-{self.mp.pk}",
                "itens-0-quantidade": "100",
                "itens-0-lote_fornecedor": "BASE-2026-01",
                "itens-0-lote_validade": (self.hoje + timedelta(days=365)).isoformat(),
                "itens-1-item": f"E-{self.embalagem.pk}",
                "itens-1-quantidade": "500",
                "itens-1-lote_fornecedor": "BIS-2026-07",
                "itens-1-lote_validade": "",
                "anexos-TOTAL_FORMS": "0",
                "anexos-INITIAL_FORMS": "0",
                "anexos-MIN_NUM_FORMS": "0",
                "anexos-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(resposta.status_code, 302, "recebimento não foi registrado")

        self.item_mp = ItemRecebimento.objects.get(materia_prima=self.mp)
        self.item_emb = ItemRecebimento.objects.get(embalagem=self.embalagem)
        self.lote_mp = self.item_mp.lote
        self.lote_emb = self.item_emb.lote

        # Lote interno gerado automaticamente e lote do fornecedor preservado
        self.assertTrue(self.lote_mp.codigo.startswith("MP-"))
        self.assertEqual(self.lote_mp.lote_fornecedor, "BASE-2026-01")
        self.assertEqual(self.item_mp.status, StatusQuarentena.EM_QUARENTENA)

    # ------------------------------------- 3. Quarentena, análise e liberação
    def _passo_3_quarentena(self):
        self.client.force_login(self.qualidade)
        for item in (self.item_mp, self.item_emb):
            resposta = self.client.post(
                reverse("recebimento:decidir", args=[item.pk]),
                {
                    "decisao": StatusQuarentena.LIBERADO,
                    "observacoes": "Laudo do fornecedor conferido.",
                    "local_destino": self.deposito.pk,
                },
            )
            self.assertEqual(resposta.status_code, 302)
            item.refresh_from_db()
            self.assertEqual(item.status, StatusQuarentena.LIBERADO)

        self.lote_mp.refresh_from_db()
        self.assertEqual(self.lote_mp.situacao, SituacaoLote.APROVADO)
        self.assertEqual(saldo(self.mp, lote=self.lote_mp, local=self.deposito),
                         Decimal("100"))

    # -------------------------------------------- 4. Pedido, PCP e OP liberada
    def _passo_4_pedido_e_op(self):
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            prazo=self.hoje + timedelta(days=20),
            criado_por=self.pcp,
            atualizado_por=self.pcp,
        )
        self.item_pedido = ItemPedido.objects.create(
            pedido=self.pedido, produto=self.produto, quantidade=Decimal("100")
        )
        self.pedido.transicionar(StatusPedido.EM_ANALISE, self.pcp)
        self.pedido.transicionar(StatusPedido.PROGRAMADO, self.pcp)

        self.client.force_login(self.pcp)
        resposta = self.client.post(
            reverse("ordens:criar"),
            {
                "item_pedido": self.item_pedido.pk,
                "formula": self.formula.pk,
                "quantidade": "100",
                "equipamento": self.equipamento.pk,
                "linha": self.linha.pk,
                "operador": self.operador.pk,
                "supervisor": self.pcp.pk,
                "data_programada": self.hoje.isoformat(),
                "prazo": (self.hoje + timedelta(days=5)).isoformat(),
                "observacoes": "",
            },
        )
        self.assertEqual(resposta.status_code, 302, "OP não foi emitida")
        self.ordem = OrdemProducao.objects.latest("id")

        resposta = self.client.post(reverse("ordens:liberar", args=[self.ordem.pk]))
        self.ordem.refresh_from_db()
        self.assertEqual(self.ordem.status, StatusOP.LIBERADA, "OP não foi liberada")

        # Liberação congela a fórmula e reserva o lote do produto
        self.assertIsNotNone(self.ordem.snapshot_formula)
        self.assertIsNotNone(self.ordem.lote_produto)
        self.lote_pa = self.ordem.lote_produto

    # ------------------------------- 5. Lotes específicos + pesagem conferida
    def _passo_5_pesagem(self):
        material_mp = self.ordem.materiais.get(materia_prima=self.mp)
        material_emb = self.ordem.materiais.get(embalagem=self.embalagem)
        apontar_consumos(
            self.ordem,
            self.operador,
            [
                (material_mp, self.lote_mp, self.deposito, Decimal("50")),
                (material_emb, self.lote_emb, self.deposito, Decimal("100")),
            ],
        )
        pesagem = registrar_pesagem(
            material=material_mp,
            lote=self.lote_mp,
            balanca=self.balanca,
            quantidade_pesada=material_mp.quantidade_necessaria,
            tolerancia_percentual=Decimal("2"),
            operador=self.operador,
            conferente=self.conferente,
            etiqueta="ETQ-H1",
        )
        self.assertNotEqual(pesagem.operador, pesagem.conferente)

    # --------------------------- 6. Equipamento, etapas e controle em processo
    def _passo_6_processo(self):
        ChecklistEquipamentoOP.objects.create(
            ordem=self.ordem,
            equipamento=self.equipamento,
            tipo=TipoChecklistEquipamento.PRE_USO,
            itens_verificados="Limpeza e vedação conferidas.",
            condicao_final="Liberado para uso",
            responsavel=self.operador,
        )
        for etapa in self.ordem.snapshot_formula.etapas.order_by("sequencia"):
            registrar_etapa(
                ordem=self.ordem,
                etapa=etapa,
                operador=self.operador,
                conferente=self.conferente,
                temperatura_real=Decimal("60"),
                tempo_real_min=Decimal("15"),
            )
        controle = registrar_controle(
            ordem=self.ordem,
            tipo=self.ph,
            analista=self.qualidade,
            resultado=Decimal("6.2"),
            metodo="Potenciométrico",
        )
        self.assertFalse(controle.fora_especificacao)

    # -------------------------------- 7. Envase, perdas e desvio + 8. conclusão
    def _passo_7_e_8_producao(self):
        execucao = ExecucaoOP.iniciar(self.ordem, self.operador)

        desvio = Desvio.objects.create(
            ordem=self.ordem,
            tipo=TipoDesvio.PROCESSO,
            descricao="Temperatura oscilou 2 °C acima na etapa 1.",
            impacto="Sem impacto no produto.",
            acao_imediata="Ajuste do setpoint.",
            responsavel=self.operador,
        )
        decidir_desvio(
            desvio, self.qualidade, DecisaoDesvio.ACEITO,
            "Desvio sem impacto na qualidade do lote.",
        )
        desvio.refresh_from_db()
        self.assertEqual(desvio.status, StatusDesvio.ENCERRADO)

        registrar_envase(
            ordem=self.ordem,
            versao_arte=self.arte,
            quantidade_envasada=Decimal("98"),
            operador=self.operador,
            conferente=self.conferente,
            linha=self.linha,
            perdas=Decimal("2"),
        )
        execucao.concluir(
            usuario=self.operador,
            quantidade_produzida=Decimal("98"),
            perdas=Decimal("2"),
            validade=self.hoje + timedelta(days=540),
            local_destino=self.acabados,
        )
        self.ordem.refresh_from_db()
        self.assertEqual(self.ordem.status, StatusOP.CONCLUIDA)
        self.lote_pa.refresh_from_db()
        self.assertEqual(self.lote_pa.situacao, SituacaoLote.AGUARDANDO_CQ)

    # ------------------------------------------------- 8b. CQ final e liberação
    def _passo_8_cq_final(self):
        analise = Analise.objects.create(
            lote=self.lote_pa,
            analista=self.qualidade,
            criado_por=self.qualidade,
            atualizado_por=self.qualidade,
        )
        analise.resultados.create(tipo=self.ph, valor_numerico=Decimal("6.2"))

        self.client.force_login(self.qualidade)
        resposta = self.client.post(
            reverse("qualidade:decidir", args=[analise.pk]),
            {"decisao": StatusAnalise.APROVADA, "parecer": "Dentro da especificação."},
        )
        self.assertEqual(resposta.status_code, 302)
        self.lote_pa.refresh_from_db()
        self.assertEqual(
            self.lote_pa.situacao, SituacaoLote.APROVADO,
            "decisão do CQ não liberou o lote",
        )

    # --------------------------------------- 9. Expedição só do lote liberado
    def _passo_9_expedicao(self):
        # Iniciar a produção já moveu o pedido para "Em produção"
        self.pedido.refresh_from_db()
        self.pedido.transicionar(StatusPedido.CQ, self.qualidade)
        self.pedido.transicionar(StatusPedido.FINALIZADO, self.qualidade)
        self.expedicao = registrar_expedicao(
            pedido=self.pedido,
            data=self.hoje,
            usuario=self.expedidor,
            linhas=[(self.item_pedido, self.lote_pa, Decimal("98"))],
            nota_fiscal="NF-SAIDA-1",
            transportadora="Transportadora Homologação",
        )
        self.pedido.transicionar(StatusPedido.EXPEDIDO, self.expedidor)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, StatusPedido.EXPEDIDO)
        self.lote_pa.refresh_from_db()
        self.assertEqual(self.lote_pa.situacao, SituacaoLote.EXPEDIDO)

    # ----------------------- 10 e 11. Do pedido expedido ao dossiê e às fichas
    def _passo_10_e_11_navegacao(self):
        self.client.force_login(self.diretor)

        detalhe = self.client.get(reverse("pedidos:detalhe", args=[self.pedido.pk]))
        self.assertContains(detalhe, self.produto.get_absolute_url())
        self.assertContains(detalhe, self.lote_pa.get_absolute_url())
        self.assertContains(
            detalhe, reverse("dossie:detalhe", args=[self.lote_pa.pk])
        )

        ficha_lote = self.client.get(self.lote_pa.get_absolute_url())
        self.assertContains(ficha_lote, self.ordem.numero)

        op = self.client.get(reverse("ordens:detalhe", args=[self.ordem.pk]))
        self.assertContains(op, self.mp.get_absolute_url())
        self.assertContains(op, self.lote_mp.codigo)
        self.assertContains(op, self.cliente.get_absolute_url())

        ficha_mp = self.client.get(self.mp.get_absolute_url())
        self.assertContains(ficha_mp, self.lote_mp.codigo)
        self.assertContains(ficha_mp, str(self.fornecedor))

    # ---------------------------------------- 12. Rastreabilidade nos dois lados
    def _passo_12_rastreabilidade(self):
        frente = rastrear_para_frente(self.lote_mp)
        self.assertEqual(frente["ordens"][0]["ordem"], self.ordem)
        self.assertEqual(frente["ordens"][0]["lote_produzido"], self.lote_pa)
        self.assertIn(self.cliente, frente["clientes_atendidos"])

        tras = rastrear_para_tras(self.lote_pa)
        lotes_usados = {linha["lote"] for linha in tras["ordens"][0]["materiais"]}
        self.assertIn(self.lote_mp, lotes_usados)
        self.assertIn(self.lote_emb, lotes_usados)
        self.assertEqual(
            tras["ordens"][0]["materiais"][0]["origem"]["fornecedor"], self.fornecedor
        )

    # -------------------------------------------------- 13. Dossiê completo + PDF
    def _passo_13_dossie(self):
        self.client.force_login(self.diretor)

        tela = self.client.get(reverse("dossie:detalhe", args=[self.lote_pa.pk]))
        self.assertEqual(tela.status_code, 200)
        for bloco in [
            "Identificação e situação",
            "Fórmula e versão utilizadas",
            "Materiais, lotes e documentos",
            "Pesagens e conferências",
            "Equipamentos e checklists",
            "Etapas do processo",
            "Controles em processo",
            "Envase, embalagem e rotulagem",
            "Perdas e rendimento",
            "Desvios e decisões",
            "Liberações e assinaturas por fase",
            "Controle de qualidade final",
            "Expedições",
            "Trilha de auditoria do lote",
        ]:
            self.assertContains(tela, bloco, msg_prefix=f"bloco ausente: {bloco}")

        pdf = self.client.post(reverse("dossie:pdf", args=[self.lote_pa.pk]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF-"))

        geracao = GeracaoDossie.objects.get(lote=self.lote_pa)
        self.assertEqual(geracao.gerado_por, self.diretor)
        self.assertEqual(len(geracao.hash_arquivo), 64)

    # ------------------------------------------------------- 14. Trilha completa
    def _passo_14_trilha(self):
        trilha = list(trilha_de(self.lote_pa))
        self.assertTrue(trilha, "o lote acabado não tem trilha de auditoria")
        acoes = {registro.acao for registro in trilha}
        self.assertTrue(acoes, "nenhuma ação registrada na trilha")

        trilha_mp = list(trilha_de(self.lote_mp))
        self.assertTrue(trilha_mp, "o lote de MP não tem trilha de auditoria")

    # =========================================================== roteiro inteiro
    def test_roteiro_de_aceite_completo(self):
        """PDF 9: do cadastro à rastreabilidade, sem planilha paralela."""
        self._passo_1_cadastros()
        self._passo_2_recebimento()
        self._passo_3_quarentena()
        self._passo_4_pedido_e_op()
        self._passo_5_pesagem()
        self._passo_6_processo()
        self._passo_7_e_8_producao()
        self._passo_8_cq_final()
        self._passo_9_expedicao()
        self._passo_10_e_11_navegacao()
        self._passo_12_rastreabilidade()
        self._passo_13_dossie()
        self._passo_14_trilha()

        # O ciclo fecha: estoque baixado e produto entregue ao cliente
        self.assertEqual(saldo(self.produto, lote=self.lote_pa), Decimal("0"))
        self.assertEqual(saldo(self.mp, lote=self.lote_mp), Decimal("50"))
