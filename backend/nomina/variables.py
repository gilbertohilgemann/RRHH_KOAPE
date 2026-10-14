"""Variables de la liquidación que pueden usar las fórmulas, además de los
parámetros legales vigentes (`legal/servicios.vigentes`). Las calculará el
motor de nómina (fase 10) para cada empleado y período; acá están su
descripción y un valor de ejemplo para "Probar fórmula"."""
from decimal import Decimal

VARIABLES = {
    'SALARIO_BASE': ('Sueldo o jornal vigente del contrato', Decimal('3500000')),
    'VALOR_DIA': ('Valor de un día de trabajo', Decimal('116667')),
    'VALOR_HORA': ('Valor de una hora ordinaria', Decimal('14583')),
    'DIAS_PAGADOS': ('Días pagados del período', Decimal('30')),
    'DIAS_TRABAJADOS': ('Días trabajados del período', Decimal('22')),
    'DIAS_AUSENCIA_NO_PAGA': ('Días de ausencia o licencia no paga', Decimal('0')),
    'HORAS_EXTRA_DIURNAS': ('Horas extra diurnas AUTORIZADAS', Decimal('4')),
    'HORAS_EXTRA_NOCTURNAS': ('Horas extra nocturnas AUTORIZADAS', Decimal('0')),
    'HORAS_NOCTURNAS': ('Horas ordinarias en horario nocturno', Decimal('0')),
    'HORAS_FERIADO': ('Horas trabajadas en feriado', Decimal('0')),
    'BASE_IPS': ('Suma de los haberes que cuentan para IPS', Decimal('3500000')),
    'TOTAL_REMUNERACIONES_ANIO': ('Remuneraciones del año que cuentan para el aguinaldo', Decimal('42000000')),
    'CANTIDAD': ('Cantidad cargada en la novedad o el concepto fijo', Decimal('1')),
    'TASA': ('Tasa o valor unitario cargado', Decimal('0')),
    'MONTO': ('Monto cargado en la novedad o el concepto fijo', Decimal('0')),
}


def ejemplos():
    return {codigo: ejemplo for codigo, (_, ejemplo) in VARIABLES.items()}
