"""Usuarios de la empresa, para el Administrador (permiso
`cuentas.gestionar_usuarios`).

Reglas (§11 bis, reglas técnicas 6 y 7):
- Solo usuarios de su empresa; nunca ve ni toca superusuarios ni usuarios de
  la plataforma, y nunca asigna el grupo Koape.
- No puede cambiarse a sí mismo los perfiles, las sucursales ni desactivarse
  (evita autoelevarse privilegios o quedarse afuera por error).
- El perfil Empleado exige un legajo de la misma empresa, que no esté
  vinculado a otro usuario.
- Los usuarios no se borran: se desactivan.
- Cada alta, cambio de perfiles y desactivación queda en la auditoría
  (nunca la contraseña)."""
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ValidationErrorDjango
from django.db import transaction
from rest_framework import permissions, serializers, viewsets
from rest_framework.exceptions import ValidationError

from core import alcance, auditoria
from core.models import EventoAuditoria
from cuentas.models import Perfil
from empleados.models import Empleado
from plataforma.models import Empresa, Sucursal

PERMISO = 'cuentas.gestionar_usuarios'


class GestionaUsuarios(permissions.BasePermission):
    message = 'No tenés permiso para administrar usuarios.'

    def has_permission(self, request, view):
        usuario = request.user
        return bool(usuario and usuario.is_authenticated and alcance.nivel_de(usuario) is not None
                    and alcance.tiene_permiso(usuario, PERMISO))


def _instantanea_usuario(usuario):
    perfil = getattr(usuario, 'perfil', None)
    return {
        'usuario': usuario.username,
        'nombre': usuario.first_name,
        'apellido': usuario.last_name,
        'correo': usuario.email,
        'activo': usuario.is_active,
        'perfiles': sorted(usuario.groups.values_list('name', flat=True)),
        'empresa': perfil.empresa_id if perfil else None,
        'sucursales': sorted(perfil.sucursales.values_list('pk', flat=True)) if perfil else [],
        'empleado': perfil.empleado_id if perfil else None,
    }


class UsuarioSerializer(serializers.ModelSerializer):
    roles = serializers.ListField(child=serializers.ChoiceField(choices=alcance.GRUPOS_ASIGNABLES), write_only=True)
    sucursales = serializers.PrimaryKeyRelatedField(queryset=Sucursal.objects.all(), many=True, required=False,
                                                    write_only=True)
    empleado = serializers.PrimaryKeyRelatedField(queryset=Empleado.objects.all(), allow_null=True, required=False,
                                                  write_only=True)
    empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all(), required=False, write_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True,
                                     style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'is_active', 'last_login', 'date_joined',
                  'roles', 'sucursales', 'empleado', 'empresa', 'password']
        read_only_fields = ['last_login', 'date_joined']

    def get_fields(self):
        campos = super().get_fields()
        usuario = self.context['request'].user
        # Solo lo que el administrador puede ver de su empresa.
        campos['sucursales'].child_relation.queryset = alcance.filtrar(Sucursal.objects.all(), usuario)
        campos['empleado'].queryset = alcance.filtrar(Empleado.objects.all(), usuario)
        if not alcance.es_plataforma(usuario):
            campos.pop('empresa')
        return campos

    def to_representation(self, instancia):
        datos = super().to_representation(instancia)
        perfil = getattr(instancia, 'perfil', None)
        roles = sorted(instancia.groups.values_list('name', flat=True))
        datos.update({
            'texto': f'{instancia.get_full_name() or instancia.username} ({instancia.username})',
            'roles': roles,
            'roles_texto': ', '.join(roles),
            'sucursales': [s.pk for s in perfil.sucursales.all()] if perfil else [],
            'sucursales_opciones': [{'id': s.pk, 'texto': str(s)} for s in perfil.sucursales.all()] if perfil else [],
            'sucursales_texto': ', '.join(str(s) for s in perfil.sucursales.all()) if perfil else '',
            'empleado': perfil.empleado_id if perfil else None,
            'empleado_texto': str(perfil.empleado) if perfil and perfil.empleado_id else '',
            'empresa_texto': str(perfil.empresa) if perfil else '',
            'is_active_texto': 'Activo' if instancia.is_active else 'Inactivo',
        })
        return datos

    def validate(self, datos):
        request = self.context['request']
        yo = request.user
        es_nuevo = self.instance is None
        perfil = getattr(self.instance, 'perfil', None) if self.instance else None

        if es_nuevo and not datos.get('roles'):
            raise ValidationError({'roles': 'Elegí al menos un perfil.'})
        if 'roles' in datos and not datos['roles']:
            raise ValidationError({'roles': 'Elegí al menos un perfil.'})
        if es_nuevo and not datos.get('password'):
            raise ValidationError({'password': 'Indicá una contraseña inicial.'})

        if self.instance is not None and self.instance.pk == yo.pk:
            if 'roles' in datos and set(datos['roles']) != set(self.instance.groups.values_list('name', flat=True)):
                raise ValidationError({'roles': 'No podés cambiar tus propios perfiles: pedíselo a otro administrador.'})
            if 'sucursales' in datos and {s.pk for s in datos['sucursales']} != set(
                    perfil.sucursales.values_list('pk', flat=True) if perfil else []):
                raise ValidationError({'sucursales': 'No podés cambiar tus propias sucursales.'})
            if datos.get('is_active') is False:
                raise ValidationError({'is_active': 'No podés desactivar tu propio usuario.'})

        empresa = datos.get('empresa') or (perfil.empresa if perfil else None) or alcance.empresa_de(yo)
        if empresa is None:
            raise ValidationError({'empresa': 'Indicá la empresa del usuario.'})
        for sucursal in datos.get('sucursales', []):
            if sucursal.empresa_id != empresa.pk:
                raise ValidationError({'sucursales': 'Las sucursales tienen que ser de la empresa del usuario.'})

        empleado = datos['empleado'] if 'empleado' in datos else (perfil.empleado if perfil else None)
        roles = datos['roles'] if 'roles' in datos else list(self.instance.groups.values_list('name', flat=True))
        if empleado is not None:
            if empleado.empresa_id != empresa.pk:
                raise ValidationError({'empleado': 'El legajo tiene que ser de la empresa del usuario.'})
            otro = Perfil.objects.filter(empleado=empleado).exclude(usuario=self.instance).first()
            if otro is not None:
                raise ValidationError({'empleado': f'Ese legajo ya está vinculado al usuario {otro.usuario.username}.'})
        if alcance.GRUPO_EMPLEADO in roles and empleado is None:
            raise ValidationError({'empleado': 'El perfil Empleado necesita el legajo del empleado.'})

        if datos.get('password'):
            candidato = self.instance or User(username=datos.get('username', ''), email=datos.get('email', ''),
                                              first_name=datos.get('first_name', ''), last_name=datos.get('last_name', ''))
            try:
                validate_password(datos['password'], candidato)
            except ValidationErrorDjango as e:
                raise ValidationError({'password': list(e.messages)})
        datos['_empresa'] = empresa
        return datos

    @transaction.atomic
    def create(self, datos):
        roles = datos.pop('roles')
        sucursales = datos.pop('sucursales', [])
        empleado = datos.pop('empleado', None)
        empresa = datos.pop('_empresa')
        datos.pop('empresa', None)
        clave = datos.pop('password')
        usuario = User(**datos)
        usuario.set_password(clave)
        usuario.save()
        usuario.groups.set(Group.objects.filter(name__in=roles))
        perfil = Perfil.objects.create(usuario=usuario, empresa=empresa, empleado=empleado)
        perfil.sucursales.set(sucursales)
        return usuario

    @transaction.atomic
    def update(self, usuario, datos):
        roles = datos.pop('roles', None)
        sucursales = datos.pop('sucursales', None)
        empleado_enviado = 'empleado' in datos
        empleado = datos.pop('empleado', None)
        empresa = datos.pop('_empresa')
        datos.pop('empresa', None)
        clave = datos.pop('password', '')
        for campo, valor in datos.items():
            setattr(usuario, campo, valor)
        if clave:
            usuario.set_password(clave)
        usuario.save()
        if roles is not None:
            usuario.groups.set(Group.objects.filter(name__in=roles))
        perfil, _ = Perfil.objects.get_or_create(usuario=usuario, defaults={'empresa': empresa})
        if empleado_enviado:
            perfil.empleado = empleado
            perfil.save(update_fields=['empleado'])
        if sucursales is not None:
            perfil.sucursales.set(sucursales)
        return usuario


