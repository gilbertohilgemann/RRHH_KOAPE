"""API de novedades (fase 9).

- `novedades`: carga (pendiente), `aprobar`, `rechazar`, `anular`. Aprobada o
  resuelta no se edita.
- `descuentos-autorizados`: con autorización o base legal documentada;
  `finalizar` y `anular` (con motivo).
- `anticipos`: el empleado los pide para sí; `aprobar` (monto), `rechazar`,
  `pagar` (genera las cuotas), `anular`, `cancelar_saldo`.
- `prestamos`: `aprobar` (con la autorización firmada), `rechazar`,
  `desembolsar` (genera las cuotas), `anular`, `cancelar_saldo`; `plan` muestra
  las cuotas antes de desembolsar.
- `cuotas-recuperacion`: solo consulta (las descuenta la nómina, fase 10)."""
from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from core import alcance, auditoria
from core.api.base import RegistroSerializer, RegistroViewSet, a_error_drf
from core.models import EventoAuditoria
from novedades import servicios
from novedades.models import (Anticipo, CuotaRecuperacion, DescuentoAutorizado, Novedad, Prestamo, ReciboAnticipo, recibo_vigente,
                              saldo_de)


def _motivo(request):
    motivo = str(request.data.get('motivo', '')).strip()
    if not motivo:
        raise ValidationError({'motivo': 'Indicá el motivo.'})
    return motivo


class _ConAcciones(RegistroViewSet):
    permite_borrar = False

    def _ejecutar(self, request, funcion, descripcion):
        objeto = self.get_object()
        try:
            resultado = funcion(objeto)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        objeto = resultado[0] if isinstance(resultado, tuple) else resultado
        texto = descripcion(resultado) if callable(descripcion) else descripcion
        auditoria.registrar(request.user, EventoAuditoria.ACCION, objeto, request=request, descripcion=texto)
        objeto.refresh_from_db()
        return Response(self.get_serializer(objeto).data)


# ------------------------------------------------------------------ novedades
class NovedadSerializer(RegistroSerializer):
    importe = serializers.SerializerMethodField()

    class Meta:
        model = Novedad
        fields = '__all__'

    def get_importe(self, novedad):
        importe = novedad.importe()
        return None if importe is None else str(importe)


class NovedadViewSet(_ConAcciones):
    serializer_class = NovedadSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'concepto__codigo', 'concepto__nombre', 'descripcion', 'referencia']
    filtros_exactos = ('empleado', 'concepto', 'estado', 'origen')
    campo_fecha = 'periodo_desde'
    permisos_acciones = {'aprobar': 'novedades.aprobar_novedad', 'rechazar': 'novedades.aprobar_novedad',
                         'anular': 'novedades.aprobar_novedad'}

    def perform_update(self, serializer):
        if serializer.instance.estado != Novedad.PENDIENTE:
            raise ValidationError({'detail': 'Solo se modifica una novedad pendiente.'})
        super().perform_update(serializer)

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        return self._ejecutar(request, lambda n: servicios.aprobar_novedad(n, request.user), 'Novedad aprobada.')

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        motivo = _motivo(request)
        return self._ejecutar(request, lambda n: servicios.rechazar_novedad(n, request.user, motivo), f'Novedad rechazada: {motivo}')

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        motivo = _motivo(request)
        return self._ejecutar(request, lambda n: servicios.anular_novedad(n, request.user, motivo), f'Novedad anulada: {motivo}')


# --------------------------------------------------------- descuentos autorizados
class DescuentoSerializer(RegistroSerializer):
    class Meta:
        model = DescuentoAutorizado
        fields = '__all__'


