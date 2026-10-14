"""Importación de marcaciones CSV: pruebas obligatorias de la especificación (§13, CSV)."""
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from asistencia.models import (ConfiguracionMarcacion, FilaImportacion, LoteImportacion, MapeoEmpleadoReloj, Marcacion,
                               PerfilImportacion, RelojExterno)
from core.datos_prueba import EscenarioMixin
from core.models import EventoAuditoria
from empleados.models import Empleado


def csv_archivo(texto, nombre='marcas.csv', codificacion='utf-8'):
    return SimpleUploadedFile(nombre, texto.encode(codificacion), content_type='text/csv')


class ImportacionMixin(EscenarioMixin):
    def setUp(self):
        config = ConfiguracionMarcacion.de(self.e1)
        config.permite_csv = True
        config.save()
        self.reloj = RelojExterno.objects.create(empresa=self.e1, codigo='ZK1', nombre='Reloj depósito')
        MapeoEmpleadoReloj.objects.create(empresa=self.e1, reloj=self.reloj, codigo_en_reloj='101', empleado=self.ana)
        MapeoEmpleadoReloj.objects.create(empresa=self.e1, reloj=self.reloj, codigo_en_reloj='102', empleado=self.beto)
        self.perfil = PerfilImportacion.objects.create(
            empresa=self.e1, codigo='ZK', nombre='Reloj ZK', separador=';', identificador='codigo_reloj',
            columna_empleado='Codigo', columna_fecha_hora='FechaHora', formato_fecha_hora='%d/%m/%Y %H:%M:%S',
            columna_tipo='Tipo', valores_entrada='E,IN', valores_salida='S,OUT', columna_evento='Evento')

    def importar(self, texto, usuario=None, perfil=None, reloj='mismo', **extra):
        datos = {'archivo': csv_archivo(texto, codificacion=extra.pop('codificacion', 'utf-8')),
                 'perfil': (perfil or self.perfil).pk, **extra}
        if reloj == 'mismo':
            datos['reloj'] = self.reloj.pk
        elif reloj is not None:
            datos['reloj'] = reloj
        return self.cliente(usuario or self.admin1).post('/api/importaciones/', datos, format='multipart')

    def filas(self, lote_id):
        return {f.numero_fila: f for f in FilaImportacion.objects.filter(lote_id=lote_id)}


BASICO = (
    'Codigo;FechaHora;Tipo;Evento\n'
    '101;02/03/2026 07:58:10;E;9001\n'
    '101;02/03/2026 17:02:00;S;9002\n'
    '102;02/03/2026 08:10:00;IN;9003\n'
)


