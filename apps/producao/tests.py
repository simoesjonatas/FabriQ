from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import COMPRAS, PCP, PRODUCAO
from apps.cadastros.models import Cliente, Equipamento, MateriaPrima, Produto
from apps.estoque.models import (
    LocalEstoque,
    Lote,
    Movimentacao,
    TipoMovimentacao,
    saldo,
)
from apps.ordens.models import (
    ComponenteFormula,
    Formula,
    OrdemProducao,
    StatusOP,
)
from apps.pedidos.models import ItemPedido, Pedido, StatusPedido
from apps.recebimento.models import local_quarentena

from .models import ExecucaoOP, Parada, ProducaoInsuficiente

User = get_user_model()


def criar_usuario(username, perfil=None, senha="senha-forte-123"):
    usuario = User.objects.create_user(username=username, password=senha)
    if perfil:
        usuario.groups.add(Group.objects.get(name=perfil))
    return usuario


def entrada(item_kwargs, quantidade, local, lote=None):
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
    return movimentacao


class BaseProducao(TestCase):
    def setUp(self):
        self.operador = criar_usuario("operador", perfil=PRODUCAO)
        self.client.login(username="operador", password="senha-forte-123")

        self.cliente = Cliente.objects.create(razao_social="Loja Bela Pele LTDA")
        self.produto = Produto.objects.create(codigo="PA-1", nome="Perfume", unidade="UN")
        self.mp = MateriaPrima.objects.create(codigo="MP-1", nome="Essência", unidade="L")
        self.equipamento = Equipamento.objects.create(codigo="EQ-1", nome="Envasadora")
        self.deposito = LocalEstoque.objects.create(nome="Almoxarifado")
        self.acabados = LocalEstoque.objects.create(nome="Produtos acabados")

        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            status=StatusPedido.PROGRAMADO,
            prazo=timezone.localdate() + timedelta(days=15),
        )
        self.item_pedido = ItemPedido.objects.create(
            pedido=self.pedido, produto=self.produto, quantidade=Decimal("100")
        )
        self.formula = Formula.objects.create(
            produto=self.produto, nome="Padrão", rendimento=Decimal("100")
        )
        ComponenteFormula.objects.create(
            formula=self.formula, materia_prima=self.mp, quantidade=Decimal("40")
        )

    def criar_op_liberada(self, quantidade="50"):
        ordem = OrdemProducao.objects.create(
            item_pedido=self.item_pedido,
            formula=self.formula,
            quantidade=Decimal(quantidade),
            equipamento=self.equipamento,
            operador=self.operador,
            data_programada=timezone.localdate() + timedelta(days=1),
            status=StatusOP.LIBERADA,
        )
        ordem.gerar_materiais()
        return ordem

    def dados_conclusao(self, **kwargs):
        dados = {
            "quantidade_produzida": "50",
            "perdas": "2",
            "lote_validade": "",
            "local_destino": str(self.acabados.pk),
        }
        dados.update(kwargs)
        return dados


class IniciarTests(BaseProducao):
    def test_iniciar_cria_execucao_e_move_pedido(self):
        ordem = self.criar_op_liberada()
        response = self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        self.assertRedirects(response, reverse("producao:painel", args=[ordem.pk]))

        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.EM_PRODUCAO)
        self.assertTrue(hasattr(ordem, "execucao"))
        self.assertEqual(ordem.execucao.iniciado_por, self.operador)

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, StatusPedido.EM_PRODUCAO)

    def test_nao_inicia_op_nao_liberada(self):
        ordem = self.criar_op_liberada()
        ordem.status = StatusOP.RASCUNHO
        ordem.save()
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.RASCUNHO)
        self.assertFalse(ExecucaoOP.objects.exists())


class ConcluirTests(BaseProducao):
    def iniciar(self, quantidade="50"):
        ordem = self.criar_op_liberada(quantidade)
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        return ordem

    def test_conclusao_consome_material_e_estoca_acabado(self):
        entrada({"materia_prima": self.mp}, "30", self.deposito)  # precisa de 20
        ordem = self.iniciar(quantidade="50")

        response = self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), self.dados_conclusao()
        )
        self.assertRedirects(response, reverse("producao:painel", args=[ordem.pk]))

        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.CONCLUIDA)
        self.assertEqual(ordem.execucao.quantidade_produzida, Decimal("50"))
        self.assertEqual(ordem.execucao.perdas, Decimal("2"))

        # Matéria-prima baixada: 30 - 20 = 10
        self.assertEqual(saldo(self.mp), Decimal("10"))
        # Produto acabado entrou: 50 no local de acabados
        self.assertEqual(saldo(self.produto, local=self.acabados), Decimal("50"))
        # Lote interno gerado automaticamente pela sequência
        self.assertRegex(ordem.execucao.lote_produzido.codigo, r"^PA-\d{4}-\d{5}$")
        self.assertEqual(ordem.execucao.lote_produzido, ordem.lote_produto)

    def test_conclusao_bloqueada_por_estoque_insuficiente(self):
        entrada({"materia_prima": self.mp}, "10", self.deposito)  # < 20
        ordem = self.iniciar(quantidade="50")

        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), self.dados_conclusao()
        )
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.EM_PRODUCAO)
        # Nenhuma saída nem entrada de acabado foi criada
        self.assertEqual(saldo(self.mp), Decimal("10"))
        self.assertEqual(saldo(self.produto), Decimal("0"))


