"""API del marcador (§6 bis).

- Empleado (sesión): enviar el QR que escaneó en la pantalla de una terminal, ver su código fijo.
- Terminal (clave propia): su QR dinámico y las marcas recientes (para su pantalla), código fijo, foto.
- RR. HH.: configuración, terminales (con su clave), códigos fijos, marcas,
  intentos rechazados e incidencias. Las marcas son de solo lectura."""
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from asistencia import marcador
from asistencia.autenticacion import AutenticacionTerminal, EsTerminal
from asistencia.models import (ConfiguracionMarcacion, CredencialMarcacion, IncidenciaAsistencia, IntentoMarcacion,
                               Marcacion, TerminalMarcacion)
from core import alcance, auditoria
from core.api.base import RegistroSerializer, RegistroViewSet
from core.models import EventoAuditoria


def _ip(request):
    return auditoria.ip_de(request)


def _datos_marca(marca, con_terminal=False):
    """Lo que muestran ambas pantallas: legajo, nombre, tipo, hora con segundos
    y si hay foto (la foto se pide aparte, con permiso)."""
    empleado = marca.empleado
    datos = {
        'id': marca.pk,
        'legajo': empleado.codigo,
        'empleado': ' '.join(p for p in (empleado.primer_nombre, empleado.segundo_nombre,
                                         empleado.primer_apellido, empleado.segundo_apellido) if p),
        'empleado_id': empleado.pk,
        'tipo': marca.tipo,
        'tipo_texto': marca.get_tipo_display(),
        'hora': timezone.localtime(marca.fecha_hora).strftime('%H:%M:%S'),
        'fecha': timezone.localtime(marca.fecha_hora).strftime('%d/%m/%Y'),
        'tiene_foto': bool(empleado.foto),
        'aviso': next((i.descripcion for i in marca.incidencias.all()), None),
    }
    if con_terminal:
        datos['terminal'] = str(marca.terminal) if marca.terminal_id else ''
    return datos


def _respuesta_marca(resultado, con_terminal=False):
    if resultado['resultado'] != 'ok':
        return resultado
    return {'resultado': 'ok', **_datos_marca(resultado['marcacion'], con_terminal)}


# ------------------------------------------------------------------ empleado

class MarcarQRView(APIView):
    """`POST /api/marcador/qr/ {"token", "tipo"?}`: el empleado, con su sesión,
    envía el QR que escaneó en la pantalla de una terminal."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'qr'

    def post(self, request):
        if not alcance.tiene_permiso(request.user, 'asistencia.marcar_con_qr'):
            raise PermissionDenied('Tu perfil no puede marcar asistencia con QR.')
        empleado = alcance.empleado_propio(request.user)
        if empleado is None:
            raise PermissionDenied('Tu usuario no tiene un legajo vinculado.')
        resultado = marcador.marcar_con_qr(empleado, str(request.data.get('token', '')),
                                           request.data.get('tipo') or None, ip=_ip(request))
        return Response(_respuesta_marca(resultado, con_terminal=True))

class MiCodigoView(APIView):
    """`GET /api/marcador/mi-codigo/`: el código fijo propio, si la empresa lo permite."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        empleado = alcance.empleado_propio(request.user)
        if empleado is None:
            raise PermissionDenied('Tu usuario no tiene un legajo vinculado.')
        configuracion = ConfiguracionMarcacion.de(empleado.empresa)
        if not configuracion.permite_codigo_fijo or not configuracion.empleado_ve_su_codigo:
            return Response({'detail': 'Tu empresa no muestra el código fijo a los empleados.'}, status=status.HTTP_403_FORBIDDEN)
        credencial = CredencialMarcacion.objects.filter(empleado=empleado, estado=CredencialMarcacion.ACTIVA).first()
        if credencial is None:
            return Response({'codigo': None})
        auditoria.registrar(request.user, EventoAuditoria.ACCION, credencial, request=request,
                            descripcion='El empleado consultó su código fijo.')
        return Response({'codigo': credencial.codigo(), 'version': credencial.version})


