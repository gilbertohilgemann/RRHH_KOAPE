"""Aislamiento entre empresas, sucursales y empleados: el único lugar que
decide qué filas puede VER cada usuario. Toda la API filtra por acá
(core/api/base.py); si una consulta no pasa por `filtrar()`, es un agujero de
seguridad.

Qué puede HACER cada usuario (ver un tipo de registro, cargar, modificar,
dar de baja, aprobar...) no se decide acá: lo dan los permisos de Django de
sus perfiles (cuentas/perfiles.py y core/api/permisos.py), que se ajustan
desde el admin sin tocar código.

Perfiles (grupos de Django) y alcance:
- Koape (plataforma): superusuario o grupo "Koape" → ve todo.
- Administrador y Gestor RR. HH.: todo lo de su empresa; si su perfil tiene
  sucursales asignadas, solo lo de esas sucursales (en los modelos que
  declaran `ruta_sucursal`).
- Empleado: solo lo de su propio legajo (`ruta_empleado` del modelo). El
  legajo se toma del perfil del usuario en el servidor: nunca de un id que
  mande el navegador.
- Sin perfil ni grupo: no ve nada.

Una persona con varios perfiles (ej. Gestor y Empleado, asignados a mano por
un administrador) tiene la unión: el alcance más amplio y todos los permisos.
"""
from django.apps import apps
from django.core.exceptions import ValidationError

NIVEL_PLATAFORMA = 'plataforma'
NIVEL_ADMINISTRADOR = 'administrador'
NIVEL_GESTOR = 'gestor'
NIVEL_EMPLEADO = 'empleado'

# Grupos (perfiles) del sistema. Los crea cuentas/apps.py al migrar, con los
# permisos iniciales de cuentas/perfiles.py.
GRUPO_KOAPE = 'Koape'
GRUPO_ADMINISTRADOR = 'Administrador'
GRUPO_GESTOR = 'Gestor RR. HH.'
GRUPO_EMPLEADO = 'Empleado'
GRUPOS_INICIALES = [GRUPO_KOAPE, GRUPO_ADMINISTRADOR, GRUPO_GESTOR, GRUPO_EMPLEADO]
# Los que un administrador de empresa puede asignar (nunca el de plataforma).
GRUPOS_ASIGNABLES = [GRUPO_ADMINISTRADOR, GRUPO_GESTOR, GRUPO_EMPLEADO]


def perfil_de(usuario):
    if not usuario or not usuario.is_authenticated:
        return None
    try:
        return usuario.perfil
    except apps.get_model('cuentas', 'Perfil').DoesNotExist:
        return None


def roles_de(usuario):
    if not usuario or not usuario.is_authenticated:
        return set()
    # Se guarda en el objeto: se consulta varias veces por pedido.
    if not hasattr(usuario, '_roles_rrhh'):
        usuario._roles_rrhh = set(usuario.groups.values_list('name', flat=True))
    return usuario._roles_rrhh


def es_plataforma(usuario):
    return bool(usuario and usuario.is_authenticated and (usuario.is_superuser or GRUPO_KOAPE in roles_de(usuario)))


def empresa_de(usuario):
    """La empresa del usuario (None para la plataforma, que ve todas)."""
    perfil = perfil_de(usuario)
    return perfil.empresa if perfil and perfil.empresa_id and perfil.empresa.activa else None


def tiene_alcance_empresa(usuario):
    """Administrador o Gestor: ve los datos generales de RR. HH. de su empresa."""
    return bool(roles_de(usuario) & {GRUPO_ADMINISTRADOR, GRUPO_GESTOR}) and empresa_de(usuario) is not None


def empleado_propio(usuario):
    """El legajo vinculado al usuario (perfil Empleado), o None."""
    perfil = perfil_de(usuario)
    if perfil is None or not perfil.empleado_id or empresa_de(usuario) is None:
        return None
    return perfil.empleado


def nivel_de(usuario):
    """El perfil más amplio del usuario (para el frontend y los mensajes)."""
    if es_plataforma(usuario):
        return NIVEL_PLATAFORMA
    if empresa_de(usuario) is None:
        return None
    roles = roles_de(usuario)
    if GRUPO_ADMINISTRADOR in roles:
        return NIVEL_ADMINISTRADOR
    if GRUPO_GESTOR in roles:
        return NIVEL_GESTOR
    if GRUPO_EMPLEADO in roles and empleado_propio(usuario) is not None:
        return NIVEL_EMPLEADO
    return None


def sucursales_limitadas(usuario):
    """Ids de las sucursales a las que está limitado el usuario, o None si ve
    todas las de su empresa."""
    perfil = perfil_de(usuario)
    if perfil is None or perfil.pk is None:
        return None
    ids = list(perfil.sucursales.values_list('pk', flat=True))
    return ids or None


def _filtro(ruta, valor, en=False):
    if ruta == '':
        return {'pk__in' if en else 'pk': valor}
    return {f'{ruta}__in' if en else ruta: valor}


def filtrar(queryset, usuario):
    """Restringe cualquier queryset a lo que el usuario puede ver, según las
    rutas del modelo (ver core/models.py)."""
    modelo = queryset.model
    nivel = nivel_de(usuario)
    if nivel == NIVEL_PLATAFORMA:
        return queryset
    if nivel is None:
        return queryset.none()
    # Catálogos con ítems globales (empresa vacía) + los de cada empresa.
    if hasattr(modelo, 'filtrar_por_alcance'):
        return modelo.filtrar_por_alcance(queryset, usuario)
    ruta = getattr(modelo, 'ruta_empresa', None)
    if ruta is None:
        raise ValueError(f'{modelo.__name__} no define ruta_empresa: no se puede filtrar por alcance.')
    empresa = empresa_de(usuario)

    if tiene_alcance_empresa(usuario):
        filtrado = queryset.filter(**_filtro(ruta, empresa.pk))
        limitadas = sucursales_limitadas(usuario)
        ruta_sucursal = getattr(modelo, 'ruta_sucursal', None)
        if limitadas is not None and ruta_sucursal is not None:
            filtrado = filtrado.filter(**_filtro(ruta_sucursal, limitadas, en=True))
        return filtrado

    # Solo Empleado: lo de su legajo.
    empleado = empleado_propio(usuario)
    ruta_empleado = getattr(modelo, 'ruta_empleado', None)
    if empleado is not None and ruta_empleado is not None:
        return queryset.filter(**_filtro(ruta, empresa.pk)).filter(**_filtro(ruta_empleado, empleado.pk))
    return queryset.none()


def empresa_para_crear(usuario, empresa_pedida):
    """La empresa de un registro nuevo. Un usuario de empresa nunca la elige:
    se toma de su perfil (si mandara otra, se ignora). La plataforma la indica."""
    if es_plataforma(usuario):
        if empresa_pedida is None:
            raise ValidationError({'empresa': 'Indicá la empresa.'})
        return empresa_pedida
    empresa = empresa_de(usuario)
    if empresa is None:
        raise ValidationError({'empresa': 'Tu usuario no tiene empresa asignada.'})
    return empresa


def tiene_permiso(usuario, permiso):
    """Permiso de Django ('app.codigo'). La plataforma, siempre."""
    return es_plataforma(usuario) or usuario.has_perm(permiso)


def permisos_de(usuario):
    """Lista de permisos para el frontend (que oculta botones); '*' = todos."""
    if es_plataforma(usuario):
        return ['*']
    return sorted(usuario.get_all_permissions())
