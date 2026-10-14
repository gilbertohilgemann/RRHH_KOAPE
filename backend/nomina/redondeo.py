"""Redondeo centralizado (§8: "redondeo centralizado y documentado").

Todos los importes de la nómina pasan por `redondear()` con el modo de la
regla del concepto. El guaraní no usa decimales: el modo por defecto es
`entero` (al guaraní más cercano, la mitad hacia arriba)."""
from decimal import ROUND_HALF_UP, Decimal

ENTERO = 'entero'
MODOS = [
    (ENTERO, 'Al guaraní (sin decimales)'),
    ('decena', 'A la decena'),
    ('centena', 'A la centena'),
    ('dos_decimales', 'Dos decimales (monedas con centavos)'),
    ('ninguno', 'Sin redondear'),
]
_PASO = {ENTERO: Decimal('1'), 'decena': Decimal('10'), 'centena': Decimal('100'), 'dos_decimales': Decimal('0.01')}


def redondear(valor, modo=ENTERO):
    valor = Decimal(valor)
    if modo == 'ninguno':
        return valor
    paso = _PASO[modo]
    return (valor / paso).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * paso
