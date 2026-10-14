"""API del motor de asistencia (fase 6).

- Días de asistencia: consulta (cada uno con su explicación y sus marcas),
  `calcular` un período y `revisar` un día.
- Ajustes de marcación: los carga RR. HH. o los pide el propio empleado
  (quedan pendientes); `aprobar` crea la marca nueva o anula la errónea, sin
  editar nunca la original; `rechazar` con motivo.
- Autorizaciones de horas extra: `aprobar` (con los minutos aprobados) o
  `rechazar`. Sin aprobación, las horas extra quedan solo como candidatas."""
import hashlib

from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from asistencia import motor
from asistencia.models import (AjusteMarcacion, AutorizacionHorasExtra, ConfiguracionMarcacion, DiaAsistencia,
                               IncidenciaAsistencia, Marcacion)
from core import alcance, auditoria
from core.api.base import RegistroSerializer, RegistroViewSet, a_error_drf
from core.models import EventoAuditoria
from empleados.models import Empleado

MAXIMO_DIAS_POR_CALCULO = 93


class DiaAsistenciaSerializer(RegistroSerializer):
    class Meta:
        model = DiaAsistencia
        fields = '__all__'


class DiaAsistenciaViewSet(RegistroViewSet):
    serializer_class = DiaAsistenciaSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'empleado__primer_nombre']
    filtros_exactos = ('empleado', 'estado', 'fecha')
    campo_fecha = 'fecha'
    permite_borrar = False
    http_method_names = ['get', 'post', 'head', 'options']
    permisos_acciones = {'calcular': 'asistencia.calcular_asistencia', 'revisar': 'asistencia.revisar_asistencia'}

    def create(self, request, *args, **kwargs):
        return Response({'detail': 'Los días los calcula el sistema: usá "calcular".'}, status=405)

    def retrieve(self, request, *args, **kwargs):
        """El día con sus marcas (también las anuladas, señaladas) y sus incidencias."""
        dia = self.get_object()
        datos = self.get_serializer(dia).data
        marcas = motor.marcas_del_dia(dia.empleado, dia.fecha)
        datos['marcas'] = [{
            'id': m.pk, 'fecha_hora': m.fecha_hora, 'tipo': m.tipo, 'tipo_texto': m.get_tipo_display(),
            'metodo_texto': m.get_metodo_display(), 'anulada': m.anulada, 'motivo_anulacion': m.motivo_anulacion,
            'terminal': str(m.terminal) if m.terminal_id else (str(m.reloj) if m.reloj_id else ''),
        } for m in marcas]
        datos['incidencias'] = [{'id': i.pk, 'tipo_texto': i.get_tipo_display(), 'descripcion': i.descripcion,
                                 'estado': i.estado, 'estado_texto': i.get_estado_display()}
                                for i in IncidenciaAsistencia.objects.filter(empleado=dia.empleado, fecha=dia.fecha)]
        return Response(datos)

    @action(detail=False, methods=['post'])
    def calcular(self, request):
        """`POST {"desde", "hasta", "empleado"?}`: calcula o recalcula ese período
        (todos los empleados que el usuario ve, o uno)."""
        campo = serializers.DateField()
        try:
            desde = campo.to_internal_value(request.data.get('desde'))
            hasta = campo.to_internal_value(request.data.get('hasta') or request.data.get('desde'))
        except serializers.ValidationError:
            raise ValidationError({'desde': 'Indicá las fechas (AAAA-MM-DD).'})
        if hasta < desde:
            raise ValidationError({'hasta': 'No puede ser anterior a "desde".'})
        hasta = min(hasta, timezone.localdate())
        if (hasta - desde).days >= MAXIMO_DIAS_POR_CALCULO:
            raise ValidationError({'hasta': f'Calculá como máximo {MAXIMO_DIAS_POR_CALCULO} días por vez.'})
        empleados = alcance.filtrar(Empleado.objects.select_related('empresa'), request.user).filter(fecha_ingreso__lte=hasta)
        if request.data.get('empleado'):
            empleados = empleados.filter(pk=request.data.get('empleado'))
        dias = 0
        for empleado in empleados:
            dias += len(motor.calcular(empleado, desde, hasta))
        auditoria.registrar(request.user, EventoAuditoria.ACCION, None, empresa=alcance.empresa_de(request.user),
                            modelo='asistencia.DiaAsistencia', request=request,
                            descripcion=f'Asistencia calculada del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}: {dias} días de {empleados.count()} empleados.')
        return Response({'dias': dias, 'empleados': empleados.count(), 'desde': desde, 'hasta': hasta})

    @action(detail=True, methods=['post'])
    def revisar(self, request, pk=None):
        dia = self.get_object()
        dia.revisado_por = request.user
        dia.revisado_en = timezone.now()
        dia.save(update_fields=['revisado_por', 'revisado_en'])
        auditoria.registrar(request.user, EventoAuditoria.ACCION, dia, request=request, descripcion='Día revisado.')
        return Response(self.get_serializer(dia).data)