class DescuentoViewSet(_ConAcciones):
    serializer_class = DescuentoSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'concepto__codigo', 'observaciones']
    filtros_exactos = ('empleado', 'estado', 'tipo')
    campo_fecha = 'fecha_desde'
    permisos_acciones = {'finalizar': 'novedades.change_descuentoautorizado', 'anular': 'novedades.change_descuentoautorizado'}

    def perform_update(self, serializer):
        if serializer.instance.estado != DescuentoAutorizado.VIGENTE:
            raise ValidationError({'detail': 'Un descuento finalizado o anulado no se modifica.'})
        super().perform_update(serializer)

    def _terminar(self, request, estado, verbo):
        motivo = _motivo(request)

        def terminar(descuento):
            if descuento.estado != DescuentoAutorizado.VIGENTE:
                raise ValidationErrorDjango('Ya no está vigente.')
            descuento.estado = estado
            descuento.motivo_fin = motivo[:250]
            if estado == DescuentoAutorizado.FINALIZADO and descuento.fecha_hasta is None:
                descuento.fecha_hasta = timezone.localdate()
            descuento.modificado_por = request.user
            descuento.save(update_fields=['estado', 'motivo_fin', 'fecha_hasta', 'modificado_por', 'modificado'])
            return descuento
        return self._ejecutar(request, terminar, f'Descuento {verbo}: {motivo}')

    @action(detail=True, methods=['post'])
    def finalizar(self, request, pk=None):
        return self._terminar(request, DescuentoAutorizado.FINALIZADO, 'finalizado')

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        return self._terminar(request, DescuentoAutorizado.ANULADO, 'anulado')


# ------------------------------------------------------- anticipos y préstamos
class _ConSaldo(RegistroSerializer):
    saldo = serializers.SerializerMethodField()

    def get_saldo(self, objeto):
        return str(saldo_de(objeto)) if objeto.pk else '0'


class AnticipoSerializer(_ConSaldo):
    class Meta:
        model = Anticipo
        fields = '__all__'


class AnticipoViewSet(_ConAcciones):
    serializer_class = AnticipoSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'motivo', 'referencia_pago']
    filtros_exactos = ('empleado', 'estado')
    campo_fecha = 'fecha'
    permisos_acciones = {'aprobar': 'novedades.aprobar_anticipo', 'rechazar': 'novedades.aprobar_anticipo',
                         'anular': 'novedades.aprobar_anticipo', 'pagar': 'novedades.pagar_anticipo',
                         'cancelar_saldo': 'novedades.pagar_anticipo', 'comprobante': 'novedades.view_reciboanticipo'}

    def perform_create(self, serializer):
        # El perfil Empleado pide solo para sí (queda solicitado).
        usuario = self.request.user
        if not (alcance.es_plataforma(usuario) or alcance.tiene_alcance_empresa(usuario)):
            propio = alcance.empleado_propio(usuario)
            if propio is None or serializer.validated_data.get('empleado') != propio:
                raise PermissionDenied('Solo podés pedirlo para vos.')
        super().perform_create(serializer)

    def perform_update(self, serializer):
        if serializer.instance.estado != Anticipo.SOLICITADO:
            raise ValidationError({'detail': 'Solo se modifica un anticipo solicitado.'})
        if not alcance.tiene_alcance_empresa(self.request.user) and not alcance.es_plataforma(self.request.user):
            raise PermissionDenied('Pedí a Recursos Humanos que lo corrija.')
        super().perform_update(serializer)

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        """`{"monto_aprobado"?}` (por defecto, lo solicitado)."""
        monto = request.data.get('monto_aprobado')
        return self._ejecutar(request, lambda a: servicios.aprobar_anticipo(a, request.user, monto),
                              lambda a: f'Anticipo aprobado por {a.monto_aprobado:,.0f}.'.replace(',', '.'))

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        motivo = _motivo(request)
        return self._ejecutar(request, lambda a: servicios.rechazar_anticipo(a, request.user, motivo), f'Anticipo rechazado: {motivo}')

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        motivo = _motivo(request)
        return self._ejecutar(request, lambda a: servicios.anular_anticipo(a, request.user, motivo), f'Anticipo anulado: {motivo}')

    @action(detail=True, methods=['post'])
    def pagar(self, request, pk=None):
        """`{"forma_pago", "referencia"?}`."""
        forma = str(request.data.get('forma_pago') or 'transferencia')
        referencia = str(request.data.get('referencia') or request.data.get('motivo') or '')
        return self._ejecutar(request, lambda a: servicios.pagar_anticipo(a, request.user, forma, referencia),
                              f'Anticipo pagado ({forma}). Se generaron sus cuotas de recuperación.')

    @action(detail=True, methods=['post'])
    def cancelar_saldo(self, request, pk=None):
        motivo = _motivo(request)
        return self._ejecutar(request, lambda a: servicios.cancelar_saldo(a, request.user, motivo),
                              lambda r: f'Saldo del anticipo pagado aparte ({r[1]:,.0f}): {motivo}'.replace(',', '.'))

    @action(detail=True, methods=['post'])
    def comprobante(self, request, pk=None):
        """El comprobante vigente del pago (para ir a verlo e imprimirlo). Si falta y el usuario puede registrar pagos, lo emite."""
        anticipo = self.get_object()
        recibo = recibo_vigente(anticipo)
        if recibo is None:
            if not alcance.tiene_permiso(request.user, 'novedades.pagar_anticipo'):
                return Response({'detail': 'Este anticipo todavía no tiene comprobante.'}, status=404)
            try:
                recibo = servicios.emitir_recibo_anticipo(anticipo, request.user)
            except ValidationErrorDjango as e:
                raise a_error_drf(e)
            auditoria.registrar(request.user, EventoAuditoria.ALTA, recibo, request=request, descripcion='Comprobante de anticipo emitido.')
        return Response(ReciboAnticipoSerializer(recibo, context=self.get_serializer_context()).data)


