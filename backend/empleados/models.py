from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from core.archivos import almacenamiento_privado, ruta_aleatoria, ruta_foto
from core.cifrado import cifrar, descifrar, enmascarar
from core.models import CatalogoEmpresa, RegistroBase, RegistroEmpresa


def _misma_empresa(errores, registro, campo, empresa_id):
    """Una relación (departamento, puesto...) tiene que ser de la misma empresa."""
    relacionado = getattr(registro, campo, None)
    if relacionado is not None and empresa_id and relacionado.empresa_id != empresa_id:
        errores[campo] = 'Tiene que ser de la misma empresa.'


class Departamento(RegistroEmpresa):
    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=150)
    departamento_padre = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='subdepartamentos',
        verbose_name='depende de',
    )
    responsable = models.ForeignKey(
        'Empleado', on_delete=models.SET_NULL, null=True, blank=True, related_name='departamentos_a_cargo',
        verbose_name='responsable',
    )
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'departamento'
        verbose_name_plural = 'departamentos'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='departamento_codigo_unico')]

    def __str__(self):
        return self.nombre

    def clean(self):
        errores = {}
        _misma_empresa(errores, self, 'departamento_padre', self.empresa_id)
        _misma_empresa(errores, self, 'responsable', self.empresa_id)
        # Sin ciclos (A depende de B que depende de A).
        padre, vistos = self.departamento_padre, set()
        while padre is not None and 'departamento_padre' not in errores:
            if padre.pk == self.pk and self.pk is not None or padre.pk in vistos:
                errores['departamento_padre'] = 'Un departamento no puede depender de sí mismo.'
            vistos.add(padre.pk)
            padre = padre.departamento_padre
        if errores:
            raise ValidationError(errores)


class Puesto(RegistroEmpresa):
    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=150)
    descripcion = models.TextField('descripción', blank=True)
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'puesto'
        verbose_name_plural = 'puestos'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='puesto_codigo_unico')]

    def __str__(self):
        return self.nombre


class CentroCosto(RegistroEmpresa):
    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=150)
    centro_padre = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='subcentros', verbose_name='depende de',
    )
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'centro de costo'
        verbose_name_plural = 'centros de costo'
        ordering = ['codigo']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='centro_costo_codigo_unico')]

    def __str__(self):
        return f'{self.codigo} · {self.nombre}'

    def clean(self):
        errores = {}
        _misma_empresa(errores, self, 'centro_padre', self.empresa_id)
        if self.centro_padre_id and self.centro_padre_id == self.pk:
            errores['centro_padre'] = 'Un centro de costo no puede depender de sí mismo.'
        if errores:
            raise ValidationError(errores)


# Campos de la asignación del empleado: si cambia alguno, queda en el historial.
CAMPOS_ASIGNACION = ('sucursal', 'departamento', 'puesto', 'centro_costo', 'supervisor')


