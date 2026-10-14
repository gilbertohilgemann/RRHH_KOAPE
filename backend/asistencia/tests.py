"""Marcador propio: criterios de aceptación de la especificación (§6 bis),
con el QR invertido (la terminal lo proyecta, el empleado lo escanea con su
sesión; decisión del cliente, 14/10/2026)."""
import io
import re
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from asistencia.models import (ConfiguracionMarcacion, CredencialMarcacion, IncidenciaAsistencia, IntentoMarcacion,
                               Marcacion, QRDinamico, TerminalMarcacion)
from core import alcance
from core.datos_prueba import EscenarioMixin, crear_usuario
from core.models import EventoAuditoria
from empleados.models import Empleado


def foto_png():
    salida = io.BytesIO()
    Image.new('RGB', (900, 1200), (200, 150, 120)).save(salida, 'PNG')
    return SimpleUploadedFile('foto.png', salida.getvalue(), content_type='image/png')


class MarcadorMixin(EscenarioMixin):
    def setUp(self):
        # Los límites de pedidos se cuentan en la caché: cada prueba arranca de cero.
        from django.core.cache import cache
        cache.clear()
        self.config = ConfiguracionMarcacion.de(self.e1)
        self.config.permite_codigo_fijo = True
        self.config.segundos_antirrebote = 0
        self.config.save()
        self.terminal = TerminalMarcacion.objects.create(empresa=self.e1, codigo='T1', nombre='Entrada principal')
        self.clave = self.terminal.generar_clave()
        self.terminal_e2 = TerminalMarcacion.objects.create(empresa=self.e2, codigo='T1', nombre='Otra empresa')
        self.clave_e2 = self.terminal_e2.generar_clave()

    def lector(self, clave=None):
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f'Terminal {clave or self.clave}')
        return cliente

    def pantalla(self, clave=None, actual=None, desde=None):
        """Lo que pide la pantalla de la terminal cada segundo."""
        params = {k: v for k, v in (('actual', actual), ('desde', desde)) if v is not None}
        return self.lector(clave).get('/api/terminal/qr/', params).data

    def token_en_pantalla(self, clave=None):
        return self.pantalla(clave)['qr']['token']

    def escanear(self, token, usuario=None, tipo=None):
        datos = {'token': token, **({'tipo': tipo} if tipo else {})}
        return self.cliente(usuario or self.usr_ana).post('/api/marcador/qr/', datos)


class QRDinamicoTests(MarcadorMixin, TestCase):
    def test_la_terminal_proyecta_el_empleado_escanea_y_ambas_pantallas_lo_muestran(self):
        datos = self.pantalla()
        token, id_qr = datos['qr']['token'], datos['qr']['id']
        self.assertNotEqual(QRDinamico.objects.get(pk=id_qr).token_huella, token)  # solo la huella
        # Mientras no cambie, la pantalla no vuelve a recibir el token.
        self.assertIsNone(self.pantalla(actual=id_qr)['qr']['token'])
        r = self.escanear(token)
        self.assertEqual(r.data['resultado'], 'ok', r.data)
        self.assertEqual(r.data['legajo'], self.ana.codigo)
        self.assertEqual(r.data['empleado'], 'Ana Apellido E001')
        self.assertRegex(r.data['hora'], r'^\d{2}:\d{2}:\d{2}$')
        self.assertEqual(r.data['terminal'], 'Entrada principal')
        marca = Marcacion.objects.get(empleado=self.ana)
        self.assertEqual((marca.metodo, marca.nivel_verificacion, marca.terminal, marca.qr_id),
                         ('qr', 'qr_autenticado', self.terminal, id_qr))
        # La pantalla de la terminal recibe la misma marca y un QR nuevo (era de un solo uso).
        pantalla = self.pantalla(actual=id_qr, desde=0)
        self.assertEqual([e['id'] for e in pantalla['eventos']], [marca.pk])
        self.assertEqual(pantalla['eventos'][0]['hora'], r.data['hora'])
        self.assertNotEqual(pantalla['qr']['id'], id_qr)
        self.assertIsNotNone(pantalla['qr']['token'])
        self.assertEqual(self.pantalla(actual=pantalla['qr']['id'], desde=marca.pk)['eventos'], [])

    def test_un_qr_usado_no_sirve_para_otro(self):
        token = self.token_en_pantalla()
        self.assertEqual(self.escanear(token).data['resultado'], 'ok')
        beto = crear_usuario('beto', self.e1, [alcance.GRUPO_EMPLEADO], empleado=self.beto)
        r = self.escanear(token, beto)
        self.assertEqual(r.data['codigo'], 'qr_usado')
        self.assertFalse(Marcacion.objects.filter(empleado=self.beto).exists())

    def test_sin_un_solo_uso_varios_marcan_con_el_mismo(self):
        self.config.qr_un_solo_uso = False
        self.config.save()
        token = self.token_en_pantalla()
        beto = crear_usuario('beto', self.e1, [alcance.GRUPO_EMPLEADO], empleado=self.beto)
        self.assertEqual(self.escanear(token).data['resultado'], 'ok')
        self.assertEqual(self.escanear(token, beto).data['resultado'], 'ok')
        self.assertEqual(QRDinamico.objects.get().usos, 2)

    def test_vencido_se_rechaza_pero_con_unos_segundos_de_gracia(self):
        token = self.token_en_pantalla()
        QRDinamico.objects.update(vence_en=timezone.now() - timedelta(seconds=5))
        self.assertEqual(self.escanear(token).data['resultado'], 'ok')
        token = self.token_en_pantalla()
        QRDinamico.objects.filter(estado='vigente').update(vence_en=timezone.now() - timedelta(seconds=30))
        r = self.escanear(token)
        self.assertEqual(r.data['codigo'], 'qr_vencido')
        self.assertTrue(IntentoMarcacion.objects.filter(codigo_rechazo='qr_vencido', empleado=self.ana).exists())

    def test_qr_reemplazado_por_otra_pantalla_no_sirve(self):
        viejo = self.token_en_pantalla()
        self.token_en_pantalla()  # recarga de la pantalla: otro QR
        self.assertEqual(self.escanear(viejo).data['codigo'], 'qr_vencido')

    def test_qr_de_otra_empresa_se_rechaza(self):
        r = self.escanear(self.token_en_pantalla(self.clave_e2))
        self.assertEqual(r.data['codigo'], 'qr_otra_empresa')
        self.assertFalse(Marcacion.objects.exists())

    def test_qr_inventado(self):
        self.assertEqual(self.escanear('inventado').data['codigo'], 'qr_desconocido')

    def test_solo_un_empleado_activo_con_su_sesion(self):
        token = self.token_en_pantalla()
        self.assertEqual(self.escanear(token, self.gestor1).status_code, 403)
        self.assertEqual(self.escanear(token, self.admin1).status_code, 403)
        self.assertEqual(APIClient().post('/api/marcador/qr/', {'token': token}).status_code, 401)
        self.assertIn(self.lector().post('/api/marcador/qr/', {'token': token}).status_code, (401, 403))
        Empleado.objects.filter(pk=self.ana.pk).update(estado=Empleado.BAJA)
        self.assertEqual(self.escanear(token).data['codigo'], 'empleado_inactivo')

    def test_qr_deshabilitado(self):
        token = self.token_en_pantalla()
        self.config.permite_qr = False
        self.config.save()
        self.assertIsNone(self.pantalla()['qr'])
        self.assertEqual(self.escanear(token).data['codigo'], 'qr_deshabilitado')

    def test_terminal_solo_codigo_no_muestra_qr(self):
        self.terminal.tipo = TerminalMarcacion.CODIGO_FIJO
        self.terminal.save()
        self.assertIsNone(self.pantalla()['qr'])

    def test_terminal_inactiva(self):
        token = self.token_en_pantalla()
        TerminalMarcacion.objects.filter(pk=self.terminal.pk).update(activa=False)
        self.assertEqual(self.escanear(token).data['codigo'], 'terminal_inactiva')


class SecuenciaTests(MarcadorMixin, TestCase):
    def marcar(self, tipo=None):
        return self.escanear(self.token_en_pantalla(), tipo=tipo).data

    def test_automatico_alterna_entrada_y_salida(self):
        self.assertEqual(self.marcar()['tipo'], 'entrada')
        self.assertEqual(self.marcar()['tipo'], 'salida')
        self.assertEqual(self.marcar()['tipo'], 'entrada')
        self.assertFalse(IncidenciaAsistencia.objects.exists())

    def test_entrada_vieja_no_se_empareja(self):
        self.marcar()
        Marcacion.objects.update(fecha_hora=timezone.now() - timedelta(hours=20))
        self.assertEqual(self.marcar()['tipo'], 'entrada')

    def test_repeticiones_incoherentes_generan_incidencia_sin_tocar_las_marcas(self):
        self.config.modo_accion = ConfiguracionMarcacion.EXPLICITA
        self.config.save()
        self.assertEqual(self.marcar()['codigo'], 'falta_tipo')
        self.assertEqual(self.marcar('entrada')['resultado'], 'ok')
        r = self.marcar('entrada')
        self.assertEqual(r['resultado'], 'ok')
        self.assertIn('Entrada sin salida', r['aviso'])
        self.assertEqual(Marcacion.objects.filter(empleado=self.ana).count(), 2)
        self.assertEqual(IncidenciaAsistencia.objects.get().tipo, IncidenciaAsistencia.ENTRADA_SIN_SALIDA)

    def test_antirrebote_sin_gastar_el_qr(self):
        self.config.segundos_antirrebote = 60
        self.config.save()
        self.marcar()
        token = self.token_en_pantalla()
        self.assertEqual(self.escanear(token).data['codigo'], 'repetida')
        self.assertEqual(Marcacion.objects.count(), 1)
        # El rechazo no consumió el QR: otro empleado lo puede usar.
        self.assertEqual(QRDinamico.objects.get(estado='vigente').usos, 0)


class FotoTests(MarcadorMixin, TestCase):
    def subir_foto(self, usuario=None, archivo=None):
        return self.cliente(usuario or self.admin1).post(f'/api/empleados/{self.ana.pk}/foto/',
                                                          {'foto': archivo or foto_png()}, format='multipart')

    def test_foto_privada_achicada_y_auditada(self):
        r = self.subir_foto()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['tiene_foto'])
        self.assertNotIn('foto', r.data)
        ana = Empleado.objects.get(pk=self.ana.pk)
        with Image.open(ana.foto.path) as imagen:
            self.assertLessEqual(max(imagen.size), 600)
            self.assertEqual(imagen.format, 'JPEG')
        self.assertTrue(EventoAuditoria.objects.filter(descripcion='Foto cambiada.').exists())
        self.assertEqual(self.cliente(self.usr_ana).get(f'/api/empleados/{self.ana.pk}/foto/').status_code, 200)
        self.assertEqual(self.cliente(self.usr_ana).get(f'/api/empleados/{self.beto.pk}/foto/').status_code, 404)
        self.assertEqual(self.cliente(self.admin2).get(f'/api/empleados/{self.ana.pk}/foto/').status_code, 404)

    def test_solo_quien_edita_el_legajo_sube_la_foto(self):
        self.assertEqual(self.subir_foto(self.gestor1).status_code, 403)
        self.assertEqual(self.subir_foto(self.usr_ana).status_code, 403)

    def test_archivo_que_no_es_imagen(self):
        falso = SimpleUploadedFile('foto.jpg', b'no soy una imagen', content_type='image/jpeg')
        self.assertEqual(self.subir_foto(archivo=falso).status_code, 400)

    def test_la_terminal_ve_solo_la_foto_de_quien_marco_en_ella_y_por_poco_tiempo(self):
        self.subir_foto()
        r = self.escanear(self.token_en_pantalla())
        self.assertTrue(r.data['tiene_foto'])
        id_marca = r.data['id']
        self.assertEqual(self.lector().get(f'/api/terminal/foto/{id_marca}/').status_code, 200)
        self.assertEqual(self.lector(self.clave_e2).get(f'/api/terminal/foto/{id_marca}/').status_code, 404)
        Marcacion.objects.filter(pk=id_marca).update(creado=timezone.now() - timedelta(minutes=10))
        self.assertEqual(self.lector().get(f'/api/terminal/foto/{id_marca}/').status_code, 404)


class CodigoFijoTests(MarcadorMixin, TestCase):
    def generar(self, empleado=None, usuario=None):
        return self.cliente(usuario or self.admin1).post('/api/codigos-marcacion/', {'empleado': (empleado or self.ana).pk})

    def test_codigo_valido_registra_y_desconocido_no(self):
        r = self.generar()
        self.assertEqual(r.status_code, 201, r.data)
        codigo = r.data['codigo']
        self.assertEqual(len(codigo), 6)
        credencial = CredencialMarcacion.objects.get(pk=r.data['id'])
        self.assertNotIn(codigo, credencial.codigo_cifrado)
        r2 = self.lector().post('/api/terminal/codigo/', {'codigo': codigo})
        self.assertEqual(r2.data['resultado'], 'ok', r2.data)
        self.assertEqual(r2.data['legajo'], self.ana.codigo)
        marca = Marcacion.objects.get()
        self.assertEqual((marca.metodo, marca.nivel_verificacion), ('codigo_fijo', 'solo_codigo'))
        r3 = self.lector().post('/api/terminal/codigo/', {'codigo': '000000' if codigo != '000000' else '111111'})
        self.assertEqual(r3.data['codigo'], 'codigo_desconocido')
        self.assertEqual(Marcacion.objects.count(), 1)

    def test_codigo_de_otra_empresa_no_sirve(self):
        codigo = self.generar().data['codigo']
        self.assertEqual(self.lector(self.clave_e2).post('/api/terminal/codigo/', {'codigo': codigo}).data['resultado'], 'rechazado')

    def test_rotar_revoca_el_anterior(self):
        viejo = self.generar().data['codigo']
        nuevo = self.generar().data['codigo']
        self.assertEqual(CredencialMarcacion.objects.filter(empleado=self.ana, estado='activa').count(), 1)
        if viejo != nuevo:
            self.assertEqual(self.lector().post('/api/terminal/codigo/', {'codigo': viejo}).data['codigo'], 'codigo_desconocido')
        self.assertEqual(self.lector().post('/api/terminal/codigo/', {'codigo': nuevo}).data['resultado'], 'ok')

    def test_revocar_con_motivo(self):
        r = self.generar()
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.post(f'/api/codigos-marcacion/{r.data["id"]}/revocar/').status_code, 400)
        self.assertEqual(cliente.post(f'/api/codigos-marcacion/{r.data["id"]}/revocar/', {'motivo': 'Pérdida'}).status_code, 200)
        self.assertEqual(self.lector().post('/api/terminal/codigo/', {'codigo': r.data['codigo']}).data['resultado'], 'rechazado')

    def test_codigo_deshabilitado_por_la_empresa(self):
        codigo = self.generar().data['codigo']
        self.config.permite_codigo_fijo = False
        self.config.save()
        self.assertEqual(self.lector().post('/api/terminal/codigo/', {'codigo': codigo}).data['codigo'], 'codigo_deshabilitado')

    def test_terminal_solo_qr_no_acepta_codigos(self):
        codigo = self.generar().data['codigo']
        self.terminal.tipo = TerminalMarcacion.LECTOR_QR
        self.terminal.save()
        self.assertEqual(self.lector().post('/api/terminal/codigo/', {'codigo': codigo}).data['codigo'], 'terminal_sin_codigo')

    def test_bloqueo_por_intentos_fallidos(self):
        for _ in range(10):
            self.lector().post('/api/terminal/codigo/', {'codigo': '123'})
        self.assertEqual(self.lector().post('/api/terminal/codigo/', {'codigo': '123'}).status_code, 429)
        # Los intentos quedan para consultar (listado de intentos rechazados).
        r = self.cliente(self.admin1).get('/api/intentos-marcacion/')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.data['count'], 10)
        self.assertEqual(r.data['results'][0]['codigo_rechazo'], 'codigo_desconocido')

    def test_ver_codigos_y_quien_puede(self):
        r = self.generar()
        self.assertEqual(self.generar(usuario=self.gestor1).status_code, 403)
        self.assertEqual(self.cliente(self.gestor1).get('/api/codigos-marcacion/').status_code, 403)
        revelado = self.cliente(self.admin1).post(f'/api/codigos-marcacion/{r.data["id"]}/revelar/')
        self.assertEqual(revelado.data['numero'], r.data['codigo'])
        self.assertTrue(EventoAuditoria.objects.filter(descripcion='Se mostró el código fijo.').exists())
        self.assertEqual(self.cliente(self.usr_ana).get('/api/marcador/mi-codigo/').data['codigo'], r.data['codigo'])
        self.config.empleado_ve_su_codigo = False
        self.config.save()
        self.assertEqual(self.cliente(self.usr_ana).get('/api/marcador/mi-codigo/').status_code, 403)


class TerminalYSeguridadTests(MarcadorMixin, TestCase):
    def marcar(self):
        self.escanear(self.token_en_pantalla())
        return Marcacion.objects.latest('pk')

    def test_clave_invalida_o_terminal_inactiva(self):
        self.assertEqual(self.lector('1.inventada').get('/api/terminal/yo/').status_code, 401)
        self.assertEqual(APIClient().get('/api/terminal/qr/').status_code, 401)
        self.assertEqual(self.lector().get('/api/terminal/yo/').data['terminal']['codigo'], 'T1')
        self.terminal.activa = False
        self.terminal.save()
        self.assertEqual(self.lector().get('/api/terminal/qr/').status_code, 401)

    def test_regenerar_la_clave_invalida_la_anterior(self):
        r = self.cliente(self.admin1).post(f'/api/terminales/{self.terminal.pk}/generar_clave/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.lector().get('/api/terminal/yo/').status_code, 401)
        self.assertEqual(self.lector(r.data['clave']).get('/api/terminal/yo/').status_code, 200)
        self.assertNotIn('clave_huella', self.cliente(self.admin1).get(f'/api/terminales/{self.terminal.pk}/').data)

    def test_un_usuario_no_puede_usar_los_endpoints_de_terminal(self):
        self.assertIn(self.cliente(self.admin1).get('/api/terminal/qr/').status_code, (401, 403))

    def test_las_marcas_no_se_editan_ni_se_borran(self):
        marca = self.marcar()
        for usuario in (self.admin1, self.plataforma):
            cliente = self.cliente(usuario)
            self.assertIn(cliente.patch(f'/api/marcaciones/{marca.pk}/', {'tipo': 'salida'}).status_code, (403, 405))
            self.assertIn(cliente.delete(f'/api/marcaciones/{marca.pk}/').status_code, (403, 405))
            self.assertIn(cliente.post('/api/marcaciones/', {}).status_code, (403, 405))

    def test_quien_ve_las_marcas(self):
        self.marcar()
        self.assertEqual(self.cliente(self.gestor1).get('/api/marcaciones/').data['count'], 1)
        self.assertEqual(self.cliente(self.admin2).get('/api/marcaciones/').data['count'], 0)
        self.assertEqual(self.cliente(self.usr_ana).get('/api/marcaciones/').data['count'], 1)
        self.assertEqual(self.cliente(self.gestor1).get('/api/terminales/').status_code, 403)

    def test_configuracion_solo_el_administrador(self):
        self.assertEqual(self.cliente(self.gestor1).patch('/api/marcador/configuracion/', {'vigencia_qr_segundos': 30}).status_code, 403)
        r = self.cliente(self.admin1).patch('/api/marcador/configuracion/', {'vigencia_qr_segundos': 30})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.cliente(self.admin1).patch('/api/marcador/configuracion/', {'vigencia_qr_segundos': 5}).status_code, 400)
        self.assertTrue(EventoAuditoria.objects.filter(modelo='asistencia.ConfiguracionMarcacion').exists())

    def test_terminal_de_otra_empresa_no_se_ve(self):
        self.assertEqual(self.cliente(self.admin1).get(f'/api/terminales/{self.terminal_e2.pk}/').status_code, 404)

    def test_el_enlace_del_qr_nunca_es_localhost(self):
        from django.test import override_settings
        # Sin URL_APP (no depende del .env de la máquina donde corren las pruebas).
        with override_settings(URL_APP=''):
            datos = self.lector().get('/api/terminal/yo/', HTTP_HOST='localhost:8004').data
            self.assertNotIn('localhost', datos['url_app'])
            self.assertTrue(datos['url_app'].endswith(':5204'))
            datos = self.lector().get('/api/terminal/yo/', HTTP_HOST='192.168.0.20:8004').data
            self.assertEqual(datos['url_app'], 'http://192.168.0.20:5204')
        with override_settings(URL_APP='https://rrhh.ejemplo.test/'):
            self.assertEqual(self.lector().get('/api/terminal/yo/').data['url_app'], 'https://rrhh.ejemplo.test')

    def test_el_qr_no_lleva_datos_personales(self):
        token = self.token_en_pantalla()
        self.assertIsNone(re.search(self.ana.numero_documento, token))
        self.assertLessEqual(len(token), 64)
