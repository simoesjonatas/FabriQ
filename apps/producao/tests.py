from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.perfis import COMPRAS, DIRETORIA, PCP, PRODUCAO
from apps.cadastros.models import Cliente, Equipamento, MateriaPrima, Produto
from apps.estoque.models import (
    LocalEstoque,
    Lote,
    Movimentacao,
    SituacaoLote,
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

from .models import (
    ConsumoMaterialOP,
    ExecucaoOP,
    Parada,
    apontar_consumos_fefo,
    sugerir_consumos_fefo,
)

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
        self.equipamento = Equipamento.objects.create(
            codigo="EQ-1", nome="Envasadora", ultima_limpeza=timezone.localdate()
        )
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

    def lote_mp(self, codigo, dias_validade=180):
        return Lote.objects.create(
            codigo=codigo,
            materia_prima=self.mp,
            validade=timezone.localdate() + timedelta(days=dias_validade),
        )

    def test_conclusao_consome_material_e_estoca_acabado(self):
        lote = self.lote_mp("MP-L1")
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.iniciar(quantidade="50")  # precisa de 20
        apontar_consumos_fefo(ordem, self.operador)

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

    def test_conclusao_bloqueada_sem_apontamento_de_lotes(self):
        lote = self.lote_mp("MP-L1")
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.iniciar(quantidade="50")

        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), self.dados_conclusao()
        )
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.EM_PRODUCAO)
        # Nenhuma saída nem entrada de acabado foi criada
        self.assertEqual(saldo(self.mp), Decimal("30"))
        self.assertEqual(saldo(self.produto), Decimal("0"))


