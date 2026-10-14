"""Reportes (§12). Cada reporte declara su permiso, sus filtros y sus columnas,
y arma las filas respetando el alcance del usuario (core/alcance.py). La API
(`/api/reportes/<clave>/`) los devuelve en JSON o los exporta a CSV / XLSX
(core/exportar.py, protegido contra fórmulas)."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from core import alcance

CERO = Decimal('0')
REPORTES = {}


def reporte(clave, titulo, permiso, columnas, filtros=('desde', 'hasta'), descripcion=''):
    def registrar(funcion):
        REPORTES[clave] = {'clave': clave, 'titulo': titulo, 'permiso': permiso, 'columnas': columnas, 'filtros': filtros,
                           'descripcion': descripcion, 'armar': funcion}
        return funcion
    return registrar


def _lineas_cerradas(usuario, desde, hasta):
    from nomina.models import CorridaNomina, LineaNomina
    qs = LineaNomina.objects.filter(liquidacion__corrida__estado=CorridaNomina.CERRADA, liquidacion__corrida__rectificada=False)
    if desde:
        qs = qs.filter(liquidacion__corrida__periodo__fecha_hasta__gte=desde)
    if hasta:
        qs = qs.filter(liquidacion__corrida__periodo__fecha_hasta__lte=hasta)
    return alcance.filtrar(qs, usuario)


@reporte('nomina_por_concepto', 'Nómina por concepto', 'nomina.view_corridanomina',
         [('codigo', 'Código'), ('nombre', 'Concepto'), ('tipo', 'Tipo'), ('empleados', 'Empleados'), ('total', 'Total')],
         descripcion='Total de cada concepto en las liquidaciones cerradas del rango.')
def _por_concepto(usuario, f):
    filas = _lineas_cerradas(usuario, f.get('desde'), f.get('hasta')).values('codigo', 'nombre', 'tipo').annotate(
        total=Sum('importe')).order_by('tipo', 'codigo')
    empleados = defaultdict(set)
    for codigo, empleado in _lineas_cerradas(usuario, f.get('desde'), f.get('hasta')).values_list('codigo', 'liquidacion__empleado'):
        empleados[codigo].add(empleado)
    ver_costo = alcance.tiene_permiso(usuario, 'nomina.ver_costo_patronal')
    return [{**fila, 'empleados': len(empleados[fila['codigo']])} for fila in filas if ver_costo or fila['tipo'] != 'aporte_patronal']


@reporte('nomina_por_empleado', 'Nómina por empleado', 'nomina.view_corridanomina',
         [('codigo', 'Legajo'), ('empleado', 'Empleado'), ('centro_costo', 'Centro de costo'), ('bruto', 'Bruto'),
          ('descuentos', 'Descuentos'), ('aportes', 'Aportes del trabajador'), ('neto', 'Neto')],
         descripcion='Haberes, descuentos, aportes y neto por empleado (liquidaciones cerradas).')
def _por_empleado(usuario, f):
    from nomina.models import CorridaNomina, LiquidacionEmpleado
    qs = alcance.filtrar(LiquidacionEmpleado.objects.filter(corrida__estado=CorridaNomina.CERRADA, corrida__rectificada=False), usuario)
    if f.get('desde'):
        qs = qs.filter(corrida__periodo__fecha_hasta__gte=f['desde'])
    if f.get('hasta'):
        qs = qs.filter(corrida__periodo__fecha_hasta__lte=f['hasta'])
    filas = qs.values('empleado__codigo', 'empleado__primer_apellido', 'empleado__primer_nombre', 'centro_costo__nombre').annotate(
        bruto=Sum('bruto'), descuentos=Sum('descuentos'), aportes=Sum('aportes_trabajador'), neto=Sum('neto')).order_by('empleado__primer_apellido')
    return [{'codigo': r['empleado__codigo'], 'empleado': f'{r["empleado__primer_apellido"]}, {r["empleado__primer_nombre"]}',
             'centro_costo': r['centro_costo__nombre'] or '', 'bruto': r['bruto'], 'descuentos': r['descuentos'],
             'aportes': r['aportes'], 'neto': r['neto']} for r in filas]


@reporte('asistencia', 'Horas y asistencia', 'asistencia.view_diaasistencia',
         [('codigo', 'Legajo'), ('empleado', 'Empleado'), ('presentes', 'Días presentes'), ('ausentes', 'Ausencias'),
          ('licencias', 'Días de licencia'), ('trabajadas', 'Horas trabajadas'), ('tardanza', 'Minutos de tardanza'),
          ('extra_candidatas', 'Horas extra candidatas'), ('extra_autorizadas', 'Horas extra autorizadas'),
          ('nocturnas', 'Horas nocturnas'), ('faltantes', 'Marcas faltantes')],
         descripcion='Resumen de la asistencia calculada en el rango.')
def _asistencia(usuario, f):
    from asistencia.models import DiaAsistencia
    qs = alcance.filtrar(DiaAsistencia.objects.all(), usuario)
    if f.get('desde'):
        qs = qs.filter(fecha__gte=f['desde'])
    if f.get('hasta'):
        qs = qs.filter(fecha__lte=f['hasta'])
    filas = defaultdict(lambda: defaultdict(int))
    nombres = {}
    for d in qs.select_related('empleado'):
        r = filas[d.empleado_id]
        nombres[d.empleado_id] = (d.empleado.codigo, str(d.empleado))
        r['presentes'] += d.estado in ('presente', 'incompleto')
        r['ausentes'] += d.estado == 'ausente'
        r['licencias'] += d.estado == 'licencia'
        for campo, origen in (('trabajadas', 'minutos_trabajados'), ('tardanza', 'minutos_tardanza'),
                              ('extra_candidatas', 'minutos_extra_candidatos'), ('extra_autorizadas', 'minutos_extra_autorizados'),
                              ('nocturnas', 'minutos_nocturnos'), ('faltantes', 'marcas_faltantes')):
            r[campo] += getattr(d, origen)
    resultado = []
    for empleado_id, r in sorted(filas.items(), key=lambda x: nombres[x[0]][1]):
        horas = {c: (Decimal(r[c]) / 60).quantize(Decimal('0.01')) for c in ('trabajadas', 'extra_candidatas', 'extra_autorizadas', 'nocturnas')}
        resultado.append({'codigo': nombres[empleado_id][0], 'empleado': nombres[empleado_id][1], 'presentes': r['presentes'],
                          'ausentes': r['ausentes'], 'licencias': r['licencias'], 'tardanza': r['tardanza'], 'faltantes': r['faltantes'], **horas})
    return resultado


@reporte('contratos_por_vencer', 'Contratos por vencer', 'contratos.view_contratoempleado',
         [('codigo', 'Legajo'), ('empleado', 'Empleado'), ('tipo', 'Tipo de contrato'), ('inicio', 'Inicio'), ('fin', 'Vence'),
          ('dias', 'Días que faltan')], filtros=('dias',), descripcion='Contratos vigentes con fecha de fin dentro de los próximos días.')
def _contratos(usuario, f):
    from contratos.models import ContratoEmpleado
    hoy = timezone.localdate()
    dias = int(f.get('dias') or 30)
    qs = alcance.filtrar(ContratoEmpleado.objects.filter(estado=ContratoEmpleado.VIGENTE, fecha_fin__isnull=False,
                                                         fecha_fin__lte=hoy + timedelta(days=dias)), usuario).select_related('empleado')
    return [{'codigo': c.empleado.codigo, 'empleado': str(c.empleado), 'tipo': c.get_tipo_contrato_display(), 'inicio': c.fecha_inicio,
             'fin': c.fecha_fin, 'dias': (c.fecha_fin - hoy).days} for c in qs.order_by('fecha_fin')]


@reporte('cambios_salariales', 'Cambios salariales', 'contratos.view_historialsalarial',
         [('codigo', 'Legajo'), ('empleado', 'Empleado'), ('desde', 'Vigente desde'), ('salario', 'Salario'), ('esquema', 'Esquema'),
          ('motivo', 'Motivo'), ('aprobado_por', 'Aprobado por')], descripcion='Sueldos aprobados que empezaron a regir en el rango.')
def _salarios(usuario, f):
    from contratos.models import HistorialSalarial
    qs = alcance.filtrar(HistorialSalarial.objects.filter(estado=HistorialSalarial.APROBADO), usuario).select_related(
        'empleado', 'esquema_salarial', 'aprobado_por')
    if f.get('desde'):
        qs = qs.filter(vigente_desde__gte=f['desde'])
    if f.get('hasta'):
        qs = qs.filter(vigente_desde__lte=f['hasta'])
    return [{'codigo': h.empleado.codigo, 'empleado': str(h.empleado), 'desde': h.vigente_desde, 'salario': h.salario_base,
             'esquema': str(h.esquema_salarial), 'motivo': h.motivo, 'aprobado_por': str(h.aprobado_por or '')}
            for h in qs.order_by('-vigente_desde')]


@reporte('saldos_anticipos_prestamos', 'Anticipos y préstamos', 'novedades.view_prestamo',
         [('codigo', 'Legajo'), ('empleado', 'Empleado'), ('tipo', 'Tipo'), ('fecha', 'Fecha'), ('monto', 'Monto'),
          ('cuotas_pendientes', 'Cuotas pendientes'), ('saldo', 'Saldo'), ('estado', 'Estado')], filtros=(),
         descripcion='Anticipos y préstamos con saldo a recuperar.')
def _saldos(usuario, f):
    from novedades.models import Anticipo, CuotaRecuperacion, Prestamo
    resultado = []
    for modelo, tipo, monto, estado in ((Anticipo, 'Anticipo', 'monto_aprobado', Anticipo.PAGADO), (Prestamo, 'Préstamo', 'capital', Prestamo.DESEMBOLSADO)):
        for o in alcance.filtrar(modelo.objects.filter(estado=estado), usuario).select_related('empleado'):
            pendientes = o.cuotas_recuperacion.filter(estado=CuotaRecuperacion.PENDIENTE)
            resultado.append({'codigo': o.empleado.codigo, 'empleado': str(o.empleado), 'tipo': tipo, 'fecha': o.fecha,
                              'monto': getattr(o, monto), 'cuotas_pendientes': pendientes.count(),
                              'saldo': pendientes.aggregate(t=Sum('monto'))['t'] or CERO, 'estado': o.get_estado_display()})
    return sorted(resultado, key=lambda r: r['empleado'])


@reporte('vacaciones', 'Saldos de vacaciones', 'licencias.view_movimientovacaciones',
         [('codigo', 'Legajo'), ('empleado', 'Empleado'), ('ingreso', 'Ingreso'), ('devengado', 'Devengado'), ('gozado', 'Gozado'),
          ('saldo', 'Saldo')], filtros=(), descripcion='Saldo de vacaciones de cada empleado activo.')
def _vacaciones(usuario, f):
    from empleados.models import Empleado
    from licencias.models import MovimientoVacaciones
    empleados = alcance.filtrar(Empleado.objects.exclude(estado=Empleado.BAJA), usuario).order_by('primer_apellido')
    movimientos = defaultdict(list)
    for m in MovimientoVacaciones.objects.filter(empleado__in=empleados):
        movimientos[m.empleado_id].append(m)
    return [{'codigo': e.codigo, 'empleado': str(e), 'ingreso': e.fecha_ingreso,
             'devengado': sum((m.dias for m in movimientos[e.pk] if m.dias > 0), CERO),
             'gozado': -sum((m.dias for m in movimientos[e.pk] if m.tipo == 'goce'), CERO),
             'saldo': sum((m.dias for m in movimientos[e.pk]), CERO)} for e in empleados]


@reporte('aguinaldo', 'Base del aguinaldo', 'nomina.view_corridanomina',
         [('codigo', 'Legajo'), ('empleado', 'Empleado'), ('computable', 'Remuneraciones computables'), ('devengado', 'Aguinaldo devengado'),
          ('pagado', 'Aguinaldo pagado'), ('saldo', 'Saldo')], filtros=('anio',),
         descripcion='Remuneraciones del año que cuentan para el aguinaldo (nóminas cerradas) y lo devengado (según AGUINALDO_DIVISOR).')
def _aguinaldo(usuario, f):
    from datetime import date
    from legal import servicios as legal
    anio = int(f.get('anio') or timezone.localdate().year)
    lineas = _lineas_cerradas(usuario, date(anio, 1, 1), date(anio, 12, 31)).select_related('liquidacion__empleado', 'concepto')
    try:
        divisor = Decimal(legal.parametro(alcance.empresa_de(usuario), 'AGUINALDO_DIVISOR', date(anio, 12, 31), simulacion=True)[0])
    except legal.ReglaNoAprobada:
        divisor = None
    datos = defaultdict(lambda: {'computable': CERO, 'pagado': CERO})
    nombres = {}
    for l in lineas:
        e = l.liquidacion.empleado
        nombres[e.pk] = (e.codigo, str(e))
        if l.tipo == 'haber' and l.concepto.afecta_base_aguinaldo:
            datos[e.pk]['computable'] += l.importe
        if l.concepto.aplicacion == 'aguinaldo':
            datos[e.pk]['pagado'] += l.importe
    resultado = []
    for pk, d in sorted(datos.items(), key=lambda x: nombres[x[0]][1]):
        devengado = (d['computable'] / divisor).quantize(Decimal('1')) if divisor else None
        resultado.append({'codigo': nombres[pk][0], 'empleado': nombres[pk][1], 'computable': d['computable'], 'devengado': devengado,
                          'pagado': d['pagado'], 'saldo': (devengado - d['pagado']) if devengado is not None else None})
    return resultado


@reporte('legajos', 'Legajos', 'empleados.view_empleado',
         [('codigo', 'Legajo'), ('documento', 'Cédula'), ('empleado', 'Empleado'), ('ingreso', 'Ingreso'), ('sucursal', 'Sucursal'),
          ('departamento', 'Departamento'), ('puesto', 'Puesto'), ('estado', 'Estado')], filtros=('estado',),
         descripcion='Listado de empleados con sus datos principales.')
def _legajos(usuario, f):
    from empleados.models import Empleado
    qs = alcance.filtrar(Empleado.objects.all(), usuario).select_related('sucursal', 'departamento', 'puesto')
    if f.get('estado'):
        qs = qs.filter(estado=f['estado'])
    return [{'codigo': e.codigo, 'documento': e.numero_documento, 'empleado': str(e), 'ingreso': e.fecha_ingreso,
             'sucursal': str(e.sucursal or ''), 'departamento': str(e.departamento or ''), 'puesto': str(e.puesto or ''),
             'estado': e.get_estado_display()} for e in qs.order_by('primer_apellido', 'primer_nombre')]


@reporte('lotes_importacion', 'Importaciones de marcas', 'asistencia.view_loteimportacion',
         [('fecha', 'Subido'), ('archivo', 'Archivo'), ('estado', 'Estado'), ('filas', 'Filas'), ('aceptadas', 'Válidas'),
          ('rechazadas', 'Rechazadas'), ('duplicadas', 'Duplicadas'), ('usuario', 'Subido por')],
         descripcion='Lotes CSV importados y su resultado.')
def _lotes(usuario, f):
    from asistencia.models import LoteImportacion
    qs = alcance.filtrar(LoteImportacion.objects.all(), usuario).select_related('creado_por')
    if f.get('desde'):
        qs = qs.filter(creado__date__gte=f['desde'])
    if f.get('hasta'):
        qs = qs.filter(creado__date__lte=f['hasta'])
    return [{'fecha': l.creado, 'archivo': l.nombre_archivo, 'estado': l.get_estado_display(), 'filas': l.total_filas,
             'aceptadas': l.aceptadas, 'rechazadas': l.rechazadas, 'duplicadas': l.duplicadas, 'usuario': str(l.creado_por or '')}
            for l in qs.order_by('-creado')]


def disponibles(usuario):
    return [r for r in REPORTES.values() if alcance.tiene_permiso(usuario, r['permiso'])]
