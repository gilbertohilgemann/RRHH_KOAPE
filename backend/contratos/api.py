"""Contratos, historial salarial y esquemas salariales.

Ni los contratos ni los sueldos se borran ni se editan una vez que rigen:
- contrato: se edita solo en borrador; `activar`, `finalizar` y `anular`
  (permiso `contratos.gestionar_estado_contrato`);
- sueldo: se edita solo pendiente; `aprobar` y `rechazar` (permiso
  `contratos.aprobar_salario`).
El perfil Empleado ve sus contratos y solo sus sueldos aprobados."""
from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contratos.models import ContratoEmpleado, EsquemaSalarial, HistorialSalarial
from core import alcance, auditoria
from core.api.base import CatalogoViewSet, RegistroSerializer, RegistroViewSet, a_error_drf
from core.models import EventoAuditoria


class EsquemaSalarialSerializer(RegistroSerializer):
    es_global = serializers.BooleanField(read_only=True)

    class Meta:
        model = EsquemaSalarial
        fields = '__all__'


class EsquemaSalarialViewSet(CatalogoViewSet):
    serializer_class = EsquemaSalarialSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('activo', 'base_calculo')


class ContratoSerializer(RegistroSerializer):
    class Meta:
        model = ContratoEmpleado
        fields = '__all__'


class HistorialSalarialSerializer(RegistroSerializer):
    class Meta:
        model = HistorialSalarial
        fields = '__all__'


def _motivo(request):
    motivo = str(request.data.get('motivo', '')).strip()
    if not motivo:
        raise ValidationError({'motivo': 'Indicá el motivo.'})
    return motivo[:250]


class _ConEstados(RegistroViewSet):
    """Acciones de cambio de estado con auditoría y errores legibles."""

    permite_borrar = False
    estado_editable = None

    def perform_update(self, serializer):
        if serializer.instance.estado != self.estado_editable:
            raise ValidationError({'detail': f'Ya no se puede editar (está {serializer.instance.get_estado_display().lower()}).'})
        super().perform_update(serializer)

    def _cambiar_estado(self, request, descripcion, operacion, accion=EventoAuditoria.ACCION):
        objeto = self.get_object()
        antes = auditoria.instantanea(objeto)
        try:
            with transaction.atomic():
                operacion(objeto)
                objeto.refresh_from_db()
                anteriores, nuevos = auditoria.diferencias(antes, auditoria.instantanea(objeto))
                auditoria.registrar(request.user, accion, objeto, antes=anteriores, despues=nuevos,
                                    descripcion=descripcion, request=request)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        return Response(self.get_serializer(objeto).data)


class ContratoViewSet(_ConEstados):
    serializer_class = ContratoSerializer
    search_fields = ['numero', 'empleado__codigo', 'empleado__primer_apellido', 'empleado__primer_nombre']
    filtros_exactos = ('empleado', 'estado', 'tipo_contrato')
    campo_fecha = 'fecha_inicio'
    estado_editable = ContratoEmpleado.BORRADOR
    permisos_acciones = {a: 'contratos.gestionar_estado_contrato' for a in ('activar', 'finalizar', 'anular')}

    @action(detail=True, methods=['post'])
    def activar(self, request, pk=None):
        return self._cambiar_estado(request, 'Contrato activado (vigente).', lambda c: c.activar(request.user))

    @action(detail=True, methods=['post'])
    def finalizar(self, request, pk=None):
        fecha = serializers.DateField().to_internal_value(request.data.get('fecha_fin') or '')
        motivo = _motivo(request)
        return self._cambiar_estado(request, f'Contrato finalizado: {motivo}',
                                    lambda c: c.finalizar(request.user, fecha, motivo))

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        motivo = _motivo(request)
        return self._cambiar_estado(request, f'Contrato anulado: {motivo}', lambda c: c.anular(request.user, motivo))


class HistorialSalarialViewSet(_ConEstados):
    serializer_class = HistorialSalarialSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'empleado__primer_nombre', 'motivo']
    filtros_exactos = ('empleado', 'contrato', 'estado')
    campo_fecha = 'vigente_desde'
    estado_editable = HistorialSalarial.PENDIENTE
    permisos_acciones = {a: 'contratos.aprobar_salario' for a in ('aprobar', 'rechazar')}

    def get_queryset(self):
        qs = super().get_queryset()
        # El empleado ve solo los sueldos que rigen o rigieron (no los pendientes ni rechazados).
        if not (alcance.es_plataforma(self.request.user) or alcance.tiene_alcance_empresa(self.request.user)):
            qs = qs.filter(estado=HistorialSalarial.APROBADO)
        return qs

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        return self._cambiar_estado(request, 'Cambio salarial aprobado.', lambda s: s.aprobar(request.user))

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        motivo = _motivo(request)
        return self._cambiar_estado(request, f'Cambio salarial rechazado: {motivo}', lambda s: s.anular(request.user, motivo))