class ConsumoPorLoteTests(BaseProducao):
    """Etapa 4: consumo real apontado por lote (PDF 2.1/5.2)."""

    def iniciar(self, quantidade="50"):
        ordem = self.criar_op_liberada(quantidade)
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        return ordem

    def lote_mp(self, codigo, dias_validade=180):
        return Lote.objects.create(
            codigo=codigo,
            materia_prima=self.mp,
            validade=timezone.localdate() + timedelta(days=dias_validade),
        )

    def dados_conclusao(self, **kwargs):
        dados = {
            "quantidade_produzida": "50",
            "perdas": "0",
            "lote_validade": "",
            "local_destino": str(self.acabados.pk),
            "justificativa_divergencia": "",
        }
        dados.update(kwargs)
        return dados

    def test_concluir_com_dois_lotes_do_mesmo_material(self):
        """Critério de aceite do PDF: dois lotes, consumo individual e baixa correta."""
        lote_a = self.lote_mp("MP-LA", dias_validade=90)   # vence depois
        lote_b = self.lote_mp("MP-LB", dias_validade=30)   # vence antes → FEFO
        entrada({"materia_prima": self.mp}, "15", self.deposito, lote=lote_a)
        entrada({"materia_prima": self.mp}, "15", self.deposito, lote=lote_b)
        ordem = self.iniciar(quantidade="50")  # necessário: 20 L

        # Apontamento pela tela: FEFO sugere B (15) + A (5); operador confirma
        material = ordem.materiais.get()
        response = self.client.post(
            reverse("producao:consumos", args=[ordem.pk]),
            {
                f"qtd-{material.pk}-{lote_b.pk}-{self.deposito.pk}": "15",
                f"qtd-{material.pk}-{lote_a.pk}-{self.deposito.pk}": "5",
            },
        )
        self.assertRedirects(response, reverse("producao:painel", args=[ordem.pk]))
        self.assertEqual(material.consumos.count(), 2)

        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), self.dados_conclusao()
        )
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.CONCLUIDA)

        # Consumo individual por lote, cada um vinculado à sua saída
        consumos = {c.lote_id: c for c in material.consumos.all()}
        self.assertEqual(consumos[lote_b.pk].quantidade, Decimal("15"))
        self.assertEqual(consumos[lote_a.pk].quantidade, Decimal("5"))
        for consumo in consumos.values():
            self.assertTrue(consumo.confirmado)
            self.assertEqual(
                consumo.movimentacao.tipo, TipoMovimentacao.SAIDA
            )
            self.assertEqual(consumo.movimentacao.quantidade, consumo.quantidade)

        # Baixa correta do estoque por lote
        self.assertEqual(saldo(self.mp, lote=lote_b), Decimal("0"))
        self.assertEqual(saldo(self.mp, lote=lote_a), Decimal("10"))

        # Coluna "Lote usado" preenchida na tela da OP (vista pelo PCP)
        criar_usuario("pcp.consulta", perfil=PCP)
        self.client.login(username="pcp.consulta", password="senha-forte-123")
        detalhe = self.client.get(reverse("ordens:detalhe", args=[ordem.pk]))
        self.assertContains(detalhe, "MP-LB")
        self.assertContains(detalhe, "MP-LA")

    def test_sugestao_fefo_prioriza_quem_vence_primeiro(self):
        lote_a = self.lote_mp("MP-LA", dias_validade=90)
        lote_b = self.lote_mp("MP-LB", dias_validade=30)
        entrada({"materia_prima": self.mp}, "15", self.deposito, lote=lote_a)
        entrada({"materia_prima": self.mp}, "15", self.deposito, lote=lote_b)
        ordem = self.iniciar(quantidade="50")

        material = ordem.materiais.get()
        sugestoes = sugerir_consumos_fefo(ordem)[material.pk]
        self.assertEqual(sugestoes[0]["lote"], lote_b)
        self.assertEqual(sugestoes[0]["quantidade"], Decimal("15"))
        self.assertEqual(sugestoes[1]["lote"], lote_a)
        self.assertEqual(sugestoes[1]["quantidade"], Decimal("5"))

    def test_concluir_sem_lote_lista_materiais_pendentes(self):
        lote = self.lote_mp("MP-L1")
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.iniciar()

        response = self.client.post(
            reverse("producao:concluir", args=[ordem.pk]),
            self.dados_conclusao(),
            follow=True,
        )
        self.assertContains(response, "Aponte os lotes consumidos")
        self.assertContains(response, "MP-1")
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.EM_PRODUCAO)

    def test_lote_vencido_fora_da_sugestao_e_rejeitado_no_apontamento(self):
        vencido = Lote.objects.create(
            codigo="MP-VENC",
            materia_prima=self.mp,
            validade=timezone.localdate() - timedelta(days=1),
        )
        valido = self.lote_mp("MP-OK")
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=vencido)
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=valido)
        ordem = self.iniciar()
        material = ordem.materiais.get()

        # Vencido não aparece na sugestão
        lotes_sugeridos = [
            s["lote"] for s in sugerir_consumos_fefo(ordem)[material.pk]
        ]
        self.assertNotIn(vencido, lotes_sugeridos)

        # Operador comum não pode apontar o vencido (bloqueio informa a causa)
        response = self.client.post(
            reverse("producao:consumos", args=[ordem.pk]),
            {f"qtd-{material.pk}-{vencido.pk}-{self.deposito.pk}": "20"},
            follow=True,
        )
        self.assertContains(response, "vencido em")
        self.assertEqual(material.consumos.count(), 0)

    def test_divergencia_exige_justificativa(self):
        lote = self.lote_mp("MP-L1")
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.iniciar()  # necessário 20
        material = ordem.materiais.get()
        self.client.post(
            reverse("producao:consumos", args=[ordem.pk]),
            {f"qtd-{material.pk}-{lote.pk}-{self.deposito.pk}": "18"},
        )

        # Sem justificativa → bloqueia
        response = self.client.post(
            reverse("producao:concluir", args=[ordem.pk]),
            self.dados_conclusao(),
            follow=True,
        )
        self.assertContains(response, "difere do necessário")
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.EM_PRODUCAO)

        # Com justificativa → conclui e registra na trilha
        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]),
            self.dados_conclusao(
                justificativa_divergencia="Rendimento melhor: sobrou essência"
            ),
        )
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.CONCLUIDA)
        self.assertEqual(saldo(self.mp), Decimal("12"))

        from apps.auditoria.models import AcaoAuditoria
        from apps.auditoria.servicos import trilha_de

        evento = trilha_de(ordem).filter(
            acao=AcaoAuditoria.ALTERACAO, campo="consumo apontado"
        ).get()
        self.assertEqual(
            evento.justificativa, "Rendimento melhor: sobrou essência"
        )

    def test_consumo_confirmado_e_imutavel(self):
        from apps.auditoria.models import TrilhaImutavelError

        lote = self.lote_mp("MP-L1")
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.iniciar()
        apontar_consumos_fefo(ordem, self.operador)
        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), self.dados_conclusao()
        )

        consumo = ConsumoMaterialOP.objects.get()
        self.assertTrue(consumo.confirmado)
        consumo.quantidade = Decimal("999")
        with self.assertRaises(TrilhaImutavelError):
            consumo.save()
        with self.assertRaises(TrilhaImutavelError):
            consumo.delete()
        with self.assertRaises(TrilhaImutavelError):
            ConsumoMaterialOP.objects.all().delete()

    def test_comando_retroativo_cria_consumos_de_op_antiga(self):
        from django.core.management import call_command

        lote = self.lote_mp("MP-ANTIGO")
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.criar_op_liberada()
        # OP "à moda antiga": concluída sem apontamento, só com a movimentação
        ordem.status = StatusOP.CONCLUIDA
        ordem.save()
        saida = Movimentacao(
            tipo=TipoMovimentacao.SAIDA,
            materia_prima=self.mp,
            lote=lote,
            quantidade=Decimal("20"),
            local_origem=self.deposito,
            motivo=f"Consumo na produção {ordem.numero}",
            documento=ordem.numero,
            criado_por=self.operador,
            atualizado_por=self.operador,
        )
        saida.full_clean()
        saida.save()

        call_command("criar_consumos_retroativos")

        consumo = ConsumoMaterialOP.objects.get(material__ordem=ordem)
        self.assertEqual(consumo.lote, lote)
        self.assertEqual(consumo.quantidade, Decimal("20"))
        self.assertEqual(consumo.movimentacao, saida)
        self.assertEqual(consumo.registrado_por, self.operador)

        # Idempotente
        call_command("criar_consumos_retroativos")
        self.assertEqual(ConsumoMaterialOP.objects.count(), 1)


