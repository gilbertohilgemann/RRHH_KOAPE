from django.contrib import admin

from core.admin_base import SoloLecturaAdmin
from core.models import EventoAuditoria


@admin.register(EventoAuditoria)
class EventoAuditoriaAdmin(SoloLecturaAdmin):
    list_display = ('fecha', 'nombre_usuario', 'empresa', 'accion', 'modelo', 'objeto_texto')
    list_filter = ('accion', 'empresa', 'modelo')
    search_fields = ('nombre_usuario', 'objeto_texto', 'descripcion', 'objeto_id')
    date_hierarchy = 'fecha'

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff
