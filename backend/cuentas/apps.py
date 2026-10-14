from django.apps import AppConfig, apps
from django.db.models.signals import post_migrate


def crear_perfiles_iniciales(sender, **kwargs):
    """Crea los grupos que falten, con sus permisos iniciales
    (cuentas/perfiles.py). Un grupo que ya existe no se toca: así se
    respetan los ajustes hechos desde el admin."""
    from django.contrib.auth.models import Group
    from . import perfiles
    for nombre, permisos in perfiles.PERMISOS_INICIALES.items():
        grupo, creado = Group.objects.get_or_create(name=nombre)
        if creado:
            perfiles.aplicar(grupo, permisos)


class CuentasConfig(AppConfig):
    name = 'cuentas'
    verbose_name = 'Usuarios y perfiles'

    def ready(self):
        # Se engancha a la señal de la ÚLTIMA app instalada (migracion): Django
        # crea los permisos de cada app en su propia señal, así que recién ahí
        # existen todos los que hay que asignar a los grupos.
        post_migrate.connect(crear_perfiles_iniciales, sender=apps.get_app_config('migracion'))
