import zipfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from migracion import backup


class FormatoDeFechasTests(TestCase):
    def test_fechas_dd_mm_aaaa(self):
        from datetime import date, datetime
        from django.utils import formats, translation
        with translation.override('es-py'):
            self.assertEqual(formats.date_format(date(2026, 10, 1)), '01/10/2026')
            self.assertEqual(formats.date_format(datetime(2026, 10, 1, 9, 5), 'DATETIME_FORMAT'), '01/10/2026 09:05')


class ManualAdminTests(TestCase):
    @override_settings(URL_APP='https://rrhh.ejemplo.test')
    def test_el_manual_abre_con_sus_enlaces(self):
        admin = User.objects.create_superuser('admin_prueba', password='clave-de-prueba')
        self.client.force_login(admin)
        r = self.client.get(reverse('admin:migracion_manualusuario_changelist'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Manual del administrador')
        self.assertContains(r, 'https://rrhh.ejemplo.test/manual')
        self.assertContains(r, reverse('admin:empleados_empleado_changelist'))

    def test_el_panel_de_migracion_abre(self):
        self.client.force_login(User.objects.create_superuser('admin_prueba', password='clave-de-prueba'))
        r = self.client.get(reverse('admin:migracion_migracionbasedatos_changelist'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Descargar backup completo')


class BackupTests(TestCase):
    def test_excluye_dependencias_y_todo_rastro_del_repositorio(self):
        import tempfile
        with tempfile.TemporaryDirectory() as carpeta:
            raiz = Path(carpeta)
            for ruta in ('backend/app.py', 'backend/privado/doc.pdf', 'backend/venv/x.py', 'frontend/node_modules/a.js',
                         '.git/config', '.github/workflows/ci.yml', '.gitignore', 'backend/__pycache__/a.pyc',
                         'logs/backend.log'):
                archivo = raiz / ruta
                archivo.parent.mkdir(parents=True, exist_ok=True)
                archivo.write_text('x')
            with mock.patch.object(backup, '_project_root', return_value=raiz):
                ruta_zip = backup.build_backup_zip(log=lambda m: None)
            try:
                with zipfile.ZipFile(ruta_zip) as zf:
                    nombres = zf.namelist()
            finally:
                Path(ruta_zip).unlink()
        self.assertIn(f'{backup.PREFIJO}/backend/app.py', nombres)
        self.assertIn(f'{backup.PREFIJO}/backend/privado/doc.pdf', nombres)
        for prohibido in ('venv', 'node_modules', '.git/', '.github', '.gitignore', '__pycache__', 'logs/'):
            self.assertFalse(any(prohibido in n for n in nombres), prohibido)
