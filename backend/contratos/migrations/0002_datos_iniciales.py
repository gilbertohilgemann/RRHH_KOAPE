"""Fase 2: ítems globales de los catálogos (esquemas salariales y tipos de
documento, cada empresa puede sumar los suyos) y permisos de la fase para
los perfiles que ya existían."""
from django.db import migrations

ESQUEMAS = [
    ('MENSUAL', 'Mensual', 'mes', 'mensual'),
    ('QUINCENAL', 'Quincenal', 'quincena', 'quincenal'),
    ('SEMANAL', 'Semanal', 'semana', 'semanal'),
    ('JORNAL', 'Jornal (por día)', 'dia', 'quincenal'),
    ('HORA', 'Por hora', 'hora', 'quincenal'),
    ('COMISION', 'Comisión', 'comision', 'mensual'),
    ('DESTAJO', 'Por pieza o producción (destajo)', 'destajo', 'quincenal'),
    ('MIXTO', 'Mixto (fijo + variable)', 'mixta', 'mensual'),
]

TIPOS_DOCUMENTO = [
    # código, nombre, confidencial, requiere vencimiento
    ('CI', 'Cédula de identidad', False, True),
    ('CONTRATO', 'Contrato firmado', False, False),
    ('ANTECEDENTES', 'Certificado de antecedentes policiales', False, True),
    ('TITULO', 'Título o certificado de estudios', False, False),
    ('CV', 'Currículum', False, False),
    ('MEDICO', 'Certificado médico', True, False),
    ('IPS', 'Documento del IPS', False, False),
    ('OTRO', 'Otro', False, False),
]


def cargar(apps, schema_editor):
    EsquemaSalarial = apps.get_model('contratos', 'EsquemaSalarial')
    TipoDocumento = apps.get_model('empleados', 'TipoDocumento')
    for codigo, nombre, base, frecuencia in ESQUEMAS:
        EsquemaSalarial.objects.get_or_create(empresa=None, codigo=codigo, defaults={
            'nombre': nombre, 'base_calculo': base, 'frecuencia_pago': frecuencia})
    for codigo, nombre, confidencial, vencimiento in TIPOS_DOCUMENTO:
        TipoDocumento.objects.get_or_create(empresa=None, codigo=codigo, defaults={
            'nombre': nombre, 'confidencial': confidencial, 'requiere_vencimiento': vencimiento})

    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_2, 'contratos')


class Migration(migrations.Migration):
    dependencies = [
        ('contratos', '0001_initial'),
        ('empleados', '0002_tipodocumento_documentoempleado_cuentabancaria_and_more'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
