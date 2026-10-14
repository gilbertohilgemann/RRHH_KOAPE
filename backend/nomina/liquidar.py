"""Ciclo de vida de la nómina: crear y calcular, revisar, aprobar, cerrar,
rectificar, anular, emitir recibos y registrar pagos (§10: "abrir período →
verificar → simular → revisar → aprobar → cerrar → pagar → emitir recibos.
Rectificar mediante corrida vinculada").

Cerrada, una liquidación no se modifica nunca: se corrige con una
rectificación enlazada, con motivo, que rehace el período con los datos
actuales; se paga (o se recupera) solo la diferencia."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from nomina import motor
from nomina.models import (AsignacionCostoPatronal, CorridaNomina, LineaNomina, LiquidacionEmpleado, PagoNomina, PeriodoNomina,
                           ReciboSueldo, SecuenciaDocumento)


def periodo_cerrado(empresa, fecha):
    """¿La fecha cae en un período de nómina cerrado? (lo consultan la asistencia, la importación y las licencias)."""
    if empresa is None:
        return False
    # Los especiales (aguinaldo, liquidación final) no cierran la asistencia del año.
    return PeriodoNomina.objects.filter(empresa=empresa, estado=PeriodoNomina.CERRADO, fecha_desde__lte=fecha,
                                        fecha_hasta__gte=fecha).exclude(tipo='especial').exists()


def _separacion(corrida, usuario):
    from asistencia.models import ConfiguracionMarcacion
    if ConfiguracionMarcacion.de(corrida.empresa).exigir_aprobador_distinto and corrida.calculado_por_id == usuario.pk:
        raise ValidationError('La empresa exige que la apruebe otra persona (no quien la calculó).')


def _calcular(corrida, usuario):
    try:
        return motor.calcular(corrida, usuario)
    except ValueError as e:
        raise ValidationError(str(e))


@transaction.atomic
def crear(periodo, usuario):
    periodo = PeriodoNomina.objects.select_for_update().get(pk=periodo.pk)
    if periodo.estado != PeriodoNomina.ABIERTO:
        raise ValidationError('El período está cerrado: para corregirlo, rectificá su liquidación.')
    if periodo.corridas.filter(tipo=CorridaNomina.REGULAR).exclude(estado=CorridaNomina.ANULADA).exists():
        raise ValidationError('El período ya tiene una liquidación: recalculala en lugar de crear otra.')
    numero = (periodo.corridas.aggregate(n=Max('numero'))['n'] or 0) + 1
    corrida = CorridaNomina.objects.create(empresa=periodo.empresa, periodo=periodo, numero=numero, creado_por=usuario,
                                           modificado_por=usuario)
    return _calcular(corrida, usuario)


def recalcular(corrida, usuario):
    return _calcular(corrida, usuario)


@transaction.atomic
def crear_aguinaldo(empresa, anio, usuario):
    """Período especial del año (01/01 al 31/12) y su liquidación de aguinaldo."""
    from datetime import date
    periodo, _ = PeriodoNomina.objects.get_or_create(
        empresa=empresa, codigo=f'AGUINALDO-{anio}',
        defaults={'tipo': 'especial', 'fecha_desde': date(anio, 1, 1), 'fecha_hasta': date(anio, 12, 31),
                  'creado_por': usuario, 'modificado_por': usuario})
    if periodo.corridas.filter(tipo='aguinaldo').exclude(estado=CorridaNomina.ANULADA).exists():
        raise ValidationError(f'El aguinaldo {anio} ya tiene una liquidación: recalculala o, si está cerrada, rectificala.')
    numero = (periodo.corridas.aggregate(n=Max('numero'))['n'] or 0) + 1
    corrida = CorridaNomina.objects.create(empresa=empresa, periodo=periodo, numero=numero, tipo='aguinaldo',
                                           creado_por=usuario, modificado_por=usuario)
    return _calcular(corrida, usuario)


@transaction.atomic
def calcular_final(final, usuario):
    """Crea (o recalcula) la corrida de la liquidación final: un período especial desde el día siguiente a la
    última nómina cerrada del empleado hasta el egreso."""
    from datetime import timedelta
    from nomina.models import LiquidacionFinal
    final = LiquidacionFinal.objects.select_for_update().select_related('empleado').get(pk=final.pk)
    if final.corrida_id and final.corrida.estado != CorridaNomina.ANULADA:
        return _calcular(final.corrida, usuario)
    abiertas = CorridaNomina.objects.filter(
        liquidaciones__empleado=final.empleado, tipo__in=(CorridaNomina.REGULAR, CorridaNomina.RECTIFICACION),
        estado__in=(CorridaNomina.CALCULADA, CorridaNomina.REVISADA, CorridaNomina.APROBADA),
        periodo__fecha_hasta__gte=final.fecha_egreso.replace(day=1))
    if abiertas.exists():
        raise ValidationError(f'El empleado está en la liquidación "{abiertas.first()}" sin cerrar: recalculala (así queda '
                              'fuera, porque cobra en la liquidación final) o anulala.')
    ultima = LiquidacionEmpleado.objects.filter(
        empleado=final.empleado, corrida__estado=CorridaNomina.CERRADA, corrida__rectificada=False,
        corrida__tipo__in=(CorridaNomina.REGULAR, CorridaNomina.RECTIFICACION)).aggregate(h=Max('corrida__periodo__fecha_hasta'))['h']
    desde = ultima + timedelta(days=1) if ultima else max(final.empleado.fecha_ingreso, final.fecha_egreso.replace(day=1))
    desde = min(desde, final.fecha_egreso)
    periodo = PeriodoNomina.objects.create(
        empresa_id=final.empresa_id, codigo=f'FINAL-{final.empleado.codigo}-{final.fecha_egreso:%Y%m%d}-{final.pk}', tipo='especial',
        fecha_desde=desde, fecha_hasta=final.fecha_egreso, creado_por=usuario, modificado_por=usuario)
    corrida = CorridaNomina.objects.create(empresa_id=final.empresa_id, periodo=periodo, numero=1, tipo='liquidacion_final',
                                           creado_por=usuario, modificado_por=usuario)
    final.corrida = corrida
    final.save(update_fields=['corrida', 'modificado'])
    return _calcular(corrida, usuario)


def revisar(corrida, usuario):
    if corrida.estado != CorridaNomina.CALCULADA:
        raise ValidationError('Solo se revisa una liquidación calculada.')
    corrida.estado = CorridaNomina.REVISADA
    corrida.revisado_por = usuario
    corrida.revisado_en = timezone.now()
    corrida.save(update_fields=['estado', 'revisado_por', 'revisado_en', 'modificado'])
    return corrida


def aprobar(corrida, usuario):
    """Bloquea si es una simulación (reglas sin aprobar) o si algún empleado tiene errores (§8)."""
    if corrida.estado != CorridaNomina.REVISADA:
        raise ValidationError('Primero hay que revisarla.')
    if corrida.es_simulacion:
        raise ValidationError('Es una simulación: usa reglas legales o de cálculo sin aprobar. Aprobalas y recalculá.')
    errores = corrida.liquidaciones.filter(estado_calculo=LiquidacionEmpleado.ERROR).count()
    if errores:
        raise ValidationError(f'{errores} empleado(s) tienen errores (contrato, sueldo, reglas…): corregilos y recalculá.')
    _separacion(corrida, usuario)
    corrida.estado = CorridaNomina.APROBADA
    corrida.aprobado_por = usuario
    corrida.aprobado_en = timezone.now()
    corrida.save(update_fields=['estado', 'aprobado_por', 'aprobado_en', 'modificado'])
    return corrida


@transaction.atomic
def cerrar(corrida, usuario):
    """Marca aplicadas las novedades y cuotas (una sola vez), guarda el costo del empleador y cierra el período."""
    from novedades.models import Anticipo, CuotaRecuperacion, Novedad, Prestamo, saldo_de
    corrida = CorridaNomina.objects.select_for_update().select_related('periodo', 'corrida_origen').get(pk=corrida.pk)
    if corrida.estado != CorridaNomina.APROBADA:
        raise ValidationError('Solo se cierra una liquidación aprobada.')
    ahora = timezone.now()
    lineas = LineaNomina.objects.filter(liquidacion__corrida=corrida)
    ids_novedades = list(lineas.filter(origen='novedad').values_list('origen_id', flat=True))
    ids_cuotas = list(lineas.filter(origen='cuota').values_list('origen_id', flat=True))
    if corrida.corrida_origen_id:
        # Lo que aplicó la corrida rectificada y ya no aparece vuelve a quedar disponible.
        Novedad.objects.filter(corrida=corrida.corrida_origen_id, estado=Novedad.APLICADA).exclude(pk__in=ids_novedades).update(
            estado=Novedad.APROBADA, corrida=None)
        CuotaRecuperacion.objects.filter(corrida=corrida.corrida_origen_id, estado=CuotaRecuperacion.APLICADA).exclude(
            pk__in=ids_cuotas).update(estado=CuotaRecuperacion.PENDIENTE, corrida=None, aplicada_en=None)
    Novedad.objects.filter(pk__in=ids_novedades).update(estado=Novedad.APLICADA, corrida=corrida.pk)
    cuotas = CuotaRecuperacion.objects.filter(pk__in=ids_cuotas)
    cuotas.update(estado=CuotaRecuperacion.APLICADA, corrida=corrida.pk, aplicada_en=ahora)
    for anticipo in Anticipo.objects.filter(cuotas_recuperacion__pk__in=ids_cuotas, estado=Anticipo.PAGADO).distinct():
        if not saldo_de(anticipo):
            Anticipo.objects.filter(pk=anticipo.pk).update(estado=Anticipo.RECUPERADO)
    for prestamo in Prestamo.objects.filter(cuotas_recuperacion__pk__in=ids_cuotas, estado=Prestamo.DESEMBOLSADO).distinct():
        if not saldo_de(prestamo):
            Prestamo.objects.filter(pk=prestamo.pk).update(estado=Prestamo.CANCELADO)
    AsignacionCostoPatronal.objects.bulk_create([AsignacionCostoPatronal(
        empresa_id=corrida.empresa_id, corrida=corrida, periodo=corrida.periodo, empleado_id=liq.empleado_id,
        centro_costo_id=liq.centro_costo_id, remuneracion_bruta=liq.bruto, aporte_patronal=liq.aportes_patronales,
        otros_costos=liq.otros_costos, costo_total=liq.costo_empleador, provision_aguinaldo=liq.provision_aguinaldo,
        creado_por=usuario, modificado_por=usuario) for liq in corrida.liquidaciones.all()])
    if corrida.corrida_origen_id:
        # La original no se toca (es histórica): queda marcada y los informes toman la rectificación.
        CorridaNomina.objects.filter(pk=corrida.corrida_origen_id).update(rectificada=True)
    if corrida.tipo == 'liquidacion_final':
        # Las vacaciones pagadas en el egreso salen del saldo (con un movimiento, nunca editando los anteriores).
        from licencias.models import MovimientoVacaciones
        for linea in lineas.filter(codigo='VACACIONES_CAUSADAS', cantidad__gt=0).select_related('liquidacion'):
            MovimientoVacaciones.objects.create(
                empresa_id=corrida.empresa_id, empleado_id=linea.liquidacion.empleado_id, fecha=corrida.periodo.fecha_hasta,
                tipo=MovimientoVacaciones.AJUSTE, dias=-linea.cantidad, motivo='Vacaciones pagadas en la liquidación final',
                creado_por=usuario, modificado_por=usuario)
    periodo = corrida.periodo
    if periodo.estado == PeriodoNomina.ABIERTO:
        periodo.estado = PeriodoNomina.CERRADO
        periodo.cerrado_por = usuario
        periodo.cerrado_en = ahora
        periodo.save(update_fields=['estado', 'cerrado_por', 'cerrado_en', 'modificado'])
    corrida.estado = CorridaNomina.CERRADA
    corrida.cerrado_por = usuario
    corrida.cerrado_en = ahora
    corrida.save(update_fields=['estado', 'cerrado_por', 'cerrado_en', 'modificado'])
    return corrida


@transaction.atomic
def rectificar(corrida, usuario, motivo):
    """Crea y calcula una corrida enlazada que rehace el período de una cerrada."""
    corrida = CorridaNomina.objects.select_for_update().get(pk=corrida.pk)
    if corrida.estado != CorridaNomina.CERRADA or corrida.rectificada:
        raise ValidationError('Solo se rectifica una liquidación cerrada (y que no esté ya rectificada).')
    if corrida.rectificaciones.exclude(estado__in=(CorridaNomina.ANULADA, CorridaNomina.CERRADA)).exists():
        raise ValidationError('Ya hay una rectificación en curso para esta liquidación.')
    numero = (corrida.periodo.corridas.aggregate(n=Max('numero'))['n'] or 0) + 1
    # El aguinaldo y la liquidación final se rectifican con su mismo tipo (enlazados a la original).
    tipo = corrida.tipo if corrida.tipo in ('aguinaldo', 'liquidacion_final') else CorridaNomina.RECTIFICACION
    nueva = CorridaNomina.objects.create(empresa_id=corrida.empresa_id, periodo=corrida.periodo, numero=numero,
                                         tipo=tipo, corrida_origen=corrida, motivo_rectificacion=motivo[:250],
                                         creado_por=usuario, modificado_por=usuario)
    return _calcular(nueva, usuario)


def anular(corrida, usuario, motivo):
    if corrida.estado in (CorridaNomina.CERRADA, CorridaNomina.ANULADA):
        raise ValidationError('Una liquidación cerrada no se anula: se rectifica.')
    corrida.estado = CorridaNomina.ANULADA
    corrida.motivo_rectificacion = motivo[:250]
    corrida.modificado_por = usuario
    corrida.save(update_fields=['estado', 'motivo_rectificacion', 'modificado_por', 'modificado'])
    return corrida


# -------------------------------------------------------------------- recibos
def _siguiente_numero(empresa, tipo, anio):
    secuencia, _ = SecuenciaDocumento.objects.select_for_update().get_or_create(empresa=empresa, tipo=tipo, anio=anio)
    numero = secuencia.siguiente
    secuencia.siguiente += 1
    secuencia.save(update_fields=['siguiente'])
    return f'{secuencia.prefijo}{anio}-{numero:06d}'


@transaction.atomic
def emitir_recibos(corrida, usuario):
    """Un recibo numerado por empleado que todavía no tenga uno vigente de esta corrida."""
    if corrida.estado != CorridaNomina.CERRADA:
        raise ValidationError('Los recibos se emiten de una liquidación cerrada.')
    tipo = {CorridaNomina.RECTIFICACION: 'rectificacion', 'aguinaldo': 'aguinaldo', 'liquidacion_final': 'liquidacion_final'}.get(
        corrida.tipo, 'sueldo')
    con_recibo = set(corrida.recibos.filter(estado=ReciboSueldo.EMITIDO).values_list('liquidacion_id', flat=True))
    emitidos = []
    for liq in corrida.liquidaciones.select_related('empleado').order_by('empleado__primer_apellido'):
        if liq.pk in con_recibo:
            continue
        emitidos.append(ReciboSueldo.objects.create(
            empresa_id=corrida.empresa_id, corrida=corrida, liquidacion=liq, empleado_id=liq.empleado_id,
            numero=_siguiente_numero(corrida.empresa, 'recibo', corrida.periodo.fecha_hasta.year), tipo=tipo,
            fecha_emision=timezone.localdate(), periodo_desde=corrida.periodo.fecha_desde, periodo_hasta=corrida.periodo.fecha_hasta,
            bruto=liq.bruto, descuentos=liq.descuentos + liq.aportes_trabajador, neto=liq.neto, costo_empleador=liq.costo_empleador,
            creado_por=usuario, modificado_por=usuario))
    return emitidos


def publicar_recibos(corrida, usuario):
    return corrida.recibos.filter(estado=ReciboSueldo.EMITIDO, publicado=False).update(
        publicado=True, modificado_por=usuario, modificado=timezone.now())


def anular_recibo(recibo, usuario, motivo):
    if recibo.estado != ReciboSueldo.EMITIDO:
        raise ValidationError('Ya está anulado.')
    recibo.estado = ReciboSueldo.ANULADO
    recibo.publicado = False
    recibo.motivo_anulacion = motivo[:250]
    recibo.modificado_por = usuario
    recibo.save(update_fields=['estado', 'publicado', 'motivo_anulacion', 'modificado_por', 'modificado'])
    return recibo


# ---------------------------------------------------------------------- pagos
@transaction.atomic
def registrar_pagos(corrida, usuario, fecha, forma='transferencia', referencia=''):
    """Un pago por empleado pendiente con importe a cobrar (en una rectificación, la diferencia).
    Una diferencia negativa (a recuperar) no genera pago: queda como advertencia."""
    from empleados.models import CuentaBancaria
    if corrida.estado != CorridaNomina.CERRADA:
        raise ValidationError('Se paga una liquidación cerrada.')
    if forma not in dict(PagoNomina.FORMA_OPCIONES):
        raise ValidationError({'forma': 'Forma de pago inválida.'})
    creados, a_recuperar = [], []
    for liq in corrida.liquidaciones.select_for_update().filter(estado_pago='pendiente'):
        monto = liq.a_pagar
        if monto < 0:
            a_recuperar.append(liq)
            continue
        if monto == 0:
            continue
        cuenta = CuentaBancaria.objects.filter(empleado_id=liq.empleado_id, activa=True, principal=True).first() \
            if forma == 'transferencia' else None
        creados.append(PagoNomina.objects.create(
            empresa_id=corrida.empresa_id, corrida=corrida, liquidacion=liq, empleado_id=liq.empleado_id, fecha=fecha, monto=monto,
            forma=forma, referencia=referencia[:100], cuenta_bancaria=cuenta, creado_por=usuario, modificado_por=usuario))
        liq.estado_pago = 'registrado'
        liq.save(update_fields=['estado_pago', 'modificado'])
    return creados, a_recuperar


def confirmar_pago(pago, usuario):
    if pago.estado != PagoNomina.REGISTRADO:
        raise ValidationError('Solo se confirma un pago registrado.')
    pago.estado = PagoNomina.CONFIRMADO
    pago.confirmado_por = usuario
    pago.confirmado_en = timezone.now()
    pago.save(update_fields=['estado', 'confirmado_por', 'confirmado_en', 'modificado'])
    LiquidacionEmpleado.objects.filter(pk=pago.liquidacion_id).update(estado_pago='pagado')
    return pago


def anular_pago(pago, usuario, motivo):
    if pago.estado != PagoNomina.REGISTRADO:
        raise ValidationError('Solo se anula un pago registrado (uno confirmado ya salió del banco).')
    pago.estado = PagoNomina.ANULADO
    pago.motivo_anulacion = motivo[:250]
    pago.modificado_por = usuario
    pago.save(update_fields=['estado', 'motivo_anulacion', 'modificado_por', 'modificado'])
    LiquidacionEmpleado.objects.filter(pk=pago.liquidacion_id).update(estado_pago='pendiente')
    return pago
