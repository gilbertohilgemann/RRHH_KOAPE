"""Asistencia (fase 4: marcador propio de Koape).

Tres modalidades de registro (§6 bis), cada una identificada en la marca:
- A) QR dinámico (invertido por decisión del cliente, 14/10/2026): la
  TERMINAL proyecta un QR que genera el servidor y cambia cada pocos
  segundos (y apenas alguien lo usa); el empleado, con su sesión iniciada en
  el celular, lo escanea. Token aleatorio, vigencia corta, solo se guarda su
  huella; se consume de forma atómica. Ambas pantallas muestran la marca.
- B) Código fijo del empleado, presentado en una terminal autorizada.
  Identifica el código, NO prueba por sí solo quién lo presenta.
- C) Archivo CSV (fase 5): primero a revisión (LoteImportacion + FilaImportacion),
  después, al confirmar, a marcas. Sin verificación presencial, con
  validación técnica, deduplicación y trazabilidad.

Las marcas (`Marcacion`) nunca se editan ni se borran: las correcciones son
marcas nuevas enlazadas (fase 6). La hora es siempre la del servidor."""
import hashlib
import hmac
import secrets
from datetime import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.archivos import almacenamiento_privado
from core.cifrado import cifrar, descifrar
from core.models import RegistroBase, RegistroEmpresa


def huella(texto):
    return hashlib.sha256(texto.encode()).hexdigest()


class ConfiguracionMarcacion(RegistroBase):
    """Opciones del marcador de cada empresa (se crea sola con valores por defecto)."""

    AUTOMATICA = 'automatica'
    EXPLICITA = 'explicita'
    MODO_OPCIONES = [
        (AUTOMATICA, 'Koape propone entrada o salida según la secuencia'),
        (EXPLICITA, 'La terminal pide elegir Entrada o Salida'),
    ]

    empresa = models.OneToOneField('plataforma.Empresa', on_delete=models.CASCADE, related_name='configuracion_marcacion',
                                   verbose_name='empresa')
    permite_qr = models.BooleanField('QR dinámico en la terminal (el empleado lo escanea con su celular)', default=True)
    permite_codigo_fijo = models.BooleanField(
        'código fijo del empleado', default=False,
        help_text='Práctico, pero el código puede compartirse: no prueba por sí solo la presencia del empleado. '
                  'Para una comprobación más fuerte, preferí el QR temporal.',
    )
    permite_csv = models.BooleanField('importación de archivo CSV', default=False,
                                      help_text='Sin verificación presencial (fase 5).')
    vigencia_qr_segundos = models.PositiveSmallIntegerField(
        'cambio del QR (segundos)', default=20, validators=[MinValueValidator(10), MaxValueValidator(300)],
        help_text='Cada cuántos segundos cambia el QR de la pantalla. Más corto = más difícil reenviarlo a alguien que no está.')
    qr_un_solo_uso = models.BooleanField(
        'el QR cambia apenas alguien lo usa', default=True,
        help_text='Recomendado: una foto del QR ya no le sirve a otro empleado.')
    modo_accion = models.CharField('entrada o salida', max_length=12, choices=MODO_OPCIONES, default=AUTOMATICA)
    largo_codigo = models.PositiveSmallIntegerField('largo del código fijo', default=6,
                                                    validators=[MinValueValidator(4), MaxValueValidator(12)])
    empleado_ve_su_codigo = models.BooleanField('el empleado puede ver su código fijo', default=True)
    segundos_antirrebote = models.PositiveSmallIntegerField(
        'segundos mínimos entre dos marcas', default=60, validators=[MaxValueValidator(900)],
        help_text='Una segunda marca del mismo empleado antes de este tiempo se rechaza como repetida.',
    )
    horas_maximas_turno = models.PositiveSmallIntegerField(
        'horas máximas de un turno', default=16, validators=[MinValueValidator(4), MaxValueValidator(24)],
        help_text='Una entrada sin salida más vieja que esto ya no se empareja con la siguiente marca.',
    )
    # Motor de asistencia (fase 6).
    inicio_nocturno = models.TimeField(
        'inicio del horario nocturno', default=time(20, 0),
        help_text='DATO LEGAL A VERIFICAR (Código del Trabajo). En la fase 8 pasa a las reglas legales versionadas.')
    fin_nocturno = models.TimeField('fin del horario nocturno', default=time(6, 0))
    minimos_extra = models.PositiveSmallIntegerField(
        'minutos mínimos para contar horas extra', default=15, validators=[MaxValueValidator(120)],
        help_text='Menos que esto por encima del horario no se considera hora extra candidata.')
    minimos_tardanza = models.PositiveSmallIntegerField(
        'minutos mínimos de salida anticipada', default=5, validators=[MaxValueValidator(120)],
        help_text='La tardanza usa la tolerancia de cada horario; esto vale para las salidas anticipadas.')
    exigir_aprobador_distinto = models.BooleanField(
        'quien aprueba un ajuste o una hora extra no puede ser quien lo pidió', default=False,
        help_text='Separación de funciones entre operador y aprobador.')

    ruta_empresa = 'empresa'

    class Meta:
        verbose_name = 'configuración del marcador'
        verbose_name_plural = 'configuraciones del marcador'

    def __str__(self):
        return f'Marcador de {self.empresa}'

    @classmethod
    def de(cls, empresa):
        configuracion, _ = cls.objects.get_or_create(empresa=empresa)
        return configuracion


