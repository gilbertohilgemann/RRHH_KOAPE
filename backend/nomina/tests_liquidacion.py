"""Motor y ciclo de la nómina (fase 10; §8 y pruebas de §13)."""
import hashlib
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import TestCase

from asistencia import motor as motor_asistencia
from asistencia.importacion import periodo_cerrado
from asistencia.models import AutorizacionHorasExtra, IncidenciaAsistencia, Marcacion
from contratos.models import ContratoEmpleado, EsquemaSalarial
from core.datos_prueba import EscenarioMixin
from jornada.models import AsignacionHorario, Horario, RegimenJornada, TramoHorario
from legal import servicios as legal
from legal.models import ConjuntoReglas
from nomina import liquidar
from nomina.models import (AsignacionCostoPatronal, ConceptoNomina, CorridaNomina, PagoNomina, PeriodoNomina, ReciboSueldo,
                           ReglaConcepto)
from novedades.models import Anticipo, CuotaRecuperacion, Novedad

ZONA = ZoneInfo('America/Asuncion')
OCTUBRE = (date(2026, 10, 1), date(2026, 10, 31))


def linea(liq, codigo):
    return liq.lineas.filter(codigo=codigo).first()


class NominaMixin(EscenarioMixin):
    """Ana: mensual 3.000.000, oficina lun–vie 08–12 y 13–17, marcó todos los días hábiles de octubre.
    Beto: jornalero sin marcas (no cobra nada, no da error)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        mensual = EsquemaSalarial.objects.get(empresa=None, codigo='MENSUAL')
        jornal = EsquemaSalarial.objects.get(empresa=None, codigo='JORNAL')
        for empleado, esquema, salario in ((cls.ana, mensual, 3000000), (cls.beto, jornal, 120000)):
            ContratoEmpleado.objects.create(empresa=cls.e1, empleado=empleado, fecha_inicio=date(2025, 1, 2), esquema_salarial=esquema,
                                            salario=salario).activar(cls.admin1)
        cls.oficina = Horario.objects.create(empresa=cls.e1, codigo='OF', nombre='Oficina',
                                             regimen=RegimenJornada.objects.get(empresa=None, codigo='DIURNA'), tolerancia_minutos=10)
        for dia in range(5):
            TramoHorario.objects.create(horario=cls.oficina, dia_semana=dia, hora_inicio=time(8), hora_fin=time(12), orden=1)
            TramoHorario.objects.create(horario=cls.oficina, dia_semana=dia, hora_inicio=time(13), hora_fin=time(17), orden=2)
        AsignacionHorario.objects.create(empresa=cls.e1, empleado=cls.ana, horario=cls.oficina, vigente_desde=date(2025, 1, 2))

    def setUp(self):
        self.contador = 0
        self.aprobar_reglas()
        dia = OCTUBRE[0]
        while dia <= OCTUBRE[1]:
            if dia.weekday() < 5:
                self.marcar(dia, '08:00', '17:00')
            dia += timedelta(days=1)
        self.recalcular_asistencia()
        self.periodo = PeriodoNomina.objects.create(empresa=self.e1, codigo='2026-10', fecha_desde=OCTUBRE[0], fecha_hasta=OCTUBRE[1])

    def aprobar_reglas(self):
        conjunto = ConjuntoReglas.objects.get(empresa=None, codigo='PY-LABORAL')
        legal.revisar(conjunto, self.plataforma)
        legal.aprobar(conjunto, self.admin1)
        ReglaConcepto.objects.filter(empresa=None).update(estado=ReglaConcepto.APROBADA)

    def marcar(self, dia, entrada, salida, empleado=None):
        for hora, tipo in ((entrada, Marcacion.ENTRADA), (salida, Marcacion.SALIDA)):
            self.contador += 1
            Marcacion.objects.create(
                empresa=self.e1, empleado=empleado or self.ana, tipo=tipo, metodo=Marcacion.MANUAL, nivel_verificacion='manual_aprobado',
                fecha_hora=datetime.combine(dia, time.fromisoformat(hora), tzinfo=ZONA),
                huella_deduplicacion=hashlib.sha256(f'n{self.contador}'.encode()).hexdigest())

    def recalcular_asistencia(self):
        motor_asistencia.calcular(self.ana, *OCTUBRE)

    def liquidacion(self, corrida, empleado=None):
        return corrida.liquidaciones.get(empleado=empleado or self.ana)

    def cerrada(self):
        corrida = liquidar.crear(self.periodo, self.gestor1)
        liquidar.revisar(corrida, self.gestor1)
        liquidar.aprobar(corrida, self.admin1)
        return liquidar.cerrar(corrida, self.admin1)


class MotorTests(NominaMixin, TestCase):
    def test_mensual_completo_con_ips_separados(self):
        corrida = liquidar.crear(self.periodo, self.gestor1)
        self.assertFalse(corrida.es_simulacion, corrida.advertencias)
        liq = self.liquidacion(corrida)
        self.assertEqual((linea(liq, 'SUELDO').importe, liq.dias_pagados), (Decimal('3000000'), Decimal('30')))
        self.assertIn('3.000.000 / 30 días', linea(liq, 'SUELDO').explicacion)
        self.assertEqual(linea(liq, 'IPS_TRABAJADOR').importe, Decimal('270000'))
        self.assertEqual(linea(liq, 'IPS_PATRONAL').importe_con_signo, Decimal('0'))  # nunca resta del neto
        self.assertEqual((liq.bruto, liq.aportes_trabajador, liq.neto), (Decimal('3000000'), Decimal('270000'), Decimal('2730000')))
        self.assertEqual((liq.aportes_patronales, liq.costo_empleador), (Decimal('495000'), Decimal('3495000')))
        self.assertEqual(liq.provision_aguinaldo, Decimal('250000'))  # aparte: no suma al costo
        beto = self.liquidacion(corrida, self.beto)
        self.assertEqual((beto.neto, beto.estado_calculo), (Decimal('0'), 'advertencia'))  # jornalero sin días trabajados

    def test_sin_ips_se_liquida_sin_aportes(self):
        type(self.ana).objects.filter(pk=self.ana.pk).update(aporta_ips=False)
        corrida = liquidar.crear(self.periodo, self.gestor1)
        liq = self.liquidacion(corrida)
        self.assertIsNone(linea(liq, 'IPS_TRABAJADOR'))
        self.assertIsNone(linea(liq, 'IPS_PATRONAL'))
        self.assertEqual((liq.bruto, liq.neto, liq.aportes_patronales, liq.costo_empleador),
                         (Decimal('3000000'), Decimal('3000000'), Decimal('0'), Decimal('3000000')))
        self.assertIn('No aporta al IPS', ' '.join(liq.advertencias))
        from cumplimiento import servicios as planillas
        from cumplimiento.models import PresentacionOficial
        liquidar.revisar(corrida, self.gestor1)
        liquidar.aprobar(corrida, self.admin1)
        liquidar.cerrar(corrida, self.admin1)
        planilla = planillas.preparar(PresentacionOficial.objects.create(
            empresa=self.e1, tipo=PresentacionOficial.IPS_MENSUAL, periodo_desde=OCTUBRE[0], periodo_hasta=OCTUBRE[1]))
        self.assertFalse(planilla.lineas.filter(empleado=self.ana).exists())  # no va en la planilla del IPS
        mtess = planillas.preparar(PresentacionOficial.objects.create(
            empresa=self.e1, tipo=PresentacionOficial.MTESS_SUELDOS, periodo_desde=date(2026, 1, 1), periodo_hasta=date(2026, 12, 31)))
        self.assertTrue(mtess.lineas.filter(empleado=self.ana).exists())  # en la del MTESS sí

    def test_recalcular_no_duplica(self):
        corrida = liquidar.crear(self.periodo, self.gestor1)
        liquidar.recalcular(corrida, self.gestor1)
        liq = self.liquidacion(corrida)
        self.assertEqual(liq.lineas.filter(codigo='SUELDO').count(), 1)
        self.assertEqual(corrida.liquidaciones.count(), 2)
        with self.assertRaises(ValidationError):
            liquidar.crear(self.periodo, self.gestor1)  # una sola liquidación regular por período

    def test_ausencia_injustificada_descuenta_y_justificada_no(self):
        Marcacion.objects.filter(fecha_hora__date=date(2026, 10, 5)).delete()
        self.recalcular_asistencia()
        corrida = liquidar.crear(self.periodo, self.gestor1)
        self.assertEqual(linea(self.liquidacion(corrida), 'DESCUENTO_AUSENCIA').importe, Decimal('100000'))
        IncidenciaAsistencia.objects.filter(empleado=self.ana, fecha=date(2026, 10, 5), tipo='ausencia').update(estado='justificada')
        liquidar.recalcular(corrida, self.gestor1)
        self.assertIsNone(linea(self.liquidacion(corrida), 'DESCUENTO_AUSENCIA'))

    def test_solo_las_horas_extra_autorizadas_se_pagan(self):
        Marcacion.objects.filter(fecha_hora__date=date(2026, 10, 6), tipo='salida').update(
            fecha_hora=datetime(2026, 10, 6, 19, 0, tzinfo=ZONA))
        self.recalcular_asistencia()
        corrida = liquidar.crear(self.periodo, self.gestor1)
        self.assertIsNone(linea(self.liquidacion(corrida), 'HORAS_EXTRA_DIURNAS'))  # candidatas, sin autorizar
        AutorizacionHorasExtra.objects.create(empresa=self.e1, empleado=self.ana, fecha=date(2026, 10, 6), minutos_solicitados=120,
                                              minutos_aprobados=120, estado='aprobada', motivo='x')
        self.recalcular_asistencia()
        liquidar.recalcular(corrida, self.gestor1)
        liq = self.liquidacion(corrida)
        self.assertEqual(linea(liq, 'HORAS_EXTRA_DIURNAS').importe, Decimal('37500'))  # 2 h × 12.500 × 1,5
        self.assertEqual(linea(liq, 'IPS_TRABAJADOR').importe, Decimal('273375'))  # la extra suma a la base de IPS

    def test_novedades_fijos_descuentos_y_cuotas(self):
        bono = ConceptoNomina.objects.get(empresa=None, codigo='BONO')
        Novedad.objects.create(empresa=self.e1, empleado=self.ana, concepto=bono, periodo_desde=OCTUBRE[0], periodo_hasta=OCTUBRE[1],
                               monto=200000, descripcion='Premio', estado=Novedad.APROBADA)
        Novedad.objects.create(empresa=self.e1, empleado=self.ana, concepto=bono, periodo_desde=OCTUBRE[0], periodo_hasta=OCTUBRE[1],
                               monto=999, descripcion='Sin aprobar')
        anticipo = Anticipo.objects.create(empresa=self.e1, empleado=self.ana, fecha=date(2026, 9, 20), monto_solicitado=500000,
                                           monto_aprobado=500000, motivo='x', estado=Anticipo.PAGADO)
        concepto_anticipo = ConceptoNomina.objects.get(empresa=None, codigo='ANTICIPO')
        CuotaRecuperacion.objects.create(empresa=self.e1, empleado=self.ana, anticipo=anticipo, concepto=concepto_anticipo, numero=1,
                                         mes=date(2026, 10, 1), monto=500000)
        corrida = liquidar.crear(self.periodo, self.gestor1)
        liq = self.liquidacion(corrida)
        self.assertEqual(linea(liq, 'BONO').importe, Decimal('200000'))
        self.assertEqual(linea(liq, 'ANTICIPO').importe_con_signo, Decimal('-500000'))
        self.assertEqual(linea(liq, 'IPS_TRABAJADOR').importe, Decimal('288000'))  # 3.200.000 × 9 %
        self.assertEqual(liq.neto, Decimal('3200000') - Decimal('288000') - Decimal('500000'))
        liquidar.revisar(corrida, self.gestor1)
        liquidar.aprobar(corrida, self.admin1)
        liquidar.cerrar(corrida, self.admin1)
        anticipo.refresh_from_db()
        self.assertEqual(anticipo.estado, Anticipo.RECUPERADO)
        self.assertEqual(Novedad.objects.get(descripcion='Premio').estado, Novedad.APLICADA)
        self.assertEqual(Novedad.objects.get(descripcion='Sin aprobar').estado, Novedad.PENDIENTE)


class CicloTests(NominaMixin, TestCase):
    def test_simulacion_no_se_aprueba(self):
        ReglaConcepto.objects.filter(empresa=None, concepto__codigo='IPS_TRABAJADOR').update(estado=ReglaConcepto.BORRADOR)
        corrida = liquidar.crear(self.periodo, self.gestor1)
        self.assertTrue(corrida.es_simulacion)
        liquidar.revisar(corrida, self.gestor1)
        with self.assertRaisesMessage(ValidationError, 'simulación'):
            liquidar.aprobar(corrida, self.admin1)

    def test_sin_contrato_bloquea_la_aprobacion(self):
        ContratoEmpleado.objects.filter(empleado=self.beto).update(estado=ContratoEmpleado.ANULADO)
        corrida = liquidar.crear(self.periodo, self.gestor1)
        self.assertEqual(self.liquidacion(corrida, self.beto).estado_calculo, 'error')
        liquidar.revisar(corrida, self.gestor1)
        with self.assertRaisesMessage(ValidationError, 'errores'):
            liquidar.aprobar(corrida, self.admin1)

    def test_cerrar_es_definitivo(self):
        corrida = self.cerrada()
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.estado, PeriodoNomina.CERRADO)
        self.assertTrue(periodo_cerrado(self.e1, date(2026, 10, 15)))
        self.assertFalse(periodo_cerrado(self.e1, date(2026, 11, 1)))
        self.assertEqual(AsignacionCostoPatronal.objects.filter(corrida=corrida).count(), 2)
        for funcion in (lambda: liquidar.recalcular(corrida, self.admin1), lambda: liquidar.anular(corrida, self.admin1, 'x')):
            with self.assertRaises(ValidationError):
                funcion()
        # La asistencia de un período cerrado no se recalcula.
        dia = motor_asistencia.calcular(self.ana, date(2026, 10, 5))
        self.assertEqual(dia, [])

    def test_rectificacion_paga_la_diferencia(self):
        original = self.cerrada()
        bono = ConceptoNomina.objects.get(empresa=None, codigo='BONO')
        Novedad.objects.create(empresa=self.e1, empleado=self.ana, concepto=bono, periodo_desde=OCTUBRE[0], periodo_hasta=OCTUBRE[1],
                               monto=100000, descripcion='Olvidado', estado=Novedad.APROBADA)
        rect = liquidar.rectificar(original, self.admin1, 'Faltó un premio')
        liq = self.liquidacion(rect)
        self.assertEqual((liq.neto_anterior, liq.a_pagar), (Decimal('2730000'), Decimal('91000')))  # 100.000 − 9 % de IPS
        liquidar.revisar(rect, self.gestor1)
        liquidar.aprobar(rect, self.admin1)
        liquidar.cerrar(rect, self.admin1)
        original.refresh_from_db()
        self.assertTrue(original.rectificada)
        self.assertEqual(self.liquidacion(original).neto, Decimal('2730000'))  # la original no se toca
        self.assertEqual(Novedad.objects.get(descripcion='Olvidado').corrida, rect.pk)
        with self.assertRaises(ValidationError):
            liquidar.rectificar(original, self.admin1, 'otra vez')

    def test_recibos_numerados_y_pagos(self):
        corrida = self.cerrada()
        recibos = liquidar.emitir_recibos(corrida, self.admin1)
        self.assertEqual(sorted(r.numero for r in recibos), ['R2026-000001', 'R2026-000002'])
        self.assertEqual(liquidar.emitir_recibos(corrida, self.admin1), [])  # no duplica
        creados, a_recuperar = liquidar.registrar_pagos(corrida, self.admin1, date(2026, 10, 31), 'transferencia', 'LOTE-1')
        self.assertEqual([(p.empleado_id, p.monto) for p in creados], [(self.ana.pk, Decimal('2730000'))])  # Beto cobra 0
        liquidar.confirmar_pago(creados[0], self.admin1)
        self.assertEqual(self.liquidacion(corrida).estado_pago, 'pagado')
        with self.assertRaises(ValidationError):
            liquidar.anular_pago(creados[0], self.admin1, 'x')


class ApiTests(NominaMixin, TestCase):
    def test_gestor_calcula_pero_no_aprueba_ni_ve_el_costo(self):
        cliente = self.cliente(self.gestor1)
        r = cliente.post('/api/corridas-nomina/', {'periodo': self.periodo.pk})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertNotIn('total_costo_empleador', r.data)
        pk = r.data['id']
        self.assertEqual(cliente.post(f'/api/corridas-nomina/{pk}/revisar/').data['estado'], 'revisada')
        self.assertEqual(cliente.post(f'/api/corridas-nomina/{pk}/aprobar/').status_code, 403)
        liq = cliente.get(f'/api/liquidaciones-nomina/?corrida={pk}&empleado={self.ana.pk}').data['results'][0]
        detalle = cliente.get(f'/api/liquidaciones-nomina/{liq["id"]}/').data
        self.assertNotIn('IPS_PATRONAL', [l['codigo'] for l in detalle['lineas']])
        self.assertEqual(cliente.get('/api/costo-patronal/').status_code, 403)
        admin = self.cliente(self.admin1)
        self.assertEqual(admin.post(f'/api/corridas-nomina/{pk}/aprobar/').data['estado'], 'aprobada')
        self.assertEqual(admin.post(f'/api/corridas-nomina/{pk}/cerrar/').data['estado'], 'cerrada')
        self.assertIn('total_costo_empleador', admin.get(f'/api/corridas-nomina/{pk}/').data)
        costo = admin.get('/api/costo-patronal/?agrupar=empleado').data
        self.assertEqual(Decimal(costo['totales']['total']), Decimal('3495000'))

    def test_el_empleado_ve_solo_sus_recibos_publicados(self):
        corrida = self.cerrada()
        liquidar.emitir_recibos(corrida, self.admin1)
        empleado = self.cliente(self.usr_ana)
        self.assertEqual(empleado.get('/api/recibos/').data['count'], 0)  # sin publicar
        self.assertEqual(empleado.get('/api/corridas-nomina/').status_code, 403)
        self.assertEqual(empleado.get('/api/liquidaciones-nomina/').status_code, 403)
        liquidar.publicar_recibos(corrida, self.admin1)
        recibos = empleado.get('/api/recibos/').data['results']
        self.assertEqual([r['empleado'] for r in recibos], [self.ana.pk])
        detalle = empleado.get(f'/api/recibos/{recibos[0]["id"]}/').data
        self.assertNotIn('costo_empleador', detalle)
        self.assertNotIn('IPS_PATRONAL', [l['codigo'] for l in detalle['lineas']])
        self.assertEqual(Decimal(detalle['neto']), Decimal('2730000'))
        recibo_beto = ReciboSueldo.objects.get(empleado=self.beto)
        self.assertEqual(empleado.get(f'/api/recibos/{recibo_beto.pk}/').status_code, 404)

    def test_otra_empresa_no_ve_ni_toca(self):
        corrida = liquidar.crear(self.periodo, self.gestor1)
        otro = self.cliente(self.admin2)
        self.assertEqual(otro.get(f'/api/corridas-nomina/{corrida.pk}/').status_code, 404)
        self.assertEqual(otro.post(f'/api/corridas-nomina/{corrida.pk}/aprobar/').status_code, 404)
        self.assertEqual(otro.post('/api/corridas-nomina/', {'periodo': self.periodo.pk}).status_code, 400)
        self.assertEqual(PagoNomina.objects.count(), 0)
        self.assertEqual(CorridaNomina.objects.count(), 1)
