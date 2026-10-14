"""API de reportes: `GET /api/reportes/` (los que el usuario puede ver) y
`GET /api/reportes/<clave>/?desde=&hasta=&anio=&dias=&estado=&formato=json|csv|xlsx`.
El perfil Empleado no tiene reportes generales (§11 bis)."""
from datetime import date

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import alcance, auditoria, exportar, reportes
from core.models import EventoAuditoria


def _general(usuario):
    return alcance.es_plataforma(usuario) or alcance.tiene_alcance_empresa(usuario)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def lista(request):
    if not _general(request.user):
        return Response([])
    return Response([{k: r[k] for k in ('clave', 'titulo', 'descripcion', 'filtros')} | {'columnas': [{'campo': c, 'etiqueta': e}
                     for c, e in r['columnas']]} for r in reportes.disponibles(request.user)])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ver(request, clave):
    definicion = reportes.REPORTES.get(clave)
    if definicion is None:
        return Response({'detail': 'Reporte inexistente.'}, status=404)
    if not _general(request.user) or not alcance.tiene_permiso(request.user, definicion['permiso']):
        return Response({'detail': 'No tenés permiso para este reporte.'}, status=403)
    filtros = {}
    for campo in ('desde', 'hasta'):
        valor = request.query_params.get(campo)
        if valor:
            try:
                filtros[campo] = date.fromisoformat(valor)
            except ValueError:
                return Response({campo: 'Fecha inválida (AAAA-MM-DD).'}, status=400)
    for campo in ('anio', 'dias'):
        valor = request.query_params.get(campo)
        if valor:
            if not valor.isdigit():
                return Response({campo: 'Tiene que ser un número.'}, status=400)
            filtros[campo] = int(valor)
    if request.query_params.get('estado'):
        filtros['estado'] = request.query_params['estado']
    filas = definicion['armar'](request.user, filtros)
    formato = request.query_params.get('formato', 'json')
    if formato in ('csv', 'xlsx'):
        auditoria.registrar(request.user, EventoAuditoria.ACCION, None, empresa=alcance.empresa_de(request.user), request=request,
                            descripcion=f'Reporte exportado: {definicion["titulo"]} ({formato}).')
        columnas = definicion['columnas']
        return exportar.respuesta([e for _, e in columnas], [[f.get(c) for c, _ in columnas] for f in filas], formato, clave,
                                  definicion['titulo'])
    return Response({'clave': clave, 'titulo': definicion['titulo'], 'columnas': [{'campo': c, 'etiqueta': e} for c, e in definicion['columnas']],
                     'filas': filas})
