from django.contrib import admin

from core.admin_base import RegistroAdmin, SoloLecturaAdmin
from licencias.models import CertificadoMedico, EscalaVacaciones, MovimientoVacaciones, SolicitudLicencia, TipoLicencia


@admin.register(TipoLicencia)
class TipoLicenciaAdmin(RegistroAdmin):
    list_display = ('nombre', 'codigo', 'categoria', 'es_paga', 'consume_vacaciones', 'cuenta_dias', 'verificado', 'empresa')
    list_filter = ('categoria', 'verificado', 'empresa')
    search_fields = ('nombre', 'codigo')


@admin.register(EscalaVacaciones)
class EscalaVacacionesAdmin(RegistroAdmin):
    list_display = ('__str__', 'dias', 'verificado', 'empresa')
    list_filter = ('verificado', 'empresa')


@admin.register(SolicitudLicencia)
class SolicitudLicenciaAdmin(SoloLecturaAdmin):
    """Se cargan y se resuelven desde la aplicación (aprobar descuenta el saldo)."""
    list_display = ('empleado', 'tipo', 'fecha_desde', 'fecha_hasta', 'dias', 'estado', 'empresa')
    list_filter = ('estado', 'tipo', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido', 'motivo')


@admin.register(MovimientoVacaciones)
class MovimientoVacacionesAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'fecha', 'tipo', 'dias', 'motivo', 'empresa')
    list_filter = ('tipo', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido', 'motivo')


@admin.register(CertificadoMedico)
class CertificadoMedicoAdmin(RegistroAdmin):
    list_display = ('empleado', 'fecha_desde', 'fecha_hasta', 'emisor', 'estado', 'empresa')
    list_filter = ('estado', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido', 'emisor', 'numero')
