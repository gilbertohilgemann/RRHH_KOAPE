from django.conf import settings
from django.db import models


class RegistroBase(models.Model):
    """Campos de auditoría comunes a todo registro del sistema: quién lo creó
    y cuándo, y quién lo modificó por última vez y cuándo. Se completan solos
    (API y admin); nunca los elige el usuario.

    SET_NULL y no CASCADE a propósito: dar de baja a un usuario no puede
    borrar el historial laboral que cargó.

    Cada modelo declara cómo se llega desde él a su empresa, su sucursal y su
    empleado, para el filtro de aislamiento (core/alcance.py):
    - `ruta_empresa`: '' = el propio modelo es la empresa; None = no pertenece
      a ninguna (no se puede consultar por la API sin una regla propia).
    - `ruta_sucursal`: si está, un usuario limitado a ciertas sucursales solo
      ve los registros de esas sucursales.
    - `ruta_empleado`: si está, el perfil Empleado ve los registros de su
      propio legajo (y nada más)."""

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        editable=False, related_name='+', verbose_name='creado por',
    )
    creado = models.DateTimeField('fecha de carga', auto_now_add=True)
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        editable=False, related_name='+', verbose_name='modificado por',
    )
    modificado = models.DateTimeField('última modificación', auto_now=True)

    ruta_empresa = None
    ruta_sucursal = None
    ruta_empleado = None

    class Meta:
        abstract = True


class RegistroEmpresa(RegistroBase):
    """Registro que pertenece directamente a una empresa. La empresa la fija
    la API según el usuario (core/api/base.py): nunca se confía en la que
    mande el navegador."""

    empresa = models.ForeignKey(
        'plataforma.Empresa', on_delete=models.PROTECT,
        related_name='%(app_label)s_%(class)s_set', verbose_name='empresa',
    )

    ruta_empresa = 'empresa'

    class Meta:
        abstract = True


class CatalogoEmpresa(RegistroBase):
    """Catálogo con ítems globales (empresa vacía, los carga la plataforma y
    los ven todas) más los propios de cada empresa. Una empresa ve los
    globales y los suyos, pero solo modifica los suyos (core/api/base.py,
    `CatalogoViewSet`)."""

    empresa = models.ForeignKey(
        'plataforma.Empresa', on_delete=models.PROTECT, null=True, blank=True,
        related_name='%(app_label)s_%(class)s_set', verbose_name='empresa',
        help_text='Vacío = ítem global, disponible para todas las empresas.',
    )

    ruta_empresa = 'empresa'

    class Meta:
        abstract = True

    @classmethod
    def filtrar_por_alcance(cls, queryset, usuario):
        from core import alcance
        empresa = alcance.empresa_de(usuario)
        if empresa is None:
            return queryset.none()
        return queryset.filter(models.Q(empresa__isnull=True) | models.Q(empresa=empresa))

    @property
    def es_global(self):
        return self.empresa_id is None


class EventoAuditoria(models.Model):
    """Bitácora de auditoría: cada alta, modificación, baja y acción
    relevante (ingresos, cambios de perfiles, cierres...) con quién, cuándo,
    qué registro y los valores anteriores y nuevos. Nunca se edita ni se
    borra: el admin la muestra de solo lectura y la API no tiene escritura.

    Reemplaza al EventLog común que pedía la especificación (en este sistema
    no existía uno previo). Se escribe con `core.auditoria.registrar()`."""

    ALTA = 'alta'
    MODIFICACION = 'modificacion'
    BAJA = 'baja'
    BORRADO = 'borrado'
    INGRESO = 'ingreso'
    INGRESO_FALLIDO = 'ingreso_fallido'
    PERMISOS = 'permisos'
    ACCION = 'accion'
    ACCION_OPCIONES = [
        (ALTA, 'Alta'),
        (MODIFICACION, 'Modificación'),
        (BAJA, 'Baja lógica'),
        (BORRADO, 'Borrado'),
        (INGRESO, 'Ingreso al sistema'),
        (INGRESO_FALLIDO, 'Ingreso fallido'),
        (PERMISOS, 'Cambio de perfiles o permisos'),
        (ACCION, 'Otra acción'),
    ]

    fecha = models.DateTimeField('fecha y hora', auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='usuario',
    )
    # Se guarda también el nombre: si el usuario se borra, la bitácora sigue
    # diciendo quién fue.
    nombre_usuario = models.CharField('nombre de usuario', max_length=150, blank=True)
    empresa = models.ForeignKey(
        'plataforma.Empresa', on_delete=models.PROTECT, null=True, blank=True,
        related_name='eventos_auditoria', verbose_name='empresa',
    )
    accion = models.CharField('acción', max_length=20, choices=ACCION_OPCIONES)
    modelo = models.CharField('tipo de registro', max_length=100, blank=True, help_text='app.Modelo')
    objeto_id = models.CharField('id del registro', max_length=50, blank=True)
    objeto_texto = models.CharField('registro', max_length=250, blank=True)
    descripcion = models.TextField('descripción', blank=True)
    datos_anteriores = models.JSONField('valores anteriores', null=True, blank=True)
    datos_nuevos = models.JSONField('valores nuevos', null=True, blank=True)
    ip = models.GenericIPAddressField('dirección IP', null=True, blank=True)

    ruta_empresa = 'empresa'

    class Meta:
        verbose_name = 'evento de auditoría'
        verbose_name_plural = 'auditoría'
        ordering = ['-fecha', '-id']
        indexes = [models.Index(fields=['modelo', 'objeto_id'])]

    def __str__(self):
        return f'{self.fecha:%d/%m/%Y %H:%M} · {self.nombre_usuario or "sistema"} · {self.get_accion_display()}'