class SituacaoLoteBloqueioTests(BaseProducao):
    """Etapa 5: situação do lote impede consumo; exceção justificada libera."""

    def iniciar(self, quantidade="50"):
        ordem = self.criar_op_liberada(quantidade)
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        return ordem

    def lote_mp(self, codigo, situacao=SituacaoLote.APROVADO, dias_validade=180):
        return Lote.objects.create(
            codigo=codigo,
            materia_prima=self.mp,
            validade=timezone.localdate() + timedelta(days=dias_validade),
            situacao=situacao,
        )

    def apontar(self, ordem, lote, quantidade, **extra):
        material = ordem.materiais.get()
        dados = {f"qtd-{material.pk}-{lote.pk}-{self.deposito.pk}": str(quantidade)}
        dados.update(extra)
        return self.client.post(
            reverse("producao:consumos", args=[ordem.pk]), dados, follow=True
        )

    def test_lote_reprovado_bloqueia_consumo_e_informa_causa(self):
        lote = self.lote_mp("MP-REP", situacao=SituacaoLote.REPROVADO)
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.iniciar()

        response = self.apontar(ordem, lote, 20)
        self.assertContains(response, "reprovado no controle de qualidade")
        self.assertEqual(ordem.materiais.get().consumos.count(), 0)

    def test_lote_bloqueado_nao_aparece_na_sugestao(self):
        bloqueado = self.lote_mp("MP-BLOQ", situacao=SituacaoLote.BLOQUEADO)
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=bloqueado)
        ordem = self.iniciar()

        lotes = [s["lote"] for s in sugerir_consumos_fefo(ordem)[ordem.materiais.get().pk]]
        self.assertNotIn(bloqueado, lotes)

    def test_operador_comum_nao_autoriza_excecao(self):
        lote = self.lote_mp("MP-REP", situacao=SituacaoLote.REPROVADO)
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.iniciar()

        # Operador (PRODUCAO) tenta forçar com justificativa: exceção ignorada
        response = self.apontar(
            ordem, lote, 20, **{f"excecao-{lote.pk}": "preciso usar"}
        )
        self.assertContains(response, "reprovado no controle de qualidade")
        self.assertEqual(ordem.materiais.get().consumos.count(), 0)

    def test_excecao_autorizada_libera_e_grava_trilha(self):
        from apps.auditoria.models import AcaoAuditoria
        from apps.auditoria.servicos import trilha_de

        diretor = criar_usuario("diretora", perfil=DIRETORIA)
        lote = self.lote_mp("MP-REP", situacao=SituacaoLote.REPROVADO)
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.iniciar()

        self.client.login(username="diretora", password="senha-forte-123")
        response = self.apontar(
            ordem, lote, 20,
            **{f"excecao-{lote.pk}": "Reanálise aprovou; usar sob responsabilidade"},
        )
        self.assertContains(response, "exceção autorizada")

        consumo = ordem.materiais.get().consumos.get()
        self.assertEqual(consumo.lote, lote)
        self.assertEqual(consumo.quantidade, Decimal("20"))

        evento = trilha_de(lote).filter(
            acao=AcaoAuditoria.EXCECAO_BLOQUEIO
        ).get()
        self.assertEqual(evento.usuario, diretor)
        self.assertIn("reprovado", evento.valor_anterior)
        self.assertEqual(
            evento.justificativa,
            "Reanálise aprovou; usar sob responsabilidade",
        )

    def test_produto_acabado_nasce_aguardando_cq(self):
        lote = self.lote_mp("MP-OK")
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.iniciar()
        apontar_consumos_fefo(ordem, self.operador)
        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]),
            {
                "quantidade_produzida": "50",
                "perdas": "0",
                "lote_validade": "",
                "local_destino": str(self.acabados.pk),
                "justificativa_divergencia": "",
            },
        )
        ordem.refresh_from_db()
        self.assertEqual(
            ordem.lote_produto.situacao, SituacaoLote.AGUARDANDO_CQ
        )


