"""
Bateria de testes de violação (Etapa 13 do plano, PDF 7.2).

Para cada bloqueio obrigatório, este módulo **tenta furar a regra** e
confirma que o sistema impede a operação. É a contraprova do roteiro de
aceite (`tests_homologacao.py`): lá tudo dá certo no caminho feliz; aqui
tudo deve falhar no caminho errado.

Um teste por item da lista do PDF 7.2.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.perfis import PCP, PRODUCAO, QUALIDADE
from apps.auditoria.models import AcaoAuditoria, RegistroAuditoria, TrilhaImutavelError
from apps.auditoria.servicos import registrar_evento
from apps.cadastros.models import (
    Balanca,
    Cliente,
    Embalagem,
    Equipamento,
    Fornecedor,
    MateriaPrima,
    Produto,
    StatusEquipamento,
    VersaoArte,
)
from apps.estoque.models import (
    LocalEstoque,
    Lote,
    Movimentacao,
    SituacaoLote,
    TipoMovimentacao,
)
from apps.expedicao.models import registrar_expedicao
from apps.ordens.models import (
    ComponenteFormula,
    Formula,
    OrdemProducao,
    StatusFormula,
    StatusOP,
)
from apps.pedidos.models import ItemPedido, Pedido, StatusPedido
from apps.producao.models import (
    Desvio,
    ExecucaoOP,
    TipoDesvio,
    apontar_consumos,
    registrar_envase,
    registrar_pesagem,
)

User = get_user_model()
SENHA = "senha-forte-123"


def criar_usuario(username, perfil):
    usuario = User.objects.create_user(username=username, password=SENHA)
    usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class BaseViolacoes(TestCase):
    """Cenário mínimo e válido — cada teste estraga um ponto de propósito."""

    def setUp(self):
        self.hoje = timezone.localdate()
        self.operador = criar_usuario("viol.op", PRODUCAO)
        self.conferente = criar_usuario("viol.conf", PRODUCAO)
        self.qualidade = criar_usuario("viol.cq", QUALIDADE)
        self.pcp = criar_usuario("viol.pcp", PCP)

        self.fornecedor = Fornecedor.objects.create(razao_social="Insumos SA")
        self.cliente = Cliente.objects.create(razao_social="Cliente Teste")
        self.produto = Produto.objects.create(codigo="PA-V", nome="Creme", unidade="UN")
        self.mp = MateriaPrima.objects.create(codigo="MP-V", nome="Base", unidade="KG")
        self.embalagem = Embalagem.objects.create(
            codigo="EMB-V", nome="Rótulo", tipo="ROTULO", unidade="UN"
        )
        self.deposito = LocalEstoque.objects.create(nome="Almoxarifado")
        self.acabados = LocalEstoque.objects.create(nome="Acabados")
        self.equipamento = Equipamento.objects.create(
            codigo="EQ-V", nome="Misturador", ultima_limpeza=self.hoje
        )
        self.balanca = Balanca.objects.create(
            codigo="BAL-V", descricao="Bancada",
            calibracao_validade=self.hoje + timedelta(days=90),
        )
        self.arte = VersaoArte.objects.create(
            produto=self.produto, versao="v1", status="APROVADA"
        )
        self.formula = Formula.objects.create(
            produto=self.produto, nome="Padrão", rendimento=Decimal("100")
        )
        ComponenteFormula.objects.create(
            formula=self.formula, materia_prima=self.mp, quantidade=Decimal("50")
        )

        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            status=StatusPedido.PROGRAMADO,
            prazo=self.hoje + timedelta(days=15),
        )
        self.item_pedido = ItemPedido.objects.create(
            pedido=self.pedido, produto=self.produto, quantidade=Decimal("100")
        )
        self.lote_mp = Lote.objects.create(
            codigo="MP-2026-00001", materia_prima=self.mp,
            situacao=SituacaoLote.APROVADO,
            validade=self.hoje + timedelta(days=180),
        )
        self._entrada({"materia_prima": self.mp}, "100", self.lote_mp)

    def _entrada(self, item_kwargs, quantidade, lote, local=None):
        movimentacao = Movimentacao(
            tipo=TipoMovimentacao.ENTRADA,
            quantidade=Decimal(quantidade),
            local_destino=local or self.deposito,
            lote=lote,
            motivo="carga de teste",
            **item_kwargs,
        )
        movimentacao.full_clean()
        movimentacao.save()

    def _op_liberada(self, quantidade="100"):
        ordem = OrdemProducao.objects.create(
            item_pedido=self.item_pedido,
            formula=self.formula,
            quantidade=Decimal(quantidade),
            equipamento=self.equipamento,
            operador=self.operador,
            data_programada=self.hoje,
            status=StatusOP.LIBERADA,
        )
        ordem.gerar_materiais()
        return ordem


class ViolacoesTests(BaseViolacoes):
    """PDF 7.2 — um teste por bloqueio obrigatório."""

    # 1 ----------------------------------------------------------------
    def test_1_op_nao_conclui_com_material_sem_lote_apontado(self):
        """Material sem lote apontado não deixa concluir a produção."""
        ordem = self._op_liberada()
        execucao = ExecucaoOP.iniciar(ordem, self.operador)
        with self.assertRaises(ValidationError) as erro:
            execucao.concluir(
                usuario=self.operador,
                quantidade_produzida=Decimal("100"),
                perdas=Decimal("0"),
                validade=self.hoje + timedelta(days=365),
                local_destino=self.acabados,
            )
        self.assertIn("lote", " ".join(erro.exception.messages).lower())

    # 2 ----------------------------------------------------------------
    def test_2_lote_vencido_ou_reprovado_nao_pode_ser_consumido(self):
        ordem = self._op_liberada()
        material = ordem.materiais.get()

        for situacao in (SituacaoLote.REPROVADO, SituacaoLote.BLOQUEADO):
            with self.subTest(situacao=situacao):
                self.lote_mp.situacao = situacao
                self.lote_mp.save(update_fields=["situacao"])
                with self.assertRaises(ValidationError):
                    apontar_consumos(
                        ordem, self.operador,
                        [(material, self.lote_mp, self.deposito, Decimal("50"))],
                    )

        # Lote vencido também é barrado
        self.lote_mp.situacao = SituacaoLote.APROVADO
        self.lote_mp.validade = self.hoje - timedelta(days=1)
        self.lote_mp.save(update_fields=["situacao", "validade"])
        with self.assertRaises(ValidationError):
            apontar_consumos(
                ordem, self.operador,
                [(material, self.lote_mp, self.deposito, Decimal("50"))],
            )

    def test_2b_material_ainda_em_quarentena_nao_pode_ser_consumido(self):
        """“Em quarentena” é barrado pelo LOCAL: o saldo lá não é apontável."""
        from apps.recebimento.models import local_quarentena

        ordem = self._op_liberada()
        material = ordem.materiais.get()
        quarentena = local_quarentena()
        lote_novo = Lote.objects.create(
            codigo="MP-2026-00002", materia_prima=self.mp,
            situacao=SituacaoLote.AGUARDANDO_CQ,
            validade=self.hoje + timedelta(days=180),
        )
        self._entrada({"materia_prima": self.mp}, "80", lote_novo, quarentena)

        with self.assertRaises(ValidationError) as erro:
            apontar_consumos(
                ordem, self.operador,
                [(material, lote_novo, quarentena, Decimal("50"))],
            )
        self.assertIn("quarentena", " ".join(erro.exception.messages).lower())

    # 3 ----------------------------------------------------------------
    def test_3_formula_alterada_apos_op_nao_muda_o_que_foi_produzido(self):
        """Editar a fórmula gera nova versão; o snapshot da OP fica intacto."""
        self.client.force_login(self.pcp)
        # A OP precisa ser liberada pela tela: é a liberação que congela a fórmula
        ordem = OrdemProducao.objects.create(
            item_pedido=self.item_pedido,
            formula=self.formula,
            quantidade=Decimal("100"),
            equipamento=self.equipamento,
            operador=self.operador,
            data_programada=self.hoje,
        )
        ordem.gerar_materiais()
        self.client.post(f"/ordens/{ordem.pk}/liberar/")
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.LIBERADA, "OP não foi liberada")
        snapshot = ordem.snapshot_formula
        versao_congelada = snapshot.versao

        resposta = self.client.post(
            f"/ordens/formulas/{self.formula.pk}/editar/",
            {
                "produto": self.produto.pk,
                "nome": "Padrão",
                "rendimento": "120",
                "ativo": "on",
                "justificativa_auditoria": "Ajuste de rendimento após validação.",
                "componentes-TOTAL_FORMS": "1",
                "componentes-INITIAL_FORMS": "0",
                "componentes-MIN_NUM_FORMS": "0",
                "componentes-MAX_NUM_FORMS": "1000",
                "componentes-0-item": f"MP-{self.mp.pk}",
                "componentes-0-quantidade": "60",
                "etapas-TOTAL_FORMS": "0",
                "etapas-INITIAL_FORMS": "0",
                "etapas-MIN_NUM_FORMS": "0",
                "etapas-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertIn(resposta.status_code, (200, 302))

        # A versão original vira histórica e o snapshot da OP não muda
        self.formula.refresh_from_db()
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.versao, versao_congelada)
        if Formula.objects.filter(produto=self.produto).count() > 1:
            self.assertEqual(self.formula.status, StatusFormula.HISTORICA)

    # 4 ----------------------------------------------------------------
    def test_4_op_nao_conclui_sem_quantidade_final(self):
        ordem = self._op_liberada()
        material = ordem.materiais.get()
        apontar_consumos(
            ordem, self.operador,
            [(material, self.lote_mp, self.deposito, Decimal("50"))],
        )
        execucao = ExecucaoOP.iniciar(ordem, self.operador)
        with self.assertRaises((ValidationError, TypeError)):
            execucao.concluir(
                usuario=self.operador,
                quantidade_produzida=None,
                perdas=Decimal("0"),
                validade=self.hoje + timedelta(days=365),
                local_destino=self.acabados,
            )

    # 5 e 6 ------------------------------------------------------------
    def test_5_e_6_lote_sem_cq_nao_pode_ser_expedido(self):
        """Liberação sem CQ e expedição de lote não liberado."""
        lote_pa = Lote.objects.create(
            codigo="PA-2026-00001", produto=self.produto,
            situacao=SituacaoLote.AGUARDANDO_CQ,
        )
        self._entrada({"produto": self.produto}, "100", lote_pa, self.acabados)

        with self.assertRaises(ValidationError) as erro:
            registrar_expedicao(
                pedido=self.pedido,
                data=self.hoje,
                usuario=self.qualidade,
                linhas=[(self.item_pedido, lote_pa, Decimal("100"))],
            )
        self.assertIn("liberado", " ".join(erro.exception.messages).lower())

        # E o pedido não vai a EXPEDIDO sem nenhuma expedição registrada
        from apps.pedidos.models import TransicaoInvalida

        self.pedido.status = StatusPedido.FINALIZADO
        self.pedido.save(update_fields=["status"])
        with self.assertRaises(TransicaoInvalida):
            self.pedido.transicionar(StatusPedido.EXPEDIDO, self.qualidade)

    # 7 ----------------------------------------------------------------
    def test_7_balanca_com_calibracao_vencida_nao_pesa(self):
        self.balanca.calibracao_validade = self.hoje - timedelta(days=1)
        self.balanca.save(update_fields=["calibracao_validade"])
        ordem = self._op_liberada()
        material = ordem.materiais.get()

        with self.assertRaises(ValidationError) as erro:
            registrar_pesagem(
                material=material,
                lote=self.lote_mp,
                balanca=self.balanca,
                quantidade_pesada=material.quantidade_necessaria,
                tolerancia_percentual=Decimal("2"),
                operador=self.operador,
                conferente=self.conferente,
            )
        self.assertIn("calibração vencida", " ".join(erro.exception.messages))

    # 8 ----------------------------------------------------------------
    def test_8_equipamento_sem_limpeza_ou_interditado_nao_libera_op(self):
        for ajuste, rotulo in [
            ({"ultima_limpeza": None}, "sem limpeza"),
            ({"status": StatusEquipamento.INTERDITADO}, "interditado"),
        ]:
            with self.subTest(caso=rotulo):
                Equipamento.objects.filter(pk=self.equipamento.pk).update(**ajuste)
                self.equipamento.refresh_from_db()
                self.assertFalse(
                    self.equipamento.pode_ser_usado(),
                    f"equipamento {rotulo} deveria estar impedido",
                )
                self.assertIn(rotulo.split()[0], self.equipamento.motivo_impedimento_uso().lower())
                # devolve ao estado bom para o próximo subteste
                Equipamento.objects.filter(pk=self.equipamento.pk).update(
                    ultima_limpeza=self.hoje, status=StatusEquipamento.LIBERADO
                )

    # 9 ----------------------------------------------------------------
    def test_9_rotulo_com_arte_nao_aprovada_e_barrado(self):
        ordem = self._op_liberada()
        self.arte.status = "OBSOLETA"
        self.arte.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            registrar_envase(
                ordem=ordem,
                versao_arte=self.arte,
                quantidade_envasada=Decimal("100"),
                operador=self.operador,
            )

        # E o rótulo vinculado à arte obsoleta não pode ser consumido
        self.embalagem.versao_arte = self.arte
        self.embalagem.save(update_fields=["versao_arte"])
        self.assertIn("obsoleta", self.embalagem.motivo_arte_invalida())

    # 10 ---------------------------------------------------------------
    def test_10_op_nao_encerra_com_desvio_pendente(self):
        ordem = self._op_liberada()
        material = ordem.materiais.get()
        apontar_consumos(
            ordem, self.operador,
            [(material, self.lote_mp, self.deposito, Decimal("50"))],
        )
        execucao = ExecucaoOP.iniciar(ordem, self.operador)
        Desvio.objects.create(
            ordem=ordem,
            tipo=TipoDesvio.PROCESSO,
            descricao="Desvio ainda em avaliação.",
            responsavel=self.operador,
        )
        with self.assertRaises(ValidationError) as erro:
            execucao.concluir(
                usuario=self.operador,
                quantidade_produzida=Decimal("100"),
                perdas=Decimal("0"),
                validade=self.hoje + timedelta(days=365),
                local_destino=self.acabados,
            )
        self.assertIn("desvio", " ".join(erro.exception.messages).lower())

    # 11 ---------------------------------------------------------------
    def test_11_registro_de_auditoria_nao_pode_ser_editado_nem_excluido(self):
        registro = registrar_evento(
            self.lote_mp,
            AcaoAuditoria.ALTERACAO,
            self.qualidade,
            campo="situacao",
            valor_anterior="AGUARDANDO_CQ",
            valor_novo="APROVADO",
        )
        registro.valor_novo = "adulterado"
        with self.assertRaises(TrilhaImutavelError):
            registro.save()
        with self.assertRaises(TrilhaImutavelError):
            registro.delete()
        with self.assertRaises(TrilhaImutavelError):
            RegistroAuditoria.objects.all().delete()
        with self.assertRaises(TrilhaImutavelError):
            RegistroAuditoria.objects.all().update(valor_novo="adulterado")

    # 12 ---------------------------------------------------------------
    def test_12_alterar_lote_interno_exige_justificativa(self):
        """`codigo`, `lote_fornecedor` e `validade` são campos críticos."""
        from apps.auditoria.campos_criticos import campos_criticos_do_modelo

        criticos = campos_criticos_do_modelo(Lote)
        self.assertIn("codigo", criticos)
        self.assertIn("lote_fornecedor", criticos)
        self.assertIn("validade", criticos)

        # Alterar pelo fluxo auditado grava a justificativa na trilha
        self.lote_mp.codigo = "MP-2026-99999"
        self.lote_mp.salvar_com_usuario(
            self.qualidade, justificativa="Correção do lote impresso na etiqueta."
        )
        # A trilha grava o rótulo do campo (verbose_name), não o nome interno
        alteracoes = RegistroAuditoria.objects.filter(
            campo="lote interno", acao=AcaoAuditoria.ALTERACAO
        )
        self.assertTrue(alteracoes.exists(), "alteração do lote não foi para a trilha")
        self.assertIn("Correção", alteracoes.first().justificativa)
