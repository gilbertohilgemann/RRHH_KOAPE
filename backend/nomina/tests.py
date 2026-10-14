"""Conceptos de nómina, fórmulas seguras y conceptos fijos (fase 8; §4.4 y §8)."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from asistencia.models import ConfiguracionMarcacion
from core.datos_prueba import EscenarioMixin
from nomina import expresiones, redondeo
from nomina.models import ConceptoNomina, ConceptoRecurrente, ReglaConcepto


class ExpresionesTests(SimpleTestCase):
    def test_calcula_con_decimal(self):
        self.assertEqual(expresiones.evaluar('A * (1 + B / 100)', {'A': 100, 'B': 50}), Decimal('150'))
        self.assertEqual(expresiones.evaluar('0.1 + 0.2', {}), Decimal('0.3'))
        self.assertEqual(expresiones.evaluar('min(A, 10) + max(1, 2) + abs(-3)', {'A': 20}), Decimal('15'))
        self.assertEqual(expresiones.evaluar('redondear(10 / 3, 2)', {}), Decimal('3.33'))
        self.assertEqual(expresiones.evaluar('100 if A > 5 and not B else 0', {'A': 6, 'B': 0}), Decimal('100'))
        self.assertTrue(expresiones.evaluar('1 < A <= 3', {'A': 3}))

    def test_rechaza_todo_lo_peligroso(self):
        for formula in ('__import__("os").system("x")', 'A.real', 'A[0]', '"texto"', '2 ** 100000', 'open("x")',
                        'lambda: 1', '[1, 2]', 'A if', 'salario', 'eval("1")', 'min(x=1)', 'A; B', 'x' * 1001):
            with self.assertRaises(expresiones.ErrorFormula, msg=formula):
                expresiones.analizar(formula)

    def test_errores_legibles_al_calcular(self):
        with self.assertRaisesMessage(expresiones.ErrorFormula, 'Falta el valor de B'):
            expresiones.evaluar('A + B', {'A': 1})
        with self.assertRaisesMessage(expresiones.ErrorFormula, 'División por cero'):
            expresiones.evaluar('A / 0', {'A': 1})
        self.assertEqual(expresiones.analizar('VALOR_HORA * HORAS + max(A, 1)')[1], {'VALOR_HORA', 'HORAS', 'A'})

    def test_redondeo(self):
        self.assertEqual(redondeo.redondear(Decimal('1234.5')), Decimal('1235'))
        self.assertEqual(redondeo.redondear(Decimal('1234.4')), Decimal('1234'))
        self.assertEqual(redondeo.redondear(Decimal('1235'), 'decena'), Decimal('1240'))
        self.assertEqual(redondeo.redondear(Decimal('1249'), 'centena'), Decimal('1200'))
        self.assertEqual(redondeo.redondear(Decimal('1.005'), 'dos_decimales'), Decimal('1.01'))


class ConceptosTests(EscenarioMixin, TestCase):
    def test_conceptos_precargados_y_reglas_en_borrador(self):
        self.assertTrue(ConceptoNomina.objects.filter(empresa=None, codigo='IPS_PATRONAL', afecta_neto=False).exists())
        self.assertFalse(ReglaConcepto.objects.filter(empresa=None).exclude(estado='borrador').exists())
        for regla in ReglaConcepto.objects.filter(empresa=None):
            regla.full_clean()  # todas las fórmulas de referencia son válidas

    def test_aporte_patronal_nunca_afecta_el_neto(self):
        c = ConceptoNomina(empresa=self.e1, codigo='OTRO_APORTE', nombre='x', tipo='aporte_patronal', afecta_neto=True)
        with self.assertRaisesMessage(ValidationError, 'nunca afecta el neto'):
            c.full_clean()
        c = ConceptoNomina(empresa=self.e1, codigo='DESC', nombre='x', tipo='descuento', afecta_base_ips=True)
        with self.assertRaises(ValidationError):
            c.full_clean()

    def test_regla_calcula_y_respeta_la_condicion(self):
        regla = ReglaConcepto.objects.get(empresa=None, concepto__codigo='HORAS_EXTRA_DIURNAS')
        datos = {'VALOR_HORA': Decimal('14583.33'), 'HORAS_EXTRA_DIURNAS': 4, 'RECARGO_EXTRA_DIURNA': 50}
        self.assertEqual(regla.calcular(datos), Decimal('87500'))
        self.assertIsNone(regla.calcular({**datos, 'HORAS_EXTRA_DIURNAS': 0}))
        regla.expresion = 'VALOR_HORA *'
        with self.assertRaises(ValidationError):
            regla.full_clean()


class ApiTests(EscenarioMixin, TestCase):
    def setUp(self):
        self.ips = ConceptoNomina.objects.get(empresa=None, codigo='IPS_TRABAJADOR')
        self.bono = ConceptoNomina.objects.get(empresa=None, codigo='BONO')  # requiere aprobación

    def test_probar_formula_con_ejemplos_y_valores_propios(self):
        regla = ReglaConcepto.objects.get(empresa=None, concepto=self.ips)
        cliente = self.cliente(self.gestor1)
        r = cliente.post(f'/api/reglas-concepto/{regla.pk}/probar/', {'fecha': '2026-07-15'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['resultado'], Decimal('315000'))  # 3.500.000 × 9 %
        self.assertTrue(r.data['advertencias'])  # parámetros en borrador
        r = cliente.post(f'/api/reglas-concepto/{regla.pk}/probar/', {'fecha': '2026-07-15', 'variables': {'BASE_IPS': 1000000}},
                         format='json')
        self.assertEqual(r.data['resultado'], Decimal('90000'))
        self.assertEqual(self.cliente(self.usr_ana).post(f'/api/reglas-concepto/{regla.pk}/probar/').status_code, 403)

    def test_regla_propia_aprobada_no_se_edita(self):
        cliente = self.cliente(self.admin1)
        r = cliente.post('/api/reglas-concepto/', {'concepto': self.ips.pk, 'vigente_desde': '2026-07-01',
                                                   'expresion': 'BASE_IPS * 0.09'})
        self.assertEqual(r.status_code, 201, r.data)
        mala = cliente.post('/api/reglas-concepto/', {'concepto': self.ips.pk, 'vigente_desde': '2026-07-01',
                                                      'expresion': '__import__("os")'})
        self.assertEqual(mala.status_code, 400)
        self.assertEqual(self.cliente(self.gestor1).post(f'/api/reglas-concepto/{r.data["id"]}/aprobar/').status_code, 403)
        a = cliente.post(f'/api/reglas-concepto/{r.data["id"]}/aprobar/')
        self.assertEqual((a.status_code, a.data['estado']), (200, 'aprobada'))
        self.assertEqual(cliente.patch(f'/api/reglas-concepto/{r.data["id"]}/', {'expresion': '1'}).status_code, 400)
        global_ = ReglaConcepto.objects.filter(empresa=None).first()
        self.assertEqual(cliente.post(f'/api/reglas-concepto/{global_.pk}/aprobar/').status_code, 403)

    def test_concepto_fijo_con_aprobacion_y_finalizacion(self):
        r = self.cliente(self.gestor1).post('/api/conceptos-fijos/', {
            'empleado': self.ana.pk, 'concepto': self.bono.pk, 'monto': '200000', 'vigente_desde': '2026-08-01',
            'motivo': 'Premio por presentismo'})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertFalse(r.data['aprobado'])
        pk = r.data['id']
        self.assertEqual(self.cliente(self.gestor1).post(f'/api/conceptos-fijos/{pk}/aprobar/').status_code, 403)
        self.assertEqual(self.cliente(self.admin1).post(f'/api/conceptos-fijos/{pk}/aprobar/').data['aprobado'], True)
        self.assertEqual(self.cliente(self.gestor1).patch(f'/api/conceptos-fijos/{pk}/', {'monto': '1'}).status_code, 400)
        f = self.cliente(self.gestor1).post(f'/api/conceptos-fijos/{pk}/finalizar/', {'vigente_hasta': '2026-12-31', 'motivo': 'Fin'})
        self.assertEqual((f.status_code, f.data['activo'], f.data['vigente_hasta']), (200, False, '2026-12-31'))
        self.assertIn(self.cliente(self.admin1).delete(f'/api/conceptos-fijos/{pk}/').status_code, (403, 405))

    def test_concepto_fijo_validaciones_y_separacion(self):
        cliente = self.cliente(self.admin1)
        r = cliente.post('/api/conceptos-fijos/', {'empleado': self.ana.pk, 'concepto': self.ips.pk, 'monto': '1',
                                                   'vigente_desde': '2026-08-01', 'motivo': 'x'})
        self.assertEqual(r.status_code, 400)  # los aportes los calcula la nómina
        r = cliente.post('/api/conceptos-fijos/', {'empleado': self.ana.pk, 'concepto': self.bono.pk, 'monto': '-5',
                                                   'vigente_desde': '2026-08-01', 'motivo': 'x'})
        self.assertEqual(r.status_code, 400)
        ConfiguracionMarcacion.de(self.e1)
        ConfiguracionMarcacion.objects.filter(empresa=self.e1).update(exigir_aprobador_distinto=True)
        r = cliente.post('/api/conceptos-fijos/', {'empleado': self.ana.pk, 'concepto': self.bono.pk, 'monto': '5',
                                                   'vigente_desde': '2026-08-01', 'motivo': 'x'})
        self.assertEqual(cliente.post(f'/api/conceptos-fijos/{r.data["id"]}/aprobar/').status_code, 400)

    def test_concepto_sin_aprobacion_queda_aprobado(self):
        sueldo_extra = ConceptoNomina.objects.create(empresa=self.e1, codigo='VIATICO', nombre='Viático', tipo='haber',
                                                     tipo_calculo='fijo')
        r = self.cliente(self.gestor1).post('/api/conceptos-fijos/', {
            'empleado': self.ana.pk, 'concepto': sueldo_extra.pk, 'monto': '100000', 'vigente_desde': '2026-08-01', 'motivo': 'x'})
        self.assertTrue(r.data['aprobado'])
        self.assertEqual(ConceptoRecurrente.objects.get(pk=r.data['id']).aprobado_por, self.gestor1)
        self.assertEqual(date(2026, 8, 1), ConceptoRecurrente.objects.get(pk=r.data['id']).vigente_desde)