class ReciboAnticipoSerializer(RegistroSerializer):
    class Meta:
        model = ReciboAnticipo
        fields = '__all__'


class ReciboAnticipoViewSet(RegistroViewSet):
    """Comprobantes de anticipo: consulta e impresión; `anular` (con motivo) no deshace el pago."""

    serializer_class = ReciboAnticipoSerializer
    search_fields = ['numero', 'empleado__codigo', 'empleado__primer_apellido']
    filtros_exactos = ('empleado', 'anticipo', 'estado')
    campo_fecha = 'fecha_emision'
    permite_borrar = False
    http_method_names = ['get', 'post', 'head', 'options']
    permisos_acciones = {'anular': 'novedades.pagar_anticipo'}

    def create(self, request, *args, **kwargs):
        return Response({'detail': 'El comprobante se emite al registrar el pago del anticipo.'}, status=405)

    def retrieve(self, request, *args, **kwargs):
        """Todo lo que lleva el comprobante impreso: empresa, empleado, pago y plan de descuento."""
        recibo = self.get_object()
        datos = self.get_serializer(recibo).data
        empresa, empleado, anticipo = recibo.empresa, recibo.empleado, recibo.anticipo
        datos['empresa'] = {'nombre': empresa.nombre, 'razon_social': empresa.razon_social, 'ruc': empresa.ruc,
                            'direccion': empresa.direccion}
        if recibo.aporta_ips:  # sin IPS, el comprobante no lleva el número patronal
            datos['empresa']['numero_patronal_ips'] = empresa.numero_patronal_ips
        datos['empleado_datos'] = {'codigo': empleado.codigo, 'nombre': str(empleado), 'documento': empleado.numero_documento,
                                   'puesto': str(empleado.puesto) if empleado.puesto_id else ''}
        datos['anticipo_datos'] = {'fecha': anticipo.fecha, 'motivo': anticipo.motivo, 'monto_solicitado': anticipo.monto_solicitado,
                                   'cuotas': anticipo.cuotas, 'saldo': saldo_de(anticipo)}
        datos['cuotas'] = [{'numero': c.numero, 'mes': c.mes, 'monto': c.monto, 'estado': c.get_estado_display()}
                           for c in anticipo.cuotas_recuperacion.order_by('numero')]
        return Response(datos)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        motivo = _motivo(request)
        recibo = self.get_object()
        try:
            servicios.anular_recibo_anticipo(recibo, request.user, motivo)
        except ValidationErrorDjango as e:
            raise a_error_drf(e)
        auditoria.registrar(request.user, EventoAuditoria.ACCION, recibo, request=request, descripcion=f'Comprobante anulado: {motivo}')
        return Response(self.get_serializer(recibo).data)