class TerminalMarcacion(RegistroEmpresa):
    """Dispositivo autorizado para registrar marcas (tablet, PC con cámara o
    lector QR). Se autentica con una clave propia que se muestra una sola vez
    al generarla; acá solo queda su huella."""

    LECTOR_QR = 'lector_qr'
    CODIGO_FIJO = 'codigo_fijo'
    HIBRIDA = 'hibrida'
    TIPO_OPCIONES = [(LECTOR_QR, 'Lector de QR'), (CODIGO_FIJO, 'Teclado de código fijo'), (HIBRIDA, 'QR y código fijo')]

    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=120)
    ubicacion = models.CharField('ubicación', max_length=150, blank=True)
    sucursal = models.ForeignKey('plataforma.Sucursal', on_delete=models.PROTECT, null=True, blank=True,
                                 related_name='terminales', verbose_name='sucursal')
    tipo = models.CharField('tipo', max_length=12, choices=TIPO_OPCIONES, default=HIBRIDA)
    clave_huella = models.CharField('huella de la clave', max_length=64, blank=True, editable=False)
    clave_generada_en = models.DateTimeField('clave generada el', null=True, blank=True, editable=False)
    activa = models.BooleanField('activa', default=True)
    ultima_conexion = models.DateTimeField('última conexión', null=True, blank=True, editable=False)

    ruta_sucursal = 'sucursal'
    campos_sin_auditar = ('clave_huella',)

    class Meta:
        verbose_name = 'terminal de marcación'
        verbose_name_plural = 'terminales de marcación'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='terminal_codigo_unico')]

    def __str__(self):
        return self.nombre

    def clean(self):
        if self.sucursal_id and self.empresa_id and self.sucursal.empresa_id != self.empresa_id:
            raise ValidationError({'sucursal': 'La sucursal no es de esta empresa.'})

    @property
    def acepta_qr(self):
        return self.tipo in (self.LECTOR_QR, self.HIBRIDA)

    @property
    def acepta_codigo(self):
        return self.tipo in (self.CODIGO_FIJO, self.HIBRIDA)

    def generar_clave(self):
        """Nueva clave (la anterior deja de valer). Devuelve la clave en claro: se muestra una sola vez."""
        from django.utils import timezone
        clave = f'{self.pk}.{secrets.token_urlsafe(32)}'
        self.clave_huella = huella(clave)
        self.clave_generada_en = timezone.now()
        self.save(update_fields=['clave_huella', 'clave_generada_en'])
        return clave

    @classmethod
    def autenticar(cls, clave):
        """La terminal activa dueña de la clave, o None."""
        identificador = clave.split('.', 1)[0]
        if not identificador.isdigit():
            return None
        terminal = cls.objects.select_related('empresa').filter(pk=int(identificador), activa=True).first()
        if terminal is None or not terminal.clave_huella or not terminal.empresa.activa:
            return None
        return terminal if hmac.compare_digest(terminal.clave_huella, huella(clave)) else None


def _huella_codigo(empresa_id, codigo):
    """HMAC del código con la clave de cifrado: permite buscarlo sin guardarlo en claro."""
    return hmac.new(settings.CLAVE_CIFRADO.encode(), f'{empresa_id}:{codigo}'.encode(), hashlib.sha256).hexdigest()


