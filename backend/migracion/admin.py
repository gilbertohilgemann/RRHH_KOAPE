"""Panel de administración "Migración de Base de Datos": migrar SQLite↔Postgres,
descargar un backup completo, y el "Manual de Usuario".

`MigracionBaseDatos` y `ManualUsuario` (en `models.py`) son modelos con
`managed = False`: no tienen tabla real, existen solo para que Django admin
les arme una entrada en el menú. Sus `ModelAdmin` sobreescriben
`changelist_view` para mostrar una página propia (formulario / manual) en vez
del listado estándar que esperaría un modelo real."""
import os
import sys
from pathlib import Path

from django.conf import settings as django_settings
from django.contrib import admin, messages
from django.http import FileResponse
from django.shortcuts import redirect, render
from django.urls import path

from core import db_migration
from . import backup as backup_module
from .models import ManualUsuario, MigracionBaseDatos

ENV_PATH = Path(django_settings.BASE_DIR) / '.env'


def current_engine():
    return os.getenv('DB_ENGINE', 'sqlite')


def write_env_db_settings(engine, **db_params):
    """Actualiza (o agrega) las líneas DB_* en .env, sin tocar el resto del archivo."""
    lines = ENV_PATH.read_text(encoding='utf-8').splitlines() if ENV_PATH.exists() else []

    values = {'DB_ENGINE': engine}
    if engine == 'postgres':
        values.update({
            'DB_NAME': db_params['dbname'],
            'DB_USER': db_params['user'],
            'DB_PASSWORD': db_params['password'],
            'DB_HOST': db_params['host'],
            'DB_PORT': db_params['port'],
        })

    seen = set()
    new_lines = []
    for line in lines:
        key = line.split('=', 1)[0] if '=' in line else None
        if key in values:
            new_lines.append(f'{key}={values[key]}')
            seen.add(key)
        else:
            new_lines.append(line)
    for key, value in values.items():
        if key not in seen:
            new_lines.append(f'{key}={value}')

    ENV_PATH.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')


def trigger_dev_reload():
    # Al tocar settings.py, el autoreload de `runserver` reinicia el proceso
    # solo y toma la nueva configuración de base de datos. En producción (sin
    # autoreload, gunicorn) hay que reiniciar el servicio: ./start.sh restart
    settings_module = sys.modules[django_settings.SETTINGS_MODULE]
    os.utime(Path(settings_module.__file__), None)


@admin.register(MigracionBaseDatos)
class MigracionAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        urls = [
            path('backup/', self.admin_site.admin_view(self.backup_view), name='migracion_backup'),
        ]
        return urls + super().get_urls()

    def backup_view(self, request):
        if not request.user.is_superuser:
            messages.error(request, 'Solo un superusuario puede descargar un backup.')
            return redirect('admin:index')

        zip_path = backup_module.build_backup_zip(log=lambda msg: None)
        response = FileResponse(open(zip_path, 'rb'), as_attachment=True, filename=os.path.basename(zip_path))
        response._resource_closers.append(lambda: os.unlink(zip_path))
        return response

    def changelist_view(self, request, extra_context=None):
        if not request.user.is_superuser:
            messages.error(request, 'Solo un superusuario puede administrar la base de datos.')
            return redirect('admin:index')

        if request.method == 'POST':
            self._handle_action(request)
            return redirect(request.path)

        context = {
            **self.admin_site.each_context(request),
            'title': 'Migración de Base de Datos',
            'opts': self.model._meta,
            'current_engine': current_engine(),
            'defaults': {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': os.getenv('DB_PORT', '5432'),
                'dbname': os.getenv('DB_NAME', 'rrhh_db'),
                'user': os.getenv('DB_USER', 'rrhh_user'),
            },
        }
        return render(request, 'admin/migracion/panel.html', context)

    def _handle_action(self, request):
        action = request.POST.get('action')
        log_lines = []

        def log(msg):
            log_lines.append(msg)

        try:
            if action == 'migrate_to_postgres':
                host = request.POST.get('host', 'localhost').strip()
                port = request.POST.get('port', '5432').strip()
                dbname = request.POST.get('dbname', '').strip()
                user = request.POST.get('user', '').strip()
                password = request.POST.get('password', '')
                admin_user = request.POST.get('admin_user', '').strip()
                admin_password = request.POST.get('admin_password', '')

                if not (dbname and user and password):
                    raise ValueError('Base de datos, usuario y contraseña son obligatorios.')

                if admin_user and admin_password:
                    db_migration.ensure_postgres_database_and_user(
                        host, port, dbname, user, password, admin_user, admin_password, log,
                    )

                db_migration.register_postgres_connection('postgres_target', host, port, dbname, user, password)
                db_migration.test_connection('postgres_target')
                db_migration.build_schema('postgres_target', log)
                db_migration.copy_data('default', 'postgres_target', log)
                db_migration.reset_sequences('postgres_target', log)
                diferencias = db_migration.verify_copy('default', 'postgres_target', log)
                if diferencias:
                    raise ValueError('La copia no coincide con el origen (no se cambió la base): ' + '; '.join(diferencias[:5]))

                write_env_db_settings('postgres', host=host, port=port, dbname=dbname, user=user, password=password)
                trigger_dev_reload()

                messages.success(
                    request,
                    'Datos migrados a PostgreSQL. El sistema va a empezar a usarla en unos segundos '
                    '(en desarrollo el servidor se reinicia solo). En producción: ./start.sh restart'
                )

            elif action == 'switch_to_sqlite':
                write_env_db_settings('sqlite')
                trigger_dev_reload()
                messages.success(
                    request,
                    'Volviendo a SQLite (los datos que ya tenía siguen intactos). '
                    'En desarrollo el servidor se reinicia solo; en producción: ./start.sh restart'
                )

            elif action == 'sync_postgres_to_sqlite':
                sqlite_path = str(Path(django_settings.BASE_DIR) / 'db.sqlite3')
                db_migration.register_sqlite_connection('sqlite_target', sqlite_path)
                db_migration.build_schema('sqlite_target', log)
                db_migration.copy_data('default', 'sqlite_target', log)
                messages.success(
                    request,
                    'Datos actuales de PostgreSQL copiados a SQLite (se reemplazó lo que hubiera ahí).'
                )

            else:
                raise ValueError('Acción desconocida.')

        except Exception as e:
            messages.error(request, f'Error: {e}')

        for line in log_lines:
            messages.info(request, line)


@admin.register(ManualUsuario)
class ManualAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Dirección de la aplicación (para enlazar el manual de la aplicación):
        # la de URL_APP en el .env, o la misma máquina en el puerto 5204.
        url_app = django_settings.URL_APP or f'{request.scheme}://{request.get_host().split(":")[0]}:5204'
        context = {
            **self.admin_site.each_context(request),
            'title': 'Manual del administrador',
            'opts': self.model._meta,
            'url_app': url_app.rstrip('/'),
        }
        return render(request, 'admin/migracion/manual.html', context)
