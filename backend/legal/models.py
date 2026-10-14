"""Reglas legales versionadas (fase 8; §4.5 y §9 de la especificación).

- `ConjuntoReglas`: una versión de un conjunto de parámetros legales (ej.
  "Parámetros laborales de Paraguay" desde el 01/07/2026), con su fuente
  oficial, su vigencia y su estado: borrador → revisado → aprobado → retirado.
  Solo los aprobados valen para liquidar; un borrador sirve para simular, con
  advertencia. Aprobado, no se edita más: un cambio es una versión nueva.
- `ParametroLegal`: cada valor (salario mínimo, recargos, divisores…), con
  unidad, vigencia propia opcional y referencia a la fuente.
- `RegimenSeguridadSocial`: tasas de aporte del trabajador y del empleador
  (ej. IPS general), dentro de un conjunto (se aprueba con él).

Ninguna tasa, mínimo, recargo o base se escribe como constante en el código:
todo se lee de acá con `legal/servicios.py`. Los conjuntos globales los
mantiene la plataforma (Koape); una empresa puede tener los suyos (ej. un
convenio), que tienen prioridad sobre los globales."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from core.models import CatalogoEmpresa

CODIGO_VARIABLE = RegexValidator(r'^[A-Z][A-Z0-9_]*$', 'Solo mayúsculas, números y guion bajo, empezando por una letra (ej. SALARIO_MINIMO).')
CODIGO_REGIMEN = RegexValidator(r'^[A-Z][A-Z0-9_-]*$', 'Solo mayúsculas, números, guion y guion bajo (ej. IPS-GENERAL).')


class ConjuntoReglas(CatalogoEmpresa):
    BORRADOR = 'borrador'
    REVISADO = 'revisado'
    APROBADO = 'aprobado'
    RETIRADO = 'retirado'
    ESTADO_OPCIONES = [(BORRADOR, 'Borrador (sin verificar)'), (REVISADO, 'Revisado'), (APROBADO, 'Aprobado'),
                       (RETIRADO, 'Retirado')]

    codigo = models.CharField('código', max_length=80, help_text='El mismo en todas las versiones (ej. PY-LABORAL).')
    nombre = models.CharField('nombre', max_length=150)
    version = models.PositiveIntegerField('versión', default=1, editable=False)
    version_anterior = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, editable=False,
                                         related_name='versiones_siguientes', verbose_name='versión anterior')
    pais = models.CharField('país', max_length=2, default='PY')
    regimen = models.CharField('régimen', max_length=80, blank=True, help_text='Opcional: régimen o actividad a la que aplica.')
    vigente_desde = models.DateField('vigente desde')
    vigente_hasta = models.DateField('vigente hasta', null=True, blank=True, help_text='Vacío = sin fin.')
    fuente_nombre = models.CharField('fuente', max_length=150, blank=True, help_text='Ej. Decreto del Poder Ejecutivo, Resolución MTESS.')
    fuente_numero = models.CharField('número de la norma', max_length=100, blank=True)
    fuente_url = models.URLField('enlace a la fuente oficial', max_length=500, blank=True)
    publicado_el = models.DateField('publicada el', null=True, blank=True)
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=BORRADOR, editable=False)
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='revisado por')
    revisado_en = models.DateTimeField('revisado el', null=True, blank=True, editable=False)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='aprobado por')
    aprobado_en = models.DateTimeField('aprobado el', null=True, blank=True, editable=False)
    motivo_retiro = models.CharField('motivo del retiro', max_length=250, blank=True, editable=False)
    notas = models.TextField('notas', blank=True)

    class Meta:
        verbose_name = 'conjunto de reglas legales'
        verbose_name_plural = 'reglas legales'
        ordering = ['codigo', '-version']
        constraints = [
            models.UniqueConstraint(fields=['codigo', 'version'], condition=models.Q(empresa__isnull=True),
                                    name='reglas_globales_version_unica'),
            models.UniqueConstraint(fields=['empresa', 'codigo', 'version'], condition=models.Q(empresa__isnull=False),
                                    name='reglas_empresa_version_unica'),
        ]
        permissions = [('revisar_reglas_legales', 'Puede marcar reglas legales como revisadas'),
                       ('aprobar_reglas_legales', 'Puede aprobar o retirar reglas legales')]

    def __str__(self):
        return f'{self.nombre} v{self.version} (desde {self.vigente_desde:%d/%m/%Y})'

    @property
    def editable(self):
        return self.estado == self.BORRADOR

    def vigente_en(self, fecha):
        return self.vigente_desde <= fecha and (self.vigente_hasta is None or fecha <= self.vigente_hasta)

    def clean(self):
        if self.vigente_desde and self.vigente_hasta and self.vigente_hasta < self.vigente_desde:
            raise ValidationError({'vigente_hasta': 'No puede ser anterior a "vigente desde".'})

    def datos_auditoria_extra(self):
        return {'parametros': [f'{p.codigo} = {p.valor_legible()}' for p in self.parametros.all()],
                'regimenes': [str(r) for r in self.regimenes.all()]}


class ParametroLegal(models.Model):
    conjunto = models.ForeignKey(ConjuntoReglas, on_delete=models.CASCADE, related_name='parametros', verbose_name='conjunto')
    codigo = models.CharField('código', max_length=100, validators=[CODIGO_VARIABLE])
    nombre = models.CharField('nombre', max_length=150)
    valor_numerico = models.DecimalField('valor numérico', max_digits=18, decimal_places=6, null=True, blank=True)
    valor_texto = models.CharField('valor de texto', max_length=250, blank=True)
    valor_json = models.JSONField('valor estructurado', null=True, blank=True)
    unidad = models.CharField('unidad', max_length=40, blank=True, help_text='Ej. Gs, %, días, horas.')
    vigente_desde = models.DateField('desde', null=True, blank=True, help_text='Vacío = el del conjunto.')
    vigente_hasta = models.DateField('hasta', null=True, blank=True)
    referencia_fuente = models.CharField('referencia en la fuente', max_length=255, blank=True, help_text='Ej. art. 234.')

    ruta_empresa = 'conjunto__empresa'

    class Meta:
        verbose_name = 'parámetro legal'
        verbose_name_plural = 'parámetros legales'
        ordering = ['codigo', 'vigente_desde']

    def __str__(self):
        return f'{self.codigo} = {self.valor_legible()}'

    def valor(self):
        if self.valor_numerico is not None:
            return self.valor_numerico
        if self.valor_json is not None:
            return self.valor_json
        return self.valor_texto

    def valor_legible(self):
        valor = self.valor()
        if self.valor_numerico is not None:
            valor = f'{self.valor_numerico.normalize():f}'
        return f'{valor} {self.unidad}'.strip()

    def vigente_en(self, fecha):
        return (self.vigente_desde is None or self.vigente_desde <= fecha) and (self.vigente_hasta is None or fecha <= self.vigente_hasta)

    def clean(self):
        if self.valor_numerico is None and not self.valor_texto and self.valor_json is None:
            raise ValidationError({'valor_numerico': 'Indicá el valor (numérico, de texto o estructurado).'})
        if self.vigente_desde and self.vigente_hasta and self.vigente_hasta < self.vigente_desde:
            raise ValidationError({'vigente_hasta': 'No puede ser anterior a "desde".'})


class RegimenSeguridadSocial(models.Model):
    conjunto = models.ForeignKey(ConjuntoReglas, on_delete=models.CASCADE, related_name='regimenes', verbose_name='conjunto')
    codigo = models.CharField('código', max_length=50, validators=[CODIGO_REGIMEN])
    nombre = models.CharField('nombre', max_length=150)
    tasa_trabajador = models.DecimalField('aporte del trabajador (%)', max_digits=7, decimal_places=4)
    tasa_patronal = models.DecimalField('aporte del empleador (%)', max_digits=7, decimal_places=4)
    base = models.CharField('base de cálculo', max_length=250, blank=True, help_text='Qué remuneraciones forman la base.')
    referencia_fuente = models.CharField('referencia en la fuente', max_length=255, blank=True)

    ruta_empresa = 'conjunto__empresa'

    class Meta:
        verbose_name = 'régimen de seguridad social'
        verbose_name_plural = 'regímenes de seguridad social'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.nombre}: trabajador {self.tasa_trabajador.normalize():f} %, empleador {self.tasa_patronal.normalize():f} %'

    def clean(self):
        for campo in ('tasa_trabajador', 'tasa_patronal'):
            valor = getattr(self, campo)
            if valor is not None and not 0 <= valor <= 100:
                raise ValidationError({campo: 'Entre 0 y 100.'})
