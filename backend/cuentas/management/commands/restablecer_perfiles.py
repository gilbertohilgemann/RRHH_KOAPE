"""Vuelve los permisos de los perfiles a los valores iniciales de
cuentas/perfiles.py (crea los grupos que falten). Los ajustes hechos desde
el admin se pierden: por eso pide confirmación."""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from cuentas import perfiles


class Command(BaseCommand):
    help = 'Restablece los permisos de los perfiles (Administrador, Gestor RR. HH., Empleado, Koape).'

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true', help='Sin esto solo muestra qué haría.')

    def handle(self, *args, **opciones):
        for nombre, permisos in perfiles.PERMISOS_INICIALES.items():
            cantidad = 'todos' if permisos == '*' else len(permisos)
            if not opciones['confirmar']:
                self.stdout.write(f'Se restablecería "{nombre}" ({cantidad} permisos).')
                continue
            grupo, _ = Group.objects.get_or_create(name=nombre)
            perfiles.aplicar(grupo, permisos)
            self.stdout.write(self.style.SUCCESS(f'Perfil "{nombre}" restablecido ({cantidad} permisos).'))
        if not opciones['confirmar']:
            self.stdout.write(self.style.WARNING('Nada cambió. Repetí con --confirmar para aplicarlo.'))
