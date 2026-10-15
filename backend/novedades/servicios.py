"""Reglas de las novedades, anticipos y préstamos, en un solo lugar."""
from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from nomina.models import ConceptoNomina
from novedades.models import (Anticipo, CuotaRecuperacion, Novedad, Prestamo, ReciboAnticipo, _sumar_meses, recibo_vigente,
                              saldo_de)


def _separacion(objeto, usuario):
    """Si la empresa exige separar funciones, no aprueba quien lo cargó."""
    from asistencia.models import ConfiguracionMarcacion
    if ConfiguracionMarcacion.de(objeto.empresa).exigir_aprobador_distinto and objeto.creado_por_id == usuario.pk:
        raise ValidationError('La empresa exige que lo apruebe otra persona (no quien lo cargó).')


def _concepto(objeto, codigo):
    if objeto.concepto_id:
        return objeto.concepto
    concepto = ConceptoNomina.objects.filter(empresa=objeto.empresa, codigo=codigo).first() \
        or ConceptoNomina.objects.filter(empresa__isnull=True, codigo=codigo).first()
    if concepto is None:
        raise ValidationError(f'Falta el concepto de nómina {codigo}.')
    return concepto


def _resolver(objeto, estado, usuario, motivo=''):
    objeto.estado = estado
    objeto.aprobado_por = usuario
    objeto.aprobado_en = timezone.now()
    campos = ['estado', 'aprobado_por', 'aprobado_en', 'modificado']
    if motivo:
        objeto.motivo_resolucion = motivo[:250]
        campos.append('motivo_resolucion')
    objeto.save(update_fields=campos)
    return objeto


# ------------------------------------------------------------------ novedades
def aprobar_novedad(novedad, usuario):
    if novedad.estado != Novedad.PENDIENTE:
        raise ValidationError('Solo se aprueba una novedad pendiente.')
    _separacion(novedad, usuario)
    novedad.full_clean()
    return _resolver(novedad, Novedad.APROBADA, usuario)


def rechazar_novedad(novedad, usuario, motivo):
    if novedad.estado != Novedad.PENDIENTE:
        raise ValidationError('Solo se rechaza una novedad pendiente.')
    return _resolver(novedad, Novedad.RECHAZADA, usuario, motivo)


def anular_novedad(novedad, usuario, motivo):
    """Una aprobada que todavía no entró en una nómina. Aplicada: hace falta una rectificación (fase 10)."""
    if novedad.estado == Novedad.APLICADA:
        raise ValidationError('Ya se aplicó en una nómina: se corrige con una rectificación, no anulándola.')
    if novedad.estado not in (Novedad.PENDIENTE, Novedad.APROBADA):
        raise ValidationError('La novedad ya fue rechazada o anulada.')
    return _resolver(novedad, Novedad.ANULADA, usuario, motivo)


# ------------------------------------------------------------------ anticipos
def aprobar_anticipo(anticipo, usuario, monto=None):
    if anticipo.estado != Anticipo.SOLICITADO:
        raise ValidationError('Solo se aprueba un anticipo solicitado.')
    _separacion(anticipo, usuario)
    monto = Decimal(monto) if monto not in (None, '') else anticipo.monto_solicitado
    if not 0 < monto <= anticipo.monto_solicitado:
        raise ValidationError({'monto_aprobado': 'Entre 1 y el monto solicitado.'})
    anticipo.monto_aprobado = monto
    anticipo.save(update_fields=['monto_aprobado'])
    return _resolver(anticipo, Anticipo.APROBADO, usuario)


def rechazar_anticipo(anticipo, usuario, motivo):
    if anticipo.estado != Anticipo.SOLICITADO:
        raise ValidationError('Solo se rechaza un anticipo solicitado.')
    return _resolver(anticipo, Anticipo.RECHAZADO, usuario, motivo)


@transaction.atomic
def pagar_anticipo(anticipo, usuario, forma_pago, referencia='', fecha=None):
    """Registra el pago (hoy, o la fecha indicada, ej. al cargar la historia de la demo), genera sus cuotas de
    recuperación (iguales; la última absorbe el redondeo) y emite el comprobante numerado."""
    anticipo = Anticipo.objects.select_for_update().get(pk=anticipo.pk)
    if anticipo.estado != Anticipo.APROBADO:
        raise ValidationError('Solo se paga un anticipo aprobado.')
    if forma_pago not in dict(Anticipo.FORMA_PAGO_OPCIONES):
        raise ValidationError({'forma_pago': 'Elegí la forma de pago.'})
    ahora = timezone.now() if fecha is None else timezone.make_aware(datetime.combine(fecha, time(10, 0)))
    concepto = _concepto(anticipo, 'ANTICIPO')
    primer_mes = anticipo.primer_mes.replace(day=1) if anticipo.primer_mes else _sumar_meses(timezone.localdate(), 1)
    n = anticipo.cuotas
    cuota = (anticipo.monto_aprobado / n).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    for i in range(1, n + 1):
        monto = cuota if i < n else anticipo.monto_aprobado - cuota * (n - 1)
        CuotaRecuperacion.objects.create(empresa_id=anticipo.empresa_id, empleado_id=anticipo.empleado_id, anticipo=anticipo,
                                         concepto=concepto, numero=i, mes=_sumar_meses(primer_mes, i - 1), monto=monto,
                                         creado_por=usuario, modificado_por=usuario)
    anticipo.estado = Anticipo.PAGADO
    anticipo.forma_pago = forma_pago
    anticipo.referencia_pago = referencia[:100]
    anticipo.pagado_por = usuario
    anticipo.pagado_en = ahora
    anticipo.save(update_fields=['estado', 'forma_pago', 'referencia_pago', 'pagado_por', 'pagado_en', 'modificado'])
    emitir_recibo_anticipo(anticipo, usuario)
    return anticipo