class CredencialMarcacion(RegistroEmpresa):
    """Código fijo de un empleado. Lo genera Koape (numérico, aleatorio, único
    en la empresa); no es la contraseña ni sirve para entrar al sistema, y no
    se arma con la cédula. Se guarda su HMAC (para buscarlo) y una copia
    cifrada (para mostrarlo a quien tiene permiso). Se revoca y se rota."""

    ACTIVA = 'activa'
    REVOCADA = 'revocada'
    ESTADO_OPCIONES = [(ACTIVA, 'Activa'), (REVOCADA, 'Revocada')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='credenciales_marcacion',
                                 verbose_name='empleado')
    codigo_huella = models.CharField('huella del código', max_length=64, editable=False)
    codigo_cifrado = models.TextField('código (cifrado)', editable=False)
    version = models.PositiveSmallIntegerField('versión', default=1, editable=False)
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=ACTIVA, editable=False)
    revocada_en = models.DateTimeField('revocada el', null=True, blank=True, editable=False)
    revocada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='revocada por')
    motivo_revocacion = models.CharField('motivo de revocación', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'
    campos_sin_auditar = ('codigo_huella', 'codigo_cifrado')

    class Meta:
        verbose_name = 'código fijo de marcación'
        verbose_name_plural = 'códigos fijos de marcación'
        ordering = ['empleado', '-version']
        constraints = [
            models.UniqueConstraint(fields=['empresa', 'codigo_huella'], condition=models.Q(estado='activa'),
                                    name='codigo_marcacion_unico_activo'),
            models.UniqueConstraint(fields=['empleado'], condition=models.Q(estado='activa'),
                                    name='un_codigo_activo_por_empleado'),
        ]
        permissions = [('ver_codigo_marcacion', 'Puede ver el código fijo de marcación de los empleados')]

    def __str__(self):
        return f'{self.empleado} · código v{self.version} ({self.get_estado_display().lower()})'

    def codigo(self):
        return descifrar(self.codigo_cifrado)

    @classmethod
    def generar(cls, empleado, usuario):
        """Código nuevo para el empleado; revoca el activo anterior. Devuelve (credencial, código en claro)."""
        from django.db import transaction
        from django.utils import timezone
        largo = ConfiguracionMarcacion.de(empleado.empresa).largo_codigo
        with transaction.atomic():
            anteriores = cls.objects.select_for_update().filter(empleado=empleado, estado=cls.ACTIVA)
            version = (cls.objects.filter(empleado=empleado).aggregate(m=models.Max('version'))['m'] or 0) + 1
            anteriores.update(estado=cls.REVOCADA, revocada_en=timezone.now(), revocada_por=usuario,
                              motivo_revocacion='Reemplazado por un código nuevo.')
            for _ in range(50):
                codigo = ''.join(secrets.choice('0123456789') for _ in range(largo))
                huella_codigo = _huella_codigo(empleado.empresa_id, codigo)
                if not cls.objects.filter(empresa_id=empleado.empresa_id, codigo_huella=huella_codigo,
                                          estado=cls.ACTIVA).exists():
                    break
            else:  # pragma: no cover - con 4+ dígitos y pocas colisiones no debería pasar
                raise ValidationError('No se pudo generar un código único: aumentá el largo del código.')
            credencial = cls.objects.create(
                empresa_id=empleado.empresa_id, empleado=empleado, codigo_huella=huella_codigo,
                codigo_cifrado=cifrar(codigo), version=version, creado_por=usuario, modificado_por=usuario,
            )
        return credencial, codigo

    @classmethod
    def buscar(cls, empresa_id, codigo):
        return cls.objects.select_related('empleado').filter(
            empresa_id=empresa_id, codigo_huella=_huella_codigo(empresa_id, codigo.strip()), estado=cls.ACTIVA,
        ).first()


class QRDinamico(models.Model):
    """QR que proyecta una terminal. Lo genera el servidor, vence en
    `vigencia_qr_segundos` y (si la empresa lo configura) sirve una sola vez:
    apenas alguien marca con él, la terminal muestra otro. Lleva solo un
    token aleatorio, sin datos personales; acá se guarda su huella."""

    VIGENTE = 'vigente'
    USADO = 'usado'
    REEMPLAZADO = 'reemplazado'
    VENCIDO = 'vencido'
    ESTADO_OPCIONES = [(VIGENTE, 'Vigente'), (USADO, 'Usado'), (REEMPLAZADO, 'Reemplazado'), (VENCIDO, 'Vencido')]

    empresa = models.ForeignKey('plataforma.Empresa', on_delete=models.PROTECT, related_name='+', verbose_name='empresa')
    terminal = models.ForeignKey(TerminalMarcacion, on_delete=models.PROTECT, related_name='qrs', verbose_name='terminal')
    token_huella = models.CharField('huella del token', max_length=64, unique=True)
    generado_en = models.DateTimeField('generado el', auto_now_add=True)
    vence_en = models.DateTimeField('vence el', db_index=True)
    estado = models.CharField('estado', max_length=12, choices=ESTADO_OPCIONES, default=VIGENTE, db_index=True)
    usos = models.PositiveIntegerField('marcas registradas', default=0)

    ruta_empresa = 'empresa'
    ruta_sucursal = 'terminal__sucursal'

    class Meta:
        verbose_name = 'QR dinámico'
        verbose_name_plural = 'QR dinámicos'
        ordering = ['-generado_en']
        indexes = [models.Index(fields=['terminal', 'estado', 'vence_en'])]

    def __str__(self):
        return f'QR de {self.terminal} · {self.generado_en:%d/%m/%Y %H:%M:%S} · {self.get_estado_display()}'


class Marcacion(RegistroEmpresa):
    """Marca de entrada o salida. Inmutable: nunca se edita ni se borra."""

    ENTRADA = 'entrada'
    SALIDA = 'salida'
    INICIO_DESCANSO = 'inicio_descanso'
    FIN_DESCANSO = 'fin_descanso'
    DESCONOCIDO = 'desconocido'
    TIPO_OPCIONES = [(ENTRADA, 'Entrada'), (SALIDA, 'Salida'), (INICIO_DESCANSO, 'Inicio de descanso'),
                     (FIN_DESCANSO, 'Fin de descanso'), (DESCONOCIDO, 'Sin determinar')]

    QR = 'qr'
    CODIGO_FIJO = 'codigo_fijo'
    CSV = 'csv'
    MANUAL = 'manual'
    API = 'api'
    METODO_OPCIONES = [(QR, 'QR dinámico'), (CODIGO_FIJO, 'Código fijo'), (CSV, 'Importación CSV'),
                       (MANUAL, 'Carga manual aprobada'), (API, 'Integración (API)')]

    VERIFICACION_OPCIONES = [
        ('qr_autenticado', 'QR dinámico leído desde la sesión del empleado'),
        ('solo_codigo', 'Solo código fijo (no prueba identidad)'),
        ('archivo_importado', 'Archivo importado (sin verificación presencial)'),
        ('manual_aprobado', 'Manual aprobado'),
        ('dispositivo_externo', 'Dispositivo externo'),
    ]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='marcaciones',
                                 verbose_name='empleado')
    fecha_hora = models.DateTimeField('fecha y hora', db_index=True)
    tipo = models.CharField('tipo', max_length=16, choices=TIPO_OPCIONES)
    metodo = models.CharField('método', max_length=12, choices=METODO_OPCIONES)
    nivel_verificacion = models.CharField('verificación', max_length=20, choices=VERIFICACION_OPCIONES)
    terminal = models.ForeignKey(TerminalMarcacion, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name='marcaciones', verbose_name='terminal')
    credencial = models.ForeignKey(CredencialMarcacion, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='marcaciones', verbose_name='código fijo usado')
    qr = models.ForeignKey(QRDinamico, on_delete=models.PROTECT, null=True, blank=True,
                           related_name='marcaciones', verbose_name='QR usado')
    id_evento_externo = models.CharField('id de evento externo', max_length=120, blank=True)
    huella_deduplicacion = models.CharField('huella para duplicados', max_length=64, db_index=True)
    referencia = models.CharField('referencia de captura', max_length=120, blank=True)
    # Importación CSV (fase 5): de qué lote y reloj vino.
    lote_importacion = models.ForeignKey('LoteImportacion', on_delete=models.PROTECT, null=True, blank=True,
                                         related_name='marcaciones', verbose_name='lote de importación')
    reloj = models.ForeignKey('RelojExterno', on_delete=models.PROTECT, null=True, blank=True,
                              related_name='marcaciones', verbose_name='reloj externo')
    # Anulación lógica (ej. al revertir un lote): la marca queda, pero no cuenta.
    anulada = models.BooleanField('anulada', default=False, editable=False)
    anulada_en = models.DateTimeField('anulada el', null=True, blank=True, editable=False)
    motivo_anulacion = models.CharField('motivo de anulación', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'marcación'
        verbose_name_plural = 'marcaciones'
        ordering = ['-fecha_hora', '-id']
        indexes = [models.Index(fields=['empresa', 'empleado', 'fecha_hora'])]
        # Única entre las marcas que cuentan: un lote revertido (marcas anuladas) se puede volver a importar.
        constraints = [models.UniqueConstraint(fields=['huella_deduplicacion'], condition=models.Q(anulada=False),
                                               name='marcacion_huella_unica_vigente')]
        permissions = [('marcar_con_qr', 'Puede marcar su asistencia escaneando el QR de una terminal')]

    def __str__(self):
        from django.utils import timezone
        return f'{self.empleado} · {self.get_tipo_display()} {timezone.localtime(self.fecha_hora):%d/%m/%Y %H:%M}'


class RelojExterno(RegistroEmpresa):
    """Reloj marcador de otra marca cuyas marcas llegan en un archivo CSV."""

    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=120)
    fabricante = models.CharField('fabricante', max_length=100, blank=True)
    modelo = models.CharField('modelo', max_length=100, blank=True)
    numero_serie = models.CharField('número de serie', max_length=100, blank=True)
    ubicacion = models.CharField('ubicación', max_length=150, blank=True)
    sucursal = models.ForeignKey('plataforma.Sucursal', on_delete=models.PROTECT, null=True, blank=True,
                                 related_name='relojes', verbose_name='sucursal')
    perfil_importacion = models.ForeignKey('PerfilImportacion', on_delete=models.PROTECT, null=True, blank=True,
                                           related_name='relojes', verbose_name='perfil de importación habitual')
    activo = models.BooleanField('activo', default=True)

    ruta_sucursal = 'sucursal'

    class Meta:
        verbose_name = 'reloj externo'
        verbose_name_plural = 'relojes externos'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='reloj_codigo_unico')]

    def __str__(self):
        return self.nombre

    def clean(self):
        errores = {}
        if self.sucursal_id and self.empresa_id and self.sucursal.empresa_id != self.empresa_id:
            errores['sucursal'] = 'La sucursal no es de esta empresa.'
        if self.perfil_importacion_id and self.empresa_id and self.perfil_importacion.empresa_id != self.empresa_id:
            errores['perfil_importacion'] = 'El perfil no es de esta empresa.'
        if errores:
            raise ValidationError(errores)


