"""Permiso por defecto de toda la API (ver REST_FRAMEWORK en settings.py).

Vive en su propio módulo, igual que la paginación, a propósito: DRF lo
importa al cargar sus propias vistas; si estuviera en `base.py` (que importa
esas vistas) se armaría un import circular y Django no arrancaría."""
from rest_framework import permissions

from core import alcance

TIPO_POR_METODO = {'POST': 'add', 'PUT': 'change', 'PATCH': 'change', 'DELETE': 'delete'}
ACCIONES_ESTANDAR = {'create', 'update', 'partial_update', 'destroy'}
ACCIONES_LECTURA = {'list', 'retrieve', 'exportar', 'metadata', None}


def permiso_requerido(request, view):
    """El permiso de Django que hace falta para este pedido:

    - acciones propias declaradas en `view.permisos_acciones`
      (ej. {'dar_baja': 'empleados.dar_baja_empleado'});
    - leer (listado, detalle, exportar) → `app.view_modelo`;
    - crear / modificar / borrar → `app.add_modelo` / `change_` / `delete_`;
    - cualquier otra acción propia → `app.change_modelo` (o `view_` si es GET)."""
    accion = getattr(view, 'action', None)
    especiales = getattr(view, 'permisos_acciones', {})
    if accion in especiales:
        return especiales[accion]
    modelo = getattr(view, 'modelo', None)
    if modelo is None:
        return None
    if request.method in permissions.SAFE_METHODS:
        tipo = 'view'
    elif accion in ACCIONES_ESTANDAR:
        tipo = TIPO_POR_METODO.get(request.method, 'change')
    else:
        tipo = 'change'
    return f'{modelo._meta.app_label}.{tipo}_{modelo._meta.model_name}'


class TieneAlcance(permissions.BasePermission):
    """Denegación por defecto: hace falta un perfil con alcance (core/alcance.py)
    y el permiso de Django de la operación, que viene de los perfiles del
    usuario (cuentas/perfiles.py) y se ajusta desde el admin. Ocultar un
    botón en el frontend nunca reemplaza este control."""

    message = 'No tenés permiso para hacer esto.'

    def has_permission(self, request, view):
        usuario = request.user
        if not usuario or not usuario.is_authenticated or alcance.nivel_de(usuario) is None:
            return False
        permiso = permiso_requerido(request, view)
        return permiso is None or alcance.tiene_permiso(usuario, permiso)
