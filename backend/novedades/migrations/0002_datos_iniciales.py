"""Fase 9: conceptos de descuento globales para los descuentos autorizados y
permisos de la fase para los perfiles que ya existían."""
from django.db import migrations

CONCEPTOS = [
    ('CUOTA_SINDICAL', 'Cuota sindical', 130),
    ('EMBARGO_JUDICIAL', 'Embargo judicial', 131),
    ('DESCUENTO_AUTORIZADO', 'Otro descuento autorizado por el empleado', 132),
]


def cargar(apps, schema_editor):
    ConceptoNomina = apps.get_model('nomina', 'ConceptoNomina')
    for codigo, nombre, orden in CONCEPTOS:
        ConceptoNomina.objects.get_or_create(empresa=None, codigo=codigo, defaults={
            'nombre': nombre, 'tipo': 'descuento', 'tipo_calculo': 'manual', 'afecta_neto': True, 'recurrente': True,
            'requiere_comprobante': True, 'orden': orden})

    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_9, 'contratos', 'jornada', 'asistencia', 'licencias', 'legal', 'nomina',
                                'novedades')


class Migration(migrations.Migration):
    dependencies = [
        ('novedades', '0001_initial'),
        ('nomina', '0002_datos_iniciales'),
    ]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
