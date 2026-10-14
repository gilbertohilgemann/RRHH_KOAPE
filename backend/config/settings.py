"""
Configuración de Django para Koape RR. HH. (legajos, asistencia y nómina).
"""

from pathlib import Path
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured
import os
import sys

# override=True: sin esto, una vez que una variable ya está en el entorno del
# proceso (por ejemplo, heredada del reinicio automático que hace
# migracion/admin.py al cambiar DB_ENGINE), load_dotenv() nunca la
# sobrescribe con el valor nuevo del archivo .env.
load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.getenv('DEBUG', 'True') == 'True'

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-solo-para-desarrollo-koape-rrhh'
    else:
        raise ImproperlyConfigured('Con DEBUG=False la SECRET_KEY es obligatoria (variable de entorno o backend/.env).')

# Clave (Fernet) con la que se cifran los números de cuenta bancaria
# (core/cifrado.py). La generan los instaladores una sola vez; si se pierde o
# se cambia, los números ya cifrados no se pueden leer más. En desarrollo,
# sin ella, se deriva de la SECRET_KEY.
CLAVE_CIFRADO = os.getenv('CLAVE_CIFRADO', '')
if not CLAVE_CIFRADO:
    if DEBUG:
        import base64
        import hashlib
        CLAVE_CIFRADO = base64.urlsafe_b64encode(hashlib.sha256(f'cifrado:{SECRET_KEY}'.encode()).digest()).decode()
    else:
        raise ImproperlyConfigured('Con DEBUG=False la CLAVE_CIFRADO es obligatoria (la genera el instalador en backend/.env).')

# En desarrollo (DEBUG=True) se acepta cualquier host: así se puede probar
# desde el celular u otra PC de la misma red sin ir agregando la IP local a
# mano cada vez que cambia. En producción (DEBUG=False) se exige la lista
# explícita que arma el instalador — ahí sí importa por seguridad.
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    # Tema del admin (administrador de plataforma): tiene que ir antes de
    # django.contrib.admin para reemplazar sus plantillas.
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Terceros
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',

    # Apps del negocio (una por dominio, ver docs/plan-fases.md)
    'core',
    'plataforma',
    'cuentas',
    'empleados',
    'contratos',
    'jornada',
    'asistencia',
    'licencias',
    'legal',
    'nomina',
    'novedades',
    'cumplimiento',

    # Infraestructura propia (patrón "sin tabla"). Tiene que ser la última:
    # cuentas/apps.py se engancha a su señal post_migrate.
    'migracion',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    # El admin solo por ip:puerto (ADMIN_HOSTS), nunca por el dominio.
    'core.middleware.AdminSoloPorHost',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# WhiteNoise sirve los estáticos del admin directo desde gunicorn (sin nginx
# delante): Django no sirve /static/ por sí solo con DEBUG=False.
if not DEBUG:
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# En las pruebas automáticas se usa un hash de contraseñas rápido (e
# inseguro): cada prueba crea varios usuarios y el hash real tarda a propósito.
EJECUTANDO_PRUEBAS = 'test' in sys.argv[1:2]
if EJECUTANDO_PRUEBAS:
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Base de datos - elegida por variable de entorno.
# DB_ENGINE=sqlite (por defecto) o DB_ENGINE=postgres (producción, o local si
# ya se migró desde el panel "Migración de Base de Datos").
if os.getenv('DB_ENGINE', 'sqlite') == 'postgres':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'rrhh_db'),
            'USER': os.getenv('DB_USER', 'rrhh_user'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-py'
# Fechas siempre dd/mm/aaaa (config/formatos/es/formats.py).
FORMAT_MODULE_PATH = ['config.formatos']
# La hora se guarda en UTC (USE_TZ) y se muestra en la de Paraguay.
TIME_ZONE = 'America/Asuncion'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Documentos confidenciales del legajo (contratos firmados, certificados
# médicos...): fuera de MEDIA_ROOT a propósito, porque /media/ se sirve a
# cualquiera. Se entregan solo por la API con control de permisos. El backup
# la incluye.
PRIVADO_ROOT = BASE_DIR / 'privado'
if EJECUTANDO_PRUEBAS:
    import tempfile
    PRIVADO_ROOT = Path(tempfile.mkdtemp(prefix='koape-rrhh-pruebas-'))

# En producción, whitenoise sirve los estáticos comprimidos y con hash en el
# nombre. En desarrollo se deja el storage por defecto: el manifest exige
# haber corrido `collectstatic` antes, cosa que no se hace en cada cambio.
if not DEBUG:
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        # No estricto: Jazzmin pide una carpeta como estático (core/estaticos.py).
        'staticfiles': {'BACKEND': 'core.estaticos.EstaticosProduccion'},
    }

# Los errores 500 se escriben en la salida del proceso, así quedan en el
# registro del servicio. Sin esto, con DEBUG=False Django solo los manda por
# correo a ADMINS, que no está configurado, y el error se pierde.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'consola': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'django': {'handlers': ['consola'], 'level': 'ERROR'},
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Dirección pública de la aplicación (frontend). La usa el manual del admin
# para enlazar el manual de la aplicación.
URL_APP = os.getenv('URL_APP', '')

# Direcciones (host:puerto) por las que responde el admin, ej. 1.2.3.4:8004.
# Por cualquier otra, /admin/ da 404 (core/middleware.py). Vacía = sin
# restricción (desarrollo local).
ADMIN_HOSTS = [h.strip().lower() for h in os.getenv('ADMIN_HOSTS', '').split(',') if h.strip()]

# CORS - habilita el frontend React. En desarrollo se acepta cualquier origen
# (mismo motivo que ALLOWED_HOSTS); en producción, la lista explícita que
# completa el instalador.
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:5204",
        "http://127.0.0.1:5204",
    ]
    _origenes_extra = os.getenv('CORS_ALLOWED_ORIGINS', '')
    if _origenes_extra:
        CORS_ALLOWED_ORIGINS += [o.strip() for o in _origenes_extra.split(',') if o.strip()]

