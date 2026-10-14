from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from cuentas.models import Perfil


class PerfilEnLinea(admin.StackedInline):
    model = Perfil
    can_delete = False
    fk_name = 'usuario'
    filter_horizontal = ('sucursales',)
    autocomplete_fields = ('empleado',)
    verbose_name_plural = 'perfil (empresa, sucursales y legajo)'


class UsuarioAdmin(UserAdmin):
    """El usuario de Django con su perfil en la misma pantalla. Los perfiles
    (Administrador, Gestor RR. HH., Empleado) se eligen en "Grupos"."""

    inlines = [PerfilEnLinea]
    list_display = ('username', 'first_name', 'last_name', 'empresa', 'perfiles', 'is_active', 'is_superuser')
    list_filter = ('is_active', 'is_superuser', 'groups', 'perfil__empresa')

    @admin.display(description='empresa')
    def empresa(self, obj):
        perfil = getattr(obj, 'perfil', None)
        return perfil.empresa if perfil else '—'

    @admin.display(description='perfiles')
    def perfiles(self, obj):
        return ', '.join(obj.groups.values_list('name', flat=True)) or '—'


admin.site.unregister(User)
admin.site.register(User, UsuarioAdmin)
