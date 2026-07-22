from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import PCP, PRODUCAO
from apps.cadastros.models import (
    Cliente,
    Equipamento,
    MateriaPrima,
    Produto,
    Setor,
)
from apps.estoque.models import LocalEstoque, Movimentacao, TipoMovimentacao
from apps.pedidos.models import ItemPedido, Pedido, StatusPedido
from apps.recebimento.models import local_quarentena

from .models import (
    ComponenteFormula,
    Formula,
    OrdemProducao,
    SnapshotFormulaOP,
    StatusFormula,
    StatusOP,
    saldo_disponivel,
)

User = get_user_model()


def criar_usuario(username, perfil=None, senha="senha-forte-123"):
    usuario = User.objects.create_user(username=username, password=senha)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


def entrada_estoque(item_kwargs, quantidade, local):
    movimentacao = Movimentacao(
        tipo=TipoMovimentacao.ENTRADA,
        quantidade=Decimal(quantidade),
        local_destino=local,
        motivo="carga de teste",
        **item_kwargs,
    )
    movimentacao.full_clean()
    movimentacao.save()
    return movimentacao


class BaseOrdens(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("pcp", perfil=PCP)
        self.client.login(username="pcp", password="senha-forte-123")

        self.cliente = Cliente.objects.create(razao_social="Loja Bela Pele LTDA")
        self.produto = Produto.objects.create(
            codigo="PA-1", nome="Perfume Lavanda", unidade="UN"
        )
        self.mp = MateriaPrima.objects.create(
            codigo="MP-1", nome="Essência de lavanda", unidade="L"
        )
        self.equipamento = Equipamento.objects.create(
            codigo="EQ-1",
            nome="Envasadora",
            ultima_limpeza=timezone.localdate(),
        )
        self.deposito = LocalEstoque.objects.create(nome="Almoxarifado MP")

        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            status=StatusPedido.PROGRAMADO,
            prazo=timezone.localdate() + timedelta(days=15),
        )
        self.item_pedido = ItemPedido.objects.create(
            pedido=self.pedido, produto=self.produto, quantidade=Decimal("100")
        )

        # Fórmula: para render 100 UN do produto usa 40 L de essência
        self.formula = Formula.objects.create(
            produto=self.produto, nome="Padrão", rendimento=Decimal("100")
        )
        ComponenteFormula.objects.create(
            formula=self.formula, materia_prima=self.mp, quantidade=Decimal("40")
        )

    def dados_op(self, **kwargs):
        dados = {
            "item_pedido": self.item_pedido.pk,
            "formula": self.formula.pk,
            "quantidade": "50",
            "equipamento": str(self.equipamento.pk),
            "operador": str(self.usuario.pk),
            "data_programada": (timezone.localdate() + timedelta(days=3)).isoformat(),
            "observacoes": "",
        }
        dados.update(kwargs)
        return dados

    def criar_op(self, **kwargs):
        self.client.post(reverse("ordens:criar"), self.dados_op(**kwargs))
        return OrdemProducao.objects.latest("id")


