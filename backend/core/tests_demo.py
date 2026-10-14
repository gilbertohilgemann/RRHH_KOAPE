from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from empleados.models import Empleado
from plataforma.models import Empresa


class DatosDemoTests(TestCase):
    def test_crea_la_empresa_demo_y_es_idempotente(self):
        call_command('cargar_datos_demo', clave='Clave-demo-123', stdout=StringIO())
        call_command('cargar_datos_demo', clave='Clave-demo-123', stdout=StringIO())
        empresa = Empresa.objects.get(nombre='Empresa Demo S.A.')
        self.assertEqual(Empleado.objects.filter(empresa=empresa).count(), 8)

    def test_cada_usuario_demo_entra_con_su_perfil(self):
        call_command('cargar_datos_demo', clave='Clave-demo-123', stdout=StringIO())
        esperado = {'admin_demo': 'administrador', 'gestor_demo': 'gestor', 'empleado_demo': 'empleado'}
        for usuario, nivel in esperado.items():
            r = APIClient().post('/api/sesion/ingresar/', {'usuario': usuario, 'clave': 'Clave-demo-123'})
            self.assertEqual(r.status_code, 200, usuario)
            self.assertEqual(r.data['usuario']['nivel'], nivel)
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION='Token ' + APIClient().post(
            '/api/sesion/ingresar/', {'usuario': 'empleado_demo', 'clave': 'Clave-demo-123'}).data['token'])
        self.assertEqual(cliente.get('/api/empleados/').data['count'], 1)
