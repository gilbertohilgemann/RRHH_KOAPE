"""Legajos: departamentos, puestos, centros de costo y empleados.

Los empleados nunca se borran por la API: la baja es lógica (`dar_baja`) y
se deshace con `reactivar`, cada una con su permiso propio (por defecto solo
el Administrador). El perfil Empleado ve solo su propio legajo, sin las
observaciones internas."""
from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core import alcance, archivos, auditoria
from core.api.base import CatalogoViewSet, RegistroSerializer, RegistroViewSet, a_error_drf
from core.models import EventoAuditoria
from empleados.models import (CentroCosto, CuentaBancaria, Departamento, DocumentoEmpleado, Empleado,
                              HistorialAsignacion, Puesto, TipoDocumento)


class DepartamentoSerializer(RegistroSerializer):
    class Meta:
        model = Departamento
        fields = '__all__'


class DepartamentoViewSet(RegistroViewSet):
    serializer_class = DepartamentoSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('activo',)


class PuestoSerializer(RegistroSerializer):
    class Meta:
        model = Puesto
        fields = '__all__'


class PuestoViewSet(RegistroViewSet):
    serializer_class = PuestoSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('activo',)


class CentroCostoSerializer(RegistroSerializer):
    class Meta:
        model = CentroCosto
        fields = '__all__'


class CentroCostoViewSet(RegistroViewSet):
    serializer_class = CentroCostoSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('activo',)


class TipoDocumentoSerializer(RegistroSerializer):
    es_global = serializers.BooleanField(read_only=True)

    class Meta:
        model = TipoDocumento
        fields = '__all__'


class TipoDocumentoViewSet(CatalogoViewSet):
    serializer_class = TipoDocumentoSerializer
    search_fields = ['codigo', 'nombre']
    filtros_exactos = ('activo', 'confidencial')


class DocumentoEmpleadoSerializer(RegistroSerializer):
    archivo = serializers.FileField(write_only=True)

    class Meta:
        model = DocumentoEmpleado
        fields = '__all__'

    def get_fields(self):
        campos = super().get_fields()
        if self.instance is not None:
            # El archivo no se reemplaza: si estaba mal, se anula y se carga otro.
            campos.pop('archivo')
            campos['empleado'].read_only = True
            campos['tipo_documento'].read_only = True
        return campos

    def validate_archivo(self, archivo):
        try:
            self._tipo_mime, self._sha256 = archivos.validar_archivo(archivo)
        except ValidationErrorDjango as e:
            raise ValidationError(e.messages)
        return archivo

    def create(self, datos):
        archivo = datos['archivo']
        datos.update(nombre_original=archivo.name[:255], tipo_mime=self._tipo_mime, tamano=archivo.size,
                     sha256=self._sha256, confidencial=datos['tipo_documento'].confidencial)
        return super().create(datos)


class DocumentoEmpleadoViewSet(RegistroViewSet):
    serializer_class = DocumentoEmpleadoSerializer
    search_fields = ['descripcion', 'nombre_original', 'tipo_documento__nombre', 'empleado__primer_apellido',
                     'empleado__codigo']
    filtros_exactos = ('empleado', 'tipo_documento', 'estado')
    campo_fecha = 'creado__date'
    permite_borrar = False
    permisos_acciones = {'descargar': 'empleados.view_documentoempleado', 'anular': 'empleados.anular_documento'}

    def get_queryset(self):
        qs = super().get_queryset()
        usuario = self.request.user
        # Confidenciales (datos médicos...): solo con el permiso, salvo los propios.
        if not alcance.tiene_permiso(usuario, 'empleados.ver_documento_confidencial'):
            propio = alcance.empleado_propio(usuario)
            qs = qs.exclude(Q(confidencial=True) & ~Q(empleado_id=propio.pk if propio else None))
        return qs

    @action(detail=True, methods=['get'])
    def descargar(self, request, pk=None):
        documento = self.get_object()
        auditoria.registrar(request.user, EventoAuditoria.ACCION, documento, request=request,
                            descripcion=f'Descarga del documento "{documento.nombre_original}".')
        return archivos.servir(documento.archivo, documento.nombre_original, documento.tipo_mime)

    @action(detail=True, methods=['post'])
    def anular(self, request, pk=None):
        documento = self.get_object()
        motivo = str(request.data.get('motivo', '')).strip()
        if documento.estado == DocumentoEmpleado.ANULADO:
            raise ValidationError({'detail': 'El documento ya está anulado.'})
        if not motivo:
            raise ValidationError({'motivo': 'Indicá el motivo.'})
        with transaction.atomic():
            documento.estado = DocumentoEmpleado.ANULADO
            documento.motivo_anulacion = motivo[:250]
            documento.modificado_por = request.user
            documento.save(update_fields=['estado', 'motivo_anulacion', 'modificado_por', 'modificado'])
            auditoria.registrar(request.user, EventoAuditoria.BAJA, documento, request=request,
                                descripcion=f'Documento anulado: {motivo}')
        return Response(self.get_serializer(documento).data)


