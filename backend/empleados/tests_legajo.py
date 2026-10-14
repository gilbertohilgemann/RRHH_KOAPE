"""Documentos del legajo (archivos privados) y cuentas bancarias cifradas."""
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.datos_prueba import EscenarioMixin
from core.models import EventoAuditoria
from empleados.models import CuentaBancaria, DocumentoEmpleado, TipoDocumento

PDF = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'


def pdf(nombre='contrato.pdf', contenido=PDF):
    return SimpleUploadedFile(nombre, contenido, content_type='application/pdf')


class DocumentoTests(EscenarioMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.contrato = TipoDocumento.objects.get(empresa=None, codigo='CONTRATO')
        cls.medico = TipoDocumento.objects.get(empresa=None, codigo='MEDICO')

    def subir(self, tipo=None, empleado=None, archivo=None, usuario=None):
        return self.cliente(usuario or self.admin1).post('/api/documentos-empleado/', {
            'empleado': (empleado or self.ana).pk, 'tipo_documento': (tipo or self.contrato).pk,
            'archivo': archivo or pdf()}, format='multipart')

    def test_subir_guarda_privado_con_huella(self):
        r = self.subir()
        self.assertEqual(r.status_code, 201, r.data)
        documento = DocumentoEmpleado.objects.get(pk=r.data['id'])
        self.assertEqual(documento.nombre_original, 'contrato.pdf')
        self.assertEqual(documento.tipo_mime, 'application/pdf')
        self.assertEqual(len(documento.sha256), 64)
        ruta = Path(documento.archivo.path)
        self.assertTrue(str(ruta).startswith(str(settings.PRIVADO_ROOT)))
        self.assertNotIn('contrato', ruta.name)  # nombre aleatorio en el disco
        self.assertNotIn('archivo', r.data)

    def test_archivo_disfrazado_se_rechaza(self):
        r = self.subir(archivo=pdf('virus.pdf', b'MZ\x90\x00 esto es un ejecutable'))
        self.assertEqual(r.status_code, 400)

    def test_descarga_con_auditoria(self):
        r = self.subir()
        respuesta = self.cliente(self.gestor1).get(f'/api/documentos-empleado/{r.data["id"]}/descargar/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(b''.join(respuesta.streaming_content), PDF)
        self.assertTrue(EventoAuditoria.objects.filter(nombre_usuario='gestor1', descripcion__startswith='Descarga').exists())

    def test_confidenciales_solo_con_permiso_o_propios(self):
        r = self.subir(tipo=self.medico)
        self.assertTrue(r.data['confidencial'])
        id_doc = r.data['id']
        self.assertEqual(self.cliente(self.gestor1).get(f'/api/documentos-empleado/{id_doc}/').status_code, 404)
        self.assertEqual(self.cliente(self.gestor1).get(f'/api/documentos-empleado/{id_doc}/descargar/').status_code, 404)
        self.assertEqual(self.cliente(self.admin1).get(f'/api/documentos-empleado/{id_doc}/').status_code, 200)
        self.assertEqual(self.cliente(self.usr_ana).get(f'/api/documentos-empleado/{id_doc}/descargar/').status_code, 200)

    def test_empleado_no_ve_documentos_ajenos_ni_sube(self):
        r = self.subir(empleado=self.beto)
        self.assertEqual(self.cliente(self.usr_ana).get(f'/api/documentos-empleado/{r.data["id"]}/').status_code, 404)
        self.assertEqual(self.subir(usuario=self.usr_ana).status_code, 403)

    def test_gestor_sube_pero_no_anula(self):
        r = self.subir(usuario=self.gestor1)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.cliente(self.gestor1).post(f'/api/documentos-empleado/{r.data["id"]}/anular/',
                                                         {'motivo': 'x'}).status_code, 403)

    def test_anular_y_nunca_borrar(self):
        r = self.subir()
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.post(f'/api/documentos-empleado/{r.data["id"]}/anular/', {'motivo': 'Duplicado'}).status_code, 200)
        self.assertEqual(DocumentoEmpleado.objects.get(pk=r.data['id']).estado, 'anulado')
        self.assertIn(self.cliente(self.plataforma).delete(f'/api/documentos-empleado/{r.data["id"]}/').status_code, (403, 405))

    def test_tipo_con_vencimiento_lo_exige(self):
        cedula = TipoDocumento.objects.get(empresa=None, codigo='CI')
        self.assertEqual(self.subir(tipo=cedula).status_code, 400)


class CuentaBancariaTests(EscenarioMixin, TestCase):
    def crear(self, usuario=None, **extra):
        datos = {'empleado': self.ana.pk, 'banco': 'Banco Ejemplo', 'numero': '0012 3456 7890', 'titular': 'Ana Apellido'}
        datos.update(extra)
        return self.cliente(usuario or self.admin1).post('/api/cuentas-bancarias/', datos)

    def test_el_numero_se_guarda_cifrado_y_se_muestra_enmascarado(self):
        r = self.crear()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['numero_enmascarado'], '•••• 7890')
        self.assertNotIn('numero', r.data)
        self.assertNotIn('numero_cifrado', r.data)
        cuenta = CuentaBancaria.objects.get(pk=r.data['id'])
        self.assertNotIn('1234567890', cuenta.numero_cifrado)
        self.assertEqual(cuenta.numero_completo(), '001234567890')
        evento = EventoAuditoria.objects.get(accion=EventoAuditoria.ALTA, modelo='empleados.CuentaBancaria')
        self.assertNotIn('numero_cifrado', evento.datos_nuevos)

    def test_revelar_solo_con_permiso_y_auditado(self):
        r = self.crear()
        self.assertEqual(self.cliente(self.gestor1).post(f'/api/cuentas-bancarias/{r.data["id"]}/revelar/').status_code, 403)
        self.assertEqual(self.cliente(self.usr_ana).post(f'/api/cuentas-bancarias/{r.data["id"]}/revelar/').status_code, 403)
        respuesta = self.cliente(self.admin1).post(f'/api/cuentas-bancarias/{r.data["id"]}/revelar/')
        self.assertEqual(respuesta.data['numero'], '001234567890')
        self.assertTrue(EventoAuditoria.objects.filter(descripcion='Se mostró el número completo de la cuenta.').exists())

    def test_una_sola_principal_activa(self):
        self.crear()
        self.assertEqual(self.crear(banco='Otro Banco').status_code, 400)
        self.assertEqual(self.crear(banco='Otro Banco', principal=False).status_code, 201)

    def test_empleado_ve_su_cuenta_enmascarada_y_no_la_edita(self):
        r = self.crear()
        cliente = self.cliente(self.usr_ana)
        self.assertEqual(cliente.get('/api/cuentas-bancarias/').data['count'], 1)
        self.assertEqual(cliente.patch(f'/api/cuentas-bancarias/{r.data["id"]}/', {'banco': 'X'}).status_code, 403)

    def test_gestor_no_carga_cuentas(self):
        self.assertEqual(self.crear(usuario=self.gestor1).status_code, 403)
