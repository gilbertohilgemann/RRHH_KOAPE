"""Conceptos salariales y sus reglas de cálculo (fase 8; §4.4).

- `ConceptoNomina`: qué puede aparecer en un recibo (sueldo, horas extra,
  bonos, IPS…), de qué tipo es y a qué bases afecta (neto, aguinaldo,
  vacaciones, IPS, costo patronal). Catálogo global + de cada empresa.
- `ReglaConcepto`: cómo se calcula un concepto en un período de vigencia: una
  condición y una fórmula (`nomina/expresiones.py`, evaluador seguro), con el
  redondeo y el conjunto de reglas legales del que toma los parámetros. Se
  aprueba; aprobada no se edita (un cambio = otra regla con otra vigencia).
- `ConceptoRecurrente`: un concepto fijo de un empleado (ej. un bono mensual,
  una cuota sindical), con vigencia y aprobación.

Liquidación (fase 10; §4.6 y §8):
- `PeriodoNomina` → `CorridaNomina` (calculada → revisada → aprobada → cerrada;
  una rectificación es otra corrida enlazada) → `LiquidacionEmpleado` →
  `LineaNomina` (cada importe con su base, cantidad, tasa, regla, origen y
  explicación, y una copia del concepto para que el recibo histórico no cambie).
- `PagoNomina`, `ReciboSueldo` (numeración con `SecuenciaDocumento`) y
  `AsignacionCostoPatronal` (costo del empleador por centro de costo, al cerrar).
El cálculo está en `nomina/motor.py`; los cambios de estado, en `nomina/liquidar.py`."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import CatalogoEmpresa, RegistroEmpresa
from legal.models import CODIGO_VARIABLE
from nomina import expresiones, redondeo


APLICACION_OPCIONES = [
    ('automatica', 'Automático en cada liquidación (por su regla)'),
    ('novedad', 'Solo por novedades, conceptos fijos o descuentos'),
    ('aguinaldo', 'En la liquidación del aguinaldo'),
    ('liquidacion_final', 'En la liquidación final'),
]


class ConceptoNomina(CatalogoEmpresa):
    HABER = 'haber'
    DESCUENTO = 'descuento'
    APORTE_TRABAJADOR = 'aporte_trabajador'
    APORTE_PATRONAL = 'aporte_patronal'
    INFORMATIVO = 'informativo'
    TIPO_OPCIONES = [(HABER, 'Haber (suma al bruto)'), (DESCUENTO, 'Descuento'),
                     (APORTE_TRABAJADOR, 'Aporte del trabajador'), (APORTE_PATRONAL, 'Aporte del empleador'),
                     (INFORMATIVO, 'Informativo')]
    CALCULO_OPCIONES = [('fijo', 'Monto fijo'), ('cantidad_tasa', 'Cantidad × valor'), ('porcentaje', 'Porcentaje de una base'),
                        ('formula', 'Fórmula'), ('importado', 'Importado (ej. comisiones)'), ('manual', 'Monto cargado a mano')]

    codigo = models.CharField('código', max_length=50, validators=[CODIGO_VARIABLE])
    nombre = models.CharField('nombre', max_length=150)
    tipo = models.CharField('tipo', max_length=20, choices=TIPO_OPCIONES)
    tipo_calculo = models.CharField('cómo se calcula', max_length=15, choices=CALCULO_OPCIONES, default='formula')
    base_por_defecto = models.CharField('base por defecto', max_length=50, blank=True,
                                        help_text='Variable que usa como base (ej. BASE_IPS), si corresponde.')
    tasa_por_defecto = models.DecimalField('tasa por defecto', max_digits=12, decimal_places=6, null=True, blank=True)
    afecta_neto = models.BooleanField('afecta el neto a cobrar', default=True)
    afecta_base_aguinaldo = models.BooleanField('cuenta para el aguinaldo', default=False)
    afecta_base_vacaciones = models.BooleanField('cuenta para las vacaciones', default=False)
    afecta_base_ips = models.BooleanField('cuenta para la base de IPS', default=False)
    afecta_costo_patronal = models.BooleanField('suma al costo del empleador', default=False)
    imponible = models.BooleanField('imponible', default=False)
    recurrente = models.BooleanField('se repite cada período', default=False)
    requiere_aprobacion = models.BooleanField('requiere aprobación', default=False)
    requiere_comprobante = models.BooleanField('requiere comprobante', default=False)
    orden = models.PositiveSmallIntegerField('orden en el recibo', default=100)
    aplicacion = models.CharField('cuándo se aplica', max_length=20, choices=APLICACION_OPCIONES, default='novedad',
                                  help_text='Automático: la nómina lo calcula con su regla en cada liquidación.')
    activo = models.BooleanField('activo', default=True)
    descripcion = models.TextField('descripción', blank=True)

    class Meta:
        verbose_name = 'concepto de nómina'
        verbose_name_plural = 'conceptos de nómina'
        ordering = ['orden', 'codigo']
        constraints = [
            models.UniqueConstraint(fields=['codigo'], condition=models.Q(empresa__isnull=True), name='concepto_global_codigo_unico'),
            models.UniqueConstraint(fields=['empresa', 'codigo'], condition=models.Q(empresa__isnull=False),
                                    name='concepto_empresa_codigo_unico'),
        ]

    def __str__(self):
        return f'{self.codigo} · {self.nombre}'

    def clean(self):
        errores = {}
        if self.tipo == self.APORTE_PATRONAL:
            # §4.6 y §8: el aporte patronal nunca se descuenta del neto del trabajador.
            if self.afecta_neto:
                errores['afecta_neto'] = 'Un aporte del empleador nunca afecta el neto del trabajador.'
            if not self.afecta_costo_patronal:
                errores['afecta_costo_patronal'] = 'Un aporte del empleador suma al costo del empleador.'
        if self.tipo == self.INFORMATIVO and self.afecta_neto:
            errores['afecta_neto'] = 'Un concepto informativo no afecta el neto.'
        if self.tipo != self.HABER and (self.afecta_base_aguinaldo or self.afecta_base_vacaciones or self.afecta_base_ips):
            errores['tipo'] = 'Solo un haber cuenta para las bases de aguinaldo, vacaciones o IPS.'
        if errores:
            raise ValidationError(errores)


class ReglaConcepto(CatalogoEmpresa):
    BORRADOR = 'borrador'
    APROBADA = 'aprobada'
    RETIRADA = 'retirada'
    ESTADO_OPCIONES = [(BORRADOR, 'Borrador'), (APROBADA, 'Aprobada'), (RETIRADA, 'Retirada')]

    concepto = models.ForeignKey(ConceptoNomina, on_delete=models.PROTECT, related_name='reglas', verbose_name='concepto')
    conjunto_legal = models.ForeignKey('legal.ConjuntoReglas', on_delete=models.PROTECT, null=True, blank=True,
                                       related_name='reglas_concepto', verbose_name='reglas legales',
                                       help_text='De dónde toma los parámetros legales (vacío = los vigentes en la fecha).')
    vigente_desde = models.DateField('vigente desde')
    vigente_hasta = models.DateField('vigente hasta', null=True, blank=True)
    condicion = models.TextField('condición', blank=True,
                                 help_text='Opcional: cuándo se aplica (ej. HORAS_EXTRA_DIURNAS > 0). Vacía = siempre.')
    expresion = models.TextField('fórmula', help_text='Ej. VALOR_HORA * HORAS_EXTRA_DIURNAS * (1 + RECARGO_EXTRA_DIURNA / 100)')
    redondeo = models.CharField('redondeo', max_length=15, choices=redondeo.MODOS, default=redondeo.ENTERO)
    prioridad = models.PositiveSmallIntegerField('prioridad', default=100, help_text='Menor = se calcula antes.')
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=BORRADOR, editable=False)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='aprobada por')
    aprobado_en = models.DateTimeField('aprobada el', null=True, blank=True, editable=False)
    notas = models.TextField('notas', blank=True)

    class Meta:
        verbose_name = 'regla de cálculo'
        verbose_name_plural = 'reglas de cálculo'
        ordering = ['concepto__orden', 'concepto__codigo', 'prioridad', '-vigente_desde']
        permissions = [('aprobar_regla_concepto', 'Puede aprobar o retirar reglas de cálculo')]

    def __str__(self):
        return f'{self.concepto.codigo} desde {self.vigente_desde:%d/%m/%Y}'

    @property
    def editable(self):
        return self.estado == self.BORRADOR

    def variables(self):
        """Variables que usan la condición y la fórmula."""
        usadas = expresiones.analizar(self.expresion)[1]
        if self.condicion.strip():
            usadas |= expresiones.analizar(self.condicion)[1]
        return usadas

    def calcular(self, variables):
        """(importe redondeado, o None si la condición no se cumple)."""
        if self.condicion.strip() and not expresiones.evaluar(self.condicion, variables):
            return None
        valor = expresiones.evaluar(self.expresion, variables)
        if isinstance(valor, bool):
            raise expresiones.ErrorFormula('La fórmula tiene que dar un importe, no verdadero/falso.')
        return redondeo.redondear(valor, self.redondeo)

    def clean(self):
        errores = {}
        for campo in ('expresion', 'condicion'):
            texto = getattr(self, campo)
            if campo == 'condicion' and not texto.strip():
                continue
            try:
                expresiones.analizar(texto)
            except expresiones.ErrorFormula as e:
                errores[campo] = str(e)
        if self.vigente_desde and self.vigente_hasta and self.vigente_hasta < self.vigente_desde:
            errores['vigente_hasta'] = 'No puede ser anterior a "vigente desde".'
        if self.concepto_id and self.concepto.empresa_id not in (None, self.empresa_id):
            errores['concepto'] = 'El concepto no es de esta empresa.'
        if self.conjunto_legal_id and self.conjunto_legal.empresa_id not in (None, self.empresa_id):
            errores['conjunto_legal'] = 'Las reglas legales no son de esta empresa.'
        if errores:
            raise ValidationError(errores)


class ConceptoRecurrente(RegistroEmpresa):
    """Concepto fijo de un empleado (§4.4 RecurringEmployeeConcept)."""

    FRECUENCIA_OPCIONES = [('cada_pago', 'En cada liquidación'), ('mensual', 'Una vez por mes')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='conceptos_recurrentes',
                                 verbose_name='empleado')
    concepto = models.ForeignKey(ConceptoNomina, on_delete=models.PROTECT, related_name='recurrentes', verbose_name='concepto')
    monto = models.DecimalField('monto', max_digits=14, decimal_places=2, null=True, blank=True)
    tasa = models.DecimalField('tasa o valor unitario', max_digits=12, decimal_places=6, null=True, blank=True)
    cantidad = models.DecimalField('cantidad', max_digits=10, decimal_places=2, null=True, blank=True)
    vigente_desde = models.DateField('vigente desde')
    vigente_hasta = models.DateField('vigente hasta', null=True, blank=True, help_text='Vacío = sin fin.')
    frecuencia = models.CharField('frecuencia', max_length=10, choices=FRECUENCIA_OPCIONES, default='cada_pago')
    centro_costo = models.ForeignKey('empleados.CentroCosto', on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+', verbose_name='centro de costo', help_text='Vacío = el del empleado.')
    documento = models.ForeignKey('empleados.DocumentoEmpleado', on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='+', verbose_name='comprobante o autorización')
    motivo = models.CharField('motivo', max_length=250)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='aprobado por')
    aprobado_en = models.DateTimeField('aprobado el', null=True, blank=True, editable=False)
    activo = models.BooleanField('activo', default=True, editable=False)
    motivo_fin = models.CharField('motivo de la finalización', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'concepto fijo de un empleado'
        verbose_name_plural = 'conceptos fijos por empleado'
        ordering = ['empleado', 'concepto__orden', '-vigente_desde']
        permissions = [('aprobar_concepto_recurrente', 'Puede aprobar conceptos fijos de empleados')]

    def __str__(self):
        return f'{self.concepto.codigo} · {self.empleado}'

    @property
    def aprobado(self):
        return self.aprobado_en is not None

    def clean(self):
        errores = {}
        concepto = self.concepto if self.concepto_id else None
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            errores['empleado'] = 'Tiene que ser un empleado de la misma empresa.'
        if concepto is not None:
            if concepto.empresa_id not in (None, self.empresa_id):
                errores['concepto'] = 'El concepto no es de esta empresa.'
            elif concepto.tipo not in (ConceptoNomina.HABER, ConceptoNomina.DESCUENTO):
                errores['concepto'] = 'Solo haberes o descuentos (los aportes los calcula la nómina).'
            elif not concepto.activo:
                errores['concepto'] = 'El concepto está inactivo.'
            elif concepto.tipo_calculo == 'fijo' and self.monto is None:
                errores['monto'] = 'Este concepto es de monto fijo: indicá el monto.'
            elif concepto.tipo_calculo == 'cantidad_tasa' and (self.cantidad is None or self.tasa is None):
                errores['cantidad'] = 'Indicá la cantidad y el valor unitario.'
            elif concepto.tipo_calculo == 'porcentaje' and self.tasa is None and concepto.tasa_por_defecto is None:
                errores['tasa'] = 'Indicá el porcentaje.'
            if concepto.requiere_comprobante and not self.documento_id:
                errores['documento'] = 'Este concepto exige un comprobante o autorización del legajo.'
        for campo in ('monto', 'tasa', 'cantidad'):
            valor = getattr(self, campo)
            if valor is not None and valor < 0:
                errores[campo] = 'No puede ser negativo (el tipo del concepto ya dice si suma o resta).'
        if self.vigente_desde and self.vigente_hasta and self.vigente_hasta < self.vigente_desde:
            errores['vigente_hasta'] = 'No puede ser anterior a "vigente desde".'
        if self.empleado_id and self.vigente_desde and self.vigente_desde < self.empleado.fecha_ingreso:
            errores['vigente_desde'] = 'No puede ser anterior al ingreso del empleado.'
        if self.documento_id and self.empleado_id and self.documento.empleado_id != self.empleado_id:
            errores['documento'] = 'El documento no es de este empleado.'
        if self.centro_costo_id and self.empresa_id and self.centro_costo.empresa_id != self.empresa_id:
            errores['centro_costo'] = 'El centro de costo no es de esta empresa.'
        if errores:
            raise ValidationError(errores)


# ======================================================================= liquidación (fase 10)
class PeriodoNomina(RegistroEmpresa):
    ABIERTO = 'abierto'
    CERRADO = 'cerrado'
    ESTADO_OPCIONES = [(ABIERTO, 'Abierto'), (CERRADO, 'Cerrado')]
    TIPO_OPCIONES = [('mensual', 'Mensual'), ('quincenal', 'Quincenal'), ('semanal', 'Semanal'), ('especial', 'Especial')]

    codigo = models.CharField('código', max_length=30, help_text='Ej. 2026-10.')
    tipo = models.CharField('tipo', max_length=10, choices=TIPO_OPCIONES, default='mensual')
    fecha_desde = models.DateField('desde')
    fecha_hasta = models.DateField('hasta')
    fecha_pago = models.DateField('fecha de pago', null=True, blank=True)
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=ABIERTO, editable=False)
    cerrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    editable=False, related_name='+', verbose_name='cerrado por')
    cerrado_en = models.DateTimeField('cerrado el', null=True, blank=True, editable=False)

    class Meta:
        verbose_name = 'período de nómina'
        verbose_name_plural = 'períodos de nómina'
        ordering = ['-fecha_desde']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='periodo_codigo_unico')]

    def __str__(self):
        return f'{self.codigo} ({self.fecha_desde:%d/%m/%Y} al {self.fecha_hasta:%d/%m/%Y})'

    def clean(self):
        errores = {}
        if self.fecha_desde and self.fecha_hasta:
            if self.fecha_hasta < self.fecha_desde:
                errores['fecha_hasta'] = 'No puede ser anterior a "desde".'
            elif self.tipo != 'especial' and (self.fecha_hasta - self.fecha_desde).days > 31:
                errores['fecha_hasta'] = 'Un período de nómina no puede pasar de un mes (salvo los especiales: aguinaldo, liquidación final).'
            elif self.empresa_id and self.tipo != 'especial':
                otros = PeriodoNomina.objects.filter(empresa_id=self.empresa_id, tipo=self.tipo, fecha_desde__lte=self.fecha_hasta,
                                                     fecha_hasta__gte=self.fecha_desde).exclude(pk=self.pk)
                if otros.exists():
                    errores['fecha_desde'] = f'Se superpone con el período {otros.first()}.'
        if self.fecha_pago and self.fecha_desde and self.fecha_pago < self.fecha_desde:
            errores['fecha_pago'] = 'No puede ser anterior al inicio del período.'
        if errores:
            raise ValidationError(errores)


class CorridaNomina(RegistroEmpresa):
    CALCULADA = 'calculada'
    REVISADA = 'revisada'
    APROBADA = 'aprobada'
    CERRADA = 'cerrada'
    ANULADA = 'anulada'
    ESTADO_OPCIONES = [(CALCULADA, 'Calculada (borrador)'), (REVISADA, 'Revisada'), (APROBADA, 'Aprobada'),
                       (CERRADA, 'Cerrada'), (ANULADA, 'Anulada')]
    REGULAR = 'regular'
    RECTIFICACION = 'rectificacion'
    TIPO_OPCIONES = [(REGULAR, 'Regular'), (RECTIFICACION, 'Rectificación'), ('aguinaldo', 'Aguinaldo'),
                     ('liquidacion_final', 'Liquidación final')]

    periodo = models.ForeignKey(PeriodoNomina, on_delete=models.PROTECT, related_name='corridas', verbose_name='período')
    numero = models.PositiveSmallIntegerField('número', editable=False)
    tipo = models.CharField('tipo', max_length=20, choices=TIPO_OPCIONES, default=REGULAR, editable=False)
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=CALCULADA, editable=False)
    es_simulacion = models.BooleanField('simulación (usa reglas sin aprobar)', default=False, editable=False)
    version_calculo = models.PositiveIntegerField('cálculo n.º', default=0, editable=False)
    corrida_origen = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, editable=False,
                                       related_name='rectificaciones', verbose_name='rectifica a')
    motivo_rectificacion = models.CharField('motivo de la rectificación o la anulación', max_length=250, blank=True, editable=False)
    rectificada = models.BooleanField('rectificada por otra corrida', default=False, editable=False)
    cantidad_empleados = models.PositiveIntegerField('empleados', default=0, editable=False)
    total_bruto = models.DecimalField('total bruto', max_digits=18, decimal_places=2, default=0, editable=False)
    total_descuentos = models.DecimalField('total descuentos', max_digits=18, decimal_places=2, default=0, editable=False)
    total_aportes_trabajador = models.DecimalField('aportes del trabajador', max_digits=18, decimal_places=2, default=0, editable=False)
    total_neto = models.DecimalField('total neto', max_digits=18, decimal_places=2, default=0, editable=False)
    total_aportes_patronales = models.DecimalField('aportes del empleador', max_digits=18, decimal_places=2, default=0, editable=False)
    total_otros_costos = models.DecimalField('otros costos del empleador', max_digits=18, decimal_places=2, default=0, editable=False)
    total_costo_empleador = models.DecimalField('costo total del empleador', max_digits=18, decimal_places=2, default=0, editable=False)
    advertencias = models.JSONField('advertencias', default=list, editable=False)
    calculado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      editable=False, related_name='+', verbose_name='calculada por')
    calculado_en = models.DateTimeField('calculada el', null=True, blank=True, editable=False)
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='revisada por')
    revisado_en = models.DateTimeField('revisada el', null=True, blank=True, editable=False)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='aprobada por')
    aprobado_en = models.DateTimeField('aprobada el', null=True, blank=True, editable=False)
    cerrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    editable=False, related_name='+', verbose_name='cerrada por')
    cerrado_en = models.DateTimeField('cerrada el', null=True, blank=True, editable=False)

    class Meta:
        verbose_name = 'liquidación de nómina'
        verbose_name_plural = 'liquidaciones de nómina'
        ordering = ['-periodo__fecha_desde', '-numero']
        constraints = [models.UniqueConstraint(fields=['empresa', 'periodo', 'numero'], name='corrida_numero_unico')]
        permissions = [
            ('calcular_nomina', 'Puede calcular y revisar nóminas'),
            ('aprobar_nomina', 'Puede aprobar nóminas'),
            ('cerrar_nomina', 'Puede cerrar nóminas'),
            ('rectificar_nomina', 'Puede rectificar nóminas cerradas'),
            ('emitir_recibos', 'Puede emitir, publicar y anular recibos'),
            ('registrar_pagos', 'Puede registrar y confirmar pagos de nómina'),
            ('ver_costo_patronal', 'Puede ver el costo del empleador'),
        ]

    def __str__(self):
        return f'{self.periodo.codigo} · n.º {self.numero} ({self.get_tipo_display().lower()})'

    @property
    def editable(self):
        return self.estado in (self.CALCULADA, self.REVISADA)

    @property
    def es_rectificacion(self):
        return self.corrida_origen_id is not None


class LiquidacionEmpleado(RegistroEmpresa):
    OK = 'ok'
    ADVERTENCIA = 'advertencia'
    ERROR = 'error'
    CALCULO_OPCIONES = [(OK, 'Correcta'), (ADVERTENCIA, 'Con advertencias'), (ERROR, 'Con errores (bloquea la aprobación)')]
    PAGO_OPCIONES = [('pendiente', 'Pendiente'), ('registrado', 'Pago registrado'), ('pagado', 'Pagado')]

    corrida = models.ForeignKey(CorridaNomina, on_delete=models.CASCADE, related_name='liquidaciones', verbose_name='liquidación')
    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='liquidaciones', verbose_name='empleado')
    contrato = models.ForeignKey('contratos.ContratoEmpleado', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                 verbose_name='contrato')
    centro_costo = models.ForeignKey('empleados.CentroCosto', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                     verbose_name='centro de costo')
    salario_base = models.DecimalField('sueldo o tarifa', max_digits=18, decimal_places=2, default=0)
    base_calculo = models.CharField('base de cálculo', max_length=12, blank=True)
    dias_trabajados = models.DecimalField('días trabajados', max_digits=6, decimal_places=2, default=0)
    dias_pagados = models.DecimalField('días pagados', max_digits=6, decimal_places=2, default=0)
    dias_no_pagados = models.DecimalField('días no pagados', max_digits=6, decimal_places=2, default=0)
    minutos_ordinarios = models.PositiveIntegerField('minutos ordinarios', default=0)
    minutos_extra = models.PositiveIntegerField('minutos extra autorizados', default=0)
    bruto = models.DecimalField('bruto', max_digits=18, decimal_places=2, default=0)
    descuentos = models.DecimalField('descuentos', max_digits=18, decimal_places=2, default=0)
    aportes_trabajador = models.DecimalField('aportes del trabajador', max_digits=18, decimal_places=2, default=0)
    neto = models.DecimalField('neto a cobrar', max_digits=18, decimal_places=2, default=0)
    aportes_patronales = models.DecimalField('aportes del empleador', max_digits=18, decimal_places=2, default=0)
    otros_costos = models.DecimalField('otros costos del empleador', max_digits=18, decimal_places=2, default=0)
    costo_empleador = models.DecimalField('costo total del empleador', max_digits=18, decimal_places=2, default=0)
    provision_aguinaldo = models.DecimalField('provisión de aguinaldo (estimada, no suma al costo)', max_digits=18,
                                              decimal_places=2, default=0)
    neto_anterior = models.DecimalField('neto de la liquidación rectificada', max_digits=18, decimal_places=2, null=True, blank=True)
    estado_calculo = models.CharField('cálculo', max_length=12, choices=CALCULO_OPCIONES, default=OK)
    advertencias = models.JSONField('advertencias', default=list)
    estado_pago = models.CharField('pago', max_length=12, choices=PAGO_OPCIONES, default='pendiente')

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'liquidación de un empleado'
        verbose_name_plural = 'liquidaciones por empleado'
        ordering = ['empleado__primer_apellido', 'empleado__primer_nombre']
        constraints = [models.UniqueConstraint(fields=['corrida', 'empleado'], name='liquidacion_empleado_unica')]

    def __str__(self):
        return f'{self.empleado} · {self.corrida}'

    @property
    def a_pagar(self):
        """En una rectificación se paga (o se recupera) solo la diferencia."""
        return self.neto - (self.neto_anterior or 0)


class LineaNomina(models.Model):
    ORIGEN_OPCIONES = [('regla', 'Regla de cálculo'), ('concepto_fijo', 'Concepto fijo'), ('novedad', 'Novedad'),
                       ('descuento', 'Descuento autorizado'), ('cuota', 'Cuota de anticipo o préstamo'), ('manual', 'Ajuste manual')]

    empresa = models.ForeignKey('plataforma.Empresa', on_delete=models.PROTECT, related_name='+', verbose_name='empresa')
    liquidacion = models.ForeignKey(LiquidacionEmpleado, on_delete=models.CASCADE, related_name='lineas', verbose_name='liquidación')
    concepto = models.ForeignKey(ConceptoNomina, on_delete=models.PROTECT, related_name='+', verbose_name='concepto')
    codigo = models.CharField('código del concepto (copia)', max_length=50)
    nombre = models.CharField('nombre del concepto (copia)', max_length=150)
    tipo = models.CharField('tipo (copia)', max_length=20, choices=ConceptoNomina.TIPO_OPCIONES)
    cantidad = models.DecimalField('cantidad', max_digits=16, decimal_places=4, null=True, blank=True)
    tasa = models.DecimalField('tasa', max_digits=16, decimal_places=6, null=True, blank=True)
    base = models.DecimalField('base', max_digits=18, decimal_places=2, null=True, blank=True)
    importe = models.DecimalField('importe', max_digits=18, decimal_places=2)
    importe_con_signo = models.DecimalField('importe con signo', max_digits=18, decimal_places=2,
                                            help_text='Positivo suma al neto; negativo resta; cero si no afecta el neto.')
    regla = models.ForeignKey(ReglaConcepto, on_delete=models.PROTECT, null=True, blank=True, related_name='+', verbose_name='regla')
    explicacion = models.TextField('explicación')
    origen = models.CharField('origen', max_length=15, choices=ORIGEN_OPCIONES)
    origen_id = models.PositiveIntegerField('id del origen', null=True, blank=True)
    secuencia = models.PositiveSmallIntegerField('orden', default=0)
    afecta_neto = models.BooleanField('afecta el neto', default=True)

    ruta_empresa = 'empresa'
    ruta_sucursal = 'liquidacion__empleado__sucursal'
    ruta_empleado = 'liquidacion__empleado'

    class Meta:
        verbose_name = 'línea de nómina'
        verbose_name_plural = 'líneas de nómina'
        ordering = ['liquidacion', 'secuencia', 'id']

    def __str__(self):
        return f'{self.codigo} {self.importe_con_signo:,.0f}'.replace(',', '.')


class PagoNomina(RegistroEmpresa):
    REGISTRADO = 'registrado'
    CONFIRMADO = 'confirmado'
    ANULADO = 'anulado'
    ESTADO_OPCIONES = [(REGISTRADO, 'Registrado'), (CONFIRMADO, 'Confirmado'), (ANULADO, 'Anulado')]
    FORMA_OPCIONES = [('transferencia', 'Transferencia'), ('efectivo', 'Efectivo'), ('cheque', 'Cheque')]

    corrida = models.ForeignKey(CorridaNomina, on_delete=models.PROTECT, related_name='pagos', verbose_name='liquidación')
    liquidacion = models.ForeignKey(LiquidacionEmpleado, on_delete=models.PROTECT, related_name='pagos', verbose_name='empleado')
    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='pagos_nomina', verbose_name='empleado')
    fecha = models.DateField('fecha de pago')
    monto = models.DecimalField('monto', max_digits=18, decimal_places=2)
    moneda = models.CharField('moneda', max_length=3, default='PYG')
    forma = models.CharField('forma de pago', max_length=15, choices=FORMA_OPCIONES, default='transferencia')
    referencia = models.CharField('referencia', max_length=100, blank=True)
    cuenta_bancaria = models.ForeignKey('empleados.CuentaBancaria', on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='+', verbose_name='cuenta bancaria')
    estado = models.CharField('estado', max_length=12, choices=ESTADO_OPCIONES, default=REGISTRADO, editable=False)
    confirmado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                       editable=False, related_name='+', verbose_name='confirmado por')
    confirmado_en = models.DateTimeField('confirmado el', null=True, blank=True, editable=False)
    motivo_anulacion = models.CharField('motivo de anulación', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'pago de nómina'
        verbose_name_plural = 'pagos de nómina'
        ordering = ['-fecha', 'empleado']

    def __str__(self):
        return f'Pago a {self.empleado} · {self.fecha:%d/%m/%Y}'


class SecuenciaDocumento(models.Model):
    """Numeración correlativa de documentos por empresa, tipo y año (sin huecos por concurrencia: se toma con bloqueo)."""

    empresa = models.ForeignKey('plataforma.Empresa', on_delete=models.PROTECT, related_name='+', verbose_name='empresa')
    tipo = models.CharField('tipo de documento', max_length=30)
    anio = models.PositiveSmallIntegerField('año')
    prefijo = models.CharField('prefijo', max_length=10, default='R')
    siguiente = models.PositiveIntegerField('siguiente número', default=1)

    ruta_empresa = 'empresa'

    class Meta:
        verbose_name = 'numeración de documentos'
        verbose_name_plural = 'numeraciones de documentos'
        constraints = [models.UniqueConstraint(fields=['empresa', 'tipo', 'anio'], name='secuencia_unica')]

    def __str__(self):
        return f'{self.tipo} {self.anio}: próximo {self.siguiente}'


class ReciboSueldo(RegistroEmpresa):
    EMITIDO = 'emitido'
    ANULADO = 'anulado'
    ESTADO_OPCIONES = [(EMITIDO, 'Emitido'), (ANULADO, 'Anulado')]
    TIPO_OPCIONES = [('sueldo', 'Sueldo'), ('rectificacion', 'Rectificación'), ('aguinaldo', 'Aguinaldo'),
                     ('liquidacion_final', 'Liquidación final')]

    corrida = models.ForeignKey(CorridaNomina, on_delete=models.PROTECT, related_name='recibos', verbose_name='liquidación')
    liquidacion = models.ForeignKey(LiquidacionEmpleado, on_delete=models.PROTECT, related_name='recibos', verbose_name='liquidación del empleado')
    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='recibos', verbose_name='empleado')
    numero = models.CharField('número', max_length=30)
    tipo = models.CharField('tipo', max_length=20, choices=TIPO_OPCIONES, default='sueldo')
    fecha_emision = models.DateField('fecha de emisión')
    periodo_desde = models.DateField('período desde')
    periodo_hasta = models.DateField('período hasta')
    bruto = models.DecimalField('bruto', max_digits=18, decimal_places=2)
    descuentos = models.DecimalField('descuentos y aportes', max_digits=18, decimal_places=2)
    neto = models.DecimalField('neto', max_digits=18, decimal_places=2)
    costo_empleador = models.DecimalField('costo del empleador (interno)', max_digits=18, decimal_places=2)
    publicado = models.BooleanField('visible para el empleado', default=False)
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=EMITIDO, editable=False)
    motivo_anulacion = models.CharField('motivo de anulación', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'recibo de sueldo'
        verbose_name_plural = 'recibos de sueldo'
        ordering = ['-fecha_emision', '-numero']
        constraints = [models.UniqueConstraint(fields=['empresa', 'numero'], name='recibo_numero_unico')]

    def __str__(self):
        return f'Recibo {self.numero} · {self.empleado}'


class AsignacionCostoPatronal(RegistroEmpresa):
    """El costo del empleador de cada empleado en una liquidación cerrada, por centro de costo (§4.6).
    La provisión de aguinaldo se guarda aparte y no suma al total (§4.6: no contar dos veces)."""

    corrida = models.ForeignKey(CorridaNomina, on_delete=models.PROTECT, related_name='costos', verbose_name='liquidación')
    periodo = models.ForeignKey(PeriodoNomina, on_delete=models.PROTECT, related_name='+', verbose_name='período')
    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='+', verbose_name='empleado')
    centro_costo = models.ForeignKey('empleados.CentroCosto', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                     verbose_name='centro de costo')
    remuneracion_bruta = models.DecimalField('remuneración bruta', max_digits=18, decimal_places=2)
    aporte_patronal = models.DecimalField('aportes del empleador', max_digits=18, decimal_places=2)
    otros_costos = models.DecimalField('otros costos', max_digits=18, decimal_places=2, default=0)
    costo_total = models.DecimalField('costo total', max_digits=18, decimal_places=2)
    provision_aguinaldo = models.DecimalField('provisión de aguinaldo (aparte)', max_digits=18, decimal_places=2, default=0)
    moneda = models.CharField('moneda', max_length=3, default='PYG')

    ruta_sucursal = 'empleado__sucursal'

    class Meta:
        verbose_name = 'costo del empleador'
        verbose_name_plural = 'costos del empleador'
        ordering = ['-periodo__fecha_desde', 'empleado']


class LiquidacionFinal(RegistroEmpresa):
    """Liquidación por egreso (§4.6 FinalSettlement). Sus importes se calculan
    en una corrida de tipo "liquidación final" (mismo ciclo: revisar, aprobar,
    cerrar, recibo, pago). Qué conceptos corresponden depende de la causal, la
    antigüedad y las reglas legales vigentes (§8: no asumir todos para todos)."""

    CAUSAL_OPCIONES = [
        ('renuncia', 'Renuncia'), ('despido_justificado', 'Despido con causa justificada'),
        ('despido_injustificado', 'Despido sin causa justificada'), ('mutuo_acuerdo', 'Mutuo acuerdo'),
        ('fin_contrato', 'Fin del plazo o de la obra'), ('jubilacion', 'Jubilación'), ('fallecimiento', 'Fallecimiento'),
        ('abandono', 'Abandono de trabajo'),
    ]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='liquidaciones_finales',
                                 verbose_name='empleado')
    fecha_egreso = models.DateField('fecha de egreso')
    causal = models.CharField('causal', max_length=25, choices=CAUSAL_OPCIONES)
    preaviso_otorgado = models.BooleanField('se otorgó (o se cumplió) el preaviso', default=False,
                                            help_text='Si se dio el preaviso, no se paga la indemnización sustitutiva.')
    motivo = models.CharField('detalle', max_length=250, blank=True)
    corrida = models.OneToOneField(CorridaNomina, on_delete=models.PROTECT, null=True, blank=True, editable=False,
                                   related_name='liquidacion_final', verbose_name='liquidación')

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'liquidación final'
        verbose_name_plural = 'liquidaciones finales'
        ordering = ['-fecha_egreso']

    def __str__(self):
        return f'Liquidación final de {self.empleado} · {self.fecha_egreso:%d/%m/%Y}'

    def clean(self):
        errores = {}
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            errores['empleado'] = 'Tiene que ser un empleado de la misma empresa.'
        if self.empleado_id and self.fecha_egreso and self.fecha_egreso < self.empleado.fecha_ingreso:
            errores['fecha_egreso'] = 'No puede ser anterior al ingreso.'
        if self.empleado_id and not errores:
            otras = LiquidacionFinal.objects.filter(empleado_id=self.empleado_id).exclude(pk=self.pk).exclude(
                corrida__estado=CorridaNomina.ANULADA)
            if otras.exists():
                errores['empleado'] = 'El empleado ya tiene una liquidación final (anulala para hacer otra).'
        if errores:
            raise ValidationError(errores)
