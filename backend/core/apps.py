from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'
    verbose_name = 'Núcleo y auditoría'

    def ready(self):
        from django.contrib import admin
        admin.site.site_header = 'Koape RR. HH. — Administración'
        admin.site.site_title = 'Koape RR. HH.'
        admin.site.index_title = 'Administración de la plataforma'
        # El link "Ver sitio" apuntaría al propio puerto del backend (donde
        # vive el admin) y no a la app (frontend, otro puerto). Se saca en vez
        # de arreglarlo: el template no lo muestra si es None.
        admin.site.site_url = None
