from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Perfil(models.Model):
    """A qué empresa pertenece un usuario, a qué sucursales está limitado y,
    si tiene el perfil Empleado, cuál es su legajo. Es la base del
    aislamiento (core/alcance.py). Los superusuarios y el grupo Koape
    (plataforma) no necesitan perfil: ven todo.

    Los perfiles en sí (Administrador, Gestor RR. HH., Empleado) son grupos
    de Django asignados al usuario (cuentas/perfiles.py)."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil', verbose_name='usuario',
    )
    empresa = models.ForeignKey(
        'plataforma.Empresa', on_delete=models.PROTECT, related_name='perfiles', verbose_name='empresa',
    )
    sucursales = models.ManyToManyField(
        'plataforma.Sucursal', blank=True, related_name='perfiles', verbose_name='sucursales',
        help_text='Vacío = todas las sucursales de la empresa.',
    )
    empleado = models.OneToOneField(
        'empleados.Empleado', on_delete=models.PROTECT, null=True, blank=True, related_name='perfil',
        verbose_name='legajo del empleado',
        help_text='Obligatorio para el perfil Empleado: es el único legajo que va a poder ver.',
    )

    ruta_empresa = 'empresa'

    class Meta:
        verbose_name = 'perfil de usuario'
        verbose_name_plural = 'perfiles de usuario'
        permissions = [
            ('gestionar_usuarios', 'Puede crear y editar usuarios de su empresa y asignarles perfiles'),
        ]

    def __str__(self):
        return f'{self.usuario} · {self.empresa}'

    def clean(self):
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            raise ValidationError({'empleado': 'El legajo tiene que ser de la misma empresa que el usuario.'})
