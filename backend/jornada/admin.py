from django.contrib import admin

from core.admin_base import RegistroAdmin
from jornada.models import AsignacionHorario, CalendarioFeriados, DiaFeriado, Horario, RegimenJornada, TramoHorario


@admin.register(RegimenJornada)
class RegimenJornadaAdmin(RegistroAdmin):
    list_display = ('nombre', 'codigo', 'tipo_jornada', 'maximo_diario_minutos', 'maximo_semanal_minutos', 'verificado', 'empresa')
    list_filter = ('tipo_jornada', 'verificado', 'empresa')
    search_fields = ('nombre', 'codigo')


class TramoEnLinea(admin.TabularInline):
    model = TramoHorario
    extra = 0


@admin.register(Horario)
class HorarioAdmin(RegistroAdmin):
    list_display = ('nombre', 'codigo', 'empresa', 'regimen', 'activo')
    list_filter = ('empresa', 'activo')
    search_fields = ('nombre', 'codigo')
    inlines = [TramoEnLinea]


@admin.register(AsignacionHorario)
class AsignacionHorarioAdmin(RegistroAdmin):
    list_display = ('empleado', 'horario', 'vigente_desde', 'vigente_hasta', 'empresa')
    list_filter = ('empresa',)
    search_fields = ('empleado__codigo', 'empleado__primer_apellido', 'horario__nombre')


class DiaEnLinea(admin.TabularInline):
    model = DiaFeriado
    extra = 0
    fields = ('fecha', 'nombre', 'tipo')


@admin.register(CalendarioFeriados)
class CalendarioFeriadosAdmin(RegistroAdmin):
    list_display = ('nombre', 'anio', 'empresa', 'verificado', 'activo')
    list_filter = ('anio', 'verificado', 'empresa')
    inlines = [DiaEnLinea]

    def save_formset(self, request, form, formset, change):
        for objeto in formset.save(commit=False):
            if objeto.pk is None:
                objeto.creado_por = request.user
            objeto.modificado_por = request.user
            objeto.save()
        for objeto in formset.deleted_objects:
            objeto.delete()
