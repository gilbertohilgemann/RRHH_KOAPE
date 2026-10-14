"""API de la liquidación de nómina (fase 10).

- `periodos-nomina`: alta y edición mientras están abiertos.
- `corridas-nomina`: `POST {"periodo"}` crea y calcula; acciones `calcular`,
  `revisar`, `aprobar`, `cerrar`, `anular`, `rectificar`, `emitir_recibos`,
  `publicar_recibos`, `registrar_pagos`. Sin `ver_costo_patronal`, no se ven
  los aportes del empleador ni el costo.
- `liquidaciones-nomina`: cada empleado de una corrida con sus líneas explicadas.
- `recibos`: el empleado ve solo los suyos publicados (sin el costo del
  empleador); `anular` con motivo.
- `pagos-nomina`: `confirmar`, `anular`.
- `costo-patronal/`: costo del empleador por centro de costo, departamento o sucursal."""
from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import alcance, auditoria
from core.api.base import RegistroSerializer, RegistroViewSet, a_error_drf
from core.models import EventoAuditoria
from nomina import liquidar
from nomina.models import (AsignacionCostoPatronal, ConceptoNomina, CorridaNomina, LineaNomina, LiquidacionEmpleado,
                           LiquidacionFinal, PagoNomina, PeriodoNomina, ReciboSueldo)

CAMPOS_COSTO = ('total_aportes_patronales', 'total_otros_costos', 'total_costo_empleador', 'aportes_patronales', 'otros_costos',
                'costo_empleador', 'provision_aguinaldo')


def _ve_costo(request):
    return alcance.tiene_permiso(request.user, 'nomina.ver_costo_patronal')


class _SinCosto(RegistroSerializer):
    """Quita el costo del empleador a quien no tiene permiso de verlo."""

    def to_representation(self, instancia):
        datos = super().to_representation(instancia)
        request = self.context.get('request')
        if request is not None and not _ve_costo(request):
            for campo in CAMPOS_COSTO:
                datos.pop(campo, None)
        return datos


def _motivo(request):
    motivo = str(request.data.get('motivo', '')).strip()
    if not motivo:
        raise ValidationError({'motivo': 'Indicá el motivo.'})
    return motivo


def _fecha(request, campo, por_defecto=None):
    valor = request.data.get(campo)
    if not valor:
        return por_defecto
    try:
        return serializers.DateField().to_internal_value(valor)
    except serializers.ValidationError:
        raise ValidationError({campo: 'Fecha inválida (AAAA-MM-DD).'})


# ------------------------------------------------------------------- períodos
class PeriodoSerializer(RegistroSerializer):
    class Meta:
        model = PeriodoNomina
        fields = '__all__'


class PeriodoViewSet(RegistroViewSet):
    serializer_class = PeriodoSerializer
    search_fields = ['codigo']
    filtros_exactos = ('estado', 'tipo')
    campo_fecha = 'fecha_desde'
    permite_borrar = False

    def perform_update(self, serializer):
        if serializer.instance.estado != PeriodoNomina.ABIERTO:
            raise ValidationError({'detail': 'Un período cerrado no se modifica.'})
        if serializer.instance.corridas.exclude(estado=CorridaNomina.ANULADA).exists() and (
                serializer.validated_data.get('fecha_desde', serializer.instance.fecha_desde) != serializer.instance.fecha_desde
                or serializer.validated_data.get('fecha_hasta', serializer.instance.fecha_hasta) != serializer.instance.fecha_hasta):
            raise ValidationError({'fecha_desde': 'El período ya tiene una liquidación: no se cambian sus fechas (anulala antes).'})
        super().perform_update(serializer)


# -------------------------------------------------------------------- corridas
class CorridaSerializer(_SinCosto):
    editable = serializers.BooleanField(read_only=True)
    es_rectificacion = serializers.BooleanField(read_only=True)

    class Meta:
        model = CorridaNomina
        fields = '__all__'


