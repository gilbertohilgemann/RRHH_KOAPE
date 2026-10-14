"""Armado y validación de las planillas oficiales desde las nóminas cerradas
(las rectificadas no cuentan: cuenta su rectificación)."""
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from cumplimiento.models import LineaPresentacion, PresentacionOficial

CERO = Decimal('0')
MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

COLUMNAS = {
    PresentacionOficial.IPS_MENSUAL: [
        ('numero_asegurado', 'N.º de asegurado IPS'), ('documento', 'Cédula'), ('apellidos', 'Apellidos'), ('nombres', 'Nombres'),
        ('fecha_ingreso', 'Ingreso'), ('fecha_egreso', 'Egreso'), ('dias', 'Días'), ('salario_imponible', 'Salario imponible'),
        ('aporte_trabajador', 'Aporte del trabajador'), ('aporte_patronal', 'Aporte del empleador'), ('total_aporte', 'Total aporte'),
    ],
    PresentacionOficial.MTESS_SUELDOS: [
        ('documento', 'Cédula'), ('apellidos', 'Apellidos'), ('nombres', 'Nombres'), ('sexo', 'Sexo'), ('cargo', 'Cargo'),
        *[(f'mes_{i}', m.capitalize()) for i, m in enumerate(MESES, start=1)],
        ('aguinaldo', 'Aguinaldo'), ('beneficios', 'Otros beneficios del egreso'), ('total', 'Total'),
    ],
    PresentacionOficial.MTESS_EMPLEADOS: [
        ('documento', 'Cédula'), ('apellidos', 'Apellidos'), ('nombres', 'Nombres'), ('sexo', 'Sexo'), ('estado_civil', 'Estado civil'),
        ('fecha_nacimiento', 'Nacimiento'), ('nacionalidad', 'Nacionalidad'), ('domicilio', 'Domicilio'), ('cargo', 'Cargo'),
        ('fecha_ingreso', 'Ingreso'), ('fecha_egreso', 'Egreso'), ('motivo_egreso', 'Motivo del egreso'),
    ],
}


def _nombres(e):
    return {'documento': e.numero_documento, 'apellidos': ' '.join(filter(None, [e.primer_apellido, e.segundo_apellido])),
            'nombres': ' '.join(filter(None, [e.primer_nombre, e.segundo_nombre]))}


def _lineas_cerradas(empresa, desde, hasta, tipos):
    from nomina.models import CorridaNomina, LineaNomina
    return LineaNomina.objects.filter(
        empresa=empresa, liquidacion__corrida__estado=CorridaNomina.CERRADA, liquidacion__corrida__rectificada=False,
        liquidacion__corrida__tipo__in=tipos, liquidacion__corrida__periodo__fecha_hasta__gte=desde,
        liquidacion__corrida__periodo__fecha_hasta__lte=hasta).select_related('concepto', 'liquidacion__empleado__puesto',
                                                                              'liquidacion__corrida__periodo')


def _ips(p):
    from legal import servicios as legal
    from nomina.models import ConceptoNomina, LiquidacionEmpleado
    from legal.servicios import ReglaNoAprobada
    try:
        minimo = Decimal(legal.parametro(p.empresa, 'SALARIO_MINIMO_MENSUAL', p.periodo_hasta, simulacion=True)[0])
    except ReglaNoAprobada:
        minimo = None
    por_empleado = defaultdict(lambda: {'imponible': CERO, 'trabajador': CERO, 'patronal': CERO})
    for l in _lineas_cerradas(p.empresa, p.periodo_desde, p.periodo_hasta, ('regular', 'rectificacion', 'liquidacion_final')):
        datos = por_empleado[l.liquidacion.empleado]
        if l.tipo == ConceptoNomina.HABER and l.concepto.afecta_base_ips:
            datos['imponible'] += l.importe
        elif l.tipo == ConceptoNomina.APORTE_TRABAJADOR:
            datos['trabajador'] += l.importe
        elif l.tipo == ConceptoNomina.APORTE_PATRONAL:
            datos['patronal'] += l.importe
    for empleado, d in por_empleado.items():
        dias = sum(LiquidacionEmpleado.objects.filter(
            empleado=empleado, corrida__estado='cerrada', corrida__rectificada=False, corrida__tipo__in=('regular', 'rectificacion', 'liquidacion_final'),
            corrida__periodo__fecha_hasta__gte=p.periodo_desde, corrida__periodo__fecha_hasta__lte=p.periodo_hasta).values_list('dias_pagados', flat=True))
        errores, avisos = [], []
        if not empleado.numero_asegurado_ips:
            errores.append('Falta el número de asegurado IPS en el legajo.')
        if not empleado.numero_documento:
            errores.append('Falta la cédula.')
        if d['imponible'] and not d['trabajador']:
            avisos.append('Tiene salario imponible pero no aporte del trabajador.')
        if minimo is not None and dias and d['imponible'] < minimo * Decimal(dias) / 30:
            avisos.append(f'El salario imponible ({d["imponible"]:,.0f}) es menor que el mínimo proporcional a {dias} días.'.replace(',', '.'))
        yield empleado, {
            'numero_asegurado': empleado.numero_asegurado_ips, **_nombres(empleado), 'fecha_ingreso': empleado.fecha_ingreso.isoformat(),
            'fecha_egreso': empleado.fecha_egreso.isoformat() if empleado.fecha_egreso else '', 'dias': str(dias),
            'salario_imponible': str(d['imponible']), 'aporte_trabajador': str(d['trabajador']), 'aporte_patronal': str(d['patronal']),
            'total_aporte': str(d['trabajador'] + d['patronal']),
        }, errores, avisos


