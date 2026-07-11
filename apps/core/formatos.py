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
