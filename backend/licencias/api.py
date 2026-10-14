"""API de licencias y vacaciones (fase 7).

- Tipos de licencia y escala de vacaciones: catálogos (globales + propios).
- Solicitudes: las carga RR. HH. o las pide el empleado para sí (pendientes);
  `aprobar`, `rechazar`, `cancelar`. Los días se calculan en el servidor.
- Movimientos de vacaciones: consulta, ajustes manuales con motivo, `saldo` y
  `devengar` (devengo anual por aniversario).
- Certificados médicos: datos del reposo, sin diagnóstico."""
from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from asistencia.models import ConfiguracionMarcacion
from core import alcance, auditoria
from core.api.base import CatalogoViewSet, RegistroSerializer, RegistroViewSet, a_error_drf
from core.models import EventoAuditoria
from empleados.models import Empleado
from licencias import servicios
from licencias.models import (CertificadoMedico, EscalaVacaciones, MovimientoVacaciones, SolicitudLicencia, TipoLicencia,
                              saldo_vacaciones)


class TipoLicenciaSerializer(RegistroSerializer):
    es_global = serializers.BooleanField(read_only=True)

    class Meta:
        model = TipoLicencia
        fields = '__all__'


class TipoLicenciaViewSet(CatalogoViewSet):
    serializer_class = TipoLicenciaSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('activo', 'categoria', 'consume_vacaciones')


class EscalaSerializer(RegistroSerializer):
    es_global = serializers.BooleanField(read_only=True)

    class Meta:
        model = EscalaVacaciones
        fields = '__all__'


class EscalaViewSet(CatalogoViewSet):
    serializer_class = EscalaSerializer
    ordering = ['desde_anios']


class SolicitudSerializer(RegistroSerializer):
    class Meta:
        model = SolicitudLicencia
        fields = '__all__'

    def create(self, datos):
        solicitud = SolicitudLicencia(**datos)
        solicitud.calcular()
        solicitud.save()
        return solicitud

    def update(self, solicitud, datos):
        for campo, valor in datos.items():
            setattr(solicitud, campo, valor)
        solicitud.calcular()
        solicitud.save()
        return solicitud


def _solo_para_si(request, empleado):
    usuario = request.user
    if not (alcance.es_plataforma(usuario) or alcance.tiene_alcance_empresa(usuario)):
        propio = alcance.empleado_propio(usuario)
        if propio is None or empleado != propio:
            raise PermissionDenied('Solo podés pedirlo para vos.')


class SolicitudViewSet(RegistroViewSet):
    serializer_class = SolicitudSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'empleado__primer_nombre', 'motivo', 'tipo__nombre']
    filtros_exactos = ('empleado', 'estado', 'tipo')
    campo_fecha = 'fecha_desde'
    permite_borrar = False
    permisos_acciones = {'aprobar': 'licencias.aprobar_licencia', 'rechazar': 'licencias.aprobar_licencia',
                         'cancelar': 'licencias.add_solicitudlicencia'}

    def perform_create(self, serializer):
        _solo_para_si(self.request, serializer.validated_data.get('empleado'))
        super().perform_create(serializer)

    def perform_update(self, serializer):
        if serializer.instance.estado != SolicitudLicencia.PENDIENTE:
            raise ValidationError({'detail': 'Solo se modifica una solicitud pendiente.'})
        _solo_para_si(self.request, serializer.instance.empleado)
        super().perform_update(serializer)

    def _resolver(self, request, funcion, descripcion):
        solicitud = self.get_object()
        try:
            solicitud = funcion(solicitud)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        solicitud.refresh_from_db()
        auditoria.registrar(request.user, EventoAuditoria.ACCION, solicitud, request=request, descripcion=descripcion)
        return Response(self.get_serializer(solicitud).data)

    def _motivo(self, request):
        motivo = str(request.data.get('motivo', '')).strip()
        if not motivo:
            raise ValidationError({'motivo': 'Indicá el motivo.'})
        return motivo

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        solicitud = self.get_object()
        if ConfiguracionMarcacion.de(solicitud.empresa).exigir_aprobador_distinto and solicitud.creado_por_id == request.user.pk:
            raise PermissionDenied('La empresa exige que lo apruebe otra persona (no quien lo cargó).')
        return self._resolver(request, lambda s: servicios.aprobar(s, request.user), 'Licencia aprobada.')

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        motivo = self._motivo(request)
        return self._resolver(request, lambda s: servicios.rechazar(s, request.user, motivo), f'Licencia rechazada: {motivo}')

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        """El empleado cancela su solicitud pendiente; una aprobada la cancela quien puede aprobar."""
        solicitud = self.get_object()
        motivo = self._motivo(request)
        puede_aprobar = alcance.tiene_permiso(request.user, 'licencias.aprobar_licencia')
        if solicitud.estado == SolicitudLicencia.APROBADA and not puede_aprobar:
            raise PermissionDenied('Una licencia aprobada la cancela Recursos Humanos.')
        if not puede_aprobar:
            _solo_para_si(request, solicitud.empleado)
        return self._resolver(request, lambda s: servicios.cancelar(s, request.user, motivo), f'Licencia cancelada: {motivo}')


class MovimientoSerializer(RegistroSerializer):
    class Meta:
        model = MovimientoVacaciones
        fields = '__all__'


