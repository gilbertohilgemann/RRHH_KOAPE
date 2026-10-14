"""Licencias, permisos y vacaciones (fase 7; §4.3).

- `TipoLicencia`: catálogo (globales + de cada empresa). Si es paga, si
  consume vacaciones, si exige documento, días hábiles o corridos, permisos
  por horas, máximo de días. Los globales traen su fuente legal y quedan
  "sin verificar" hasta que alguien los revise (§9).
- `SolicitudLicencia`: pendiente → aprobada / rechazada / cancelada. Al
  aprobarse, si consume vacaciones, descuenta el saldo; el motor de asistencia
  marca esos días como licencia (fase 6).
- `MovimientoVacaciones`: el saldo es la suma de los movimientos (devengo,
  goce, ajuste, vencimiento, corrección). Nunca se editan ni se borran.
- `EscalaVacaciones`: días de vacaciones por antigüedad (dato legal, versionable).
- `CertificadoMedico`: datos del reposo (sin diagnóstico); el archivo es un
  documento confidencial del legajo."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import CatalogoEmpresa, RegistroEmpresa


class TipoLicencia(CatalogoEmpresa):
    CATEGORIA_OPCIONES = [
        ('vacaciones', 'Vacaciones'), ('enfermedad', 'Enfermedad o reposo médico'), ('maternidad', 'Maternidad'),
        ('paternidad', 'Paternidad'), ('duelo', 'Duelo'), ('matrimonio', 'Matrimonio'), ('estudio', 'Estudio o examen'),
        ('particular', 'Permiso particular'), ('otra', 'Otra'),
    ]
    CUENTA_OPCIONES = [('habiles', 'Días hábiles (según el horario del empleado)'), ('corridos', 'Días corridos')]

    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=120)
    categoria = models.CharField('categoría', max_length=12, choices=CATEGORIA_OPCIONES, default='otra')
    es_paga = models.BooleanField('es paga', default=True)
    consume_vacaciones = models.BooleanField('descuenta del saldo de vacaciones', default=False)
    requiere_documento = models.BooleanField('exige un documento (ej. certificado)', default=False)
    cuenta_dias = models.CharField('cómo se cuentan los días', max_length=8, choices=CUENTA_OPCIONES, default='habiles')
    permite_horas = models.BooleanField('admite permisos por horas', default=False,
                                        help_text='Un permiso de unas horas dentro de un mismo día.')
    maximo_dias = models.PositiveSmallIntegerField('máximo de días por solicitud', null=True, blank=True)
    fuente = models.CharField('fuente legal', max_length=250, blank=True)
    verificado = models.BooleanField('verificado', default=False,
                                     help_text='Marcalo cuando alguien revisó el tipo y sus días contra la norma vigente.')
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'tipo de licencia'
        verbose_name_plural = 'tipos de licencia'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='tipo_licencia_codigo_unico')]

    def __str__(self):
        return self.nombre


def contar_dias(empleado, desde, hasta, cuenta):
    """Días de una licencia: corridos, o hábiles según el horario vigente cada
    día (sin feriados). Sin horario asignado, lunes a viernes sin feriados."""
    if cuenta == 'corridos':
        return (hasta - desde).days + 1
    from jornada.models import feriado_en, horario_vigente
    total, fecha = 0, desde
    while fecha <= hasta:
        horario = horario_vigente(empleado, fecha)
        laborable = bool(horario.tramos_del_dia(fecha.weekday())) if horario else fecha.weekday() < 5
        if laborable and not feriado_en(empleado.empresa, fecha):
            total += 1
        fecha += timedelta(days=1)
    return total


class SolicitudLicencia(RegistroEmpresa):
    PENDIENTE = 'pendiente'
    APROBADA = 'aprobada'
    RECHAZADA = 'rechazada'
    CANCELADA = 'cancelada'
    ESTADO_OPCIONES = [(PENDIENTE, 'Pendiente'), (APROBADA, 'Aprobada'), (RECHAZADA, 'Rechazada'), (CANCELADA, 'Cancelada')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='solicitudes_licencia',
                                 verbose_name='empleado')
    tipo = models.ForeignKey(TipoLicencia, on_delete=models.PROTECT, related_name='solicitudes', verbose_name='tipo')
    fecha_desde = models.DateField('desde')
    fecha_hasta = models.DateField('hasta')
    hora_desde = models.TimeField('desde la hora', null=True, blank=True, help_text='Solo para permisos por horas.')
    hora_hasta = models.TimeField('hasta la hora', null=True, blank=True)
    dias = models.DecimalField('días', max_digits=6, decimal_places=1, default=0, editable=False)
    minutos = models.PositiveIntegerField('minutos', default=0, editable=False)
    motivo = models.CharField('motivo', max_length=250, blank=True)
    documento = models.ForeignKey('empleados.DocumentoEmpleado', on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='+', verbose_name='documento de respaldo')
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=PENDIENTE, editable=False)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='resuelta por')
    aprobado_en = models.DateTimeField('resuelta el', null=True, blank=True, editable=False)
    motivo_resolucion = models.CharField('motivo del rechazo o la cancelación', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'solicitud de licencia'
        verbose_name_plural = 'licencias y vacaciones'
        ordering = ['-fecha_desde', '-id']
        permissions = [('aprobar_licencia', 'Puede aprobar, rechazar o cancelar licencias')]

    def __str__(self):
        hasta = '' if self.fecha_hasta == self.fecha_desde else f' al {self.fecha_hasta:%d/%m/%Y}'
        return f'{self.tipo} · {self.empleado} · {self.fecha_desde:%d/%m/%Y}{hasta}'

    @property
    def por_horas(self):
        return self.hora_desde is not None

    def calcular(self):
        """Días u horas que abarca (se guarda con la solicitud)."""
        if self.por_horas:
            self.dias = Decimal('0')
            self.minutos = (self.hora_hasta.hour * 60 + self.hora_hasta.minute) - (self.hora_desde.hour * 60 + self.hora_desde.minute)
        else:
            self.minutos = 0
            self.dias = Decimal(contar_dias(self.empleado, self.fecha_desde, self.fecha_hasta, self.tipo.cuenta_dias))

    def clean(self):
        errores = {}
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            errores['empleado'] = 'Tiene que ser un empleado de la misma empresa.'
        tipo = self.tipo if self.tipo_id else None
        if tipo is not None and tipo.empresa_id not in (None, self.empresa_id):
            errores['tipo'] = 'El tipo de licencia no es de esta empresa.'
        if self.fecha_desde and self.fecha_hasta and self.fecha_hasta < self.fecha_desde:
            errores['fecha_hasta'] = 'No puede ser anterior a "desde".'
        if self.empleado_id and self.fecha_desde and self.fecha_desde < self.empleado.fecha_ingreso:
            errores['fecha_desde'] = 'No puede ser anterior al ingreso del empleado.'
        if (self.hora_desde is None) != (self.hora_hasta is None):
            errores['hora_hasta'] = 'Indicá las dos horas o ninguna.'
        elif self.hora_desde is not None:
            if tipo is not None and not tipo.permite_horas:
                errores['hora_desde'] = 'Este tipo de licencia no admite permisos por horas.'
            if self.fecha_desde != self.fecha_hasta:
                errores['fecha_hasta'] = 'Un permiso por horas es de un solo día.'
            if self.hora_hasta <= self.hora_desde:
                errores['hora_hasta'] = 'Tiene que ser posterior a la hora de inicio.'
        if tipo is not None and tipo.maximo_dias and self.fecha_desde and self.fecha_hasta and not errores \
                and self.empleado_id and self.hora_desde is None:
            if contar_dias(self.empleado, self.fecha_desde, self.fecha_hasta, tipo.cuenta_dias) > tipo.maximo_dias:
                errores['fecha_hasta'] = f'Supera el máximo de {tipo.maximo_dias} días de este tipo de licencia.'
        if self.documento_id and self.empleado_id and self.documento.empleado_id != self.empleado_id:
            errores['documento'] = 'El documento no es de este empleado.'
        if not errores and self.empleado_id and self.fecha_desde and self.fecha_hasta:
            # Dos licencias del mismo empleado no se superponen (salvo permisos por horas distintos del mismo día).
            otras = SolicitudLicencia.objects.filter(
                empleado_id=self.empleado_id, estado__in=(self.PENDIENTE, self.APROBADA),
                fecha_desde__lte=self.fecha_hasta, fecha_hasta__gte=self.fecha_desde).exclude(pk=self.pk)
            for otra in otras:
                if self.por_horas and otra.por_horas and (self.hora_hasta <= otra.hora_desde or otra.hora_hasta <= self.hora_desde):
                    continue
                errores['fecha_desde'] = f'Se superpone con otra licencia: {otra} ({otra.get_estado_display().lower()}).'
                break
        if errores:
            raise ValidationError(errores)


class MovimientoVacaciones(RegistroEmpresa):
    """Movimiento del saldo de vacaciones. Positivo suma, negativo resta."""

    DEVENGO = 'devengo'
    GOCE = 'goce'
    AJUSTE = 'ajuste'
    VENCIMIENTO = 'vencimiento'
    CORRECCION = 'correccion'
    TIPO_OPCIONES = [(DEVENGO, 'Devengo anual'), (GOCE, 'Goce (vacaciones tomadas)'), (AJUSTE, 'Ajuste'),
                     (VENCIMIENTO, 'Vencimiento'), (CORRECCION, 'Corrección')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='movimientos_vacaciones',
                                 verbose_name='empleado')
    fecha = models.DateField('fecha')
    tipo = models.CharField('tipo', max_length=12, choices=TIPO_OPCIONES)
    dias = models.DecimalField('días', max_digits=6, decimal_places=1,
                               help_text='Positivo suma al saldo, negativo resta (ej. -5).')
    periodo = models.PositiveSmallIntegerField('año de antigüedad', null=True, blank=True, editable=False,
                                               help_text='En los devengos: qué aniversario se devengó.')
    solicitud = models.ForeignKey(SolicitudLicencia, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='movimientos_vacaciones', editable=False, verbose_name='solicitud')
    motivo = models.CharField('motivo', max_length=250)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'movimiento de vacaciones'
        verbose_name_plural = 'movimientos de vacaciones'
        ordering = ['empleado', '-fecha', '-id']
        constraints = [models.UniqueConstraint(fields=['empleado', 'periodo'], condition=models.Q(tipo='devengo'),
                                               name='un_devengo_por_aniversario')]
        permissions = [('devengar_vacaciones', 'Puede generar el devengo anual de vacaciones')]

    def __str__(self):
        return f'{self.empleado} · {self.get_tipo_display()} {self.dias:+} días · {self.fecha:%d/%m/%Y}'

    def clean(self):
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            raise ValidationError({'empleado': 'Tiene que ser un empleado de la misma empresa.'})
        if self.dias == 0:
            raise ValidationError({'dias': 'Indicá los días (positivo suma, negativo resta).'})


def saldo_vacaciones(empleado, fecha=None):
    movimientos = MovimientoVacaciones.objects.filter(empleado=empleado)
    if fecha is not None:
        movimientos = movimientos.filter(fecha__lte=fecha)
    return movimientos.aggregate(t=models.Sum('dias'))['t'] or Decimal('0')


class EscalaVacaciones(CatalogoEmpresa):
    """Días de vacaciones por año según la antigüedad. Dato legal: con fuente y
    "sin verificar" hasta que alguien lo revise. Si la empresa carga su propia
    escala, se usa la suya en lugar de la global."""

    desde_anios = models.PositiveSmallIntegerField('desde (años de antigüedad)', validators=[MinValueValidator(1)])
    hasta_anios = models.PositiveSmallIntegerField('hasta (años, sin incluir)', null=True, blank=True)
    dias = models.PositiveSmallIntegerField('días de vacaciones', validators=[MaxValueValidator(60)])
    fuente = models.CharField('fuente legal', max_length=250, blank=True)
    verificado = models.BooleanField('verificado', default=False)

    class Meta:
        verbose_name = 'escala de vacaciones'
        verbose_name_plural = 'escala de vacaciones'
        ordering = ['empresa', 'desde_anios']

    def __str__(self):
        hasta = f'{self.hasta_anios}' if self.hasta_anios else 'más'
        return f'De {self.desde_anios} a {hasta} años: {self.dias} días'

    def clean(self):
        if self.hasta_anios is not None and self.hasta_anios <= self.desde_anios:
            raise ValidationError({'hasta_anios': 'Tiene que ser mayor que "desde".'})

    @classmethod
    def dias_para(cls, empresa, anios):
        """Días que corresponden con esos años de antigüedad (escala propia de la empresa, o la global)."""
        filas = list(cls.objects.filter(empresa=empresa)) or list(cls.objects.filter(empresa__isnull=True))
        for fila in filas:
            if fila.desde_anios <= anios and (fila.hasta_anios is None or anios < fila.hasta_anios):
                return fila.dias, fila
        return 0, None


class CertificadoMedico(RegistroEmpresa):
    """Certificado de reposo: fechas, emisor y número (sin diagnóstico). El
    archivo va como documento confidencial del legajo."""

    RECIBIDO = 'recibido'
    VALIDADO = 'validado'
    RECHAZADO = 'rechazado'
    ESTADO_OPCIONES = [(RECIBIDO, 'Recibido'), (VALIDADO, 'Validado'), (RECHAZADO, 'Rechazado')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='certificados_medicos',
                                 verbose_name='empleado')
    fecha_desde = models.DateField('reposo desde')
    fecha_hasta = models.DateField('reposo hasta')
    emisor = models.CharField('médico o institución', max_length=150)
    numero = models.CharField('número del certificado', max_length=60, blank=True)
    documento = models.ForeignKey('empleados.DocumentoEmpleado', on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='+', verbose_name='archivo (documento confidencial)')
    solicitud = models.ForeignKey(SolicitudLicencia, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='certificados', verbose_name='licencia que respalda')
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=RECIBIDO)
    observaciones = models.CharField('observaciones administrativas', max_length=250, blank=True,
                                     help_text='Nunca el diagnóstico.')

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'certificado médico'
        verbose_name_plural = 'certificados médicos'
        ordering = ['-fecha_desde']

    def __str__(self):
        return f'Certificado de {self.empleado} · {self.fecha_desde:%d/%m/%Y} al {self.fecha_hasta:%d/%m/%Y}'

    def clean(self):
        errores = {}
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            errores['empleado'] = 'Tiene que ser un empleado de la misma empresa.'
        if self.fecha_desde and self.fecha_hasta and self.fecha_hasta < self.fecha_desde:
            errores['fecha_hasta'] = 'No puede ser anterior a "desde".'
        if self.documento_id and self.empleado_id and self.documento.empleado_id != self.empleado_id:
            errores['documento'] = 'El documento no es de este empleado.'
        if self.solicitud_id and self.empleado_id and self.solicitud.empleado_id != self.empleado_id:
            errores['solicitud'] = 'La licencia no es de este empleado.'
        if errores:
            raise ValidationError(errores)
