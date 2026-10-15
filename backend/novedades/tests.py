"""Novedades, descuentos autorizados, anticipos y préstamos (fase 9; §4.4 y §8)."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from asistencia.models import ConfiguracionMarcacion
from core.datos_prueba import EscenarioMixin
from empleados.models import DocumentoEmpleado, TipoDocumento
from nomina.models import ConceptoNomina
from novedades import servicios
from novedades.models import Anticipo, CuotaRecuperacion, DescuentoAutorizado, Novedad, Prestamo, saldo_de


class NovedadesMixin(EscenarioMixin):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        tipo = TipoDocumento.objects.filter(empresa=None).first()
        cls.doc_ana = DocumentoEmpleado.objects.create(empresa=cls.e1, empleado=cls.ana, tipo_documento=tipo, archivo='x.pdf',
                                                       nombre_original='autorizacion.pdf', sha256='0' * 64)
        cls.comision = ConceptoNomina.objects.get(empresa=None, codigo='COMISION')
        cls.bono = ConceptoNomina.objects.get(empresa=None, codigo='BONO')
        cls.sindical = ConceptoNomina.objects.get(empresa=None, codigo='CUOTA_SINDICAL')
        cls.ips = ConceptoNomina.objects.get(empresa=None, codigo='IPS_TRABAJADOR')


class ModelosTests(NovedadesMixin, TestCase):
    def test_comision_calcula_base_por_tasa(self):
        n = Novedad(empresa=self.e1, empleado=self.ana, concepto=self.comision, periodo_desde=date(2026, 9, 1),
                    periodo_hasta=date(2026, 9, 30), cantidad=Decimal('15000000'), tasa=Decimal('3'), origen='comision',
                    descripcion='Ventas de septiembre')
        n.full_clean()
        self.assertEqual(n.importe(), Decimal('450000'))

    def test_novedad_sin_importe_negativa_o_de_aporte_no_vale(self):
        base = dict(empresa=self.e1, empleado=self.ana, periodo_desde=date(2026, 9, 1), periodo_hasta=date(2026, 9, 30), descripcion='x')
        for extra in ({'concepto': self.comision}, {'concepto': self.comision, 'monto': Decimal('-1')},
                      {'concepto': self.ips, 'monto': Decimal('1')}):
            with self.assertRaises(ValidationError, msg=extra):
                Novedad(**base, **extra).full_clean()

    def test_descuento_exige_autorizacion_documentada(self):
        d = DescuentoAutorizado(empresa=self.e1, empleado=self.ana, concepto=self.sindical, tipo='sindical',
                                monto_cuota=Decimal('50000'), fecha_desde=date(2026, 9, 1))
        with self.assertRaisesMessage(ValidationError, 'autorización firmada'):
            d.full_clean()
        d.documento = self.doc_ana
        with self.assertRaisesMessage(ValidationError, 'autorización escrita'):
            d.full_clean()
        d.autorizado_por_empleado = True
        d.full_clean()
        d.concepto = self.bono
        with self.assertRaisesMessage(ValidationError, 'solo descuentos'):
            d.full_clean()

    def test_plan_del_prestamo(self):
        p = Prestamo(empresa=self.e1, empleado=self.ana, fecha=date(2026, 10, 1), capital=Decimal('1000000'), cantidad_cuotas=3,
                     primer_mes=date(2026, 11, 1), motivo='x')
        plan = p.plan()
        self.assertEqual([m for _, m, _ in plan], [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)])
        self.assertEqual([c for _, _, c in plan], [Decimal('333333'), Decimal('333333'), Decimal('333334')])
        p.tasa_interes_mensual = Decimal('2')
        cuotas = [c for _, _, c in p.plan()]
        self.assertEqual(cuotas[0], Decimal('346755'))  # sistema francés
        self.assertGreater(sum(cuotas), Decimal('1000000'))


class ServiciosTests(NovedadesMixin, TestCase):
    def test_anticipo_completo(self):
        a = Anticipo.objects.create(empresa=self.e1, empleado=self.ana, fecha=date(2026, 10, 1), monto_solicitado=Decimal('900000'),
                                    cuotas=2, primer_mes=date(2026, 11, 1), motivo='Urgencia', creado_por=self.usr_ana)
        with self.assertRaises(ValidationError):
            servicios.pagar_anticipo(a, self.admin1, 'efectivo')  # sin aprobar
        servicios.aprobar_anticipo(a, self.admin1, Decimal('700000'))
        servicios.pagar_anticipo(a, self.admin1, 'transferencia', 'TRF-1')
        a.refresh_from_db()
        self.assertEqual(a.estado, Anticipo.PAGADO)
        self.assertEqual([(c.mes, c.monto) for c in a.cuotas_recuperacion.all()],
                         [(date(2026, 11, 1), Decimal('350000')), (date(2026, 12, 1), Decimal('350000'))])
        self.assertEqual(saldo_de(a), Decimal('700000'))
        with self.assertRaises(ValidationError):
            servicios.anular_anticipo(a, self.admin1, 'x')  # ya pagado
        servicios.cancelar_saldo(a, self.admin1, 'Devolvió en efectivo')
        a.refresh_from_db()
        self.assertEqual((a.estado, saldo_de(a)), (Anticipo.RECUPERADO, Decimal('0')))
        self.assertEqual(a.cuotas_recuperacion.filter(estado=CuotaRecuperacion.PAGADA_APARTE).count(), 2)

    def test_prestamo_necesita_autorizacion_y_genera_cuotas(self):
        p = Prestamo.objects.create(empresa=self.e1, empleado=self.ana, fecha=date(2026, 10, 1), capital=Decimal('1200000'),
                                    cantidad_cuotas=4, primer_mes=date(2026, 11, 1), motivo='x')
        with self.assertRaisesMessage(ValidationError, 'autorización firmada'):
            servicios.aprobar_prestamo(p, self.admin1)
        p.documento = self.doc_ana
        p.save()
        servicios.aprobar_prestamo(p, self.admin1)
        servicios.desembolsar_prestamo(p, self.admin1, 'TRF-2')
        p.refresh_from_db()
        self.assertEqual((p.estado, p.cuotas_recuperacion.count(), saldo_de(p)), (Prestamo.DESEMBOLSADO, 4, Decimal('1200000')))
        with self.assertRaises(ValidationError):
            servicios.desembolsar_prestamo(p, self.admin1)  # no se desembolsa dos veces

    def test_novedad_aplicada_no_se_anula(self):
        n = Novedad.objects.create(empresa=self.e1, empleado=self.ana, concepto=self.bono, periodo_desde=date(2026, 9, 1),
                                   periodo_hasta=date(2026, 9, 30), monto=1, descripcion='x')
        servicios.aprobar_novedad(n, self.admin1)
        Novedad.objects.filter(pk=n.pk).update(estado=Novedad.APLICADA)
        n.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, 'rectificación'):
            servicios.anular_novedad(n, self.admin1, 'x')


class ApiTests(NovedadesMixin, TestCase):
    def test_gestor_carga_y_no_aprueba_novedades(self):
        r = self.cliente(self.gestor1).post('/api/novedades/', {
            'empleado': self.ana.pk, 'concepto': self.comision.pk, 'periodo_desde': '2026-09-01', 'periodo_hasta': '2026-09-30',
            'cantidad': '10000000', 'tasa': '2', 'origen': 'comision', 'descripcion': 'Ventas'})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data['estado'], r.data['importe']), ('pendiente', '200000'))
        self.assertEqual(self.cliente(self.gestor1).post(f'/api/novedades/{r.data["id"]}/aprobar/').status_code, 403)
        a = self.cliente(self.admin1).post(f'/api/novedades/{r.data["id"]}/aprobar/')
        self.assertEqual(a.data['estado'], 'aprobada')
        self.assertEqual(self.cliente(self.admin1).patch(f'/api/novedades/{r.data["id"]}/', {'monto': '1'}).status_code, 400)

    def test_empleado_pide_anticipo_solo_para_si(self):
        cliente = self.cliente(self.usr_ana)
        r = cliente.post('/api/anticipos/', {'empleado': self.ana.pk, 'fecha': '2026-10-14', 'monto_solicitado': '500000',
                                             'motivo': 'Gastos médicos'})
        self.assertEqual((r.status_code, r.data.get('estado')), (201, 'solicitado'), r.data)
        self.assertEqual(cliente.post(f'/api/anticipos/{r.data["id"]}/aprobar/').status_code, 403)
        self.assertEqual(cliente.patch(f'/api/anticipos/{r.data["id"]}/', {'monto_solicitado': '1'}).status_code, 403)
        self.assertEqual(cliente.post('/api/novedades/', {}).status_code, 403)
        self.assertEqual(cliente.post('/api/prestamos/', {}).status_code, 403)

    def test_separacion_de_funciones(self):
        ConfiguracionMarcacion.de(self.e1)
        ConfiguracionMarcacion.objects.filter(empresa=self.e1).update(exigir_aprobador_distinto=True)
        r = self.cliente(self.admin1).post('/api/anticipos/', {'empleado': self.ana.pk, 'fecha': '2026-10-14',
                                                               'monto_solicitado': '500000', 'motivo': 'x'})
        self.assertEqual(self.cliente(self.admin1).post(f'/api/anticipos/{r.data["id"]}/aprobar/').status_code, 400)

    def test_comprobante_de_anticipo(self):
        from novedades.models import ReciboAnticipo
        type(self.ana).objects.filter(pk=self.ana.pk).update(aporta_ips=False)
        a = Anticipo.objects.create(empresa=self.e1, empleado=self.ana, fecha=date(2026, 3, 9), monto_solicitado=600000, cuotas=2,
                                    primer_mes=date(2026, 4, 1), motivo='Urgencia')
        servicios.aprobar_anticipo(a, self.admin1)
        servicios.pagar_anticipo(a, self.admin1, 'transferencia', 'TRF-9', fecha=date(2026, 3, 10))
        recibo = ReciboAnticipo.objects.get(anticipo=a)
        self.assertEqual((recibo.numero, recibo.fecha_emision, recibo.monto), ('A2026-000001', date(2026, 3, 10), Decimal('600000')))
        b = Anticipo.objects.create(empresa=self.e1, empleado=self.beto, fecha=date(2026, 3, 11), monto_solicitado=100000, motivo='x')
        servicios.aprobar_anticipo(b, self.admin1)
        servicios.pagar_anticipo(b, self.admin1, 'efectivo', fecha=date(2026, 3, 11))
        self.assertEqual(ReciboAnticipo.objects.get(anticipo=b).numero, 'A2026-000002')  # correlativo
        # La empleada ve el suyo (sin número patronal: no aporta al IPS) y no el de otro.
        cliente = self.cliente(self.usr_ana)
        datos = cliente.get(f'/api/recibos-anticipo/{recibo.pk}/').data
        self.assertNotIn('numero_patronal_ips', datos['empresa'])
        self.assertEqual([c['numero'] for c in datos['cuotas']], [1, 2])
        self.assertEqual(cliente.get(f'/api/recibos-anticipo/{ReciboAnticipo.objects.get(anticipo=b).pk}/').status_code, 404)
        self.assertEqual(cliente.post(f'/api/anticipos/{a.pk}/comprobante/').data['numero'], 'A2026-000001')
        self.assertEqual(self.cliente(self.admin2).get(f'/api/recibos-anticipo/{recibo.pk}/').status_code, 404)
        self.assertIn('numero_patronal_ips', self.cliente(self.admin1).get(
            f'/api/recibos-anticipo/{ReciboAnticipo.objects.get(anticipo=b).pk}/').data['empresa'])
        # Anular el comprobante no deshace el pago; se puede emitir otro, con número nuevo.
        self.assertEqual(cliente.post(f'/api/recibos-anticipo/{recibo.pk}/anular/', {'motivo': 'x'}).status_code, 403)
        self.cliente(self.admin1).post(f'/api/recibos-anticipo/{recibo.pk}/anular/', {'motivo': 'Error de impresión'})
        nuevo = self.cliente(self.admin1).post(f'/api/anticipos/{a.pk}/comprobante/').data
        self.assertEqual(nuevo['numero'], 'A2026-000003')
        a.refresh_from_db()
        self.assertEqual(a.estado, Anticipo.PAGADO)

    def test_prestamo_por_api_con_plan(self):
        cliente = self.cliente(self.admin1)
        r = cliente.post('/api/prestamos/', {'empleado': self.ana.pk, 'fecha': '2026-10-01', 'capital': '600000',
                                             'cantidad_cuotas': 3, 'primer_mes': '2026-11-01', 'motivo': 'x', 'documento': self.doc_ana.pk})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['monto_cuota'], '200000')
        plan = cliente.get(f'/api/prestamos/{r.data["id"]}/plan/').data
        self.assertEqual((len(plan['cuotas']), plan['total']), (3, '600000'))
        cliente.post(f'/api/prestamos/{r.data["id"]}/aprobar/')
        d = cliente.post(f'/api/prestamos/{r.data["id"]}/desembolsar/', {'referencia': 'TRF'})
        self.assertEqual((d.data['estado'], Decimal(d.data['saldo'])), ('desembolsado', Decimal('600000')))
        self.assertEqual(self.cliente(self.usr_ana).get('/api/cuotas-recuperacion/').data['count'], 3)
        self.assertIn(cliente.post('/api/cuotas-recuperacion/', {}).status_code, (403, 405))