def _mtess_sueldos(p):
    from nomina.models import ConceptoNomina
    por_empleado = defaultdict(lambda: defaultdict(lambda: CERO))
    for l in _lineas_cerradas(p.empresa, p.periodo_desde, p.periodo_hasta, ('regular', 'rectificacion', 'aguinaldo', 'liquidacion_final')):
        if l.tipo != ConceptoNomina.HABER:
            continue
        d = por_empleado[l.liquidacion.empleado]
        if l.concepto.aplicacion == 'aguinaldo':
            d['aguinaldo'] += l.importe
        elif l.concepto.aplicacion == 'liquidacion_final':
            d['beneficios'] += l.importe
        else:
            d[f'mes_{l.liquidacion.corrida.periodo.fecha_hasta.month}'] += l.importe
    for empleado, d in por_empleado.items():
        errores = [texto for falta, texto in ((not empleado.sexo, 'Falta el sexo.'), (not empleado.fecha_nacimiento, 'Falta la fecha de nacimiento.'),
                                               (not empleado.numero_documento, 'Falta la cédula.')) if falta]
        avisos = [] if empleado.puesto_id else ['Sin puesto (cargo) en el legajo.']
        fila = {**_nombres(empleado), 'sexo': empleado.sexo, 'cargo': str(empleado.puesto) if empleado.puesto_id else ''}
        fila.update({f'mes_{i}': str(d[f'mes_{i}']) for i in range(1, 13)})
        fila.update({'aguinaldo': str(d['aguinaldo']), 'beneficios': str(d['beneficios']), 'total': str(sum(d.values(), CERO))})
        yield empleado, fila, errores, avisos


def _mtess_empleados(p):
    from empleados.models import Empleado
    empleados = Empleado.objects.filter(empresa=p.empresa, fecha_ingreso__lte=p.periodo_hasta).filter(
        Q(fecha_egreso__isnull=True) | Q(fecha_egreso__gte=p.periodo_desde)).select_related('puesto')
    for e in empleados:
        errores = [texto for falta, texto in ((not e.numero_documento, 'Falta la cédula.'), (not e.sexo, 'Falta el sexo.'),
                                               (not e.fecha_nacimiento, 'Falta la fecha de nacimiento.'),
                                               (not e.nacionalidad, 'Falta la nacionalidad.')) if falta]
        avisos = [texto for falta, texto in ((not e.direccion, 'Sin domicilio.'), (not e.puesto_id, 'Sin puesto (cargo).'),
                                              (not e.estado_civil, 'Sin estado civil.')) if falta]
        yield e, {**_nombres(e), 'sexo': e.sexo, 'estado_civil': e.get_estado_civil_display() if e.estado_civil else '',
                  'fecha_nacimiento': e.fecha_nacimiento.isoformat() if e.fecha_nacimiento else '', 'nacionalidad': e.nacionalidad,
                  'domicilio': e.direccion, 'cargo': str(e.puesto) if e.puesto_id else '', 'fecha_ingreso': e.fecha_ingreso.isoformat(),
                  'fecha_egreso': e.fecha_egreso.isoformat() if e.fecha_egreso else '', 'motivo_egreso': e.motivo_egreso}, errores, avisos


ARMADORES = {PresentacionOficial.IPS_MENSUAL: _ips, PresentacionOficial.MTESS_SUELDOS: _mtess_sueldos,
             PresentacionOficial.MTESS_EMPLEADOS: _mtess_empleados}


@transaction.atomic
def preparar(presentacion):
    """(Re)arma las líneas de la planilla con los datos actuales y las valida."""
    presentacion.lineas.all().delete()
    lineas, totales = [], defaultdict(lambda: CERO)
    for empleado, datos, errores, avisos in ARMADORES[presentacion.tipo](presentacion):
        lineas.append(LineaPresentacion(presentacion=presentacion, empleado=empleado, datos=datos, valida=not errores,
                                        errores=errores, advertencias=avisos))
        for campo in ('salario_imponible', 'aporte_trabajador', 'aporte_patronal', 'total_aporte', 'total', 'aguinaldo'):
            if campo in datos:
                totales[campo] += Decimal(datos[campo])
    LineaPresentacion.objects.bulk_create(lineas)
    presentacion.autoridad = PresentacionOficial.AUTORIDAD[presentacion.tipo]
    presentacion.cantidad_lineas = len(lineas)
    presentacion.lineas_con_errores = sum(1 for l in lineas if not l.valida)
    presentacion.resumen = {k: str(v) for k, v in totales.items()}
    presentacion.preparado_en = timezone.now()
    presentacion.save(update_fields=['autoridad', 'cantidad_lineas', 'lineas_con_errores', 'resumen', 'preparado_en', 'modificado'])
    return presentacion


def filas_para_exportar(presentacion):
    columnas = COLUMNAS[presentacion.tipo]
    encabezado = [etiqueta for _, etiqueta in columnas] + ['Errores']
    numericos = {'dias', 'salario_imponible', 'aporte_trabajador', 'aporte_patronal', 'total_aporte', 'aguinaldo', 'beneficios', 'total',
                 *[f'mes_{i}' for i in range(1, 13)]}
    filas = []
    for linea in presentacion.lineas.all():
        filas.append([Decimal(linea.datos.get(c) or 0) if c in numericos else linea.datos.get(c, '') for c, _ in columnas]
                     + ['; '.join(linea.errores)])
    return encabezado, filas
