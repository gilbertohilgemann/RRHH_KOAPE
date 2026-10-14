from django.contrib import admin

from core.admin_base import RegistroAdmin
from plataforma.models import Empresa, Sucursal


class SucursalEnLinea(admin.TabularInline):
    model = Sucursal
    extra = 0
    fields = ('codigo', 'nombre', 'ciudad', 'activa')
    show_change_link = True


@admin.register(Empresa)
class EmpresaAdmin(RegistroAdmin):
    list_display = ('nombre', 'ruc', 'numero_patronal_ips', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre', 'razon_social', 'ruc')
    inlines = [SucursalEnLinea]

    def save_formset(self, request, form, formset, change):
        # Las sucursales cargadas en línea también llevan su auditoría.
        for objeto in formset.save(commit=False):
            if objeto.pk is None:
                objeto.creado_por = request.user
            objeto.modificado_por = request.user
            objeto.save()
        for objeto in formset.deleted_objects:
            objeto.delete()
        formset.save_m2m()

    def has_delete_permission(self, request, obj=None):
        # Una empresa nunca se borra: se desactiva.
        return False


@admin.register(Sucursal)
class SucursalAdmin(RegistroAdmin):
    list_display = ('nombre', 'codigo', 'empresa', 'ciudad', 'activa')
    list_filter = ('empresa', 'activa')
    search_fields = ('nombre', 'codigo')