class PesagemTests(BaseProducao):
    """Etapa 6b: pesagem com balança calibrada, dupla conferência e tolerância."""

    def setUp(self):
        super().setUp()
        from apps.cadastros.models import Balanca

        self.conferente = criar_usuario("conferente", perfil=PRODUCAO)
        self.balanca = Balanca.objects.create(
            codigo="BAL-1",
            descricao="Balança de bancada",
            calibracao_validade=timezone.localdate() + timedelta(days=30),
        )
        self.balanca_vencida = Balanca.objects.create(
            codigo="BAL-VENC",
            descricao="Balança vencida",
            calibracao_validade=timezone.localdate() - timedelta(days=1),
        )

    def iniciar(self):
        ordem = self.criar_op_liberada("50")
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        return ordem

    def registrar(self, ordem, **extra):
        material = ordem.materiais.get()
        lote, _ = Lote.objects.get_or_create(codigo="MP-P1", materia_prima=self.mp)
        dados = {
            "material": str(material.pk),
            "lote": str(lote.pk),
            "balanca": str(self.balanca.pk),
            "quantidade_pesada": "20",
            "tolerancia_percentual": "1",
            "conferente": "",
            "etiqueta": "ETQ-1",
        }
        dados.update(extra)
        return self.client.post(
            reverse("producao:pesagem", args=[ordem.pk]), dados, follow=True
        )

    def test_pesagem_dentro_da_tolerancia_registra(self):
        from .models import PesagemOP

        ordem = self.iniciar()  # necessário 20
        response = self.registrar(ordem, quantidade_pesada="20.1")
        self.assertContains(response, "Pesagem registrada")
        pesagem = PesagemOP.objects.get()
        self.assertTrue(pesagem.dentro_tolerancia)

    def test_fora_da_tolerancia_bloqueia(self):
        from .models import PesagemOP

        ordem = self.iniciar()
        response = self.registrar(ordem, quantidade_pesada="25")  # 25% > 1%
        self.assertContains(response, "fora da tolerância")
        self.assertEqual(PesagemOP.objects.count(), 0)

    def test_balanca_vencida_bloqueia(self):
        from .models import PesagemOP

        ordem = self.iniciar()
        response = self.registrar(ordem, balanca=str(self.balanca_vencida.pk))
        self.assertContains(response, "calibração vencida")
        self.assertEqual(PesagemOP.objects.count(), 0)

    def test_material_critico_exige_conferente_diferente(self):
        from .models import PesagemOP

        self.mp.critico = True
        self.mp.save()
        ordem = self.iniciar()

        # Sem conferente: bloqueia
        response = self.registrar(ordem)
        self.assertContains(response, "dupla conferência")
        self.assertEqual(PesagemOP.objects.count(), 0)

        # Conferente = operador: bloqueia
        response = self.registrar(ordem, conferente=str(self.operador.pk))
        self.assertContains(response, "diferente do operador")
        self.assertEqual(PesagemOP.objects.count(), 0)

        # Conferente distinto: registra
        response = self.registrar(ordem, conferente=str(self.conferente.pk))
        self.assertContains(response, "Pesagem registrada")
        self.assertEqual(PesagemOP.objects.get().conferente, self.conferente)