def emitir_recibo_anticipo(anticipo, usuario, fecha=None):
    """Comprobante numerado del pago (A<año>-000001). Uno vigente por anticipo: si ya hay, lo devuelve."""
    from nomina.liquidar import siguiente_numero
    if anticipo.estado not in (Anticipo.PAGADO, Anticipo.RECUPERADO):
        raise ValidationError('El comprobante se emite cuando el anticipo está pagado.')
    vigente = recibo_vigente(anticipo)
    if vigente is not None:
        return vigente
    fecha = fecha or (timezone.localtime(anticipo.pagado_en).date() if anticipo.pagado_en else timezone.localdate())
    return ReciboAnticipo.objects.create(
        empresa_id=anticipo.empresa_id, anticipo=anticipo, empleado_id=anticipo.empleado_id,
        numero=siguiente_numero(anticipo.empresa, 'recibo_anticipo', fecha.year, prefijo='A'), fecha_emision=fecha,
        monto=anticipo.monto_aprobado, moneda=anticipo.moneda, forma_pago=anticipo.get_forma_pago_display(),
        referencia_pago=anticipo.referencia_pago, aporta_ips=anticipo.empleado.aporta_ips,
        creado_por=usuario, modificado_por=usuario)


def anular_recibo_anticipo(recibo, usuario, motivo):
    """Anula el comprobante (no el pago): después se puede emitir otro, con número nuevo."""
    if recibo.estado != ReciboAnticipo.EMITIDO:
        raise ValidationError('Ya está anulado.')
    recibo.estado = ReciboAnticipo.ANULADO
    recibo.motivo_anulacion = motivo[:250]
    recibo.modificado_por = usuario
    recibo.save(update_fields=['estado', 'motivo_anulacion', 'modificado_por', 'modificado'])
    return recibo


def anular_anticipo(anticipo, usuario, motivo):
    if anticipo.estado not in (Anticipo.SOLICITADO, Anticipo.APROBADO):
        raise ValidationError('Solo se anula un anticipo que todavía no se pagó.')
    return _resolver(anticipo, Anticipo.ANULADO, usuario, motivo)


# ------------------------------------------------------------------ préstamos
def aprobar_prestamo(prestamo, usuario):
    if prestamo.estado != Prestamo.SOLICITADO:
        raise ValidationError('Solo se aprueba un préstamo solicitado.')
    if not prestamo.documento_id:
        raise ValidationError({'documento': 'Adjuntá la autorización firmada del empleado antes de aprobar.'})
    _separacion(prestamo, usuario)
    prestamo.full_clean()
    return _resolver(prestamo, Prestamo.APROBADO, usuario)


def rechazar_prestamo(prestamo, usuario, motivo):
    if prestamo.estado != Prestamo.SOLICITADO:
        raise ValidationError('Solo se rechaza un préstamo solicitado.')
    return _resolver(prestamo, Prestamo.RECHAZADO, usuario, motivo)


@transaction.atomic
def desembolsar_prestamo(prestamo, usuario, referencia=''):
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.APROBADO:
        raise ValidationError('Solo se desembolsa un préstamo aprobado.')
    concepto = _concepto(prestamo, 'CUOTA_PRESTAMO')
    for numero, mes, monto in prestamo.plan():
        CuotaRecuperacion.objects.create(empresa_id=prestamo.empresa_id, empleado_id=prestamo.empleado_id, prestamo=prestamo,
                                         concepto=concepto, numero=numero, mes=mes, monto=monto,
                                         creado_por=usuario, modificado_por=usuario)
    prestamo.estado = Prestamo.DESEMBOLSADO
    prestamo.desembolsado_por = usuario
    prestamo.desembolsado_en = timezone.now()
    prestamo.referencia_pago = referencia[:100]
    prestamo.save(update_fields=['estado', 'desembolsado_por', 'desembolsado_en', 'referencia_pago', 'modificado'])
    return prestamo


def anular_prestamo(prestamo, usuario, motivo):
    if prestamo.estado not in (Prestamo.SOLICITADO, Prestamo.APROBADO):
        raise ValidationError('Solo se anula un préstamo que todavía no se desembolsó.')
    return _resolver(prestamo, Prestamo.ANULADO, usuario, motivo)


@transaction.atomic
def cancelar_saldo(objeto, usuario, motivo):
    """El empleado pagó aparte lo que faltaba: las cuotas pendientes quedan "pagadas aparte" (no se borran)."""
    estado_activo = Anticipo.PAGADO if isinstance(objeto, Anticipo) else Prestamo.DESEMBOLSADO
    if objeto.estado != estado_activo:
        raise ValidationError('No tiene saldo en curso.')
    saldo = saldo_de(objeto)
    objeto.cuotas_recuperacion.filter(estado=CuotaRecuperacion.PENDIENTE).update(
        estado=CuotaRecuperacion.PAGADA_APARTE, modificado_por=usuario, modificado=timezone.now())
    objeto.estado = Anticipo.RECUPERADO if isinstance(objeto, Anticipo) else Prestamo.CANCELADO
    objeto.motivo_resolucion = f'Saldo de {saldo:,.0f} pagado aparte: {motivo}'.replace(',', '.')[:250]
    objeto.modificado_por = usuario
    objeto.save(update_fields=['estado', 'motivo_resolucion', 'modificado_por', 'modificado'])
    return objeto, saldo
