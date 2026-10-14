"""API de reglas legales (fase 8).

- `reglas-legales`: conjuntos con sus parámetros y regímenes (filas anidadas,
  editables solo en borrador). Acciones: `revisar`, `volver_a_borrador`,
  `aprobar` (persona distinta de quien revisó), `nueva_version` (copia como
  borrador), `retirar` (con motivo). Los globales solo los toca la plataforma.
- `reglas-legales/vigentes/?fecha=`: los parámetros que valen esa fecha para
  la empresa del usuario, con su conjunto y su estado (`simulacion=true`
  incluye borradores, con advertencia)."""
from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core import alcance, auditoria
from core.api.base import CatalogoViewSet, ConAnidadosSerializer, a_error_drf
from core.models import EventoAuditoria
from legal import servicios
from legal.models import ConjuntoReglas, ParametroLegal, RegimenSeguridadSocial


class ParametroSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParametroLegal
        fields = ['id', 'codigo', 'nombre', 'valor_numerico', 'valor_texto', 'valor_json', 'unidad', 'vigente_desde',
                  'vigente_hasta', 'referencia_fuente']


class RegimenSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegimenSeguridadSocial
        fields = ['id', 'codigo', 'nombre', 'tasa_trabajador', 'tasa_patronal', 'base', 'referencia_fuente']


class ConjuntoSerializer(ConAnidadosSerializer):
    parametros = ParametroSerializer(many=True, required=False)
    regimenes = RegimenSerializer(many=True, required=False)
    anidados = {'parametros': 'conjunto', 'regimenes': 'conjunto'}
    es_global = serializers.BooleanField(read_only=True)
    editable = serializers.SerializerMethodField()

    class Meta:
        model = ConjuntoReglas
        fields = '__all__'

    def get_editable(self, conjunto):
        usuario = getattr(self.context.get('request'), 'user', None)
        return conjunto.editable and (not conjunto.es_global or alcance.es_plataforma(usuario))

    def validar_anidados(self, nombre, instancias):
        if nombre == 'parametros':
            vistos = {}
            for p in instancias:
                for otro in vistos.get(p.codigo, []):
                    if (p.vigente_hasta is None or otro.vigente_desde is None or otro.vigente_desde <= p.vigente_hasta) and \
                            (otro.vigente_hasta is None or p.vigente_desde is None or p.vigente_desde <= otro.vigente_hasta):
                        raise ValidationErrorDjango(f'{p.codigo} está repetido con vigencias que se superponen.')
                vistos.setdefault(p.codigo, []).append(p)
        else:
            codigos = [r.codigo for r in instancias]
            repetidos = {c for c in codigos if codigos.count(c) > 1}
            if repetidos:
                raise ValidationErrorDjango(f'Régimen repetido: {", ".join(sorted(repetidos))}.')


class ConjuntoViewSet(CatalogoViewSet):
    serializer_class = ConjuntoSerializer
    search_fields = ['codigo', 'nombre', 'fuente_nombre', 'fuente_numero']
    filtros_exactos = ('estado', 'codigo')
    permite_borrar = False
    permisos_acciones = {
        'revisar': 'legal.revisar_reglas_legales', 'volver_a_borrador': 'legal.revisar_reglas_legales',
        'aprobar': 'legal.aprobar_reglas_legales', 'retirar': 'legal.aprobar_reglas_legales',
        'nueva_version': 'legal.add_conjuntoreglas', 'vigentes': 'legal.view_conjuntoreglas',
    }

    def get_queryset(self):
        return super().get_queryset().prefetch_related('parametros', 'regimenes')

    def perform_update(self, serializer):
        if not serializer.instance.editable:
            raise ValidationError({'detail': 'Solo se edita un borrador. Para cambiar uno revisado, volvelo a borrador; '
                                             'para uno aprobado, creá una versión nueva.'})
        super().perform_update(serializer)

    def _accion(self, request, funcion, descripcion):
        conjunto = self.get_object()
        self._solo_propios(conjunto)
        try:
            resultado = funcion(conjunto)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        conjunto = resultado[0] if isinstance(resultado, tuple) else resultado
        auditoria.registrar(request.user, EventoAuditoria.ACCION, conjunto, request=request,
                            descripcion=descripcion(resultado) if callable(descripcion) else descripcion)
        conjunto = self.get_queryset().get(pk=conjunto.pk)
        return Response(self.get_serializer(conjunto).data)

    @action(detail=True, methods=['post'])
    def revisar(self, request, pk=None):
        return self._accion(request, lambda c: servicios.revisar(c, request.user), 'Reglas legales revisadas.')

    @action(detail=True, methods=['post'])
    def volver_a_borrador(self, request, pk=None):
        return self._accion(request, lambda c: servicios.volver_a_borrador(c, request.user), 'Reglas legales vueltas a borrador.')

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        def descripcion(resultado):
            cerradas = resultado[1]
            extra = f' Se cerró la vigencia de: {", ".join(str(c) for c in cerradas)}.' if cerradas else ''
            return 'Reglas legales aprobadas.' + extra
        return self._accion(request, lambda c: servicios.aprobar(c, request.user), descripcion)

    @action(detail=True, methods=['post'])
    def retirar(self, request, pk=None):
        motivo = str(request.data.get('motivo', '')).strip()
        if not motivo:
            raise ValidationError({'motivo': 'Indicá el motivo.'})
        return self._accion(request, lambda c: servicios.retirar(c, request.user, motivo), f'Reglas legales retiradas: {motivo}')

    @action(detail=True, methods=['post'])
    def nueva_version(self, request, pk=None):
        """`{"vigente_desde": "AAAA-MM-DD"}`: borrador nuevo copiado de este."""
        conjunto = self.get_object()
        self._solo_propios(conjunto)
        try:
            desde = serializers.DateField().to_internal_value(request.data.get('vigente_desde'))
        except serializers.ValidationError:
            raise ValidationError({'vigente_desde': 'Indicá desde cuándo vale (AAAA-MM-DD).'})
        try:
            nuevo = servicios.nueva_version(conjunto, request.user, desde)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ALTA, nuevo, request=request,
                            descripcion=f'Versión nueva de "{conjunto}".')
        return Response(self.get_serializer(self.get_queryset().get(pk=nuevo.pk)).data, status=201)

    @action(detail=False, methods=['get'])
    def vigentes(self, request):
        """`?fecha=AAAA-MM-DD&simulacion=true`: parámetros resueltos para la empresa del usuario."""
        try:
            fecha = serializers.DateField().to_internal_value(request.query_params['fecha']) \
                if request.query_params.get('fecha') else timezone.localdate()
        except serializers.ValidationError:
            raise ValidationError({'fecha': 'Fecha inválida (AAAA-MM-DD).'})
        simulacion = request.query_params.get('simulacion') in ('1', 'true')
        empresa = alcance.empresa_de(request.user)
        if empresa is None and not alcance.es_plataforma(request.user):
            raise PermissionDenied('Sin empresa.')
        resultado = servicios.vigentes(empresa, fecha, simulacion)
        resultado.pop('variables')
        return Response({'fecha': fecha, 'simulacion': simulacion, **resultado})
