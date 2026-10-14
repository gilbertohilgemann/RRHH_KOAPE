"""Fase 6: permisos del motor de asistencia para los perfiles que ya existían."""
from django.db import migrations


def cargar(apps, schema_editor):
    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_6, 'contratos', 'jornada', 'asistencia')


class Migration(migrations.Migration):
    dependencies = [('asistencia', '0008_motor_asistencia')]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