def _separacion(request, objeto):
    """Quien aprueba no puede ser quien pidió, si la empresa lo exige."""
    if ConfiguracionMarcacion.de(objeto.empresa).exigir_aprobador_distinto and objeto.creado_por_id == request.user.pk:
        raise PermissionDenied('La empresa exige que lo apruebe otra persona (no quien lo cargó).')


def _motivo(request):
    motivo = str(request.data.get('motivo', '')).strip()
    if not motivo:
        raise ValidationError({'motivo': 'Indicá el motivo.'})
    return motivo[:250]


class _ConSolicitudPropia(RegistroViewSet):
    """El perfil Empleado puede pedir para sí mismo (queda pendiente); el
    legajo se toma de su sesión, no del que mande el navegador."""

    permite_borrar = False
    http_method_names = ['get', 'post', 'head', 'options']

    def perform_create(self, serializer):
        usuario = self.request.user
        if not (alcance.es_plataforma(usuario) or alcance.tiene_alcance_empresa(usuario)):
            propio = alcance.empleado_propio(usuario)
            if propio is None or serializer.validated_data.get('empleado') != propio:
                raise PermissionDenied('Solo podés pedirlo para vos.')
        super().perform_create(serializer)


class AjusteSerializer(RegistroSerializer):
    class Meta:
        model = AjusteMarcacion
        fields = '__all__'


class AjusteViewSet(_ConSolicitudPropia):
    serializer_class = AjusteSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'motivo']
    filtros_exactos = ('empleado', 'estado', 'accion')
    campo_fecha = 'creado__date'
    permisos_acciones = {'aprobar': 'asistencia.aprobar_ajuste', 'rechazar': 'asistencia.aprobar_ajuste'}

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        ajuste = self.get_object()
        if ajuste.estado != AjusteMarcacion.PENDIENTE:
            raise ValidationError({'detail': 'El ajuste ya fue resuelto.'})
        _separacion(request, ajuste)
        try:
            ajuste.full_clean()
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        ahora = timezone.now()
        with transaction.atomic():
            if ajuste.accion == AjusteMarcacion.AGREGAR:
                ajuste.marcacion_creada = Marcacion.objects.create(
                    empresa_id=ajuste.empresa_id, empleado=ajuste.empleado, fecha_hora=ajuste.fecha_hora, tipo=ajuste.tipo,
                    metodo=Marcacion.MANUAL, nivel_verificacion='manual_aprobado', referencia=f'Ajuste {ajuste.pk}',
                    huella_deduplicacion=hashlib.sha256(f'ajuste|{ajuste.pk}'.encode()).hexdigest(),
                    creado_por=request.user, modificado_por=request.user,
                )
                momento = ajuste.fecha_hora
            else:
                Marcacion.objects.filter(pk=ajuste.marcacion_id).update(
                    anulada=True, anulada_en=ahora, motivo_anulacion=f'Ajuste {ajuste.pk}: {ajuste.motivo}'[:250])
                momento = ajuste.marcacion.fecha_hora
            ajuste.estado = AjusteMarcacion.APROBADO
            ajuste.aprobado_por = request.user
            ajuste.aprobado_en = ahora
            ajuste.save(update_fields=['estado', 'aprobado_por', 'aprobado_en', 'marcacion_creada', 'modificado'])
            auditoria.registrar(request.user, EventoAuditoria.ACCION, ajuste, request=request,
                                descripcion=f'Ajuste aprobado ({ajuste.get_accion_display().lower()}): {ajuste.motivo}')
            motor.recalcular_despues(ajuste.empleado, [momento])
        return Response(self.get_serializer(ajuste).data)

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        ajuste = self.get_object()
        if ajuste.estado != AjusteMarcacion.PENDIENTE:
            raise ValidationError({'detail': 'El ajuste ya fue resuelto.'})
        motivo = _motivo(request)
        ajuste.estado = AjusteMarcacion.RECHAZADO
        ajuste.aprobado_por = request.user
        ajuste.aprobado_en = timezone.now()
        ajuste.motivo_rechazo = motivo
        ajuste.save(update_fields=['estado', 'aprobado_por', 'aprobado_en', 'motivo_rechazo', 'modificado'])
        auditoria.registrar(request.user, EventoAuditoria.ACCION, ajuste, request=request, descripcion=f'Ajuste rechazado: {motivo}')
        return Response(self.get_serializer(ajuste).data)


