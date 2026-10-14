"""Licencias, permisos, vacaciones y certificados (fase 7; §4.3 y pruebas de §13)."""
from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from asistencia.models import ConfiguracionMarcacion, DiaAsistencia, IncidenciaAsistencia, Marcacion
from asistencia.tests_motor import MotorMixin
from licencias import servicios
from licencias.models import (EscalaVacaciones, MovimientoVacaciones, SolicitudLicencia, TipoLicencia, contar_dias,
                              saldo_vacaciones)

LUNES = date(2026, 10, 5)
VIERNES = date(2026, 10, 9)


class LicenciasMixin(MotorMixin):
    def setUp(self):
        super().setUp()
        self.vac = TipoLicencia.objects.get(empresa=None, codigo='VAC')
        self.reposo = TipoLicencia.objects.get(empresa=None, codigo='REPOSO')
        self.duelo = TipoLicencia.objects.get(empresa=None, codigo='DUELO')
        self.particular = TipoLicencia.objects.get(empresa=None, codigo='PARTICULAR')

    def solicitud(self, tipo, desde, hasta=None, empleado=None, **extra):
        s = SolicitudLicencia(empresa=self.e1, empleado=empleado or self.ana, tipo=tipo, fecha_desde=desde,
                              fecha_hasta=hasta or desde, **extra)
        s.full_clean()
        s.calcular()
        s.save()
        return s

    def devengo(self, dias, empleado=None):
        return MovimientoVacaciones.objects.create(empresa=self.e1, empleado=empleado or self.ana, fecha=date(2026, 1, 2),
                                                   tipo=MovimientoVacaciones.AJUSTE, dias=dias, motivo='Saldo inicial')


class ReglasTests(LicenciasMixin, TestCase):
    def test_datos_legales_precargados_sin_verificar(self):
        self.assertTrue(self.vac.consume_vacaciones)
        self.assertFalse(TipoLicencia.objects.filter(empresa=None, verificado=True).exists())
        self.assertEqual([EscalaVacaciones.dias_para(self.e1, n)[0] for n in (1, 4, 5, 9, 10, 25)], [12, 12, 18, 18, 30, 30])

    def test_escala_propia_de_la_empresa_reemplaza_la_global(self):
        EscalaVacaciones.objects.create(empresa=self.e1, desde_anios=1, dias=20)
        self.assertEqual(EscalaVacaciones.dias_para(self.e1, 1)[0], 20)
        self.assertEqual(EscalaVacaciones.dias_para(self.e2, 1)[0], 12)

    def test_dias_habiles_segun_horario_y_feriados(self):
        self.assertEqual(contar_dias(self.ana, LUNES, date(2026, 10, 11), 'habiles'), 5)  # lunes a domingo, horario L–V
        self.assertEqual(contar_dias(self.ana, LUNES, date(2026, 10, 11), 'corridos'), 7)
        self.assertEqual(contar_dias(self.ana, date(2026, 5, 11), date(2026, 5, 15), 'habiles'), 3)  # 14 y 15 feriados

    def test_no_se_superponen_y_respeta_el_maximo(self):
        self.solicitud(self.vac, LUNES, VIERNES)
        with self.assertRaises(Exception):
            self.solicitud(self.reposo, VIERNES, date(2026, 10, 12))
        with self.assertRaises(Exception):
            self.solicitud(self.duelo, date(2026, 10, 12), date(2026, 10, 16))  # 5 días corridos, máximo 3

    def test_permisos_por_horas(self):
        with self.assertRaises(Exception):
            self.solicitud(self.vac, LUNES, hora_desde=time(8), hora_hasta=time(10))  # vacaciones no admite horas
        p = self.solicitud(self.particular, LUNES, hora_desde=time(8), hora_hasta=time(10))
        self.assertEqual((p.dias, p.minutos), (Decimal('0'), 120))
        self.solicitud(self.particular, LUNES, hora_desde=time(15), hora_hasta=time(17))  # otra franja del mismo día: vale
        with self.assertRaises(Exception):
            self.solicitud(self.particular, LUNES, hora_desde=time(9), hora_hasta=time(11))