class MovimientoViewSet(RegistroViewSet):
    """Los movimientos no se editan ni se borran: un error se corrige con otro movimiento."""

    serializer_class = MovimientoSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'motivo']
    filtros_exactos = ('empleado', 'tipo')
    campo_fecha = 'fecha'
    permite_borrar = False
    http_method_names = ['get', 'post', 'head', 'options']
    permisos_acciones = {'saldo': 'licencias.view_movimientovacaciones', 'saldos': 'licencias.view_movimientovacaciones',
                         'devengar': 'licencias.devengar_vacaciones'}

    def perform_create(self, serializer):
        if serializer.validated_data.get('tipo') not in (MovimientoVacaciones.AJUSTE, MovimientoVacaciones.VENCIMIENTO,
                                                          MovimientoVacaciones.CORRECCION):
            raise ValidationError({'tipo': 'A mano solo se cargan ajustes, vencimientos o correcciones (el devengo y el goce los genera el sistema).'})
        super().perform_create(serializer)

    @action(detail=False, methods=['get'])
    def saldo(self, request):
        """`?empleado=<id>`: saldo de vacaciones (el propio para el perfil Empleado)."""
        empleados = alcance.filtrar(Empleado.objects.all(), request.user)
        empleado = empleados.filter(pk=request.query_params.get('empleado') or 0).first() or alcance.empleado_propio(request.user)
        if empleado is None or not empleados.filter(pk=empleado.pk).exists():
            return Response({'detail': 'Empleado no encontrado.'}, status=404)
        movimientos = MovimientoVacaciones.objects.filter(empleado=empleado)
        return Response({
            'empleado': empleado.pk,
            'saldo': saldo_vacaciones(empleado),
            'devengado': sum(m.dias for m in movimientos if m.dias > 0),
            'gozado': -sum(m.dias for m in movimientos if m.tipo == MovimientoVacaciones.GOCE),
            'pendiente_de_aprobar': sum(s.dias for s in SolicitudLicencia.objects.filter(
                empleado=empleado, estado=SolicitudLicencia.PENDIENTE, tipo__consume_vacaciones=True)),
            'proximo_aniversario': servicios.proximo_aniversario(empleado),
        })

    @action(detail=False, methods=['get'])
    def saldos(self, request):
        """Saldo de cada empleado activo que el usuario ve (`?buscar=` por código o nombre)."""
        empleados = alcance.filtrar(Empleado.objects.all(), request.user).exclude(estado=Empleado.BAJA)
        buscar = request.query_params.get('buscar', '').strip()
        if buscar:
            empleados = empleados.filter(Q(codigo__icontains=buscar) | Q(primer_apellido__icontains=buscar)
                                         | Q(primer_nombre__icontains=buscar))
        saldos = dict(MovimientoVacaciones.objects.filter(empleado__in=empleados).values('empleado')
                      .annotate(t=Sum('dias')).values_list('empleado', 't'))
        pendientes = dict(SolicitudLicencia.objects.filter(
            empleado__in=empleados, estado=SolicitudLicencia.PENDIENTE, tipo__consume_vacaciones=True,
        ).values('empleado').annotate(t=Sum('dias')).values_list('empleado', 't'))
        return Response([{
            'empleado': e.pk, 'codigo': e.codigo, 'nombre': str(e), 'fecha_ingreso': e.fecha_ingreso,
            'saldo': saldos.get(e.pk) or 0, 'pendiente_de_aprobar': pendientes.get(e.pk) or 0,
            'proximo_aniversario': servicios.proximo_aniversario(e),
        } for e in empleados.order_by('primer_apellido', 'primer_nombre')[:500]])

    @action(detail=False, methods=['post'])
    def devengar(self, request):
        """`{"desde"?, "hasta"?}`: devengo de los aniversarios del período (por defecto, el último año)."""
        campo = serializers.DateField()
        hoy = timezone.localdate()
        try:
            hasta = campo.to_internal_value(request.data['hasta']) if request.data.get('hasta') else hoy
            desde = campo.to_internal_value(request.data['desde']) if request.data.get('desde') else hasta.replace(year=hasta.year - 1)
        except (serializers.ValidationError, ValueError):
            raise ValidationError({'desde': 'Fechas inválidas (AAAA-MM-DD).'})
        hasta = min(hasta, hoy)
        empleados = alcance.filtrar(Empleado.objects.select_related('empresa'), request.user).exclude(estado=Empleado.BAJA)
        creados = servicios.devengar(empleados, desde, hasta, request.user)
        auditoria.registrar(request.user, EventoAuditoria.ACCION, None, empresa=alcance.empresa_de(request.user),
                            modelo='licencias.MovimientoVacaciones', request=request,
                            descripcion=f'Devengo de vacaciones del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}: {len(creados)} movimientos.')
        return Response({'creados': len(creados), 'desde': desde, 'hasta': hasta,
                         'detalle': [{'empleado': str(e), 'aniversario': a, 'anios': n, 'dias': d} for e, a, n, d in creados]})


class CertificadoSerializer(RegistroSerializer):
    class Meta:
        model = CertificadoMedico
        fields = '__all__'


class CertificadoViewSet(RegistroViewSet):
    serializer_class = CertificadoSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'emisor', 'numero']
    filtros_exactos = ('empleado', 'estado')
    campo_fecha = 'fecha_desde'
    permite_borrar = False
