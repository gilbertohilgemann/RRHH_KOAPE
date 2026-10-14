"""Personalización de cada empresa: logo y colores."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from core.datos_prueba import EscenarioMixin
from core.models import EventoAuditoria
from plataforma.models import COLOR_PRIMARIO_KOAPE, contraste_con_blanco


def imagen(formato='PNG', nombre='logo.png'):
    salida = io.BytesIO()
    Image.new('RGBA' if formato == 'PNG' else 'RGB', (40, 40), (233, 38, 75, 255)).save(salida, formato)
    return SimpleUploadedFile(nombre, salida.getvalue(), content_type=f'image/{formato.lower()}')


class MarcaEmpresaTests(EscenarioMixin, TestCase):
    def test_sin_personalizar_la_sesion_trae_la_marca_de_koape(self):
        marca = self.cliente(self.gestor1).get('/api/sesion/yo/').data['marca']
        self.assertEqual(marca['color_primario'], COLOR_PRIMARIO_KOAPE)
        self.assertIsNone(marca['logo'])
        self.assertFalse(marca['personalizada'])

    def test_el_color_de_koape_se_lee_con_texto_blanco(self):
        self.assertGreaterEqual(contraste_con_blanco(COLOR_PRIMARIO_KOAPE), 3)

    def test_administrador_cambia_los_colores_y_todos_los_de_su_empresa_los_ven(self):
        r = self.cliente(self.admin1).patch(f'/api/empresas/{self.e1.pk}/', {'color_primario': '#1d4ed8', 'color_secundario': '#f59e0b'})
        self.assertEqual(r.status_code, 200, r.data)
        # Recargado: el de setUpTestData trae la empresa en memoria de antes del cambio.
        ana = type(self.usr_ana).objects.get(pk=self.usr_ana.pk)
        marca = self.cliente(ana).get('/api/sesion/yo/').data['marca']
        self.assertEqual(marca['color_primario'], '#1D4ED8')
        self.assertTrue(marca['personalizada'])
        # La otra empresa sigue con lo suyo.
        self.assertEqual(self.cliente(self.admin2).get('/api/sesion/yo/').data['marca']['color_primario'], COLOR_PRIMARIO_KOAPE)

    def test_color_mal_escrito_o_demasiado_claro_se_rechaza(self):
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.patch(f'/api/empresas/{self.e1.pk}/', {'color_primario': 'rojo'}).status_code, 400)
        r = cliente.patch(f'/api/empresas/{self.e1.pk}/', {'color_primario': '#FFFF66'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('claro', str(r.data['color_primario']))

    def test_gestor_no_personaliza(self):
        cliente = self.cliente(self.gestor1)
        self.assertEqual(cliente.patch(f'/api/empresas/{self.e1.pk}/', {'color_primario': '#1D4ED8'}).status_code, 403)
        self.assertEqual(cliente.post(f'/api/empresas/{self.e1.pk}/logo/', {'logo': imagen()}, format='multipart').status_code, 403)


@override_settings(MEDIA_ROOT=__import__('tempfile').mkdtemp(prefix='koape-rrhh-media-'))
class LogoEmpresaTests(EscenarioMixin, TestCase):
    def test_subir_y_quitar_el_logo_con_auditoria(self):
        cliente = self.cliente(self.admin1)
        r = cliente.post(f'/api/empresas/{self.e1.pk}/logo/', {'logo': imagen()}, format='multipart')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['marca']['logo'].startswith('http'))
        self.assertTrue(EventoAuditoria.objects.filter(descripcion='Logo cambiado.', objeto_id=str(self.e1.pk)).exists())
        r = cliente.delete(f'/api/empresas/{self.e1.pk}/logo/')
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data['marca']['logo'])

    def test_solo_imagenes_de_mapa_de_bits(self):
        svg = SimpleUploadedFile('logo.svg', b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                                 content_type='image/svg+xml')
        r = self.cliente(self.admin1).post(f'/api/empresas/{self.e1.pk}/logo/', {'logo': svg}, format='multipart')
        self.assertEqual(r.status_code, 400)

    def test_no_toca_el_logo_de_otra_empresa(self):
        r = self.cliente(self.admin1).post(f'/api/empresas/{self.e2.pk}/logo/', {'logo': imagen()}, format='multipart')
        self.assertEqual(r.status_code, 404)
