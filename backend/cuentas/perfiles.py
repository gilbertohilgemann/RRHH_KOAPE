"""Permisos iniciales de cada perfil (grupo de Django), según la matriz de
la especificación (§11 bis).

Son solo el punto de partida: después se ajustan desde el admin
(Autenticación → Grupos) sin tocar código. Se asignan cuando el grupo se
crea; para volver a estos valores: `manage.py restablecer_perfiles`.

Cada fase nueva define acá sus permisos (`FASE_N`) y suma una migración de
datos que llama a `sumar_en_migracion()`: así las instalaciones que ya
tienen los grupos reciben los permisos de los módulos nuevos sin perder los
ajustes que se hayan hecho desde el admin."""
from core import alcance

# ---------------------------------------------------------------- Fase 1
ESTRUCTURA = ['plataforma.sucursal', 'empleados.departamento', 'empleados.puesto', 'empleados.centrocosto']
LEGAJOS = ['empleados.empleado']
HISTORIALES = ['empleados.historialasignacion']


def _permisos(modelos, *tipos):
    return [f'{modelo.split(".")[0]}.{tipo}_{modelo.split(".")[1]}' for modelo in modelos for tipo in tipos]


FASE_1 = {
    # Todo dentro de su empresa: usuarios y perfiles, sucursales, estructura,
    # alta/edición/baja lógica de empleados, auditoría.
    alcance.GRUPO_ADMINISTRADOR: (
        _permisos(ESTRUCTURA + LEGAJOS, 'view', 'add', 'change')
        + _permisos(HISTORIALES, 'view')
        + ['plataforma.view_empresa', 'plataforma.change_empresa',
           'empleados.dar_baja_empleado', 'empleados.reactivar_empleado',
           'cuentas.gestionar_usuarios', 'core.view_eventoauditoria']
    ),
    # Consulta empleados y estructura. No da de alta ni de baja empleados,
    # usuarios, empresas ni sucursales, ni entra a la configuración.
    alcance.GRUPO_GESTOR: _permisos(ESTRUCTURA + LEGAJOS + HISTORIALES, 'view') + ['plataforma.view_empresa'],
    # Solo lo suyo (core/alcance.py recorta por su legajo).
    alcance.GRUPO_EMPLEADO: _permisos(LEGAJOS + HISTORIALES, 'view'),
}

# ---------------------------------------------------------------- Fase 2
CONTRATOS = ['contratos.contratoempleado', 'contratos.historialsalarial']
CATALOGOS_LEGAJO = ['contratos.esquemasalarial', 'empleados.tipodocumento']
DOCUMENTOS = ['empleados.documentoempleado']
CUENTAS = ['empleados.cuentabancaria']

FASE_2 = {
    # Contratos y sueldos (con su aprobación), documentos (también los
    # confidenciales), cuentas bancarias con el número completo.
    alcance.GRUPO_ADMINISTRADOR: (
        _permisos(CONTRATOS + CATALOGOS_LEGAJO + DOCUMENTOS + CUENTAS, 'view', 'add', 'change')
        + ['contratos.gestionar_estado_contrato', 'contratos.aprobar_salario',
           'empleados.ver_documento_confidencial', 'empleados.anular_documento', 'empleados.ver_cuenta_completa']
    ),
    # Consulta contratos y sueldos; carga documentos (no ve los confidenciales
    # ni los números completos de cuenta: "restringir cuentas bancarias y
    # certificados médicos", §11).
    alcance.GRUPO_GESTOR: (
        _permisos(CONTRATOS + CATALOGOS_LEGAJO + CUENTAS, 'view') + _permisos(DOCUMENTOS, 'view', 'add')
    ),
    # Sus contratos, sus sueldos aprobados, sus documentos y sus cuentas (enmascaradas).
    alcance.GRUPO_EMPLEADO: _permisos(CONTRATOS + DOCUMENTOS + CUENTAS, 'view'),
}

# ---------------------------------------------------------------- Fase 3
CONFIG_JORNADA = ['jornada.regimenjornada', 'jornada.horario', 'jornada.calendarioferiados']
ASIGNACIONES = ['jornada.asignacionhorario']

