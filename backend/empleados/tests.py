"""Legajos: validaciones, baja lógica, reactivación, historial de
asignaciones y auditoría."""
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from core.datos_prueba import EscenarioMixin
from core.models import EventoAuditoria
from empleados.models import Departamento, Empleado, HistorialAsignacion


class EmpleadoTests(EscenarioMixin, TestCase):
    def test_codigo_y_documento_unicos_por_empresa(self):
        cliente = self.cliente(self.admin1)
        base = {'primer_nombre': 'X', 'primer_apellido': 'Y', 'fecha_ingreso': '2026-01-05'}
        r = cliente.post('/api/empleados/', {**base, 'codigo': 'E001', 'numero_documento': '777'})
        self.assertEqual(r.status_code, 400)
        r = cliente.post('/api/empleados/', {**base, 'codigo': 'E777', 'numero_documento': '1000001'})
        self.assertEqual(r.status_code, 400)
        # El mismo código en otra empresa sí se puede (E001 existe en las dos).
        self.assertTrue(Empleado.objects.filter(empresa=self.e2, codigo='E001').exists())

    def test_fecha_de_ingreso_posterior_al_nacimiento(self):
        r = self.cliente(self.admin1).post('/api/empleados/', {
            'codigo': 'E300', 'numero_documento': '300', 'primer_nombre': 'X', 'primer_apellido': 'Y',
            'fecha_ingreso': '2000-01-01', 'fecha_nacimiento': '2001-01-01',
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn('fecha_ingreso', r.data)

    def test_el_alta_abre_el_historial_de_asignaciones(self):
        historial = HistorialAsignacion.objects.filter(empleado=self.ana)
        self.assertEqual(historial.count(), 1)
        self.assertEqual(historial.first().vigente_desde, self.ana.fecha_ingreso)
        self.assertEqual(historial.first().sucursal, self.centro)

    def test_cambio_de_asignacion_cierra_la_vigencia_anterior(self):
        r = self.cliente(self.admin1).patch(f'/api/empleados/{self.ana.pk}/', {'sucursal': self.norte.pk})
        self.assertEqual(r.status_code, 200, r.data)
        hoy = timezone.localdate()
        filas = list(HistorialAsignacion.objects.filter(empleado=self.ana).order_by('vigente_desde'))
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[0].vigente_hasta, hoy - timedelta(days=1))
        self.assertEqual(filas[1].sucursal, self.norte)
        self.assertIsNone(filas[1].vigente_hasta)
        r = self.cliente(self.admin1).get(f'/api/empleados/{self.ana.pk}/historial/')
        self.assertEqual(len(r.data), 2)

    def test_cambiar_otro_dato_no_toca_el_historial(self):
        self.cliente(self.admin1).patch(f'/api/empleados/{self.ana.pk}/', {'telefono': '0981 000000'})
        self.assertEqual(HistorialAsignacion.objects.filter(empleado=self.ana).count(), 1)

    def test_baja_logica_y_reactivacion_auditadas(self):
        cliente = self.cliente(self.admin1)
        r = cliente.post(f'/api/empleados/{self.beto.pk}/dar_baja/', {'fecha_egreso': '2026-06-30', 'motivo': 'Renuncia'})
        self.assertEqual(r.status_code, 200, r.data)
        self.beto.refresh_from_db()
        self.assertEqual(self.beto.estado, Empleado.BAJA)
        self.assertEqual(self.beto.fecha_egreso, date(2026, 6, 30))
        evento = EventoAuditoria.objects.get(accion=EventoAuditoria.BAJA, objeto_id=str(self.beto.pk))
        self.assertEqual(evento.datos_anteriores['estado'], 'activo')
        self.assertEqual(evento.datos_nuevos['estado'], 'baja')
        # Una baja no se repite.
        r = cliente.post(f'/api/empleados/{self.beto.pk}/dar_baja/', {'fecha_egreso': '2026-07-01', 'motivo': 'x'})
        self.assertEqual(r.status_code, 400)
        # El legajo sigue existiendo y se puede reactivar con motivo.
        self.assertEqual(cliente.post(f'/api/empleados/{self.beto.pk}/reactivar/', {}).status_code, 400)
        r = cliente.post(f'/api/empleados/{self.beto.pk}/reactivar/', {'motivo': 'Reingreso'})
        self.assertEqual(r.status_code, 200, r.data)
        self.beto.refresh_from_db()
        self.assertEqual(self.beto.estado, Empleado.ACTIVO)

    def test_baja_anterior_al_ingreso_se_rechaza(self):
        r = self.cliente(self.admin1).post(f'/api/empleados/{self.beto.pk}/dar_baja/',
                                           {'fecha_egreso': '2020-01-01', 'motivo': 'x'})
        self.assertEqual(r.status_code, 400)

    def test_el_estado_no_se_cambia_editando(self):
        self.cliente(self.admin1).patch(f'/api/empleados/{self.beto.pk}/', {'estado': 'baja'})
        self.beto.refresh_from_db()
        self.assertEqual(self.beto.estado, Empleado.ACTIVO)

    def test_las_modificaciones_quedan_auditadas_con_valores_previos(self):
        self.cliente(self.admin1).patch(f'/api/empleados/{self.ana.pk}/', {'telefono': '0981 123456'})
        evento = EventoAuditoria.objects.get(accion=EventoAuditoria.MODIFICACION, objeto_id=str(self.ana.pk))
        self.assertEqual(evento.datos_anteriores, {'telefono': ''})
        self.assertEqual(evento.datos_nuevos, {'telefono': '0981 123456'})
        self.assertEqual(evento.empresa, self.e1)


class DepartamentoTests(EscenarioMixin, TestCase):
    def test_sin_ciclos(self):
        hijo = Departamento.objects.create(empresa=self.e1, codigo='HIJ', nombre='Hijo', departamento_padre=self.ventas)
        r = self.cliente(self.admin1).patch(f'/api/departamentos/{self.ventas.pk}/', {'departamento_padre': hijo.pk})
        self.assertEqual(r.status_code, 400)

    def test_departamento_con_empleados_no_se_borra(self):
        r = self.cliente(self.plataforma).delete(f'/api/departamentos/{self.ventas.pk}/')
        self.assertEqual(r.status_code, 409)