class MapeoEmpleadoReloj(RegistroEmpresa):
    """Qué empleado es cada código del reloj externo (el código del reloj no
    se asume igual al de Koape). Puede tener vigencia: un código del reloj
    puede pasar a otra persona."""

    reloj = models.ForeignKey(RelojExterno, on_delete=models.PROTECT, related_name='mapeos', verbose_name='reloj')
    codigo_en_reloj = models.CharField('código en el reloj', max_length=80)
    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='codigos_reloj',
                                 verbose_name='empleado')
    vigente_desde = models.DateField('vigente desde', null=True, blank=True)
    vigente_hasta = models.DateField('vigente hasta', null=True, blank=True)
    notas = models.CharField('notas', max_length=250, blank=True)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'código de reloj'
        verbose_name_plural = 'códigos de reloj'
        ordering = ['reloj', 'codigo_en_reloj']

    def __str__(self):
        return f'{self.reloj} · {self.codigo_en_reloj} → {self.empleado}'

    def clean(self):
        errores = {}
        if self.reloj_id and self.empresa_id and self.reloj.empresa_id != self.empresa_id:
            errores['reloj'] = 'El reloj no es de esta empresa.'
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            errores['empleado'] = 'Tiene que ser un empleado de la misma empresa.'
        if self.vigente_desde and self.vigente_hasta and self.vigente_hasta < self.vigente_desde:
            errores['vigente_hasta'] = 'No puede ser anterior a "vigente desde".'
        if self.reloj_id and self.codigo_en_reloj and not errores:
            # El mismo código del mismo reloj no puede ser de dos personas a la vez.
            for otro in MapeoEmpleadoReloj.objects.filter(reloj_id=self.reloj_id,
                                                          codigo_en_reloj=self.codigo_en_reloj.strip()).exclude(pk=self.pk):
                inicio_a, fin_a = self.vigente_desde, self.vigente_hasta
                inicio_b, fin_b = otro.vigente_desde, otro.vigente_hasta
                if (fin_b is None or inicio_a is None or inicio_a <= fin_b) and (fin_a is None or inicio_b is None or inicio_b <= fin_a):
                    errores['codigo_en_reloj'] = f'Ese código ya está asignado en esas fechas ({otro.empleado}).'
                    break
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.codigo_en_reloj = self.codigo_en_reloj.strip()
        super().save(*args, **kwargs)


