"""API de la importación de marcaciones CSV (fase 5).

- Relojes externos, códigos de reloj por empleado y perfiles de importación.
- Importaciones (lotes): `vista_previa` (sin guardar nada), alta (valida y
  deja en revisión), `confirmar` (crea las marcas), `cancelar`, `revertir`
  (anula las marcas, con motivo) y `errores` (descarga CSV/XLSX).
- Filas de un lote, para revisar el resultado de cada una."""
from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.http import HttpResponse
from django.utils.http import content_disposition_header
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from asistencia import importacion
from asistencia.models import FilaImportacion, LoteImportacion, MapeoEmpleadoReloj, PerfilImportacion, RelojExterno
from core import alcance, auditoria
from core.api.base import RegistroSerializer, RegistroViewSet, a_error_drf
from core.models import EventoAuditoria


class RelojExternoSerializer(RegistroSerializer):
    class Meta:
        model = RelojExterno
        fields = '__all__'


class RelojExternoViewSet(RegistroViewSet):
    serializer_class = RelojExternoSerializer
    search_fields = ['codigo', 'nombre', 'fabricante', 'numero_serie']
    filtros_exactos = ('activo',)
    permite_borrar = False


class MapeoSerializer(RegistroSerializer):
    class Meta:
        model = MapeoEmpleadoReloj
        fields = '__all__'


class MapeoViewSet(RegistroViewSet):
    serializer_class = MapeoSerializer
    search_fields = ['codigo_en_reloj', 'empleado__codigo', 'empleado__primer_apellido', 'empleado__primer_nombre']
    filtros_exactos = ('reloj', 'empleado')


class PerfilImportacionSerializer(RegistroSerializer):
    class Meta:
        model = PerfilImportacion
        fields = '__all__'


class PerfilImportacionViewSet(RegistroViewSet):
    serializer_class = PerfilImportacionSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('activo', 'modo')
    permite_borrar = False


class LoteSerializer(RegistroSerializer):
    class Meta:
        model = LoteImportacion
        exclude = ['archivo', 'sha256']


class FilaSerializer(RegistroSerializer):
    class Meta:
        model = FilaImportacion
        fields = '__all__'


class FilaViewSet(RegistroViewSet, viewsets.ReadOnlyModelViewSet):
    serializer_class = FilaSerializer
    filtros_exactos = ('lote', 'estado')
    search_fields = ['codigo_en_archivo', 'mensaje']
    ordering = ['numero_fila']
    http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        return super().get_queryset().order_by('numero_fila')


def _fecha(valor):
    if not valor:
        return None
    try:
        return serializers.DateField().to_internal_value(valor)
    except serializers.ValidationError:
        raise ValidationError({'periodo_desde': 'Fecha inválida (AAAA-MM-DD).'})


