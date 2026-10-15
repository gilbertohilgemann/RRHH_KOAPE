from django.contrib import admin

from core.admin_base import SoloLecturaAdmin
from novedades.models import Anticipo, CuotaRecuperacion, DescuentoAutorizado, Novedad, Prestamo, ReciboAnticipo


@admin.register(ReciboAnticipo)
class ReciboAnticipoAdmin(SoloLecturaAdmin):
    """Se emiten al registrar el pago del anticipo (en la aplicación)."""
    list_display = ('numero', 'empleado', 'fecha_emision', 'monto', 'estado', 'empresa')
    list_filter = ('estado', 'empresa')
    search_fields = ('numero', 'empleado__codigo', 'empleado__primer_apellido')


@admin.register(Novedad)
class NovedadAdmin(SoloLecturaAdmin):
    """Se cargan y se aprueban desde la aplicación."""
    list_display = ('empleado', 'concepto', 'periodo_desde', 'monto', 'estado', 'empresa')
    list_filter = ('estado', 'origen', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido', 'descripcion')


@admin.register(DescuentoAutorizado)
class DescuentoAutorizadoAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'tipo', 'concepto', 'monto_cuota', 'porcentaje', 'fecha_desde', 'estado', 'empresa')
    list_filter = ('estado', 'tipo', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido')


@admin.register(Anticipo)
class AnticipoAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'fecha', 'monto_solicitado', 'monto_aprobado', 'estado', 'empresa')
    list_filter = ('estado', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido', 'motivo')


@admin.register(Prestamo)
class PrestamoAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'fecha', 'capital', 'cantidad_cuotas', 'estado', 'empresa')
    list_filter = ('estado', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido', 'motivo')


@admin.register(CuotaRecuperacion)
class CuotaRecuperacionAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'numero', 'mes', 'monto', 'estado', 'anticipo', 'prestamo', 'empresa')
    list_filter = ('estado', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido')
