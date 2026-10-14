from django.contrib import admin

from core.admin_base import SoloLecturaAdmin
from cumplimiento.models import PresentacionOficial


@admin.register(PresentacionOficial)
class PresentacionOficialAdmin(SoloLecturaAdmin):
    """Se preparan, exportan y registran desde la aplicación."""
    list_display = ('tipo', 'periodo_desde', 'periodo_hasta', 'estado', 'cantidad_lineas', 'lineas_con_errores', 'numero_comprobante', 'empresa')
    list_filter = ('tipo', 'estado', 'empresa')
