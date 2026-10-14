"""API de las planillas MTESS / IPS (fase 11).

`POST` crea y arma la planilla; `preparar` la vuelve a armar (si no se
presentó); `exportar?formato=csv|xlsx`; `presentada` (con el número de
comprobante), `rechazada` (con el motivo) y `anular`."""
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core import auditoria, exportar
from core.api.base import RegistroSerializer, RegistroViewSet
from core.models import EventoAuditoria
from cumplimiento import servicios
from cumplimiento.models import LineaPresentacion, PresentacionOficial


class PresentacionSerializer(RegistroSerializer):
    class Meta:
        model = PresentacionOficial
        fields = '__all__'


class LineaSerializer(serializers.ModelSerializer):
    empleado_texto = serializers.CharField(source='empleado.__str__', read_only=True)

    class Meta:
        model = LineaPresentacion
        fields = ['id', 'empleado', 'empleado_texto', 'datos', 'valida', 'errores', 'advertencias']


class PresentacionViewSet(RegistroViewSet):
    serializer_class = PresentacionSerializer
    search_fields = ['numero_comprobante']
    filtros_exactos = ('tipo', 'estado')
    campo_fecha = 'periodo_desde'
    permite_borrar = False
    http_method_names = ['get', 'post', 'head', 'options']
    permisos_acciones = {'preparar': 'cumplimiento.preparar_presentacion', 'exportar': 'cumplimiento.preparar_presentacion',
                         'presentada': 'cumplimiento.confirmar_presentacion', 'rechazada': 'cumplimiento.confirmar_presentacion',
                         'anular': 'cumplimiento.confirmar_presentacion'}

    def perform_create(self, serializer):
        super().perform_create(serializer)
        servicios.preparar(serializer.instance)

    def retrieve(self, request, *args, **kwargs):
        presentacion = self.get_object()
        datos = self.get_serializer(presentacion).data
        datos['columnas'] = [{'campo': c, 'etiqueta': e} for c, e in servicios.COLUMNAS[presentacion.tipo]]
        datos['lineas'] = LineaSerializer(presentacion.lineas.select_related('empleado'), many=True).data
        return Response(datos)

    def _cambiar(self, request, estado, descripcion, **campos):
        presentacion = self.get_object()
        if presentacion.estado in (PresentacionOficial.PRESENTADA, PresentacionOficial.ANULADA) and estado != PresentacionOficial.RECHAZADA:
            raise ValidationError({'detail': f'La planilla ya está {presentacion.get_estado_display().lower()}.'})
        presentacion.estado = estado
        for campo, valor in campos.items():
            setattr(presentacion, campo, valor)
        presentacion.modificado_por = request.user
        presentacion.save()
        auditoria.registrar(request.user, EventoAuditoria.ACCION, presentacion, request=request, descripcion=descripcion)
        return Response(self.get_serializer(presentacion).data)

    def _texto(self, request, campo='motivo'):
        texto = str(request.data.get(campo) or request.data.get('motivo') or '').strip()
        if not texto:
            raise ValidationError({'motivo': 'Completá el dato.'})
        return texto[:250]

    @action(detail=True, methods=['post'])
    def preparar(self, request, pk=None):
        presentacion = self.get_object()
        if presentacion.estado not in (PresentacionOficial.PREPARADA, PresentacionOficial.RECHAZADA):
            raise ValidationError({'detail': 'Ya se presentó o se anuló: prepará una nueva.'})
        servicios.preparar(presentacion)
        presentacion.estado = PresentacionOficial.PREPARADA
        presentacion.save(update_fields=['estado'])
        auditoria.registrar(request.user, EventoAuditoria.ACCION, presentacion, request=request, descripcion='Planilla preparada de nuevo.')
        return Response(self.get_serializer(presentacion).data)

    @action(detail=True, methods=['get'])
    def exportar(self, request, pk=None):
        presentacion = self.get_object()
        formato = 'xlsx' if request.query_params.get('formato') == 'xlsx' else 'csv'
        encabezado, filas = servicios.filas_para_exportar(presentacion)
        auditoria.registrar(request.user, EventoAuditoria.ACCION, presentacion, request=request, descripcion=f'Planilla exportada ({formato}).')
        return exportar.respuesta(encabezado, filas, formato, f'{presentacion.tipo}_{presentacion.periodo_desde:%Y%m}', 'Planilla')

    @action(detail=True, methods=['post'])
    def presentada(self, request, pk=None):
        presentacion = self.get_object()
        if presentacion.lineas_con_errores:
            raise ValidationError({'detail': f'Tiene {presentacion.lineas_con_errores} línea(s) con errores: corregí el legajo y prepará de nuevo.'})
        comprobante = self._texto(request, 'numero_comprobante')
        return self._cambiar(request, PresentacionOficial.PRESENTADA, f'Planilla presentada: comprobante {comprobante}.',
                             numero_comprobante=comprobante, presentado_por=request.user, presentado_en=timezone.now())

    @action(detail=True, methods=['post'])
    def rechazada(self, request, pk=None):
        motivo = self._texto(request)
        return self._cambiar(request, PresentacionOficial.RECHAZADA, f'Planilla rechazada: {motivo}', observaciones=motivo)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        motivo = self._texto(request)
        return self._cambiar(request, PresentacionOficial.ANULADA, f'Planilla anulada: {motivo}', observaciones=motivo)
