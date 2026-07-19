"""
Carga de demonstração do FabriQ.

Monta um cenário completo para apresentar o sistema, usando os métodos
reais de negócio (transições de pedido, quarentena, FEFO, conclusão de
produção) — os históricos e movimentações saem como numa operação real.

Uso:
    python manage.py carregar_demo               # carrega (se ainda não houver demo)
    python manage.py carregar_demo --recarregar  # APAGA os dados operacionais e recria

No container:
    docker compose exec web python manage.py carregar_demo

O --recarregar apaga TODOS os dados operacionais (pedidos, OPs,
movimentações, recebimentos, análises, programações e lotes) — use
somente em ambiente de demonstração. Cadastros e usuários são mantidos
e atualizados por chave (idempotentes).

As datas são relativas a HOJE: a demo sempre mostra pedido atrasado,
calendário do mês, produção do dia e lotes vencendo.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.utils import timezone

from apps.accounts import perfis
from apps.cadastros.models import (
    Cliente,
    Embalagem,
    Equipamento,
    Fornecedor,
    MateriaPrima,
    Produto,
)
from apps.estoque.models import (
    LocalEstoque,
    Lote,
    Movimentacao,
    SequenciaLote,
    TipoMovimentacao,
)
from apps.ordens.models import (
    ComponenteFormula,
    Formula,
    HistoricoOP,
    MaterialOP,
    OrdemProducao,
    SnapshotFormulaOP,
    StatusFormula,
    StatusOP,
)
from apps.pcp.models import Programacao
from apps.pedidos.models import HistoricoPedido, ItemPedido, Pedido, StatusPedido
from apps.producao.models import (
    AtividadeOP,
    ExecucaoOP,
    FotoProducao,
    Ocorrencia,
    Parada,
    TipoAtividadeOP,
)
from apps.qualidade.models import Analise, AnexoAnalise, ResultadoAnalise, StatusAnalise, TipoAnalise
from apps.recebimento.models import (
    AnexoRecebimento,
    DecisaoQuarentena,
    ItemRecebimento,
    Recebimento,
    StatusQuarentena,
    local_quarentena,
)

User = get_user_model()

SENHA_DEMO = "fabriq.demo"
MARCADOR = "[demo]"

USUARIOS_DEMO = [
    ("diretor", "Roberto", "Cardoso", perfis.DIRETORIA),
    ("ana.pcp", "Ana", "Martins", perfis.PCP),
    ("carlos.compras", "Carlos", "Nogueira", perfis.COMPRAS),
    ("jose.almoxarife", "José", "Ribeiro", perfis.ALMOXARIFADO),
    ("paula.qualidade", "Paula", "Ferreira", perfis.QUALIDADE),
    ("marcos.producao", "Marcos", "Oliveira", perfis.PRODUCAO),
    ("rita.expedicao", "Rita", "Santana", perfis.EXPEDICAO),
    ("admin.fabriq", "Admin", "FabriQ", perfis.ADMINISTRADOR),
]


class Command(BaseCommand):
    help = (
        "Carrega um cenário completo de demonstração (pedidos, PCP, estoque, "
        "quarentena, qualidade, OPs e produção). Use --recarregar para limpar "
        "os dados operacionais e recriar — apenas em ambiente de demonstração."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--recarregar",
            action="store_true",
            help="Apaga TODOS os dados operacionais antes de carregar (demo apenas).",
        )

    def handle(self, *args, **options):
        ja_carregado = Pedido.objects.filter(
            observacoes__startswith=MARCADOR
        ).exists()

        if ja_carregado and not options["recarregar"]:
            self.stdout.write(
                self.style.WARNING(
                    "Dados de demonstração já carregados. "
                    "Use --recarregar para limpar e recriar."
                )
            )
            return

        with transaction.atomic():
            if options["recarregar"]:
                self._limpar_dados_operacionais()

            self.hoje = timezone.localdate()
            self.agora = timezone.now()

            call_command("popular_demo", verbosity=0)
            self.stdout.write("✓ Cadastros base (popular_demo)")

            self._usuarios()
            self._locais()
            self._tipos_analise()
            self._formulas()
            self._recebimentos_e_quarentena()
            self._estoque_extra()
            self._pedidos_e_fluxo()

        self._resumo()

    # ------------------------------------------------------------------ limpeza

    def _limpar_dados_operacionais(self):
        self.stdout.write(self.style.WARNING(
            "Apagando dados operacionais (pedidos, OPs, movimentações, "
            "recebimentos, análises, programações e lotes)..."
        ))
        # Ordem respeita as FKs com PROTECT
        FotoProducao.objects.all().delete()
        Ocorrencia.objects.all().delete()
        Parada.objects.all().delete()
        ExecucaoOP.objects.all().delete()
        HistoricoOP.objects.all().delete()
        MaterialOP.objects.all().delete()
        # Atividades e snapshots são imutáveis para usuários; a recarga da
        # demo usa o caminho interno para limpar o ambiente de demonstração.
        models.QuerySet.delete(AtividadeOP.objects.all())
        models.QuerySet.delete(SnapshotFormulaOP.objects.all())
        OrdemProducao.objects.all().delete()
        AnexoAnalise.objects.all().delete()
        ResultadoAnalise.objects.all().delete()
        Analise.objects.all().delete()
        DecisaoQuarentena.objects.all().delete()
        AnexoRecebimento.objects.all().delete()
        ItemRecebimento.objects.all().delete()
        Recebimento.objects.all().delete()
        Programacao.objects.all().delete()
        Movimentacao.objects.all().delete()
        Lote.objects.all().delete()
        SequenciaLote.objects.all().delete()
        HistoricoPedido.objects.all().delete()
        ItemPedido.objects.all().delete()
        Pedido.objects.all().delete()

    # ------------------------------------------------------------------ blocos

    def _usuarios(self):
        self.usuarios = {}
        criados = 0
        for username, nome, sobrenome, perfil in USUARIOS_DEMO:
            usuario, criado = User.objects.get_or_create(
                username=username.upper(),
                defaults={
                    "first_name": nome,
                    "last_name": sobrenome,
                    "email": f"{username}@fabriq.demo".upper(),
                },
            )
            if criado:
                usuario.set_password(SENHA_DEMO)
                usuario.save()
                criados += 1
            usuario.groups.add(Group.objects.get(name=perfil))
            self.usuarios[username] = usuario
        self.stdout.write(f"✓ Usuários por perfil ({criados} novos)")

    def _locais(self):
        nomes = [
            "Almoxarifado MP",
            "Almoxarifado Embalagens",
            "Produtos Acabados",
            "Expedição",
        ]
        self.locais = {}
        for nome in nomes:
            local, _ = LocalEstoque.objects.get_or_create(nome=nome)
            self.locais[nome] = local
        self.quarentena = local_quarentena()
        self.stdout.write("✓ Locais de estoque")

    def _tipos_analise(self):
        dados = [
            ("pH", "pH", Decimal("5.5"), Decimal("7.5"), ""),
            ("Densidade", "g/mL", Decimal("0.95"), Decimal("1.05"), ""),
            ("Viscosidade", "cP", Decimal("2000"), Decimal("6000"), ""),
            ("Aparência", "", None, None, "Límpido, homogêneo, sem partículas"),
            ("Odor", "", None, None, "Característico da fragrância"),
        ]
        for nome, unidade, minimo, maximo, texto in dados:
            TipoAnalise.objects.update_or_create(
                nome=nome,
                defaults={
                    "unidade": unidade,
                    "valor_minimo": minimo,
                    "valor_maximo": maximo,
                    "referencia_texto": texto,
                    "ativo": True,
                },
            )
        self.stdout.write("✓ Tipos de análise")

    def _formulas(self):
        item = self._itens_de_cadastro()
        receitas = {
            ("PA-001", "Padrão"): (Decimal("500"), [
                (item["MP-TENSO-ANF"], "60"),
                (item["MP-ALOE"], "10"),
                (item["EMB-FR-250"], "500"),
                (item["EMB-VALV-28"], "500"),
                (item["EMB-ROT-SAB"], "500"),
            ]),
            ("PA-002", "Padrão"): (Decimal("300"), [
                (item["MP-BASE-CREME"], "140"),
                (item["MP-FRAG-LAV"], "6"),
                (item["EMB-FR-300"], "300"),
                (item["EMB-VALV-28"], "300"),
            ]),
            ("PA-003", "Padrão"): (Decimal("400"), [
                (item["MP-TENSO-ANF"], "55"),
                (item["MP-OLEO-ARG"], "8"),
                (item["EMB-FR-300"], "400"),
                (item["EMB-VALV-28"], "400"),
            ]),
            ("PA-005", "Padrão"): (Decimal("300"), [
                (item["MP-BASE-CREME"], "25"),
                (item["EMB-TMP-24"], "300"),
            ]),
        }
        self.formulas = {}
        for (codigo_produto, nome), (rendimento, componentes) in receitas.items():
            formula, _ = Formula.objects.update_or_create(
                produto=Produto.objects.get(codigo=codigo_produto),
                nome=nome,
                status=StatusFormula.VIGENTE,
                defaults={
                    "rendimento": rendimento,
                    "aprovada_por": self.usuarios["ana.pcp"],
                    "aprovada_em": self.agora,
                    "criado_por": self.usuarios["ana.pcp"],
                    "atualizado_por": self.usuarios["ana.pcp"],
                },
            )
            formula.componentes.all().delete()
            for material, quantidade in componentes:
                componente = ComponenteFormula(
                    formula=formula, quantidade=Decimal(quantidade)
                )
                if isinstance(material, MateriaPrima):
                    componente.materia_prima = material
                else:
                    componente.embalagem = material
                componente.save()
            self.formulas[codigo_produto] = formula
        self.stdout.write("✓ Fórmulas com componentes")

    def _recebimentos_e_quarentena(self):
        item = self._itens_de_cadastro()
        jose = self.usuarios["jose.almoxarife"]
        paula = self.usuarios["paula.qualidade"]

        notas = [
            # (dias atrás, fornecedor, NF, itens, decisões)
            (12, "Essencia Brasil", "10234", [
                (item["MP-FRAG-LAV"], "40", "FRAG-2026-08", 240, "liberar", "Almoxarifado MP"),
                (item["MP-OLEO-ARG"], "30", "ARG-2026-05", 180, "liberar", "Almoxarifado MP"),
            ]),
            (9, "Quimica Pura", "88712", [
                (item["MP-TENSO-ANF"], "400", "TENSO-114", 365, "liberar", "Almoxarifado MP"),
                (item["MP-BASE-CREME"], "350", "BASE-2201", 300, "liberar", "Almoxarifado MP"),
                (item["MP-ALOE"], "60", "ALOE-77", 20, "liberar", "Almoxarifado MP"),
            ]),
            (6, "Packline", "5566", [
                (item["EMB-FR-250"], "3000", "PL-250-A", None, "liberar", "Almoxarifado Embalagens"),
                (item["EMB-VALV-28"], "2500", "PL-VLV-B", None, "liberar", "Almoxarifado Embalagens"),
                (item["EMB-FR-300"], "2000", "PL-300-C", None, "liberar", "Almoxarifado Embalagens"),
                (item["EMB-TMP-24"], "2000", "PL-TMP-D", None, "liberar", "Almoxarifado Embalagens"),
                (item["EMB-ROT-SAB"], "4000", "GR-ROT-1", None, "liberar", "Almoxarifado Embalagens"),
            ]),
            (2, "Essencia Brasil", "10412", [
                (item["MP-FRAG-LAV"], "25", "FRAG-2026-09", 300, "pendente", None),
                (item["MP-OLEO-ARG"], "20", "ARG-2026-06", 200, "bloquear", None),
                (item["MP-ALOE"], "15", "ALOE-78", 90, "reprovar", None),
            ]),
        ]

        self.lotes = {}
        for dias_atras, fornecedor_nome, nf, itens in notas:
            data = self.hoje - timedelta(days=dias_atras)
            fornecedor = Fornecedor.objects.filter(
                nome_fantasia=fornecedor_nome
            ).first()
            recebimento = Recebimento.objects.create(
                fornecedor=fornecedor,
                nota_fiscal=nf,
                data_recebimento=data,
                observacoes=f"{MARCADOR} carga de demonstração",
                criado_por=jose,
                atualizado_por=jose,
            )
            for material, qtd, lote_codigo, dias_validade, decisao, destino in itens:
                lote = self._lote(material, lote_codigo, dias_validade)
                campo = self._campo(material)
                item_recebido = ItemRecebimento.objects.create(
                    recebimento=recebimento,
                    lote=lote,
                    quantidade=Decimal(qtd),
                    **{campo: material},
                )
                self._mover(
                    TipoMovimentacao.ENTRADA, material, qtd,
                    destino=self.quarentena, lote=lote,
                    motivo=f"Recebimento {recebimento.numero}",
                    documento=f"NF {nf}", usuario=jose,
                    dias_atras=dias_atras,
                )

                if decisao == "liberar":
                    self._mover(
                        TipoMovimentacao.TRANSFERENCIA, material, qtd,
                        origem=self.quarentena, destino=self.locais[destino],
                        lote=lote,
                        motivo=f"Liberação da quarentena — {recebimento.numero}",
                        documento=f"NF {nf}", usuario=paula,
                        dias_atras=dias_atras - 1,
                    )
                    item_recebido.status = StatusQuarentena.LIBERADO
                    item_recebido.save()
                    DecisaoQuarentena.objects.create(
                        item=item_recebido,
                        decisao=StatusQuarentena.LIBERADO,
                        responsavel=paula,
                        local_destino=self.locais[destino],
                    )
                elif decisao == "bloquear":
                    item_recebido.status = StatusQuarentena.BLOQUEADO
                    item_recebido.save()
                    DecisaoQuarentena.objects.create(
                        item=item_recebido,
                        decisao=StatusQuarentena.BLOQUEADO,
                        responsavel=paula,
                        observacoes="Aguardando COA complementar do fornecedor.",
                    )
                elif decisao == "reprovar":
                    item_recebido.status = StatusQuarentena.REPROVADO
                    item_recebido.save()
                    DecisaoQuarentena.objects.create(
                        item=item_recebido,
                        decisao=StatusQuarentena.REPROVADO,
                        responsavel=paula,
                        observacoes="Coloração fora de especificação — devolver.",
                    )

        self._analises()
        self.stdout.write("✓ Recebimentos, quarentena e análises")

    def _analises(self):
        paula = self.usuarios["paula.qualidade"]
        ph = TipoAnalise.objects.get(nome="pH")
        aparencia = TipoAnalise.objects.get(nome="Aparência")

        aprovada = Analise.objects.create(
            lote=self.lotes["FRAG-2026-08"],
            status=StatusAnalise.APROVADA,
            decidido_por=paula,
            decidido_em=self.agora - timedelta(days=11),
            parecer="Dentro das especificações.",
            criado_por=paula,
            atualizado_por=paula,
        )
        ResultadoAnalise.objects.create(
            analise=aprovada, tipo=ph, valor_numerico=Decimal("6.2")
        )
        ResultadoAnalise.objects.create(
            analise=aprovada, tipo=aparencia, valor_texto="Límpido, sem partículas"
        )

        reprovada = Analise.objects.create(
            lote=self.lotes["ALOE-78"],
            status=StatusAnalise.REPROVADA,
            decidido_por=paula,
            decidido_em=self.agora - timedelta(days=1),
            parecer="pH acima da faixa e coloração alterada. Lote reprovado.",
            criado_por=paula,
            atualizado_por=paula,
        )
        ResultadoAnalise.objects.create(
            analise=reprovada, tipo=ph, valor_numerico=Decimal("8.3")
        )

        em_analise = Analise.objects.create(
            lote=self.lotes["FRAG-2026-09"],
            observacoes="Aguardando resultado de viscosidade.",
            criado_por=paula,
            atualizado_por=paula,
        )
        ResultadoAnalise.objects.create(
            analise=em_analise, tipo=ph, valor_numerico=Decimal("6.4")
        )

    def _estoque_extra(self):
        # Lote vencido encontrado em inventário — alimenta o alerta de validade
        aloe = MateriaPrima.objects.get(codigo="MP-ALOE")
        lote_vencido = self._lote(aloe, "ALOE-VENC-24", -30)
        self._mover(
            TipoMovimentacao.AJUSTE_ENTRADA, aloe, "5",
            destino=self.locais["Almoxarifado MP"], lote=lote_vencido,
            motivo="Sobra encontrada no inventário",
            documento="INV-2026-07",
            usuario=self.usuarios["jose.almoxarife"],
            dias_atras=4,
        )
        self.stdout.write("✓ Estoque extra (lote vencido para o alerta)")

    def _pedidos_e_fluxo(self):
        ana = self.usuarios["ana.pcp"]
        diretor = self.usuarios["diretor"]
        marcos = self.usuarios["marcos.producao"]
        produto = {p.codigo: p for p in Produto.objects.all()}
        cliente = {c.nome_fantasia: c for c in Cliente.objects.all()}
        equipamento = {e.codigo: e for e in Equipamento.objects.all()}

        def novo_pedido(dias_atras, nome_cliente, itens, prazo_em_dias, obs=""):
            pedido = Pedido.objects.create(
                cliente=cliente[nome_cliente],
                prazo=self.hoje + timedelta(days=prazo_em_dias),
                observacoes=f"{MARCADOR} {obs}".strip(),
                criado_por=diretor,
                atualizado_por=diretor,
            )
            for codigo, qtd in itens:
                ItemPedido.objects.create(
                    pedido=pedido, produto=produto[codigo], quantidade=Decimal(qtd)
                )
            HistoricoPedido.registrar(pedido, diretor, "Pedido criado")
            Pedido.objects.filter(pk=pedido.pk).update(
                criado_em=self.agora - timedelta(days=dias_atras)
            )
            return pedido

        def avancar(pedido, *status_alvo, usuario=ana, motivo=""):
            for status in status_alvo:
                pedido.transicionar(status, usuario, motivo=motivo)

        # 1) Recebido hoje
        novo_pedido(0, "Studio Belle", [("PA-001", "600"), ("PA-002", "200")], 20)

        # 2) Em análise
        p2 = novo_pedido(2, "Primavera Farma", [("PA-005", "300")], 15)
        avancar(p2, StatusPedido.EM_ANALISE)

        # 3) Aguardando MP (óleo de argan bloqueado na quarentena)
        p3 = novo_pedido(4, "Natural do Vale", [("PA-003", "400"), ("PA-004", "400")], 18,
                         obs="Aguardando liberação do óleo de argan.")
        avancar(p3, StatusPedido.EM_ANALISE, StatusPedido.AGUARDANDO_MP)

        # 4) Programado, com programações no calendário (uma com sobrecarga)
        p4 = novo_pedido(6, "Aroma Sul", [("PA-002", "300"), ("PA-005", "250")], 10)
        avancar(p4, StatusPedido.EM_ANALISE, StatusPedido.PROGRAMADO)
        itens_p4 = list(p4.itens.all())
        Programacao.objects.create(
            item=itens_p4[0], equipamento=equipamento["EQ-REATOR-01"],
            operador=marcos, data=self.hoje + timedelta(days=3),
            quantidade=Decimal("300"), criado_por=ana, atualizado_por=ana,
        )
        # Mesmo dia e equipamento: 300 + 250 = 550 > capacidade 500 → sobrecarga
        Programacao.objects.create(
            item=itens_p4[1], equipamento=equipamento["EQ-REATOR-01"],
            operador=marcos, data=self.hoje + timedelta(days=3),
            quantidade=Decimal("250"), criado_por=ana, atualizado_por=ana,
        )

        # 5) Em produção agora (OP iniciada hoje, com parada e ocorrência)
        p5 = novo_pedido(10, "Studio Belle", [("PA-001", "500")], 6)
        avancar(p5, StatusPedido.EM_ANALISE, StatusPedido.PROGRAMADO)
        op5 = self._op_liberada(p5.itens.first(), "EQ-ENV-01", marcos, dias=0)
        execucao = ExecucaoOP.iniciar(op5, marcos)
        ExecucaoOP.objects.filter(pk=execucao.pk).update(
            iniciado_em=self.agora - timedelta(hours=3)
        )
        Parada.objects.create(
            execucao=execucao, motivo="SETUP",
            inicio=self.agora - timedelta(hours=2, minutes=30),
            fim=self.agora - timedelta(hours=2, minutes=5),
            observacoes="Troca de bico de envase",
            registrado_por=marcos,
        )
        Ocorrencia.objects.create(
            execucao=execucao,
            descricao="Viscosidade levemente acima do padrão, dentro da tolerância.",
            registrado_por=marcos,
        )

        # 6) CQ: OP concluída ontem, análise do lote produzido em andamento
        p6 = novo_pedido(14, "Primavera Farma", [("PA-003", "400")], -2,
                         obs="Prazo estourado — priorizar expedição.")
        avancar(p6, StatusPedido.EM_ANALISE, StatusPedido.PROGRAMADO)
        op6 = self._op_liberada(p6.itens.first(), "EQ-MIST-02", marcos, dias=1)
        self._produzir(op6, marcos, "392", "8", "PA3-2026-011", dias_atras=1)
        avancar(p6, StatusPedido.CQ, usuario=marcos)
        analise_pa3 = Analise.objects.create(
            lote=self.lotes["PA3-2026-011"],
            observacoes="Análise do lote produzido.",
            criado_por=self.usuarios["paula.qualidade"],
            atualizado_por=self.usuarios["paula.qualidade"],
        )
        ResultadoAnalise.objects.create(
            analise=analise_pa3,
            tipo=TipoAnalise.objects.get(nome="pH"),
            valor_numerico=Decimal("6.1"),
        )

        # 7) Expedido: ciclo completo com saída de expedição
        p7 = novo_pedido(20, "Aroma Sul", [("PA-001", "500")], -5)
        avancar(p7, StatusPedido.EM_ANALISE, StatusPedido.PROGRAMADO)
        op7 = self._op_liberada(p7.itens.first(), "EQ-ENV-01", marcos, dias=7)
        self._produzir(op7, marcos, "498", "2", "PA1-2026-030", dias_atras=7)
        avancar(p7, StatusPedido.CQ, StatusPedido.FINALIZADO, usuario=marcos)
        self._mover(
            TipoMovimentacao.SAIDA, produto["PA-001"], "498",
            origem=self.locais["Produtos Acabados"],
            lote=self.lotes["PA1-2026-030"],
            motivo=f"Expedição {p7.numero}",
            documento=p7.numero,
            usuario=self.usuarios["rita.expedicao"],
            dias_atras=5,
        )
        avancar(p7, StatusPedido.EXPEDIDO, usuario=self.usuarios["rita.expedicao"])

        # 8) Cancelado com motivo
        p8 = novo_pedido(8, "Natural do Vale", [("PA-005", "250")], 12)
        avancar(p8, StatusPedido.EM_ANALISE)
        p8.transicionar(
            StatusPedido.CANCELADO, diretor,
            motivo="Cliente adiou a campanha promocional.",
        )

        # 9) Finalizado hoje: produção do dia concluída e lote aprovado
        p9 = novo_pedido(5, "Primavera Farma", [("PA-005", "300")], 8)
        avancar(p9, StatusPedido.EM_ANALISE, StatusPedido.PROGRAMADO)
        op9 = self._op_liberada(p9.itens.first(), "EQ-MIST-02", marcos, dias=0)
        self._produzir(op9, marcos, "297", "3", "PA5-2026-018", dias_atras=0)
        avancar(p9, StatusPedido.CQ, usuario=marcos)
        analise_pa5 = Analise.objects.create(
            lote=self.lotes["PA5-2026-018"],
            status=StatusAnalise.APROVADA,
            decidido_por=self.usuarios["paula.qualidade"],
            decidido_em=self.agora,
            parecer="Lote aprovado para expedição.",
            criado_por=self.usuarios["paula.qualidade"],
            atualizado_por=self.usuarios["paula.qualidade"],
        )
        ResultadoAnalise.objects.create(
            analise=analise_pa5,
            tipo=TipoAnalise.objects.get(nome="pH"),
            valor_numerico=Decimal("6.0"),
        )
        avancar(p9, StatusPedido.FINALIZADO, usuario=self.usuarios["paula.qualidade"])

        # OP em rascunho com pendência no checklist (sem operador)
        op_rascunho = OrdemProducao.objects.create(
            item_pedido=itens_p4[0],
            formula=self.formulas["PA-002"],
            quantidade=Decimal("300"),
            equipamento=equipamento["EQ-REATOR-01"],
            data_programada=self.hoje + timedelta(days=3),
            observacoes=f"{MARCADOR} definir operador antes de liberar",
            criado_por=ana,
            atualizado_por=ana,
        )
        op_rascunho.gerar_materiais()
        HistoricoOP.registrar(op_rascunho, ana, "OP emitida")

        self.stdout.write("✓ Pedidos, PCP, OPs e produção")

    # ------------------------------------------------------------------ apoio

    def _op_liberada(self, item_pedido, codigo_equipamento, operador, dias):
        ana = self.usuarios["ana.pcp"]
        ordem = OrdemProducao.objects.create(
            item_pedido=item_pedido,
            formula=self.formulas[item_pedido.produto.codigo],
            quantidade=item_pedido.quantidade,
            equipamento=Equipamento.objects.get(codigo=codigo_equipamento),
            operador=operador,
            data_programada=self.hoje - timedelta(days=dias),
            status=StatusOP.LIBERADA,
            liberado_por=ana,
            liberado_em=self.agora - timedelta(days=dias, hours=2),
            criado_por=ana,
            atualizado_por=ana,
        )
        ordem.gerar_materiais()
        lote = ordem.reservar_lote_produto(ana)
        SnapshotFormulaOP.congelar(ordem, ana)
        AtividadeOP.registrar(
            ordem, TipoAtividadeOP.LIBERACAO, ana, "OP liberada para produção"
        )
        AtividadeOP.registrar(
            ordem,
            TipoAtividadeOP.ATRIBUICAO_LOTE,
            ana,
            f"Lote interno {lote.codigo} reservado",
        )
        HistoricoOP.registrar(ordem, ana, "OP emitida")
        HistoricoOP.registrar(
            ordem,
            ana,
            f"OP liberada para produção — lote interno {lote.codigo} reservado",
        )
        return ordem

    def _produzir(self, ordem, operador, produzido, perdas, chave_lote, dias_atras):
        """`chave_lote` é só a chave em self.lotes — o código interno é automático."""
        execucao = ExecucaoOP.iniciar(ordem, operador)
        execucao.concluir(
            usuario=operador,
            quantidade_produzida=Decimal(produzido),
            perdas=Decimal(perdas),
            validade=self.hoje + timedelta(days=540),
            local_destino=self.locais["Produtos Acabados"],
        )
        inicio = self.agora - timedelta(days=dias_atras, hours=6)
        fim = self.agora - timedelta(days=dias_atras, hours=1)
        ExecucaoOP.objects.filter(pk=execucao.pk).update(
            iniciado_em=inicio, concluido_em=fim
        )
        self.lotes[chave_lote] = execucao.lote_produzido

    def _lote(self, material, lote_fornecedor, dias_validade):
        """
        Lote com código interno automático; o código "de demonstração"
        vira o lote do fornecedor e continua sendo a chave em self.lotes.
        """
        from apps.estoque.models import criar_lote_interno

        validade = (
            self.hoje + timedelta(days=dias_validade)
            if dias_validade is not None
            else None
        )
        lote = next(
            (
                existente
                for existente in self.lotes.values()
                if existente.lote_fornecedor == lote_fornecedor
                and existente.item == material
            ),
            None,
        )
        if lote is None:
            lote = criar_lote_interno(
                material,
                self.usuarios["jose.almoxarife"],
                validade=validade,
                lote_fornecedor=lote_fornecedor,
            )
        self.lotes[lote_fornecedor] = lote
        return lote

    def _mover(self, tipo, material, quantidade, *, usuario, motivo,
               documento="", origem=None, destino=None, lote=None, dias_atras=0):
        campo = self._campo(material)
        movimentacao = Movimentacao(
            tipo=tipo,
            quantidade=Decimal(quantidade),
            local_origem=origem,
            local_destino=destino,
            lote=lote,
            motivo=motivo,
            documento=documento,
            criado_por=usuario,
            atualizado_por=usuario,
            **{campo: material},
        )
        movimentacao.full_clean()
        movimentacao.save()
        if dias_atras:
            Movimentacao.objects.filter(pk=movimentacao.pk).update(
                criado_em=self.agora - timedelta(days=dias_atras)
            )
        return movimentacao

    @staticmethod
    def _campo(material):
        if isinstance(material, Produto):
            return "produto"
        if isinstance(material, MateriaPrima):
            return "materia_prima"
        if isinstance(material, Embalagem):
            return "embalagem"
        raise TypeError(material)

    def _itens_de_cadastro(self):
        itens = {}
        for modelo in (MateriaPrima, Embalagem):
            for objeto in modelo.objects.all():
                itens[objeto.codigo] = objeto
        return itens

    def _resumo(self):
        linhas = [
            ("Pedidos", Pedido.objects.count()),
            ("Recebimentos", Recebimento.objects.count()),
            ("Movimentações de estoque", Movimentacao.objects.count()),
            ("Lotes", Lote.objects.count()),
            ("Análises", Analise.objects.count()),
            ("Programações PCP", Programacao.objects.count()),
            ("Ordens de produção", OrdemProducao.objects.count()),
            ("Execuções de produção", ExecucaoOP.objects.count()),
        ]
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demonstração carregada!"))
        for nome, total in linhas:
            self.stdout.write(f"  {nome}: {total}")
        self.stdout.write("")
        self.stdout.write("Usuários de demonstração (senha: fabriq.demo):")
        for username, nome, sobrenome, perfil in USUARIOS_DEMO:
            self.stdout.write(f"  {username.upper():18} {nome} {sobrenome} · {perfil}")