class ImportacionTests(ImportacionMixin, TestCase):
    def test_lote_en_revision_y_confirmacion_transaccional(self):
        r = self.importar(BASICO)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data['total_filas'], r.data['aceptadas'], r.data['rechazadas']), (3, 3, 0))
        self.assertEqual(r.data['estado'], 'validado')
        self.assertFalse(Marcacion.objects.exists())  # nunca directo a marcas
        lote = LoteImportacion.objects.get(pk=r.data['id'])
        self.assertEqual(len(lote.sha256), 64)
        self.assertEqual(lote.modo, 'reloj_externo')
        self.assertFalse(lote.verificacion_identidad)
        c = self.cliente(self.admin1).post(f'/api/importaciones/{lote.pk}/confirmar/')
        self.assertEqual(c.status_code, 200, c.data)
        self.assertEqual(c.data['estado'], 'confirmado')
        marcas = Marcacion.objects.filter(lote_importacion=lote).order_by('fecha_hora')
        self.assertEqual(marcas.count(), 3)
        primera = marcas.filter(empleado=self.ana).first()
        self.assertEqual((primera.metodo, primera.nivel_verificacion, primera.tipo, primera.reloj, primera.id_evento_externo),
                         ('csv', 'archivo_importado', 'entrada', self.reloj, '9001'))
        self.assertEqual(timezone.localtime(primera.fecha_hora).strftime('%d/%m/%Y %H:%M:%S'), '02/03/2026 07:58:10')
        self.assertTrue(EventoAuditoria.objects.filter(modelo='asistencia.LoteImportacion', descripcion__startswith='Importación confirmada').exists())

    def test_reimportar_el_mismo_archivo_no_duplica(self):
        lote = self.importar(BASICO).data['id']
        self.cliente(self.admin1).post(f'/api/importaciones/{lote}/confirmar/')
        r = self.importar(BASICO)
        self.assertEqual((r.data['aceptadas'], r.data['duplicadas']), (0, 3))
        self.assertIn('ya se importó', r.data['aviso'])
        self.cliente(self.admin1).post(f'/api/importaciones/{r.data["id"]}/confirmar/')
        self.assertEqual(Marcacion.objects.count(), 3)

    def test_duplicados_dentro_del_archivo_y_por_id_de_evento(self):
        texto = BASICO + '101;02/03/2026 07:58:10;E;9001\n'
        filas = self.filas(self.importar(texto).data['id'])
        self.assertEqual(filas[5].estado, FilaImportacion.DUPLICADA)
        self.assertIn('fila 2', filas[5].mensaje)
        # Mismo número de evento del reloj con otra hora: también repetida.
        filas = self.filas(self.importar(BASICO + '101;02/03/2026 07:59:00;E;9001\n').data['id'])
        self.assertEqual(filas[5].estado, FilaImportacion.DUPLICADA)
        self.assertIn('evento 9001', filas[5].mensaje)

    def test_lote_parcialmente_valido_con_motivos(self):
        texto = (
            'Codigo;FechaHora;Tipo;Evento\n'
            '101;02/03/2026 07:58:10;E;1\n'
            '999;02/03/2026 08:00:00;E;2\n'          # código desconocido
            '101;2026-03-02 09:00;E;3\n'              # no respeta el formato
            '102;02/03/2026 12:00:00;X;4\n'           # tipo no reconocido
            '101;02/03/2099 08:00:00;E;5\n'           # futura
            '101;02/03/2026\n'                         # faltan columnas
            '102;01/01/2024 08:00:00;E;6\n'           # antes del ingreso
        )
        r = self.importar(texto)
        self.assertEqual((r.data['aceptadas'], r.data['rechazadas']), (1, 6))
        filas = self.filas(r.data['id'])
        self.assertIn('desconocido', filas[3].mensaje)
        self.assertIn('formato', filas[4].mensaje)
        self.assertIn('no reconocida', filas[5].mensaje)
        self.assertIn('futura', filas[6].mensaje)
        self.assertIn('Faltan columnas', filas[7].mensaje)
        self.assertIn('no trabajaba', filas[8].mensaje)
        self.cliente(self.admin1).post(f'/api/importaciones/{r.data["id"]}/confirmar/')
        self.assertEqual(Marcacion.objects.count(), 1)

    def test_empleado_dado_de_baja_solo_hasta_su_egreso(self):
        Empleado.objects.filter(pk=self.beto.pk).update(estado=Empleado.BAJA, fecha_egreso=date(2026, 3, 1))
        texto = 'Codigo;FechaHora;Tipo;Evento\n102;01/03/2026 08:00:00;E;1\n102;02/03/2026 08:00:00;E;2\n'
        filas = self.filas(self.importar(texto).data['id'])
        self.assertEqual(filas[2].estado, FilaImportacion.VALIDA)
        self.assertEqual(filas[3].estado, FilaImportacion.RECHAZADA)

    def test_fuera_del_periodo_elegido(self):
        r = self.importar(BASICO, periodo_desde='2026-03-03', periodo_hasta='2026-03-31')
        self.assertEqual(r.data['rechazadas'], 3)

    def test_coma_sin_encabezado_latin1_fecha_y_hora_separadas_y_fecha_ambigua(self):
        perfil = PerfilImportacion.objects.create(
            empresa=self.e1, codigo='GEN', nombre='Genérico', separador=',', codificacion='latin-1',
            tiene_encabezado=False, identificador='codigo_empleado', columna_empleado='1', columna_fecha='2',
            formato_fecha='%d/%m/%Y', columna_hora='3', formato_hora='%H:%M', modo='predefinido')
        texto = 'E001,03/04/2026,08:00,Depósito\nE002,03/04/2026,23:50,Depósito\nE002,04/04/2026,06:10,Depósito\n'
        r = self.importar(texto, perfil=perfil, reloj=None, codificacion='latin-1')
        self.assertEqual(r.data['aceptadas'], 3, r.data)
        self.cliente(self.admin1).post(f'/api/importaciones/{r.data["id"]}/confirmar/')
        marca = Marcacion.objects.filter(empleado=self.ana).get()
        # 03/04 con formato día/mes = 3 de abril (nunca se adivina el orden).
        self.assertEqual(timezone.localtime(marca.fecha_hora).date(), date(2026, 4, 3))
        # Sin columna de tipo: queda "sin determinar" (el motor de asistencia lo empareja, fase 6).
        self.assertEqual(marca.tipo, 'desconocido')
        # Turno noche y marcas en cualquier orden: se importan tal cual, sin inventar entradas o salidas.
        self.assertEqual(Marcacion.objects.filter(empleado=self.beto).count(), 2)

    def test_codificacion_equivocada_se_avisa(self):
        texto = 'Codigo;FechaHora;Tipo;Evento\n101;02/03/2026 07:58:10;E;Depósito\n'
        r = self.importar(texto, codificacion='latin-1')  # el perfil dice UTF-8
        self.assertEqual(r.status_code, 400)
        self.assertIn('Probá con Latin-1', str(r.data))

    def test_columna_inexistente_rechaza_el_archivo(self):
        r = self.importar('Empleado;Momento\n101;02/03/2026 07:58:10\n')
        self.assertEqual(r.status_code, 400)
        self.assertIn('no tiene la columna', str(r.data))

    def test_archivo_que_no_es_csv(self):
        r = self.cliente(self.admin1).post('/api/importaciones/', {
            'archivo': SimpleUploadedFile('x.csv', b'PK\x03\x04\x00\x00binario'), 'perfil': self.perfil.pk, 'reloj': self.reloj.pk},
            format='multipart')
        self.assertEqual(r.status_code, 400)

    def test_codigo_de_reloj_exige_reloj(self):
        self.assertEqual(self.importar(BASICO, reloj=None).status_code, 400)

    def test_csv_deshabilitado(self):
        ConfiguracionMarcacion.objects.filter(empresa=self.e1).update(permite_csv=False)
        self.assertEqual(self.importar(BASICO).status_code, 400)

    def test_vista_previa_no_guarda_nada(self):
        r = self.cliente(self.admin1).post('/api/importaciones/vista_previa/', {
            'archivo': csv_archivo(BASICO), 'separador': ';', 'codificacion': 'utf-8', 'tiene_encabezado': 'true'},
            format='multipart')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['encabezado'], ['Codigo', 'FechaHora', 'Tipo', 'Evento'])
        self.assertEqual(r.data['total_filas'], 3)
        self.assertEqual(r.data['filas'][0]['columnas'][0], '101')
        self.assertFalse(LoteImportacion.objects.exists())


