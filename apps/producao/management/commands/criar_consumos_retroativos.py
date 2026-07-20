"""
Migração de dados da Etapa 4 (plano de correções): OPs concluídas ANTES
do apontamento por lote têm as baixas registradas apenas em
`Movimentacao` (SAÍDA com documento = número da OP). Este comando cria
os `ConsumoMaterialOP` retroativos a partir delas, já vinculados às
movimentações — a coluna "Lote usado" passa a aparecer também nas OPs
antigas.

Idempotente: OPs que já têm consumo são ignoradas.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.estoque.models import Movimentacao, TipoMovimentacao
from apps.ordens.models import OrdemProducao, StatusOP
from apps.producao.models import ConsumoMaterialOP


class Command(BaseCommand):
    help = (
        "Cria consumos por lote retroativos para OPs concluídas antes da "
        "Etapa 4, a partir das movimentações de saída da produção."
    )

    def handle(self, *args, **options):
        criados = 0
        ordens_migradas = 0
        avisos: list[str] = []

        ordens = OrdemProducao.objects.filter(
            status=StatusOP.CONCLUIDA
        ).prefetch_related("materiais__materia_prima", "materiais__embalagem")

        for ordem in ordens:
            if ConsumoMaterialOP.objects.filter(material__ordem=ordem).exists():
                continue

            materiais_por_item = {}
            for material in ordem.materiais.all():
                if material.materia_prima_id:
                    chave = ("materia_prima", material.materia_prima_id)
                else:
                    chave = ("embalagem", material.embalagem_id)
                materiais_por_item[chave] = material

            saidas = Movimentacao.objects.filter(
                tipo=TipoMovimentacao.SAIDA,
                documento=ordem.numero,
                motivo__startswith="Consumo na produção",
            ).select_related("lote", "local_origem", "criado_por")

            novos = 0
            with transaction.atomic():
                for movimentacao in saidas:
                    if movimentacao.materia_prima_id:
                        chave = ("materia_prima", movimentacao.materia_prima_id)
                    elif movimentacao.embalagem_id:
                        chave = ("embalagem", movimentacao.embalagem_id)
                    else:
                        chave = ("produto", movimentacao.produto_id)

                    material = materiais_por_item.get(chave)
                    responsavel = (
                        movimentacao.criado_por
                        or ordem.atualizado_por
                        or ordem.criado_por
                    )
                    if (
                        material is None
                        or movimentacao.lote_id is None
                        or movimentacao.local_origem_id is None
                        or responsavel is None
                    ):
                        avisos.append(
                            f"{ordem.numero}: movimentação #{movimentacao.pk} sem "
                            "material/lote/local/responsável correspondente — pulada."
                        )
                        continue

                    ConsumoMaterialOP.objects.create(
                        material=material,
                        lote=movimentacao.lote,
                        local=movimentacao.local_origem,
                        quantidade=movimentacao.quantidade,
                        movimentacao=movimentacao,
                        registrado_por=responsavel,
                    )
                    novos += 1

            if novos:
                ordens_migradas += 1
                criados += novos
                self.stdout.write(f"  {ordem.numero}: {novos} consumo(s) criado(s)")

        for aviso in avisos:
            self.stdout.write(self.style.WARNING(f"  ⚠ {aviso}"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Concluído: {criados} consumo(s) retroativo(s) em "
                f"{ordens_migradas} OP(s)."
            )
        )