class PerfilImportacion(RegistroEmpresa):
    """Cómo leer el CSV de un reloj o de un sistema: separador, codificación,
    columnas y formatos explícitos (sin adivinar fechas ambiguas). Las
    columnas se indican por el nombre del encabezado o por su número (1, 2…).
    Cada cambio sube la versión, que queda guardada en cada lote."""

    IDENTIFICADOR_OPCIONES = [
        ('codigo_reloj', 'Código del reloj (se traduce con los códigos de reloj)'),
        ('codigo_empleado', 'Código de empleado de Koape'),
        ('documento', 'Número de documento (cédula)'),
    ]
    MODO_OPCIONES = [
        ('reloj_externo', 'Archivo de un reloj externo'),
        ('predefinido', 'Archivo con el formato de Koape'),
        ('confiado', 'Archivo confiado: sin verificación presencial'),
    ]
    SEPARADOR_OPCIONES = [(',', 'Coma ( , )'), (';', 'Punto y coma ( ; )'), ('\t', 'Tabulación')]
    CODIFICACION_OPCIONES = [('utf-8', 'UTF-8'), ('latin-1', 'Latin-1 (ISO-8859-1)'), ('cp1252', 'Windows-1252')]

    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=120)
    modo = models.CharField('tipo de archivo', max_length=15, choices=MODO_OPCIONES, default='reloj_externo')
    separador = models.CharField('separador', max_length=2, choices=SEPARADOR_OPCIONES, default=';')
    codificacion = models.CharField('codificación', max_length=10, choices=CODIFICACION_OPCIONES, default='utf-8')
    tiene_encabezado = models.BooleanField('la primera fila es el encabezado', default=True)
    identificador = models.CharField('cómo viene el empleado', max_length=16, choices=IDENTIFICADOR_OPCIONES,
                                     default='codigo_reloj')
    columna_empleado = models.CharField('columna del empleado', max_length=100)
    columna_fecha_hora = models.CharField('columna de fecha y hora (juntas)', max_length=100, blank=True)
    formato_fecha_hora = models.CharField('formato de fecha y hora', max_length=50, blank=True,
                                          help_text='Ej. %d/%m/%Y %H:%M:%S (formato de Python).')
    columna_fecha = models.CharField('columna de la fecha', max_length=100, blank=True)
    formato_fecha = models.CharField('formato de la fecha', max_length=30, blank=True, help_text='Ej. %d/%m/%Y.')
    columna_hora = models.CharField('columna de la hora', max_length=100, blank=True)
    formato_hora = models.CharField('formato de la hora', max_length=30, blank=True, help_text='Ej. %H:%M:%S o %H:%M.')
    columna_tipo = models.CharField('columna de entrada/salida', max_length=100, blank=True,
                                    help_text='Vacía = el archivo no dice si es entrada o salida (se determina después).')
    valores_entrada = models.CharField('valores que significan entrada', max_length=150, blank=True,
                                       help_text='Separados por coma. Ej. E, IN, 0, Entrada.')
    valores_salida = models.CharField('valores que significan salida', max_length=150, blank=True,
                                      help_text='Separados por coma. Ej. S, OUT, 1, Salida.')
    columna_evento = models.CharField('columna del id de evento', max_length=100, blank=True,
                                      help_text='Si el reloj numera cada marca: se usa para detectar duplicados.')
    zona_horaria = models.CharField('zona horaria del archivo', max_length=60, default='America/Asuncion')
    activo = models.BooleanField('activo', default=True)
    version = models.PositiveIntegerField('versión', default=1, editable=False)

    class Meta:
        verbose_name = 'perfil de importación'
        verbose_name_plural = 'perfiles de importación'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['empresa', 'codigo'], name='perfil_importacion_codigo_unico')]

    def __str__(self):
        return self.nombre

    def clean(self):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        errores = {}
        if self.columna_fecha_hora:
            if not self.formato_fecha_hora:
                errores['formato_fecha_hora'] = 'Indicá el formato (ej. %d/%m/%Y %H:%M:%S).'
        elif not (self.columna_fecha and self.columna_hora):
            errores['columna_fecha_hora'] = 'Indicá la columna de fecha y hora, o la de fecha y la de hora por separado.'
        else:
            if not self.formato_fecha:
                errores['formato_fecha'] = 'Indicá el formato de la fecha (ej. %d/%m/%Y).'
            if not self.formato_hora:
                errores['formato_hora'] = 'Indicá el formato de la hora (ej. %H:%M:%S).'
        if self.columna_tipo and not (self.valores_entrada and self.valores_salida):
            errores['valores_entrada'] = 'Si hay columna de entrada/salida, indicá qué valores significan cada una.'
        for campo in ('formato_fecha_hora', 'formato_fecha', 'formato_hora'):
            if getattr(self, campo) and '%' not in getattr(self, campo):
                errores[campo] = 'Usá el formato de Python, ej. %d/%m/%Y.'
        try:
            ZoneInfo(self.zona_horaria)
        except (ZoneInfoNotFoundError, ValueError):
            errores['zona_horaria'] = 'Zona horaria desconocida (ej. America/Asuncion).'
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        if self.pk:
            self.version += 1
        super().save(*args, **kwargs)

    @staticmethod
    def _lista(texto):
        return {v.strip().lower() for v in texto.split(',') if v.strip()}

    @property
    def conjunto_entrada(self):
        return self._lista(self.valores_entrada)

    @property
    def conjunto_salida(self):
        return self._lista(self.valores_salida)


