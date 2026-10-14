"""Reglas legales versionadas (fase 8; §4.5 y §9)."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.datos_prueba import EscenarioMixin
from legal import servicios
from legal.models import ConjuntoReglas, ParametroLegal

JULIO = date(2026, 7, 15)


class ServiciosTests(EscenarioMixin, TestCase):
    def setUp(self):
        self.global_ = ConjuntoReglas.objects.get(empresa=None, codigo='PY-LABORAL')

    def aprobar(self, conjunto, revisor=None, aprobador=None):
        servicios.revisar(conjunto, revisor or self.plataforma)
        return servicios.aprobar(conjunto, aprobador or self.admin1)[0]

    def test_referencia_precargada_en_borrador_bloquea_la_liquidacion(self):
        self.assertEqual(self.global_.estado, 'borrador')
        with self.assertRaisesMessage(servicios.ReglaNoAprobada, 'Hay uno sin aprobar'):
            servicios.parametro(self.e1, 'SALARIO_MINIMO_MENSUAL', JULIO)
        valor, _, aviso = servicios.parametro(self.e1, 'SALARIO_MINIMO_MENSUAL', JULIO, simulacion=True)
        self.assertEqual(valor, Decimal('3044000'))
        self.assertIn('sirve para simular', aviso)
        with self.assertRaises(servicios.ReglaNoAprobada):
            servicios.parametro(self.e1, 'SALARIO_MINIMO_MENSUAL', date(2026, 6, 30), simulacion=True)  # antes de la vigencia

    def test_cuatro_ojos_y_aprobado_ya_vale(self):
        servicios.revisar(self.global_, self.plataforma)
        with self.assertRaisesMessage(ValidationError, 'distinta'):
            servicios.aprobar(self.global_, self.plataforma)
        servicios.aprobar(self.global_, self.admin1)
        self.assertEqual(servicios.parametro(self.e1, 'RECARGO_EXTRA_DIURNA', JULIO)[0], Decimal('50'))
        regimen, aviso = servicios.regimen(self.e1, 'IPS-GENERAL', JULIO)
        self.assertEqual((regimen.tasa_trabajador, aviso), (Decimal('9'), ''))
        variables = servicios.vigentes(self.e1, JULIO)['variables']
        self.assertEqual((variables['IPS_TASA_TRABAJADOR'], variables['IPS_GENERAL_TASA_PATRONAL']), (Decimal('9'), Decimal('16.5')))

    def test_nueva_version_cierra_la_anterior_y_respeta_las_fechas(self):
        self.aprobar(self.global_)
        nueva = servicios.nueva_version(self.global_, self.plataforma, date(2027, 1, 1))
        self.assertEqual((nueva.version, nueva.estado, nueva.parametros.count()), (2, 'borrador', self.global_.parametros.count()))
        ParametroLegal.objects.filter(conjunto=nueva, codigo='SALARIO_MINIMO_MENSUAL').update(valor_numerico=3300000)
        self.aprobar(nueva)
        self.global_.refresh_from_db()
        self.assertEqual(self.global_.vigente_hasta, date(2026, 12, 31))
        self.assertEqual(servicios.parametro(self.e1, 'SALARIO_MINIMO_MENSUAL', JULIO)[0], Decimal('3044000'))
        self.assertEqual(servicios.parametro(self.e1, 'SALARIO_MINIMO_MENSUAL', date(2027, 2, 1))[0], Decimal('3300000'))

    def test_superposicion_no_se_aprueba(self):
        self.aprobar(self.global_)
        otro = ConjuntoReglas.objects.create(empresa=None, codigo='PY-LABORAL', nombre='x', version=9, vigente_desde=date(2026, 5, 1),
                                             vigente_hasta=date(2026, 8, 1))
        ParametroLegal.objects.create(conjunto=otro, codigo='X', nombre='x', valor_numerico=1)
        servicios.revisar(otro, self.plataforma)
        with self.assertRaisesMessage(ValidationError, 'Se superpone'):
            servicios.aprobar(otro, self.admin1)

    def test_las_reglas_de_la_empresa_tienen_prioridad(self):
        self.aprobar(self.global_)
        propio = ConjuntoReglas.objects.create(empresa=self.e1, codigo='CONVENIO', nombre='Convenio', vigente_desde=date(2026, 1, 1))
        ParametroLegal.objects.create(conjunto=propio, codigo='RECARGO_EXTRA_DIURNA', nombre='x', valor_numerico=60, unidad='%')
        self.aprobar(propio, self.gestor1, self.admin1)
        self.assertEqual(servicios.parametro(self.e1, 'RECARGO_EXTRA_DIURNA', JULIO)[0], Decimal('60'))
        self.assertEqual(servicios.parametro(self.e2, 'RECARGO_EXTRA_DIURNA', JULIO)[0], Decimal('50'))
        self.assertEqual(servicios.parametro(self.e1, 'RECARGO_EXTRA_NOCTURNA', JULIO)[0], Decimal('100'))

    def test_retirado_deja_de_valer(self):
        self.aprobar(self.global_)
        servicios.retirar(self.global_, self.plataforma, 'Error de carga')
        with self.assertRaises(servicios.ReglaNoAprobada):
            servicios.parametro(self.e1, 'SALARIO_MINIMO_MENSUAL', JULIO)


class ApiTests(EscenarioMixin, TestCase):
    def setUp(self):
        self.global_ = ConjuntoReglas.objects.get(empresa=None, codigo='PY-LABORAL')

    def test_la_empresa_no_toca_los_globales(self):
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.patch(f'/api/reglas-legales/{self.global_.pk}/', {'nombre': 'x'}).status_code, 403)
        self.assertEqual(cliente.post(f'/api/reglas-legales/{self.global_.pk}/revisar/').status_code, 403)
        r = self.cliente(self.plataforma).post(f'/api/reglas-legales/{self.global_.pk}/revisar/')
        self.assertEqual((r.status_code, r.data['estado']), (200, 'revisado'))

    def test_conjunto_propio_con_parametros_y_ciclo_completo(self):
        cliente = self.cliente(self.admin1)
        r = cliente.post('/api/reglas-legales/', {
            'codigo': 'CONVENIO', 'nombre': 'Convenio colectivo', 'vigente_desde': '2026-01-01',
            'parametros': [{'codigo': 'PLUS_ANTIGUEDAD', 'nombre': 'Plus', 'valor_numerico': '5', 'unidad': '%'},
                           {'codigo': 'PLUS_ANTIGUEDAD', 'nombre': 'Plus', 'valor_numerico': '6', 'unidad': '%'}]}, format='json')
        self.assertEqual(r.status_code, 400)  # repetido con vigencias superpuestas
        r = cliente.post('/api/reglas-legales/', {
            'codigo': 'CONVENIO', 'nombre': 'Convenio colectivo', 'vigente_desde': '2026-01-01',
            'parametros': [{'codigo': 'PLUS_ANTIGUEDAD', 'nombre': 'Plus', 'valor_numerico': '5', 'unidad': '%'}]}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        pk = r.data['id']
        self.assertTrue(r.data['editable'])
        self.assertEqual(cliente.post(f'/api/reglas-legales/{pk}/revisar/').status_code, 200)
        self.assertEqual(cliente.patch(f'/api/reglas-legales/{pk}/', {'nombre': 'x'}, format='json').status_code, 400)
        self.assertEqual(cliente.post(f'/api/reglas-legales/{pk}/aprobar/').status_code, 400)  # mismo revisor
        self.assertEqual(self.cliente(self.gestor1).post(f'/api/reglas-legales/{pk}/aprobar/').status_code, 403)
        vig = cliente.get('/api/reglas-legales/vigentes/?fecha=2026-07-15').data
        self.assertEqual(vig['detalle'], [])
        vig = cliente.get('/api/reglas-legales/vigentes/?fecha=2026-07-15&simulacion=true').data
        self.assertIn('PLUS_ANTIGUEDAD', [d['codigo'] for d in vig['detalle']])
        self.assertIn('SALARIO_MINIMO_MENSUAL', [d['codigo'] for d in vig['detalle']])
        self.assertTrue(vig['advertencias'])

    def test_nueva_version_por_api(self):
        servicios.revisar(self.global_, self.plataforma)
        servicios.aprobar(self.global_, self.admin1)
        r = self.cliente(self.plataforma).post(f'/api/reglas-legales/{self.global_.pk}/nueva_version/', {'vigente_desde': '2027-01-01'})
        self.assertEqual((r.status_code, r.data['version'], r.data['estado']), (201, 2, 'borrador'))
        self.assertEqual(len(r.data['parametros']), self.global_.parametros.count())
