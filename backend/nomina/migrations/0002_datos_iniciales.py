"""Fase 8: conceptos de nómina globales de referencia y sus reglas de cálculo
EN BORRADOR (toman los parámetros del conjunto PY-LABORAL, también en
borrador), y permisos de la fase para los perfiles que ya existían."""
from datetime import date

from django.db import migrations

# (código, nombre, tipo, cálculo, neto, aguinaldo, vacaciones, ips, costo, recurrente, aprobación, comprobante, orden)
CONCEPTOS = [
    ('SUELDO', 'Sueldo o jornales del período', 'haber', 'formula', True, True, True, True, True, True, False, False, 10),
    ('HORAS_EXTRA_DIURNAS', 'Horas extra diurnas', 'haber', 'formula', True, True, True, True, True, False, False, False, 20),
    ('HORAS_EXTRA_NOCTURNAS', 'Horas extra nocturnas', 'haber', 'formula', True, True, True, True, True, False, False, False, 21),
    ('RECARGO_NOCTURNO', 'Recargo por horas nocturnas', 'haber', 'formula', True, True, True, True, True, False, False, False, 22),
    ('FERIADO_TRABAJADO', 'Trabajo en feriado o día de descanso', 'haber', 'formula', True, True, True, True, True, False, False, False, 23),
    ('VACACIONES', 'Vacaciones remuneradas', 'haber', 'formula', True, True, False, True, True, False, False, False, 30),
    ('BONIFICACION_FAMILIAR', 'Bonificación familiar', 'haber', 'formula', True, False, False, False, True, True, False, True, 40),
    ('COMISION', 'Comisiones', 'haber', 'importado', True, True, True, True, True, False, True, False, 50),
    ('BONO', 'Bonificación o premio', 'haber', 'manual', True, True, False, True, True, False, True, False, 51),
    ('AGUINALDO', 'Aguinaldo', 'haber', 'formula', True, False, False, False, True, False, False, False, 60),
    ('IPS_TRABAJADOR', 'Aporte IPS del trabajador', 'aporte_trabajador', 'porcentaje', True, False, False, False, False, False, False, False, 100),
    ('DESCUENTO_AUSENCIA', 'Descuento por ausencias no pagas', 'descuento', 'formula', True, False, False, False, False, False, False, False, 110),
    ('ANTICIPO', 'Recuperación de anticipo', 'descuento', 'manual', True, False, False, False, False, False, True, True, 120),
    ('CUOTA_PRESTAMO', 'Cuota de préstamo', 'descuento', 'manual', True, False, False, False, False, False, True, True, 121),
    ('IPS_PATRONAL', 'Aporte IPS del empleador', 'aporte_patronal', 'porcentaje', False, False, False, False, True, False, False, False, 200),
]
REGLAS = [
    ('SUELDO', '', 'VALOR_DIA * DIAS_PAGADOS'),
    ('HORAS_EXTRA_DIURNAS', 'HORAS_EXTRA_DIURNAS > 0', 'VALOR_HORA * HORAS_EXTRA_DIURNAS * (1 + RECARGO_EXTRA_DIURNA / 100)'),
    ('HORAS_EXTRA_NOCTURNAS', 'HORAS_EXTRA_NOCTURNAS > 0', 'VALOR_HORA * HORAS_EXTRA_NOCTURNAS * (1 + RECARGO_EXTRA_NOCTURNA / 100)'),
    ('RECARGO_NOCTURNO', 'HORAS_NOCTURNAS > 0', 'VALOR_HORA * HORAS_NOCTURNAS * RECARGO_NOCTURNO / 100'),
    ('FERIADO_TRABAJADO', 'HORAS_FERIADO > 0', 'VALOR_HORA * HORAS_FERIADO * (1 + RECARGO_FERIADO / 100)'),
    ('DESCUENTO_AUSENCIA', 'DIAS_AUSENCIA_NO_PAGA > 0', 'VALOR_DIA * DIAS_AUSENCIA_NO_PAGA'),
    ('AGUINALDO', '', 'TOTAL_REMUNERACIONES_ANIO / AGUINALDO_DIVISOR'),
    ('IPS_TRABAJADOR', '', 'BASE_IPS * IPS_TASA_TRABAJADOR / 100'),
    ('IPS_PATRONAL', '', 'BASE_IPS * IPS_TASA_PATRONAL / 100'),
]


def cargar(apps, schema_editor):
    ConceptoNomina = apps.get_model('nomina', 'ConceptoNomina')
    ReglaConcepto = apps.get_model('nomina', 'ReglaConcepto')
    ConjuntoReglas = apps.get_model('legal', 'ConjuntoReglas')
    conceptos = {}
    for (codigo, nombre, tipo, calculo, neto, aguinaldo, vacaciones, ips, costo, recurrente, aprobacion, comprobante,
         orden) in CONCEPTOS:
        conceptos[codigo], _ = ConceptoNomina.objects.get_or_create(empresa=None, codigo=codigo, defaults={
            'nombre': nombre, 'tipo': tipo, 'tipo_calculo': calculo, 'afecta_neto': neto, 'afecta_base_aguinaldo': aguinaldo,
            'afecta_base_vacaciones': vacaciones, 'afecta_base_ips': ips, 'afecta_costo_patronal': costo,
            'recurrente': recurrente, 'requiere_aprobacion': aprobacion, 'requiere_comprobante': comprobante, 'orden': orden,
            'base_por_defecto': 'BASE_IPS' if codigo.startswith('IPS_') else ''})
    conjunto = ConjuntoReglas.objects.filter(empresa=None, codigo='PY-LABORAL').order_by('version').first()
    if not ReglaConcepto.objects.filter(empresa=None).exists():
        ReglaConcepto.objects.bulk_create([ReglaConcepto(
            empresa=None, concepto=conceptos[codigo], conjunto_legal=conjunto, vigente_desde=date(2026, 7, 1),
            condicion=condicion, expresion=expresion, notas='Regla de referencia en borrador: revisarla antes de aprobarla.')
            for codigo, condicion, expresion in REGLAS])

    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_8, 'contratos', 'jornada', 'asistencia', 'licencias', 'legal', 'nomina')


class Migration(migrations.Migration):
    dependencies = [
        ('nomina', '0001_initial'),
        ('legal', '0002_datos_iniciales'),
        ('licencias', '0002_datos_iniciales'),
    ]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
