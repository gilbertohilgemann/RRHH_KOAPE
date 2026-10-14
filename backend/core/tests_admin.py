"""El admin responde solo por la dirección de ADMIN_HOSTS (core/middleware.py)."""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

DOMINIO = 'rrhh.ejemplo.test'
IP_ADMIN = '10.0.0.5:8004'


@override_settings(ALLOWED_HOSTS=[DOMINIO, '10.0.0.5'], ADMIN_HOSTS=[IP_ADMIN])
class AdminSoloPorHostTests(TestCase):
    def test_por_el_dominio_el_admin_no_existe(self):
        self.assertEqual(self.client.get('/admin/', HTTP_HOST=DOMINIO).status_code, 404)

    def test_por_el_dominio_tampoco_con_sesion_de_superusuario(self):
        self.client.force_login(User.objects.create_superuser('jefe', password='x'))
        self.assertEqual(self.client.get('/admin/', HTTP_HOST=DOMINIO).status_code, 404)

    def test_por_ip_y_puerto_el_admin_responde(self):
        self.assertEqual(self.client.get('/admin/login/', HTTP_HOST=IP_ADMIN).status_code, 200)

    def test_la_api_sigue_por_el_dominio(self):
        r = self.client.post('/api/sesion/ingresar/', {'usuario': 'nadie', 'clave': 'x'}, HTTP_HOST=DOMINIO)
        self.assertNotEqual(r.status_code, 404)


@override_settings(ADMIN_HOSTS=[])
class AdminSinRestriccionTests(TestCase):
    def test_sin_admin_hosts_responde_por_cualquier_host(self):
        self.assertEqual(self.client.get('/admin/login/').status_code, 200)


class CrearAdminTests(TestCase):
    def test_es_idempotente_y_resetea_la_clave(self):
        from django.core.management import call_command
        from io import StringIO
        call_command('crear_admin', stdout=StringIO())
        usuario = User.objects.get(username='admin')
        usuario.set_password('otra')
        usuario.save()
        call_command('crear_admin', stdout=StringIO())
        usuario.refresh_from_db()
        self.assertTrue(usuario.is_superuser)
        self.assertTrue(usuario.check_password('Admin*2026'))
        self.assertEqual(User.objects.filter(username='admin').count(), 1)
