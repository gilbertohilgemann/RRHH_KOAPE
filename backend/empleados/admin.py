from django.contrib import admin

from core.admin_base import RegistroAdmin, SoloLecturaAdmin
from empleados.models import (CentroCosto, CuentaBancaria, Departamento, DocumentoEmpleado, Empleado,
                              HistorialAsignacion, Puesto, TipoDocumento)


@admin.register(Departamento)
class DepartamentoAdmin(RegistroAdmin):
    list_display = ('nombre', 'codigo', 'empresa', 'departamento_padre', 'activo')
    list_filter = ('empresa', 'activo')
    search_fields = ('nombre', 'codigo')


@admin.register(Puesto)
class PuestoAdmin(RegistroAdmin):
    list_display = ('nombre', 'codigo', 'empresa', 'activo')
    list_filter = ('empresa', 'activo')
    search_fields = ('nombre', 'codigo')


@admin.register(CentroCosto)
class CentroCostoAdmin(RegistroAdmin):
    list_display = ('codigo', 'nombre', 'empresa', 'activo')
    list_filter = ('empresa', 'activo')
    search_fields = ('nombre', 'codigo')


@admin.register(Empleado)
class EmpleadoAdmin(RegistroAdmin):
    list_display = ('codigo', 'nombre_completo', 'numero_documento', 'empresa', 'sucursal', 'estado', 'fecha_ingreso')
    list_filter = ('empresa', 'estado', 'sucursal')
    search_fields = ('codigo', 'numero_documento', 'primer_nombre', 'primer_apellido', 'segundo_apellido')
    readonly_fields = ('estado', 'fecha_egreso', 'motivo_egreso')

    def has_delete_permission(self, request, obj=None):
        # La baja es lógica (desde la aplicación); el legajo nunca se borra.
        return False


@admin.register(TipoDocumento)
class TipoDocumentoAdmin(RegistroAdmin):
    list_display = ('nombre', 'codigo', 'empresa', 'confidencial', 'requiere_vencimiento', 'activo')
    list_filter = ('confidencial', 'activo', 'empresa')
    search_fields = ('nombre', 'codigo')


@admin.register(DocumentoEmpleado)
class DocumentoEmpleadoAdmin(SoloLecturaAdmin):
    """Solo consulta: el archivo es privado y se descarga desde la aplicación (con auditoría)."""
    list_display = ('empleado', 'tipo_documento', 'nombre_original', 'confidencial', 'estado', 'creado')
    list_filter = ('estado', 'confidencial', 'empresa')
    search_fields = ('nombre_original', 'empleado__codigo', 'empleado__primer_apellido')
    exclude = ('archivo',)


@admin.register(CuentaBancaria)
class CuentaBancariaAdmin(SoloLecturaAdmin):
    """El número va cifrado: acá solo se ven los últimos dígitos."""
    list_display = ('empleado', 'banco', 'tipo_cuenta', 'numero_enmascarado', 'principal', 'activa')
    list_filter = ('activa', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido', 'banco')
    exclude = ('numero_cifrado',)


@admin.register(HistorialAsignacion)
class HistorialAsignacionAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'vigente_desde', 'vigente_hasta', 'sucursal', 'departamento', 'puesto')
    list_filter = ('empresa',)
    search_fields = ('empleado__primer_apellido', 'empleado__codigo')
