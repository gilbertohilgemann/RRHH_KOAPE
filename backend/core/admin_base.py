from django.contrib import admin
from django.db import transaction

from core import auditoria
from core.models import EventoAuditoria

CAMPOS_AUDITORIA = ('creado_por', 'creado', 'modificado_por', 'modificado')


class RegistroAdmin(admin.ModelAdmin):
    """Base para el admin (solo administrador de plataforma) de todo modelo
    que hereda de `RegistroBase`: muestra la auditoría en solo lectura, la
    completa al guardar y escribe la bitácora, igual que hace la API."""

    list_per_page = 50

    def get_readonly_fields(self, request, obj=None):
        return tuple(super().get_readonly_fields(request, obj)) + CAMPOS_AUDITORIA

    def save_model(self, request, obj, form, change):
        antes = auditoria.instantanea(type(obj).objects.get(pk=obj.pk)) if change else None
        if not change and obj.creado_por_id is None:
            obj.creado_por = request.user
        obj.modificado_por = request.user
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if change:
                anteriores, nuevos = auditoria.diferencias(antes, auditoria.instantanea(obj))
                if nuevos:
                    auditoria.registrar(request.user, EventoAuditoria.MODIFICACION, obj, antes=anteriores,
                                        despues=nuevos, request=request, descripcion='Desde el admin.')
            else:
                auditoria.registrar(request.user, EventoAuditoria.ALTA, obj, despues=auditoria.instantanea(obj),
                                    request=request, descripcion='Desde el admin.')

    def delete_model(self, request, obj):
        with transaction.atomic():
            auditoria.registrar(request.user, EventoAuditoria.BORRADO, obj, antes=auditoria.instantanea(obj),
                                request=request, descripcion='Desde el admin.')
            super().delete_model(request, obj)


class SoloLecturaAdmin(admin.ModelAdmin):
    """Registros que se consultan desde el admin pero nunca se cargan,
    modifican ni borran a mano (auditoría, historiales)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