FASE_3 = {
    # Define regímenes, horarios y feriados (configuración) y asigna horarios.
    alcance.GRUPO_ADMINISTRADOR: _permisos(CONFIG_JORNADA + ASIGNACIONES, 'view', 'add', 'change')
    + _permisos(['jornada.horario'], 'delete'),
    # Consulta la configuración y asigna horarios a los empleados (operativo).
    alcance.GRUPO_GESTOR: _permisos(CONFIG_JORNADA, 'view') + _permisos(ASIGNACIONES, 'view', 'add', 'change'),
    # Su horario (por su asignación) y los feriados.
    alcance.GRUPO_EMPLEADO: _permisos(ASIGNACIONES + ['jornada.calendarioferiados'], 'view'),
}

# ---------------------------------------------------------------- Fase 4
MARCADOR_CONFIG = ['asistencia.configuracionmarcacion', 'asistencia.terminalmarcacion', 'asistencia.credencialmarcacion']
MARCAS = ['asistencia.marcacion', 'asistencia.intentomarcacion', 'asistencia.incidenciaasistencia']

FASE_4 = {
    # Configura el marcador, las terminales (y sus claves) y los códigos fijos; consulta todo.
    alcance.GRUPO_ADMINISTRADOR: (
        _permisos(MARCADOR_CONFIG, 'view', 'add', 'change') + _permisos(MARCAS, 'view')
        + ['asistencia.change_incidenciaasistencia', 'asistencia.ver_codigo_marcacion']
    ),
    # Consulta marcas, intentos e incidencias y resuelve incidencias. No entra a la
    # configuración, las terminales ni los códigos ("credenciales y seguridad", §11 bis).
    alcance.GRUPO_GESTOR: _permisos(MARCAS, 'view') + ['asistencia.change_incidenciaasistencia'],
    # Marca escaneando el QR de la terminal y ve sus marcas e incidencias.
    alcance.GRUPO_EMPLEADO: (
        ['asistencia.marcar_con_qr']
        + _permisos(['asistencia.marcacion', 'asistencia.incidenciaasistencia', 'asistencia.credencialmarcacion'], 'view')
    ),
}

# ---------------------------------------------------------------- Fase 5
IMPORTACION_CONFIG = ['asistencia.relojexterno', 'asistencia.perfilimportacion']
CODIGOS_RELOJ = ['asistencia.mapeoempleadoreloj']
LOTES = ['asistencia.loteimportacion', 'asistencia.filaimportacion']

FASE_5 = {
    # Configura relojes y perfiles, importa, confirma y revierte.
    alcance.GRUPO_ADMINISTRADOR: (
        _permisos(IMPORTACION_CONFIG + CODIGOS_RELOJ, 'view', 'add', 'change') + _permisos(LOTES, 'view')
        + ['asistencia.add_loteimportacion', 'asistencia.confirmar_importacion', 'asistencia.revertir_importacion']
    ),
    # Importa y confirma archivos y corrige los códigos de reloj (§11 bis: "importar CSV y cargar lecturas
    # de horas"); consulta relojes y perfiles; no revierte lotes confirmados.
    alcance.GRUPO_GESTOR: (
        _permisos(IMPORTACION_CONFIG, 'view') + _permisos(CODIGOS_RELOJ, 'view', 'add', 'change') + _permisos(LOTES, 'view')
        + ['asistencia.add_loteimportacion', 'asistencia.confirmar_importacion']
    ),
}

# ---------------------------------------------------------------- Fase 6
DIAS = ['asistencia.diaasistencia']
SOLICITUDES = ['asistencia.ajustemarcacion', 'asistencia.autorizacionhorasextra']

FASE_6 = {
    # Calcula y revisa la asistencia; carga y aprueba ajustes y horas extra.
    alcance.GRUPO_ADMINISTRADOR: (
        _permisos(DIAS, 'view') + _permisos(SOLICITUDES, 'view', 'add')
        + ['asistencia.calcular_asistencia', 'asistencia.revisar_asistencia', 'asistencia.aprobar_ajuste',
           'asistencia.aprobar_horas_extra']
    ),
    # "Cargar/ajustar lecturas de horas o marcaciones" (§11 bis): calcula, revisa, carga y aprueba ajustes;
    # carga horas extra pero no las aprueba ("solo si se concede permiso explícito").
    alcance.GRUPO_GESTOR: (
        _permisos(DIAS, 'view') + _permisos(SOLICITUDES, 'view', 'add')
        + ['asistencia.calcular_asistencia', 'asistencia.revisar_asistencia', 'asistencia.aprobar_ajuste']
    ),
    # Ve su asistencia y pide correcciones de marca (quedan pendientes).
    alcance.GRUPO_EMPLEADO: (
        _permisos(DIAS + SOLICITUDES, 'view') + ['asistencia.add_ajustemarcacion']
    ),
}

