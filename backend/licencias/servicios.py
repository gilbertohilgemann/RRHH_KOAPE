"""Operaciones de licencias y vacaciones: un solo lugar con las reglas, para
que la API, el admin y los comandos se comporten igual."""
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from licencias.models import EscalaVacaciones, MovimientoVacaciones, SolicitudLicencia, saldo_vacaciones


def _recalcular_asistencia(solicitud):
    """Al confirmarse la transacción, el motor recalcula los días de la licencia (ya pasados)."""
    from asistencia import motor
    hasta = min(solicitud.fecha_hasta, timezone.localdate())
    if hasta >= solicitud.fecha_desde:
        empleado = solicitud.empleado
        transaction.on_commit(lambda: motor.calcular(empleado, solicitud.fecha_desde, hasta))


@transaction.atomic
def aprobar(solicitud, usuario):
    solicitud = SolicitudLicencia.objects.select_for_update().select_related('tipo', 'empleado__empresa').get(pk=solicitud.pk)
    if solicitud.estado != SolicitudLicencia.PENDIENTE:
        raise ValidationError('Solo se aprueba una solicitud pendiente.')
    if solicitud.tipo.requiere_documento and not solicitud.documento_id:
        raise ValidationError('Este tipo de licencia exige un documento de respaldo: adjuntalo antes de aprobar.')
    solicitud.full_clean()
    solicitud.calcular()
    if solicitud.tipo.consume_vacaciones:
        saldo = saldo_vacaciones(solicitud.empleado)
        if solicitud.dias > saldo:
            raise ValidationError(f'Saldo de vacaciones insuficiente: tiene {saldo} días y pide {solicitud.dias}.')
        MovimientoVacaciones.objects.create(
            empresa_id=solicitud.empresa_id, empleado=solicitud.empleado, fecha=solicitud.fecha_desde,
            tipo=MovimientoVacaciones.GOCE, dias=-solicitud.dias, solicitud=solicitud,
            motivo=f'Vacaciones del {solicitud.fecha_desde:%d/%m/%Y} al {solicitud.fecha_hasta:%d/%m/%Y}',
            creado_por=usuario, modificado_por=usuario,
        )
    solicitud.estado = SolicitudLicencia.APROBADA
    solicitud.aprobado_por = usuario
    solicitud.aprobado_en = timezone.now()
    solicitud.save(update_fields=['estado', 'aprobado_por', 'aprobado_en', 'dias', 'minutos', 'modificado'])
    _recalcular_asistencia(solicitud)
    return solicitud


@transaction.atomic
def rechazar(solicitud, usuario, motivo):
    if solicitud.estado != SolicitudLicencia.PENDIENTE:
        raise ValidationError('Solo se rechaza una solicitud pendiente.')
    solicitud.estado = SolicitudLicencia.RECHAZADA
    solicitud.aprobado_por = usuario
    solicitud.aprobado_en = timezone.now()
    solicitud.motivo_resolucion = motivo[:250]
    solicitud.save(update_fields=['estado', 'aprobado_por', 'aprobado_en', 'motivo_resolucion', 'modificado'])
    return solicitud


@transaction.atomic
def cancelar(solicitud, usuario, motivo):
    """Una pendiente o una aprobada. Si ya había descontado vacaciones, las
    devuelve con un movimiento de corrección (el de goce no se borra)."""
    from asistencia.importacion import periodo_cerrado
    solicitud = SolicitudLicencia.objects.select_for_update().get(pk=solicitud.pk)
    if solicitud.estado not in (SolicitudLicencia.PENDIENTE, SolicitudLicencia.APROBADA):
        raise ValidationError('La solicitud ya fue rechazada o cancelada.')
    if solicitud.estado == SolicitudLicencia.APROBADA:
        if periodo_cerrado(solicitud.empresa, solicitud.fecha_desde):
            raise ValidationError('La licencia ya entró en una nómina cerrada: hace falta una rectificación.')
        tomado = sum(m.dias for m in solicitud.movimientos_vacaciones.all())
        if tomado:
            MovimientoVacaciones.objects.create(
                empresa_id=solicitud.empresa_id, empleado=solicitud.empleado, fecha=timezone.localdate(),
                tipo=MovimientoVacaciones.CORRECCION, dias=-tomado, solicitud=solicitud,
                motivo=f'Devolución por cancelación: {motivo}'[:250], creado_por=usuario, modificado_por=usuario,
            )
        _recalcular_asistencia(solicitud)
    solicitud.estado = SolicitudLicencia.CANCELADA
    solicitud.motivo_resolucion = motivo[:250]
    solicitud.modificado_por = usuario
    solicitud.save(update_fields=['estado', 'motivo_resolucion', 'modificado_por', 'modificado'])
    return solicitud


def _aniversario(ingreso, anios):
    try:
        return ingreso.replace(year=ingreso.year + anios)
    except ValueError:  # 29 de febrero
        return date(ingreso.year + anios, 2, 28)


def devengar(empleados, desde, hasta, usuario):
    """Genera el devengo de vacaciones de cada aniversario entre `desde` y
    `hasta` que todavía no tenga el suyo, según la escala por antigüedad.
    Devuelve [(empleado, aniversario, años, días)]."""
    creados = []
    for empleado in empleados:
        anios = 1
        while True:
            aniversario = _aniversario(empleado.fecha_ingreso, anios)
            if aniversario > hasta or (empleado.fecha_egreso and aniversario > empleado.fecha_egreso):
                break
            if aniversario >= desde and not MovimientoVacaciones.objects.filter(
                    empleado=empleado, tipo=MovimientoVacaciones.DEVENGO, periodo=anios).exists():
                dias, fila = EscalaVacaciones.dias_para(empleado.empresa, anios)
                if dias:
                    aviso = '' if fila.verificado else ' (escala sin verificar)'
                    MovimientoVacaciones.objects.create(
                        empresa_id=empleado.empresa_id, empleado=empleado, fecha=aniversario,
                        tipo=MovimientoVacaciones.DEVENGO, dias=dias, periodo=anios,
                        motivo=f'Devengo por {anios} año(s) de antigüedad: {fila}{aviso}'[:250],
                        creado_por=usuario, modificado_por=usuario,
                    )
                    creados.append((empleado, aniversario, anios, dias))
            anios += 1
    return creados


def proximo_aniversario(empleado, hoy=None):
    hoy = hoy or timezone.localdate()
    anios = max(hoy.year - empleado.fecha_ingreso.year, 1)
    aniversario = _aniversario(empleado.fecha_ingreso, anios)
    if aniversario < hoy:
        aniversario = _aniversario(empleado.fecha_ingreso, anios + 1)
    return aniversario

