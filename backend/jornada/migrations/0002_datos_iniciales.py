"""Fase 3: regímenes de jornada y calendario nacional 2026 de referencia
(globales, SIN VERIFICAR: alguien tiene que revisarlos contra la norma y el
decreto del año antes de usarlos para liquidar), y permisos de la fase para
los perfiles que ya existían."""
from datetime import date

from django.db import migrations

FUENTE = 'Código del Trabajo (Ley 213/93), jornada máxima — valor de referencia a verificar'
REGIMENES = [
    ('DIURNA', 'Jornada diurna', 'diurna', 8 * 60, 48 * 60),
    ('NOCTURNA', 'Jornada nocturna', 'nocturna', 7 * 60, 42 * 60),
    ('MIXTA', 'Jornada mixta', 'mixta', 7 * 60 + 30, 45 * 60),
]

# Fechas de la ley de feriados; las trasladables pueden moverse por ley o
# decreto cada año: por eso el calendario queda "sin verificar".
FERIADOS_2026 = [
    (date(2026, 1, 1), 'Año Nuevo'),
    (date(2026, 3, 1), 'Día de los Héroes'),
    (date(2026, 4, 2), 'Jueves Santo'),
    (date(2026, 4, 3), 'Viernes Santo'),
    (date(2026, 5, 1), 'Día del Trabajador'),
    (date(2026, 5, 14), 'Independencia Nacional'),
    (date(2026, 5, 15), 'Independencia Nacional y Día de la Madre'),
    (date(2026, 6, 12), 'Paz del Chaco'),
    (date(2026, 8, 15), 'Fundación de Asunción'),
    (date(2026, 9, 29), 'Victoria de Boquerón'),
    (date(2026, 12, 8), 'Virgen de Caacupé'),
    (date(2026, 12, 25), 'Navidad'),
]


def cargar(apps, schema_editor):
    RegimenJornada = apps.get_model('jornada', 'RegimenJornada')
    CalendarioFeriados = apps.get_model('jornada', 'CalendarioFeriados')
    DiaFeriado = apps.get_model('jornada', 'DiaFeriado')
    for codigo, nombre, tipo, diario, semanal in REGIMENES:
        RegimenJornada.objects.get_or_create(empresa=None, codigo=codigo, defaults={
            'nombre': nombre, 'tipo_jornada': tipo, 'maximo_diario_minutos': diario,
            'maximo_semanal_minutos': semanal, 'fuente': FUENTE, 'verificado': False})
    calendario, creado = CalendarioFeriados.objects.get_or_create(
        empresa=None, codigo='PY-NACIONAL', anio=2026, defaults={'nombre': 'Feriados nacionales de Paraguay'})
    if creado:
        DiaFeriado.objects.bulk_create([DiaFeriado(calendario=calendario, fecha=f, nombre=n, tipo='nacional')
                                        for f, n in FERIADOS_2026])

    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_3, 'contratos', 'jornada')


class Migration(migrations.Migration):
    dependencies = [
        ('jornada', '0001_initial'),
        ('contratos', '0002_datos_iniciales'),
    ]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