class Empleado(RegistroEmpresa):
    """Legajo del empleado. Nunca se borra: la baja es lógica (estado "Baja",
    fecha y motivo de egreso) y conserva contratos, marcaciones, nóminas,
    documentos y auditoría. La baja y la reactivación son acciones propias
    (`dar_baja` / `reactivar`) con su permiso, no una edición común.

    Cada cambio de sucursal, departamento, puesto, centro de costo o
    supervisor queda en `HistorialAsignacion` con su vigencia."""

    ACTIVO = 'activo'
    SUSPENDIDO = 'suspendido'
    BAJA = 'baja'
    ESTADO_OPCIONES = [(ACTIVO, 'Activo'), (SUSPENDIDO, 'Suspendido'), (BAJA, 'Baja')]

    TIPO_DOCUMENTO_OPCIONES = [
        ('CI', 'Cédula de identidad'),
        ('PAS', 'Pasaporte'),
        ('CE', 'Cédula extranjera'),
        ('OTRO', 'Otro'),
    ]
    SEXO_OPCIONES = [('F', 'Femenino'), ('M', 'Masculino')]
    ESTADO_CIVIL_OPCIONES = [
        ('soltero', 'Soltero/a'), ('casado', 'Casado/a'), ('divorciado', 'Divorciado/a'),
        ('viudo', 'Viudo/a'), ('union', 'Unión de hecho'),
    ]

    codigo = models.CharField('código de empleado', max_length=30)
    tipo_documento = models.CharField('tipo de documento', max_length=5, choices=TIPO_DOCUMENTO_OPCIONES, default='CI')
    numero_documento = models.CharField('número de documento', max_length=30)
    primer_nombre = models.CharField('primer nombre', max_length=80)
    segundo_nombre = models.CharField('segundo nombre', max_length=80, blank=True)
    primer_apellido = models.CharField('primer apellido', max_length=80)
    segundo_apellido = models.CharField('segundo apellido', max_length=80, blank=True)
    fecha_nacimiento = models.DateField('fecha de nacimiento', null=True, blank=True)
    # Sexo, nacionalidad y estado civil: los piden las planillas del MTESS y del IPS.
    sexo = models.CharField('sexo', max_length=1, choices=SEXO_OPCIONES, blank=True)
    nacionalidad = models.CharField('nacionalidad', max_length=60, blank=True, default='Paraguaya')
    estado_civil = models.CharField('estado civil', max_length=12, choices=ESTADO_CIVIL_OPCIONES, blank=True)
    numero_asegurado_ips = models.CharField('número de asegurado IPS', max_length=30, blank=True)
    correo_personal = models.EmailField('correo personal', blank=True)
    correo_laboral = models.EmailField('correo laboral', blank=True)
    telefono = models.CharField('teléfono', max_length=50, blank=True)
    direccion = models.CharField('dirección', max_length=250, blank=True)

    fecha_ingreso = models.DateField('fecha de ingreso')
    fecha_egreso = models.DateField('fecha de egreso', null=True, blank=True, editable=False)
    motivo_egreso = models.CharField('motivo de egreso', max_length=250, blank=True, editable=False)
    estado = models.CharField('estado', max_length=12, choices=ESTADO_OPCIONES, default=ACTIVO, editable=False)

    sucursal = models.ForeignKey('plataforma.Sucursal', on_delete=models.PROTECT, null=True, blank=True,
                                 related_name='empleados', verbose_name='sucursal')
    departamento = models.ForeignKey(Departamento, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='empleados', verbose_name='departamento')
    puesto = models.ForeignKey(Puesto, on_delete=models.PROTECT, null=True, blank=True,
                               related_name='empleados', verbose_name='puesto')
    centro_costo = models.ForeignKey(CentroCosto, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='empleados', verbose_name='centro de costo')
    supervisor = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='supervisados', verbose_name='supervisor')
    observaciones = models.TextField('observaciones internas', blank=True,
                                     help_text='Solo las ven Administración y RR. HH.; el empleado no.')
    # Privada (fuera de /media/): se sube con la acción `foto` de la API y se
    # entrega solo a quien puede ver el legajo (y a la terminal donde marcó).
    foto = models.ImageField('foto', upload_to=ruta_foto, storage=almacenamiento_privado, blank=True, editable=False)

    ruta_sucursal = 'sucursal'
    ruta_empleado = ''

    class Meta:
        verbose_name = 'empleado'
        verbose_name_plural = 'empleados'
        ordering = ['primer_apellido', 'primer_nombre']
        constraints = [
            models.UniqueConstraint(fields=['empresa', 'codigo'], name='empleado_codigo_unico'),
            models.UniqueConstraint(fields=['empresa', 'tipo_documento', 'numero_documento'],
                                    name='empleado_documento_unico'),
        ]
        permissions = [
            ('dar_baja_empleado', 'Puede dar de baja (lógica) un empleado'),
            ('reactivar_empleado', 'Puede reactivar un empleado dado de baja'),
        ]

    def __str__(self):
        return f'{self.nombre_completo} ({self.codigo})'

    @property
    def nombre_completo(self):
        nombres = ' '.join(p for p in (self.primer_nombre, self.segundo_nombre) if p)
        apellidos = ' '.join(p for p in (self.primer_apellido, self.segundo_apellido) if p)
        return f'{apellidos}, {nombres}'

    @property
    def activo(self):
        return self.estado != self.BAJA

    def clean(self):
        errores = {}
        for campo in CAMPOS_ASIGNACION:
            _misma_empresa(errores, self, campo, self.empresa_id)
        if self.supervisor_id and self.supervisor_id == self.pk:
            errores['supervisor'] = 'Un empleado no puede ser su propio supervisor.'
        hoy = timezone.localdate()
        if self.fecha_nacimiento and self.fecha_nacimiento >= hoy:
            errores['fecha_nacimiento'] = 'La fecha de nacimiento tiene que ser anterior a hoy.'
        if self.fecha_nacimiento and self.fecha_ingreso and self.fecha_ingreso <= self.fecha_nacimiento:
            errores['fecha_ingreso'] = 'La fecha de ingreso tiene que ser posterior al nacimiento.'
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        """Guarda y, si cambió la asignación, cierra la vigencia anterior y
        abre una nueva en el historial (en la misma transacción)."""
        nuevo = self.pk is None
        anterior = None if nuevo else Empleado.objects.filter(pk=self.pk).values(*[f'{c}_id' for c in CAMPOS_ASIGNACION]).first()
        with transaction.atomic():
            super().save(*args, **kwargs)
            actual = {f'{c}_id': getattr(self, f'{c}_id') for c in CAMPOS_ASIGNACION}
            if nuevo or anterior != actual:
                self._registrar_asignacion(desde=self.fecha_ingreso if nuevo else timezone.localdate(),
                                           motivo='Alta del empleado' if nuevo else 'Cambio de asignación')

    def _registrar_asignacion(self, desde, motivo):
        abiertas = HistorialAsignacion.objects.filter(empleado=self, vigente_hasta__isnull=True)
        for abierta in abiertas:
            # Un cambio el mismo día que la vigencia anterior empezó la reemplaza.
            if abierta.vigente_desde >= desde:
                abierta.delete()
            else:
                abierta.vigente_hasta = desde - timedelta(days=1)
                abierta.save(update_fields=['vigente_hasta'])
        HistorialAsignacion.objects.create(
            empresa_id=self.empresa_id, empleado=self, vigente_desde=desde, motivo=motivo,
            creado_por=self.modificado_por or self.creado_por, modificado_por=self.modificado_por or self.creado_por,
            **{f'{c}_id': getattr(self, f'{c}_id') for c in CAMPOS_ASIGNACION},
        )


