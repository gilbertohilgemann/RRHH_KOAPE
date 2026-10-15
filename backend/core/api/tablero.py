"""API del tablero: `GET /api/tablero/opciones/` (listas para los filtros) y
`GET /api/tablero/?desde=&hasta=&agrupar=mes|total|departamento|sucursal|centro_costo|empleado
&por_mes=1&departamentos=1,2&sucursales=&centros=&empleados=&formato=json|csv|xlsx`.
Como los reportes, es para Administrador y Gestor (el perfil Empleado no lo ve)."""
from datetime import date

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import alcance, auditoria, exportar, tablero
from core.models import EventoAuditoria

MAXIMO_MESES = 60
COLUMNAS = [('etiqueta', 'Grupo'), ('mes', 'Mes'), ('empleados_liquidados', 'Empleados liquidados'), ('bruto', 'Bruto'),
            ('descuentos', 'Descuentos'), ('aportes_trabajador', 'Aporte IPS del trabajador'), ('neto', 'Neto'),
            ('aportes_patronales', 'Aporte IPS del empleador'), ('costo_empleador', 'Costo del empleador'),
            ('licencias', 'Licencias'), ('dias_licencia', 'Días de licencia'), ('horas_permiso', 'Horas de permiso'),
            ('dias_laborables', 'Días laborables'), ('ausencias', 'Ausencias'), ('minutos_tardanza', 'Minutos de tardanza'),
            ('horas_extra', 'Horas extra autorizadas'), ('dotacion', 'Dotación'), ('altas', 'Altas'), ('bajas', 'Bajas')]


def _general(usuario):
    return alcance.es_plataforma(usuario) or alcance.tiene_alcance_empresa(usuario)


def _ids(valor):
    if not valor:
        return []
    partes = [p for p in valor.split(',') if p]
    if not all(p.isdigit() for p in partes):
        raise ValueError
    return [int(p) for p in partes]


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def opciones(request):
    if not _general(request.user):
        return Response({'detail': 'No tenés acceso al tablero.'}, status=403)
    return Response({'secciones': tablero.secciones(request.user), **tablero.opciones(request.user)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ver(request):
    if not _general(request.user) or not any(tablero.secciones(request.user).values()):
        return Response({'detail': 'No tenés acceso al tablero.'}, status=403)
    hoy = date.today()
    try:
        desde = date.fromisoformat(request.query_params['desde']) if request.query_params.get('desde') else date(hoy.year - 1, hoy.month, 1)
        hasta = date.fromisoformat(request.query_params['hasta']) if request.query_params.get('hasta') else hoy
    except ValueError:
        return Response({'detail': 'Fecha inválida (AAAA-MM-DD).'}, status=400)
    if desde > hasta:
        return Response({'detail': '"Desde" no puede ser posterior a "hasta".'}, status=400)
    if len(tablero.meses_entre(desde, hasta)) > MAXIMO_MESES:
        return Response({'detail': f'El rango puede abarcar como máximo {MAXIMO_MESES} meses.'}, status=400)
    agrupar = request.query_params.get('agrupar', 'mes')
    if agrupar not in tablero.AGRUPACIONES:
        return Response({'detail': 'Agrupación inválida.'}, status=400)
    filtros = {}
    for campo in ('departamentos', 'sucursales', 'centros', 'empleados'):
        try:
            filtros[campo] = _ids(request.query_params.get(campo))
        except ValueError:
            return Response({'detail': f'"{campo}": lista de números separados por coma.'}, status=400)
    datos = tablero.armar(request.user, desde, hasta, agrupar, request.query_params.get('por_mes') == '1', filtros)
    formato = request.query_params.get('formato', 'json')
    if formato in ('csv', 'xlsx'):
        auditoria.registrar(request.user, EventoAuditoria.ACCION, None, empresa=alcance.empresa_de(request.user), request=request,
                            descripcion=f'Tablero exportado ({agrupar}, {desde} a {hasta}, {formato}).')
        presentes = {c for fila in datos['filas'] for c in fila} | {c for fila in datos['filas'] for m in fila.get('meses', []) for c in m}
        columnas = [(c, e) for c, e in COLUMNAS if c in presentes or c == 'etiqueta']
        filas = []
        for fila in datos['filas']:
            for detalle in fila.get('meses') or [fila]:
                filas.append([fila['etiqueta'] if c == 'etiqueta' else detalle.get(c) for c, _ in columnas])
        return exportar.respuesta([e for _, e in columnas], filas, formato, 'tablero', 'Tablero')
    return Response(datos)
