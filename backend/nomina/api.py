"""API de conceptos salariales (fase 8).

- `conceptos-nomina`: catálogo (globales + propios).
- `reglas-concepto`: fórmulas con vigencia; `probar` (con valores de ejemplo
  o los que se manden), `aprobar`, `retirar`. Aprobada no se edita.
- `variables-nomina`: las variables de la liquidación que pueden usar las fórmulas.
- `conceptos-fijos`: conceptos recurrentes de cada empleado; `aprobar` y
  `finalizar` (con fecha y motivo). Aprobado, no se edita: se finaliza y se
  carga otro."""
from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import alcance, auditoria
from core.api.base import CatalogoViewSet, RegistroSerializer, RegistroViewSet, a_error_drf
from core.models import EventoAuditoria
from nomina import servicios, variables
from nomina.models import ConceptoNomina, ConceptoRecurrente, ReglaConcepto


class ConceptoSerializer(RegistroSerializer):
    es_global = serializers.BooleanField(read_only=True)

    class Meta:
        model = ConceptoNomina
        fields = '__all__'


class ConceptoViewSet(CatalogoViewSet):
    serializer_class = ConceptoSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('tipo', 'activo', 'tipo_calculo')
    permite_borrar = False


class ReglaSerializer(RegistroSerializer):
    es_global = serializers.BooleanField(read_only=True)
    editable = serializers.SerializerMethodField()
    variables_usadas = serializers.SerializerMethodField()

    class Meta:
        model = ReglaConcepto
        fields = '__all__'

    def get_editable(self, regla):
        usuario = getattr(self.context.get('request'), 'user', None)
        return regla.editable and (not regla.es_global or alcance.es_plataforma(usuario))

    def get_variables_usadas(self, regla):
        try:
            return ', '.join(sorted(regla.variables()))
        except Exception:  # noqa: BLE001 — una fórmula vieja inválida no rompe el listado
            return ''


class ReglaViewSet(CatalogoViewSet):
    serializer_class = ReglaSerializer
    search_fields = ['concepto__codigo', 'concepto__nombre', 'expresion']
    filtros_exactos = ('concepto', 'estado')
    campo_fecha = 'vigente_desde'
    permite_borrar = False
    permisos_acciones = {'probar': 'nomina.view_reglaconcepto', 'aprobar': 'nomina.aprobar_regla_concepto',
                         'retirar': 'nomina.aprobar_regla_concepto'}

    def perform_update(self, serializer):
        if not serializer.instance.editable:
            raise ValidationError({'detail': 'Una regla aprobada no se edita: retirala y cargá otra con su vigencia.'})
        super().perform_update(serializer)

    def _accion(self, request, funcion, descripcion):
        regla = self.get_object()
        self._solo_propios(regla)
        try:
            regla = funcion(regla)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ACCION, regla, request=request, descripcion=descripcion)
        return Response(self.get_serializer(regla).data)

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        return self._accion(request, lambda r: servicios.aprobar_regla(r, request.user), 'Regla de cálculo aprobada.')

    @action(detail=True, methods=['post'])
    def retirar(self, request, pk=None):
        return self._accion(request, lambda r: servicios.retirar_regla(r, request.user), 'Regla de cálculo retirada.')

    @action(detail=True, methods=['post'])
    def probar(self, request, pk=None):
        """`{"fecha"?, "variables"?: {"SALARIO_BASE": 4000000}}`: calcula con ejemplos, sin guardar nada."""
        regla = self.get_object()
        try:
            fecha = serializers.DateField().to_internal_value(request.data['fecha']) if request.data.get('fecha') \
                else max(regla.vigente_desde, timezone.localdate()) if regla.vigente_hasta is None \
                else regla.vigente_desde
        except serializers.ValidationError:
            raise ValidationError({'fecha': 'Fecha inválida (AAAA-MM-DD).'})
        propias = request.data.get('variables') or {}
        if not isinstance(propias, dict):
            raise ValidationError({'variables': 'Mandá un objeto {VARIABLE: valor}.'})
        try:
            resultado = servicios.probar(regla, alcance.empresa_de(request.user) or regla.empresa, fecha, propias)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        return Response({**resultado, 'fecha': fecha})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def variables_nomina(request):
    """Variables de la liquidación disponibles para las fórmulas (con su ejemplo)."""
    if not alcance.tiene_permiso(request.user, 'nomina.view_reglaconcepto'):
        return Response({'detail': 'Sin permiso.'}, status=403)
    return Response([{'codigo': c, 'descripcion': d, 'ejemplo': e} for c, (d, e) in variables.VARIABLES.items()])


class RecurrenteSerializer(RegistroSerializer):
    aprobado = serializers.BooleanField(read_only=True)

    class Meta:
        model = ConceptoRecurrente
        fields = '__all__'


class RecurrenteViewSet(RegistroViewSet):
    serializer_class = RecurrenteSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'concepto__codigo', 'concepto__nombre', 'motivo']
    filtros_exactos = ('empleado', 'concepto', 'activo')
    campo_fecha = 'vigente_desde'
    permite_borrar = False
    permisos_acciones = {'aprobar': 'nomina.aprobar_concepto_recurrente', 'finalizar': 'nomina.change_conceptorecurrente'}

    def perform_create(self, serializer):
        super().perform_create(serializer)
        servicios.recurrente_al_crear(serializer.instance, self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.aprobado or not serializer.instance.activo:
            raise ValidationError({'detail': 'Aprobado o finalizado no se edita: finalizalo y cargá uno nuevo.'})
        super().perform_update(serializer)

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        recurrente = self.get_object()
        try:
            servicios.aprobar_recurrente(recurrente, request.user)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ACCION, recurrente, request=request, descripcion='Concepto fijo aprobado.')
        return Response(self.get_serializer(recurrente).data)

    @action(detail=True, methods=['post'])
    def finalizar(self, request, pk=None):
        """`{"vigente_hasta": "AAAA-MM-DD", "motivo"}`."""
        recurrente = self.get_object()
        motivo = str(request.data.get('motivo', '')).strip()
        if not motivo:
            raise ValidationError({'motivo': 'Indicá el motivo.'})
        try:
            fecha = serializers.DateField().to_internal_value(request.data.get('vigente_hasta'))
        except serializers.ValidationError:
            raise ValidationError({'vigente_hasta': 'Indicá hasta cuándo se aplica (AAAA-MM-DD).'})
        try:
            servicios.finalizar_recurrente(recurrente, request.user, fecha, motivo)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ACCION, recurrente, request=request,
                            descripcion=f'Concepto fijo finalizado el {fecha:%d/%m/%Y}: {motivo}')
        return Response(self.get_serializer(recurrente).data)