class TipoDocumento(CatalogoEmpresa):
    """Tipos de documento del legajo (cédula, contrato firmado, certificado
    médico...): los globales los carga la plataforma, cada empresa suma los suyos."""

    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=120)
    confidencial = models.BooleanField(
        'confidencial', default=False,
        help_text='Datos médicos u otros sensibles: solo los ve quien tiene el permiso de documentos confidenciales '
                  '(y el propio empleado).',
    )
    requiere_vencimiento = models.BooleanField('pide fecha de vencimiento', default=False)
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'tipo de documento'
        verbose_name_plural = 'tipos de documento'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='tipo_documento_codigo_unico')]

    def __str__(self):
        return self.nombre


class DocumentoEmpleado(RegistroEmpresa):
    """Archivo del legajo. Se guarda privado (core/archivos.py), con su
    huella SHA-256, y nunca se borra: se anula con motivo (es evidencia)."""

    VIGENTE = 'vigente'
    ANULADO = 'anulado'
    ESTADO_OPCIONES = [(VIGENTE, 'Vigente'), (ANULADO, 'Anulado')]

    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name='documentos', verbose_name='empleado')
    tipo_documento = models.ForeignKey(TipoDocumento, on_delete=models.PROTECT, related_name='documentos',
                                       verbose_name='tipo de documento')
    descripcion = models.CharField('descripción', max_length=250, blank=True)
    archivo = models.FileField('archivo', upload_to=ruta_aleatoria, storage=almacenamiento_privado)
    nombre_original = models.CharField('nombre del archivo', max_length=255, editable=False)
    tipo_mime = models.CharField('tipo de archivo', max_length=100, editable=False)
    tamano = models.PositiveIntegerField('tamaño (bytes)', editable=False, default=0)
    sha256 = models.CharField('huella SHA-256', max_length=64, editable=False)
    fecha_emision = models.DateField('fecha de emisión', null=True, blank=True)
    fecha_vencimiento = models.DateField('fecha de vencimiento', null=True, blank=True)
    confidencial = models.BooleanField('confidencial', default=False, editable=False,
                                       help_text='Se toma del tipo de documento al cargarlo.')
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=VIGENTE, editable=False)
    motivo_anulacion = models.CharField('motivo de anulación', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'documento del legajo'
        verbose_name_plural = 'documentos del legajo'
        ordering = ['-creado']
        permissions = [
            ('ver_documento_confidencial', 'Puede ver y descargar documentos confidenciales de otros empleados'),
            ('anular_documento', 'Puede anular documentos del legajo'),
        ]

    def __str__(self):
        return f'{self.tipo_documento} · {self.empleado}'

    def clean(self):
        errores = {}
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            errores['empleado'] = 'Tiene que ser un empleado de la misma empresa.'
        tipo = self.tipo_documento if self.tipo_documento_id else None
        if tipo is not None:
            if tipo.empresa_id not in (None, self.empresa_id):
                errores['tipo_documento'] = 'El tipo de documento no es de esta empresa.'
            if tipo.requiere_vencimiento and not self.fecha_vencimiento:
                errores['fecha_vencimiento'] = 'Este tipo de documento pide fecha de vencimiento.'
        if self.fecha_emision and self.fecha_vencimiento and self.fecha_vencimiento < self.fecha_emision:
            errores['fecha_vencimiento'] = 'No puede ser anterior a la emisión.'
        if errores:
            raise ValidationError(errores)


class CuentaBancaria(RegistroEmpresa):
    """Cuenta donde se le paga al empleado. El número se guarda cifrado
    (core/cifrado.py) y en los listados solo se ven los últimos 4 dígitos;
    el número completo lo ve quien tiene el permiso, a pedido y auditado."""

    TIPO_OPCIONES = [('ahorro', 'Caja de ahorro'), ('corriente', 'Cuenta corriente'), ('billetera', 'Billetera electrónica')]

    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name='cuentas_bancarias',
                                 verbose_name='empleado')
    banco = models.CharField('banco o entidad', max_length=120)
    tipo_cuenta = models.CharField('tipo de cuenta', max_length=12, choices=TIPO_OPCIONES, default='ahorro')
    numero_cifrado = models.TextField('número (cifrado)', editable=False)
    ultimos_digitos = models.CharField('últimos dígitos', max_length=4, editable=False)
    moneda = models.CharField('moneda', max_length=3, default='PYG')
    titular = models.CharField('titular', max_length=150)
    documento_titular = models.CharField('documento del titular', max_length=30, blank=True)
    principal = models.BooleanField('cuenta principal', default=True,
                                    help_text='Donde se deposita el sueldo. Solo una principal por empleado.')
    activa = models.BooleanField('activa', default=True)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'
    # Nunca a la bitácora, ni cifrado.
    campos_sin_auditar = ('numero_cifrado',)

    class Meta:
        verbose_name = 'cuenta bancaria'
        verbose_name_plural = 'cuentas bancarias'
        ordering = ['empleado', '-principal', 'banco']
        constraints = [
            models.UniqueConstraint(fields=['empleado'], condition=models.Q(principal=True, activa=True),
                                    name='una_cuenta_principal_por_empleado'),
        ]
        permissions = [('ver_cuenta_completa', 'Puede ver el número completo de las cuentas bancarias')]

    def __str__(self):
        return f'{self.banco} {enmascarar(self.ultimos_digitos)}'

    @property
    def numero_enmascarado(self):
        return enmascarar(self.ultimos_digitos)

    def fijar_numero(self, numero):
        limpio = ''.join(numero.split())
        if not limpio or len(limpio) < 4 or len(limpio) > 40:
            raise ValidationError({'numero': 'Indicá el número de cuenta completo (entre 4 y 40 caracteres).'})
        self.numero_cifrado = cifrar(limpio)
        self.ultimos_digitos = limpio[-4:]

    def numero_completo(self):
        return descifrar(self.numero_cifrado) if self.numero_cifrado else None

    def clean(self):
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            raise ValidationError({'empleado': 'Tiene que ser un empleado de la misma empresa.'})
        if self.principal and self.activa and self.empleado_id and CuentaBancaria.objects.filter(
                empleado_id=self.empleado_id, principal=True, activa=True).exclude(pk=self.pk).exists():
            raise ValidationError({'principal': 'El empleado ya tiene una cuenta principal activa: desmarcala primero.'})


