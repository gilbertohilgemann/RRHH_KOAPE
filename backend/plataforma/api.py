"""Empresas y sucursales para la aplicación.

- La empresa: el administrador ve y edita la suya, incluida su
  personalización (logo y colores). No crea ni desactiva empresas: eso lo
  hace la plataforma desde el admin.
- Sucursales: el administrador las da de alta, las edita y las desactiva;
  nunca se borran (tienen empleados e historia)."""
from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from core import alcance, auditoria
from core.api.base import RegistroSerializer, RegistroViewSet
from core.models import EventoAuditoria
from plataforma.models import Empresa, Sucursal

# Logos: solo imágenes de mapa de bits (un SVG puede llevar código y /media/ es público).
FORMATOS_LOGO = {'PNG', 'JPEG', 'WEBP'}
TAMANO_MAXIMO_LOGO = 2 * 1024 * 1024


class EmpresaSerializer(RegistroSerializer):
    marca = serializers.SerializerMethodField()

    class Meta:
        model = Empresa
        exclude = ['logo']
        read_only_fields = ['activa']

    def get_fields(self):
        campos = super().get_fields()
        # La dirección de acceso la asigna la plataforma (cambiarla rompe el enlace que usan los empleados).
        usuario = getattr(self.context.get('request'), 'user', None)
        if 'direccion_acceso' in campos and not alcance.es_plataforma(usuario):
            campos['direccion_acceso'].read_only = True
        return campos

    def get_marca(self, empresa):
        return empresa.marca(self.context.get('request'))

    def validate_color_primario(self, valor):
        return valor.upper()

    def validate_color_secundario(self, valor):
        return valor.upper()


class LogoSerializer(serializers.Serializer):
    logo = serializers.ImageField()

    def validate_logo(self, archivo):
        if archivo.size > TAMANO_MAXIMO_LOGO:
            raise ValidationError('El logo no puede pasar de 2 MB.')
        formato = getattr(getattr(archivo, 'image', None), 'format', None)
        if formato not in FORMATOS_LOGO:
            raise ValidationError('Usá una imagen PNG, JPG o WEBP.')
        return archivo


class EmpresaViewSet(RegistroViewSet):
    serializer_class = EmpresaSerializer
    search_fields = ['nombre', 'razon_social', 'ruc']
    permite_borrar = False
    http_method_names = ['get', 'patch', 'put', 'post', 'delete', 'head', 'options']
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    permisos_acciones = {'logo': 'plataforma.change_empresa'}

    def create(self, request, *args, **kwargs):
        return Response({'detail': 'Las empresas las da de alta la plataforma.'}, status=405)

    @action(detail=True, methods=['post', 'delete'])
    def logo(self, request, pk=None):
        """`POST /api/empresas/<id>/logo/` (multipart, campo `logo`) lo
        reemplaza; `DELETE` lo quita (vuelve el de Koape)."""
        empresa = self.get_object()
        anterior = empresa.logo.name if empresa.logo else ''
        with transaction.atomic():
            if request.method == 'DELETE':
                empresa.logo = None
            else:
                datos = LogoSerializer(data=request.data)
                datos.is_valid(raise_exception=True)
                empresa.logo = datos.validated_data['logo']
            empresa.modificado_por = request.user
            empresa.save(update_fields=['logo', 'modificado_por', 'modificado'])
            auditoria.registrar(request.user, EventoAuditoria.MODIFICACION, empresa, request=request,
                                antes={'logo': anterior}, despues={'logo': empresa.logo.name if empresa.logo else ''},
                                descripcion='Logo quitado.' if request.method == 'DELETE' else 'Logo cambiado.')
        return Response(self.get_serializer(empresa).data)


class SucursalSerializer(RegistroSerializer):
    class Meta:
        model = Sucursal
        fields = '__all__'


class SucursalViewSet(RegistroViewSet):
    serializer_class = SucursalSerializer
    search_fields = ['nombre', 'codigo', 'ciudad']
    filtros_exactos = ('activa',)
    permite_borrar = False