class EtapaProcessoTests(BaseProducao):
    """Etapa 6d: etapas seguem a sequência; pular exige justificativa."""

    def setUp(self):
        super().setUp()
        from apps.ordens.models import EtapaFormula

        EtapaFormula.objects.create(
            formula=self.formula, sequencia=1, instrucao="Aquecer base",
            temperatura_prevista=Decimal("60"),
        )
        EtapaFormula.objects.create(
            formula=self.formula, sequencia=2, instrucao="Adicionar essência",
        )

    def op_em_producao_com_snapshot(self):
        from apps.ordens.models import SnapshotFormulaOP

        ordem = self.criar_op_liberada("50")
        SnapshotFormulaOP.congelar(ordem, self.operador)
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        return ordem

    def test_etapas_congeladas_no_snapshot(self):
        ordem = self.op_em_producao_com_snapshot()
        etapas = ordem.snapshot_formula.etapas.all()
        self.assertEqual(etapas.count(), 2)
        self.assertEqual(etapas[0].sequencia, 1)
        self.assertEqual(etapas[0].temperatura_prevista, Decimal("60"))

    def registrar(self, ordem, sequencia, **extra):
        etapa = ordem.snapshot_formula.etapas.get(sequencia=sequencia)
        dados = {
            "etapa": str(etapa.pk),
            "temperatura_real": "",
            "tempo_real_min": "",
            "velocidade_real": "",
            "conferente": "",
            "justificativa": "",
            "observacoes": "",
        }
        dados.update(extra)
        return self.client.post(
            reverse("producao:etapas", args=[ordem.pk]), dados, follow=True
        )

    def test_registra_etapas_na_sequencia(self):
        from .models import EtapaOP

        ordem = self.op_em_producao_com_snapshot()
        response = self.registrar(ordem, 1, temperatura_real="61")
        self.assertContains(response, "Etapa registrada")
        self.assertEqual(EtapaOP.objects.count(), 1)

        response = self.registrar(ordem, 2)
        self.assertContains(response, "Etapa registrada")
        self.assertEqual(EtapaOP.objects.count(), 2)

    def test_pular_etapa_anterior_bloqueia_sem_justificativa(self):
        from .models import EtapaOP

        ordem = self.op_em_producao_com_snapshot()
        # Registrar a etapa 2 antes da 1 sem justificar
        response = self.registrar(ordem, 2)
        self.assertContains(response, "etapas anteriores não executadas")
        self.assertEqual(EtapaOP.objects.count(), 0)

    def test_pular_etapa_com_justificativa_registra_e_audita(self):
        from apps.auditoria.models import AcaoAuditoria
        from apps.auditoria.servicos import trilha_de

        from .models import EtapaOP

        ordem = self.op_em_producao_com_snapshot()
        response = self.registrar(
            ordem, 2, pulada="on",
            justificativa="Etapa 1 não se aplica a este lote",
        )
        self.assertContains(response, "Etapa registrada")
        self.assertTrue(EtapaOP.objects.get().pulada)

        evento = trilha_de(ordem).filter(
            acao=AcaoAuditoria.ALTERACAO, campo="etapa 2"
        ).get()
        self.assertEqual(
            evento.justificativa, "Etapa 1 não se aplica a este lote"
        )