class ReversionYErroresTests(ImportacionMixin, TestCase):
    def confirmado(self):
        lote = self.importar(BASICO).data['id']
        self.cliente(self.admin1).post(f'/api/importaciones/{lote}/confirmar/')
        return lote

    def test_revertir_anula_sin_borrar_y_se_puede_reimportar(self):
        lote = self.confirmado()
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.post(f'/api/importaciones/{lote}/revertir/').status_code, 400)  # sin motivo
        r = cliente.post(f'/api/importaciones/{lote}/revertir/', {'motivo': 'Archivo equivocado'})
        self.assertEqual(r.data['estado'], 'revertido')
        self.assertEqual(Marcacion.objects.filter(anulada=True).count(), 3)
        self.assertEqual(Marcacion.objects.count(), 3)  # siguen existiendo
        nuevo = self.importar(BASICO).data
        self.assertEqual(nuevo['aceptadas'], 3)
        cliente.post(f'/api/importaciones/{nuevo["id"]}/confirmar/')
        self.assertEqual(Marcacion.objects.filter(anulada=False).count(), 3)

    def test_no_se_confirma_dos_veces_ni_se_cancela_confirmado(self):
        lote = self.confirmado()
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.post(f'/api/importaciones/{lote}/confirmar/').status_code, 400)
        self.assertEqual(cliente.post(f'/api/importaciones/{lote}/cancelar/').status_code, 400)

    def test_errores_descargables_protegidos_contra_formulas(self):
        texto = 'Codigo;FechaHora;Tipo;Evento\n=HYPERLINK("http://malo");02/03/2026 07:58:10;E;1\n'
        lote = self.importar(texto).data['id']
        r = self.cliente(self.admin1).get(f'/api/importaciones/{lote}/errores/', {'formato': 'csv'})
        contenido = r.content.decode('utf-8-sig')
        self.assertIn('Fila;Estado;Motivo', contenido)
        self.assertIn("'=HYPERLINK", contenido)
        self.assertNotIn(';=HYPERLINK', contenido)
        x = self.cliente(self.admin1).get(f'/api/importaciones/{lote}/errores/', {'formato': 'xlsx'})
        self.assertEqual(x.status_code, 200)
        self.assertTrue(x.content.startswith(b'PK'))

    def test_las_filas_se_revisan_por_lote(self):
        lote = self.importar(BASICO + '999;02/03/2026 08:00:00;E;7\n').data['id']
        r = self.cliente(self.admin1).get('/api/filas-importacion/', {'lote': lote, 'estado': 'rechazada'})
        self.assertEqual(r.data['count'], 1)
        self.assertIn('desconocido', r.data['results'][0]['mensaje'])


