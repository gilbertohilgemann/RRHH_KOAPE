"""Preparación de información para MTESS e IPS (fase 11; §4.7).

`PresentacionOficial`: una planilla preparada desde las nóminas cerradas
(planilla mensual de aportes del IPS; planilla anual de sueldos y jornales y
de empleados y obreros del MTESS), con una `LineaPresentacion` por empleado,
cada una validada (qué dato falta o no cuadra). Se exporta a CSV o Excel y se
registra cuándo se presentó y con qué comprobante.

PROPUESTA: las columnas son las de los datos que piden esas planillas, pero
el formato oficial de cada sistema (REI del IPS, planillas del MTESS) tiene
que verificarse antes de usar el archivo para presentar."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import RegistroEmpresa


class PresentacionOficial(RegistroEmpresa):
    IPS_MENSUAL = 'ips_mensual'
    MTESS_SUELDOS = 'mtess_sueldos'
    MTESS_EMPLEADOS = 'mtess_empleados'
    TIPO_OPCIONES = [(IPS_MENSUAL, 'IPS · planilla mensual de aportes'), (MTESS_SUELDOS, 'MTESS · planilla de sueldos y jornales'),
                     (MTESS_EMPLEADOS, 'MTESS · planilla de empleados y obreros')]
    AUTORIDAD = {IPS_MENSUAL: 'IPS', MTESS_SUELDOS: 'MTESS', MTESS_EMPLEADOS: 'MTESS'}
    PREPARADA = 'preparada'
    PRESENTADA = 'presentada'
    RECHAZADA = 'rechazada'
    ANULADA = 'anulada'
    ESTADO_OPCIONES = [(PREPARADA, 'Preparada'), (PRESENTADA, 'Presentada'), (RECHAZADA, 'Rechazada por el organismo'),
                       (ANULADA, 'Anulada')]

    tipo = models.CharField('planilla', max_length=20, choices=TIPO_OPCIONES)
    autoridad = models.CharField('organismo', max_length=10, editable=False)
    periodo_desde = models.DateField('período desde')
    periodo_hasta = models.DateField('período hasta')
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=PREPARADA, editable=False)
    cantidad_lineas = models.PositiveIntegerField('empleados', default=0, editable=False)
    lineas_con_errores = models.PositiveIntegerField('con errores', default=0, editable=False)
    resumen = models.JSONField('totales', default=dict, editable=False)
    preparado_en = models.DateTimeField('preparada el', null=True, blank=True, editable=False)
    presentado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                       editable=False, related_name='+', verbose_name='presentada por')
    presentado_en = models.DateTimeField('presentada el', null=True, blank=True, editable=False)
    numero_comprobante = models.CharField('número de comprobante', max_length=100, blank=True, editable=False)
    observaciones = models.CharField('observaciones o motivo del rechazo', max_length=250, blank=True, editable=False)

    class Meta:
        verbose_name = 'planilla oficial'
        verbose_name_plural = 'planillas MTESS / IPS'
        ordering = ['-periodo_desde', 'tipo']
        permissions = [('preparar_presentacion', 'Puede preparar y exportar planillas MTESS/IPS'),
                       ('confirmar_presentacion', 'Puede registrar la presentación o el rechazo de una planilla')]

    def __str__(self):
        return f'{self.get_tipo_display()} · {self.periodo_desde:%d/%m/%Y} al {self.periodo_hasta:%d/%m/%Y}'

    def clean(self):
        if self.periodo_desde and self.periodo_hasta and self.periodo_hasta < self.periodo_desde:
            raise ValidationError({'periodo_hasta': 'No puede ser anterior a "desde".'})


class LineaPresentacion(models.Model):
    presentacion = models.ForeignKey(PresentacionOficial, on_delete=models.CASCADE, related_name='lineas', verbose_name='planilla')
    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='+', verbose_name='empleado')
    datos = models.JSONField('datos', default=dict)
    valida = models.BooleanField('válida', default=True)
    errores = models.JSONField('errores', default=list)
    advertencias = models.JSONField('advertencias', default=list)

    ruta_empresa = 'presentacion__empresa'
    ruta_sucursal = 'empleado__sucursal'

    class Meta:
        verbose_name = 'línea de planilla'
        verbose_name_plural = 'líneas de planilla'
        ordering = ['presentacion', 'empleado__primer_apellido']
