"""Tablero (gráficos de gestión). Junta, para un rango de meses, la nómina
cerrada (bruto, descuentos, aportes al IPS, neto y, para quien puede verlo,
el costo del empleador), las licencias aprobadas, la asistencia calculada y
la dotación, agrupado por mes, departamento, sucursal, centro de costo o
empleado. Con `por_mes`, cada grupo trae además su serie mensual (para
comparar departamentos o empleados mes a mes).

Cada bloque exige su permiso de consulta (sin él, el bloque no viene) y
todo se recorta con core/alcance.py. Departamento, sucursal y centro de
costo son los actuales del legajo. La nómina cuenta solo las liquidaciones
cerradas que no fueron rectificadas (las rectificaciones reemplazan a la
original), en el mes de fin de su período."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum

from core import alcance

CERO = Decimal('0')
AGRUPACIONES = ('total', 'mes', 'departamento', 'sucursal', 'centro_costo', 'empleado')
NOMINA = ('bruto', 'descuentos', 'aportes_trabajador', 'neto')
COSTO = ('aportes_patronales', 'costo_empleador')
ESTADOS_LABORABLES = ('presente', 'incompleto', 'ausente', 'licencia')


def secciones(usuario):
    """Qué bloques puede ver el usuario."""
    nomina = alcance.tiene_permiso(usuario, 'nomina.view_corridanomina')
    return {
        'nomina': nomina,
        'costo': nomina and alcance.tiene_permiso(usuario, 'nomina.ver_costo_patronal'),
        'licencias': alcance.tiene_permiso(usuario, 'licencias.view_solicitudlicencia'),
        'asistencia': alcance.tiene_permiso(usuario, 'asistencia.view_diaasistencia'),
        'personal': alcance.tiene_permiso(usuario, 'empleados.view_empleado'),
    }


def mes_de(fecha):
    return f'{fecha.year:04d}-{fecha.month:02d}'


def meses_entre(desde, hasta):
    meses, actual = [], date(desde.year, desde.month, 1)
    while actual <= hasta:
        meses.append(mes_de(actual))
        actual = date(actual.year + actual.month // 12, actual.month % 12 + 1, 1)
    return meses


def fin_de_mes(mes):
    anio, numero = int(mes[:4]), int(mes[5:])
    return date(anio + numero // 12, numero % 12 + 1, 1) - timedelta(days=1)


def _por_dimension(qs, prefijo, f):
    """Aplica los filtros de departamento, sucursal, centro de costo y empleados."""
    rutas = {'departamentos': f'{prefijo}departamento', 'sucursales': f'{prefijo}sucursal',
             'centros': f'{prefijo}centro_costo', 'empleados': prefijo.rstrip('_') or 'pk'}
    for campo, ruta in rutas.items():
        if f.get(campo):
            qs = qs.filter(**{f'{ruta}__in': f[campo]})
    return qs


class _Grupos:
    """Arma la clave y la etiqueta del grupo de cada registro."""

    def __init__(self, agrupar, prefijo):
        self.agrupar, self.prefijo = agrupar, prefijo
        p = prefijo
        self.campos = {
            'total': [],
            'mes': [],
            'departamento': [f'{p}departamento', f'{p}departamento__nombre'],
            'sucursal': [f'{p}sucursal', f'{p}sucursal__nombre'],
            'centro_costo': [f'{p}centro_costo', f'{p}centro_costo__nombre'],
            'empleado': [p.rstrip('_') or 'pk', f'{p}codigo', f'{p}primer_apellido', f'{p}primer_nombre'],
        }[agrupar]

    def clave(self, fila, mes=None):
        if self.agrupar == 'total':
            return 'total', 'Total'
        if self.agrupar == 'mes':
            return mes, mes
        valores = [fila[c] for c in self.campos]
        if valores[0] is None:
            return 'sin', {'departamento': 'Sin departamento', 'sucursal': 'Sin sucursal',
                           'centro_costo': 'Sin centro de costo'}.get(self.agrupar, 'Sin dato')
        if self.agrupar == 'empleado':
            return str(valores[0]), f'{valores[2]}, {valores[3]} ({valores[1]})'
        return str(valores[0]), valores[1]


class _Acumulador:
    def __init__(self, por_mes):
        self.por_mes = por_mes
        self.filas = {}
        self.series = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: CERO)))

    def sumar(self, clave, etiqueta, mes, campo, valor):
        fila = self.filas.setdefault(clave, {'clave': clave, 'etiqueta': etiqueta})
        fila[campo] = fila.get(campo, CERO) + valor
        if self.por_mes and mes:
            self.series[clave][mes][campo] += valor

    def poner(self, clave, etiqueta, mes, campo, valor):
        fila = self.filas.setdefault(clave, {'clave': clave, 'etiqueta': etiqueta})
        fila[campo] = valor
        if self.por_mes and mes:
            self.series[clave][mes][campo] = valor


def _liquidaciones(usuario, desde, hasta, f):
    from nomina.models import CorridaNomina, LiquidacionEmpleado
    qs = alcance.filtrar(LiquidacionEmpleado.objects.filter(
        corrida__estado=CorridaNomina.CERRADA, corrida__rectificada=False, corrida__es_simulacion=False,
        corrida__periodo__fecha_hasta__gte=desde, corrida__periodo__fecha_hasta__lte=hasta), usuario)
    return _por_dimension(qs, 'empleado__', f)


def _nomina(usuario, desde, hasta, f, grupos, acumulador, ver_costo):
    campos = NOMINA + (COSTO if ver_costo else ())
    filas = _liquidaciones(usuario, desde, hasta, f).values('corrida__periodo__fecha_hasta', 'empleado', *grupos.campos).annotate(
        **{c: Sum(c) for c in campos})
    empleados = defaultdict(set)
    empleados_mes = defaultdict(lambda: defaultdict(set))
    for fila in filas:
        mes = mes_de(fila['corrida__periodo__fecha_hasta'])
        clave, etiqueta = grupos.clave(fila, mes)
        for campo in campos:
            acumulador.sumar(clave, etiqueta, mes, campo, fila[campo] or CERO)
        empleados[clave].add(fila['empleado'])
        empleados_mes[clave][mes].add(fila['empleado'])
    for clave, conjunto in empleados.items():
        acumulador.filas[clave]['empleados_liquidados'] = len(conjunto)
        if acumulador.por_mes:
            for mes, del_mes in empleados_mes[clave].items():
                acumulador.series[clave][mes]['empleados_liquidados'] = len(del_mes)


def _licencias(usuario, desde, hasta, f, grupos, acumulador):
    from licencias.models import SolicitudLicencia
    qs = _por_dimension(alcance.filtrar(SolicitudLicencia.objects.filter(
        estado=SolicitudLicencia.APROBADA, fecha_desde__gte=desde, fecha_desde__lte=hasta), usuario), 'empleado__', f)
    for fila in qs.values('fecha_desde', 'dias', 'minutos', *grupos.campos):
        mes = mes_de(fila['fecha_desde'])
        clave, etiqueta = grupos.clave(fila, mes)
        acumulador.sumar(clave, etiqueta, mes, 'licencias', Decimal(1))
        acumulador.sumar(clave, etiqueta, mes, 'dias_licencia', fila['dias'] or CERO)
        acumulador.sumar(clave, etiqueta, mes, 'horas_permiso', Decimal(fila['minutos'] or 0) / 60)


def licencias_por_tipo(usuario, desde, hasta, f):
    from licencias.models import SolicitudLicencia
    qs = _por_dimension(alcance.filtrar(SolicitudLicencia.objects.filter(
        estado=SolicitudLicencia.APROBADA, fecha_desde__gte=desde, fecha_desde__lte=hasta), usuario), 'empleado__', f)
    return [{'tipo': r['tipo__nombre'], 'categoria': r['tipo__categoria'], 'solicitudes': r['solicitudes'], 'dias': r['dias'] or CERO,
             'horas': (Decimal(r['minutos'] or 0) / 60).quantize(Decimal('0.1'))}
            for r in qs.values('tipo__nombre', 'tipo__categoria').annotate(
                solicitudes=Count('id'), dias=Sum('dias'), minutos=Sum('minutos')).order_by('-dias', 'tipo__nombre')]


def _asistencia(usuario, desde, hasta, f, grupos, acumulador):
    from asistencia.models import DiaAsistencia
    qs = _por_dimension(alcance.filtrar(DiaAsistencia.objects.filter(fecha__gte=desde, fecha__lte=hasta), usuario), 'empleado__', f)
    for fila in qs.values('fecha', 'estado', 'minutos_tardanza', 'minutos_extra_autorizados', *grupos.campos):
        mes = mes_de(fila['fecha'])
        clave, etiqueta = grupos.clave(fila, mes)
        if fila['estado'] in ESTADOS_LABORABLES:
            acumulador.sumar(clave, etiqueta, mes, 'dias_laborables', Decimal(1))
        acumulador.sumar(clave, etiqueta, mes, 'ausencias', Decimal(fila['estado'] == 'ausente'))
        acumulador.sumar(clave, etiqueta, mes, 'minutos_tardanza', Decimal(fila['minutos_tardanza']))
        acumulador.sumar(clave, etiqueta, mes, 'horas_extra', Decimal(fila['minutos_extra_autorizados']) / 60)


def _personal(usuario, desde, hasta, f, grupos, acumulador, meses):
    from empleados.models import Empleado
    qs = _por_dimension(alcance.filtrar(Empleado.objects.all(), usuario), '', f)
    corte = min(hasta, date.today())
    # Fin de cada mes (sin pasar de hoy); los meses futuros no tienen dotación.
    cortes = {mes: min(fin_de_mes(mes), corte) for mes in meses if mes <= mes_de(corte)}
    activo = lambda ingreso, egreso, dia: ingreso <= dia and (egreso is None or egreso > dia)
    for fila in qs.values('fecha_ingreso', 'fecha_egreso', *grupos.campos):
        ingreso, egreso = fila['fecha_ingreso'], fila['fecha_egreso']
        altas = desde <= ingreso <= hasta
        bajas = egreso is not None and desde <= egreso <= hasta
        if grupos.agrupar == 'mes':
            for mes, dia in cortes.items():
                if activo(ingreso, egreso, dia):
                    acumulador.sumar(mes, mes, None, 'dotacion', Decimal(1))
            if altas:
                acumulador.sumar(mes_de(ingreso), mes_de(ingreso), None, 'altas', Decimal(1))
            if bajas:
                acumulador.sumar(mes_de(egreso), mes_de(egreso), None, 'bajas', Decimal(1))
            continue
        clave, etiqueta = grupos.clave(fila)
        acumulador.sumar(clave, etiqueta, None, 'dotacion', Decimal(activo(ingreso, egreso, corte)))
        acumulador.sumar(clave, etiqueta, mes_de(ingreso) if altas else None, 'altas', Decimal(altas))
        acumulador.sumar(clave, etiqueta, mes_de(egreso) if bajas else None, 'bajas', Decimal(bajas))
        if acumulador.por_mes:
            for mes, dia in cortes.items():
                if activo(ingreso, egreso, dia):
                    acumulador.series[clave][mes]['dotacion'] += 1


def conceptos(usuario, desde, hasta, f, ver_costo):
    """Composición: total de cada concepto en el rango."""
    from nomina.models import LineaNomina
    liquidaciones = _liquidaciones(usuario, desde, hasta, f)
    qs = LineaNomina.objects.filter(liquidacion__in=liquidaciones).exclude(tipo='informativo')
    if not ver_costo:
        qs = qs.exclude(tipo='aporte_patronal')
    return [{'codigo': r['codigo'], 'nombre': r['nombre'], 'tipo': r['tipo'], 'total': r['total']}
            for r in qs.values('codigo', 'nombre', 'tipo').annotate(total=Sum('importe')).order_by('tipo', '-total')]


def resumen(usuario, hasta, f, ver_costo):
    """Tarjetas: el último mes con nómina cerrada hasta `hasta`, el mes anterior
    y el mismo mes del año anterior."""
    ultima =_liquidaciones(usuario, date(2000, 1, 1), hasta, f).order_by('-corrida__periodo__fecha_hasta').values_list(
        'corrida__periodo__fecha_hasta', flat=True).first()
    if ultima is None:
        return None
    mes = mes_de(ultima)
    anterior = mes_de(date(ultima.year, ultima.month, 1) - timedelta(days=1))
    anio_anterior = f'{ultima.year - 1:04d}-{ultima.month:02d}'
    inicio = date(ultima.year - 1, ultima.month, 1)
    grupos, acumulador = _Grupos('mes', 'empleado__'), _Acumulador(False)
    _nomina(usuario, inicio, fin_de_mes(mes), f, grupos, acumulador, ver_costo)
    return {nombre: {**acumulador.filas.get(m, {}), 'mes': m}
            for nombre, m in (('mes', mes), ('anterior', anterior), ('anio_anterior', anio_anterior))}


def armar(usuario, desde, hasta, agrupar='mes', por_mes=False, f=None):
    f = f or {}
    if agrupar not in AGRUPACIONES:
        raise ValueError('Agrupación inválida.')
    ver = secciones(usuario)
    meses = meses_entre(desde, hasta)
    por_mes = por_mes and agrupar not in ('mes',)
    acumulador = _Acumulador(por_mes)
    if agrupar == 'mes':
        for mes in meses:
            acumulador.filas[mes] = {'clave': mes, 'etiqueta': mes}
    if ver['nomina']:
        _nomina(usuario, desde, hasta, f, _Grupos(agrupar, 'empleado__'), acumulador, ver['costo'])
    if ver['licencias']:
        _licencias(usuario, desde, hasta, f, _Grupos(agrupar, 'empleado__'), acumulador)
    if ver['asistencia']:
        _asistencia(usuario, desde, hasta, f, _Grupos(agrupar, 'empleado__'), acumulador)
    if ver['personal']:
        _personal(usuario, desde, hasta, f, _Grupos(agrupar, ''), acumulador, meses)
    filas = list(acumulador.filas.values())
    if agrupar == 'mes':
        filas.sort(key=lambda r: r['clave'])
    else:
        filas.sort(key=lambda r: (r['clave'] == 'sin', -(r.get('bruto') or CERO), r['etiqueta']))
    if por_mes:
        for fila in filas:
            serie = acumulador.series.get(fila['clave'], {})
            fila['meses'] = [{'mes': m, **serie.get(m, {})} for m in meses]
    for fila in filas:
        for detalle in [fila, *fila.get('meses', [])]:
            for campo in ('horas_extra', 'horas_permiso'):
                if campo in detalle:
                    detalle[campo] = Decimal(detalle[campo]).quantize(Decimal('0.1'))
    resultado = {'secciones': ver, 'agrupar': agrupar, 'desde': desde, 'hasta': hasta, 'meses': meses, 'filas': filas}
    if ver['nomina']:
        resultado['conceptos'] = conceptos(usuario, desde, hasta, f, ver['costo'])
        resultado['resumen'] = resumen(usuario, hasta, f, ver['costo'])
    if ver['licencias']:
        resultado['licencias_por_tipo'] = licencias_por_tipo(usuario, desde, hasta, f)
    return resultado


def opciones(usuario):
    """Listas para los filtros (según el alcance del usuario)."""
    from empleados.models import CentroCosto, Departamento, Empleado
    from plataforma.models import Sucursal
    return {
        'departamentos': [{'id': d.pk, 'nombre': d.nombre} for d in alcance.filtrar(Departamento.objects.all(), usuario).order_by('nombre')],
        'sucursales': [{'id': s.pk, 'nombre': s.nombre} for s in alcance.filtrar(Sucursal.objects.all(), usuario).order_by('nombre')],
        'centros': [{'id': c.pk, 'nombre': str(c)} for c in alcance.filtrar(CentroCosto.objects.all(), usuario).order_by('codigo')],
        'empleados': [{'id': e.pk, 'nombre': f'{e.primer_apellido}, {e.primer_nombre} ({e.codigo})', 'baja': e.estado == Empleado.BAJA}
                      for e in alcance.filtrar(Empleado.objects.all(), usuario).order_by('primer_apellido', 'primer_nombre')],
    }