class CorridaViewSet(RegistroViewSet):
    serializer_class = CorridaSerializer
    search_fields = ['periodo__codigo']
    filtros_exactos = ('periodo', 'estado', 'tipo')
    campo_fecha = 'periodo__fecha_desde'
    permite_borrar = False
    http_method_names = ['get', 'post', 'head', 'options']
    permisos_acciones = {
        'calcular': 'nomina.calcular_nomina', 'revisar': 'nomina.calcular_nomina', 'aprobar': 'nomina.aprobar_nomina',
        'cerrar': 'nomina.cerrar_nomina', 'anular': 'nomina.aprobar_nomina', 'rectificar': 'nomina.rectificar_nomina',
        'emitir_recibos': 'nomina.emitir_recibos', 'publicar_recibos': 'nomina.emitir_recibos',
        'registrar_pagos': 'nomina.registrar_pagos',
    }

    def create(self, request, *args, **kwargs):
        if not alcance.tiene_permiso(request.user, 'nomina.calcular_nomina'):
            return Response({'detail': 'No tenés permiso para calcular nóminas.'}, status=403)
        periodo = alcance.filtrar(PeriodoNomina.objects.all(), request.user).filter(pk=request.data.get('periodo') or 0).first()
        if periodo is None:
            raise ValidationError({'periodo': 'Elegí un período.'})
        try:
            corrida = liquidar.crear(periodo, request.user)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ALTA, corrida, request=request,
                            descripcion=f'Liquidación calculada: {corrida.cantidad_empleados} empleados.')
        return Response(self.get_serializer(corrida).data, status=201)

    def _accion(self, request, funcion, descripcion):
        corrida = self.get_object()
        try:
            resultado = funcion(corrida)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        texto = descripcion(resultado) if callable(descripcion) else descripcion
        objetivo = resultado if isinstance(resultado, CorridaNomina) else corrida
        auditoria.registrar(request.user, EventoAuditoria.ACCION, objetivo, request=request, descripcion=texto)
        objetivo.refresh_from_db()
        return Response(self.get_serializer(objetivo).data)

    @action(detail=False, methods=['post'])
    def aguinaldo(self, request):
        """`{"anio"}`: crea y calcula la liquidación del aguinaldo de ese año."""
        if not alcance.tiene_permiso(request.user, 'nomina.calcular_nomina'):
            return Response({'detail': 'No tenés permiso para calcular nóminas.'}, status=403)
        empresa = alcance.empresa_de(request.user)
        try:
            anio = int(request.data.get('anio'))
        except (TypeError, ValueError):
            raise ValidationError({'anio': 'Indicá el año.'})
        if empresa is None or not 2000 <= anio <= timezone.localdate().year + 1:
            raise ValidationError({'anio': 'Año inválido (o usuario sin empresa).'})
        try:
            corrida = liquidar.crear_aguinaldo(empresa, anio, request.user)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ALTA, corrida, request=request,
                            descripcion=f'Aguinaldo {anio} calculado: {corrida.cantidad_empleados} empleados.')
        return Response(self.get_serializer(corrida).data, status=201)

    @action(detail=True, methods=['post'])
    def calcular(self, request, pk=None):
        return self._accion(request, lambda c: liquidar.recalcular(c, request.user),
                            lambda c: f'Liquidación recalculada (cálculo n.º {c.version_calculo}).')

    @action(detail=True, methods=['post'])
    def revisar(self, request, pk=None):
        return self._accion(request, lambda c: liquidar.revisar(c, request.user), 'Liquidación revisada.')

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        return self._accion(request, lambda c: liquidar.aprobar(c, request.user), 'Liquidación aprobada.')

    @action(detail=True, methods=['post'])
    def cerrar(self, request, pk=None):
        return self._accion(request, lambda c: liquidar.cerrar(c, request.user), 'Liquidación cerrada: novedades y cuotas aplicadas.')

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        motivo = _motivo(request)
        return self._accion(request, lambda c: liquidar.anular(c, request.user, motivo), f'Liquidación anulada: {motivo}')

    @action(detail=True, methods=['post'])
    def rectificar(self, request, pk=None):
        motivo = _motivo(request)
        corrida = self.get_object()
        try:
            nueva = liquidar.rectificar(corrida, request.user, motivo)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ALTA, nueva, request=request,
                            descripcion=f'Rectificación de "{corrida}": {motivo}')
        return Response(self.get_serializer(nueva).data, status=201)

    @action(detail=True, methods=['post'])
    def emitir_recibos(self, request, pk=None):
        return self._accion(request, lambda c: liquidar.emitir_recibos(c, request.user),
                            lambda emitidos: f'{len(emitidos)} recibos emitidos.')

    @action(detail=True, methods=['post'])
    def publicar_recibos(self, request, pk=None):
        return self._accion(request, lambda c: liquidar.publicar_recibos(c, request.user),
                            lambda n: f'{n} recibos publicados para los empleados.')

    @action(detail=True, methods=['post'])
    def registrar_pagos(self, request, pk=None):
        """`{"fecha"?, "forma"?, "referencia"?}` (o `motivo` como referencia)."""
        fecha = _fecha(request, 'fecha', timezone.localdate())
        forma = str(request.data.get('forma') or 'transferencia')
        referencia = str(request.data.get('referencia') or request.data.get('motivo') or '')

        def descripcion(resultado):
            creados, recuperar = resultado
            extra = f' {len(recuperar)} con diferencia a recuperar (sin pago).' if recuperar else ''
            return f'{len(creados)} pagos registrados ({forma}).{extra}'
        return self._accion(request, lambda c: liquidar.registrar_pagos(c, request.user, fecha, forma, referencia), descripcion)