class ControleProcessoTests(BaseProducao):
    """Etapa 6e: controle em processo contra a especificação do produto."""

    def setUp(self):
        super().setUp()
        from apps.qualidade.models import EspecificacaoProduto, TipoAnalise

        self.ph = TipoAnalise.objects.create(
            nome="pH", unidade="pH",
            valor_minimo=Decimal("5.5"), valor_maximo=Decimal("7.0"),
        )
        # Especificação do PRODUTO (mais restrita que o tipo genérico)
        EspecificacaoProduto.objects.create(
            produto=self.produto, tipo=self.ph,
            valor_minimo=Decimal("6.0"), valor_maximo=Decimal("6.5"),
        )

    def iniciar(self):
        ordem = self.criar_op_liberada("50")
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        return ordem

    def medir(self, ordem, resultado):
        return self.client.post(
            reverse("producao:controles", args=[ordem.pk]),
            {
                "tipo": str(self.ph.pk),
                "resultado": resultado,
                "resultado_texto": "",
                "metodo": "Potenciômetro",
                "equipamento": "",
            },
            follow=True,
        )

    def test_usa_limite_da_especificacao_do_produto(self):
        from .models import ControleProcessoOP

        ordem = self.iniciar()
        # 6.8 passa no tipo genérico (5.5–7.0) mas FALHA na espec do produto (6.0–6.5)
        response = self.medir(ordem, "6.8")
        self.assertContains(response, "FORA da especificação")
        controle = ControleProcessoOP.objects.get()
        self.assertTrue(controle.fora_especificacao)
        self.assertEqual(controle.valor_maximo, Decimal("6.5"))

    def test_medicoes_acumulam_sem_apagar_a_anterior(self):
        from .models import ControleProcessoOP

        ordem = self.iniciar()
        self.medir(ordem, "6.8")   # fora
        self.medir(ordem, "6.3")   # dentro

        controles = ControleProcessoOP.objects.filter(ordem=ordem).order_by("id")
        self.assertEqual(controles.count(), 2)
        self.assertTrue(controles[0].fora_especificacao)   # a primeira foi preservada
        self.assertFalse(controles[1].fora_especificacao)


class EnvaseTests(BaseProducao):
    """Etapa 7a: envase só com versão de arte aprovada."""

    def setUp(self):
        super().setUp()
        from apps.cadastros.models import VersaoArte

        self.arte = VersaoArte.objects.create(
            produto=self.produto, versao="v1",
            data_aprovacao=timezone.localdate(), status="APROVADA",
        )
        self.arte_obsoleta = VersaoArte.objects.create(
            produto=self.produto, versao="v0", status="OBSOLETA",
        )

    def iniciar(self):
        ordem = self.criar_op_liberada("50")
        ordem.reservar_lote_produto(self.operador)
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        return ordem

    def envasar(self, ordem, arte, quantidade="48"):
        return self.client.post(
            reverse("producao:envase", args=[ordem.pk]),
            {
                "versao_arte": str(arte.pk),
                "linha": "",
                "quantidade_envasada": quantidade,
                "peso_volume_medio": "",
                "perdas": "0",
                "controles": "",
                "conferente": "",
            },
            follow=True,
        )

    def test_envase_com_arte_aprovada_registra(self):
        from .models import EnvaseOP

        ordem = self.iniciar()
        response = self.envasar(ordem, self.arte)
        self.assertContains(response, "Envase registrado")
        self.assertEqual(EnvaseOP.objects.count(), 1)

    def test_envase_com_arte_obsoleta_bloqueia(self):
        from .models import EnvaseOP

        ordem = self.iniciar()
        # A arte obsoleta nem aparece no select (queryset filtrado)
        response = self.envasar(ordem, self.arte_obsoleta)
        self.assertEqual(EnvaseOP.objects.count(), 0)
        self.assertEqual(response.status_code, 200)