class HistorialAsignacion(RegistroBase):
    """Dónde estuvo asignado el empleado y desde/hasta cuándo. Lo escribe
    solo `Empleado.save()`; no se carga ni se edita a mano."""

    empresa = models.ForeignKey('plataforma.Empresa', on_delete=models.PROTECT, related_name='+', verbose_name='empresa')
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name='historial_asignaciones',
                                 verbose_name='empleado')
    sucursal = models.ForeignKey('plataforma.Sucursal', on_delete=models.PROTECT, null=True, blank=True,
                                 related_name='+', verbose_name='sucursal')
    departamento = models.ForeignKey(Departamento, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+', verbose_name='departamento')
    puesto = models.ForeignKey(Puesto, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                               verbose_name='puesto')
    centro_costo = models.ForeignKey(CentroCosto, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+', verbose_name='centro de costo')
    supervisor = models.ForeignKey(Empleado, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                   verbose_name='supervisor')
    vigente_desde = models.DateField('vigente desde')
    vigente_hasta = models.DateField('vigente hasta', null=True, blank=True)
    motivo = models.CharField('motivo', max_length=250, blank=True)

    ruta_empresa = 'empresa'
    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'historial de asignación'
        verbose_name_plural = 'historial de asignaciones'
        ordering = ['empleado', '-vigente_desde']

    def __str__(self):
        hasta = f'{self.vigente_hasta:%d/%m/%Y}' if self.vigente_hasta else 'hoy'
        return f'{self.empleado} · {self.vigente_desde:%d/%m/%Y} a {hasta}'