class MiMarcadorView(APIView):
    """`GET /api/marcador/mi-marcador/`: qué modalidades puede usar el empleado."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        empleado = alcance.empleado_propio(request.user)
        if empleado is None:
            return Response({'qr': False, 'codigo_fijo': False})
        configuracion = ConfiguracionMarcacion.de(empleado.empresa)
        return Response({
            'qr': configuracion.permite_qr and alcance.tiene_permiso(request.user, 'asistencia.marcar_con_qr'),
            'codigo_fijo': configuracion.permite_codigo_fijo and configuracion.empleado_ve_su_codigo,
            'pide_tipo': configuracion.modo_accion == ConfiguracionMarcacion.EXPLICITA,
        })


# ------------------------------------------------------------------ terminal

class _VistaTerminal(APIView):
    authentication_classes = [AutenticacionTerminal]
    permission_classes = [EsTerminal]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'terminal'

    @property
    def terminal(self):
        return self.request.auth


PUERTO_APP_DESARROLLO = 5204


def _ip_de_la_red_local():
    """La IP de esta máquina en la red local (sin enviar nada: el socket UDP no transmite)."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))
            return s.getsockname()[0]
    except OSError:
        return None


def url_de_la_app(request):
    """Dirección de la aplicación que va dentro del QR. Tiene que abrirse
    desde el celular: nunca `localhost` (para el teléfono, es el propio
    teléfono). Usa URL_APP del .env si está; si no, el host desde el que se
    pide, cambiando localhost por la IP de la red local (desarrollo)."""
    from django.conf import settings
    if settings.URL_APP:
        return settings.URL_APP.rstrip('/')
    host = request.get_host().split(':')[0]
    if host in ('localhost', '127.0.0.1', '::1', '[::1]'):
        host = _ip_de_la_red_local() or host
    return f'{request.scheme}://{host}:{PUERTO_APP_DESARROLLO}'


class TerminalYoView(_VistaTerminal):
    """`GET /api/terminal/yo/`: datos para la pantalla de la terminal."""

    def get(self, request):
        terminal = self.terminal
        configuracion = ConfiguracionMarcacion.de(terminal.empresa)
        return Response({
            'terminal': {'id': terminal.pk, 'codigo': terminal.codigo, 'nombre': terminal.nombre,
                         'ubicacion': terminal.ubicacion, 'tipo': terminal.tipo},
            'empresa': terminal.empresa.nombre,
            'marca': terminal.empresa.marca(request),
            'qr': terminal.acepta_qr and configuracion.permite_qr,
            'codigo_fijo': terminal.acepta_codigo and configuracion.permite_codigo_fijo,
            'pide_tipo': configuracion.modo_accion == ConfiguracionMarcacion.EXPLICITA,
            'largo_codigo': configuracion.largo_codigo,
            # Base del enlace del QR (…/marcar/<token>), alcanzable desde el celular.
            'url_app': url_de_la_app(request),
        })


class TerminalQRView(_VistaTerminal):
    """`GET /api/terminal/qr/?actual=<id del QR en pantalla>&desde=<última marca vista>`:
    la pantalla lo consulta cada segundo. Devuelve el QR a mostrar (el token
    solo cuando cambia) y las marcas nuevas hechas en esta terminal."""

    def get(self, request):
        terminal = self.terminal
        actual = request.query_params.get('actual')
        registro, token = marcador.qr_actual(terminal, int(actual) if actual and actual.isdigit() else None)
        desde = request.query_params.get('desde')
        eventos = marcador.eventos_de_terminal(terminal, int(desde) if desde and desde.isdigit() else 0)
        return Response({
            'qr': None if registro is None else {
                'id': registro.pk, 'token': token, 'vence_en': registro.vence_en,
                'segundos': max(int((registro.vence_en - timezone.now()).total_seconds()), 0),
            },
            'eventos': [_datos_marca(m) for m in eventos.prefetch_related('incidencias')],
        })


class TerminalFotoView(_VistaTerminal):
    """`GET /api/terminal/foto/<id de marca>/`: la foto de quien acaba de marcar
    en ESTA terminal (solo durante unos minutos; nunca la de cualquiera)."""

    def get(self, request, pk):
        from datetime import timedelta
        from core import archivos
        marca = Marcacion.objects.select_related('empleado').filter(
            pk=pk, terminal=self.terminal, creado__gte=timezone.now() - timedelta(minutes=5)).first()
        if marca is None or not marca.empleado.foto:
            return Response({'detail': 'Sin foto.'}, status=status.HTTP_404_NOT_FOUND)
        return archivos.servir(marca.empleado.foto, 'foto.jpg', 'image/jpeg')