class ServiciosTests(LicenciasMixin, TestCase):
    def test_aprobar_vacaciones_descuenta_saldo_y_cancelar_lo_devuelve(self):
        s = self.solicitud(self.vac, LUNES, VIERNES)
        with self.assertRaisesMessage(Exception, 'Saldo de vacaciones insuficiente'):
            servicios.aprobar(s, self.admin1)
        self.devengo(12)
        servicios.aprobar(s, self.admin1)
        self.assertEqual(saldo_vacaciones(self.ana), 7)
        servicios.cancelar(s, self.admin1, 'Se postergan')
        self.assertEqual(saldo_vacaciones(self.ana), 12)
        self.assertEqual(MovimientoVacaciones.objects.filter(solicitud=s).count(), 2)  # el goce no se borra

    def test_exige_documento_para_aprobar(self):
        s = self.solicitud(self.reposo, LUNES, VIERNES)
        with self.assertRaisesMessage(Exception, 'documento'):
            servicios.aprobar(s, self.admin1)

    def test_el_motor_marca_licencia_y_no_ausencia(self):
        s = self.solicitud(self.vac, LUNES, VIERNES)
        self.devengo(12)
        with self.captureOnCommitCallbacks(execute=True):
            servicios.aprobar(s, self.admin1)
        d = DiaAsistencia.objects.get(empleado=self.ana, fecha=LUNES)
        self.assertEqual((d.estado, d.licencia_id), (DiaAsistencia.LICENCIA, s.pk))
        self.assertNotIn('ausencia', self.incidencias(self.ana, LUNES))
        with self.captureOnCommitCallbacks(execute=True):
            servicios.cancelar(s, self.admin1, 'Error de carga')
        self.assertEqual(DiaAsistencia.objects.get(empleado=self.ana, fecha=LUNES).estado, DiaAsistencia.AUSENTE)

    def test_permiso_por_horas_justifica_la_llegada_tarde(self):
        self.marca(self.ana, '2026-10-05 10:00')
        self.marca(self.ana, '2026-10-05 17:00', Marcacion.SALIDA)
        self.assertEqual(self.dia(self.ana, LUNES).minutos_tardanza, 120)
        servicios.aprobar(self.solicitud(self.particular, LUNES, hora_desde=time(8), hora_hasta=time(10)), self.admin1)
        d = self.dia(self.ana, LUNES)
        self.assertEqual((d.minutos_tardanza, d.estado), (0, DiaAsistencia.PRESENTE))
        self.assertFalse(IncidenciaAsistencia.objects.filter(empleado=self.ana, fecha=LUNES, tipo='tardanza').exists())

    def test_devengo_por_aniversario_es_idempotente(self):
        # Ana ingresó el 02/01/2025: su primer aniversario es el 02/01/2026.
        creados = servicios.devengar([self.ana], date(2025, 10, 14), date(2026, 10, 14), self.admin1)
        self.assertEqual([(a, n, d) for _, a, n, d in creados], [(date(2026, 1, 2), 1, 12)])
        self.assertEqual(servicios.devengar([self.ana], date(2025, 10, 14), date(2026, 10, 14), self.admin1), [])
        self.assertEqual(saldo_vacaciones(self.ana), 12)
        self.assertEqual(servicios.proximo_aniversario(self.ana, date(2026, 10, 14)), date(2027, 1, 2))