class PrestamoSerializer(_ConSaldo):
    monto_cuota = serializers.SerializerMethodField()

    class Meta:
        model = Prestamo
        fields = '__all__'

    def get_monto_cuota(self, prestamo):
        plan = prestamo.plan() if prestamo.capital and prestamo.cantidad_cuotas and prestamo.primer_mes else []
        return str(plan[0][2]) if plan else None


class PrestamoViewSet(_ConAcciones):
    serializer_class = PrestamoSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'motivo']
    filtros_exactos = ('empleado', 'estado')
    campo_fecha = 'fecha'
    permisos_acciones = {'aprobar': 'novedades.aprobar_prestamo', 'rechazar': 'novedades.aprobar_prestamo',
                         'anular': 'novedades.aprobar_prestamo', 'desembolsar': 'novedades.desembolsar_prestamo',
                         'cancelar_saldo': 'novedades.desembolsar_prestamo', 'plan': 'novedades.view_prestamo'}

    def perform_update(self, serializer):
        if serializer.instance.estado != Prestamo.SOLICITADO:
            raise ValidationError({'detail': 'Solo se modifica un préstamo solicitado.'})
        super().perform_update(serializer)

    @action(detail=True, methods=['get', 'post'])
    def plan(self, request, pk=None):
        """Las cuotas que se generarían (o las generadas, con su estado). Con POST, devuelve el plan en texto."""
        prestamo = self.get_object()
        generadas = list(prestamo.cuotas_recuperacion.all())
        if generadas:
            filas = [(c.numero, c.mes, c.monto, c.get_estado_display()) for c in generadas]
        else:
            filas = [(n, m, monto, 'a generar') for n, m, monto in prestamo.plan()]
        total = sum(f[2] for f in filas)
        texto = '\n'.join([f'Cuota {n:>2} · {m:%m/%Y} · {monto:>14,.0f} · {estado}'.replace(',', '.') for n, m, monto, estado in filas]
                          + [f'Total: {total:,.0f}'.replace(',', '.')])
        return Response({'cuotas': [{'numero': n, 'mes': m, 'monto': str(monto), 'estado': e} for n, m, monto, e in filas],
                         'total': str(total), 'texto': texto})

    @action(detail=True, methods=['post'])
    def aprobar(self, request, pk=None):
        return self._ejecutar(request, lambda p: servicios.aprobar_prestamo(p, request.user), 'Préstamo aprobado.')

    @action(detail=True, methods=['post'])
    def rechazar(self, request, pk=None):
        motivo = _motivo(request)
        return self._ejecutar(request, lambda p: servicios.rechazar_prestamo(p, request.user, motivo), f'Préstamo rechazado: {motivo}')

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        motivo = _motivo(request)
        return self._ejecutar(request, lambda p: servicios.anular_prestamo(p, request.user, motivo), f'Préstamo anulado: {motivo}')

    @action(detail=True, methods=['post'])
    def desembolsar(self, request, pk=None):
        """`{"referencia"?}`."""
        referencia = str(request.data.get('referencia') or request.data.get('motivo') or '')
        return self._ejecutar(request, lambda p: servicios.desembolsar_prestamo(p, request.user, referencia),
                              'Préstamo desembolsado. Se generaron sus cuotas.')

    @action(detail=True, methods=['post'])
    def cancelar_saldo(self, request, pk=None):
        motivo = _motivo(request)
        return self._ejecutar(request, lambda p: servicios.cancelar_saldo(p, request.user, motivo),
                              lambda r: f'Saldo del préstamo pagado aparte ({r[1]:,.0f}): {motivo}'.replace(',', '.'))


class CuotaSerializer(RegistroSerializer):
    class Meta:
        model = CuotaRecuperacion
        fields = '__all__'


class CuotaViewSet(RegistroViewSet):
    serializer_class = CuotaSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido']
    filtros_exactos = ('empleado', 'estado', 'anticipo', 'prestamo', 'mes')
    campo_fecha = 'mes'
    permite_borrar = False
    http_method_names = ['get', 'head', 'options']
