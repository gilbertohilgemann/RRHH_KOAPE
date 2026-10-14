from django.contrib import admin

from contratos.models import ContratoEmpleado, EsquemaSalarial, HistorialSalarial
from core.admin_base import RegistroAdmin, SoloLecturaAdmin


@admin.register(EsquemaSalarial)
class EsquemaSalarialAdmin(RegistroAdmin):
    list_display = ('nombre', 'codigo', 'base_calculo', 'frecuencia_pago', 'empresa', 'activo')
    list_filter = ('base_calculo', 'activo', 'empresa')
    search_fields = ('nombre', 'codigo')


@admin.register(ContratoEmpleado)
class ContratoAdmin(SoloLecturaAdmin):
    """Se consultan desde acá; se cargan y cambian de estado desde la aplicación
    (que valida solapamientos y abre el historial salarial)."""
    list_display = ('empleado', 'numero', 'tipo_contrato', 'fecha_inicio', 'fecha_fin', 'salario', 'estado', 'empresa')
    list_filter = ('estado', 'tipo_contrato', 'empresa')
    search_fields = ('numero', 'empleado__codigo', 'empleado__primer_apellido')


@admin.register(HistorialSalarial)
class HistorialSalarialAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'vigente_desde', 'vigente_hasta', 'salario_base', 'estado', 'aprobado_por')
    list_filter = ('estado', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido')