class PerdasTests(BaseProducao):
    """Etapa 7b: perda acima do limite exige justificativa e aprovação."""

    def iniciar(self, quantidade="100"):
        lote = Lote.objects.create(
            codigo="MP-PERDA", materia_prima=self.mp,
            validade=timezone.localdate() + timedelta(days=180),
        )
        entrada({"materia_prima": self.mp}, "60", self.deposito, lote=lote)
        ordem = self.criar_op_liberada(quantidade)
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        apontar_consumos_fefo(ordem, self.operador)
        return ordem

    def concluir(self, ordem, quantidade_produzida, perdas, **extra):
        dados = {
            "quantidade_produzida": quantidade_produzida,
            "perdas": perdas,
            "lote_validade": "",
            "local_destino": str(self.acabados.pk),
            "justificativa_divergencia": "",
            "justificativa_perda": "",
        }
        dados.update(extra)
        return self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), dados, follow=True
        )

    def test_perda_dentro_do_limite_encerra_e_calcula_rendimento(self):
        from apps.ordens.models import StatusOP

        # limite padrão do produto = 5%
        ordem = self.iniciar(quantidade="100")
        self.concluir(ordem, quantidade_produzida="97", perdas="3")  # 3% < 5%
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.CONCLUIDA)
        self.assertEqual(ordem.execucao.perda_percentual, Decimal("3.000"))
        self.assertEqual(ordem.execucao.rendimento_percentual, Decimal("97.000"))

    def test_perda_acima_do_limite_bloqueia_sem_justificativa(self):
        from apps.ordens.models import StatusOP

        ordem = self.iniciar(quantidade="100")
        response = self.concluir(ordem, quantidade_produzida="90", perdas="8")  # 8% > 5%
        self.assertContains(response, "acima do limite")
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.EM_PRODUCAO)

    def test_perda_acima_do_limite_com_justificativa_encerra(self):
        from apps.ordens.models import StatusOP

        ordem = self.iniciar(quantidade="100")
        self.concluir(
            ordem, quantidade_produzida="90", perdas="8",
            justificativa_perda="Vazamento no envase — aprovado pela supervisão",
        )
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.CONCLUIDA)
        self.assertEqual(ordem.execucao.perda_aprovada_por, self.operador)
        self.assertIn("Vazamento", ordem.execucao.perda_justificativa)


