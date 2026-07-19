"""
Campos críticos: alterá-los exige justificativa obrigatória.

Lista do PDF de complementação funcional (seção 2.3): fórmula, lote,
quantidade, resultado, status, aprovação e validade. O mapa abaixo
traduz essa lista para os campos concretos de cada modelo; os forms
usam `JustificativaAuditoriaMixin` (apps/auditoria/forms.py) para
bloquear a alteração sem justificativa, e os fluxos de decisão
(cancelar, decidir análise, quarentena) já coletam o motivo nas
próprias telas.
"""

# model._meta.label_lower -> campos que exigem justificativa ao alterar
CAMPOS_CRITICOS: dict[str, set[str]] = {
    "ordens.formula": {"produto", "nome", "rendimento", "ativo"},
    "ordens.ordemproducao": {"formula", "quantidade", "status", "data_programada"},
    "estoque.lote": {"codigo", "lote_fornecedor", "validade"},
    "pedidos.pedido": {"cliente", "status", "prazo"},
    "qualidade.analise": {"lote", "status"},
    "producao.execucaoop": {"quantidade_produzida", "perdas", "lote_produzido"},
}


def campos_criticos_do_modelo(modelo) -> set[str]:
    return CAMPOS_CRITICOS.get(modelo._meta.label_lower, set())
