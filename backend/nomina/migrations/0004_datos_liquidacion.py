"""Fase 10: qué conceptos globales calcula la nómina sola en cada liquidación
(por su regla), cuáles van en el aguinaldo, y los permisos de la fase para los
perfiles que ya existían."""
from django.db import migrations

AUTOMATICOS = ['SUELDO', 'HORAS_EXTRA_DIURNAS', 'HORAS_EXTRA_NOCTURNAS', 'RECARGO_NOCTURNO', 'FERIADO_TRABAJADO',
               'DESCUENTO_AUSENCIA', 'IPS_TRABAJADOR', 'IPS_PATRONAL']


def cargar(apps, schema_editor):
    ConceptoNomina = apps.get_model('nomina', 'ConceptoNomina')
    ConceptoNomina.objects.filter(empresa=None, codigo__in=AUTOMATICOS).update(aplicacion='automatica')
    ConceptoNomina.objects.filter(empresa=None, codigo='AGUINALDO').update(aplicacion='aguinaldo')

    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_10, 'contratos', 'jornada', 'asistencia', 'licencias', 'legal', 'nomina',
                                'novedades')


class Migration(migrations.Migration):
    dependencies = [
        ('nomina', '0003_liquidacion'),
        ('novedades', '0002_datos_iniciales'),
    ]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
