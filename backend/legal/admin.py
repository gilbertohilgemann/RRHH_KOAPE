from django.contrib import admin

from core.admin_base import RegistroAdmin
from legal.models import ConjuntoReglas, ParametroLegal, RegimenSeguridadSocial


class ParametroInline(admin.TabularInline):
    model = ParametroLegal
    extra = 0


class RegimenInline(admin.TabularInline):
    model = RegimenSeguridadSocial
    extra = 0


@admin.register(ConjuntoReglas)
class ConjuntoReglasAdmin(RegistroAdmin):
    """El estado (revisado, aprobado, retirado) se cambia desde la aplicación,
    con sus controles (cuatro ojos, superposiciones)."""
    list_display = ('nombre', 'codigo', 'version', 'vigente_desde', 'vigente_hasta', 'estado', 'empresa')
    list_filter = ('estado', 'empresa')
    search_fields = ('codigo', 'nombre', 'fuente_numero')
    readonly_fields = ('version', 'version_anterior', 'estado', 'revisado_por', 'revisado_en', 'aprobado_por', 'aprobado_en',
                       'motivo_retiro')
    inlines = [ParametroInline, RegimenInline]

    def has_change_permission(self, request, obj=None):
        if obj is not None and not obj.editable:
            return False
        return super().has_change_permission(request, obj)
