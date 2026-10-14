"""Fase 5: permisos de la importación CSV para los perfiles que ya existían."""
from django.db import migrations


def cargar(apps, schema_editor):
    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_5, 'contratos', 'jornada', 'asistencia')


class Migration(migrations.Migration):
    dependencies = [('asistencia', '0006_importacion_csv')]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