# ----------------------------------------------------------- liquidación final
class LiquidacionFinalSerializer(RegistroSerializer):
    corrida_estado = serializers.CharField(source='corrida.get_estado_display', read_only=True, default='')

    class Meta:
        model = LiquidacionFinal
        fields = '__all__'


class LiquidacionFinalViewSet(RegistroViewSet):
    serializer_class = LiquidacionFinalSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'motivo']
    filtros_exactos = ('empleado', 'causal')
    campo_fecha = 'fecha_egreso'
    permite_borrar = True
    permisos_acciones = {'calcular': 'nomina.calcular_nomina'}

    def perform_update(self, serializer):
        if serializer.instance.corrida_id and serializer.instance.corrida.estado != CorridaNomina.ANULADA:
            if serializer.instance.corrida.estado not in (CorridaNomina.CALCULADA, CorridaNomina.REVISADA):
                raise ValidationError({'detail': 'Ya está aprobada o cerrada: no se modifica (se rectifica su liquidación).'})
        super().perform_update(serializer)

    def destroy(self, request, *args, **kwargs):
        if self.get_object().corrida_id:
            return Response({'detail': 'Ya tiene su liquidación calculada: anulala en lugar de borrar.'}, status=409)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def calcular(self, request, pk=None):
        """Crea o recalcula su corrida; devuelve la corrida (para ir a revisarla)."""
        final = self.get_object()
        try:
            corrida = liquidar.calcular_final(final, request.user)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ACCION, final, request=request,
                            descripcion=f'Liquidación final calculada ({corrida}).')
        return Response(CorridaSerializer(corrida, context=self.get_serializer_context()).data)


# ------------------------------------------------------- liquidación por empleado
class LineaSerializer(serializers.ModelSerializer):
    tipo_texto = serializers.CharField(source='get_tipo_display', read_only=True)
    origen_texto = serializers.CharField(source='get_origen_display', read_only=True)

    class Meta:
        model = LineaNomina
        fields = ['id', 'codigo', 'nombre', 'tipo', 'tipo_texto', 'cantidad', 'tasa', 'base', 'importe', 'importe_con_signo',
                  'explicacion', 'origen', 'origen_texto', 'origen_id', 'regla', 'secuencia', 'afecta_neto']


