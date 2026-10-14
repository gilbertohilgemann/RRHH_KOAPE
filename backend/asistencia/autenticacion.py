"""Autenticación de las terminales de marcación: no son usuarios. Cada
terminal manda su clave en `Authorization: Terminal <clave>`; la clave se
compara contra su huella (asistencia.models.TerminalMarcacion)."""
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework import authentication, exceptions, permissions


class AutenticacionTerminal(authentication.BaseAuthentication):
    palabra = 'Terminal'

    def authenticate(self, request):
        from asistencia.models import TerminalMarcacion
        partes = authentication.get_authorization_header(request).split()
        if not partes or partes[0].lower() != self.palabra.lower().encode():
            return None
        if len(partes) != 2:
            raise exceptions.AuthenticationFailed('Clave de terminal mal formada.')
        terminal = TerminalMarcacion.autenticar(partes[1].decode(errors='ignore'))
        if terminal is None:
            raise exceptions.AuthenticationFailed('Terminal no autorizada o inactiva.')
        # Última conexión (a lo sumo una escritura por minuto).
        ahora = timezone.now()
        if terminal.ultima_conexion is None or ahora - terminal.ultima_conexion > timedelta(minutes=1):
            TerminalMarcacion.objects.filter(pk=terminal.pk).update(ultima_conexion=ahora)
        return AnonymousUser(), terminal

    def authenticate_header(self, request):
        return self.palabra


class EsTerminal(permissions.BasePermission):
    message = 'Solo una terminal autorizada puede hacer esto.'

    def has_permission(self, request, view):
        from asistencia.models import TerminalMarcacion
        return isinstance(request.auth, TerminalMarcacion)
