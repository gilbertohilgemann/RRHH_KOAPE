"""Comprobantes para los anticipos que ya estaban pagados (en orden de fecha de pago) y permiso para verlos."""
from django.db import migrations
from django.utils import timezone

FORMAS = {'transferencia': 'Transferencia', 'efectivo': 'Efectivo', 'cheque': 'Cheque'}


def emitir(apps, schema_editor):
    Anticipo = apps.get_model('novedades', 'Anticipo')
    ReciboAnticipo = apps.get_model('novedades', 'ReciboAnticipo')
    SecuenciaDocumento = apps.get_model('nomina', 'SecuenciaDocumento')
    pagados = Anticipo.objects.filter(estado__in=('pagado', 'recuperado')).select_related('empleado').order_by('pagado_en', 'fecha', 'id')
    for anticipo in pagados:
        if ReciboAnticipo.objects.filter(anticipo=anticipo, estado='emitido').exists():
            continue
        fecha = timezone.localtime(anticipo.pagado_en).date() if anticipo.pagado_en else anticipo.fecha
        secuencia, _ = SecuenciaDocumento.objects.get_or_create(empresa_id=anticipo.empresa_id, tipo='recibo_anticipo', anio=fecha.year,
                                                                defaults={'prefijo': 'A'})
        numero = f'{secuencia.prefijo}{fecha.year}-{secuencia.siguiente:06d}'
        secuencia.siguiente += 1
        secuencia.save(update_fields=['siguiente'])
        ReciboAnticipo.objects.create(
            empresa_id=anticipo.empresa_id, anticipo=anticipo, empleado_id=anticipo.empleado_id, numero=numero, fecha_emision=fecha,
            monto=anticipo.monto_aprobado or anticipo.monto_solicitado, moneda=anticipo.moneda,
            forma_pago=FORMAS.get(anticipo.forma_pago, anticipo.forma_pago), referencia_pago=anticipo.referencia_pago,
            aporta_ips=anticipo.empleado.aporta_ips, creado_por_id=anticipo.pagado_por_id, modificado_por_id=anticipo.pagado_por_id)

    from cuentas import perfiles
    perfiles.sumar_en_migracion(apps, perfiles.COMPROBANTES_ANTICIPO, 'contratos', 'jornada', 'asistencia', 'licencias', 'legal',
                                'nomina', 'novedades', 'cumplimiento')


class Migration(migrations.Migration):
    dependencies = [
        ('novedades', '0003_recibo_anticipo'),
        ('nomina', '0007_liquidacion_aporta_ips'),
        ('cumplimiento', '0001_initial'),
    ]

    operations = [migrations.RunPython(emitir, migrations.RunPython.noop)]
