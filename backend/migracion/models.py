from django.db import models


class MigracionBaseDatos(models.Model):
    """Modelo sin tabla real: existe solo para que el panel de administración
    tenga una sección 'Migración de Base de Datos' donde correr el traspaso
    de SQLite a PostgreSQL (o viceversa) y descargar el backup."""

    class Meta:
        managed = False
        verbose_name = 'Migración'
        verbose_name_plural = 'Migración'
        default_permissions = ('view',)

    def __str__(self):
        return 'Migración de Base de Datos'


class ManualUsuario(models.Model):
    """Modelo sin tabla real: existe solo para que el panel de administración
    tenga una sección 'Manual de Usuario' con la guía de uso del sistema."""

    class Meta:
        managed = False
        verbose_name = 'Manual del administrador'
        verbose_name_plural = 'Manual del administrador'
        default_permissions = ('view',)

    def __str__(self):
        return 'Manual de Usuario'