def _lineas(liquidacion, request, para_recibo=False):
    lineas = liquidacion.lineas.all()
    if para_recibo or not _ve_costo(request):
        # El aporte del empleador no es del recibo del trabajador (ni lo ve quien no tiene permiso).
        lineas = lineas.exclude(tipo=ConceptoNomina.APORTE_PATRONAL)
    return LineaSerializer(lineas, many=True).data


class LiquidacionSerializer(_SinCosto):
    a_pagar = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = LiquidacionEmpleado
        fields = '__all__'


class LiquidacionViewSet(RegistroViewSet):
    serializer_class = LiquidacionSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'empleado__primer_nombre']
    filtros_exactos = ('corrida', 'empleado', 'estado_calculo', 'estado_pago')
    permite_borrar = False
    http_method_names = ['get', 'head', 'options']

    def retrieve(self, request, *args, **kwargs):
        liquidacion = self.get_object()
        datos = self.get_serializer(liquidacion).data
        datos['lineas'] = _lineas(liquidacion, request)
        return Response(datos)


# --------------------------------------------------------------------- recibos
class ReciboSerializer(_SinCosto):
    class Meta:
        model = ReciboSueldo
        fields = '__all__'

    def to_representation(self, recibo):
        datos = super().to_representation(recibo)
        request = self.context.get('request')
        if request is not None and not _ve_costo(request):
            datos.pop('costo_empleador', None)
        return datos


class ReciboViewSet(RegistroViewSet):
    serializer_class = ReciboSerializer
    search_fields = ['numero', 'empleado__codigo', 'empleado__primer_apellido']
    filtros_exactos = ('corrida', 'empleado', 'estado', 'publicado')
    campo_fecha = 'periodo_desde'
    permite_borrar = False
    http_method_names = ['get', 'post', 'head', 'options']
    permisos_acciones = {'anular': 'nomina.emitir_recibos'}

    def get_queryset(self):
        qs = super().get_queryset()
        usuario = self.request.user
        if not (alcance.es_plataforma(usuario) or alcance.tiene_alcance_empresa(usuario)):
            qs = qs.filter(publicado=True, estado=ReciboSueldo.EMITIDO)  # §11 bis: el empleado ve sus recibos publicados
        return qs

    def create(self, request, *args, **kwargs):
        return Response({'detail': 'Los recibos se emiten desde la liquidación cerrada.'}, status=405)

    def retrieve(self, request, *args, **kwargs):
        """El recibo para ver o imprimir: empresa, empleado, líneas y totales."""
        recibo = self.get_object()
        datos = self.get_serializer(recibo).data
        empresa, empleado, liq = recibo.empresa, recibo.empleado, recibo.liquidacion
        datos['empresa'] = {'nombre': empresa.nombre, 'razon_social': empresa.razon_social, 'ruc': empresa.ruc,
                            'numero_patronal_ips': empresa.numero_patronal_ips, 'direccion': empresa.direccion}
        datos['empleado_datos'] = {'codigo': empleado.codigo, 'nombre': str(empleado), 'documento': empleado.numero_documento,
                                   'puesto': str(empleado.puesto) if empleado.puesto_id else '',
                                   'fecha_ingreso': empleado.fecha_ingreso}
        datos['liquidacion_datos'] = {'dias_pagados': liq.dias_pagados, 'dias_trabajados': liq.dias_trabajados,
                                      'salario_base': liq.salario_base, 'neto_anterior': liq.neto_anterior}
        datos['lineas'] = _lineas(liq, request, para_recibo=True)
        return Response(datos)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        motivo = _motivo(request)
        recibo = self.get_object()
        try:
            liquidar.anular_recibo(recibo, request.user, motivo)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ACCION, recibo, request=request, descripcion=f'Recibo anulado: {motivo}')
        return Response(self.get_serializer(recibo).data)


