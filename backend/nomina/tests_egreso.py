"""Aguinaldo, liquidación final, planillas MTESS/IPS y reportes (fase 11)."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from asistencia.importacion import periodo_cerrado
from cumplimiento import servicios as planillas
from cumplimiento.models import PresentacionOficial
from legal import servicios as legal
from legal.models import ConjuntoReglas
from licencias.models import MovimientoVacaciones, saldo_vacaciones
from nomina import liquidar
from nomina.models import CorridaNomina, LiquidacionFinal, PeriodoNomina
from nomina.tests_liquidacion import NominaMixin, linea


class EgresoMixin(NominaMixin):
    def setUp(self):
        super().setUp()
        egreso = ConjuntoReglas.objects.get(empresa=None, codigo='PY-EGRESO')
        legal.revisar(egreso, self.plataforma)
        legal.aprobar(egreso, self.admin1)
        self.octubre = self.cerrada()

    def cerrar(self, corrida):
        liquidar.revisar(corrida, self.gestor1)
        liquidar.aprobar(corrida, self.admin1)
        return liquidar.cerrar(corrida, self.admin1)

    def final(self, causal='despido_injustificado', **extra):
        f = LiquidacionFinal.objects.create(empresa=self.e1, empleado=self.ana, fecha_egreso=date(2026, 11, 20), causal=causal, **extra)
        return f, liquidar.calcular_final(f, self.gestor1)


class AguinaldoTests(EgresoMixin, TestCase):
    def test_aguinaldo_del_anio(self):
        corrida = liquidar.crear_aguinaldo(self.e1, 2026, self.gestor1)
        self.assertFalse(corrida.es_simulacion, corrida.advertencias)
        liq = self.liquidacion(corrida)
        self.assertEqual(linea(liq, 'AGUINALDO').importe, Decimal('250000'))  # 3.000.000 / 12 (solo octubre cerrado)
        self.assertIsNone(linea(liq, 'IPS_TRABAJADOR'))  # el aguinaldo no lleva los conceptos automáticos
        self.assertTrue(any('meses con nómina cerrada' in a for a in liq.advertencias))
        self.assertEqual(liq.neto, Decimal('250000'))
        self.assertFalse(corrida.liquidaciones.filter(empleado=self.beto).exists())  # sin remuneraciones computables
        with self.assertRaises(ValidationError):
            liquidar.crear_aguinaldo(self.e1, 2026, self.gestor1)
        self.cerrar(corrida)
        self.assertFalse(periodo_cerrado(self.e1, date(2026, 11, 15)))  # el período especial no cierra la asistencia
        rect = liquidar.rectificar(corrida, self.admin1, 'Revisión')
        self.assertEqual((rect.tipo, linea(self.liquidacion(rect), 'AGUINALDO').importe), ('aguinaldo', Decimal('250000')))


class LiquidacionFinalTests(EgresoMixin, TestCase):
    def test_despido_injustificado(self):
        MovimientoVacaciones.objects.create(empresa=self.e1, empleado=self.ana, fecha=date(2026, 1, 2), tipo='ajuste', dias=10, motivo='x')
        final, corrida = self.final()
        self.assertEqual((corrida.tipo, corrida.periodo.fecha_desde), ('liquidacion_final', date(2026, 11, 1)))
        self.assertFalse(corrida.es_simulacion, corrida.advertencias)
        liq = self.liquidacion(corrida)
        self.assertEqual(linea(liq, 'SUELDO').importe, Decimal('2000000'))  # 1 al 20 de noviembre
        self.assertEqual(linea(liq, 'VACACIONES_CAUSADAS').importe, Decimal('1000000'))  # 10 días
        self.assertEqual(linea(liq, 'PREAVISO').importe, Decimal('4500000'))  # 45 días (1 a 5 años)
        self.assertEqual(linea(liq, 'INDEMNIZACION').importe, Decimal('3000000'))  # 15 días × 2 años (1 año y 10 meses)
        self.assertEqual(linea(liq, 'AGUINALDO').importe, Decimal('416667'))  # (3.000.000 + 2.000.000) / 12
        self.assertEqual(linea(liq, 'IPS_TRABAJADOR').importe, Decimal('180000'))  # solo sobre el sueldo
        self.cerrar(corrida)
        self.assertEqual(saldo_vacaciones(self.ana), 0)  # las vacaciones pagadas salen del saldo

    def test_renuncia_no_lleva_preaviso_ni_indemnizacion(self):
        _, corrida = self.final(causal='renuncia')
        liq = self.liquidacion(corrida)
        self.assertIsNone(linea(liq, 'PREAVISO'))
        self.assertIsNone(linea(liq, 'INDEMNIZACION'))
        self.assertIsNotNone(linea(liq, 'AGUINALDO'))

    def test_preaviso_otorgado_no_se_paga(self):
        _, corrida = self.final(preaviso_otorgado=True)
        self.assertIsNone(linea(self.liquidacion(corrida), 'PREAVISO'))

    def test_la_nomina_regular_lo_excluye(self):
        self.final()
        noviembre = PeriodoNomina.objects.create(empresa=self.e1, codigo='2026-11', fecha_desde=date(2026, 11, 1), fecha_hasta=date(2026, 11, 30))
        corrida = liquidar.crear(noviembre, self.gestor1)
        self.assertFalse(corrida.liquidaciones.filter(empleado=self.ana).exists())
        self.assertTrue(any('liquidación final' in a for a in corrida.advertencias))

    def test_no_dos_finales(self):
        self.final()
        otra = LiquidacionFinal(empresa=self.e1, empleado=self.ana, fecha_egreso=date(2026, 12, 1), causal='renuncia')
        with self.assertRaises(ValidationError):
            otra.full_clean()

    def test_api(self):
        r = self.cliente(self.gestor1).post('/api/liquidaciones-finales/', {
            'empleado': self.ana.pk, 'fecha_egreso': '2026-11-20', 'causal': 'renuncia'})
        self.assertEqual(r.status_code, 201, r.data)
        c = self.cliente(self.gestor1).post(f'/api/liquidaciones-finales/{r.data["id"]}/calcular/')
        self.assertEqual((c.status_code, c.data['tipo']), (200, 'liquidacion_final'))
        self.assertEqual(self.cliente(self.usr_ana).get('/api/liquidaciones-finales/').status_code, 403)
        self.assertEqual(self.cliente(self.admin2).get(f'/api/liquidaciones-finales/{r.data["id"]}/').status_code, 404)
        self.assertEqual(self.cliente(self.admin1).delete(f'/api/liquidaciones-finales/{r.data["id"]}/').status_code, 409)


class PlanillasTests(EgresoMixin, TestCase):
    def planilla(self, tipo, desde=date(2026, 10, 1), hasta=date(2026, 10, 31)):
        return planillas.preparar(PresentacionOficial.objects.create(empresa=self.e1, tipo=tipo, periodo_desde=desde, periodo_hasta=hasta))

    def test_ips_mensual_valida_y_exporta_seguro(self):
        p = self.planilla(PresentacionOficial.IPS_MENSUAL)
        ana = p.lineas.get(empleado=self.ana)
        self.assertEqual((ana.datos['salario_imponible'], ana.datos['aporte_trabajador'], ana.datos['aporte_patronal']),
                         ('3000000.00', '270000.00', '495000.00'))
        self.assertIn('Falta el número de asegurado IPS en el legajo.', ana.errores)
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.post(f'/api/planillas-oficiales/{p.pk}/presentada/', {'numero_comprobante': '1'}).status_code, 400)
        type(self.ana).objects.filter(pk__in=[self.ana.pk, self.beto.pk]).update(numero_asegurado_ips='=HYPERLINK("x")')
        cliente.post(f'/api/planillas-oficiales/{p.pk}/preparar/')
        csv = cliente.get(f'/api/planillas-oficiales/{p.pk}/exportar/?formato=csv').content.decode('utf-8-sig')
        self.assertIn("'=HYPERLINK", csv)  # protegido contra fórmulas
        self.assertIn('3000000', csv.replace(',00', ''))
        r = cliente.post(f'/api/planillas-oficiales/{p.pk}/presentada/', {'numero_comprobante': 'REI-123'})
        self.assertEqual((r.status_code, r.data['estado']), (200, 'presentada'))
        self.assertEqual(self.cliente(self.gestor1).post(f'/api/planillas-oficiales/{p.pk}/rechazada/', {'motivo': 'x'}).status_code, 403)

    def test_mtess_anual(self):
        p = self.planilla(PresentacionOficial.MTESS_SUELDOS, date(2026, 1, 1), date(2026, 12, 31))
        ana = p.lineas.get(empleado=self.ana)
        self.assertEqual((ana.datos['mes_10'], ana.datos['total']), ('3000000.00', '3000000.00'))
        e = self.planilla(PresentacionOficial.MTESS_EMPLEADOS, date(2026, 1, 1), date(2026, 12, 31))
        self.assertIn('Falta el sexo.', e.lineas.get(empleado=self.ana).errores)
        self.assertEqual(self.cliente(self.usr_ana).get('/api/planillas-oficiales/').status_code, 403)


class ReportesTests(EgresoMixin, TestCase):
    def test_reportes_segun_perfil(self):
        claves = [r['clave'] for r in self.cliente(self.admin1).get('/api/reportes/').data]
        self.assertIn('nomina_por_concepto', claves)
        self.assertEqual(self.cliente(self.usr_ana).get('/api/reportes/').data, [])
        self.assertEqual(self.cliente(self.usr_ana).get('/api/reportes/legajos/').status_code, 403)
        r = self.cliente(self.admin1).get('/api/reportes/nomina_por_empleado/?desde=2026-10-01&hasta=2026-10-31').data
        self.assertEqual({f['codigo']: Decimal(f['neto']) for f in r['filas']}['E001'], Decimal('2730000'))
        conceptos = {f['codigo'] for f in self.cliente(self.gestor1).get('/api/reportes/nomina_por_concepto/').data['filas']}
        self.assertNotIn('IPS_PATRONAL', conceptos)  # el gestor no ve el costo del empleador
        legajos = self.cliente(self.gestor_norte).get('/api/reportes/legajos/').data['filas']
        self.assertEqual([f['codigo'] for f in legajos], ['E002'])
        x = self.cliente(self.admin1).get('/api/reportes/asistencia/?desde=2026-10-01&hasta=2026-10-31&formato=xlsx')
        self.assertEqual(x['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        aguinaldo = self.cliente(self.admin1).get('/api/reportes/aguinaldo/?anio=2026').data['filas']
        self.assertEqual(Decimal(aguinaldo[0]['devengado']), Decimal('250000'))
        self.assertEqual(self.cliente(self.admin1).get('/api/reportes/no-existe/').status_code, 404)
        self.assertEqual(CorridaNomina.objects.filter(estado='cerrada').count(), 1)
