"""Fase 7: tipos de licencia y escala de vacaciones de referencia (globales,
SIN VERIFICAR: alguien tiene que revisarlos contra la norma vigente antes de
usarlos para liquidar), y permisos de la fase para los perfiles que ya existían."""
from django.db import migrations

CT = 'Código del Trabajo (Ley 213/93)'
# (código, nombre, categoría, paga, consume vacaciones, exige documento, cuenta, por horas, máximo, fuente)
TIPOS = [
    ('VAC', 'Vacaciones', 'vacaciones', True, True, False, 'habiles', False, None, f'{CT}, art. 218 — a verificar'),
    ('REPOSO', 'Reposo médico', 'enfermedad', True, False, True, 'corridos', False, None,
     'Seguro social (IPS) y certificado médico — a verificar quién paga cada tramo'),
    ('MATERNIDAD', 'Licencia por maternidad', 'maternidad', True, False, True, 'corridos', False, 126,
     'Ley 5508/15 (18 semanas) — a verificar'),
    ('PATERNIDAD', 'Licencia por paternidad', 'paternidad', True, False, True, 'corridos', False, 14,
     'Ley 5508/15 (2 semanas) — a verificar'),
    ('DUELO', 'Licencia por duelo', 'duelo', True, False, True, 'corridos', False, 3, f'{CT}, art. 61 — a verificar'),
    ('MATRIMONIO', 'Licencia por matrimonio', 'matrimonio', True, False, True, 'corridos', False, 3,
     f'{CT}, art. 61 — a verificar'),
    ('EXAMEN', 'Permiso por examen', 'estudio', True, False, True, 'habiles', True, None, 'Convenio o política de la empresa'),
    ('PARTICULAR', 'Permiso particular (sin goce)', 'particular', False, False, False, 'habiles', True, None,
     'Política de la empresa'),
]
ESCALA = [(1, 5, 12), (5, 10, 18), (10, None, 30)]


def cargar(apps, schema_editor):
    TipoLicencia = apps.get_model('licencias', 'TipoLicencia')
    EscalaVacaciones = apps.get_model('licencias', 'EscalaVacaciones')
    for codigo, nombre, categoria, paga, vacaciones, documento, cuenta, horas, maximo, fuente in TIPOS:
        TipoLicencia.objects.get_or_create(empresa=None, codigo=codigo, defaults={
            'nombre': nombre, 'categoria': categoria, 'es_paga': paga, 'consume_vacaciones': vacaciones,
            'requiere_documento': documento, 'cuenta_dias': cuenta, 'permite_horas': horas, 'maximo_dias': maximo,
            'fuente': fuente, 'verificado': False})
    if not EscalaVacaciones.objects.filter(empresa=None).exists():
        EscalaVacaciones.objects.bulk_create([
            EscalaVacaciones(empresa=None, desde_anios=desde, hasta_anios=hasta, dias=dias,
                             fuente=f'{CT}, art. 218 — a verificar', verificado=False)
            for desde, hasta, dias in ESCALA])

    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.FASE_7, 'contratos', 'jornada', 'asistencia', 'licencias')


class Migration(migrations.Migration):
    dependencies = [
        ('licencias', '0001_initial'),
        ('asistencia', '0010_diaasistencia_licencia_alter_diaasistencia_estado'),
    ]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
