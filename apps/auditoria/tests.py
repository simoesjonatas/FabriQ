"""
Testes da trilha de auditoria (Etapa 1 do plano de correções).

Critério de aceite do PDF (2.3/7.1): alterar um campo e confirmar que o
sistema registra automaticamente valor anterior, valor novo, usuário,
data, hora e motivo; a trilha não pode ser alterada nem excluída.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.accounts.perfis import PCP
from apps.cadastros.models import Cliente, MateriaPrima, Produto
from apps.ordens.models import ComponenteFormula, Formula, OrdemProducao
from apps.pedidos.models import ItemPedido, Pedido, StatusPedido

from .models import AcaoAuditoria, RegistroAuditoria, TrilhaImutavelError
from .servicos import registrar_alteracoes, trilha_de

User = get_user_model()
SENHA = "senha-forte-123"


def criar_usuario(username, perfil=None):
    usuario = User.objects.create_user(username=username, password=SENHA)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


class BaseAuditoria(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("pcp", perfil=PCP)
        self.client.login(username="pcp", password=SENHA)

        self.produto = Produto(codigo="P-1", nome="Shampoo Lavanda")
        self.produto.salvar_com_usuario(self.usuario)
        self.mp = MateriaPrima(codigo="MP-1", nome="Essência de lavanda")
        self.mp.salvar_com_usuario(self.usuario)

        self.formula = Formula(
            produto=self.produto, nome="Padrão", rendimento=Decimal("10")
        )
        self.formula.salvar_com_usuario(self.usuario)
        ComponenteFormula.objects.create(
            formula=self.formula, materia_prima=self.mp, quantidade=Decimal("2")
        )

    def dados_formula(self, **kwargs):
        """POST completo da tela de fórmula (form + formset de componentes)."""
        componente = self.formula.componentes.get()
        dados = {
            "produto": str(self.produto.pk),
            "nome": "Padrão",
            "rendimento": "10",
            "observacoes": "",
            "ativo": "on",
            "justificativa_alteracao": "",
            "componentes-TOTAL_FORMS": "1",
            "componentes-INITIAL_FORMS": "1",
            "componentes-MIN_NUM_FORMS": "0",
            "componentes-MAX_NUM_FORMS": "1000",
            "componentes-0-id": str(componente.pk),
            "componentes-0-item": f"MP-{self.mp.pk}",
            "componentes-0-quantidade": "2",
            "etapas-TOTAL_FORMS": "0",
            "etapas-INITIAL_FORMS": "0",
            "etapas-MIN_NUM_FORMS": "0",
            "etapas-MAX_NUM_FORMS": "1000",
        }
        dados.update(kwargs)
        return dados


class TrilhaAutomaticaTests(BaseAuditoria):
    def test_criacao_registra_na_trilha(self):
        registro = trilha_de(self.formula).get()
        self.assertEqual(registro.acao, AcaoAuditoria.CRIACAO)
        self.assertEqual(registro.usuario, self.usuario)
        self.assertIn("Padrão", registro.objeto_repr)

    def test_alteracao_grava_valor_anterior_novo_usuario_e_motivo(self):
        self.formula.rendimento = Decimal("12")
        self.formula.salvar_com_usuario(self.usuario, justificativa="Ajuste de escala")

        registro = trilha_de(self.formula).filter(acao=AcaoAuditoria.ALTERACAO).get()
        self.assertEqual(registro.campo, "rendimento")
        self.assertEqual(registro.valor_anterior, "10")
        self.assertEqual(registro.valor_novo, "12")
        self.assertEqual(registro.usuario, self.usuario)
        self.assertEqual(registro.justificativa, "Ajuste de escala")
        self.assertIsNotNone(registro.data)

    def test_um_registro_por_campo_alterado(self):
        self.formula.nome = "Padrão v2"
        self.formula.rendimento = Decimal("15")
        self.formula.salvar_com_usuario(self.usuario, justificativa="Revisão")

        alteracoes = trilha_de(self.formula).filter(acao=AcaoAuditoria.ALTERACAO)
        self.assertEqual(alteracoes.count(), 2)
        self.assertEqual(
            {registro.campo for registro in alteracoes}, {"nome", "rendimento"}
        )

    def test_inativacao_tem_acao_propria(self):
        self.formula.ativo = False
        self.formula.salvar_com_usuario(self.usuario, justificativa="Descontinuada")

        registro = trilha_de(self.formula).filter(acao=AcaoAuditoria.INATIVACAO).get()
        self.assertEqual(registro.campo, "ativo")
        self.assertEqual(registro.valor_anterior, "Sim")
        self.assertEqual(registro.valor_novo, "Não")

    def test_salvar_sem_alteracao_nao_gera_registro(self):
        self.formula.salvar_com_usuario(self.usuario)
        self.assertEqual(
            trilha_de(self.formula).exclude(acao=AcaoAuditoria.CRIACAO).count(), 0
        )

    def test_registrar_alteracoes_compara_campo_a_campo(self):
        antiga = Formula.objects.get(pk=self.formula.pk)
        self.formula.rendimento = Decimal("20")
        registros = registrar_alteracoes(
            antiga, self.formula, self.usuario, justificativa="Teste direto"
        )
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0].campo, "rendimento")


class ImutabilidadeTests(BaseAuditoria):
    def setUp(self):
        super().setUp()
        self.registro = trilha_de(self.formula).get()

    def test_update_de_registro_falha(self):
        self.registro.justificativa = "adulterada"
        with self.assertRaises(TrilhaImutavelError):
            self.registro.save()

    def test_delete_de_registro_falha(self):
        with self.assertRaises(TrilhaImutavelError):
            self.registro.delete()

    def test_update_em_massa_falha(self):
        with self.assertRaises(TrilhaImutavelError):
            RegistroAuditoria.objects.all().update(justificativa="x")

    def test_delete_em_massa_falha(self):
        with self.assertRaises(TrilhaImutavelError):
            RegistroAuditoria.objects.all().delete()

    def test_admin_somente_leitura(self):
        from django.contrib.admin.sites import site

        admin_registro = site._registry[RegistroAuditoria]
        self.assertFalse(admin_registro.has_add_permission(None))
        self.assertFalse(admin_registro.has_change_permission(None))
        self.assertFalse(admin_registro.has_delete_permission(None))


class JustificativaObrigatoriaTests(BaseAuditoria):
    def test_alterar_campo_critico_sem_justificativa_bloqueia(self):
        response = self.client.post(
            reverse("ordens:formula_editar", args=[self.formula.pk]),
            self.dados_formula(rendimento="12"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informe a justificativa")

        self.formula.refresh_from_db()
        self.assertEqual(self.formula.rendimento, Decimal("10"))
        self.assertEqual(
            trilha_de(self.formula).filter(acao=AcaoAuditoria.ALTERACAO).count(), 0
        )

    def test_alterar_campo_critico_com_justificativa_grava_trilha(self):
        response = self.client.post(
            reverse("ordens:formula_editar", args=[self.formula.pk]),
            self.dados_formula(
                rendimento="12", justificativa_alteracao="Nova escala de produção"
            ),
        )
        self.assertRedirects(response, reverse("ordens:formula_lista"))

        self.formula.refresh_from_db()
        self.assertEqual(self.formula.rendimento, Decimal("12"))

        # A tela também grava "aprovada por/em" — filtra o campo crítico
        registro = trilha_de(self.formula).filter(
            acao=AcaoAuditoria.ALTERACAO, campo="rendimento"
        ).get()
        self.assertEqual(registro.valor_anterior, "10")
        self.assertEqual(registro.valor_novo, "12")
        self.assertEqual(registro.usuario, self.usuario)
        self.assertEqual(registro.justificativa, "Nova escala de produção")

    def test_campo_nao_critico_dispensa_justificativa(self):
        response = self.client.post(
            reverse("ordens:formula_editar", args=[self.formula.pk]),
            self.dados_formula(observacoes="Misturar devagar"),
        )
        self.assertRedirects(response, reverse("ordens:formula_lista"))
        self.formula.refresh_from_db()
        self.assertEqual(self.formula.observacoes, "Misturar devagar")

    def test_criacao_nao_exibe_campo_de_justificativa(self):
        response = self.client.get(reverse("ordens:formula_criar"))
        self.assertNotContains(response, "justificativa_alteracao")


class EventosDeFluxoTests(BaseAuditoria):
    def setUp(self):
        super().setUp()
        self.cliente = Cliente(razao_social="Corpo & Cheiro")
        self.cliente.salvar_com_usuario(self.usuario)
        self.pedido = Pedido(cliente=self.cliente, prazo=date(2026, 12, 1))
        self.pedido.salvar_com_usuario(self.usuario)
        self.item = ItemPedido.objects.create(
            pedido=self.pedido, produto=self.produto, quantidade=Decimal("50")
        )
        self.ordem = OrdemProducao(
            item_pedido=self.item,
            formula=self.formula,
            quantidade=Decimal("50"),
            data_programada=date(2026, 11, 1),
        )
        self.ordem.salvar_com_usuario(self.usuario)

    def test_cancelamento_de_op_registra_evento_com_motivo(self):
        response = self.client.post(
            reverse("ordens:cancelar", args=[self.ordem.pk]),
            {"motivo": "Pedido suspenso pelo cliente"},
        )
        self.assertRedirects(response, self.ordem.get_absolute_url())

        trilha = trilha_de(self.ordem)
        evento = trilha.filter(acao=AcaoAuditoria.CANCELAMENTO).get()
        self.assertEqual(evento.justificativa, "Pedido suspenso pelo cliente")
        self.assertEqual(evento.usuario, self.usuario)

        alteracao_status = trilha.filter(
            acao=AcaoAuditoria.ALTERACAO, campo="status"
        ).get()
        self.assertEqual(alteracao_status.valor_anterior, "Rascunho")
        self.assertEqual(alteracao_status.valor_novo, "Cancelada")
        self.assertEqual(
            alteracao_status.justificativa, "Pedido suspenso pelo cliente"
        )

    def test_cancelamento_de_pedido_registra_evento(self):
        self.pedido.transicionar(
            StatusPedido.CANCELADO, self.usuario, motivo="Cliente desistiu"
        )
        evento = trilha_de(self.pedido).filter(acao=AcaoAuditoria.CANCELAMENTO).get()
        self.assertEqual(evento.justificativa, "Cliente desistiu")


class TelasComTrilhaTests(BaseAuditoria):
    def test_edicao_de_formula_mostra_trilha_e_justificativa(self):
        response = self.client.get(
            reverse("ordens:formula_editar", args=[self.formula.pk])
        )
        self.assertContains(response, "Trilha de auditoria")
        self.assertContains(response, "justificativa_alteracao")

    def test_detalhe_da_op_mostra_trilha(self):
        cliente = Cliente(razao_social="Cliente X")
        cliente.salvar_com_usuario(self.usuario)
        pedido = Pedido(cliente=cliente, prazo=date(2026, 12, 1))
        pedido.salvar_com_usuario(self.usuario)
        item = ItemPedido.objects.create(
            pedido=pedido, produto=self.produto, quantidade=Decimal("10")
        )
        ordem = OrdemProducao(
            item_pedido=item,
            formula=self.formula,
            quantidade=Decimal("10"),
            data_programada=date(2026, 11, 1),
        )
        ordem.salvar_com_usuario(self.usuario)

        response = self.client.get(reverse("ordens:detalhe", args=[ordem.pk]))
        self.assertContains(response, "Trilha de auditoria")
        self.assertContains(response, "Criação")
