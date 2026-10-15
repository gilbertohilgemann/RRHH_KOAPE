"""Novedades de nómina, descuentos autorizados, anticipos y préstamos (fase 9; §4.4 y §8).

- `Novedad`: un movimiento de un período para un empleado (comisión, bono,
  horas, descuento puntual…) con su concepto, cantidad, tasa o monto. Pendiente
  → aprobada / rechazada; aprobada la toma la nómina (fase 10) y queda
  "aplicada": ya no se toca. Comisiones y bonos son novedades del concepto
  COMISION (base de ventas × tasa) o BONO (monto).
- `DescuentoAutorizado`: un descuento que se repite (cuota sindical, embargo,
  compra en la empresa…), siempre con autorización del empleado o base legal
  documentada (§8: "no aplicar descuentos sin autorización/base legal").
- `Anticipo` y `Prestamo`: con aprobación, pago o desembolso y recuperación en
  `CuotaRecuperacion`. El saldo es la suma de las cuotas pendientes; cada cuota
  se descuenta una sola vez (§8: "evitar doble descuento")."""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import RegistroEmpresa

UN_GUARANI = Decimal('1')


def _validar_empleado_y_documento(objeto, errores):
    if objeto.empleado_id and objeto.empresa_id and objeto.empleado.empresa_id != objeto.empresa_id:
        errores['empleado'] = 'Tiene que ser un empleado de la misma empresa.'
    documento = getattr(objeto, 'documento', None) if getattr(objeto, 'documento_id', None) else None
    if documento is not None and objeto.empleado_id and documento.empleado_id != objeto.empleado_id:
        errores['documento'] = 'El documento no es de este empleado.'


def _validar_concepto(objeto, errores, tipos):
    concepto = objeto.concepto if objeto.concepto_id else None
    if concepto is None:
        return
    if concepto.empresa_id not in (None, objeto.empresa_id):
        errores['concepto'] = 'El concepto no es de esta empresa.'
    elif concepto.tipo not in tipos:
        errores['concepto'] = 'Este concepto no sirve acá: ' + ('solo descuentos.' if tipos == ('descuento',) else 'solo haberes o descuentos.')
    elif not concepto.activo:
        errores['concepto'] = 'El concepto está inactivo.'


