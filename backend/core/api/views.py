"""Sesión de la app (ingresar/salir/yo) y el resumen del panel."""
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core import alcance, auditoria
from core.models import EventoAuditoria


def _marca_koape():
    from plataforma.models import COLOR_PRIMARIO_KOAPE, COLOR_SECUNDARIO_KOAPE
    return {'logo': None, 'color_primario': COLOR_PRIMARIO_KOAPE, 'color_secundario': COLOR_SECUNDARIO_KOAPE,
            'personalizada': False}


def datos_usuario(usuario, request=None):
    perfil = alcance.perfil_de(usuario)
    empresa = alcance.empresa_de(usuario)
    empleado = alcance.empleado_propio(usuario)
    return {
        'usuario': usuario.username,
        'nombre': usuario.get_full_name() or usuario.username,
        'nivel': alcance.nivel_de(usuario),
        'perfiles': sorted(alcance.roles_de(usuario)),
        'empresa': {'id': empresa.pk, 'nombre': empresa.nombre} if empresa else None,
        # Logo y colores de la empresa (los de Koape para la plataforma o si no cargó los suyos).
        'marca': empresa.marca(request) if empresa else _marca_koape(),
        'sucursales': [{'id': s.pk, 'nombre': s.nombre} for s in perfil.sucursales.all()] if perfil else [],
        'empleado': {'id': empleado.pk, 'codigo': empleado.codigo, 'nombre': empleado.nombre_completo}
        if empleado else None,
        # Para que el frontend oculte los botones que la API igual rechazaría.
        'permisos': alcance.permisos_de(usuario),
    }


class IngresarView(APIView):
    """Usuario y contraseña → token que el frontend manda en cada pedido. Es
    el único endpoint abierto de la API, por eso tiene límite de intentos.
    Los ingresos (y los intentos fallidos) quedan en la auditoría."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ingreso'

    def post(self, request):
        nombre = str(request.data.get('usuario', ''))[:150]
        usuario = authenticate(request, username=nombre, password=request.data.get('clave', ''))
        if usuario is None or not usuario.is_active:
            conocido = User.objects.filter(username=nombre).first()
            auditoria.registrar(None, EventoAuditoria.INGRESO_FALLIDO, conocido, request=request,
                                empresa=getattr(getattr(conocido, 'perfil', None), 'empresa', None),
                                descripcion=f'Intento de ingreso fallido con el usuario "{nombre}".', modelo='auth.User')
            return Response({'detail': 'Usuario o contraseña incorrectos.'}, status=status.HTTP_400_BAD_REQUEST)
        if alcance.nivel_de(usuario) is None:
            return Response(
                {'detail': 'Tu usuario todavía no tiene una empresa y un perfil asignados (o la empresa está inactiva). '
                           'Consultá al administrador.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        token, _ = Token.objects.get_or_create(user=usuario)
        auditoria.registrar(usuario, EventoAuditoria.INGRESO, usuario, empresa=alcance.empresa_de(usuario),
                            request=request, descripcion='Ingreso a la aplicación.')
        return Response({'token': token.key, 'usuario': datos_usuario(usuario, request)})


class SalirView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Borrar el token lo invalida en todos los dispositivos donde se usó.
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class YoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if alcance.nivel_de(request.user) is None:
            return Response({'detail': 'Tu usuario no tiene acceso.'}, status=status.HTTP_403_FORBIDDEN)
        return Response(datos_usuario(request.user, request))


class ResumenView(APIView):
    """Números de cabecera del panel, dentro del alcance del usuario. El
    perfil Empleado no recibe datos generales."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from empleados.models import Empleado
        from plataforma.models import Sucursal

        usuario = request.user
        if not (alcance.es_plataforma(usuario) or alcance.tiene_alcance_empresa(usuario)) \
                or not alcance.tiene_permiso(usuario, 'empleados.view_empleado'):
            return Response({})
        hoy = timezone.localdate()
        inicio_mes = hoy.replace(day=1)
        empleados = alcance.filtrar(Empleado.objects.all(), usuario)
        return Response({
            'empleados_activos': empleados.filter(estado=Empleado.ACTIVO).count(),
            'empleados_suspendidos': empleados.filter(estado=Empleado.SUSPENDIDO).count(),
            'altas_del_mes': empleados.filter(fecha_ingreso__gte=inicio_mes, fecha_ingreso__lte=hoy).count(),
            'bajas_del_mes': empleados.filter(estado=Empleado.BAJA, fecha_egreso__gte=inicio_mes,
                                              fecha_egreso__lte=hoy).count(),
            'sucursales_activas': alcance.filtrar(Sucursal.objects.filter(activa=True), usuario).count(),
        })