# ---------------------------------------------------------------- Fase 7
CATALOGOS_LICENCIA = ['licencias.tipolicencia', 'licencias.escalavacaciones']
LICENCIAS = ['licencias.solicitudlicencia']
VACACIONES = ['licencias.movimientovacaciones']
CERTIFICADOS = ['licencias.certificadomedico']

FASE_7 = {
    # Define los tipos de licencia y la escala; carga, aprueba y cancela licencias; devenga y ajusta vacaciones.
    alcance.GRUPO_ADMINISTRADOR: (
        _permisos(CATALOGOS_LICENCIA + LICENCIAS + CERTIFICADOS, 'view', 'add', 'change')
        + _permisos(VACACIONES, 'view', 'add')
        + ['licencias.aprobar_licencia', 'licencias.devengar_vacaciones']
    ),
    # "Aprobar licencias y vacaciones" (§11 bis): carga y aprueba licencias, carga certificados,
    # devenga y ajusta saldos; consulta los tipos y la escala.
    alcance.GRUPO_GESTOR: (
        _permisos(CATALOGOS_LICENCIA, 'view') + _permisos(LICENCIAS + CERTIFICADOS, 'view', 'add', 'change')
        + _permisos(VACACIONES, 'view', 'add') + ['licencias.aprobar_licencia', 'licencias.devengar_vacaciones']
    ),
    # Pide licencias para sí (quedan pendientes), ve su saldo y sus certificados.
    alcance.GRUPO_EMPLEADO: (
        _permisos(['licencias.tipolicencia'] + VACACIONES + CERTIFICADOS, 'view')
        + _permisos(LICENCIAS, 'view', 'add', 'change')
    ),
}

# ---------------------------------------------------------------- Fase 8
REGLAS_LEGALES = ['legal.conjuntoreglas']
CONCEPTOS = ['nomina.conceptonomina', 'nomina.reglaconcepto']
FIJOS = ['nomina.conceptorecurrente']

FASE_8 = {
    # "Configuración global, seguridad y reglas legales: Sí, con auditoría" (§11 bis): carga, revisa y aprueba
    # reglas legales propias (las globales las mantiene Koape), conceptos, reglas de cálculo y conceptos fijos.
    alcance.GRUPO_ADMINISTRADOR: (
        _permisos(REGLAS_LEGALES + CONCEPTOS + FIJOS, 'view', 'add', 'change')
        + ['legal.revisar_reglas_legales', 'legal.aprobar_reglas_legales', 'nomina.aprobar_regla_concepto',
           'nomina.aprobar_concepto_recurrente']
    ),
    # No entra a "parámetros legales" (§11 bis): solo los consulta. Carga conceptos fijos de empleados
    # (movimientos), pero no los aprueba ni toca el catálogo ni las fórmulas.
    alcance.GRUPO_GESTOR: _permisos(REGLAS_LEGALES + CONCEPTOS, 'view') + _permisos(FIJOS, 'view', 'add', 'change'),
    # Sus conceptos fijos (movimientos personales autorizados).
    alcance.GRUPO_EMPLEADO: _permisos(FIJOS, 'view'),
}

# ---------------------------------------------------------------- Fase 9
MOVIMIENTOS = ['novedades.novedad', 'novedades.descuentoautorizado', 'novedades.anticipo', 'novedades.prestamo']
CUOTAS = ['novedades.cuotarecuperacion']

FASE_9 = {
    # Carga y aprueba novedades, descuentos, anticipos y préstamos; registra pagos y desembolsos.
    alcance.GRUPO_ADMINISTRADOR: (
        _permisos(MOVIMIENTOS, 'view', 'add', 'change') + _permisos(CUOTAS, 'view')
        + ['novedades.aprobar_novedad', 'novedades.aprobar_anticipo', 'novedades.pagar_anticipo',
           'novedades.aprobar_prestamo', 'novedades.desembolsar_prestamo']
    ),
    # "Cargar... bonos, comisiones, descuentos, anticipos, préstamos" (§11 bis); aprobar y pagar, solo con permiso explícito.
    alcance.GRUPO_GESTOR: _permisos(MOVIMIENTOS, 'view', 'add', 'change') + _permisos(CUOTAS, 'view'),
    # Ve sus movimientos y pide anticipos para sí.
    alcance.GRUPO_EMPLEADO: _permisos(MOVIMIENTOS + CUOTAS, 'view') + ['novedades.add_anticipo'],
}

