"""Crea (o resetea) el usuario administrador fijo. Lo llaman los
instaladores de Linux y Windows en cada instalación: así nunca se pierde el
acceso al panel, aunque se haya olvidado una contraseña anterior. Es
idempotente — correrlo de nuevo solo confirma el mismo usuario."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from core.alcance import GRUPO_KOAPE

USUARIO_ADMIN = 'admin'
CLAVE_ADMIN = 'Admin*2026'


class Command(BaseCommand):
    help = f'Crea o resetea el usuario administrador fijo ("{USUARIO_ADMIN}").'

    def handle(self, *args, **options):
        User = get_user_model()
        usuario, creado = User.objects.get_or_create(username=USUARIO_ADMIN)
        usuario.is_staff = True
        usuario.is_superuser = True
        usuario.is_active = True
        usuario.set_password(CLAVE_ADMIN)
        usuario.save()
        # Preasignado al grupo Koape (nivel plataforma, puede todo).
        koape, _ = Group.objects.get_or_create(name=GRUPO_KOAPE)
        usuario.groups.add(koape)

        accion = 'creado' if creado else 'reseteado'
        self.stdout.write(self.style.SUCCESS(
            f'Usuario admin {accion} -> usuario: {USUARIO_ADMIN} / contraseña: {CLAVE_ADMIN}'
        ))
        self.stdout.write(self.style.WARNING(
            'Cambiá esta contraseña desde /admin/ apenas entres (es la misma para todas las instalaciones).'
        ))