class AutorizacionSerializer(RegistroSerializer):
    class Meta:
        model = AutorizacionHorasExtra
        fields = '__all__'


class AutorizacionViewSet(_ConSolicitudPropia):
    serializer_class = AutorizacionSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'motivo']
    filtros_exactos = ('empleado', 'estado')
    campo_fecha = 'fecha'
    permisos_acciones = {'aprobar': 'asistencia.aprobar_horas_extra', 'rechazar': 'asistencia.aprobar_horas_extra'}

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        """`{"minutos_aprobados"?}` (por defecto, los solicitados)."""
        autorizacion = self.get_object()
        if autorizacion.estado != AutorizacionHorasExtra.PENDIENTE:
            raise ValidationError({'detail': 'La autorización ya fue resuelta.'})
        _separacion(request, autorizacion)
        try:
            minutos = int(request.data.get('minutos_aprobados') or autorizacion.minutos_solicitados)
        except (TypeError, ValueError):
            raise ValidationError({'minutos_aprobados': 'Indicá los minutos.'})
        if not 0 < minutos <= autorizacion.minutos_solicitados:
            raise ValidationError({'minutos_aprobados': 'Entre 1 y los minutos solicitados.'})
        with transaction.atomic():
            autorizacion.estado = AutorizacionHorasExtra.APROBADA
            autorizacion.minutos_aprobados = minutos
            autorizacion.aprobado_por = request.user
            autorizacion.aprobado_en = timezone.now()
            autorizacion.save(update_fields=['estado', 'minutos_aprobados', 'aprobado_por', 'aprobado_en', 'modificado'])
            auditoria.registrar(request.user, EventoAuditoria.ACCION, autorizacion, request=request,
                                descripcion=f'Horas extra aprobadas: {minutos} min del {autorizacion.fecha:%d/%m/%Y}.')
            transaction.on_commit(lambda: motor.calcular(autorizacion.empleado, autorizacion.fecha))
        return Response(self.get_serializer(autorizacion).data)

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        autorizacion = self.get_object()
        if autorizacion.estado != AutorizacionHorasExtra.PENDIENTE:
            raise ValidationError({'detail': 'La autorización ya fue resuelta.'})
        motivo = _motivo(request)
        autorizacion.estado = AutorizacionHorasExtra.RECHAZADA
        autorizacion.aprobado_por = request.user
        autorizacion.aprobado_en = timezone.now()
        autorizacion.motivo_rechazo = motivo
        autorizacion.save(update_fields=['estado', 'aprobado_por', 'aprobado_en', 'motivo_rechazo', 'modificado'])
        auditoria.registrar(request.user, EventoAuditoria.ACCION, autorizacion, request=request,
                            descripcion=f'Horas extra rechazadas: {motivo}')
        return Response(self.get_serializer(autorizacion).data)