class UsuarioViewSet(viewsets.ModelViewSet):
    serializer_class = UsuarioSerializer
    permission_classes = [GestionaUsuarios]
    http_method_names = ['get', 'post', 'patch', 'put', 'head', 'options']
    search_fields = ['username', 'first_name', 'last_name', 'email']
    ordering_fields = ['username', 'first_name', 'last_name', 'last_login', 'is_active']

    def get_queryset(self):
        usuario = self.request.user
        qs = User.objects.filter(perfil__isnull=False).select_related('perfil__empresa', 'perfil__empleado') \
            .prefetch_related('groups', 'perfil__sucursales').order_by('username')
        if not alcance.es_plataforma(usuario):
            qs = qs.filter(perfil__empresa=alcance.empresa_de(usuario), is_superuser=False) \
                .exclude(groups__name=alcance.GRUPO_KOAPE)
        activo = self.request.query_params.get('is_active')
        if activo in ('true', 'false'):
            qs = qs.filter(is_active=activo == 'true')
        return qs

    def perform_create(self, serializer):
        usuario = serializer.save()
        auditoria.registrar(self.request.user, EventoAuditoria.ALTA, usuario, empresa=usuario.perfil.empresa,
                            despues=_instantanea_usuario(usuario), request=self.request,
                            descripcion='Alta de usuario con perfiles: ' + ', '.join(_instantanea_usuario(usuario)['perfiles']))

    def perform_update(self, serializer):
        antes = _instantanea_usuario(serializer.instance)
        clave_cambiada = bool(serializer.validated_data.get('password'))
        usuario = serializer.save()
        anteriores, nuevos = auditoria.diferencias(antes, _instantanea_usuario(usuario))
        if clave_cambiada:
            nuevos['contraseña'] = 'cambiada'
        if nuevos:
            permisos = any(c in nuevos for c in ('perfiles', 'sucursales', 'empleado', 'activo'))
            auditoria.registrar(self.request.user, EventoAuditoria.PERMISOS if permisos else EventoAuditoria.MODIFICACION,
                                usuario, empresa=usuario.perfil.empresa, antes=anteriores, despues=nuevos,
                                request=self.request)