# ----------------------------------------------------------------------- pagos
class PagoSerializer(RegistroSerializer):
    class Meta:
        model = PagoNomina
        fields = '__all__'


class PagoViewSet(RegistroViewSet):
    serializer_class = PagoSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'referencia']
    filtros_exactos = ('corrida', 'empleado', 'estado', 'forma')
    campo_fecha = 'fecha'
    permite_borrar = False
    http_method_names = ['get', 'post', 'head', 'options']
    permisos_acciones = {'confirmar': 'nomina.registrar_pagos', 'anular': 'nomina.registrar_pagos'}

    def create(self, request, *args, **kwargs):
        return Response({'detail': 'Los pagos se registran desde la liquidación cerrada.'}, status=405)

    def _accion(self, request, funcion, descripcion):
        pago = self.get_object()
        try:
            funcion(pago)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ACCION, pago, request=request, descripcion=descripcion)
        return Response(self.get_serializer(pago).data)

    @action(detail=True, methods=['post'])
    def confirmar(self, request, pk=None):
        return self._accion(request, lambda p: liquidar.confirmar_pago(p, request.user), 'Pago confirmado.')

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        motivo = _motivo(request)
        return self._accion(request, lambda p: liquidar.anular_pago(p, request.user, motivo), f'Pago anulado: {motivo}')


# -------------------------------------------------------------- costo patronal
AGRUPACIONES = {'centro_costo': ('centro_costo', 'centro_costo__nombre'), 'departamento': ('empleado__departamento', 'empleado__departamento__nombre'),
                'sucursal': ('empleado__sucursal', 'empleado__sucursal__nombre'), 'empleado': ('empleado', 'empleado__primer_apellido')}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def costo_patronal(request):
    """`?desde=&hasta=&agrupar=centro_costo|departamento|sucursal|empleado`: costo del empleador de las liquidaciones
    cerradas (sin las rectificadas). La provisión de aguinaldo va aparte y no suma al total."""
    if not _ve_costo(request):
        return Response({'detail': 'No tenés permiso para ver el costo del empleador.'}, status=403)
    agrupar = request.query_params.get('agrupar', 'centro_costo')
    if agrupar not in AGRUPACIONES:
        raise ValidationError({'agrupar': f'Usá: {", ".join(AGRUPACIONES)}.'})
    qs = alcance.filtrar(AsignacionCostoPatronal.objects.filter(corrida__rectificada=False), request.user)
    for campo, filtro in (('desde', 'periodo__fecha_desde__gte'), ('hasta', 'periodo__fecha_hasta__lte')):
        if request.query_params.get(campo):
            try:
                qs = qs.filter(**{filtro: serializers.DateField().to_internal_value(request.query_params[campo])})
            except serializers.ValidationError:
                raise ValidationError({campo: 'Fecha inválida (AAAA-MM-DD).'})
    clave, nombre = AGRUPACIONES[agrupar]
    filas = qs.values(clave, nombre).annotate(
        bruto=Sum('remuneracion_bruta'), aportes=Sum('aporte_patronal'), otros=Sum('otros_costos'), total=Sum('costo_total'),
        provision=Sum('provision_aguinaldo')).order_by(nombre)
    resultado = []
    for f in filas:
        texto = f[nombre] or 'Sin asignar'
        if agrupar == 'empleado':
            from empleados.models import Empleado
            texto = str(Empleado.objects.get(pk=f[clave]))
        resultado.append({'grupo': texto, 'bruto': f['bruto'], 'aportes_patronales': f['aportes'], 'otros_costos': f['otros'],
                          'costo_total': f['total'], 'provision_aguinaldo': f['provision']})
    totales = qs.aggregate(bruto=Sum('remuneracion_bruta'), aportes=Sum('aporte_patronal'), otros=Sum('otros_costos'),
                           total=Sum('costo_total'), provision=Sum('provision_aguinaldo'))
    return Response({'filas': resultado, 'totales': totales})
