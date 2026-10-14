from django.contrib import admin

from core.admin_base import RegistroAdmin, SoloLecturaAdmin
from nomina.models import (AsignacionCostoPatronal, ConceptoNomina, ConceptoRecurrente, CorridaNomina, LiquidacionEmpleado,
                           LiquidacionFinal, PagoNomina, PeriodoNomina, ReciboSueldo, ReglaConcepto, SecuenciaDocumento)


@admin.register(PeriodoNomina)
class PeriodoNominaAdmin(SoloLecturaAdmin):
    list_display = ('codigo', 'tipo', 'fecha_desde', 'fecha_hasta', 'estado', 'empresa')
    list_filter = ('estado', 'tipo', 'empresa')


@admin.register(CorridaNomina)
class CorridaNominaAdmin(SoloLecturaAdmin):
    """Las liquidaciones se calculan, aprueban y cierran desde la aplicación; cerradas, no se modifican nunca."""
    list_display = ('periodo', 'numero', 'tipo', 'estado', 'es_simulacion', 'cantidad_empleados', 'total_neto', 'empresa')
    list_filter = ('estado', 'tipo', 'empresa')


@admin.register(LiquidacionEmpleado)
class LiquidacionEmpleadoAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'corrida', 'bruto', 'neto', 'estado_calculo', 'estado_pago')
    list_filter = ('estado_calculo', 'estado_pago', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido')


@admin.register(ReciboSueldo)
class ReciboSueldoAdmin(SoloLecturaAdmin):
    list_display = ('numero', 'empleado', 'periodo_desde', 'neto', 'publicado', 'estado', 'empresa')
    list_filter = ('estado', 'publicado', 'empresa')
    search_fields = ('numero', 'empleado__codigo', 'empleado__primer_apellido')


@admin.register(PagoNomina)
class PagoNominaAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'fecha', 'monto', 'forma', 'estado', 'empresa')
    list_filter = ('estado', 'forma', 'empresa')


@admin.register(AsignacionCostoPatronal)
class AsignacionCostoPatronalAdmin(SoloLecturaAdmin):
    list_display = ('periodo', 'empleado', 'centro_costo', 'remuneracion_bruta', 'aporte_patronal', 'costo_total', 'empresa')
    list_filter = ('empresa',)


@admin.register(LiquidacionFinal)
class LiquidacionFinalAdmin(SoloLecturaAdmin):
    """Se cargan y se calculan desde la aplicación."""
    list_display = ('empleado', 'fecha_egreso', 'causal', 'preaviso_otorgado', 'corrida', 'empresa')
    list_filter = ('causal', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido')


@admin.register(SecuenciaDocumento)
class SecuenciaDocumentoAdmin(admin.ModelAdmin):
    """Se puede ajustar el prefijo o el próximo número (ej. para continuar la numeración de otro sistema)."""
    list_display = ('empresa', 'tipo', 'anio', 'prefijo', 'siguiente')
    list_filter = ('empresa',)


@admin.register(ConceptoNomina)
class ConceptoNominaAdmin(RegistroAdmin):
    list_display = ('codigo', 'nombre', 'tipo', 'tipo_calculo', 'afecta_neto', 'afecta_base_ips', 'activo', 'empresa')
    list_filter = ('tipo', 'activo', 'empresa')
    search_fields = ('codigo', 'nombre')


@admin.register(ReglaConcepto)
class ReglaConceptoAdmin(RegistroAdmin):
    """Se aprueban y se prueban desde la aplicación."""
    list_display = ('concepto', 'vigente_desde', 'vigente_hasta', 'estado', 'prioridad', 'empresa')
    list_filter = ('estado', 'empresa')
    search_fields = ('concepto__codigo', 'expresion')
    readonly_fields = ('estado', 'aprobado_por', 'aprobado_en')

    def has_change_permission(self, request, obj=None):
        if obj is not None and not obj.editable:
            return False
        return super().has_change_permission(request, obj)


@admin.register(ConceptoRecurrente)
class ConceptoRecurrenteAdmin(RegistroAdmin):
    list_display = ('empleado', 'concepto', 'monto', 'vigente_desde', 'vigente_hasta', 'aprobado_en', 'activo', 'empresa')
    list_filter = ('activo', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido', 'concepto__codigo')
    readonly_fields = ('aprobado_por', 'aprobado_en', 'activo', 'motivo_fin')
