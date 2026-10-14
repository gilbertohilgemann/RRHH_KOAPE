"""Contratos y salarios (fase 2).

- `EsquemaSalarial`: cómo se calcula el salario (por hora, jornal, mensual,
  comisión...). La frecuencia de pago se guarda aparte de la base (§2).
- `ContratoEmpleado`: borrador → vigente → finalizado (o anulado si nunca
  rigió). Un contrato vigente no se edita: el sueldo cambia con un registro
  nuevo en el historial salarial, y el contrato se cierra con `finalizar`.
- `HistorialSalarial`: cada sueldo con su vigencia. Se carga pendiente y rige
  recién al aprobarse; al aprobar uno nuevo se cierra el anterior el día
  previo. Nunca hay dos vigencias aprobadas solapadas.

Los montos son DECIMAL; las tasas legales (recargos, aportes) no viven acá:
se aplican en la nómina con reglas versionadas (fase 8)."""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from core.models import CatalogoEmpresa, RegistroEmpresa

BASE_HORA = 'hora'
BASE_DIA = 'dia'
BASE_SEMANA = 'semana'
BASE_QUINCENA = 'quincena'
BASE_MES = 'mes'
BASE_COMISION = 'comision'
BASE_DESTAJO = 'destajo'
BASE_MIXTA = 'mixta'
BASE_OPCIONES = [
    (BASE_HORA, 'Por hora'), (BASE_DIA, 'Por día (jornal)'), (BASE_SEMANA, 'Semanal'),
    (BASE_QUINCENA, 'Quincenal'), (BASE_MES, 'Mensual'), (BASE_COMISION, 'Comisión'),
    (BASE_DESTAJO, 'Por pieza o producción (destajo)'), (BASE_MIXTA, 'Mixta'),
]
FRECUENCIA_OPCIONES = [
    ('semanal', 'Semanal'), ('quincenal', 'Quincenal'), ('mensual', 'Mensual'),
]


class EsquemaSalarial(CatalogoEmpresa):
    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=120)
    base_calculo = models.CharField('base de cálculo', max_length=12, choices=BASE_OPCIONES)
    frecuencia_pago = models.CharField('frecuencia de pago habitual', max_length=12, choices=FRECUENCIA_OPCIONES,
                                       default='mensual')
    descripcion = models.TextField('descripción', blank=True)
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'esquema salarial'
        verbose_name_plural = 'esquemas salariales'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='esquema_codigo_unico')]

    def __str__(self):
        return self.nombre


def _validar_empleado(errores, registro):
    empleado = registro.empleado if registro.empleado_id else None
    if empleado is not None and registro.empresa_id and empleado.empresa_id != registro.empresa_id:
        errores['empleado'] = 'Tiene que ser un empleado de la misma empresa.'
    return empleado


def _validar_esquema(errores, registro):
    esquema = registro.esquema_salarial if registro.esquema_salarial_id else None
    if esquema is not None and esquema.empresa_id not in (None, registro.empresa_id):
        errores['esquema_salarial'] = 'El esquema salarial no es de esta empresa.'


def _se_solapan(desde_a, hasta_a, desde_b, hasta_b):
    """Dos vigencias [desde, hasta] (hasta vacío = sin fin) se solapan."""
    return (hasta_b is None or desde_a <= hasta_b) and (hasta_a is None or desde_b <= hasta_a)