class AtividadeOPTests(BaseProducao):
    """Etapa 2c: quem fez o quê na OP."""

    def iniciar(self, quantidade="50"):
        ordem = self.criar_op_liberada(quantidade)
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        return ordem

    def test_iniciar_e_concluir_registram_atividades_automaticas(self):
        from .models import TipoAtividadeOP

        entrada({"materia_prima": self.mp}, "30", self.deposito)
        ordem = self.iniciar()
        atividades = list(ordem.atividades.values_list("atividade", flat=True))
        self.assertIn(TipoAtividadeOP.PRODUCAO, atividades)

        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), self.dados_conclusao()
        )
        ordem.refresh_from_db()
        atividades = list(
            ordem.atividades.values_list("atividade", "observacao")
        )
        # OP de teste não tinha lote reservado → atribuição na conclusão
        observacao_lote = (
            f"Lote interno {ordem.lote_produto.codigo} atribuído na conclusão"
        )
        self.assertIn(
            (TipoAtividadeOP.ATRIBUICAO_LOTE, observacao_lote), atividades
        )
        conclusoes = [
            obs for tipo, obs in atividades
            if tipo == TipoAtividadeOP.PRODUCAO and "concluída" in obs
        ]
        self.assertEqual(len(conclusoes), 1)
        self.assertEqual(
            ordem.atividades.last().funcionario, self.operador
        )

    def test_registro_manual_de_envase_aparece_no_painel(self):
        from .models import TipoAtividadeOP

        ordem = self.iniciar()
        response = self.client.post(
            reverse("producao:atividade", args=[ordem.pk]),
            {"atividade": TipoAtividadeOP.ENVASE, "observacao": "Linha 2, frascos 250 ml"},
        )
        self.assertRedirects(response, reverse("producao:painel", args=[ordem.pk]))

        envase = ordem.atividades.get(atividade=TipoAtividadeOP.ENVASE)
        self.assertEqual(envase.funcionario, self.operador)
        self.assertEqual(envase.observacao, "Linha 2, frascos 250 ml")

        painel = self.client.get(reverse("producao:painel", args=[ordem.pk]))
        self.assertContains(painel, "Quem fez o quê")
        self.assertContains(painel, "Envase")
        self.assertContains(painel, "Linha 2, frascos 250 ml")

    def test_atividade_automatica_nao_e_opcao_manual(self):
        from .models import TipoAtividadeOP

        ordem = self.iniciar()
        self.client.post(
            reverse("producao:atividade", args=[ordem.pk]),
            {"atividade": TipoAtividadeOP.LIBERACAO, "observacao": "forjada"},
        )
        self.assertFalse(
            ordem.atividades.filter(observacao="forjada").exists()
        )

    def test_atividade_e_imutavel(self):
        from apps.auditoria.models import TrilhaImutavelError

        from .models import AtividadeOP, TipoAtividadeOP

        ordem = self.iniciar()
        atividade = ordem.atividades.get(atividade=TipoAtividadeOP.PRODUCAO)

        atividade.observacao = "adulterada"
        with self.assertRaises(TrilhaImutavelError):
            atividade.save()
        with self.assertRaises(TrilhaImutavelError):
            atividade.delete()
        with self.assertRaises(TrilhaImutavelError):
            AtividadeOP.objects.all().delete()

    def test_estoque_em_quarentena_nao_e_consumido(self):
        entrada({"materia_prima": self.mp}, "30", local_quarentena())
        ordem = self.iniciar(quantidade="50")

        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), self.dados_conclusao()
        )
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.EM_PRODUCAO)
        # Continua tudo na quarentena
        self.assertEqual(saldo(self.mp, local=local_quarentena()), Decimal("30"))

    def test_consumo_respeita_fefo(self):
        # Lote A vence depois; lote B vence antes → B deve sair primeiro
        hoje = timezone.localdate()
        lote_a = Lote.objects.create(
            materia_prima=self.mp, codigo="A", validade=hoje + timedelta(days=90)
        )
        lote_b = Lote.objects.create(
            materia_prima=self.mp, codigo="B", validade=hoje + timedelta(days=10)
        )
        entrada({"materia_prima": self.mp}, "15", self.deposito, lote=lote_a)
        entrada({"materia_prima": self.mp}, "15", self.deposito, lote=lote_b)

        ordem = self.iniciar(quantidade="50")  # precisa de 20
        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), self.dados_conclusao()
        )

        # B (vence antes) esgota 15; A cede 5 → sobra 10 em A, 0 em B
        self.assertEqual(saldo(self.mp, lote=lote_b), Decimal("0"))
        self.assertEqual(saldo(self.mp, lote=lote_a), Decimal("10"))

    def test_consumir_material_fefo_ordem_direta(self):
        hoje = timezone.localdate()
        lote_a = Lote.objects.create(
            materia_prima=self.mp, codigo="A", validade=hoje + timedelta(days=90)
        )
        lote_b = Lote.objects.create(
            materia_prima=self.mp, codigo="B", validade=hoje + timedelta(days=10)
        )
        entrada({"materia_prima": self.mp}, "15", self.deposito, lote=lote_a)
        entrada({"materia_prima": self.mp}, "15", self.deposito, lote=lote_b)

        from .models import consumir_material_fefo

        consumir_material_fefo(
            self.mp,
            Decimal("20"),
            usuario=self.operador,
            motivo="teste",
            documento="OP-1",
            excluir_local=local_quarentena(),
        )
        self.assertEqual(saldo(self.mp, lote=lote_b), Decimal("0"))
        self.assertEqual(saldo(self.mp, lote=lote_a), Decimal("10"))

    def test_saldo_insuficiente_levanta_excecao(self):
        entrada({"materia_prima": self.mp}, "5", self.deposito)
        from .models import consumir_material_fefo

        with self.assertRaises(ProducaoInsuficiente):
            consumir_material_fefo(
                self.mp,
                Decimal("20"),
                usuario=self.operador,
                motivo="teste",
                documento="OP-1",
                excluir_local=local_quarentena(),
            )


