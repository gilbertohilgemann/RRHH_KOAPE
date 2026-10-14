from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from rest_framework.routers import DefaultRouter

from core.api.auditoria import EventoAuditoriaViewSet
from core.api.views import IngresarView, ResumenView, SalirView, YoView
from core.api import reportes as api_reportes
from cumplimiento.api import PresentacionViewSet
from cuentas.api import UsuarioViewSet
from asistencia.api import (ConfiguracionMarcacionView, CredencialViewSet, IncidenciaViewSet, IntentoViewSet,
                            MarcacionViewSet, MarcarQRView, MiCodigoView, MiMarcadorView, TerminalCodigoView,
                            TerminalFotoView, TerminalQRView, TerminalViewSet, TerminalYoView)
from asistencia.api_importacion import (FilaViewSet, ImportacionViewSet, MapeoViewSet, PerfilImportacionViewSet,
                                        RelojExternoViewSet)
from asistencia.api_motor import AjusteViewSet, AutorizacionViewSet, DiaAsistenciaViewSet
from contratos.api import ContratoViewSet, EsquemaSalarialViewSet, HistorialSalarialViewSet
from licencias.api import CertificadoViewSet, EscalaViewSet, MovimientoViewSet, SolicitudViewSet, TipoLicenciaViewSet
from legal.api import ConjuntoViewSet
from nomina.api import ConceptoViewSet, RecurrenteViewSet, ReglaViewSet, variables_nomina
from novedades.api import AnticipoViewSet, CuotaViewSet, DescuentoViewSet, NovedadViewSet, PrestamoViewSet
from nomina.api_liquidacion import (CorridaViewSet, LiquidacionFinalViewSet, LiquidacionViewSet, PagoViewSet, PeriodoViewSet,
                                    ReciboViewSet, costo_patronal)
from empleados.api import (CentroCostoViewSet, CuentaBancariaViewSet, DepartamentoViewSet, DocumentoEmpleadoViewSet,
                           EmpleadoViewSet, PuestoViewSet, TipoDocumentoViewSet)
from jornada.api import AsignacionHorarioViewSet, CalendarioFeriadosViewSet, HorarioViewSet, RegimenJornadaViewSet
from plataforma.api import EmpresaViewSet, SucursalViewSet

