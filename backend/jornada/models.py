"""Jornada laboral (fase 3): regímenes, horarios con tramos, asignación de
horarios a empleados y calendarios de feriados. Es la base del motor de
asistencia (fase 6): con esto se sabe qué tenía que trabajar cada empleado
cada día.

Los topes legales de jornada (minutos diarios y semanales por régimen) son
DATOS, no constantes: vienen precargados como referencia, marcados "sin
verificar", y se ajustan desde el sistema. Acá solo generan advertencias;
las reglas legales que liquidan (recargos, nocturnidad) van en la fase 8."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from core.models import CatalogoEmpresa, RegistroBase, RegistroEmpresa

DIAS_SEMANA = [(0, 'Lunes'), (1, 'Martes'), (2, 'Miércoles'), (3, 'Jueves'), (4, 'Viernes'), (5, 'Sábado'), (6, 'Domingo')]
DIA_CORTO = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']


class RegimenJornada(CatalogoEmpresa):
    DIURNA = 'diurna'
    NOCTURNA = 'nocturna'
    MIXTA = 'mixta'
    OTRA = 'otra'
    TIPO_OPCIONES = [(DIURNA, 'Diurna'), (NOCTURNA, 'Nocturna'), (MIXTA, 'Mixta'), (OTRA, 'Otra')]

    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=120)
    tipo_jornada = models.CharField('tipo de jornada', max_length=10, choices=TIPO_OPCIONES)
    maximo_diario_minutos = models.PositiveIntegerField('máximo diario (minutos)', null=True, blank=True,
                                                        validators=[MaxValueValidator(24 * 60)])
    maximo_semanal_minutos = models.PositiveIntegerField('máximo semanal (minutos)', null=True, blank=True,
                                                         validators=[MaxValueValidator(7 * 24 * 60)])
    fuente = models.CharField('fuente legal', max_length=250, blank=True,
                              help_text='Norma de la que salen los máximos (ej. Código del Trabajo, art. …).')
    verificado = models.BooleanField('verificado', default=False,
                                     help_text='Marcalo cuando alguien revisó los máximos contra la norma vigente.')
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'régimen de jornada'
        verbose_name_plural = 'regímenes de jornada'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='regimen_codigo_unico')]

    def __str__(self):
        return self.nombre


def minutos_tramo(inicio, fin):
    """Minutos entre dos horas; si el fin es igual o anterior al inicio, el
    tramo termina al día siguiente (cruza la medianoche)."""
    a = inicio.hour * 60 + inicio.minute
    b = fin.hour * 60 + fin.minute
    return b - a if b > a else b + 24 * 60 - a


class Horario(RegistroEmpresa):
    """Horario semanal: uno o varios tramos por día (ej. 08–12 y 13–17)."""

    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=120)
    regimen = models.ForeignKey(RegimenJornada, on_delete=models.PROTECT, related_name='horarios',
                                verbose_name='régimen de jornada')
    tolerancia_minutos = models.PositiveSmallIntegerField(
        'tolerancia de llegada (minutos)', default=0, validators=[MaxValueValidator(120)],
        help_text='Minutos de gracia antes de contar una llegada tarde.',
    )
    descanso_pagado = models.BooleanField(
        'el descanso es pago', default=False,
        help_text='Si se marca, los minutos de descanso de cada tramo cuentan como trabajados.',
    )
    vigente_desde = models.DateField('vigente desde', null=True, blank=True)
    vigente_hasta = models.DateField('vigente hasta', null=True, blank=True)
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'horario'
        verbose_name_plural = 'horarios'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='horario_codigo_unico')]

    def __str__(self):
        return self.nombre

    def clean(self):
        errores = {}
        if self.regimen_id and self.regimen.empresa_id not in (None, self.empresa_id):
            errores['regimen'] = 'El régimen no es de esta empresa.'
        if self.vigente_desde and self.vigente_hasta and self.vigente_hasta < self.vigente_desde:
            errores['vigente_hasta'] = 'No puede ser anterior a "vigente desde".'
        if errores:
            raise ValidationError(errores)

    def datos_auditoria_extra(self):
        """Los tramos van a la auditoría junto con el horario (core/auditoria.py)."""
        return {'tramos': self.resumen()}

    # --- cálculos (los usan la API, el resumen y el motor de asistencia) ---

    def tramos_del_dia(self, dia_semana):
        return [t for t in self.tramos.all() if t.dia_semana == dia_semana and t.laborable]

    def minutos_dia(self, dia_semana):
        return sum(t.minutos_trabajo(self.descanso_pagado) for t in self.tramos_del_dia(dia_semana))

    @property
    def minutos_semana(self):
        return sum(self.minutos_dia(d) for d, _ in DIAS_SEMANA)

    @property
    def cruza_medianoche(self):
        return any(t.cruza_medianoche for t in self.tramos.all())

    def advertencias(self):
        """Avisos visibles (no bloquean): días o semana por encima del máximo del régimen."""
        avisos = []
        regimen = self.regimen
        if regimen.maximo_diario_minutos:
            for dia, nombre in DIAS_SEMANA:
                minutos = self.minutos_dia(dia)
                if minutos > regimen.maximo_diario_minutos:
                    avisos.append(f'{nombre}: {_hhmm(minutos)} h, más que el máximo diario del régimen '
                                  f'({_hhmm(regimen.maximo_diario_minutos)} h).')
        if regimen.maximo_semanal_minutos and self.minutos_semana > regimen.maximo_semanal_minutos:
            avisos.append(f'Semana: {_hhmm(self.minutos_semana)} h, más que el máximo semanal del régimen '
                          f'({_hhmm(regimen.maximo_semanal_minutos)} h).')
        if not regimen.verificado and (regimen.maximo_diario_minutos or regimen.maximo_semanal_minutos):
            avisos.append(f'Los máximos del régimen "{regimen}" todavía no fueron verificados contra la norma vigente.')
        return avisos

    def resumen(self):
        """Texto corto: 'Lun–Vie 08:00–12:00, 13:00–17:00 · Sáb 08:00–12:00'."""
        por_dia = []
        for dia, _ in DIAS_SEMANA:
            tramos = sorted(self.tramos_del_dia(dia), key=lambda t: (t.orden, t.hora_inicio))
            por_dia.append(', '.join(f'{t.hora_inicio:%H:%M}–{t.hora_fin:%H:%M}' for t in tramos))
        partes, i = [], 0
        while i < 7:
            j = i
            while j + 1 < 7 and por_dia[j + 1] == por_dia[i]:
                j += 1
            if por_dia[i]:
                dias = DIA_CORTO[i] if i == j else f'{DIA_CORTO[i]}–{DIA_CORTO[j]}'
                partes.append(f'{dias} {por_dia[i]}')
            i = j + 1
        return ' · '.join(partes) or 'Sin tramos'


def _hhmm(minutos):
    return f'{minutos // 60}:{minutos % 60:02d}'


class TramoHorario(models.Model):
    """Un tramo de trabajo de un día. Si la hora de fin es igual o anterior a
    la de inicio, termina al día siguiente (turno noche)."""

    horario = models.ForeignKey(Horario, on_delete=models.CASCADE, related_name='tramos', verbose_name='horario')
    dia_semana = models.PositiveSmallIntegerField('día', choices=DIAS_SEMANA)
    hora_inicio = models.TimeField('desde')
    hora_fin = models.TimeField('hasta')
    descanso_minutos = models.PositiveSmallIntegerField('descanso (minutos)', default=0,
                                                        validators=[MaxValueValidator(600)])
    laborable = models.BooleanField('laborable', default=True)
    orden = models.PositiveSmallIntegerField('orden', default=1)

    class Meta:
        verbose_name = 'tramo de horario'
        verbose_name_plural = 'tramos de horario'
        ordering = ['dia_semana', 'orden', 'hora_inicio']

    def __str__(self):
        return f'{self.get_dia_semana_display()} {self.hora_inicio:%H:%M}–{self.hora_fin:%H:%M}'

    @property
    def cruza_medianoche(self):
        return self.hora_fin <= self.hora_inicio

    @property
    def minutos_brutos(self):
        return minutos_tramo(self.hora_inicio, self.hora_fin)

    def minutos_trabajo(self, descanso_pagado=False):
        return self.minutos_brutos if descanso_pagado else max(self.minutos_brutos - self.descanso_minutos, 0)

    def clean(self):
        if self.hora_inicio and self.hora_fin and self.descanso_minutos >= self.minutos_brutos:
            raise ValidationError({'descanso_minutos': 'El descanso no puede ser igual o mayor que el tramo.'})

    def intervalo(self):
        """(inicio, fin) en minutos desde el lunes 00:00, para detectar superposiciones."""
        base = self.dia_semana * 24 * 60 + self.hora_inicio.hour * 60 + self.hora_inicio.minute
        return base, base + self.minutos_brutos


def validar_tramos(tramos):
    """Los tramos de un horario no se pueden superponer (tampoco el turno
    noche del domingo con el lunes siguiente). Lanza ValidationError."""
    semana = 7 * 24 * 60
    intervalos = []
    for tramo in tramos:
        if not tramo.laborable:
            continue
        inicio, fin = tramo.intervalo()
        intervalos.append((inicio, fin, tramo))
        if fin > semana:  # el turno del domingo que sigue el lunes
            intervalos.append((inicio - semana, fin - semana, tramo))
    intervalos.sort(key=lambda x: x[0])
    for (a_ini, a_fin, a), (b_ini, b_fin, b) in zip(intervalos, intervalos[1:]):
        if b_ini < a_fin and a is not b:
            raise ValidationError(f'Los tramos {a} y {b} se superponen.')


class AsignacionHorario(RegistroEmpresa):
    """Qué horario tiene un empleado y desde/hasta cuándo. Al asignar uno
    nuevo, el anterior (abierto) se cierra el día previo; nunca hay dos
    asignaciones superpuestas para el mismo empleado."""

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='asignaciones_horario',
                                 verbose_name='empleado')
    horario = models.ForeignKey(Horario, on_delete=models.PROTECT, related_name='asignaciones', verbose_name='horario')
    vigente_desde = models.DateField('vigente desde')
    vigente_hasta = models.DateField('vigente hasta', null=True, blank=True)
    motivo = models.CharField('motivo', max_length=250, blank=True)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'asignación de horario'
        verbose_name_plural = 'asignaciones de horario'
        ordering = ['empleado', '-vigente_desde']

    def __str__(self):
        hasta = f'{self.vigente_hasta:%d/%m/%Y}' if self.vigente_hasta else 'sin fin'
        return f'{self.empleado} · {self.horario} ({self.vigente_desde:%d/%m/%Y} a {hasta})'

    def clean(self):
        errores = {}
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            errores['empleado'] = 'Tiene que ser un empleado de la misma empresa.'
        if self.horario_id and self.empresa_id and self.horario.empresa_id != self.empresa_id:
            errores['horario'] = 'El horario no es de esta empresa.'
        if self.vigente_desde and self.vigente_hasta and self.vigente_hasta < self.vigente_desde:
            errores['vigente_hasta'] = 'No puede ser anterior a "vigente desde".'
        if self.empleado_id and self.vigente_desde and 'empleado' not in errores:
            if self.vigente_desde < self.empleado.fecha_ingreso:
                errores['vigente_desde'] = 'No puede ser anterior a la fecha de ingreso del empleado.'
            for otra in AsignacionHorario.objects.filter(empleado_id=self.empleado_id).exclude(pk=self.pk):
                # La abierta que empieza antes se cierra sola al guardar (ver save()).
                if otra.vigente_hasta is None and otra.vigente_desde < self.vigente_desde:
                    continue
                if (otra.vigente_hasta is None or self.vigente_desde <= otra.vigente_hasta) and \
                        (self.vigente_hasta is None or otra.vigente_desde <= self.vigente_hasta):
                    errores['vigente_desde'] = f'Se superpone con otra asignación: {otra}.'
                    break
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.pk is None:
                AsignacionHorario.objects.filter(
                    empleado_id=self.empleado_id, vigente_hasta__isnull=True, vigente_desde__lt=self.vigente_desde,
                ).update(vigente_hasta=self.vigente_desde - timedelta(days=1))
            super().save(*args, **kwargs)


def horario_vigente(empleado, fecha=None):
    """El horario asignado al empleado en una fecha (hoy por defecto), o None."""
    fecha = fecha or timezone.localdate()
    asignacion = AsignacionHorario.objects.select_related('horario').filter(
        empleado=empleado, vigente_desde__lte=fecha,
    ).filter(models.Q(vigente_hasta__isnull=True) | models.Q(vigente_hasta__gte=fecha)).first()
    return asignacion.horario if asignacion else None


class CalendarioFeriados(CatalogoEmpresa):
    """Calendario de un año. El nacional es global (lo carga la plataforma);
    cada empresa puede sumar los suyos (feriados locales, días de la empresa)."""

    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=120)
    anio = models.PositiveSmallIntegerField('año', validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    verificado = models.BooleanField('verificado', default=False,
                                     help_text='Marcalo cuando las fechas se revisaron contra la ley o el decreto del año '
                                               '(los feriados trasladables cambian cada año).')
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'calendario de feriados'
        verbose_name_plural = 'calendarios de feriados'
        ordering = ['-anio', 'nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo', 'anio'], name='calendario_codigo_unico')]

    def __str__(self):
        return f'{self.nombre} {self.anio}'

    def datos_auditoria_extra(self):
        return {'dias': [f'{d.fecha:%d/%m} {d.nombre}' for d in self.dias.all()]}


class DiaFeriado(RegistroBase):
    NACIONAL = 'nacional'
    TRASLADADO = 'trasladado'
    LOCAL = 'local'
    EMPRESA = 'empresa'
    TIPO_OPCIONES = [(NACIONAL, 'Nacional'), (TRASLADADO, 'Nacional trasladado'), (LOCAL, 'Local'), (EMPRESA, 'De la empresa')]

    calendario = models.ForeignKey(CalendarioFeriados, on_delete=models.CASCADE, related_name='dias',
                                   verbose_name='calendario')
    fecha = models.DateField('fecha')
    nombre = models.CharField('nombre', max_length=150)
    tipo = models.CharField('tipo', max_length=12, choices=TIPO_OPCIONES, default=NACIONAL)

    ruta_empresa = 'calendario__empresa'

    class Meta:
        verbose_name = 'feriado'
        verbose_name_plural = 'feriados'
        ordering = ['fecha']
        constraints = [models.UniqueConstraint(fields=['calendario', 'fecha'], name='feriado_unico_por_calendario')]

    def __str__(self):
        return f'{self.fecha:%d/%m/%Y} · {self.nombre}'

    @classmethod
    def filtrar_por_alcance(cls, queryset, usuario):
        from core import alcance
        empresa = alcance.empresa_de(usuario)
        if empresa is None:
            return queryset.none()
        return queryset.filter(models.Q(calendario__empresa__isnull=True) | models.Q(calendario__empresa=empresa))

    def clean(self):
        if self.calendario_id and self.fecha and self.fecha.year != self.calendario.anio:
            raise ValidationError({'fecha': f'Tiene que ser del año {self.calendario.anio}.'})


def feriado_en(empresa, fecha):
    """El feriado que rige para la empresa en una fecha (de los calendarios
    activos: el global y los de la empresa), o None."""
    return DiaFeriado.objects.filter(
        fecha=fecha, calendario__activo=True,
    ).filter(models.Q(calendario__empresa__isnull=True) | models.Q(calendario__empresa=empresa)).first()