class FormulaTests(BaseOrdens):
    def dados_formula(self, **kwargs):
        dados = {
            "produto": self.produto.pk,
            "nome": "v2",
            "rendimento": "100",
            "observacoes": "",
            "ativo": "on",
            "componentes-TOTAL_FORMS": "1",
            "componentes-INITIAL_FORMS": "0",
            "componentes-MIN_NUM_FORMS": "0",
            "componentes-MAX_NUM_FORMS": "1000",
            "etapas-TOTAL_FORMS": "0",
            "etapas-INITIAL_FORMS": "0",
            "etapas-MIN_NUM_FORMS": "0",
            "etapas-MAX_NUM_FORMS": "1000",
            "componentes-0-item": f"MP-{self.mp.pk}",
            "componentes-0-quantidade": "40",
        }
        dados.update(kwargs)
        return dados

    def test_criar_formula_com_componentes(self):
        response = self.client.post(
            reverse("ordens:formula_criar"), self.dados_formula()
        )
        self.assertRedirects(response, reverse("ordens:formula_lista"))
        formula = Formula.objects.get(nome="v2")
        self.assertEqual(formula.componentes.count(), 1)
        self.assertEqual(formula.criado_por, self.usuario)

    def test_formula_sem_componentes_e_rejeitada(self):
        response = self.client.post(
            reverse("ordens:formula_criar"),
            self.dados_formula(
                **{"componentes-0-item": "", "componentes-0-quantidade": ""}
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pelo menos um material")

    def test_componente_duplicado_e_rejeitado(self):
        dados = self.dados_formula(
            **{
                "componentes-TOTAL_FORMS": "2",
                "componentes-1-item": f"MP-{self.mp.pk}",
                "componentes-1-quantidade": "10",
            }
        )
        response = self.client.post(reverse("ordens:formula_criar"), dados)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "já está na fórmula")


class IdentificacaoOPTests(BaseOrdens):
    """Etapa 6a: linha, supervisor, prazo e regra de cliente/produto ativos."""

    def test_op_grava_linha_supervisor_prazo(self):
        setor = Setor.objects.create(nome="Linha 1")
        prazo = (timezone.localdate() + timedelta(days=10)).isoformat()
        self.criar_op(
            linha=str(setor.pk),
            supervisor=str(self.usuario.pk),
            prazo=prazo,
        )
        ordem = OrdemProducao.objects.latest("id")
        self.assertEqual(ordem.linha, setor)
        self.assertEqual(ordem.supervisor, self.usuario)
        self.assertEqual(ordem.prazo.isoformat(), prazo)

        response = self.client.get(reverse("ordens:detalhe", args=[ordem.pk]))
        self.assertContains(response, "Linha 1")
        self.assertContains(response, "Supervisor")

    def test_produto_inativo_impede_emitir_op(self):
        self.produto.ativo = False
        self.produto.save()
        response = self.client.post(reverse("ordens:criar"), self.dados_op())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "está inativo")
        self.assertEqual(OrdemProducao.objects.count(), 0)

    def test_cliente_inativo_impede_emitir_op(self):
        self.cliente.ativo = False
        self.cliente.save()
        response = self.client.post(reverse("ordens:criar"), self.dados_op())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "está inativo")
        self.assertEqual(OrdemProducao.objects.count(), 0)


class BloqueioOPProdutoTests(BaseOrdens):
    """Etapa 10: produto/cliente bloqueado ou sem regularização não gera OP."""

    def test_produto_bloqueado_impede_emitir_op(self):
        self.produto.bloqueado = True
        self.produto.motivo_bloqueio = "Reclamação em apuração"
        self.produto.save()
        response = self.client.post(reverse("ordens:criar"), self.dados_op())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bloqueado")
        self.assertEqual(OrdemProducao.objects.count(), 0)

    def test_produto_sem_regularizacao_impede_emitir_op(self):
        self.produto.situacao_regulatoria = "VENCIDO"
        self.produto.save()
        response = self.client.post(reverse("ordens:criar"), self.dados_op())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "sem regularização")
        self.assertEqual(OrdemProducao.objects.count(), 0)

    def test_cliente_bloqueado_impede_emitir_op(self):
        self.cliente.bloqueado = True
        self.cliente.save()
        response = self.client.post(reverse("ordens:criar"), self.dados_op())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bloqueado")
        self.assertEqual(OrdemProducao.objects.count(), 0)

    def test_produto_isento_gera_op(self):
        self.produto.situacao_regulatoria = "ISENTO"
        self.produto.save()
        self.client.post(reverse("ordens:criar"), self.dados_op())
        self.assertEqual(OrdemProducao.objects.count(), 1)