class CuentaBancariaSerializer(RegistroSerializer):
    numero = serializers.CharField(write_only=True, required=False, max_length=60,
                                   help_text='Número completo; se guarda cifrado y no se devuelve.')
    numero_enmascarado = serializers.CharField(read_only=True)

    class Meta:
        model = CuentaBancaria
        exclude = ['numero_cifrado']

    def validate(self, datos):
        numero = datos.pop('numero', None)
        if self.instance is None and not numero:
            raise ValidationError({'numero': 'Indicá el número de cuenta.'})
        if numero:
            try:
                CuentaBancaria().fijar_numero(numero)
            except ValidationErrorDjango as e:
                raise a_error_drf(e)
        datos = super().validate(datos)
        self._numero = numero
        return datos

    def create(self, datos):
        cuenta = CuentaBancaria(**datos)
        cuenta.fijar_numero(self._numero)
        cuenta.save()
        return cuenta

    def update(self, cuenta, datos):
        if self._numero:
            cuenta.fijar_numero(self._numero)
        return super().update(cuenta, datos)


class CuentaBancariaViewSet(RegistroViewSet):
    serializer_class = CuentaBancariaSerializer
    search_fields = ['banco', 'titular', 'ultimos_digitos', 'empleado__primer_apellido', 'empleado__codigo']
    filtros_exactos = ('empleado', 'activa', 'principal')
    permite_borrar = False
    permisos_acciones = {'revelar': 'empleados.ver_cuenta_completa'}

    @action(detail=True, methods=['post'])
    def revelar(self, request, pk=None):
        """`POST .../revelar/`: el número completo, a pedido; queda en la auditoría."""
        cuenta = self.get_object()
        numero = cuenta.numero_completo()
        auditoria.registrar(request.user, EventoAuditoria.ACCION, cuenta, request=request,
                            descripcion='Se mostró el número completo de la cuenta.')
        if numero is None:
            return Response({'detail': 'No se pudo descifrar (¿cambió la CLAVE_CIFRADO del servidor?).'}, status=409)
        return Response({'numero': numero})


class EmpleadoSerializer(RegistroSerializer):
    nombre_completo = serializers.CharField(read_only=True)
    # La foto es privada: no se expone su ruta, se pide a `<id>/foto/`.
    tiene_foto = serializers.SerializerMethodField()
    # Tipo de sueldo (hora, día, semana, quincena, mes…) del sueldo vigente: se cambia en Contratos / Historial salarial.
    tipo_sueldo = serializers.SerializerMethodField()

    class Meta:
        model = Empleado
        exclude = ['foto']

    def get_tiene_foto(self, empleado):
        return bool(empleado.foto)

    def get_tipo_sueldo(self, empleado):
        from contratos.models import sueldo_vigente
        if not empleado.pk:
            return ''
        sueldo = sueldo_vigente(empleado, empleado.fecha_egreso or None)
        return sueldo.esquema_salarial.get_base_calculo_display() if sueldo else 'Sin sueldo vigente'


class FichaPropiaSerializer(EmpleadoSerializer):
    """Lo que ve el propio empleado de su legajo: todo menos las observaciones internas."""

    class Meta(EmpleadoSerializer.Meta):
        exclude = ['observaciones', 'foto']


class BajaSerializer(serializers.Serializer):
    fecha_egreso = serializers.DateField()
    motivo = serializers.CharField(max_length=250)


class HistorialAsignacionSerializer(RegistroSerializer):
    class Meta:
        model = HistorialAsignacion
        fields = '__all__'