class TerminalCodigoView(_VistaTerminal):
    """`POST /api/terminal/codigo/ {"codigo", "tipo"?}`."""

    def post(self, request):
        if marcador.terminal_bloqueada(self.terminal):
            return Response({'resultado': 'rechazado', 'codigo': 'bloqueada',
                             'mensaje': 'Demasiados intentos fallidos. Esperá unos minutos.'}, status=429)
        resultado = marcador.marcar_con_codigo(self.terminal, str(request.data.get('codigo', '')),
                                               request.data.get('tipo') or None, ip=_ip(request))
        return Response(_respuesta_marca(resultado))


# ------------------------------------------------------------------ RR. HH.

class ConfiguracionMarcacionSerializer(RegistroSerializer):
    class Meta:
        model = ConfiguracionMarcacion
        fields = '__all__'
        read_only_fields = ['empresa']


class ConfiguracionMarcacionView(APIView):
    """`GET/PATCH /api/marcador/configuracion/`: la de la empresa del usuario."""

    def _configuracion(self, request, tipo):
        if not alcance.tiene_permiso(request.user, f'asistencia.{tipo}_configuracionmarcacion'):
            raise PermissionDenied('No tenés permiso para la configuración del marcador.')
        empresa = alcance.empresa_de(request.user)
        if empresa is None:
            raise ValidationError({'detail': 'Tu usuario no tiene empresa (la plataforma la configura desde el admin).'})
        return ConfiguracionMarcacion.de(empresa)

    def get(self, request):
        configuracion = self._configuracion(request, 'view')
        return Response(ConfiguracionMarcacionSerializer(configuracion, context={'request': request}).data)

    def patch(self, request):
        configuracion = self._configuracion(request, 'change')
        antes = auditoria.instantanea(configuracion)
        datos = ConfiguracionMarcacionSerializer(configuracion, data=request.data, partial=True, context={'request': request})
        datos.is_valid(raise_exception=True)
        with transaction.atomic():
            configuracion = datos.save(modificado_por=request.user)
            anteriores, nuevos = auditoria.diferencias(antes, auditoria.instantanea(configuracion))
            if nuevos:
                auditoria.registrar(request.user, EventoAuditoria.MODIFICACION, configuracion, antes=anteriores,
                                    despues=nuevos, request=request)
        return Response(ConfiguracionMarcacionSerializer(configuracion, context={'request': request}).data)


class TerminalSerializer(RegistroSerializer):
    tiene_clave = serializers.SerializerMethodField()

    class Meta:
        model = TerminalMarcacion
        exclude = ['clave_huella']

    def get_tiene_clave(self, terminal):
        return bool(terminal.clave_huella)


class TerminalViewSet(RegistroViewSet):
    serializer_class = TerminalSerializer
    search_fields = ['codigo', 'nombre', 'ubicacion']
    filtros_exactos = ('activa', 'tipo')
    permite_borrar = False
    permisos_acciones = {'generar_clave': 'asistencia.change_terminalmarcacion'}

    @action(detail=True, methods=['post'])
    def generar_clave(self, request, pk=None):
        """Clave nueva para configurar el dispositivo (la anterior deja de valer). Se muestra una sola vez."""
        terminal = self.get_object()
        clave = terminal.generar_clave()
        auditoria.registrar(request.user, EventoAuditoria.PERMISOS, terminal, request=request,
                            descripcion='Se generó una clave nueva para la terminal (la anterior quedó sin efecto).')
        return Response({'clave': clave})


class CredencialSerializer(RegistroSerializer):
    class Meta:
        model = CredencialMarcacion
        exclude = ['codigo_huella', 'codigo_cifrado']


