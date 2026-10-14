"""Consulta de la auditoría (solo lectura; por defecto, el Administrador)."""
from rest_framework import viewsets

from core.api.base import RegistroSerializer, RegistroViewSet
from core.models import EventoAuditoria


class EventoAuditoriaSerializer(RegistroSerializer):
    class Meta:
        model = EventoAuditoria
        exclude = ['usuario']


class EventoAuditoriaViewSet(RegistroViewSet, viewsets.ReadOnlyModelViewSet):
    serializer_class = EventoAuditoriaSerializer
    search_fields = ['nombre_usuario', 'objeto_texto', 'descripcion', 'modelo']
    filtros_exactos = ('accion', 'modelo', 'objeto_id')
    campo_fecha = 'fecha__date'
    http_method_names = ['get', 'head', 'options']