class Novedad(RegistroEmpresa):
    PENDIENTE = 'pendiente'
    APROBADA = 'aprobada'
    RECHAZADA = 'rechazada'
    APLICADA = 'aplicada'
    ANULADA = 'anulada'
    ESTADO_OPCIONES = [(PENDIENTE, 'Pendiente'), (APROBADA, 'Aprobada'), (RECHAZADA, 'Rechazada'),
                       (APLICADA, 'Aplicada en nómina'), (ANULADA, 'Anulada')]
    ORIGEN_OPCIONES = [('manual', 'Carga manual'), ('comision', 'Comisión'), ('bono', 'Bono o premio'),
                       ('importado', 'Importado'), ('asistencia', 'Asistencia')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='novedades', verbose_name='empleado')
    concepto = models.ForeignKey('nomina.ConceptoNomina', on_delete=models.PROTECT, related_name='novedades', verbose_name='concepto')
    periodo_desde = models.DateField('período desde')
    periodo_hasta = models.DateField('período hasta')
    cantidad = models.DecimalField('cantidad o base', max_digits=16, decimal_places=2, null=True, blank=True,
                                   help_text='Ej. horas, o la base de ventas de una comisión.')
    tasa = models.DecimalField('tasa o valor unitario', max_digits=12, decimal_places=4, null=True, blank=True,
                               help_text='Ej. el % de comisión.')
    monto = models.DecimalField('monto', max_digits=14, decimal_places=2, null=True, blank=True,
                                help_text='Vacío = cantidad × tasa (con tasa en %, si es una comisión). Siempre positivo.')
    moneda = models.CharField('moneda', max_length=3, default='PYG')
    descripcion = models.CharField('descripción', max_length=250)
    origen = models.CharField('origen', max_length=12, choices=ORIGEN_OPCIONES, default='manual')
    referencia = models.CharField('referencia', max_length=100, blank=True, help_text='Ej. número de factura o de liquidación de ventas.')
    documento = models.ForeignKey('empleados.DocumentoEmpleado', on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='+', verbose_name='comprobante')
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=PENDIENTE, editable=False)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='resuelta por')
    aprobado_en = models.DateTimeField('resuelta el', null=True, blank=True, editable=False)
    motivo_resolucion = models.CharField('motivo del rechazo o la anulación', max_length=250, blank=True, editable=False)
    corrida = models.PositiveIntegerField('liquidación en la que se aplicó', null=True, blank=True, editable=False,
                                          help_text='Lo completa la nómina (fase 10).')

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'novedad'
        verbose_name_plural = 'novedades'
        ordering = ['-periodo_desde', '-id']
        permissions = [('aprobar_novedad', 'Puede aprobar, rechazar o anular novedades')]

    def __str__(self):
        return f'{self.concepto.codigo} · {self.empleado} · {self.periodo_desde:%m/%Y}'

    def importe(self):
        """El monto, o cantidad × tasa (la tasa de una comisión es un %)."""
        if self.monto is not None:
            return self.monto
        if self.cantidad is not None and self.tasa is not None:
            valor = self.cantidad * self.tasa
            if self.origen == 'comision' or (self.concepto_id and self.concepto.tipo_calculo == 'porcentaje'):
                valor = valor / 100
            return valor.quantize(UN_GUARANI, rounding=ROUND_HALF_UP)
        return None

    def clean(self):
        errores = {}
        _validar_empleado_y_documento(self, errores)
        _validar_concepto(self, errores, ('haber', 'descuento'))
        if self.periodo_desde and self.periodo_hasta and self.periodo_hasta < self.periodo_desde:
            errores['periodo_hasta'] = 'No puede ser anterior a "desde".'
        for campo in ('cantidad', 'tasa', 'monto'):
            valor = getattr(self, campo)
            if valor is not None and valor < 0:
                errores[campo] = 'No puede ser negativo (el concepto ya dice si suma o resta).'
        if self.monto is None and (self.cantidad is None or self.tasa is None):
            errores['monto'] = 'Indicá el monto, o la cantidad y la tasa.'
        if self.concepto_id and self.concepto.requiere_comprobante and not self.documento_id:
            errores['documento'] = 'Este concepto exige un comprobante del legajo.'
        if self.empleado_id and self.periodo_hasta and self.periodo_hasta < self.empleado.fecha_ingreso:
            errores['periodo_desde'] = 'El empleado todavía no trabajaba en ese período.'
        if errores:
            raise ValidationError(errores)