class CredencialViewSet(RegistroViewSet):
    """Códigos fijos: `POST` con {"empleado"} genera uno nuevo (revoca el
    anterior) y lo devuelve una sola vez; `revocar` lo anula; `revelar` lo
    muestra a quien tiene permiso (auditado)."""

    serializer_class = CredencialSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'empleado__primer_nombre']
    filtros_exactos = ('empleado', 'estado')
    permite_borrar = False
    http_method_names = ['get', 'post', 'head', 'options']
    permisos_acciones = {'revocar': 'asistencia.change_credencialmarcacion',
                         'revelar': 'asistencia.ver_codigo_marcacion'}

    def create(self, request, *args, **kwargs):
        from empleados.models import Empleado
        empleado = alcance.filtrar(Empleado.objects.all(), request.user).filter(pk=request.data.get('empleado') or 0).first()
        if empleado is None:
            raise ValidationError({'empleado': 'Elegí un empleado de tu empresa.'})
        if empleado.estado != Empleado.ACTIVO:
            raise ValidationError({'empleado': 'El empleado no está activo.'})
        credencial, codigo = CredencialMarcacion.generar(empleado, request.user)
        auditoria.registrar(request.user, EventoAuditoria.ALTA, credencial, request=request,
                            descripcion=f'Código fijo v{credencial.version} generado (el anterior, si había, quedó revocado).')
        datos = self.get_serializer(credencial).data
        datos['codigo'] = codigo
        return Response(datos, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def revocar(self, request, pk=None):
        credencial = self.get_object()
        motivo = str(request.data.get('motivo', '')).strip()
        if credencial.estado != CredencialMarcacion.ACTIVA:
            raise ValidationError({'detail': 'El código ya está revocado.'})
        if not motivo:
            raise ValidationError({'motivo': 'Indicá el motivo (pérdida, sospecha de uso indebido…).'})
        credencial.estado = CredencialMarcacion.REVOCADA
        credencial.revocada_en = timezone.now()
        credencial.revocada_por = request.user
        credencial.motivo_revocacion = motivo[:250]
        credencial.save(update_fields=['estado', 'revocada_en', 'revocada_por', 'motivo_revocacion', 'modificado'])
        auditoria.registrar(request.user, EventoAuditoria.BAJA, credencial, request=request,
                            descripcion=f'Código fijo revocado: {motivo}')
        return Response(self.get_serializer(credencial).data)

    @action(detail=True, methods=['post'])
    def revelar(self, request, pk=None):
        credencial = self.get_object()
        auditoria.registrar(request.user, EventoAuditoria.ACCION, credencial, request=request,
                            descripcion='Se mostró el código fijo.')
        return Response({'numero': credencial.codigo()})


class MarcacionSerializer(RegistroSerializer):
    class Meta:
        model = Marcacion
        exclude = ['huella_deduplicacion']


class MarcacionViewSet(RegistroViewSet, viewsets.ReadOnlyModelViewSet):
    serializer_class = MarcacionSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'empleado__primer_nombre', 'referencia']
    filtros_exactos = ('empleado', 'tipo', 'metodo', 'terminal')
    campo_fecha = 'fecha_hora__date'
    http_method_names = ['get', 'head', 'options']


class IntentoSerializer(RegistroSerializer):
    class Meta:
        model = IntentoMarcacion
        fields = '__all__'


class IntentoViewSet(RegistroViewSet, viewsets.ReadOnlyModelViewSet):
    serializer_class = IntentoSerializer
    search_fields = ['mensaje', 'codigo_rechazo', 'empleado__primer_apellido']
    filtros_exactos = ('terminal', 'codigo_rechazo', 'metodo')
    campo_fecha = 'fecha_hora__date'
    http_method_names = ['get', 'head', 'options']


class IncidenciaSerializer(RegistroSerializer):
    class Meta:
        model = IncidenciaAsistencia
        fields = '__all__'
        read_only_fields = ['empleado', 'fecha', 'tipo', 'descripcion', 'marcacion']


class IncidenciaViewSet(RegistroViewSet):
    serializer_class = IncidenciaSerializer
    search_fields = ['empleado__codigo', 'empleado__primer_apellido', 'descripcion']
    filtros_exactos = ('empleado', 'estado', 'tipo')
    campo_fecha = 'fecha'
    permite_borrar = False
    http_method_names = ['get', 'patch', 'head', 'options']