class ImportacionViewSet(RegistroViewSet):
    """Lotes de importación. El alta recibe el archivo (multipart) y lo valida
    contra el perfil; las marcas se crean recién con `confirmar`."""

    serializer_class = LoteSerializer
    search_fields = ['nombre_archivo', 'notas']
    filtros_exactos = ('estado', 'perfil', 'reloj')
    campo_fecha = 'creado__date'
    permite_borrar = False
    http_method_names = ['get', 'post', 'head', 'options']
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permisos_acciones = {
        'vista_previa': 'asistencia.add_loteimportacion',
        'cancelar': 'asistencia.add_loteimportacion',
        'confirmar': 'asistencia.confirmar_importacion',
        'revertir': 'asistencia.revertir_importacion',
        'errores': 'asistencia.view_loteimportacion',
    }

    def _empresa(self):
        empresa = alcance.empresa_de(self.request.user)
        if empresa is None:
            raise ValidationError({'detail': 'Las importaciones las hace un usuario de la empresa.'})
        return empresa

    def _perfil(self, empresa):
        perfil = PerfilImportacion.objects.filter(empresa=empresa, pk=self.request.data.get('perfil') or 0).first()
        if perfil is None:
            raise ValidationError({'perfil': 'Elegí un perfil de importación de tu empresa.'})
        return perfil

    @action(detail=False, methods=['post'])
    def vista_previa(self, request):
        """Las primeras filas del archivo tal cual (no guarda nada). Toma el
        separador, la codificación y el encabezado del perfil, o los que se
        manden para probar antes de crear el perfil."""
        archivo = request.FILES.get('archivo')
        if archivo is None:
            raise ValidationError({'archivo': 'Elegí el archivo CSV.'})
        perfil = None
        if request.data.get('perfil'):
            perfil = self._perfil(self._empresa())
        separador = request.data.get('separador') or (perfil.separador if perfil else ';')
        if separador == 'tab':
            separador = '\t'
        codificacion = request.data.get('codificacion') or (perfil.codificacion if perfil else 'utf-8')
        encabezado = request.data.get('tiene_encabezado')
        tiene_encabezado = (str(encabezado).lower() in ('true', '1')) if encabezado not in (None, '') else (
            perfil.tiene_encabezado if perfil else True)
        try:
            return Response(importacion.vista_previa(archivo, separador, codificacion, tiene_encabezado))
        except ValidationErrorDjango as e:
            raise a_error_drf(e)

    def create(self, request, *args, **kwargs):
        empresa = self._empresa()
        archivo = request.FILES.get('archivo')
        if archivo is None:
            raise ValidationError({'archivo': 'Elegí el archivo CSV.'})
        perfil = self._perfil(empresa)
        reloj = None
        if request.data.get('reloj'):
            reloj = RelojExterno.objects.filter(empresa=empresa, pk=request.data.get('reloj')).first()
            if reloj is None:
                raise ValidationError({'reloj': 'Elegí un reloj de tu empresa.'})
        try:
            lote = importacion.crear_lote(request.user, empresa, archivo, perfil, reloj,
                                          _fecha(request.data.get('periodo_desde')), _fecha(request.data.get('periodo_hasta')),
                                          str(request.data.get('notas', ''))[:2000])
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ALTA, lote, request=request,
                            descripcion=f'Archivo "{lote.nombre_archivo}" validado: {lote.aceptadas} válidas, '
                                        f'{lote.rechazadas} rechazadas, {lote.duplicadas} duplicadas (perfil v{lote.perfil_version}).')
        return Response(self.get_serializer(lote).data, status=status.HTTP_201_CREATED)

    def _accion(self, request, funcion, descripcion, accion=EventoAuditoria.ACCION):
        lote = self.get_object()
        try:
            resultado = funcion(lote)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        lote.refresh_from_db()
        auditoria.registrar(request.user, accion, lote, request=request, descripcion=descripcion(lote, resultado))
        return Response(self.get_serializer(lote).data)

    @action(detail=True, methods=['post'])
    def confirmar(self, request, pk=None):
        return self._accion(request, lambda l: importacion.confirmar(l, request.user),
                            lambda l, n: f'Importación confirmada: {n} marcas creadas.')

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        return self._accion(request, lambda l: importacion.cancelar(l, request.user),
                            lambda l, n: 'Importación cancelada sin confirmar.')

    @action(detail=True, methods=['post'])
    def revertir(self, request, pk=None):
        motivo = str(request.data.get('motivo', '')).strip()
        if not motivo:
            raise ValidationError({'motivo': 'Indicá el motivo de la reversión.'})
        return self._accion(request, lambda l: importacion.revertir(l, request.user, motivo),
                            lambda l, n: f'Importación revertida ({n} marcas anuladas): {motivo}', EventoAuditoria.BAJA)

    @action(detail=True, methods=['get'])
    def errores(self, request, pk=None):
        """`?formato=csv|xlsx`: las filas que no se importaron, con fila, dato y motivo."""
        lote = self.get_object()
        contenido, tipo, extension = importacion.exportar_errores(lote, request.query_params.get('formato', 'csv'))
        respuesta = HttpResponse(contenido, content_type=tipo)
        respuesta['Content-Disposition'] = content_disposition_header(True, f'errores-lote-{lote.pk}.{extension}')
        return respuesta