# --------------------------------------------------------------- Fase 10
PERIODOS = ['nomina.periodonomina']
CORRIDAS = ['nomina.corridanomina']
RESULTADOS = ['nomina.liquidacionempleado', 'nomina.recibosueldo', 'nomina.pagonomina']

FASE_10 = {
    # Prepara, calcula, aprueba, cierra, rectifica, paga, emite recibos y ve el costo del empleador.
    alcance.GRUPO_ADMINISTRADOR: (
        _permisos(PERIODOS, 'view', 'add', 'change') + _permisos(CORRIDAS, 'view', 'add') + _permisos(RESULTADOS, 'view')
        + ['nomina.view_asignacioncostopatronal', 'nomina.calcular_nomina', 'nomina.aprobar_nomina', 'nomina.cerrar_nomina',
           'nomina.rectificar_nomina', 'nomina.emitir_recibos', 'nomina.registrar_pagos', 'nomina.ver_costo_patronal']
    ),
    # "Preparar, calcular, revisar y generar liquidaciones… emitir/consultar recibos" (§11 bis). Aprobar, cerrar,
    # pagar y rectificar, "solo si se concede permiso explícito"; tampoco ve el costo del empleador.
    alcance.GRUPO_GESTOR: (
        _permisos(PERIODOS, 'view', 'add', 'change') + _permisos(CORRIDAS, 'view', 'add') + _permisos(RESULTADOS, 'view')
        + ['nomina.calcular_nomina', 'nomina.emitir_recibos']
    ),
    # Sus recibos publicados.
    alcance.GRUPO_EMPLEADO: ['nomina.view_recibosueldo'],
}

# --------------------------------------------------------------- Fase 11
FINALES = ['nomina.liquidacionfinal']
PLANILLAS = ['cumplimiento.presentacionoficial']

FASE_11 = {
    # Liquidaciones finales y planillas MTESS/IPS (prepara, exporta y registra la presentación).
    alcance.GRUPO_ADMINISTRADOR: (
        _permisos(FINALES, 'view', 'add', 'change', 'delete') + _permisos(PLANILLAS, 'view', 'add')
        + ['cumplimiento.preparar_presentacion', 'cumplimiento.confirmar_presentacion']
    ),
    # Prepara liquidaciones finales y planillas ("preparar… liquidación final", §11 bis); no registra la presentación.
    alcance.GRUPO_GESTOR: (
        _permisos(FINALES, 'view', 'add', 'change') + _permisos(PLANILLAS, 'view', 'add') + ['cumplimiento.preparar_presentacion']
    ),
}

FASES = [FASE_1, FASE_2, FASE_3, FASE_4, FASE_5, FASE_6, FASE_7, FASE_8, FASE_9, FASE_10, FASE_11]


def _unir(*fases):
    union = {}
    for fase in fases:
        for grupo, permisos in fase.items():
            union.setdefault(grupo, []).extend(permisos)
    return union


PERMISOS_INICIALES = {alcance.GRUPO_KOAPE: '*', **_unir(*FASES)}


def _buscar(Permission, codigos):
    elegidos = []
    for codigo in codigos:
        app, codename = codigo.split('.')
        elegidos.extend(Permission.objects.filter(content_type__app_label=app, codename=codename))
    return elegidos


def aplicar(grupo, permisos):
    from django.contrib.auth.models import Permission
    if permisos == '*':
        grupo.permissions.set(Permission.objects.all())
        return
    grupo.permissions.set(_buscar(Permission, permisos))


def sumar_en_migracion(apps, fase, *apps_de_la_fase):
    """Para la migración de datos de cada fase: suma (no reemplaza) los
    permisos de la fase a los grupos que ya existen. Los grupos que todavía
    no existen se crean después con todos sus permisos (cuentas/apps.py)."""
    from django.apps import apps as apps_reales
    from django.contrib.auth.management import create_permissions
    # Los permisos de un modelo se crean recién al terminar todas las
    # migraciones: se fuerzan ahora para poder asignarlos.
    for etiqueta in ('core', 'plataforma', 'cuentas', 'empleados', *apps_de_la_fase):
        create_permissions(apps_reales.get_app_config(etiqueta), verbosity=0)
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    for nombre, permisos in fase.items():
        grupo = Group.objects.filter(name=nombre).first()
        if grupo is not None:
            grupo.permissions.add(*_buscar(Permission, permisos))