class EmpleadoViewSet(RegistroViewSet):
    serializer_class = EmpleadoSerializer
    search_fields = ['codigo', 'numero_documento', 'primer_nombre', 'segundo_nombre', 'primer_apellido',
                     'segundo_apellido']
    filtros_exactos = ('estado', 'departamento', 'puesto', 'centro_costo')
    campo_fecha = 'fecha_ingreso'
    permite_borrar = False
    permisos_acciones = {
        'dar_baja': 'empleados.dar_baja_empleado',
        'reactivar': 'empleados.reactivar_empleado',
        'historial': 'empleados.view_historialasignacion',
    }

    def get_serializer_class(self):
        if self.request.user.is_authenticated and not alcance.es_plataforma(self.request.user) \
                and not alcance.tiene_alcance_empresa(self.request.user):
            return FichaPropiaSerializer
        return EmpleadoSerializer

    @action(detail=True, methods=['post'])
    def dar_baja(self, request, pk=None):
        """`POST /api/empleados/<id>/dar_baja/ {"fecha_egreso", "motivo"}`: baja lógica."""
        empleado = self.get_object()
        datos = BajaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        fecha, motivo = datos.validated_data['fecha_egreso'], datos.validated_data['motivo'].strip()
        if empleado.estado == Empleado.BAJA:
            raise ValidationError({'detail': 'El empleado ya está dado de baja.'})
        if fecha < empleado.fecha_ingreso:
            raise ValidationError({'fecha_egreso': 'No puede ser anterior a la fecha de ingreso.'})
        if not motivo:
            raise ValidationError({'motivo': 'Indicá el motivo de la baja.'})
        antes = auditoria.instantanea(empleado)
        with transaction.atomic():
            empleado.estado = Empleado.BAJA
            empleado.fecha_egreso = fecha
            empleado.motivo_egreso = motivo
            empleado.modificado_por = request.user
            empleado.save(update_fields=['estado', 'fecha_egreso', 'motivo_egreso', 'modificado_por', 'modificado'])
            HistorialAsignacion.objects.filter(empleado=empleado, vigente_hasta__isnull=True).update(vigente_hasta=fecha)
            anteriores, nuevos = auditoria.diferencias(antes, auditoria.instantanea(empleado))
            auditoria.registrar(request.user, EventoAuditoria.BAJA, empleado, antes=anteriores, despues=nuevos,
                                descripcion=f'Baja lógica: {motivo}', request=request)
        return Response(self.get_serializer(empleado).data)

    @action(detail=True, methods=['post'])
    def reactivar(self, request, pk=None):
        """`POST /api/empleados/<id>/reactivar/ {"motivo"}`: deshace una baja."""
        empleado = self.get_object()
        motivo = str(request.data.get('motivo', '')).strip()
        if empleado.estado != Empleado.BAJA:
            raise ValidationError({'detail': 'El empleado no está dado de baja.'})
        if not motivo:
            raise ValidationError({'motivo': 'Indicá el motivo de la reactivación.'})
        antes = auditoria.instantanea(empleado)
        with transaction.atomic():
            empleado.estado = Empleado.ACTIVO
            empleado.fecha_egreso = None
            empleado.motivo_egreso = ''
            empleado.modificado_por = request.user
            empleado.save(update_fields=['estado', 'fecha_egreso', 'motivo_egreso', 'modificado_por', 'modificado'])
            empleado._registrar_asignacion(desde=max(timezone.localdate(), empleado.fecha_ingreso),
                                           motivo=f'Reactivación: {motivo}')
            anteriores, nuevos = auditoria.diferencias(antes, auditoria.instantanea(empleado))
            auditoria.registrar(request.user, EventoAuditoria.ACCION, empleado, antes=anteriores, despues=nuevos,
                                descripcion=f'Reactivación: {motivo}', request=request)
        return Response(self.get_serializer(empleado).data)

    @action(detail=True, methods=['get', 'post', 'delete'])
    def foto(self, request, pk=None):
        """`GET` la foto (quien puede ver el legajo); `POST` (multipart, campo
        `foto`) la reemplaza y `DELETE` la quita (permiso de modificar el legajo)."""
        empleado = self.get_object()
        if request.method == 'GET':
            if not empleado.foto:
                return Response({'detail': 'El empleado no tiene foto.'}, status=404)
            return archivos.servir(empleado.foto, f'foto-{empleado.codigo}.jpg', 'image/jpeg')
        anterior = empleado.foto.name if empleado.foto else ''
        if request.method == 'DELETE':
            empleado.foto = None
        else:
            subida = request.FILES.get('foto')
            if subida is None:
                raise ValidationError({'foto': 'Elegí una foto.'})
            try:
                empleado.foto.save('foto.jpg', archivos.preparar_foto(subida), save=False)
            except ValidationErrorDjango as e:
                raise ValidationError({'foto': e.messages})
        empleado.modificado_por = request.user
        empleado.save(update_fields=['foto', 'modificado_por', 'modificado'])
        auditoria.registrar(request.user, EventoAuditoria.MODIFICACION, empleado, request=request,
                            antes={'foto': anterior}, despues={'foto': empleado.foto.name if empleado.foto else ''},
                            descripcion='Foto quitada.' if request.method == 'DELETE' else 'Foto cambiada.')
        return Response(self.get_serializer(empleado).data)

    @action(detail=True, methods=['get'])
    def historial(self, request, pk=None):
        """Historial de asignaciones del empleado (más reciente primero)."""
        empleado = self.get_object()
        filas = empleado.historial_asignaciones.select_related(
            'sucursal', 'departamento', 'puesto', 'centro_costo', 'supervisor',
        ).order_by('-vigente_desde', '-id')
        return Response(HistorialAsignacionSerializer(filas, many=True, context=self.get_serializer_context()).data)
