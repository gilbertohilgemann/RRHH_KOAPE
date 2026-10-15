"""Tablero: datos agrupados por mes, departamento y empleado, permisos por perfil y aislamiento."""
from decimal import Decimal

from django.test import TestCase

from nomina.tests_liquidacion import NominaMixin

RANGO = 'desde=2026-09-01&hasta=2026-10-31'


class TableroTests(NominaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.octubre = self.cerrada()

    def get(self, usuario, consulta=''):
        return self.cliente(usuario).get(f'/api/tablero/?{RANGO}&{consulta}')

    def test_por_mes_y_resumen(self):
        r = self.get(self.admin1, 'agrupar=mes')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['meses'], ['2026-09', '2026-10'])
        octubre = {f['clave']: f for f in r.data['filas']}['2026-10']
        ana = self.liquidacion(self.octubre)
        self.assertEqual(Decimal(octubre['neto']), self.octubre.total_neto)
        self.assertEqual(Decimal(octubre['costo_empleador']), self.octubre.total_costo_empleador)
        self.assertGreaterEqual(Decimal(octubre['bruto']), ana.bruto)
        self.assertEqual(r.data['resumen']['mes']['mes'], '2026-10')
        self.assertNotIn('bruto', r.data['resumen']['anterior'])  # septiembre no tiene nómina cerrada
        self.assertIn('IPS_PATRONAL', {c['codigo'] for c in r.data['conceptos']})

    def test_gestor_no_ve_el_costo_del_empleador(self):
        r = self.get(self.gestor1, 'agrupar=total')
        self.assertFalse(r.data['secciones']['costo'])
        self.assertNotIn('costo_empleador', r.data['filas'][0])
        self.assertNotIn('aportes_patronales', r.data['filas'][0])
        self.assertNotIn('IPS_PATRONAL', {c['codigo'] for c in r.data['conceptos']})

    def test_empleado_y_otra_empresa(self):
        self.assertEqual(self.get(self.usr_ana).status_code, 403)
        self.assertEqual(self.cliente(self.usr_ana).get('/api/tablero/opciones/').status_code, 403)
        otra = self.get(self.admin2, 'agrupar=total').data
        self.assertNotIn('bruto', otra['filas'][0])  # la nómina de la empresa 1 no se ve desde la 2
        opciones = self.cliente(self.admin2).get('/api/tablero/opciones/').data
        self.assertNotIn(self.ana.pk, [e['id'] for e in opciones['empleados']])

    def test_gestor_limitado_a_su_sucursal(self):
        filas = self.get(self.gestor_norte, 'agrupar=empleado').data['filas']
        self.assertEqual({f['clave'] for f in filas}, {str(self.beto.pk)})

    def test_comparar_empleados_mes_a_mes(self):
        r = self.get(self.admin1, f'agrupar=empleado&por_mes=1&empleados={self.ana.pk}').data
        self.assertEqual([f['clave'] for f in r['filas']], [str(self.ana.pk)])
        meses = r['filas'][0]['meses']
        self.assertEqual([m['mes'] for m in meses], ['2026-09', '2026-10'])
        self.assertEqual(Decimal(meses[1]['neto']), self.liquidacion(self.octubre).neto)
        self.assertNotIn('neto', meses[0])

    def test_por_departamento_y_exportacion(self):
        r = self.get(self.admin1, 'agrupar=departamento')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sum(Decimal(f.get('neto', 0)) for f in r.data['filas']), self.octubre.total_neto)
        x = self.get(self.admin1, 'agrupar=departamento&por_mes=1&formato=xlsx')
        self.assertEqual(x['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_parametros_invalidos(self):
        c = self.cliente(self.admin1)
        self.assertEqual(c.get('/api/tablero/?agrupar=otra').status_code, 400)
        self.assertEqual(c.get('/api/tablero/?desde=2026-10-01&hasta=2026-09-01').status_code, 400)
        self.assertEqual(c.get('/api/tablero/?desde=2010-01-01&hasta=2026-01-01').status_code, 400)
        self.assertEqual(c.get('/api/tablero/?empleados=1,x').status_code, 400)