class DescuentoAutorizado(RegistroEmpresa):
    VIGENTE = 'vigente'
    FINALIZADO = 'finalizado'
    ANULADO = 'anulado'
    ESTADO_OPCIONES = [(VIGENTE, 'Vigente'), (FINALIZADO, 'Finalizado'), (ANULADO, 'Anulado')]
    TIPO_OPCIONES = [('sindical', 'Cuota sindical'), ('embargo', 'Embargo judicial'), ('compra', 'Compra o consumo en la empresa'),
                     ('seguro', 'Seguro o cobertura'), ('otro', 'Otro')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='descuentos_autorizados',
                                 verbose_name='empleado')
    concepto = models.ForeignKey('nomina.ConceptoNomina', on_delete=models.PROTECT, related_name='descuentos_autorizados',
                                 verbose_name='concepto')
    tipo = models.CharField('tipo', max_length=10, choices=TIPO_OPCIONES)
    monto_cuota = models.DecimalField('monto por liquidación', max_digits=14, decimal_places=2, null=True, blank=True)
    porcentaje = models.DecimalField('o porcentaje del sueldo', max_digits=6, decimal_places=3, null=True, blank=True,
                                     validators=[MinValueValidator(0), MaxValueValidator(100)])
    monto_total = models.DecimalField('monto total a descontar', max_digits=14, decimal_places=2, null=True, blank=True,
                                      help_text='Vacío = sin tope (ej. una cuota sindical).')
    fecha_desde = models.DateField('desde')
    fecha_hasta = models.DateField('hasta', null=True, blank=True)
    autorizado_por_empleado = models.BooleanField('autorizado por escrito por el empleado', default=False)
    documento = models.ForeignKey('empleados.DocumentoEmpleado', on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='+', verbose_name='autorización u orden judicial')
    prioridad = models.PositiveSmallIntegerField('prioridad', default=100, help_text='Menor = se descuenta antes si no alcanza.')
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=VIGENTE, editable=False)
    motivo_fin = models.CharField('motivo de la finalización o anulación', max_length=250, blank=True, editable=False)
    observaciones = models.CharField('observaciones', max_length=250, blank=True)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'descuento autorizado'
        verbose_name_plural = 'descuentos autorizados'
        ordering = ['empleado', 'prioridad', '-fecha_desde']

    def __str__(self):
        return f'{self.get_tipo_display()} · {self.empleado}'

    def clean(self):
        errores = {}
        _validar_empleado_y_documento(self, errores)
        _validar_concepto(self, errores, ('descuento',))
        if (self.monto_cuota is None) == (self.porcentaje is None):
            errores['monto_cuota'] = 'Indicá el monto por liquidación o el porcentaje (uno de los dos).'
        if self.monto_cuota is not None and self.monto_cuota <= 0:
            errores['monto_cuota'] = 'Tiene que ser mayor que cero.'
        if self.monto_total is not None and self.monto_total <= 0:
            errores['monto_total'] = 'Tiene que ser mayor que cero.'
        if self.fecha_desde and self.fecha_hasta and self.fecha_hasta < self.fecha_desde:
            errores['fecha_hasta'] = 'No puede ser anterior a "desde".'
        # §8: sin autorización del empleado o base legal documentada, no se descuenta.
        if not self.documento_id:
            errores['documento'] = 'Adjuntá la autorización firmada o la orden (documento del legajo).'
        elif self.tipo != 'embargo' and not self.autorizado_por_empleado:
            errores['autorizado_por_empleado'] = 'Este descuento necesita la autorización escrita del empleado.'
        if errores:
            raise ValidationError(errores)