class PermisosImportacionTests(ImportacionMixin, TestCase):
    def test_gestor_importa_y_confirma_pero_no_revierte(self):
        r = self.importar(BASICO, usuario=self.gestor1)
        self.assertEqual(r.status_code, 201, r.data)
        cliente = self.cliente(self.gestor1)
        self.assertEqual(cliente.post(f'/api/importaciones/{r.data["id"]}/confirmar/').status_code, 200)
        self.assertEqual(cliente.post(f'/api/importaciones/{r.data["id"]}/revertir/', {'motivo': 'x'}).status_code, 403)
        # Corrige códigos de reloj, pero no configura perfiles.
        self.assertEqual(cliente.post('/api/codigos-reloj/', {'reloj': self.reloj.pk, 'codigo_en_reloj': '200',
                                                              'empleado': self.ana.pk}).status_code, 201)
        self.assertEqual(cliente.post('/api/perfiles-importacion/', {'codigo': 'X', 'nombre': 'X', 'columna_empleado': '1'}).status_code, 403)

    def test_empleado_no_importa(self):
        self.assertEqual(self.importar(BASICO, usuario=self.usr_ana).status_code, 403)

    def test_otra_empresa_no_ve_ni_usa(self):
        lote = self.importar(BASICO).data['id']
        self.assertEqual(self.cliente(self.admin2).get(f'/api/importaciones/{lote}/').status_code, 404)
        self.assertEqual(self.importar(BASICO, usuario=self.admin2).status_code, 400)  # el perfil no es suyo

    def test_un_codigo_de_reloj_no_puede_ser_de_dos_personas_a_la_vez(self):
        r = self.cliente(self.admin1).post('/api/codigos-reloj/', {'reloj': self.reloj.pk, 'codigo_en_reloj': '101',
                                                                   'empleado': self.beto.pk})
        self.assertEqual(r.status_code, 400)

    def test_perfil_exige_formatos_explicitos(self):
        r = self.cliente(self.admin1).post('/api/perfiles-importacion/', {
            'codigo': 'MAL', 'nombre': 'Mal', 'columna_empleado': '1', 'columna_fecha_hora': '2'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('formato_fecha_hora', r.data)