class LoteImportacion(RegistroEmpresa):
    """Un archivo importado. Sus filas quedan primero en revisión
    (`FilaImportacion`); recién al confirmar se crean las marcas, en una sola
    transacción. Revertir anula las marcas del lote (no las borra)."""

    VALIDADO = 'validado'
    CONFIRMADO = 'confirmado'
    CANCELADO = 'cancelado'
    REVERTIDO = 'revertido'
    ESTADO_OPCIONES = [(VALIDADO, 'Validado, sin confirmar'), (CONFIRMADO, 'Confirmado'),
                       (CANCELADO, 'Cancelado'), (REVERTIDO, 'Revertido')]

    reloj = models.ForeignKey(RelojExterno, on_delete=models.PROTECT, null=True, blank=True, related_name='lotes',
                              verbose_name='reloj externo')
    perfil = models.ForeignKey(PerfilImportacion, on_delete=models.PROTECT, related_name='lotes',
                               verbose_name='perfil de importación')
    perfil_version = models.PositiveIntegerField('versión del perfil', editable=False)
    modo = models.CharField('tipo de archivo', max_length=15, choices=PerfilImportacion.MODO_OPCIONES, editable=False)
    verificacion_identidad = models.BooleanField(
        'se verificó la identidad en el momento', default=False, editable=False,
        help_text='En un archivo nunca: se considera la fuente entregada por quien lo sube.')
    archivo = models.FileField('archivo', upload_to='importaciones/%Y/%m/', storage=almacenamiento_privado)
    nombre_archivo = models.CharField('nombre del archivo', max_length=255, editable=False)
    sha256 = models.CharField('huella SHA-256', max_length=64, editable=False, db_index=True)
    tamano = models.PositiveIntegerField('tamaño (bytes)', editable=False, default=0)
    periodo_desde = models.DateField('desde', null=True, blank=True)
    periodo_hasta = models.DateField('hasta', null=True, blank=True)
    estado = models.CharField('estado', max_length=12, choices=ESTADO_OPCIONES, default=VALIDADO, editable=False)
    total_filas = models.PositiveIntegerField('filas', default=0, editable=False)
    aceptadas = models.PositiveIntegerField('aceptadas', default=0, editable=False)
    rechazadas = models.PositiveIntegerField('rechazadas', default=0, editable=False)
    duplicadas = models.PositiveIntegerField('duplicadas', default=0, editable=False)
    confirmado_en = models.DateTimeField('confirmado el', null=True, blank=True, editable=False)
    confirmado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                       editable=False, related_name='+', verbose_name='confirmado por')
    motivo_reversion = models.CharField('motivo de reversión', max_length=250, blank=True, editable=False)
    notas = models.TextField('notas de quien lo sube', blank=True)
    aviso = models.CharField('aviso', max_length=250, blank=True, editable=False)

    class Meta:
        verbose_name = 'importación de marcaciones'
        verbose_name_plural = 'importaciones de marcaciones'
        ordering = ['-creado']
        permissions = [
            ('confirmar_importacion', 'Puede confirmar una importación de marcaciones'),
            ('revertir_importacion', 'Puede revertir una importación ya confirmada'),
        ]

    def __str__(self):
        return f'Lote {self.pk} · {self.nombre_archivo}'


class FilaImportacion(models.Model):
    VALIDA = 'valida'
    RECHAZADA = 'rechazada'
    DUPLICADA = 'duplicada'
    ESTADO_OPCIONES = [(VALIDA, 'Válida'), (RECHAZADA, 'Rechazada'), (DUPLICADA, 'Duplicada')]

    lote = models.ForeignKey(LoteImportacion, on_delete=models.CASCADE, related_name='filas', verbose_name='lote')
    numero_fila = models.PositiveIntegerField('fila del archivo')
    datos = models.JSONField('datos originales', default=list)
    codigo_en_archivo = models.CharField('empleado en el archivo', max_length=80, blank=True)
    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, null=True, blank=True,
                                 related_name='+', verbose_name='empleado')
    fecha_hora = models.DateTimeField('fecha y hora', null=True, blank=True)
    tipo = models.CharField('tipo', max_length=16, choices=Marcacion.TIPO_OPCIONES, blank=True)
    id_evento = models.CharField('id de evento', max_length=120, blank=True)
    huella = models.CharField('huella normalizada', max_length=64, blank=True, db_index=True)
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES)
    mensaje = models.CharField('motivo', max_length=250, blank=True)
    marcacion = models.ForeignKey(Marcacion, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
                                  verbose_name='marca creada')

    ruta_empresa = 'lote__empresa'

    class Meta:
        verbose_name = 'fila importada'
        verbose_name_plural = 'filas importadas'
        ordering = ['lote', 'numero_fila']
        constraints = [models.UniqueConstraint(fields=['lote', 'numero_fila'], name='fila_unica_por_lote')]

    def __str__(self):
        return f'Fila {self.numero_fila} · {self.get_estado_display()}'


class IntentoMarcacion(models.Model):
    """Cada intento rechazado en una terminal (QR vencido, código desconocido,
    marca repetida...): para auditar y detectar abusos."""

    empresa = models.ForeignKey('plataforma.Empresa', on_delete=models.PROTECT, related_name='+', verbose_name='empresa')
    terminal = models.ForeignKey(TerminalMarcacion, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name='intentos', verbose_name='terminal')
    fecha_hora = models.DateTimeField('fecha y hora', auto_now_add=True, db_index=True)
    metodo = models.CharField('método', max_length=12, choices=Marcacion.METODO_OPCIONES)
    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, null=True, blank=True,
                                 related_name='+', verbose_name='empleado (si se identificó)')
    codigo_rechazo = models.CharField('rechazo', max_length=30)
    mensaje = models.CharField('mensaje', max_length=250)
    ip = models.GenericIPAddressField('dirección IP', null=True, blank=True)

    ruta_empresa = 'empresa'
    ruta_sucursal = 'terminal__sucursal'

    class Meta:
        verbose_name = 'intento rechazado'
        verbose_name_plural = 'intentos rechazados'
        ordering = ['-fecha_hora']

    def __str__(self):
        return f'{self.fecha_hora:%d/%m/%Y %H:%M:%S} · {self.mensaje}'


