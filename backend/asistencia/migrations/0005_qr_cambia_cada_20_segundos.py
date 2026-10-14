"""Con el QR invertido, "vigencia" pasó a ser "cada cuántos segundos cambia
el QR de la pantalla": las configuraciones que tenían el valor por defecto
anterior (60 s) pasan al nuevo recomendado (20 s). Las que alguien cambió a
mano no se tocan."""
from django.db import migrations


def actualizar(apps, schema_editor):
    ConfiguracionMarcacion = apps.get_model('asistencia', 'ConfiguracionMarcacion')
    ConfiguracionMarcacion.objects.filter(vigencia_qr_segundos=60).update(vigencia_qr_segundos=20)


class Migration(migrations.Migration):
    dependencies = [('asistencia', '0004_permiso_marcar_con_qr')]

    operations = [migrations.RunPython(actualizar, migrations.RunPython.noop)]
