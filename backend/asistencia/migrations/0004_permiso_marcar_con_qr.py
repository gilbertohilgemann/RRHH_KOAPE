"""QR invertido (14/10/2026): el permiso "pedir su QR temporal" se reemplaza
por "marcar escaneando el QR de una terminal". Se suma el nuevo a los
perfiles existentes y se quita el viejo (su modelo ya no existe)."""
from django.db import migrations


def cargar(apps, schema_editor):
    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_4, 'contratos', 'jornada', 'asistencia')
    Permission = apps.get_model('auth', 'Permission')
    Permission.objects.filter(content_type__app_label='asistencia', codename='solicitar_qr_propio').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('asistencia', '0003_qr_dinamico_y_foto'),
        ('empleados', '0003_qr_dinamico_y_foto'),
    ]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