class IncidenciaAsistencia(RegistroEmpresa):
    """Anomalía para que RR. HH. la revise. Las del marcador (secuencia
    incoherente) se crean al marcar; las del motor (tardanza, ausencia, marca
    faltante, extra sin autorizar…) las regenera cada cálculo del día, salvo
    las que alguien ya resolvió o justificó."""

    ENTRADA_SIN_SALIDA = 'entrada_sin_salida'
    SALIDA_SIN_ENTRADA = 'salida_sin_entrada'
    TARDANZA = 'tardanza'
    SALIDA_ANTICIPADA = 'salida_anticipada'
    AUSENCIA = 'ausencia'
    MARCA_FALTANTE = 'marca_faltante'
    EXTRA_SIN_AUTORIZAR = 'extra_sin_autorizar'
    TRABAJO_EN_DESCANSO = 'trabajo_en_descanso'
    TIPO_OPCIONES = [
        (ENTRADA_SIN_SALIDA, 'Entrada sin salida previa'), (SALIDA_SIN_ENTRADA, 'Salida sin entrada'),
        (TARDANZA, 'Llegada tarde'), (SALIDA_ANTICIPADA, 'Salida anticipada'), (AUSENCIA, 'Ausencia'),
        (MARCA_FALTANTE, 'Marca faltante'), (EXTRA_SIN_AUTORIZAR, 'Horas extra sin autorizar'),
        (TRABAJO_EN_DESCANSO, 'Trabajo en día franco o feriado'),
    ]
    PENDIENTE = 'pendiente'
    RESUELTA = 'resuelta'
    JUSTIFICADA = 'justificada'
    ESTADO_OPCIONES = [(PENDIENTE, 'Pendiente'), (RESUELTA, 'Resuelta'), (JUSTIFICADA, 'Justificada')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='incidencias_asistencia',
                                 verbose_name='empleado')
    fecha = models.DateField('fecha')
    tipo = models.CharField('tipo', max_length=24, choices=TIPO_OPCIONES)
    descripcion = models.CharField('descripción', max_length=250)
    marcacion = models.ForeignKey(Marcacion, on_delete=models.PROTECT, null=True, blank=True, related_name='incidencias',
                                  verbose_name='marca que la originó')
    minutos = models.PositiveIntegerField('minutos', default=0)
    automatica = models.BooleanField('la generó el cálculo del día', default=False, editable=False)
    estado = models.CharField('estado', max_length=12, choices=ESTADO_OPCIONES, default=PENDIENTE)
    resolucion = models.TextField('resolución', blank=True)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'incidencia de asistencia'
        verbose_name_plural = 'incidencias de asistencia'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'{self.empleado} · {self.fecha:%d/%m/%Y} · {self.get_tipo_display()}'


class DiaAsistencia(RegistroEmpresa):
    """Resultado del cálculo de un día de un empleado (asistencia/motor.py).
    Lo escribe solo el motor; se recalcula cuando cambian las marcas, los
    ajustes o las autorizaciones. `explicacion` dice cómo se llegó a cada número."""

    PRESENTE = 'presente'
    INCOMPLETO = 'incompleto'
    AUSENTE = 'ausente'
    FRANCO = 'franco'
    FERIADO = 'feriado'
    SIN_HORARIO = 'sin_horario'
    LICENCIA = 'licencia'
    ESTADO_OPCIONES = [(PRESENTE, 'Presente'), (INCOMPLETO, 'Incompleto (faltan marcas)'), (AUSENTE, 'Ausente'),
                       (FRANCO, 'Franco'), (FERIADO, 'Feriado'), (SIN_HORARIO, 'Sin horario asignado'),
                       (LICENCIA, 'Licencia o vacaciones')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='dias_asistencia',
                                 verbose_name='empleado')
    fecha = models.DateField('fecha', db_index=True)
    horario = models.ForeignKey('jornada.Horario', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                verbose_name='horario')
    horario_resumen = models.CharField('horario del día', max_length=250, blank=True)
    feriado = models.CharField('feriado', max_length=150, blank=True)
    licencia = models.ForeignKey('licencias.SolicitudLicencia', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='+', verbose_name='licencia del día')
    es_laborable = models.BooleanField('día laborable según el horario', default=False)
    primera_entrada = models.DateTimeField('primera entrada', null=True, blank=True)
    ultima_salida = models.DateTimeField('última salida', null=True, blank=True)
    minutos_programados = models.PositiveIntegerField('programados', default=0)
    minutos_trabajados = models.PositiveIntegerField('trabajados', default=0)
    minutos_descanso = models.PositiveIntegerField('descanso', default=0)
    minutos_tardanza = models.PositiveIntegerField('tardanza', default=0)
    minutos_salida_anticipada = models.PositiveIntegerField('salida anticipada', default=0)
    minutos_ordinarios = models.PositiveIntegerField('ordinarios', default=0)
    minutos_extra_candidatos = models.PositiveIntegerField('extra candidatos', default=0)
    minutos_extra_autorizados = models.PositiveIntegerField('extra autorizados', default=0)
    minutos_nocturnos = models.PositiveIntegerField('nocturnos', default=0)
    minutos_feriado = models.PositiveIntegerField('en feriado', default=0)
    marcas_faltantes = models.PositiveSmallIntegerField('marcas faltantes', default=0)
    estado = models.CharField('estado', max_length=12, choices=ESTADO_OPCIONES)
    explicacion = models.JSONField('cómo se calculó', default=list)
    version_calculo = models.PositiveIntegerField('cálculo n.º', default=1)
    calculado_en = models.DateTimeField('calculado el', null=True, blank=True)
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='+', verbose_name='revisado por')
    revisado_en = models.DateTimeField('revisado el', null=True, blank=True)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'día de asistencia'
        verbose_name_plural = 'días de asistencia'
        ordering = ['-fecha', 'empleado']
        constraints = [models.UniqueConstraint(fields=['empleado', 'fecha'], name='un_dia_por_empleado')]
        permissions = [
            ('calcular_asistencia', 'Puede calcular o recalcular la asistencia de un período'),
            ('revisar_asistencia', 'Puede marcar días de asistencia como revisados'),
        ]

    def __str__(self):
        return f'{self.empleado} · {self.fecha:%d/%m/%Y} · {self.get_estado_display()}'