class VersionamentoFormulaTests(BaseOrdens):
    """Etapa 3: editar fórmula com OP emitida gera nova versão."""

    def dados_edicao(self, **kwargs):
        componente = self.formula.componentes.get()
        dados = {
            "produto": self.produto.pk,
            "nome": "Padrão",
            "rendimento": "100",
            "observacoes": "",
            "ativo": "on",
            "justificativa_alteracao": "",
            "componentes-TOTAL_FORMS": "1",
            "componentes-INITIAL_FORMS": "1",
            "componentes-MIN_NUM_FORMS": "0",
            "componentes-MAX_NUM_FORMS": "1000",
            "etapas-TOTAL_FORMS": "0",
            "etapas-INITIAL_FORMS": "0",
            "etapas-MIN_NUM_FORMS": "0",
            "etapas-MAX_NUM_FORMS": "1000",
            "componentes-0-id": str(componente.pk),
            "componentes-0-item": f"MP-{self.mp.pk}",
            "componentes-0-quantidade": "40",
        }
        dados.update(kwargs)
        return dados

    def editar_formula(self, **kwargs):
        return self.client.post(
            reverse("ordens:formula_editar", args=[self.formula.pk]),
            self.dados_edicao(**kwargs),
        )

    def test_editar_sem_op_altera_em_vigor(self):
        response = self.editar_formula(
            rendimento="120", justificativa_alteracao="Ajuste"
        )
        self.assertRedirects(response, reverse("ordens:formula_lista"))

        self.assertEqual(Formula.objects.count(), 1)
        self.formula.refresh_from_db()
        self.assertEqual(self.formula.rendimento, Decimal("120"))
        self.assertEqual(self.formula.versao, 1)
        self.assertEqual(self.formula.status, StatusFormula.VIGENTE)
        self.assertEqual(self.formula.aprovada_por, self.usuario)

    def test_editar_com_op_gera_nova_versao_e_preserva_a_antiga(self):
        """Critério de aceite do PDF (2.4/4.2)."""
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.criar_op(quantidade="50")
        material_original = ordem.materiais.get().quantidade_necessaria

        response = self.editar_formula(
            rendimento="50",
            justificativa_alteracao="Reduzir batelada e concentrar essência",
            **{"componentes-0-quantidade": "30"},
        )
        self.assertRedirects(response, reverse("ordens:formula_lista"))

        # Duas versões: a antiga intacta e histórica, a nova vigente
        self.assertEqual(Formula.objects.count(), 2)
        self.formula.refresh_from_db()
        self.assertEqual(self.formula.versao, 1)
        self.assertEqual(self.formula.status, StatusFormula.HISTORICA)
        self.assertEqual(self.formula.rendimento, Decimal("100"))
        self.assertEqual(
            self.formula.componentes.get().quantidade, Decimal("40")
        )

        nova = Formula.objects.get(versao=2)
        self.assertEqual(nova.status, StatusFormula.VIGENTE)
        self.assertEqual(nova.rendimento, Decimal("50"))
        self.assertEqual(nova.componentes.get().quantidade, Decimal("30"))
        self.assertEqual(nova.aprovada_por, self.usuario)
        self.assertIsNotNone(nova.aprovada_em)

        # A OP antiga continua na v1, com o snapshot de materiais original
        ordem.refresh_from_db()
        self.assertEqual(ordem.formula, self.formula)
        self.assertEqual(
            ordem.materiais.get().quantidade_necessaria, material_original
        )

        # Trilha registra o versionamento na versão antiga
        from apps.auditoria.models import AcaoAuditoria
        from apps.auditoria.servicos import trilha_de

        evento = trilha_de(self.formula).filter(
            acao=AcaoAuditoria.ALTERACAO, campo="versão"
        ).get()
        self.assertIn("v2", evento.valor_novo)
        self.assertEqual(
            evento.justificativa, "Reduzir batelada e concentrar essência"
        )

    def test_versionar_exige_justificativa_mesmo_so_nos_componentes(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        self.criar_op(quantidade="50")

        response = self.editar_formula(**{"componentes-0-quantidade": "35"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "nova versão da fórmula")
        self.assertEqual(Formula.objects.count(), 1)
        self.assertEqual(
            self.formula.componentes.get().quantidade, Decimal("40")
        )

    def test_nova_op_usa_somente_a_versao_vigente(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        self.criar_op(quantidade="50")
        self.editar_formula(
            rendimento="50", justificativa_alteracao="Nova escala"
        )
        nova = Formula.objects.get(versao=2)

        response = self.client.get(reverse("ordens:criar"))
        form = response.context["form"]
        formulas_disponiveis = set(
            form.fields["formula"].queryset.values_list("pk", flat=True)
        )
        self.assertIn(nova.pk, formulas_disponiveis)
        self.assertNotIn(self.formula.pk, formulas_disponiveis)

        ordem_nova = self.criar_op(formula=str(nova.pk), quantidade="25")
        self.assertEqual(ordem_nova.formula, nova)

    def test_formula_historica_nao_pode_ser_editada(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        self.criar_op(quantidade="50")
        self.editar_formula(
            rendimento="50", justificativa_alteracao="Nova escala"
        )
        self.formula.refresh_from_db()
        self.assertEqual(self.formula.status, StatusFormula.HISTORICA)

        response = self.client.get(
            reverse("ordens:formula_editar", args=[self.formula.pk])
        )
        self.assertRedirects(response, reverse("ordens:formula_lista"))

    def test_produto_nao_muda_em_formula_com_op(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        self.criar_op(quantidade="50")
        outro_produto = Produto.objects.create(codigo="PA-9", nome="Outro")

        response = self.editar_formula(
            produto=outro_produto.pk, justificativa_alteracao="tentativa"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "o produto não pode ser")
        self.assertEqual(Formula.objects.count(), 1)


class SnapshotFormulaTests(BaseOrdens):
    """Etapa 3: a liberação da OP congela a fórmula (versão + composição)."""

    def liberar_op(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.criar_op(quantidade="50")
        self.client.post(reverse("ordens:liberar", args=[ordem.pk]))
        ordem.refresh_from_db()
        return ordem

    def test_liberacao_congela_versao_e_composicao(self):
        ordem = self.liberar_op()

        snapshot = ordem.snapshot_formula
        self.assertEqual(snapshot.nome, "Padrão")
        self.assertEqual(snapshot.versao, 1)
        self.assertEqual(snapshot.rendimento, Decimal("100"))
        self.assertEqual(snapshot.congelado_por, self.usuario)

        item = snapshot.itens.get()
        self.assertEqual(item.item_codigo, "MP-1")
        self.assertEqual(item.quantidade_teorica, Decimal("40"))
        self.assertEqual(item.quantidade_escalada, Decimal("20"))

    def test_snapshot_nao_muda_quando_a_formula_muda(self):
        ordem = self.liberar_op()

        componente = self.formula.componentes.get()
        self.client.post(
            reverse("ordens:formula_editar", args=[self.formula.pk]),
            {
                "produto": self.produto.pk,
                "nome": "Padrão",
                "rendimento": "50",
                "observacoes": "",
                "ativo": "on",
                "justificativa_alteracao": "Nova escala",
                "componentes-TOTAL_FORMS": "1",
                "componentes-INITIAL_FORMS": "1",
                "componentes-MIN_NUM_FORMS": "0",
                "componentes-MAX_NUM_FORMS": "1000",
                "etapas-TOTAL_FORMS": "0",
                "etapas-INITIAL_FORMS": "0",
                "etapas-MIN_NUM_FORMS": "0",
                "etapas-MAX_NUM_FORMS": "1000",
                "componentes-0-id": str(componente.pk),
                "componentes-0-item": f"MP-{self.mp.pk}",
                "componentes-0-quantidade": "10",
            },
        )
        self.assertEqual(Formula.objects.count(), 2)

        snapshot = SnapshotFormulaOP.objects.get(ordem=ordem)
        self.assertEqual(snapshot.versao, 1)
        self.assertEqual(snapshot.rendimento, Decimal("100"))
        self.assertEqual(
            snapshot.itens.get().quantidade_teorica, Decimal("40")
        )

        response = self.client.get(reverse("ordens:detalhe", args=[ordem.pk]))
        self.assertContains(response, "Versão congelada")
        self.assertContains(response, "v1")

    def test_snapshot_e_imutavel(self):
        from apps.auditoria.models import TrilhaImutavelError

        ordem = self.liberar_op()
        snapshot = ordem.snapshot_formula

        snapshot.rendimento = Decimal("999")
        with self.assertRaises(TrilhaImutavelError):
            snapshot.save()
        with self.assertRaises(TrilhaImutavelError):
            snapshot.delete()
        with self.assertRaises(TrilhaImutavelError):
            SnapshotFormulaOP.objects.all().update(rendimento=Decimal("999"))
        with self.assertRaises(TrilhaImutavelError):
            snapshot.itens.all().delete()


class EmissaoOPTests(BaseOrdens):
    def test_op_gera_materiais_escalados(self):
        ordem = self.criar_op(quantidade="50")
        material = ordem.materiais.get()
        # 40 L para 100 UN → 20 L para 50 UN
        self.assertEqual(material.quantidade_necessaria, Decimal("20"))
        self.assertEqual(material.materia_prima, self.mp)
        self.assertEqual(ordem.status, StatusOP.RASCUNHO)
        self.assertIn(
            "Ordem de produção",
            self.pedido.historico.first().descricao,
        )

    def test_editar_recalcula_materiais(self):
        ordem = self.criar_op(quantidade="50")
        self.client.post(
            reverse("ordens:editar", args=[ordem.pk]),
            # Quantidade é campo crítico: a edição exige justificativa
            self.dados_op(
                quantidade="100",
                justificativa_alteracao="Cliente dobrou o pedido",
            ),
        )
        material = ordem.materiais.get()
        self.assertEqual(material.quantidade_necessaria, Decimal("40"))

    def test_formula_de_outro_produto_e_rejeitada(self):
        outro_produto = Produto.objects.create(codigo="PA-2", nome="Sabonete")
        formula_errada = Formula.objects.create(
            produto=outro_produto, nome="Padrão", rendimento=Decimal("100")
        )
        ComponenteFormula.objects.create(
            formula=formula_errada, materia_prima=self.mp, quantidade=Decimal("10")
        )
        response = self.client.post(
            reverse("ordens:criar"), self.dados_op(formula=formula_errada.pk)
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mas o item do pedido é")
        self.assertEqual(OrdemProducao.objects.count(), 0)


class LiberacaoTests(BaseOrdens):
    def liberar(self, ordem):
        return self.client.post(reverse("ordens:liberar", args=[ordem.pk]))

    def test_libera_com_todas_as_condicoes(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.criar_op(quantidade="50")  # precisa de 20 L

        self.liberar(ordem)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.LIBERADA)
        self.assertEqual(ordem.liberado_por, self.usuario)
        self.assertIsNotNone(ordem.liberado_em)
        descricoes = [h.descricao for h in ordem.historico.all()]
        self.assertTrue(any("liberada" in d for d in descricoes))

    def test_liberacao_reserva_lote_interno_do_produto(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.criar_op(quantidade="50")
        self.assertIsNone(ordem.lote_produto)

        self.liberar(ordem)
        ordem.refresh_from_db()
        self.assertIsNotNone(ordem.lote_produto)
        self.assertRegex(ordem.lote_produto.codigo, r"^PA-\d{4}-00001$")
        self.assertEqual(ordem.lote_produto.produto, ordem.produto)

        # A reserva aparece no histórico e na tela de detalhe
        descricoes = [h.descricao for h in ordem.historico.all()]
        self.assertTrue(any(ordem.lote_produto.codigo in d for d in descricoes))
        response = self.client.get(reverse("ordens:detalhe", args=[ordem.pk]))
        self.assertContains(response, ordem.lote_produto.codigo)

        # E gera as atividades "Liberação" e "Atribuição de lote" (Etapa 2c)
        from apps.producao.models import TipoAtividadeOP

        atividades = list(ordem.atividades.values_list("atividade", flat=True))
        self.assertIn(TipoAtividadeOP.LIBERACAO, atividades)
        self.assertIn(TipoAtividadeOP.ATRIBUICAO_LOTE, atividades)
        self.assertContains(response, "Quem fez o quê")

    def test_nao_libera_sem_estoque(self):
        entrada_estoque({"materia_prima": self.mp}, "10", self.deposito)  # < 20
        ordem = self.criar_op(quantidade="50")

        self.liberar(ordem)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.RASCUNHO)

    def test_saldo_em_quarentena_nao_conta(self):
        # 30 L existem, mas SÓ na quarentena: MP não liberada pela Qualidade
        entrada_estoque({"materia_prima": self.mp}, "30", local_quarentena())
        ordem = self.criar_op(quantidade="50")

        self.assertEqual(saldo_disponivel(self.mp), Decimal("0"))
        self.liberar(ordem)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.RASCUNHO)

        condicoes = {c["rotulo"]: c["ok"] for c in ordem.condicoes_liberacao()}
        self.assertFalse(condicoes["Estoque liberado de MP-1"])

    def test_nao_libera_sem_equipamento_ou_operador(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.criar_op(equipamento="", operador="")

        self.liberar(ordem)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.RASCUNHO)

    def test_nao_libera_com_pedido_encerrado(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.criar_op()
        self.pedido.status = StatusPedido.CANCELADO
        self.pedido.save()

        self.liberar(ordem)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.RASCUNHO)

    def test_op_liberada_trava_edicao(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.criar_op()
        self.liberar(ordem)

        response = self.client.get(reverse("ordens:editar", args=[ordem.pk]))
        self.assertRedirects(response, reverse("ordens:detalhe", args=[ordem.pk]))

    def test_equipamento_em_manutencao_impede_liberacao(self):
        """Etapa 6c: equipamento inapto bloqueia a liberação."""
        from apps.cadastros.models import StatusEquipamento

        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.criar_op(quantidade="50")
        self.equipamento.status = StatusEquipamento.MANUTENCAO
        self.equipamento.save()

        self.liberar(ordem)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.RASCUNHO)

        condicoes = {c["rotulo"]: c for c in ordem.condicoes_liberacao()}
        cond = condicoes["Equipamento em condição de uso"]
        self.assertFalse(cond["ok"])
        self.assertIn("manutenção", cond["detalhe"])

    def test_equipamento_sem_limpeza_impede_liberacao(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.criar_op(quantidade="50")
        self.equipamento.ultima_limpeza = None
        self.equipamento.save()

        self.liberar(ordem)
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.RASCUNHO)


class CancelamentoTests(BaseOrdens):
    def test_cancelar_exige_motivo(self):
        ordem = self.criar_op()
        self.client.post(reverse("ordens:cancelar", args=[ordem.pk]), {"motivo": ""})
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.RASCUNHO)

        self.client.post(
            reverse("ordens:cancelar", args=[ordem.pk]),
            {"motivo": "Pedido renegociado"},
        )
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.CANCELADA)
        self.assertEqual(ordem.motivo_cancelamento, "Pedido renegociado")

    def test_op_cancelada_nao_libera(self):
        entrada_estoque({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.criar_op()
        self.client.post(
            reverse("ordens:cancelar", args=[ordem.pk]), {"motivo": "cancelada"}
        )
        self.client.post(reverse("ordens:liberar", args=[ordem.pk]))
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.CANCELADA)


class TelasTests(BaseOrdens):
    def test_detalhe_mostra_checklist(self):
        ordem = self.criar_op(equipamento="")
        response = self.client.get(reverse("ordens:detalhe", args=[ordem.pk]))
        self.assertContains(response, "Checklist de liberação")
        self.assertContains(response, "Equipamento definido")
        self.assertContains(response, "Estoque liberado de MP-1")

    def test_impressao_renderiza(self):
        ordem = self.criar_op()
        response = self.client.get(reverse("ordens:imprimir", args=[ordem.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ordem.numero)
        self.assertContains(response, "Materiais necessários")
        self.assertContains(response, "Operador")


class PermissoesTests(TestCase):
    def setUp(self):
        criar_usuario("pcp", perfil=PCP)
        criar_usuario("operador", perfil=PRODUCAO)

    def test_producao_nao_acessa_ordens(self):
        self.client.login(username="operador", password="senha-forte-123")
        for rota in ["ordens:lista", "ordens:criar", "ordens:formula_lista"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 403)

    def test_pcp_acessa_ordens(self):
        self.client.login(username="pcp", password="senha-forte-123")
        for rota in ["ordens:lista", "ordens:criar", "ordens:formula_lista"]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse(rota)).status_code, 200)