class ContratoEmpleado(RegistroEmpresa):
    BORRADOR = 'borrador'
    VIGENTE = 'vigente'
    FINALIZADO = 'finalizado'
    ANULADO = 'anulado'
    ESTADO_OPCIONES = [(BORRADOR, 'Borrador'), (VIGENTE, 'Vigente'), (FINALIZADO, 'Finalizado'), (ANULADO, 'Anulado')]

    TIPO_OPCIONES = [
        ('indefinido', 'Por tiempo indefinido'),
        ('plazo_fijo', 'A plazo fijo'),
        ('obra', 'Por obra o servicio determinado'),
        ('aprendizaje', 'De aprendizaje'),
        ('temporal', 'Temporal o eventual'),
    ]
    # Los que exigen fecha de fin.
    TIPOS_CON_FIN = {'plazo_fijo', 'temporal'}

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='contratos',
                                 verbose_name='empleado')
    numero = models.CharField('número de contrato', max_length=40, blank=True)
    tipo_contrato = models.CharField('tipo de contrato', max_length=15, choices=TIPO_OPCIONES, default='indefinido')
    fecha_inicio = models.DateField('fecha de inicio')
    fecha_fin = models.DateField('fecha de fin', null=True, blank=True,
                                 help_text='Obligatoria en contratos a plazo fijo o temporales.')
    periodo_prueba_dias = models.PositiveSmallIntegerField('período de prueba (días)', null=True, blank=True)
    esquema_salarial = models.ForeignKey(EsquemaSalarial, on_delete=models.PROTECT, related_name='contratos',
                                         verbose_name='esquema salarial')
    frecuencia_pago = models.CharField('frecuencia de pago', max_length=12, choices=FRECUENCIA_OPCIONES, default='mensual')
    salario = models.DecimalField('salario o tarifa inicial', max_digits=18, decimal_places=2,
                                  validators=[MinValueValidator(0)],
                                  help_text='Según el esquema: monto mensual, jornal, tarifa por hora, etc.')
    moneda = models.CharField('moneda', max_length=3, default='PYG')
    estado = models.CharField('estado', max_length=12, choices=ESTADO_OPCIONES, default=BORRADOR, editable=False)
    motivo_finalizacion = models.CharField('motivo de finalización', max_length=250, blank=True, editable=False)
    observaciones = models.TextField('observaciones', blank=True)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'contrato'
        verbose_name_plural = 'contratos'
        ordering = ['-fecha_inicio', '-id']
        constraints = [
            models.UniqueConstraint(fields=['empresa', 'numero'], condition=~models.Q(numero=''),
                                    name='contrato_numero_unico'),
        ]
        permissions = [
            ('gestionar_estado_contrato', 'Puede activar, finalizar o anular contratos'),
        ]

    def __str__(self):
        numero = f'N.º {self.numero} · ' if self.numero else ''
        return f'{numero}{self.get_tipo_contrato_display()} desde {self.fecha_inicio:%d/%m/%Y}'

    def clean(self):
        errores = {}
        empleado = _validar_empleado(errores, self)
        _validar_esquema(errores, self)
        if self.fecha_fin and self.fecha_inicio and self.fecha_fin < self.fecha_inicio:
            errores['fecha_fin'] = 'No puede ser anterior a la fecha de inicio.'
        if self.tipo_contrato in self.TIPOS_CON_FIN and not self.fecha_fin:
            errores['fecha_fin'] = 'Este tipo de contrato necesita fecha de fin.'
        if empleado is not None and self.fecha_inicio and self.fecha_inicio < empleado.fecha_ingreso:
            errores['fecha_inicio'] = 'No puede ser anterior a la fecha de ingreso del empleado.'
        if errores:
            raise ValidationError(errores)

    def contratos_solapados(self):
        """Otros contratos vigentes del mismo empleado que se superponen con este."""
        otros = ContratoEmpleado.objects.filter(empleado_id=self.empleado_id, estado=self.VIGENTE).exclude(pk=self.pk)
        return [c for c in otros if _se_solapan(self.fecha_inicio, self.fecha_fin, c.fecha_inicio, c.fecha_fin)]

    @transaction.atomic
    def activar(self, usuario):
        """Borrador → vigente. Abre el primer registro del historial salarial
        (aprobado) con el salario del contrato."""
        if self.estado != self.BORRADOR:
            raise ValidationError('Solo se activa un contrato en borrador.')
        if self.empleado.estado == self.empleado.BAJA:
            raise ValidationError('El empleado está dado de baja.')
        solapados = self.contratos_solapados()
        if solapados:
            raise ValidationError(f'Se superpone con otro contrato vigente ({solapados[0]}). Finalizalo primero.')
        self.estado = self.VIGENTE
        self.modificado_por = usuario
        self.save(update_fields=['estado', 'modificado_por', 'modificado'])
        sueldo = HistorialSalarial(
            empresa_id=self.empresa_id, empleado_id=self.empleado_id, contrato=self, vigente_desde=self.fecha_inicio,
            esquema_salarial_id=self.esquema_salarial_id, salario_base=self.salario, moneda=self.moneda,
            frecuencia_pago=self.frecuencia_pago, motivo='Salario inicial del contrato',
            creado_por=usuario, modificado_por=usuario,
        )
        sueldo.save()
        sueldo.aprobar(usuario)
        return sueldo

    @transaction.atomic
    def finalizar(self, usuario, fecha, motivo):
        if self.estado != self.VIGENTE:
            raise ValidationError('Solo se finaliza un contrato vigente.')
        if fecha < self.fecha_inicio:
            raise ValidationError({'fecha_fin': 'No puede ser anterior al inicio del contrato.'})
        self.estado = self.FINALIZADO
        self.fecha_fin = fecha
        self.motivo_finalizacion = motivo
        self.modificado_por = usuario
        self.save(update_fields=['estado', 'fecha_fin', 'motivo_finalizacion', 'modificado_por', 'modificado'])
        # El sueldo vigente termina con el contrato; los pendientes ya no rigen.
        self.historial_salarial.filter(estado=HistorialSalarial.APROBADO, vigente_hasta__isnull=True).update(vigente_hasta=fecha)
        self.historial_salarial.filter(estado=HistorialSalarial.APROBADO, vigente_desde__gt=fecha).update(
            estado=HistorialSalarial.ANULADO, motivo_anulacion='El contrato terminó antes de esta vigencia.')
        self.historial_salarial.filter(estado=HistorialSalarial.PENDIENTE).update(
            estado=HistorialSalarial.ANULADO, motivo_anulacion='El contrato fue finalizado.')

    def anular(self, usuario, motivo):
        if self.estado != self.BORRADOR:
            raise ValidationError('Solo se anula un contrato en borrador; uno vigente se finaliza.')
        self.estado = self.ANULADO
        self.motivo_finalizacion = motivo
        self.modificado_por = usuario
        self.save(update_fields=['estado', 'motivo_finalizacion', 'modificado_por', 'modificado'])


