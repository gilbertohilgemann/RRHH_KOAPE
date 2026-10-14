"""Fase 4: permisos del marcador para los perfiles que ya existían."""
from django.db import migrations


def cargar(apps, schema_editor):
    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_4, 'contratos', 'jornada', 'asistencia')


class Migration(migrations.Migration):
    dependencies = [
        ('asistencia', '0001_initial'),
        ('jornada', '0002_datos_iniciales'),
    ]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