router = DefaultRouter()
router.register(r'empresas', EmpresaViewSet, basename='empresa')
router.register(r'sucursales', SucursalViewSet, basename='sucursal')
router.register(r'usuarios', UsuarioViewSet, basename='usuario')
router.register(r'departamentos', DepartamentoViewSet, basename='departamento')
router.register(r'puestos', PuestoViewSet, basename='puesto')
router.register(r'centros-costo', CentroCostoViewSet, basename='centro-costo')
router.register(r'empleados', EmpleadoViewSet, basename='empleado')
router.register(r'auditoria', EventoAuditoriaViewSet, basename='auditoria')
# Fase 2: contratos, salarios, documentos y cuentas bancarias.
router.register(r'esquemas-salariales', EsquemaSalarialViewSet, basename='esquema-salarial')
router.register(r'contratos', ContratoViewSet, basename='contrato')
router.register(r'historial-salarial', HistorialSalarialViewSet, basename='historial-salarial')
router.register(r'tipos-documento', TipoDocumentoViewSet, basename='tipo-documento')
router.register(r'documentos-empleado', DocumentoEmpleadoViewSet, basename='documento-empleado')
router.register(r'cuentas-bancarias', CuentaBancariaViewSet, basename='cuenta-bancaria')
# Fase 3: jornada, horarios y feriados.
router.register(r'regimenes-jornada', RegimenJornadaViewSet, basename='regimen-jornada')
router.register(r'horarios', HorarioViewSet, basename='horario')
router.register(r'asignaciones-horario', AsignacionHorarioViewSet, basename='asignacion-horario')
router.register(r'calendarios-feriados', CalendarioFeriadosViewSet, basename='calendario-feriados')
# Fase 4: marcador propio.
router.register(r'terminales', TerminalViewSet, basename='terminal')
router.register(r'codigos-marcacion', CredencialViewSet, basename='codigo-marcacion')
router.register(r'marcaciones', MarcacionViewSet, basename='marcacion')
router.register(r'intentos-marcacion', IntentoViewSet, basename='intento-marcacion')
router.register(r'incidencias-asistencia', IncidenciaViewSet, basename='incidencia-asistencia')
# Fase 5: importación de marcaciones CSV.
router.register(r'relojes-externos', RelojExternoViewSet, basename='reloj-externo')
router.register(r'codigos-reloj', MapeoViewSet, basename='codigo-reloj')
router.register(r'perfiles-importacion', PerfilImportacionViewSet, basename='perfil-importacion')
router.register(r'importaciones', ImportacionViewSet, basename='importacion')
router.register(r'filas-importacion', FilaViewSet, basename='fila-importacion')
# Fase 6: motor de asistencia.
router.register(r'dias-asistencia', DiaAsistenciaViewSet, basename='dia-asistencia')
router.register(r'ajustes-marcacion', AjusteViewSet, basename='ajuste-marcacion')
router.register(r'autorizaciones-extra', AutorizacionViewSet, basename='autorizacion-extra')
router.register(r'tipos-licencia', TipoLicenciaViewSet, basename='tipo-licencia')
router.register(r'escala-vacaciones', EscalaViewSet, basename='escala-vacaciones')
router.register(r'licencias', SolicitudViewSet, basename='licencia')
router.register(r'movimientos-vacaciones', MovimientoViewSet, basename='movimiento-vacaciones')
router.register(r'certificados-medicos', CertificadoViewSet, basename='certificado-medico')
router.register(r'reglas-legales', ConjuntoViewSet, basename='regla-legal')
router.register(r'conceptos-nomina', ConceptoViewSet, basename='concepto-nomina')
router.register(r'reglas-concepto', ReglaViewSet, basename='regla-concepto')
router.register(r'conceptos-fijos', RecurrenteViewSet, basename='concepto-fijo')
router.register(r'novedades', NovedadViewSet, basename='novedad')
router.register(r'descuentos-autorizados', DescuentoViewSet, basename='descuento-autorizado')
router.register(r'anticipos', AnticipoViewSet, basename='anticipo')
router.register(r'prestamos', PrestamoViewSet, basename='prestamo')
router.register(r'cuotas-recuperacion', CuotaViewSet, basename='cuota-recuperacion')
router.register(r'periodos-nomina', PeriodoViewSet, basename='periodo-nomina')
router.register(r'corridas-nomina', CorridaViewSet, basename='corrida-nomina')
router.register(r'liquidaciones-nomina', LiquidacionViewSet, basename='liquidacion-nomina')
router.register(r'recibos', ReciboViewSet, basename='recibo')
router.register(r'pagos-nomina', PagoViewSet, basename='pago-nomina')
router.register(r'liquidaciones-finales', LiquidacionFinalViewSet, basename='liquidacion-final')
router.register(r'planillas-oficiales', PresentacionViewSet, basename='planilla-oficial')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/sesion/ingresar/', IngresarView.as_view(), name='sesion-ingresar'),
    path('api/sesion/salir/', SalirView.as_view(), name='sesion-salir'),
    path('api/sesion/yo/', YoView.as_view(), name='sesion-yo'),
    path('api/resumen/', ResumenView.as_view(), name='resumen'),
    path('api/reportes/', api_reportes.lista, name='reportes'),
    path('api/reportes/<slug:clave>/', api_reportes.ver, name='reporte'),
    path('api/variables-nomina/', variables_nomina, name='variables-nomina'),
    path('api/costo-patronal/', costo_patronal, name='costo-patronal'),
    # Marcador: el empleado escanea con su sesión el QR que proyecta la terminal (con su clave).
    path('api/marcador/mi-marcador/', MiMarcadorView.as_view(), name='mi-marcador'),
    path('api/marcador/qr/', MarcarQRView.as_view(), name='marcar-qr'),
    path('api/marcador/mi-codigo/', MiCodigoView.as_view(), name='mi-codigo'),
    path('api/marcador/configuracion/', ConfiguracionMarcacionView.as_view(), name='configuracion-marcador'),
    path('api/terminal/yo/', TerminalYoView.as_view(), name='terminal-yo'),
    path('api/terminal/qr/', TerminalQRView.as_view(), name='terminal-qr'),
    path('api/terminal/foto/<int:pk>/', TerminalFotoView.as_view(), name='terminal-foto'),
    path('api/terminal/codigo/', TerminalCodigoView.as_view(), name='terminal-codigo'),
    path('api/', include(router.urls)),
]

# Media pública (logos). Los documentos confidenciales del legajo NO van por
# acá: se entregan por la API con control de permisos (PRIVADO_ROOT).
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
