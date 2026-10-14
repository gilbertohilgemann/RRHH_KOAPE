from django.contrib import admin

from asistencia.models import (AjusteMarcacion, AutorizacionHorasExtra, DiaAsistencia, ConfiguracionMarcacion, CredencialMarcacion, FilaImportacion, IncidenciaAsistencia,
                               IntentoMarcacion, LoteImportacion, MapeoEmpleadoReloj, Marcacion, PerfilImportacion,
                               QRDinamico, RelojExterno, TerminalMarcacion)
from core.admin_base import RegistroAdmin, SoloLecturaAdmin


@admin.register(ConfiguracionMarcacion)
class ConfiguracionMarcacionAdmin(RegistroAdmin):
    list_display = ('empresa', 'permite_qr', 'permite_codigo_fijo', 'permite_csv', 'vigencia_qr_segundos', 'modo_accion')


@admin.register(TerminalMarcacion)
class TerminalAdmin(RegistroAdmin):
    """La clave de cada terminal se genera desde la aplicación (se muestra una sola vez)."""
    list_display = ('nombre', 'codigo', 'empresa', 'sucursal', 'tipo', 'activa', 'ultima_conexion')
    list_filter = ('empresa', 'tipo', 'activa')
    search_fields = ('nombre', 'codigo')
    readonly_fields = ('clave_generada_en', 'ultima_conexion')


@admin.register(CredencialMarcacion)
class CredencialAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'version', 'estado', 'creado', 'revocada_en')
    list_filter = ('estado', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido')
    exclude = ('codigo_huella', 'codigo_cifrado')


@admin.register(QRDinamico)
class QRDinamicoAdmin(SoloLecturaAdmin):
    list_display = ('terminal', 'generado_en', 'vence_en', 'estado', 'usos')
    list_filter = ('estado', 'empresa')
    exclude = ('token_huella',)


@admin.register(Marcacion)
class MarcacionAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'fecha_hora', 'tipo', 'metodo', 'nivel_verificacion', 'terminal', 'empresa')
    list_filter = ('metodo', 'tipo', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido')
    date_hierarchy = 'fecha_hora'


@admin.register(IntentoMarcacion)
class IntentoAdmin(SoloLecturaAdmin):
    list_display = ('fecha_hora', 'terminal', 'metodo', 'codigo_rechazo', 'mensaje', 'empleado')
    list_filter = ('codigo_rechazo', 'empresa')


@admin.register(IncidenciaAsistencia)
class IncidenciaAdmin(RegistroAdmin):
    list_display = ('empleado', 'fecha', 'tipo', 'estado', 'empresa')
    list_filter = ('estado', 'tipo', 'empresa')
    readonly_fields = ('empleado', 'fecha', 'tipo', 'descripcion', 'marcacion')


@admin.register(RelojExterno)
class RelojExternoAdmin(RegistroAdmin):
    list_display = ('nombre', 'codigo', 'empresa', 'fabricante', 'modelo', 'activo')
    list_filter = ('empresa', 'activo')
    search_fields = ('nombre', 'codigo', 'numero_serie')


@admin.register(MapeoEmpleadoReloj)
class MapeoAdmin(RegistroAdmin):
    list_display = ('reloj', 'codigo_en_reloj', 'empleado', 'vigente_desde', 'vigente_hasta')
    list_filter = ('empresa', 'reloj')
    search_fields = ('codigo_en_reloj', 'empleado__codigo', 'empleado__primer_apellido')


@admin.register(PerfilImportacion)
class PerfilImportacionAdmin(RegistroAdmin):
    list_display = ('nombre', 'codigo', 'empresa', 'modo', 'separador', 'codificacion', 'version', 'activo')
    list_filter = ('empresa', 'modo', 'activo')


class FilaEnLinea(admin.TabularInline):
    model = FilaImportacion
    extra = 0
    can_delete = False
    fields = ('numero_fila', 'estado', 'mensaje', 'codigo_en_archivo', 'empleado', 'fecha_hora', 'tipo')
    readonly_fields = fields
    max_num = 0


@admin.register(LoteImportacion)
class LoteImportacionAdmin(SoloLecturaAdmin):
    """Se consultan acá; se importan, confirman y revierten desde la aplicación."""
    list_display = ('pk', 'nombre_archivo', 'empresa', 'estado', 'total_filas', 'aceptadas', 'rechazadas', 'duplicadas', 'creado')
    list_filter = ('estado', 'empresa')
    exclude = ('archivo',)
    inlines = [FilaEnLinea]

@admin.register(DiaAsistencia)
class DiaAsistenciaAdmin(SoloLecturaAdmin):
    """Lo calcula el sistema (asistencia/motor.py): solo consulta."""
    list_display = ('fecha', 'empleado', 'estado', 'minutos_trabajados', 'minutos_tardanza', 'minutos_extra_candidatos',
                    'minutos_extra_autorizados', 'marcas_faltantes')
    list_filter = ('estado', 'empresa')
    search_fields = ('empleado__codigo', 'empleado__primer_apellido')
    date_hierarchy = 'fecha'


@admin.register(AjusteMarcacion)
class AjusteAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'accion', 'fecha_hora', 'estado', 'creado', 'aprobado_por')
    list_filter = ('estado', 'accion', 'empresa')


@admin.register(AutorizacionHorasExtra)
class AutorizacionAdmin(SoloLecturaAdmin):
    list_display = ('empleado', 'fecha', 'minutos_solicitados', 'minutos_aprobados', 'estado', 'aprobado_por')
    list_filter = ('estado', 'empresa')