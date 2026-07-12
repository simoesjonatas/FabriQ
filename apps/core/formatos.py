"""Formatação de valores para exibição."""

from decimal import Decimal


def quantidade(valor) -> str:
    """
    Formata quantidades sem zeros à direita: 100.000 -> "100",
    0.500 -> "0.5". Evita que "100.000" seja lido como cem mil.
    """
    if valor is None:
        return ""
    texto = f"{Decimal(valor).normalize():f}"
    return texto


def quantidade_com_unidade(valor, unidade_display: str) -> str:
    """"40" + "Unidade" -> "40 unidades"; "1" + "Litro" -> "1 litro"."""
    texto = quantidade(valor)
    unidade = unidade_display.lower()
    if texto and Decimal(valor) != 1 and not unidade.endswith("s"):
        unidade += "s"
    return f"{texto} {unidade}"