class AjusteMarcacion(RegistroEmpresa):
    """Corrección de marcas: agregar una que faltó o anular una errónea.
    Nunca edita la marca original: al aprobarse crea una marca nueva
    (método manual) o anula la existente, con el motivo enlazado."""

    AGREGAR = 'agregar'
    ANULAR = 'anular'
    ACCION_OPCIONES = [(AGREGAR, 'Agregar una marca que faltó'), (ANULAR, 'Anular una marca errónea')]
    PENDIENTE = 'pendiente'
    APROBADO = 'aprobado'
    RECHAZADO = 'rechazado'
    ESTADO_OPCIONES = [(PENDIENTE, 'Pendiente'), (APROBADO, 'Aprobado'), (RECHAZADO, 'Rechazado')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='ajustes_marcacion',
                                 verbose_name='empleado')
    accion = models.CharField('qué corregir', max_length=8, choices=ACCION_OPCIONES, default=AGREGAR)
    fecha_hora = models.DateTimeField('fecha y hora de la marca', null=True, blank=True,
                                      help_text='Para agregar: cuándo entró o salió realmente.')
    tipo = models.CharField('tipo', max_length=16, choices=Marcacion.TIPO_OPCIONES[:2], blank=True)
    marcacion = models.ForeignKey(Marcacion, on_delete=models.PROTECT, null=True, blank=True, related_name='ajustes',
                                  verbose_name='marca a anular')
    motivo = models.CharField('motivo', max_length=250)
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=PENDIENTE, editable=False)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='resuelto por')
    aprobado_en = models.DateTimeField('resuelto el', null=True, blank=True, editable=False)
    motivo_rechazo = models.CharField('motivo del rechazo', max_length=250, blank=True, editable=False)
    marcacion_creada = models.ForeignKey(Marcacion, on_delete=models.PROTECT, null=True, blank=True, editable=False,
                                         related_name='+', verbose_name='marca creada')

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'ajuste de marcación'
        verbose_name_plural = 'ajustes de marcación'
        ordering = ['-creado']
        permissions = [('aprobar_ajuste', 'Puede aprobar o rechazar ajustes de marcación')]

    def __str__(self):
        return f'{self.get_accion_display()} · {self.empleado} · {self.get_estado_display()}'

    def clean(self):
        from django.utils import timezone
        errores = {}
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            errores['empleado'] = 'Tiene que ser un empleado de la misma empresa.'
        if self.accion == self.AGREGAR:
            if not self.fecha_hora:
                errores['fecha_hora'] = 'Indicá la fecha y hora de la marca que faltó.'
            elif self.fecha_hora > timezone.now():
                errores['fecha_hora'] = 'No puede ser futura.'
            if self.tipo not in (Marcacion.ENTRADA, Marcacion.SALIDA):
                errores['tipo'] = 'Indicá si fue entrada o salida.'
        else:
            if not self.marcacion_id:
                errores['marcacion'] = 'Elegí la marca a anular.'
            elif self.empleado_id and self.marcacion.empleado_id != self.empleado_id:
                errores['marcacion'] = 'La marca no es de este empleado.'
            elif self.marcacion.anulada:
                errores['marcacion'] = 'Esa marca ya está anulada.'
        if errores:
            raise ValidationError(errores)


class AutorizacionHorasExtra(RegistroEmpresa):
    """Autorización de horas extra de un día. Sin una autorización aprobada,
    las horas de más quedan como "candidatas" y no se pagan (§7)."""

    PENDIENTE = 'pendiente'
    APROBADA = 'aprobada'
    RECHAZADA = 'rechazada'
    ESTADO_OPCIONES = [(PENDIENTE, 'Pendiente'), (APROBADA, 'Aprobada'), (RECHAZADA, 'Rechazada')]

    empleado = models.ForeignKey('empleados.Empleado', on_delete=models.PROTECT, related_name='autorizaciones_extra',
                                 verbose_name='empleado')
    fecha = models.DateField('fecha')
    minutos_solicitados = models.PositiveIntegerField('minutos solicitados', validators=[MinValueValidator(1),
                                                                                        MaxValueValidator(16 * 60)])
    minutos_aprobados = models.PositiveIntegerField('minutos aprobados', null=True, blank=True, editable=False)
    motivo = models.CharField('motivo', max_length=250)
    estado = models.CharField('estado', max_length=10, choices=ESTADO_OPCIONES, default=PENDIENTE, editable=False)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name='+', verbose_name='resuelto por')
    aprobado_en = models.DateTimeField('resuelto el', null=True, blank=True, editable=False)
    motivo_rechazo = models.CharField('motivo del rechazo', max_length=250, blank=True, editable=False)

    ruta_sucursal = 'empleado__sucursal'
    ruta_empleado = 'empleado'

    class Meta:
        verbose_name = 'autorización de horas extra'
        verbose_name_plural = 'autorizaciones de horas extra'
        ordering = ['-fecha', '-id']
        permissions = [('aprobar_horas_extra', 'Puede aprobar o rechazar horas extra')]

    def __str__(self):
        return f'{self.empleado} · {self.fecha:%d/%m/%Y} · {self.minutos_solicitados} min · {self.get_estado_display()}'

    def clean(self):
        if self.empleado_id and self.empresa_id and self.empleado.empresa_id != self.empresa_id:
            raise ValidationError({'empleado': 'Tiene que ser un empleado de la misma empresa.'})