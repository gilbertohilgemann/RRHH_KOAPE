"""Fase 11: parámetros legales del egreso (conjunto global PY-EGRESO, EN
BORRADOR, SIN VERIFICAR), conceptos y reglas de la liquidación final (en
borrador) y permisos de la fase para los perfiles que ya existían."""
from datetime import date
from decimal import Decimal

from django.db import migrations

CT = 'Código del Trabajo (Ley 213/93)'
PARAMETROS = [
    ('PREAVISO_DIAS', 'Días de preaviso según la antigüedad', None,
     [{'desde_anios': 0, 'hasta_anios': 1, 'dias': 30}, {'desde_anios': 1, 'hasta_anios': 5, 'dias': 45},
      {'desde_anios': 5, 'hasta_anios': 10, 'dias': 60}, {'desde_anios': 10, 'hasta_anios': None, 'dias': 90}], 'días', f'{CT} — a verificar'),
    ('CAUSALES_PREAVISO', 'Causales en las que se paga el preaviso no otorgado', None, ['despido_injustificado'], '', 'A verificar'),
    ('CAUSALES_INDEMNIZACION', 'Causales con indemnización por antigüedad', None, ['despido_injustificado'], '', 'A verificar'),
    ('INDEMNIZACION_DIAS_POR_ANIO', 'Días de salario de indemnización por año de antigüedad', Decimal('15'), None, 'días', f'{CT} — a verificar'),
    ('INDEMNIZACION_FRACCION_MESES', 'Meses de una fracción de año que cuentan como año entero', Decimal('6'), None, 'meses', f'{CT} — a verificar'),
]
CONCEPTOS = [('VACACIONES_CAUSADAS', 'Vacaciones causadas no gozadas', 70), ('PREAVISO', 'Indemnización por falta de preaviso', 71),
             ('INDEMNIZACION', 'Indemnización por antigüedad', 72)]
REGLAS = [
    ('VACACIONES_CAUSADAS', 'SALDO_VACACIONES > 0', 'VALOR_DIA * SALDO_VACACIONES'),
    ('PREAVISO', 'CORRESPONDE_PREAVISO == 1', 'VALOR_DIA * DIAS_PREAVISO'),
    ('INDEMNIZACION', 'CORRESPONDE_INDEMNIZACION == 1 and ANIOS_INDEMNIZACION > 0',
     'VALOR_DIA * INDEMNIZACION_DIAS_POR_ANIO * ANIOS_INDEMNIZACION'),
]


def cargar(apps, schema_editor):
    ConjuntoReglas = apps.get_model('legal', 'ConjuntoReglas')
    ParametroLegal = apps.get_model('legal', 'ParametroLegal')
    ConceptoNomina = apps.get_model('nomina', 'ConceptoNomina')
    ReglaConcepto = apps.get_model('nomina', 'ReglaConcepto')
    if not ConjuntoReglas.objects.filter(empresa=None, codigo='PY-EGRESO').exists():
        conjunto = ConjuntoReglas.objects.create(
            empresa=None, codigo='PY-EGRESO', nombre='Parámetros del egreso de Paraguay (referencia)', version=1, pais='PY',
            vigente_desde=date(2026, 1, 1), estado='borrador', fuente_nombre=f'{CT} y jurisprudencia — a verificar',
            notas='Preaviso, indemnización y causales de referencia, SIN VERIFICAR: revisarlos con un profesional laboral antes de aprobar.')
        ParametroLegal.objects.bulk_create([
            ParametroLegal(conjunto=conjunto, codigo=c, nombre=n, valor_numerico=v, valor_json=j, unidad=u, referencia_fuente=r)
            for c, n, v, j, u, r in PARAMETROS])
    for codigo, nombre, orden in CONCEPTOS:
        concepto, _ = ConceptoNomina.objects.get_or_create(empresa=None, codigo=codigo, defaults={
            'nombre': nombre, 'tipo': 'haber', 'tipo_calculo': 'formula', 'afecta_neto': True, 'afecta_costo_patronal': True,
            'aplicacion': 'liquidacion_final', 'orden': orden})
        expresion = next((r for r in REGLAS if r[0] == codigo))
        if not ReglaConcepto.objects.filter(empresa=None, concepto=concepto).exists():
            ReglaConcepto.objects.create(empresa=None, concepto=concepto, vigente_desde=date(2026, 1, 1), condicion=expresion[1],
                                         expresion=expresion[2], notas='Regla de referencia en borrador: revisarla antes de aprobarla.')

    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_11, 'contratos', 'jornada', 'asistencia', 'licencias', 'legal', 'nomina',
                                'novedades', 'cumplimiento')


class Migration(migrations.Migration):
    dependencies = [
        ('nomina', '0005_liquidacionfinal'),
        ('cumplimiento', '0001_initial'),
        ('legal', '0002_datos_iniciales'),
    ]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
