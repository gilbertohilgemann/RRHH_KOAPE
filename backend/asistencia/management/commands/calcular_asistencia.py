"""Calcula (o recalcula) la asistencia de un período, para todas las empresas
o una. Útil para correrlo cada noche o después de cargar horarios o feriados.

    manage.py calcular_asistencia --desde 2026-10-01 --hasta 2026-10-15 [--empresa <id>]
    manage.py calcular_asistencia --ayer
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from asistencia import motor
from empleados.models import Empleado


class Command(BaseCommand):
    help = 'Calcula los días de asistencia de un período (horas, tardanzas, ausencias, extras, incidencias).'

    def add_arguments(self, parser):
        parser.add_argument('--desde', type=date.fromisoformat)
        parser.add_argument('--hasta', type=date.fromisoformat)
        parser.add_argument('--ayer', action='store_true', help='Solo el día de ayer.')
        parser.add_argument('--empresa', type=int)

    def handle(self, *args, **opciones):
        if opciones['ayer']:
            desde = hasta = timezone.localdate() - timedelta(days=1)
        elif opciones['desde']:
            desde, hasta = opciones['desde'], opciones['hasta'] or opciones['desde']
        else:
            raise CommandError('Indicá --desde (y --hasta) o --ayer.')
        hasta = min(hasta, timezone.localdate())
        empleados = Empleado.objects.select_related('empresa').filter(empresa__activa=True, fecha_ingreso__lte=hasta)
        if opciones['empresa']:
            empleados = empleados.filter(empresa_id=opciones['empresa'])
        dias = sum(len(motor.calcular(empleado, desde, hasta)) for empleado in empleados)
        self.stdout.write(self.style.SUCCESS(f'{dias} días calculados ({empleados.count()} empleados, {desde} a {hasta}).'))