class Anticipo(RegistroEmpresa):
    SOLICITADO = 'solicitado'
    APROBADO = 'aprobado'
    RECHAZADO = 'rechazado'
    PAGADO = 'pagado'
    RECUPERADO = 'recuperado'
    ANULADO = 'anulado'
    ESTADO_OPCIONES = [(SOLICITADO, 'Solicitado'), (APROBADO, 'Aprobado (a pagar)'), (RECHAZADO, 'Rechazado'),
                       (PAGADO, 'Pagado (recuperándose)'), (RECUPERADO, 'Recuperado'), (ANULADO, 'Anulado')]
    FORMA_PAGO_OPCIONES = [('transferencia', 'Transferencia'), ('efectivo', 'Efectivo'), ('cheque', 'Cheque')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='anticipos', verbose_name='empleado')
    fecha = models.DateField('fecha del pedido')
    monto_solicitado = models.DecimalField('monto solicitado', max_digits=14, decimal_places=2)
    monto_aprobado = models.DecimalField('monto aprobado', max_digits=14, decimal_places=2, null=True, blank=True, editable=False)
    moneda = models.CharField('moneda', max_length=3, default='PYG')
    motivo = models.CharField('motivo', max_length=250)
    cuotas = models.PositiveSmallIntegerField('se recupera en (cuotas)', default=1, validators=[MinValueValidator(1), MaxValueValidator(12)],
                                              help_text='1 = se descuenta entero en la próxima liquidación.')
    primer_mes = models.DateField('primer mes de descuento', null=True, blank=True,
                                  help_text='Vacío = el mes siguiente al pago.')
    concepto = models.ForeignKey('nomina.ConceptoNomina', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                 verbose_name='concepto de descuento', help_text='Vacío = ANTICIPO.')
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=SOLICITADO, editable=False)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='resuelto por')
    aprobado_en = models.DateTimeField('resuelto el', null=True, blank=True, editable=False)
    forma_pago = models.CharField('forma de pago', max_length=15, choices=FORMA_PAGO_OPCIONES, blank=True, editable=False)
    referencia_pago = models.CharField('referencia del pago', max_length=100, blank=True, editable=False)
    pagado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   editable=False, related_name='+', verbose_name='pagado por')
    pagado_en = models.DateTimeField('pagado el', null=True, blank=True, editable=False)
    motivo_resolucion = models.CharField('motivo del rechazo o la anulación', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'anticipo'
        verbose_name_plural = 'anticipos'
        ordering = ['-fecha', '-id']
        permissions = [('aprobar_anticipo', 'Puede aprobar o rechazar anticipos'), ('pagar_anticipo', 'Puede registrar el pago de anticipos')]

    def __str__(self):
        return f'Anticipo de {self.empleado} · {self.fecha:%d/%m/%Y}'

    def clean(self):
        errores = {}
        _validar_empleado_y_documento(self, errores)
        if self.concepto_id:
            _validar_concepto(self, errores, ('descuento',))
        if self.monto_solicitado is not None and self.monto_solicitado <= 0:
            errores['monto_solicitado'] = 'Tiene que ser mayor que cero.'
        if self.empleado_id and self.fecha and self.fecha < self.empleado.fecha_ingreso:
            errores['fecha'] = 'No puede ser anterior al ingreso del empleado.'
        if errores:
            raise ValidationError(errores)


class Prestamo(RegistroEmpresa):
    SOLICITADO = 'solicitado'
    APROBADO = 'aprobado'
    RECHAZADO = 'rechazado'
    DESEMBOLSADO = 'desembolsado'
    CANCELADO = 'cancelado'
    ANULADO = 'anulado'
    ESTADO_OPCIONES = [(SOLICITADO, 'Solicitado'), (APROBADO, 'Aprobado (a desembolsar)'), (RECHAZADO, 'Rechazado'),
                       (DESEMBOLSADO, 'Desembolsado (en cuotas)'), (CANCELADO, 'Cancelado (pagado)'), (ANULADO, 'Anulado')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='prestamos', verbose_name='empleado')
    fecha = models.DateField('fecha')
    capital = models.DecimalField('capital', max_digits=14, decimal_places=2)
    moneda = models.CharField('moneda', max_length=3, default='PYG')
    cantidad_cuotas = models.PositiveSmallIntegerField('cantidad de cuotas', validators=[MinValueValidator(1), MaxValueValidator(60)])
    tasa_interes_mensual = models.DecimalField('interés mensual (%)', max_digits=6, decimal_places=3, default=0,
                                               validators=[MinValueValidator(0), MaxValueValidator(10)],
                                               help_text='0 = sin interés. Con interés: cuota fija (sistema francés).')
    primer_mes = models.DateField('primer mes de descuento', help_text='Se descuenta una cuota por mes desde ese mes.')
    motivo = models.CharField('motivo', max_length=250)
    concepto = models.ForeignKey('nomina.ConceptoNomina', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                 verbose_name='concepto de descuento', help_text='Vacío = CUOTA_PRESTAMO.')
    documento = models.ForeignKey('empleados.DocumentoEmpleado', on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='+', verbose_name='autorización firmada')
    estado = models.CharField('estado', max_length=12, choices=ESTADO_OPCIONES, default=SOLICITADO, editable=False)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='resuelto por')
    aprobado_en = models.DateTimeField('resuelto el', null=True, blank=True, editable=False)
    desembolsado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                         editable=False, related_name='+', verbose_name='desembolsado por')
    desembolsado_en = models.DateTimeField('desembolsado el', null=True, blank=True, editable=False)
    referencia_pago = models.CharField('referencia del desembolso', max_length=100, blank=True, editable=False)
    motivo_resolucion = models.CharField('motivo del rechazo, la anulación o la cancelación', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'préstamo'
        verbose_name_plural = 'préstamos'
        ordering = ['-fecha', '-id']
        permissions = [('aprobar_prestamo', 'Puede aprobar o rechazar préstamos'),
                       ('desembolsar_prestamo', 'Puede registrar el desembolso y la cancelación de préstamos')]

    def __str__(self):
        return f'Préstamo de {self.empleado} · {self.fecha:%d/%m/%Y}'

    def plan(self):
        """[(número, mes, monto de la cuota)] con cuota fija; la última absorbe el redondeo."""
        n, capital = self.cantidad_cuotas, Decimal(self.capital)
        tasa = Decimal(self.tasa_interes_mensual) / 100
        if tasa:
            cuota = (capital * tasa / (1 - (1 + tasa) ** -n)).quantize(UN_GUARANI, rounding=ROUND_HALF_UP)
            total = cuota * n
        else:
            cuota = (capital / n).quantize(UN_GUARANI, rounding=ROUND_HALF_UP)
            total = capital
        filas, acumulado = [], Decimal('0')
        for i in range(1, n + 1):
            monto = cuota if i < n else (total - acumulado).quantize(UN_GUARANI, rounding=ROUND_HALF_UP)
            filas.append((i, _sumar_meses(self.primer_mes, i - 1), monto))
            acumulado += monto
        return filas

    def clean(self):
        errores = {}
        _validar_empleado_y_documento(self, errores)
        if self.concepto_id:
            _validar_concepto(self, errores, ('descuento',))
        if self.capital is not None and self.capital <= 0:
            errores['capital'] = 'Tiene que ser mayor que cero.'
        if self.fecha and self.primer_mes and self.primer_mes < self.fecha.replace(day=1):
            errores['primer_mes'] = 'No puede ser anterior al mes del préstamo.'
        if self.empleado_id and self.fecha and self.fecha < self.empleado.fecha_ingreso:
            errores['fecha'] = 'No puede ser anterior al ingreso del empleado.'
        if errores:
            raise ValidationError(errores)


def _sumar_meses(fecha, meses):
    total = fecha.year * 12 + fecha.month - 1 + meses
    return fecha.replace(year=total // 12, month=total % 12 + 1, day=1)


class CuotaRecuperacion(RegistroEmpresa):
    """Una cuota a descontar de un anticipo o un préstamo, en un mes. La nómina
    (fase 10) la marca aplicada una sola vez; nunca se borra."""

    PENDIENTE = 'pendiente'
    APLICADA = 'aplicada'
    PAGADA_APARTE = 'pagada_aparte'
    ANULADA = 'anulada'
    ESTADO_OPCIONES = [(PENDIENTE, 'Pendiente'), (APLICADA, 'Descontada en nómina'), (PAGADA_APARTE, 'Pagada aparte'),
                       (ANULADA, 'Anulada')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='cuotas_recuperacion',
                                 verbose_name='empleado')
    anticipo = models.ForeignKey(Anticipo, on_delete=models.PROTECT, null=True, blank=True, related_name='cuotas_recuperacion',
                                 verbose_name='anticipo')
    prestamo = models.ForeignKey(Prestamo, on_delete=models.PROTECT, null=True, blank=True, related_name='cuotas_recuperacion',
                                 verbose_name='préstamo')
    concepto = models.ForeignKey('nomina.ConceptoNomina', on_delete=models.PROTECT, related_name='+', verbose_name='concepto')
    numero = models.PositiveSmallIntegerField('cuota número')
    mes = models.DateField('mes a descontar', help_text='Primer día del mes.')
    monto = models.DecimalField('monto', max_digits=14, decimal_places=2)
    estado = models.CharField('estado', max_length=14, choices=ESTADO_OPCIONES, default=PENDIENTE)
    corrida = models.PositiveIntegerField('liquidación en la que se descontó', null=True, blank=True,
                                          help_text='Lo completa la nómina (fase 10).')
    aplicada_en = models.DateTimeField('descontada el', null=True, blank=True)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'cuota a descontar'
        verbose_name_plural = 'cuotas a descontar'
        ordering = ['mes', 'empleado', 'numero']
        constraints = [
            models.CheckConstraint(condition=models.Q(anticipo__isnull=False, prestamo__isnull=True)
                                   | models.Q(anticipo__isnull=True, prestamo__isnull=False), name='cuota_de_anticipo_o_prestamo'),
            models.UniqueConstraint(fields=['anticipo', 'numero'], condition=models.Q(anticipo__isnull=False), name='cuota_anticipo_unica'),
            models.UniqueConstraint(fields=['prestamo', 'numero'], condition=models.Q(prestamo__isnull=False), name='cuota_prestamo_unica'),
        ]

    def __str__(self):
        origen = 'anticipo' if self.anticipo_id else 'préstamo'
        return f'Cuota {self.numero} del {origen} de {self.empleado} · {self.mes:%m/%Y}'


def saldo_de(objeto):
    """Lo que falta recuperar de un anticipo o un préstamo: sus cuotas pendientes."""
    return objeto.cuotas_recuperacion.filter(estado=CuotaRecuperacion.PENDIENTE).aggregate(
        t=models.Sum('monto'))['t'] or Decimal('0')


class ReciboAnticipo(RegistroEmpresa):
    """Comprobante del pago de un anticipo, numerado (A<año>-000001), para imprimir y firmar al entregarlo.
    Las cuotas que lo descuentan en la nómina citan su número y su fecha."""

    EMITIDO = 'emitido'
    ANULADO = 'anulado'
    ESTADO_OPCIONES = [(EMITIDO, 'Emitido'), (ANULADO, 'Anulado')]

    anticipo = models.ForeignKey(Anticipo, on_delete=models.PROTECT, related_name='recibos', verbose_name='anticipo')
    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='recibos_anticipo',
                                 verbose_name='empleado')
    numero = models.CharField('número', max_length=30)
    fecha_emision = models.DateField('fecha')
    monto = models.DecimalField('monto entregado', max_digits=14, decimal_places=2)
    moneda = models.CharField('moneda', max_length=3, default='PYG')
    forma_pago = models.CharField('forma de pago', max_length=15, blank=True)
    referencia_pago = models.CharField('referencia del pago', max_length=100, blank=True)
    aporta_ips = models.BooleanField('aportaba al IPS', default=True,
                                     help_text='Copia del legajo al emitir: sin IPS, el comprobante no lleva el número patronal.')
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=EMITIDO, editable=False)
    motivo_anulacion = models.CharField('motivo de anulación', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'comprobante de anticipo'
        verbose_name_plural = 'comprobantes de anticipo'
        ordering = ['-fecha_emision', '-numero']
        constraints = [models.UniqueConstraint(fields=['empresa', 'numero'], name='recibo_anticipo_numero_unico')]

    def __str__(self):
        return f'{self.numero} del {self.fecha_emision:%d/%m/%Y}'


def recibo_vigente(anticipo):
    """El comprobante emitido (no anulado) del anticipo, o None."""
    return anticipo.recibos.filter(estado=ReciboAnticipo.EMITIDO).order_by('-fecha_emision', '-id').first()
