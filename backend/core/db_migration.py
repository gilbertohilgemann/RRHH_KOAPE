"""Lógica compartida para pasar los datos de una base de datos Django a otra
(SQLite → PostgreSQL o viceversa). La usan tanto el comando de terminal
`manage.py migrate_to_postgres` como los botones del panel de admin
"Migración de Base de Datos" (`migracion/admin.py`) — un único lugar con la
lógica real, para que ambos caminos se comporten igual.

Estrategia: en vez de copiar tabla por tabla a mano (habría que resolver el
orden de FKs y las relaciones M2M), se usa `dumpdata`/`loaddata` de Django,
que ya sabe ordenar por dependencias y serializar M2M correctamente. Se
registra la base destino como un alias de conexión temporal
(`connections.databases[alias] = {...}`) en vez de tocar `settings.DATABASES`,
así no hace falta reiniciar el proceso para poder usarla."""
import io
import os
import tempfile

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from django.apps import apps
from django.core.management import call_command
from django.db import connections

EXCLUDED_APPS = ['contenttypes', 'auth.permission', 'admin.logentry', 'sessions.session', 'migracion']

# Windows + locale en español hace que Postgres devuelva sus mensajes de error
# en una codificación que psycopg2 no puede decodificar como UTF-8 (el
# carácter « rompe la conexión antes de poder mostrar el error real). Se
# fuerzan mensajes en inglés/ASCII para evitarlo.
_PG_CONNECT_OPTIONS = '-c lc_messages=C'

_CONNECTION_DEFAULTS = {
    'ATOMIC_REQUESTS': False,
    'AUTOCOMMIT': True,
    'CONN_MAX_AGE': 0,
    'CONN_HEALTH_CHECKS': False,
    'OPTIONS': {},
    'TIME_ZONE': None,
    'TEST': {'NAME': None, 'MIRROR': None, 'CHARSET': None, 'COLLATION': None},
}


def ensure_postgres_database_and_user(host, port, dbname, user, password, admin_user, admin_password, log):
    log(f'Conectando como administrador ("{admin_user}")...')
    conn = psycopg2.connect(
        host=host, port=port, user=admin_user, password=admin_password, dbname='postgres',
        options=_PG_CONNECT_OPTIONS,
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
    if cur.fetchone():
        # Ya existe: igual se fija la contraseña al valor del formulario, para
        # que nunca quede desincronizada con la que se usa después para conectar.
        cur.execute(f'ALTER USER "{user}" WITH PASSWORD %s', (password,))
        log(f'El usuario "{user}" ya existía; contraseña actualizada.')
    else:
        cur.execute(f'CREATE USER "{user}" WITH PASSWORD %s', (password,))
        log(f'Usuario "{user}" creado.')

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
    if cur.fetchone():
        log(f'La base de datos "{dbname}" ya existe.')
    else:
        cur.execute(f'CREATE DATABASE "{dbname}" OWNER "{user}"')
        log(f'Base de datos "{dbname}" creada.')

    cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{dbname}" TO "{user}"')
    cur.close()
    conn.close()

    conn2 = psycopg2.connect(
        host=host, port=port, user=admin_user, password=admin_password, dbname=dbname,
        options=_PG_CONNECT_OPTIONS,
    )
    conn2.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur2 = conn2.cursor()
    cur2.execute(f'GRANT ALL ON SCHEMA public TO "{user}"')
    cur2.close()
    conn2.close()


def register_postgres_connection(alias, host, port, dbname, user, password):
    # No se fuerza lc_messages acá: un usuario de la app sin privilegios de
    # superusuario no puede fijar ese parámetro por conexión.
    connections.databases[alias] = {
        **_CONNECTION_DEFAULTS,
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': dbname, 'USER': user, 'PASSWORD': password, 'HOST': host, 'PORT': port,
    }


def register_sqlite_connection(alias, path):
    connections.databases[alias] = {
        **_CONNECTION_DEFAULTS,
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': path,
    }


def test_connection(alias):
    with connections[alias].cursor() as cursor:
        cursor.execute('SELECT 1')


def build_schema(alias, log):
    log('Creando la estructura de tablas...')
    call_command('migrate', database=alias, interactive=False, verbosity=1)


def copy_data(source_alias, target_alias, log):
    log('Exportando los datos actuales...')
    buffer = io.StringIO()
    call_command('dumpdata', database=source_alias, exclude=EXCLUDED_APPS, stdout=buffer)
    data = buffer.getvalue()

    log('Cargando los datos en el destino...')
    fd, tmp_path = tempfile.mkstemp(suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(data)
        call_command('loaddata', tmp_path, database=target_alias)
    finally:
        os.unlink(tmp_path)


def verify_copy(source_alias, target_alias, log):
    """Después de copiar: misma cantidad de registros en cada tabla copiada y
    los mismos permisos en cada grupo (por nombre, no por id: dumpdata guarda
    los permisos por id y, si en la base nueva salieran con otros números,
    los perfiles quedarían con permisos cambiados). Devuelve la lista de
    diferencias (vacía = todo igual). Agregado 02/10/2026."""
    from django.contrib.auth.models import Group
    log('Verificando la copia...')
    excluidos = {e for e in EXCLUDED_APPS if '.' not in e}
    excluidos_modelos = {e for e in EXCLUDED_APPS if '.' in e}
    diferencias = []
    for model in apps.get_models():
        meta = model._meta
        if (not meta.managed or meta.proxy or meta.app_label in excluidos
                or f'{meta.app_label}.{meta.model_name}' in excluidos_modelos):
            continue
        origen = model.objects.using(source_alias).count()
        destino = model.objects.using(target_alias).count()
        if origen != destino:
            diferencias.append(f'{meta.label}: {origen} en el origen, {destino} en el destino')

    def permisos(alias):
        return {
            g.name: {f'{p.content_type.app_label}.{p.codename}' for p in g.permissions.using(alias).select_related('content_type')}
            for g in Group.objects.using(alias).all()
        }
    p_origen, p_destino = permisos(source_alias), permisos(target_alias)
    for grupo in sorted(set(p_origen) | set(p_destino)):
        if p_origen.get(grupo) != p_destino.get(grupo):
            diferencias.append(f'Permisos del grupo "{grupo}" distintos')
    log('Copia verificada: todo igual.' if not diferencias else f'{len(diferencias)} diferencia(s) en la copia.')
    return diferencias


def reset_sequences(alias, log):
    log('Reiniciando los contadores de ID...')
    app_labels = sorted({
        model._meta.app_label for model in apps.get_models()
        if model._meta.managed and model._meta.app_label != 'migracion'
    })
    buffer = io.StringIO()
    call_command('sqlsequencereset', *app_labels, database=alias, stdout=buffer)
    sql = buffer.getvalue()
    if sql.strip():
        with connections[alias].cursor() as cursor:
            cursor.execute(sql)