# REST Framework
# Toda la API es privada: legajos y sueldos son datos sensibles. El frontend
# se autentica con token (header "Authorization: Token ..."), que evita los
# problemas de cookies/CSRF entre puertos distintos; la sesión queda para
# poder navegar la API desde el navegador estando logueado en /admin/.
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    # Denegación por defecto: hace falta el permiso de Django de cada
    # lectura y escritura; qué filas ve cada uno lo decide core/alcance.py.
    'DEFAULT_PERMISSION_CLASSES': [
        'core.api.permisos.TieneAlcance',
    ],
    'DEFAULT_PAGINATION_CLASS': 'core.api.paginacion.Paginacion',
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'SEARCH_PARAM': 'buscar',
    'ORDERING_PARAM': 'orden',
    # El único endpoint abierto es el de ingreso (login): se limita para que
    # no se pueda usar para probar contraseñas por fuerza bruta.
    'DEFAULT_THROTTLE_RATES': {
        'ingreso': '10/minute',
        # Pantalla de ingreso de cada empresa (/<dirección>): solo nombre, logo y colores.
        'acceso': '60/minute',
        # Marcador: QR que envía el empleado y consultas de cada terminal (su pantalla pregunta cada segundo).
        'qr': '12/minute',
        'terminal': '300/minute',
    },
}

# Admin de Django con el tema Jazzmin: es el panel del administrador de
# plataforma (Koape). Las empresas trabajan desde la app React.
JAZZMIN_SETTINGS = {
    'site_title': 'Koape RR. HH.',
    'site_header': 'Koape RR. HH.',
    'site_brand': 'Koape RR. HH.',
    'welcome_sign': 'Administración de la plataforma',
    # Identidad de Koape (core/static/core/): logo y acentos del degradado del logo.
    'site_logo': 'core/logo-koape.png',
    'login_logo': 'core/logo-koape.png',
    'site_logo_classes': '',
    'site_icon': 'core/logo-koape.png',
    'custom_css': 'core/admin-koape.css',
    'copyright': 'Koape Sistemas',
    'search_model': ['empleados.Empleado', 'auth.User'],
    'show_ui_builder': False,
    'order_with_respect_to': ['plataforma', 'auth', 'cuentas', 'empleados', 'core', 'migracion'],
    'icons': {
        'auth.User': 'fas fa-user',
        'auth.Group': 'fas fa-users-cog',
        'plataforma.Empresa': 'fas fa-building',
        'plataforma.Sucursal': 'fas fa-store',
        'cuentas.Perfil': 'fas fa-id-badge',
        'empleados.Empleado': 'fas fa-id-card',
        'empleados.Departamento': 'fas fa-sitemap',
        'empleados.Puesto': 'fas fa-briefcase',
        'empleados.CentroCosto': 'fas fa-coins',
        'empleados.HistorialAsignacion': 'fas fa-history',
        'core.EventoAuditoria': 'fas fa-clipboard-list',
        'migracion.MigracionBaseDatos': 'fas fa-database',
        'migracion.ManualUsuario': 'fas fa-book-open',
    },
}
JAZZMIN_UI_TWEAKS = {
    'navbar': 'navbar-white navbar-light',
    'sidebar': 'sidebar-light-danger',
    'brand_colour': 'navbar-white',
}

# El sistema puede correr detrás de nginx (reverse proxy + certificado SSL):
# gunicorn solo ve HTTP plano, así que sin esto Django cree que toda conexión
# es insegura. Este header lo agrega nginx en cada proxy_pass.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if not DEBUG:
    # Orígenes desde los que se envían formularios al admin (login, etc.).
    # Detrás de nginx con HTTPS, Django los exige para aceptar el login.
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]
    # Desactivable con SECURE_SSL_REDIRECT=False en .env para el período
    # inicial de pruebas por IP pública sin certificado todavía.
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True') == 'True'
    # Tienen que viajar juntos con SECURE_SSL_REDIRECT: por HTTP plano una
    # cookie "Secure" nunca se guarda y el login del admin queda en un loop.
    SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
    CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Importación de marcaciones CSV (fase 5): tamaño y cantidad de filas máximos por archivo.
IMPORTACION_MAX_BYTES = int(os.getenv('IMPORTACION_MAX_BYTES', 5 * 1024 * 1024))
IMPORTACION_MAX_FILAS = int(os.getenv('IMPORTACION_MAX_FILAS', 50000))