class ApiTests(LicenciasMixin, TestCase):
    def test_el_empleado_pide_para_si_y_no_aprueba(self):
        cliente = self.cliente(self.usr_ana)
        r = cliente.post('/api/licencias/', {'empleado': self.ana.pk, 'tipo': self.vac.pk,
                                             'fecha_desde': '2026-10-05', 'fecha_hasta': '2026-10-09'})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data['estado'], r.data['dias']), ('pendiente', '5.0'))
        self.assertEqual(cliente.post(f'/api/licencias/{r.data["id"]}/aprobar/').status_code, 403)
        r2 = cliente.post('/api/licencias/', {'empleado': self.beto.pk, 'tipo': self.vac.pk,
                                              'fecha_desde': '2026-10-05', 'fecha_hasta': '2026-10-05'})
        self.assertEqual(r2.status_code, 400)  # Beto no está en su alcance
        self.assertEqual(cliente.post(f'/api/licencias/{r.data["id"]}/cancelar/', {'motivo': 'Ya no'}).status_code, 200)

    def test_gestor_aprueba_y_consulta_saldo(self):
        self.devengo(12)
        r = self.cliente(self.usr_ana).post('/api/licencias/', {'empleado': self.ana.pk, 'tipo': self.vac.pk,
                                                                'fecha_desde': '2026-10-05', 'fecha_hasta': '2026-10-06'})
        a = self.cliente(self.gestor1).post(f'/api/licencias/{r.data["id"]}/aprobar/')
        self.assertEqual((a.status_code, a.data['estado']), (200, 'aprobada'))
        saldo = self.cliente(self.usr_ana).get('/api/movimientos-vacaciones/saldo/').data
        self.assertEqual((saldo['saldo'], saldo['gozado'], saldo['devengado']), (Decimal('10'), Decimal('2'), Decimal('12')))
        self.assertEqual(self.cliente(self.usr_ana).post(f'/api/licencias/{r.data["id"]}/cancelar/', {'motivo': 'x'}).status_code, 403)

    def test_separacion_de_funciones(self):
        ConfiguracionMarcacion.de(self.e1)
        ConfiguracionMarcacion.objects.filter(empresa=self.e1).update(exigir_aprobador_distinto=True)
        self.devengo(12)
        r = self.cliente(self.gestor1).post('/api/licencias/', {'empleado': self.ana.pk, 'tipo': self.vac.pk,
                                                               'fecha_desde': '2026-10-05', 'fecha_hasta': '2026-10-05'})
        self.assertEqual(self.cliente(self.gestor1).post(f'/api/licencias/{r.data["id"]}/aprobar/').status_code, 403)
        self.assertEqual(self.cliente(self.admin1).post(f'/api/licencias/{r.data["id"]}/aprobar/').status_code, 200)

    def test_movimientos_manuales_y_devengo(self):
        cliente = self.cliente(self.admin1)
        r = cliente.post('/api/movimientos-vacaciones/', {'empleado': self.ana.pk, 'fecha': '2026-10-01',
                                                          'tipo': 'goce', 'dias': '-3', 'motivo': 'x'})
        self.assertEqual(r.status_code, 400)  # el goce lo genera el sistema
        r = cliente.post('/api/movimientos-vacaciones/', {'empleado': self.ana.pk, 'fecha': '2026-10-01',
                                                          'tipo': 'ajuste', 'dias': '4', 'motivo': 'Saldo anterior'})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn(cliente.delete(f'/api/movimientos-vacaciones/{r.data["id"]}/').status_code, (403, 405))
        d = cliente.post('/api/movimientos-vacaciones/devengar/', {'hasta': '2026-10-14'})
        self.assertEqual(d.data['creados'], 2)  # Ana y Beto, primer aniversario
        self.assertEqual(self.cliente(self.usr_ana).post('/api/movimientos-vacaciones/devengar/').status_code, 403)
        saldos = {s['codigo']: s['saldo'] for s in cliente.get('/api/movimientos-vacaciones/saldos/').data}
        self.assertEqual(saldos, {'E001': Decimal('16'), 'E002': Decimal('12')})
        self.assertEqual([s['codigo'] for s in self.cliente(self.usr_ana).get('/api/movimientos-vacaciones/saldos/').data], ['E001'])

    def test_aislamiento_entre_empresas(self):
        self.solicitud(self.vac, LUNES)
        self.assertEqual(self.cliente(self.admin2).get('/api/licencias/').data['count'], 0)
        r = self.cliente(self.admin2).post('/api/movimientos-vacaciones/', {
            'empleado': self.ana.pk, 'fecha': '2026-10-01', 'tipo': 'ajuste', 'dias': '4', 'motivo': 'x'})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.cliente(self.admin2).get(f'/api/movimientos-vacaciones/saldo/?empleado={self.ana.pk}').status_code, 404)

    def test_tipos_globales_no_los_edita_la_empresa(self):
        r = self.cliente(self.admin1).patch(f'/api/tipos-licencia/{self.vac.pk}/', {'nombre': 'Otro'})
        self.assertEqual(r.status_code, 403)
        r = self.cliente(self.admin1).post('/api/tipos-licencia/', {'codigo': 'CUMPLE', 'nombre': 'Día de cumpleaños'})
        self.assertEqual(r.status_code, 201, r.data)
