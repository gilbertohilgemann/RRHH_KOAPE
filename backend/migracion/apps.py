from django.apps import AppConfig
from django.contrib import admin


class MigracionConfig(AppConfig):
    name = 'migracion'
    verbose_name = 'Migración de Base de Datos'

    def ready(self):
        # Empuja esta sección al final del panel de administración, sin
        # importar el orden alfabético del resto de las apps. Y dentro de
        # ella, deja "Migración" primero y "Manual de Usuario" justo debajo
        # (alfabéticamente "Manual" iría antes que "Migración").
        original_get_app_list = admin.site.get_app_list
        orden_modelos = ['MigracionBaseDatos', 'ManualUsuario']

        def get_app_list(request, app_label=None):
            app_list = original_get_app_list(request, app_label)
            app_list.sort(key=lambda app: app['app_label'] == 'migracion')
            for app in app_list:
                if app['app_label'] == 'migracion':
                    app['models'].sort(
                        key=lambda m: orden_modelos.index(m['object_name'])
                        if m['object_name'] in orden_modelos else 99
                    )
            return app_list

        admin.site.get_app_list = get_app_list
