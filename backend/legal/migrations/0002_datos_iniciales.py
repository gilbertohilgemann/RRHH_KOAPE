"""Fase 8: conjunto global de parámetros laborales de Paraguay como REFERENCIA
EN BORRADOR (§9: "si no se verificó, mantenerla en Draft y bloquear la
liquidación real"). Nada de esto vale para liquidar hasta que alguien lo
revise contra las fuentes oficiales y otra persona lo apruebe."""
from datetime import date
from decimal import Decimal

from django.db import migrations

CT = 'Código del Trabajo (Ley 213/93)'
# (código, nombre, valor numérico, valor texto, unidad, referencia)
PARAMETROS = [
    ('SALARIO_MINIMO_MENSUAL', 'Salario mínimo legal mensual (actividades diversas no especificadas)', Decimal('3044000'), '', 'Gs',
     'Dato reportado para julio de 2026 en la especificación (§9): verificar categoría y resolución oficial'),
    ('JORNAL_MINIMO_DIARIO', 'Jornal mínimo diario (actividades diversas no especificadas)', Decimal('117077'), '', 'Gs',
     'Dato reportado para julio de 2026 en la especificación (§9): verificar'),
    ('DIVISOR_MENSUAL_DIAS', 'Días del mes para calcular el valor del día', Decimal('30'), '', 'días', 'A verificar'),
    ('HORAS_JORNADA_DIURNA', 'Horas de la jornada ordinaria diurna', Decimal('8'), '', 'horas', f'{CT} — a verificar'),
    ('RECARGO_EXTRA_DIURNA', 'Recargo de la hora extra diurna', Decimal('50'), '', '%', f'{CT} — a verificar'),
    ('RECARGO_EXTRA_NOCTURNA', 'Recargo de la hora extra nocturna', Decimal('100'), '', '%', f'{CT} — a verificar'),
    ('RECARGO_NOCTURNO', 'Recargo de la hora ordinaria nocturna', Decimal('30'), '', '%', f'{CT} — a verificar'),
    ('RECARGO_FERIADO', 'Recargo por trabajar en feriado o día de descanso', Decimal('100'), '', '%', f'{CT} — a verificar'),
    ('AGUINALDO_DIVISOR', 'Divisor del aguinaldo (doceava parte de lo percibido en el año)', Decimal('12'), '', '', f'{CT} — a verificar'),
    ('BONIFICACION_FAMILIAR_PORCENTAJE', 'Bonificación familiar por hijo (sobre el salario mínimo)', Decimal('5'), '', '%',
     f'{CT} — a verificar condiciones y topes'),
    ('HORA_INICIO_NOCTURNO', 'Inicio del horario nocturno', None, '20:00', 'hora', f'{CT} — a verificar'),
    ('HORA_FIN_NOCTURNO', 'Fin del horario nocturno', None, '06:00', 'hora', f'{CT} — a verificar'),
]


def cargar(apps, schema_editor):
    ConjuntoReglas = apps.get_model('legal', 'ConjuntoReglas')
    ParametroLegal = apps.get_model('legal', 'ParametroLegal')
    RegimenSeguridadSocial = apps.get_model('legal', 'RegimenSeguridadSocial')
    if ConjuntoReglas.objects.filter(empresa=None, codigo='PY-LABORAL').exists():
        return
    conjunto = ConjuntoReglas.objects.create(
        empresa=None, codigo='PY-LABORAL', nombre='Parámetros laborales de Paraguay (referencia)', version=1,
        pais='PY', vigente_desde=date(2026, 7, 1), estado='borrador',
        fuente_nombre=f'{CT}, resoluciones del MTESS y normativa del IPS',
        notas='Valores de referencia cargados al instalar, SIN VERIFICAR. Revisarlos contra las fuentes oficiales '
              '(BACN, MTESS, IPS) con un profesional laboral-contable antes de aprobarlos.')
    ParametroLegal.objects.bulk_create([
        ParametroLegal(conjunto=conjunto, codigo=c, nombre=n, valor_numerico=v, valor_texto=t, unidad=u, referencia_fuente=r)
        for c, n, v, t, u, r in PARAMETROS])
    RegimenSeguridadSocial.objects.create(
        conjunto=conjunto, codigo='IPS-GENERAL', nombre='IPS — régimen general', tasa_trabajador=Decimal('9'),
        tasa_patronal=Decimal('16.5'), base='Salario y remuneraciones computables (a verificar inclusiones y exclusiones)',
        referencia_fuente='Normativa del IPS — a verificar tasas, bases y regímenes especiales')


class Migration(migrations.Migration):
    dependencies = [('legal', '0001_initial')]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
