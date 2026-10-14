"""Contratos, historial salarial y esquemas salariales."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from contratos.models import ContratoEmpleado, EsquemaSalarial, HistorialSalarial, sueldo_vigente
from core.datos_prueba import EscenarioMixin
from core.models import EventoAuditoria


class ContratoMixin(EscenarioMixin):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.mensual = EsquemaSalarial.objects.get(empresa=None, codigo='MENSUAL')

    def contrato(self, empleado=None, **extra):
        datos = {'empleado': (empleado or self.ana).pk, 'tipo_contrato': 'indefinido', 'fecha_inicio': '2025-01-02',
                 'esquema_salarial': self.mensual.pk, 'salario': '3500000'}
        datos.update(extra)
        return self.cliente(self.admin1).post('/api/contratos/', datos)

    def contrato_vigente(self, empleado=None, **extra):
        r = self.contrato(empleado, **extra)
        self.assertEqual(r.status_code, 201, r.data)
        r = self.cliente(self.admin1).post(f'/api/contratos/{r.data["id"]}/activar/')
        self.assertEqual(r.status_code, 200, r.data)
        return ContratoEmpleado.objects.get(pk=r.data['id'])


class ContratoTests(ContratoMixin, TestCase):
    def test_activar_abre_el_historial_salarial(self):
        contrato = self.contrato_vigente()
        self.assertEqual(contrato.estado, ContratoEmpleado.VIGENTE)
        sueldo = HistorialSalarial.objects.get(contrato=contrato)
        self.assertEqual(sueldo.estado, HistorialSalarial.APROBADO)
        self.assertEqual(sueldo.salario_base, Decimal('3500000'))
        self.assertEqual(sueldo_vigente(self.ana, date(2026, 1, 1)), sueldo)
        self.assertTrue(EventoAuditoria.objects.filter(descripcion='Contrato activado (vigente).').exists())

    def test_un_contrato_vigente_no_se_edita(self):
        contrato = self.contrato_vigente()
        r = self.cliente(self.admin1).patch(f'/api/contratos/{contrato.pk}/', {'salario': '1'})
        self.assertEqual(r.status_code, 400)

    def test_no_se_activan_dos_contratos_solapados(self):
        self.contrato_vigente()
        r = self.contrato(fecha_inicio='2025-06-01')
        r = self.cliente(self.admin1).post(f'/api/contratos/{r.data["id"]}/activar/')
        self.assertEqual(r.status_code, 400)
        self.assertIn('superpone', str(r.data))

    def test_validaciones_de_fechas(self):
        self.assertEqual(self.contrato(tipo_contrato='plazo_fijo').status_code, 400)  # sin fecha de fin
        self.assertEqual(self.contrato(fecha_inicio='2024-01-01').status_code, 400)  # antes del ingreso
        self.assertEqual(self.contrato(fecha_fin='2024-12-31').status_code, 400)  # fin antes del inicio

    def test_finalizar_cierra_el_sueldo_y_anula_los_pendientes(self):
        contrato = self.contrato_vigente()
        cliente = self.cliente(self.admin1)
        r = cliente.post('/api/historial-salarial/', {'empleado': self.ana.pk, 'contrato': contrato.pk,
                                                      'vigente_desde': '2026-08-01', 'esquema_salarial': self.mensual.pk,
                                                      'salario_base': '4000000', 'motivo': 'Aumento'})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(cliente.post(f'/api/contratos/{contrato.pk}/finalizar/', {'fecha_fin': '2026-06-30'}).status_code, 400)
        r = cliente.post(f'/api/contratos/{contrato.pk}/finalizar/', {'fecha_fin': '2026-06-30', 'motivo': 'Renuncia'})
        self.assertEqual(r.status_code, 200, r.data)
        inicial = HistorialSalarial.objects.get(contrato=contrato, motivo='Salario inicial del contrato')
        self.assertEqual(inicial.vigente_hasta, date(2026, 6, 30))
        self.assertEqual(HistorialSalarial.objects.get(motivo='Aumento').estado, HistorialSalarial.ANULADO)

    def test_anular_solo_un_borrador(self):
        r = self.contrato()
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.post(f'/api/contratos/{r.data["id"]}/anular/', {'motivo': 'Error de carga'}).status_code, 200)
        contrato = self.contrato_vigente(self.beto)
        self.assertEqual(cliente.post(f'/api/contratos/{contrato.pk}/anular/', {'motivo': 'x'}).status_code, 400)

    def test_contratos_no_se_borran(self):
        r = self.contrato()
        self.assertIn(self.cliente(self.plataforma).delete(f'/api/contratos/{r.data["id"]}/').status_code, (403, 405))


class ContratoPermisosTests(ContratoMixin, TestCase):
    def test_gestor_consulta_pero_no_carga_ni_activa(self):
        contrato = self.contrato_vigente()
        cliente = self.cliente(self.gestor1)
        self.assertEqual(cliente.get('/api/contratos/').status_code, 200)
        r = cliente.post('/api/contratos/', {'empleado': self.beto.pk, 'fecha_inicio': '2025-02-01',
                                             'esquema_salarial': self.mensual.pk, 'salario': '1'})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(cliente.post(f'/api/contratos/{contrato.pk}/finalizar/',
                                      {'fecha_fin': '2026-01-01', 'motivo': 'x'}).status_code, 403)

    def test_empleado_ve_sus_contratos_y_solo_sueldos_aprobados(self):
        contrato = self.contrato_vigente()
        self.contrato_vigente(self.beto)
        self.cliente(self.admin1).post('/api/historial-salarial/', {
            'empleado': self.ana.pk, 'contrato': contrato.pk, 'vigente_desde': '2026-08-01',
            'esquema_salarial': self.mensual.pk, 'salario_base': '4000000', 'motivo': 'Aumento propuesto'})
        cliente = self.cliente(self.usr_ana)
        contratos = cliente.get('/api/contratos/').data
        self.assertEqual({c['empleado'] for c in contratos['results']}, {self.ana.pk})
        sueldos = cliente.get('/api/historial-salarial/').data['results']
        self.assertEqual([s['estado'] for s in sueldos], ['aprobado'])

    def test_otra_empresa_no_ve_los_contratos(self):
        contrato = self.contrato_vigente()
        self.assertEqual(self.cliente(self.admin2).get(f'/api/contratos/{contrato.pk}/').status_code, 404)

    def test_no_se_usa_el_empleado_de_otra_empresa(self):
        self.assertEqual(self.contrato(self.ceci_e2).status_code, 400)


class HistorialSalarialTests(ContratoMixin, TestCase):
    def cambio(self, contrato, desde, monto='4000000', usuario=None):
        return self.cliente(usuario or self.admin1).post('/api/historial-salarial/', {
            'empleado': self.ana.pk, 'contrato': contrato.pk, 'vigente_desde': desde,
            'esquema_salarial': self.mensual.pk, 'salario_base': monto, 'motivo': 'Ajuste'})

    def test_aprobar_cierra_la_vigencia_anterior(self):
        contrato = self.contrato_vigente()
        r = self.cambio(contrato, '2026-07-01')
        self.assertEqual(r.data['estado'], 'pendiente')
        r = self.cliente(self.admin1).post(f'/api/historial-salarial/{r.data["id"]}/aprobar/')
        self.assertEqual(r.status_code, 200, r.data)
        inicial = HistorialSalarial.objects.get(contrato=contrato, motivo='Salario inicial del contrato')
        self.assertEqual(inicial.vigente_hasta, date(2026, 6, 30))
        self.assertEqual(sueldo_vigente(self.ana, date(2026, 6, 30)).salario_base, Decimal('3500000'))
        self.assertEqual(sueldo_vigente(self.ana, date(2026, 7, 1)).salario_base, Decimal('4000000'))

    def test_no_se_aprueban_vigencias_solapadas(self):
        contrato = self.contrato_vigente()
        r = self.cambio(contrato, '2025-01-02')  # el mismo día que el sueldo inicial
        r = self.cliente(self.admin1).post(f'/api/historial-salarial/{r.data["id"]}/aprobar/')
        self.assertEqual(r.status_code, 400)

    def test_fuera_del_contrato_se_rechaza(self):
        contrato = self.contrato_vigente()
        self.assertEqual(self.cambio(contrato, '2024-06-01').status_code, 400)

    def test_gestor_no_aprueba(self):
        contrato = self.contrato_vigente()
        r = self.cambio(contrato, '2026-07-01')
        self.assertEqual(self.cliente(self.gestor1).post(f'/api/historial-salarial/{r.data["id"]}/aprobar/').status_code, 403)

    def test_rechazar_con_motivo_y_un_aprobado_no_se_toca(self):
        contrato = self.contrato_vigente()
        r = self.cambio(contrato, '2026-07-01')
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.post(f'/api/historial-salarial/{r.data["id"]}/rechazar/').status_code, 400)
        self.assertEqual(cliente.post(f'/api/historial-salarial/{r.data["id"]}/rechazar/', {'motivo': 'No corresponde'}).status_code, 200)
        inicial = HistorialSalarial.objects.get(contrato=contrato, motivo='Salario inicial del contrato')
        self.assertEqual(cliente.patch(f'/api/historial-salarial/{inicial.pk}/', {'salario_base': '1'}).status_code, 400)
        self.assertEqual(cliente.post(f'/api/historial-salarial/{inicial.pk}/rechazar/', {'motivo': 'x'}).status_code, 400)


class EsquemaSalarialTests(ContratoMixin, TestCase):
    def test_globales_y_propios(self):
        propio = EsquemaSalarial.objects.create(empresa=self.e1, codigo='PROPIO', nombre='Propio', base_calculo='mes')
        ajeno = EsquemaSalarial.objects.create(empresa=self.e2, codigo='AJENO', nombre='Ajeno', base_calculo='mes')
        ids = self.ids(self.cliente(self.admin1).get('/api/esquemas-salariales/', {'por_pagina': 100}))
        self.assertIn(self.mensual.pk, ids)
        self.assertIn(propio.pk, ids)
        self.assertNotIn(ajeno.pk, ids)

    def test_la_empresa_no_modifica_un_global_pero_crea_los_suyos(self):
        cliente = self.cliente(self.admin1)
        self.assertEqual(cliente.patch(f'/api/esquemas-salariales/{self.mensual.pk}/', {'nombre': 'X'}).status_code, 403)
        r = cliente.post('/api/esquemas-salariales/', {'codigo': 'MIO', 'nombre': 'Mío', 'base_calculo': 'hora'})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['empresa'], self.e1.pk)

    def test_no_se_usa_el_esquema_de_otra_empresa(self):
        ajeno = EsquemaSalarial.objects.create(empresa=self.e2, codigo='AJENO', nombre='Ajeno', base_calculo='mes')
        self.assertEqual(self.contrato(esquema_salarial=ajeno.pk).status_code, 400)
