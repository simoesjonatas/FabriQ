"""
Produção (Fase 9 + Etapa 4 do plano de correções).

A execução de uma Ordem de Produção liberada é registrada aqui:
início, paradas (com motivo), ocorrências, fotos, apontamento de lotes
e conclusão.

O consumo de materiais é APONTADO POR LOTE pelo operador
(`ConsumoMaterialOP`) — o sistema sugere FEFO, mas quem confirma quais
lotes físicos foram usados é a produção. Ao CONCLUIR, em transação
atômica, o estoque é baixado a partir dos consumos apontados (uma
movimentação de SAÍDA por lote/local) e o produto acabado entra no lote
interno reservado na liberação.

Movimentações de estoque são imutáveis (Fase 5): uma vez concluída, a
execução não é editada — eventuais correções são novas movimentações.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.auditoria.models import TrilhaImutavelError
from apps.cadastros.itens import campo_do_item
from apps.core import formatos
from apps.core.models import ModeloAuditado
from apps.estoque.models import (
    LocalEstoque,
    Lote,
    Movimentacao,
    SituacaoLote,
    TipoMovimentacao,
    posicoes_para_consumo,
)
from apps.ordens.models import MaterialOP, OrdemProducao, StatusOP
from apps.pedidos.models import HistoricoPedido, StatusPedido


class TipoAtividadeOP(models.TextChoices):
    LIBERACAO = "LIBERACAO", "Liberação da OP"
    ATRIBUICAO_LOTE = "ATRIBUICAO_LOTE", "Atribuição de lote"
    SEPARACAO = "SEPARACAO", "Separação de materiais"
    PRODUCAO = "PRODUCAO", "Produção"
    ENVASE = "ENVASE", "Envase"
    CONFERENCIA = "CONFERENCIA", "Conferência"
    OUTRO = "OUTRO", "Outro"


# Atividades que o operador registra manualmente na tela da OP em
# produção; as demais são geradas pelos próprios fluxos do sistema.
ATIVIDADES_MANUAIS = [
    TipoAtividadeOP.SEPARACAO,
    TipoAtividadeOP.ENVASE,
    TipoAtividadeOP.CONFERENCIA,
    TipoAtividadeOP.OUTRO,
]


class AtividadeOPQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TrilhaImutavelError("Atividades da OP não podem ser alteradas.")

    def delete(self):
        raise TrilhaImutavelError("Atividades da OP não podem ser excluídas.")


class AtividadeOP(models.Model):
    """
    Quem fez o quê na OP (Etapa 2c do plano de correções): registro
    imutável por atividade — produção, envase, atribuição de lote,
    separação, conferência — com funcionário, data/hora e observação.
    """

    ordem = models.ForeignKey(
        OrdemProducao,
        verbose_name="ordem de produção",
        on_delete=models.PROTECT,
        related_name="atividades",
    )
    atividade = models.CharField(
        "atividade", max_length=20, choices=TipoAtividadeOP.choices
    )
    funcionario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="funcionário",
        on_delete=models.PROTECT,
        related_name="atividades_de_op",
    )
    data = models.DateTimeField("data", auto_now_add=True)
    observacao = models.CharField("observação", max_length=200, blank=True)

    objects = AtividadeOPQuerySet.as_manager()

    class Meta:
        verbose_name = "atividade da OP"
        verbose_name_plural = "atividades da OP"
        ordering = ["data", "id"]

    def __str__(self) -> str:
        return f"{self.get_atividade_display()} · {self.ordem.numero} · {self.funcionario}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TrilhaImutavelError("Atividades da OP não podem ser alteradas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TrilhaImutavelError("Atividades da OP não podem ser excluídas.")

    @classmethod
    def registrar(cls, ordem, atividade, funcionario, observacao=""):
        return cls.objects.create(
            ordem=ordem,
            atividade=atividade,
            funcionario=funcionario,
            observacao=observacao,
        )


def posicoes_para_apontamento(item) -> list[dict]:
    """
    Todas as posições fora da Quarentena e com lote, para a tela de
    apontamento. Cada posição traz `bloqueio`: o motivo pelo qual o lote
    não pode ser consumido (vencido, reprovado, bloqueado...) ou "" se
    está apto. Lotes bloqueados aparecem, mas só entram com exceção
    autorizada (Etapa 5). Ordenadas em FEFO.
    """
    from apps.recebimento.models import local_quarentena

    return [
        {**posicao, "bloqueio": posicao["lote"].motivo_bloqueio_consumo()}
        for posicao in posicoes_para_consumo(item, excluir_local=local_quarentena())
        if posicao["lote"] is not None
    ]


def posicoes_consumiveis(item) -> list[dict]:
    """
    Posições APTAS ao consumo (sem bloqueio): fora da Quarentena, com
    lote, validade em dia e situação que permite consumo (Etapa 5).
    """
    return [
        posicao
        for posicao in posicoes_para_apontamento(item)
        if not posicao["bloqueio"]
    ]


def sugerir_consumos_fefo(ordem) -> dict[int, list[dict]]:
    """
    Sugestão FEFO por material da OP: {material_id: [{"lote", "local",
    "saldo", "quantidade"}]}, cortada na quantidade necessária. Posições
    além do necessário vêm com quantidade 0 (o operador decide).
    """
    sugestoes: dict[int, list[dict]] = {}
    for material in ordem.materiais.all():
        restante = material.quantidade_necessaria
        linhas = []
        for posicao in posicoes_consumiveis(material.item):
            usar = min(restante, posicao["saldo"]) if restante > 0 else Decimal("0")
            linhas.append({**posicao, "quantidade": usar})
            restante -= usar
        sugestoes[material.pk] = linhas
    return sugestoes


class ConsumoQuerySet(models.QuerySet):
    def delete(self):
        if self.filter(movimentacao__isnull=False).exists():
            raise TrilhaImutavelError(
                "Consumo já confirmado na conclusão não pode ser excluído."
            )
        return super().delete()

    def update(self, **kwargs):
        raise TrilhaImutavelError(
            "Consumos não são editados em massa — reaponte os lotes."
        )


class ConsumoMaterialOP(models.Model):
    """
    Consumo REAL apontado por lote (Etapa 4, PDF 2.1/5.2): qual lote,
    de qual local e quanto. Antes da conclusão é um plano reapontável;
    depois que a `movimentacao` de saída é gerada, torna-se imutável.
    """

    material = models.ForeignKey(
        MaterialOP,
        verbose_name="material da OP",
        on_delete=models.PROTECT,
        related_name="consumos",
    )
    lote = models.ForeignKey(
        Lote,
        verbose_name="lote",
        on_delete=models.PROTECT,
        related_name="consumos_em_op",
    )
    local = models.ForeignKey(
        LocalEstoque,
        verbose_name="local de origem",
        on_delete=models.PROTECT,
        related_name="+",
    )
    quantidade = models.DecimalField(
        "quantidade",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    movimentacao = models.ForeignKey(
        Movimentacao,
        verbose_name="movimentação de saída",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        help_text="Preenchida na conclusão da OP — confirma a baixa do estoque.",
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrado por",
        on_delete=models.PROTECT,
        related_name="+",
    )
    registrado_em = models.DateTimeField("registrado em", auto_now_add=True)

    objects = ConsumoQuerySet.as_manager()

    class Meta:
        verbose_name = "consumo de material da OP"
        verbose_name_plural = "consumos de material da OP"
        ordering = ["material_id", "lote__validade", "id"]

    def __str__(self) -> str:
        return (
            f"{self.material.item.codigo} · lote {self.lote.codigo} × "
            f"{formatos.quantidade(self.quantidade)}"
        )

    def save(self, *args, **kwargs):
        if self.pk is not None:
            ja_confirmado = ConsumoMaterialOP.objects.filter(
                pk=self.pk, movimentacao__isnull=False
            ).exists()
            if ja_confirmado:
                raise TrilhaImutavelError(
                    "Consumo já confirmado na conclusão não pode ser alterado."
                )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.confirmado:
            raise TrilhaImutavelError(
                "Consumo já confirmado na conclusão não pode ser excluído."
            )
        super().delete(*args, **kwargs)

    @property
    def confirmado(self) -> bool:
        return self.movimentacao_id is not None


def apontar_consumos(ordem, usuario, linhas, excecoes=None) -> list[ConsumoMaterialOP]:
    """
    Substitui o apontamento (não confirmado) da OP pelas `linhas`:
    [(material, lote, local, quantidade)]. Valida posição, situação do
    lote (Etapa 5) e saldo. Deve rodar dentro de transaction.atomic.

    `excecoes`: {lote_pk: justificativa} para lotes BLOQUEADOS que um
    usuário autorizado liberou — a view faz o controle de permissão.
    Cada exceção usada grava um RegistroAuditoria "exceção de bloqueio".
    """
    from apps.auditoria import servicos as auditoria
    from apps.auditoria.models import AcaoAuditoria

    excecoes = excecoes or {}
    erros = []
    excecoes_usadas = []
    posicoes_por_material: dict[int, dict] = {}
    for material, lote, local, quantidade in linhas:
        if material.pk not in posicoes_por_material:
            posicoes_por_material[material.pk] = {
                (posicao["lote"].pk, posicao["local"].pk): posicao
                for posicao in posicoes_para_apontamento(material.item)
            }
        posicao = posicoes_por_material[material.pk].get((lote.pk, local.pk))
        if posicao is None:
            erros.append(
                f"Lote {lote.codigo} em {local} não está disponível para "
                f"{material.item.codigo} (em quarentena ou sem saldo)."
            )
            continue
        if posicao["bloqueio"]:
            justificativa = (excecoes.get(lote.pk) or "").strip()
            if not justificativa:
                erros.append(
                    f"{material.item.codigo}: {posicao['bloqueio']}."
                )
                continue
            excecoes_usadas.append((lote, posicao["bloqueio"], justificativa))
        if quantidade > posicao["saldo"]:
            erros.append(
                f"Lote {lote.codigo} em {local}: apontado "
                f"{formatos.quantidade(quantidade)}, saldo "
                f"{formatos.quantidade(posicao['saldo'])}."
            )
    if erros:
        raise ValidationError(erros)

    ConsumoMaterialOP.objects.filter(
        material__ordem=ordem, movimentacao__isnull=True
    ).delete()
    consumos = [
        ConsumoMaterialOP.objects.create(
            material=material,
            lote=lote,
            local=local,
            quantidade=quantidade,
            registrado_por=usuario,
        )
        for material, lote, local, quantidade in linhas
    ]
    for lote, bloqueio, justificativa in excecoes_usadas:
        auditoria.registrar_evento(
            lote,
            AcaoAuditoria.EXCECAO_BLOQUEIO,
            usuario,
            justificativa=justificativa,
            campo="consumo com bloqueio",
            valor_anterior=bloqueio,
            valor_novo=f"consumo autorizado na {ordem.numero}",
        )
    return consumos


def apontar_consumos_fefo(ordem, usuario) -> list[ConsumoMaterialOP]:
    """Apontamento automático pela sugestão FEFO (usado pela demo)."""
    sugestoes = sugerir_consumos_fefo(ordem)
    linhas = [
        (material, sugestao["lote"], sugestao["local"], sugestao["quantidade"])
        for material in ordem.materiais.all()
        for sugestao in sugestoes[material.pk]
        if sugestao["quantidade"] > 0
    ]
    return apontar_consumos(ordem, usuario, linhas)


class ExecucaoOP(ModeloAuditado):
    ordem = models.OneToOneField(
        OrdemProducao,
        verbose_name="ordem de produção",
        on_delete=models.PROTECT,
        related_name="execucao",
    )
    iniciado_em = models.DateTimeField("início da produção", default=timezone.now)
    iniciado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="iniciada por",
        on_delete=models.PROTECT,
        related_name="+",
    )
    concluido_em = models.DateTimeField("fim da produção", null=True, blank=True)
    concluido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="concluída por",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    quantidade_produzida = models.DecimalField(
        "quantidade produzida",
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
    )
    perdas = models.DecimalField(
        "perdas", max_digits=12, decimal_places=3, default=Decimal("0")
    )
    lote_produzido = models.ForeignKey(
        Lote,
        verbose_name="lote do produto acabado",
        on_delete=models.PROTECT,
        related_name="execucoes",
        null=True,
        blank=True,
    )
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "execução da produção"
        verbose_name_plural = "execuções da produção"
        ordering = ["-iniciado_em", "-id"]

    def __str__(self) -> str:
        return f"Execução de {self.ordem.numero}"

    @property
    def concluida(self) -> bool:
        return self.concluido_em is not None

    @property
    def tempo_paradas(self) -> timedelta:
        total = timedelta()
        for parada in self.paradas.all():
            total += parada.duracao
        return total

    @property
    def tempo_total(self) -> timedelta:
        fim = self.concluido_em or timezone.now()
        return fim - self.iniciado_em

    @property
    def tempo_produtivo(self) -> timedelta:
        produtivo = self.tempo_total - self.tempo_paradas
        return produtivo if produtivo > timedelta() else timedelta()

    @property
    def tem_parada_aberta(self) -> bool:
        return self.paradas.filter(fim__isnull=True).exists()

    @classmethod
    def iniciar(cls, ordem, usuario) -> ExecucaoOP:
        """Inicia a produção de uma OP liberada e move o pedido."""
        if ordem.status != StatusOP.LIBERADA:
            raise ValidationError(
                f"A OP {ordem.numero} precisa estar “Liberada” para iniciar a produção."
            )

        execucao = cls.objects.create(
            ordem=ordem,
            iniciado_por=usuario,
            criado_por=usuario,
            atualizado_por=usuario,
        )
        ordem.status = StatusOP.EM_PRODUCAO
        ordem.atualizado_por = usuario
        ordem.save()

        AtividadeOP.registrar(
            ordem, TipoAtividadeOP.PRODUCAO, usuario, "Produção iniciada"
        )

        pedido = ordem.pedido
        if pedido.status == StatusPedido.PROGRAMADO:
            pedido.transicionar(StatusPedido.EM_PRODUCAO, usuario)
        else:
            HistoricoPedido.registrar(
                pedido=pedido,
                usuario=usuario,
                descricao=f"Produção iniciada pela OP {ordem.numero}",
            )
        return execucao

    def concluir(
        self,
        *,
        usuario,
        quantidade_produzida,
        perdas,
        validade,
        local_destino,
        justificativa_divergencia="",
    ) -> None:
        """
        Conclui a produção baixando o estoque a partir dos CONSUMOS
        APONTADOS por lote (Etapa 4) e dá entrada do produto acabado no
        lote interno reservado na liberação. Deve rodar dentro de uma
        transação (a view garante transaction.atomic).
        """
        from apps.auditoria import servicos as auditoria
        from apps.auditoria.models import AcaoAuditoria
        from apps.ordens.models import HistoricoOP

        if self.ordem.status != StatusOP.EM_PRODUCAO:
            raise ValidationError("A produção não está em andamento.")

        documento = self.ordem.numero
        materiais = list(
            self.ordem.materiais.select_related("materia_prima", "embalagem")
        )
        consumos = list(
            ConsumoMaterialOP.objects.filter(
                material__ordem=self.ordem, movimentacao__isnull=True
            ).select_related("material", "lote", "local")
        )
        consumos_por_material: dict[int, list[ConsumoMaterialOP]] = {}
        for consumo in consumos:
            consumos_por_material.setdefault(consumo.material_id, []).append(consumo)

        # Bloqueio: nenhum material pode ficar sem lote apontado (PDF 2.1)
        sem_lote = [
            material.item.codigo
            for material in materiais
            if material.pk not in consumos_por_material
        ]
        if sem_lote:
            raise ValidationError(
                "Aponte os lotes consumidos antes de concluir. "
                "Sem lote: " + ", ".join(sem_lote) + "."
            )

        # A elegibilidade do lote (situação, validade, exceção autorizada)
        # é controlada no APONTAMENTO — a conclusão apenas efetiva a baixa
        # dos consumos já apontados.

        # Divergência entre apontado e necessário exige justificativa
        divergentes = []
        for material in materiais:
            apontado = sum(
                (c.quantidade for c in consumos_por_material[material.pk]),
                Decimal("0"),
            )
            if apontado != material.quantidade_necessaria:
                divergentes.append(
                    f"{material.item.codigo} (necessário "
                    f"{formatos.quantidade(material.quantidade_necessaria)}, "
                    f"apontado {formatos.quantidade(apontado)})"
                )
        if divergentes and not justificativa_divergencia.strip():
            raise ValidationError(
                "A quantidade apontada difere do necessário em: "
                + "; ".join(divergentes)
                + ". Informe a justificativa da divergência para concluir."
            )

        for consumo in consumos:
            item = consumo.material.item
            movimentacao = Movimentacao(
                tipo=TipoMovimentacao.SAIDA,
                lote=consumo.lote,
                quantidade=consumo.quantidade,
                local_origem=consumo.local,
                motivo=f"Consumo na produção {self.ordem.numero}",
                documento=documento,
                criado_por=usuario,
                atualizado_por=usuario,
                **{campo_do_item(item): item},
            )
            movimentacao.full_clean()
            movimentacao.save()
            consumo.movimentacao = movimentacao
            consumo.save()

        if divergentes:
            auditoria.registrar_evento(
                self.ordem,
                AcaoAuditoria.ALTERACAO,
                usuario,
                justificativa=justificativa_divergencia.strip(),
                campo="consumo apontado",
                valor_novo="Divergência do necessário: " + "; ".join(divergentes),
            )

        produto = self.ordem.produto
        # OPs liberadas antes da automação do lote interno não têm
        # reserva — o lote é gerado agora, pela mesma sequência.
        sem_lote_reservado = self.ordem.lote_produto_id is None
        lote_produto = self.ordem.reservar_lote_produto(usuario)
        if sem_lote_reservado:
            AtividadeOP.registrar(
                self.ordem,
                TipoAtividadeOP.ATRIBUICAO_LOTE,
                usuario,
                f"Lote interno {lote_produto.codigo} atribuído na conclusão",
            )
        # O produto acabado entra aguardando o CQ final (Etapa 5/8):
        # sai de "em produção" para "aguardando CQ" — não pode ser
        # expedido enquanto a Qualidade não aprovar.
        if validade and lote_produto.validade != validade:
            lote_produto.validade = validade
        lote_produto.situacao = SituacaoLote.AGUARDANDO_CQ
        lote_produto.salvar_com_usuario(usuario)
        lote_codigo = lote_produto.codigo

        entrada = Movimentacao(
            tipo=TipoMovimentacao.ENTRADA,
            produto=produto,
            lote=lote_produto,
            quantidade=quantidade_produzida,
            local_destino=local_destino,
            motivo=f"Produção concluída {self.ordem.numero}",
            documento=documento,
            criado_por=usuario,
            atualizado_por=usuario,
        )
        entrada.full_clean()
        entrada.save()

        self.quantidade_produzida = quantidade_produzida
        self.perdas = perdas
        self.lote_produzido = lote_produto
        self.concluido_em = timezone.now()
        self.concluido_por = usuario
        self.atualizado_por = usuario
        self.save()

        self.ordem.status = StatusOP.CONCLUIDA
        self.ordem.atualizado_por = usuario
        self.ordem.save()

        AtividadeOP.registrar(
            self.ordem,
            TipoAtividadeOP.PRODUCAO,
            usuario,
            f"Produção concluída no lote {lote_codigo}",
        )

        HistoricoOP.registrar(
            self.ordem,
            usuario,
            f"Produção concluída: {formatos.quantidade(quantidade_produzida)} "
            f"{produto.get_unidade_display().lower()} no lote {lote_codigo}"
            + (
                f", {formatos.quantidade(perdas)} de perdas"
                if perdas
                else ""
            ),
        )
        HistoricoPedido.registrar(
            pedido=self.ordem.pedido,
            usuario=usuario,
            descricao=(
                f"Produção da OP {self.ordem.numero} concluída "
                f"({formatos.quantidade(quantidade_produzida)} "
                f"{produto.get_unidade_display().lower()}, lote {lote_codigo})"
            ),
        )


class EtapaOP(models.Model):
    """
    Execução de uma etapa do processo (Etapa 6d, PDF 5.5): valores reais
    contra os previstos no snapshot, responsáveis e horários. Pular uma
    etapa exige justificativa (registrada aqui e na trilha).
    """

    ordem = models.ForeignKey(
        OrdemProducao,
        verbose_name="ordem de produção",
        on_delete=models.PROTECT,
        related_name="etapas_execucao",
    )
    etapa = models.ForeignKey(
        "ordens.EtapaSnapshotOP",
        verbose_name="etapa da fórmula",
        on_delete=models.PROTECT,
        related_name="execucoes",
    )
    temperatura_real = models.DecimalField(
        "temperatura real (°C)", max_digits=7, decimal_places=2, null=True, blank=True
    )
    tempo_real_min = models.DecimalField(
        "tempo real (min)", max_digits=7, decimal_places=1, null=True, blank=True
    )
    velocidade_real = models.DecimalField(
        "velocidade real (rpm)", max_digits=8, decimal_places=1, null=True, blank=True
    )
    inicio = models.DateTimeField("início", null=True, blank=True)
    termino = models.DateTimeField("término", null=True, blank=True)
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="operador",
        on_delete=models.PROTECT,
        related_name="+",
    )
    conferente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="conferente",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    pulada = models.BooleanField("etapa pulada", default=False)
    justificativa = models.TextField("justificativa", blank=True)
    observacoes = models.TextField("observações", blank=True)
    registrado_em = models.DateTimeField("registrado em", auto_now_add=True)

    class Meta:
        verbose_name = "etapa executada da OP"
        verbose_name_plural = "etapas executadas da OP"
        ordering = ["etapa__sequencia", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["ordem", "etapa"],
                name="etapa_op_unica_por_ordem",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ordem.numero} · etapa {self.etapa.sequencia}"


def registrar_etapa(
    *, ordem, etapa, operador, conferente=None, temperatura_real=None,
    tempo_real_min=None, velocidade_real=None, pulada=False,
    justificativa="", observacoes="",
) -> EtapaOP:
    """
    Registra a execução de uma etapa (Etapa 6d). Regras:
    - as etapas seguem a sequência da fórmula: só registra a próxima
      etapa ainda não executada;
    - pular uma etapa exige justificativa.
    Deve rodar em transaction.atomic.
    """
    ja_registradas = set(
        EtapaOP.objects.filter(ordem=ordem).values_list("etapa__sequencia", flat=True)
    )
    if etapa.sequencia in ja_registradas:
        raise ValidationError(f"A etapa {etapa.sequencia} já foi registrada.")

    pendentes_antes = [
        e.sequencia
        for e in ordem.snapshot_formula.etapas.all()
        if e.sequencia < etapa.sequencia and e.sequencia not in ja_registradas
    ]
    if pendentes_antes and not (pulada and justificativa.strip()):
        raise ValidationError(
            "Há etapas anteriores não executadas: "
            + ", ".join(str(s) for s in pendentes_antes)
            + ". Registre-as em ordem ou justifique o salto."
        )
    if pulada and not justificativa.strip():
        raise ValidationError("Pular uma etapa exige justificativa.")

    execucao = EtapaOP.objects.create(
        ordem=ordem,
        etapa=etapa,
        operador=operador,
        conferente=conferente,
        temperatura_real=temperatura_real,
        tempo_real_min=tempo_real_min,
        velocidade_real=velocidade_real,
        pulada=pulada,
        justificativa=justificativa.strip(),
        observacoes=observacoes,
    )
    if pulada or justificativa.strip():
        from apps.auditoria import servicos as auditoria
        from apps.auditoria.models import AcaoAuditoria

        auditoria.registrar_evento(
            ordem,
            AcaoAuditoria.ALTERACAO,
            operador,
            justificativa=justificativa.strip(),
            campo=f"etapa {etapa.sequencia}",
            valor_novo="etapa pulada" if pulada else "etapa fora de ordem",
        )
    return execucao


class ControleProcessoOP(models.Model):
    """
    Controle em processo (Etapa 6e, PDF 5.6): medição de um parâmetro
    durante a produção, comparada com a especificação DO PRODUTO. Fora da
    especificação bloqueia a etapa; nova medição não apaga a anterior
    (registros acumulam — a correção é uma nova medição).
    """

    ordem = models.ForeignKey(
        OrdemProducao,
        verbose_name="ordem de produção",
        on_delete=models.PROTECT,
        related_name="controles_processo",
    )
    etapa = models.ForeignKey(
        "ordens.EtapaSnapshotOP",
        verbose_name="etapa",
        on_delete=models.PROTECT,
        related_name="controles",
        null=True,
        blank=True,
    )
    tipo = models.ForeignKey(
        "qualidade.TipoAnalise",
        verbose_name="parâmetro",
        on_delete=models.PROTECT,
        related_name="+",
    )
    valor_minimo = models.DecimalField(
        "limite mínimo aplicado", max_digits=12, decimal_places=4,
        null=True, blank=True,
    )
    valor_maximo = models.DecimalField(
        "limite máximo aplicado", max_digits=12, decimal_places=4,
        null=True, blank=True,
    )
    resultado = models.DecimalField(
        "resultado", max_digits=12, decimal_places=4, null=True, blank=True
    )
    resultado_texto = models.CharField("resultado descritivo", max_length=200, blank=True)
    metodo = models.CharField("método", max_length=120, blank=True)
    equipamento = models.ForeignKey(
        "cadastros.Equipamento",
        verbose_name="equipamento",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    analista = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="analista",
        on_delete=models.PROTECT,
        related_name="+",
    )
    fora_especificacao = models.BooleanField("fora da especificação", default=False)
    data = models.DateTimeField("data", auto_now_add=True)

    class Meta:
        verbose_name = "controle em processo da OP"
        verbose_name_plural = "controles em processo da OP"
        ordering = ["data", "id"]

    def __str__(self) -> str:
        return f"{self.ordem.numero} · {self.tipo.nome}"


def registrar_controle(
    *, ordem, tipo, analista, etapa=None, resultado=None, resultado_texto="",
    metodo="", equipamento=None,
) -> ControleProcessoOP:
    """
    Registra um controle em processo (Etapa 6e). O limite vem da
    especificação DO PRODUTO; se não houver, cai na referência do tipo.
    Não bloqueia o registro (acumula), mas marca `fora_especificacao`.
    """
    from apps.qualidade.models import EspecificacaoProduto

    espec = EspecificacaoProduto.objects.filter(
        produto=ordem.produto, tipo=tipo
    ).first()
    if espec is not None:
        minimo, maximo = espec.valor_minimo, espec.valor_maximo
    else:
        minimo, maximo = tipo.valor_minimo, tipo.valor_maximo

    fora = False
    if resultado is not None:
        if minimo is not None and resultado < minimo:
            fora = True
        if maximo is not None and resultado > maximo:
            fora = True

    return ControleProcessoOP.objects.create(
        ordem=ordem,
        etapa=etapa,
        tipo=tipo,
        valor_minimo=minimo,
        valor_maximo=maximo,
        resultado=resultado,
        resultado_texto=resultado_texto,
        metodo=metodo,
        equipamento=equipamento,
        analista=analista,
        fora_especificacao=fora,
    )


class TipoChecklistEquipamento(models.TextChoices):
    PRE_USO = "PRE_USO", "Pré-uso"
    POS_USO = "POS_USO", "Pós-uso"


class ChecklistEquipamentoOP(models.Model):
    """Checklist de limpeza/condição do equipamento na OP (Etapa 6c, PDF 5.4)."""

    ordem = models.ForeignKey(
        OrdemProducao,
        verbose_name="ordem de produção",
        on_delete=models.PROTECT,
        related_name="checklists_equipamento",
    )
    equipamento = models.ForeignKey(
        "cadastros.Equipamento",
        verbose_name="equipamento",
        on_delete=models.PROTECT,
        related_name="+",
    )
    tipo = models.CharField(
        "tipo", max_length=10, choices=TipoChecklistEquipamento.choices
    )
    itens_verificados = models.TextField("itens verificados", blank=True)
    condicao_final = models.CharField("condição final", max_length=120, blank=True)
    danos = models.TextField("danos identificados", blank=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="responsável pela liberação",
        on_delete=models.PROTECT,
        related_name="+",
    )
    data = models.DateTimeField("data", auto_now_add=True)

    class Meta:
        verbose_name = "checklist de equipamento da OP"
        verbose_name_plural = "checklists de equipamento da OP"
        ordering = ["data", "id"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} · {self.equipamento.codigo}"


class PesagemOP(models.Model):
    """
    Pesagem de um material da OP com dupla conferência (Etapa 6b, PDF 5.3).

    Registro acumulativo (correção = nova pesagem, nunca edição). As
    regras (balança calibrada, dupla conferência de material crítico,
    tolerância) são aplicadas em `registrar_pesagem`.
    """

    material = models.ForeignKey(
        MaterialOP,
        verbose_name="material da OP",
        on_delete=models.PROTECT,
        related_name="pesagens",
    )
    lote = models.ForeignKey(
        Lote,
        verbose_name="lote pesado",
        on_delete=models.PROTECT,
        related_name="pesagens",
    )
    quantidade_prevista = models.DecimalField(
        "quantidade prevista", max_digits=12, decimal_places=3
    )
    quantidade_pesada = models.DecimalField(
        "quantidade pesada",
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0"))],
    )
    tolerancia_percentual = models.DecimalField(
        "tolerância (%)", max_digits=6, decimal_places=3, default=Decimal("1")
    )
    balanca = models.ForeignKey(
        "cadastros.Balanca",
        verbose_name="balança",
        on_delete=models.PROTECT,
        related_name="pesagens",
    )
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="operador",
        on_delete=models.PROTECT,
        related_name="+",
    )
    conferente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="conferente",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    etiqueta = models.CharField("identificação da etiqueta", max_length=60, blank=True)
    data = models.DateTimeField("data", auto_now_add=True)

    class Meta:
        verbose_name = "pesagem da OP"
        verbose_name_plural = "pesagens da OP"
        ordering = ["data", "id"]

    def __str__(self) -> str:
        return (
            f"{self.material.item.codigo} · "
            f"{formatos.quantidade(self.quantidade_pesada)}"
        )

    @property
    def diferenca(self) -> Decimal:
        return self.quantidade_pesada - self.quantidade_prevista

    @property
    def diferenca_percentual(self) -> Decimal:
        if self.quantidade_prevista == 0:
            return Decimal("0")
        return (abs(self.diferenca) / self.quantidade_prevista * 100).quantize(
            Decimal("0.01")
        )

    @property
    def dentro_tolerancia(self) -> bool:
        return self.diferenca_percentual <= self.tolerancia_percentual


def registrar_pesagem(
    *, material, lote, balanca, quantidade_pesada, tolerancia_percentual,
    operador, conferente=None, etiqueta="",
) -> PesagemOP:
    """
    Valida e registra uma pesagem (Etapa 6b). Levanta ValidationError se:
    - a balança está com calibração vencida;
    - o material é crítico e falta dupla conferência (conferente ≠ operador);
    - o resultado está fora da tolerância.
    """
    erros = []
    if balanca.calibracao_vencida:
        erros.append(
            f"Balança {balanca.codigo} com calibração vencida em "
            f"{balanca.calibracao_validade:%d/%m/%Y} — use outra balança."
        )

    critico = bool(
        material.materia_prima_id and material.materia_prima.critico
    )
    if critico:
        if conferente is None:
            erros.append(
                f"{material.item.codigo} é material crítico: exige dupla "
                "conferência (informe o conferente)."
            )
        elif conferente == operador:
            erros.append(
                "Na dupla conferência o conferente deve ser diferente do operador."
            )

    pesagem = PesagemOP(
        material=material,
        lote=lote,
        quantidade_prevista=material.quantidade_necessaria,
        quantidade_pesada=quantidade_pesada,
        tolerancia_percentual=tolerancia_percentual,
        balanca=balanca,
        operador=operador,
        conferente=conferente,
        etiqueta=etiqueta,
    )
    if not pesagem.dentro_tolerancia:
        erros.append(
            f"Pesagem fora da tolerância ({pesagem.diferenca_percentual}% > "
            f"{formatos.quantidade(tolerancia_percentual)}%): pese novamente "
            "ou registre um desvio."
        )

    if erros:
        raise ValidationError(erros)

    pesagem.save()
    return pesagem


class MotivoParada(models.TextChoices):
    MANUTENCAO = "MANUTENCAO", "Manutenção"
    FALTA_MATERIAL = "FALTA_MATERIAL", "Falta de material"
    SETUP = "SETUP", "Setup / troca"
    LIMPEZA = "LIMPEZA", "Limpeza"
    REFEICAO = "REFEICAO", "Refeição / intervalo"
    FALTA_OPERADOR = "FALTA_OPERADOR", "Falta de operador"
    OUTRO = "OUTRO", "Outro"


class Parada(models.Model):
    execucao = models.ForeignKey(
        ExecucaoOP,
        verbose_name="execução",
        on_delete=models.CASCADE,
        related_name="paradas",
    )
    motivo = models.CharField("motivo", max_length=20, choices=MotivoParada.choices)
    inicio = models.DateTimeField("início", default=timezone.now)
    fim = models.DateTimeField("fim", null=True, blank=True)
    observacoes = models.CharField("observações", max_length=200, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrada por",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = "parada"
        verbose_name_plural = "paradas"
        ordering = ["-inicio", "-id"]

    def __str__(self) -> str:
        return f"{self.get_motivo_display()} · {self.execucao.ordem.numero}"

    @property
    def em_aberto(self) -> bool:
        return self.fim is None

    @property
    def duracao(self) -> timedelta:
        fim = self.fim or timezone.now()
        return fim - self.inicio


class Ocorrencia(models.Model):
    execucao = models.ForeignKey(
        ExecucaoOP,
        verbose_name="execução",
        on_delete=models.CASCADE,
        related_name="ocorrencias",
    )
    descricao = models.TextField("descrição")
    data = models.DateTimeField("data", auto_now_add=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrada por",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = "ocorrência"
        verbose_name_plural = "ocorrências"
        ordering = ["-data", "-id"]

    def __str__(self) -> str:
        return self.descricao[:60]


class FotoProducao(ModeloAuditado):
    execucao = models.ForeignKey(
        ExecucaoOP,
        verbose_name="execução",
        on_delete=models.CASCADE,
        related_name="fotos",
    )
    arquivo = models.FileField(
        "arquivo",
        upload_to="producao/%Y/%m/",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
        help_text="Foto do processo (JPG, PNG ou WEBP).",
    )
    descricao = models.CharField("descrição", max_length=120, blank=True)

    class Meta:
        verbose_name = "foto da produção"
        verbose_name_plural = "fotos da produção"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.descricao or self.arquivo.name