class ParadaOcorrenciaTests(BaseProducao):
    def setUp(self):
        super().setUp()
        self.ordem = self.criar_op_liberada()
        self.client.post(reverse("producao:iniciar", args=[self.ordem.pk]))
        self.ordem.refresh_from_db()
        self.execucao = self.ordem.execucao

    def test_abrir_e_encerrar_parada(self):
        self.client.post(
            reverse("producao:abrir_parada", args=[self.ordem.pk]),
            {"motivo": "MANUTENCAO", "observacoes": "troca de peça"},
        )
        self.assertTrue(self.execucao.tem_parada_aberta)

        self.client.post(reverse("producao:encerrar_parada", args=[self.ordem.pk]))
        self.execucao.refresh_from_db()
        parada = self.execucao.paradas.get()
        self.assertIsNotNone(parada.fim)
        self.assertFalse(self.execucao.tem_parada_aberta)

    def test_nao_abre_segunda_parada_com_uma_aberta(self):
        for _ in range(2):
            self.client.post(
                reverse("producao:abrir_parada", args=[self.ordem.pk]),
                {"motivo": "LIMPEZA", "observacoes": ""},
            )
        self.assertEqual(self.execucao.paradas.count(), 1)

    def test_nao_conclui_com_parada_aberta(self):
        entrada({"materia_prima": self.mp}, "30", self.deposito)
        self.client.post(
            reverse("producao:abrir_parada", args=[self.ordem.pk]),
            {"motivo": "REFEICAO", "observacoes": ""},
        )
        self.client.post(
            reverse("producao:concluir", args=[self.ordem.pk]), self.dados_conclusao()
        )
        self.ordem.refresh_from_db()
        self.assertEqual(self.ordem.status, StatusOP.EM_PRODUCAO)

    def test_registrar_ocorrencia(self):
        self.client.post(
            reverse("producao:ocorrencia", args=[self.ordem.pk]),
            {"descricao": "Viscosidade acima do normal"},
        )
        ocorrencia = self.execucao.ocorrencias.get()
        self.assertEqual(ocorrencia.registrado_por, self.operador)

    def test_tempo_de_parada_contabilizado(self):
        parada = Parada.objects.create(
            execucao=self.execucao,
            motivo="MANUTENCAO",
            inicio=timezone.now() - timedelta(minutes=30),
            fim=timezone.now(),
            registrado_por=self.operador,
        )
        self.assertGreaterEqual(parada.duracao, timedelta(minutes=29))
        self.assertGreaterEqual(self.execucao.tempo_paradas, timedelta(minutes=29))


class PermissoesTests(BaseProducao):
    def test_pcp_acessa_producao(self):
        criar_usuario("pcp", perfil=PCP)
        self.client.login(username="pcp", password="senha-forte-123")
        self.assertEqual(self.client.get(reverse("producao:fila")).status_code, 200)

    def test_compras_nao_acessa_producao(self):
        criar_usuario("compras", perfil=COMPRAS)
        self.client.login(username="compras", password="senha-forte-123")
        self.assertEqual(self.client.get(reverse("producao:fila")).status_code, 403)
        ordem = self.criar_op_liberada()
        self.assertEqual(
            self.client.post(reverse("producao:iniciar", args=[ordem.pk])).status_code,
            403,
        )