class HistorialSalarial(RegistroEmpresa):
    PENDIENTE = 'pendiente'
    APROBADO = 'aprobado'
    ANULADO = 'anulado'
    ESTADO_OPCIONES = [(PENDIENTE, 'Pendiente de aprobación'), (APROBADO, 'Aprobado'), (ANULADO, 'Anulado o rechazado')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='historial_salarial',
                                 verbose_name='empleado')
    contrato = models.ForeignKey(ContratoEmpleado, on_delete=models.PROTECT, related_name='historial_salarial',
                                 verbose_name='contrato')
    vigente_desde = models.DateField('vigente desde')
    vigente_hasta = models.DateField('vigente hasta', null=True, blank=True, editable=False)
    esquema_salarial = models.ForeignKey(EsquemaSalarial, on_delete=models.PROTECT, related_name='+',
                                         verbose_name='esquema salarial')
    salario_base = models.DecimalField('salario base', max_digits=18, decimal_places=2, validators=[MinValueValidator(0)])
    tarifa_hora = models.DecimalField('tarifa por hora', max_digits=18, decimal_places=4, null=True, blank=True,
                                      validators=[MinValueValidator(0)],
                                      help_text='Opcional: si no se carga, la nómina la calcula con las reglas legales vigentes.')
    tarifa_dia = models.DecimalField('jornal (tarifa por día)', max_digits=18, decimal_places=4, null=True, blank=True,
                                     validators=[MinValueValidator(0)])
    moneda = models.CharField('moneda', max_length=3, default='PYG')
    frecuencia_pago = models.CharField('frecuencia de pago', max_length=12, choices=FRECUENCIA_OPCIONES, default='mensual')
    motivo = models.CharField('motivo del cambio', max_length=250)
    estado = models.CharField('estado', max_length=12, choices=ESTADO_OPCIONES, default=PENDIENTE, editable=False)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='aprobado por')
    aprobado_en = models.DateTimeField('aprobado el', null=True, blank=True, editable=False)
    motivo_anulacion = models.CharField('motivo de anulación o rechazo', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'cambio salarial'
        verbose_name_plural = 'historial salarial'
        ordering = ['empleado', '-vigente_desde', '-id']
        permissions = [('aprobar_salario', 'Puede aprobar o rechazar cambios salariales')]

    def __str__(self):
        return f'{self.empleado} · {self.salario_base:,.0f} {self.moneda} desde {self.vigente_desde:%d/%m/%Y}'.replace(',', '.')

    def clean(self):
        errores = {}
        _validar_empleado(errores, self)
        _validar_esquema(errores, self)
        contrato = self.contrato if self.contrato_id else None
        if contrato is not None:
            if contrato.empleado_id != self.empleado_id:
                errores['contrato'] = 'El contrato no es de este empleado.'
            elif contrato.estado != ContratoEmpleado.VIGENTE and self.pk is None:
                errores['contrato'] = 'Solo se cargan cambios salariales en un contrato vigente.'
            elif self.vigente_desde and (self.vigente_desde < contrato.fecha_inicio
                                         or (contrato.fecha_fin and self.vigente_desde > contrato.fecha_fin)):
                errores['vigente_desde'] = 'Tiene que estar dentro de las fechas del contrato.'
        if errores:
            raise ValidationError(errores)

    @transaction.atomic
    def aprobar(self, usuario):
        """Pendiente → aprobado. Cierra la vigencia anterior el día previo.
        No se aprueba un sueldo que empiece antes o el mismo día que el
        vigente (sería un solapamiento): eso se corrige anulando y cargando
        de nuevo."""
        if self.estado != self.PENDIENTE:
            raise ValidationError('Solo se aprueba un cambio pendiente.')
        if self.contrato.estado != ContratoEmpleado.VIGENTE:
            raise ValidationError('El contrato no está vigente.')
        anteriores = HistorialSalarial.objects.select_for_update().filter(
            contrato_id=self.contrato_id, estado=self.APROBADO).exclude(pk=self.pk)
        for anterior in anteriores:
            if anterior.vigente_desde >= self.vigente_desde:
                raise ValidationError(
                    f'Ya hay un sueldo aprobado desde el {anterior.vigente_desde:%d/%m/%Y}: este tiene que empezar después.')
            if anterior.vigente_hasta is None or anterior.vigente_hasta >= self.vigente_desde:
                anterior.vigente_hasta = self.vigente_desde - timedelta(days=1)
                anterior.save(update_fields=['vigente_hasta'])
        self.estado = self.APROBADO
        self.aprobado_por = usuario
        self.aprobado_en = timezone.now()
        self.vigente_hasta = self.contrato.fecha_fin
        self.save(update_fields=['estado', 'aprobado_por', 'aprobado_en', 'vigente_hasta', 'modificado'])

    def anular(self, usuario, motivo):
        """Rechaza un pendiente. Un aprobado no se anula acá: se corrige con
        un cambio nuevo (y si ya entró en una nómina cerrada, con una
        rectificación, fase 10)."""
        if self.estado != self.PENDIENTE:
            raise ValidationError('Solo se rechaza un cambio pendiente; un sueldo aprobado se corrige con un cambio nuevo.')
        self.estado = self.ANULADO
        self.motivo_anulacion = motivo
        self.modificado_por = usuario
        self.save(update_fields=['estado', 'motivo_anulacion', 'modificado_por', 'modificado'])


def sueldo_vigente(empleado, fecha=None):
    """El sueldo aprobado del empleado en una fecha (hoy por defecto), o None."""
    fecha = fecha or timezone.localdate()
    return HistorialSalarial.objects.filter(
        empleado=empleado, estado=HistorialSalarial.APROBADO, vigente_desde__lte=fecha,
    ).filter(models.Q(vigente_hasta__isnull=True) | models.Q(vigente_hasta__gte=fecha)).order_by('-vigente_desde').first()