class DesvioTests(BaseProducao):
    """Etapa 7c: OP não encerra com desvio pendente; decisão da Qualidade."""

    def setUp(self):
        super().setUp()
        from apps.accounts.perfis import QUALIDADE

        self.analista = criar_usuario("analista", perfil=QUALIDADE)

    def iniciar(self):
        lote = Lote.objects.create(
            codigo="MP-D1", materia_prima=self.mp,
            validade=timezone.localdate() + timedelta(days=180),
        )
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.criar_op_liberada("50")
        ordem.reservar_lote_produto(self.operador)  # como na liberação real
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        apontar_consumos_fefo(ordem, self.operador)
        return ordem

    def registrar_desvio(self, ordem, **extra):
        dados = {
            "acao": "registrar",
            "tipo": "PROCESSO",
            "etapa": "",
            "descricao": "Temperatura acima do previsto na mistura",
            "impacto": "",
            "acao_imediata": "",
        }
        dados.update(extra)
        return self.client.post(
            reverse("producao:desvios", args=[ordem.pk]), dados, follow=True
        )

    def dados_conclusao(self):
        return {
            "quantidade_produzida": "50",
            "perdas": "0",
            "lote_validade": "",
            "local_destino": str(self.acabados.pk),
            "justificativa_divergencia": "",
        }

    def test_desvio_pendente_bloqueia_encerramento(self):
        from apps.ordens.models import StatusOP

        ordem = self.iniciar()
        self.registrar_desvio(ordem)

        response = self.client.post(
            reverse("producao:concluir", args=[ordem.pk]),
            self.dados_conclusao(), follow=True,
        )
        self.assertContains(response, "desvio(s) pendente(s)")
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.EM_PRODUCAO)

    def test_decisao_da_qualidade_encerra_e_libera(self):
        from apps.ordens.models import StatusOP

        from .models import Desvio, StatusDesvio

        ordem = self.iniciar()
        self.registrar_desvio(ordem)
        desvio = Desvio.objects.get()

        # Operador (produção) não decide
        self.client.post(
            reverse("producao:desvios", args=[ordem.pk]),
            {"acao": "decidir", "desvio": str(desvio.pk),
             "decisao": "ACEITO", "justificativa": "Sem impacto na qualidade"},
        )
        desvio.refresh_from_db()
        self.assertEqual(desvio.status, StatusDesvio.ABERTO)

        # Qualidade decide
        self.client.login(username="analista", password="senha-forte-123")
        self.client.post(
            reverse("producao:desvios", args=[ordem.pk]),
            {"acao": "decidir", "desvio": str(desvio.pk),
             "decisao": "ACEITO", "justificativa": "Sem impacto na qualidade"},
        )
        desvio.refresh_from_db()
        self.assertEqual(desvio.status, StatusDesvio.ENCERRADO)
        self.assertEqual(desvio.avaliador, self.analista)

        # Agora encerra
        self.client.login(username="operador", password="senha-forte-123")
        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), self.dados_conclusao()
        )
        ordem.refresh_from_db()
        self.assertEqual(ordem.status, StatusOP.CONCLUIDA)

    def test_desvio_critico_reprovado_bloqueia_lote(self):
        from apps.estoque.models import SituacaoLote

        from .models import Desvio

        ordem = self.iniciar()
        self.registrar_desvio(ordem, critico="on")
        desvio = Desvio.objects.get()

        self.client.login(username="analista", password="senha-forte-123")
        self.client.post(
            reverse("producao:desvios", args=[ordem.pk]),
            {"acao": "decidir", "desvio": str(desvio.pk),
             "decisao": "REPROVADO", "justificativa": "Lote comprometido"},
        )
        ordem.refresh_from_db()
        self.assertEqual(ordem.lote_produto.situacao, SituacaoLote.BLOQUEADO)


class AtividadeOPTests(BaseProducao):
    """Etapa 2c: quem fez o quê na OP."""

    def iniciar(self, quantidade="50"):
        ordem = self.criar_op_liberada(quantidade)
        self.client.post(reverse("producao:iniciar", args=[ordem.pk]))
        ordem.refresh_from_db()
        return ordem

    def test_iniciar_e_concluir_registram_atividades_automaticas(self):
        from .models import TipoAtividadeOP

        lote = Lote.objects.create(
            codigo="MP-ATIV",
            materia_prima=self.mp,
            validade=timezone.localdate() + timedelta(days=180),
        )
        entrada({"materia_prima": self.mp}, "30", self.deposito, lote=lote)
        ordem = self.iniciar()
        atividades = list(ordem.atividades.values_list("atividade", flat=True))
        self.assertIn(TipoAtividadeOP.PRODUCAO, atividades)

        apontar_consumos_fefo(ordem, self.operador)
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

    def test_apontamento_fefo_automatico_consome_quem_vence_primeiro(self):
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
        apontar_consumos_fefo(ordem, self.operador)
        self.client.post(
            reverse("producao:concluir", args=[ordem.pk]), self.dados_conclusao()
        )

        # B (vence antes) esgota 15; A cede 5 → sobra 10 em A, 0 em B
        self.assertEqual(saldo(self.mp, lote=lote_b), Decimal("0"))
        self.assertEqual(saldo(self.mp, lote=lote_a), Decimal("10"))


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
