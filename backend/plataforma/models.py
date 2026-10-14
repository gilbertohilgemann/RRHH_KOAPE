from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from core.models import RegistroBase, RegistroEmpresa

# Identidad de Koape (logo: degradado magenta → rojo → naranja → amarillo).
# Es la de la plataforma y la de toda empresa que no cargue la suya.
COLOR_PRIMARIO_KOAPE = '#E9264B'
COLOR_SECUNDARIO_KOAPE = '#F7941D'

validar_color = RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Usá un color en formato #RRGGBB (ej. #E9264B).')
validar_direccion = RegexValidator(r'^[a-z0-9]+(-[a-z0-9]+)*$',
                                   'Solo minúsculas sin acentos, números y guiones (ej. delacosta o de-la-costa).')
# Primeros tramos de las direcciones de la aplicación y del servidor: una empresa no puede usarlos.
DIRECCIONES_RESERVADAS = {
    'admin', 'api', 'static', 'media', 'assets', 'ingresar', 'terminal', 'marcar', 'm', 'manual', 'asistencia', 'nomina',
    'recibos', 'reportes', 'vacaciones', 'mi-ficha', 'mi-marcacion', 'mi-asistencia', 'mis-licencias', 'mis-movimientos',
    'mis-recibos', 'koape-rrhh', 'plataforma', 'salir', 'login', 'www',
}


def _luminancia(color):
    """Luminancia relativa (WCAG 2.1) de un color #RRGGBB."""
    canales = []
    for i in (1, 3, 5):
        c = int(color[i:i + 2], 16) / 255
        canales.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = canales
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste_con_blanco(color):
    return 1.05 / (_luminancia(color) + 0.05)


class Empresa(RegistroBase):
    """Empresa empleadora. La crea el administrador de plataforma desde el
    admin; su administrador la puede editar desde la aplicación. Nunca se
    borra: se desactiva (los legajos, nóminas y la auditoría se conservan)."""

    nombre = models.CharField('nombre comercial', max_length=150, unique=True)
    direccion_acceso = models.CharField(
        'dirección de acceso', max_length=40, unique=True, null=True, blank=True, validators=[validar_direccion],
        help_text='La parte final de la dirección de ingreso propia de la empresa: hhrr.koapesystem.com/<dirección>. '
                  'Ahí el ingreso muestra su logo y sus colores, y solo entran sus usuarios. Vacía = sin dirección propia.')
    razon_social = models.CharField('razón social', max_length=200, blank=True)
    ruc = models.CharField('RUC', max_length=30, blank=True)
    # Datos para las obligaciones ante IPS y MTESS (fase 11).
    numero_patronal_ips = models.CharField('número patronal IPS', max_length=30, blank=True)
    numero_patronal_mtess = models.CharField('número patronal MTESS', max_length=30, blank=True)
    actividad = models.CharField('actividad económica', max_length=150, blank=True)
    direccion = models.CharField('dirección', max_length=250, blank=True)
    telefono = models.CharField('teléfono', max_length=50, blank=True)
    correo = models.EmailField('correo electrónico', blank=True)
    zona_horaria = models.CharField(
        'zona horaria', max_length=60, default='America/Asuncion',
        help_text='Las marcaciones se guardan en hora universal y se muestran en esta zona.',
    )
    moneda = models.CharField('moneda', max_length=3, default='PYG')
    # Personalización de la empresa: su logo y sus colores reemplazan a los de
    # Koape en la aplicación, los recibos y los informes. Vacíos = los de Koape.
    logo = models.ImageField('logo', upload_to='logos/empresas/', blank=True,
                             help_text='PNG, JPG o WEBP, idealmente con fondo transparente. Sale en la aplicación, '
                                       'los recibos y los informes.')
    color_primario = models.CharField(
        'color principal', max_length=7, blank=True, validators=[validar_color],
        help_text='Botones, menú y encabezados. Vacío = el de Koape. Tiene que ser lo bastante oscuro para '
                  'leer texto blanco encima.',
    )
    color_secundario = models.CharField(
        'color secundario', max_length=7, blank=True, validators=[validar_color],
        help_text='Detalles y franja del encabezado. Vacío = el de Koape.',
    )
    activa = models.BooleanField('activa', default=True,
                                 help_text='Una empresa inactiva no puede ingresar al sistema; sus datos se conservan.')

    ruta_empresa = ''

    class Meta:
        verbose_name = 'empresa'
        verbose_name_plural = 'empresas'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        # Vacía = NULL (varias empresas pueden no tener dirección propia sin chocar con la unicidad).
        self.direccion_acceso = (self.direccion_acceso or '').strip().lower() or None
        super().save(*args, **kwargs)

    def clean(self):
        if self.direccion_acceso:
            self.direccion_acceso = self.direccion_acceso.strip().lower()
            if self.direccion_acceso in DIRECCIONES_RESERVADAS:
                raise ValidationError({'direccion_acceso': 'Esa dirección la usa el sistema: elegí otra.'})
        # Los botones llevan texto blanco sobre el color principal: se exige
        # el contraste mínimo de WCAG para texto grande/negrita (3:1).
        if self.color_primario and validar_color.regex.match(self.color_primario) \
                and contraste_con_blanco(self.color_primario) < 3:
            raise ValidationError({'color_primario': 'Es demasiado claro: el texto blanco de los botones no se '
                                                     'leería. Elegí un tono más oscuro.'})

    def marca(self, request=None):
        """Logo y colores para la aplicación (los de Koape si faltan)."""
        logo = None
        if self.logo:
            logo = request.build_absolute_uri(self.logo.url) if request else self.logo.url
        return {
            'logo': logo,
            'color_primario': (self.color_primario or COLOR_PRIMARIO_KOAPE).upper(),
            'color_secundario': (self.color_secundario or COLOR_SECUNDARIO_KOAPE).upper(),
            'personalizada': bool(self.logo or self.color_primario or self.color_secundario),
        }


class Sucursal(RegistroEmpresa):
    """Sucursal o establecimiento de una empresa. Los usuarios se pueden
    limitar a ciertas sucursales (cuentas.Perfil.sucursales)."""

    codigo = models.CharField('código', max_length=30)
    nombre = models.CharField('nombre', max_length=150)
    direccion = models.CharField('dirección', max_length=250, blank=True)
    ciudad = models.CharField('ciudad', max_length=100, blank=True)
    telefono = models.CharField('teléfono', max_length=50, blank=True)
    activa = models.BooleanField('activa', default=True)

    ruta_sucursal = ''

    class Meta:
        verbose_name = 'sucursal'
        verbose_name_plural = 'sucursales'
        ordering = ['empresa', 'nombre']
        constraints = [
            models.UniqueConstraint(fields=['empresa', 'codigo'], name='sucursal_codigo_unico_por_empresa'),
        ]

    def __str__(self):
        return self.nombre
