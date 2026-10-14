"""Lectura de los parámetros legales vigentes y ciclo de vida de los
conjuntos (revisar, aprobar, nueva versión, retirar).

Prioridad al buscar un parámetro en una fecha: primero los conjuntos propios
de la empresa, después los globales; entre ellos, la versión más nueva. Para
liquidar de verdad solo valen los APROBADOS: si falta uno, `ReglaNoAprobada`
explica qué falta (y si hay un borrador). Para simular (`simulacion=True`)
también se usan borradores y revisados, con advertencia."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from legal.models import ConjuntoReglas, ParametroLegal, RegimenSeguridadSocial


class ReglaNoAprobada(Exception):
    """Falta una regla legal aprobada: la liquidación real queda bloqueada (§9)."""


def _conjuntos(empresa, fecha, simulacion):
    estados = [ConjuntoReglas.APROBADO] + ([ConjuntoReglas.REVISADO, ConjuntoReglas.BORRADOR] if simulacion else [])
    qs = ConjuntoReglas.objects.filter(estado__in=estados, vigente_desde__lte=fecha).filter(
        Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=fecha)).filter(
        Q(empresa__isnull=True) | Q(empresa=empresa)).prefetch_related('parametros', 'regimenes')
    orden_estado = {ConjuntoReglas.APROBADO: 0, ConjuntoReglas.REVISADO: 1, ConjuntoReglas.BORRADOR: 2}
    # Propios antes que globales; aprobados antes que borradores; la versión más nueva primero.
    return sorted(qs, key=lambda c: (c.empresa_id is None, orden_estado[c.estado], -c.vigente_desde.toordinal(), -c.version))


def _advertencia(conjunto):
    if conjunto.estado == ConjuntoReglas.APROBADO:
        return ''
    return f'"{conjunto}" está {conjunto.get_estado_display().lower()}: sirve para simular, no para liquidar.'


def _faltante(empresa, codigo, fecha, que='el parámetro legal'):
    borradores = [c for c in _conjuntos(empresa, fecha, True) if c.estado != ConjuntoReglas.APROBADO]
    detalle = f' Hay uno sin aprobar en "{borradores[0]}".' if borradores else ''
    return ReglaNoAprobada(f'Falta {que} {codigo} aprobado y vigente el {fecha:%d/%m/%Y}.{detalle}')


def parametro(empresa, codigo, fecha, simulacion=False):
    """(valor, ParametroLegal, advertencia) del parámetro vigente esa fecha."""
    for conjunto in _conjuntos(empresa, fecha, simulacion):
        for p in conjunto.parametros.all():
            if p.codigo == codigo and p.vigente_en(fecha):
                return p.valor(), p, _advertencia(conjunto)
    raise _faltante(empresa, codigo, fecha)


def regimen(empresa, codigo, fecha, simulacion=False):
    """(RegimenSeguridadSocial, advertencia) vigente esa fecha."""
    for conjunto in _conjuntos(empresa, fecha, simulacion):
        for r in conjunto.regimenes.all():
            if r.codigo == codigo:
                return r, _advertencia(conjunto)
    raise _faltante(empresa, codigo, fecha, 'el régimen de seguridad social')


def vigentes(empresa, fecha, simulacion=False):
    """Todos los parámetros vigentes esa fecha, resueltos con la prioridad.

    Devuelve {'variables': {CODIGO: valor}, 'detalle': [...], 'advertencias': [...]}.
    Los regímenes aportan además `<CODIGO>_TASA_TRABAJADOR` y `<CODIGO>_TASA_PATRONAL`
    con el guion convertido en guion bajo (ej. IPS_GENERAL_TASA_TRABAJADOR) y, el
    primero que aparezca, `IPS_TASA_TRABAJADOR` / `IPS_TASA_PATRONAL` si su código empieza con IPS."""
    variables, detalle, advertencias = {}, [], []
    for conjunto in _conjuntos(empresa, fecha, simulacion):
        aviso = _advertencia(conjunto)
        usado = False
        for p in conjunto.parametros.all():
            if p.codigo not in variables and p.vigente_en(fecha):
                variables[p.codigo] = p.valor()
                detalle.append({'codigo': p.codigo, 'nombre': p.nombre, 'valor': p.valor_legible(), 'unidad': p.unidad,
                                'referencia': p.referencia_fuente, 'conjunto': str(conjunto), 'conjunto_id': conjunto.pk,
                                'estado': conjunto.estado, 'global': conjunto.empresa_id is None})
                usado = True
        for r in conjunto.regimenes.all():
            base = r.codigo.replace('-', '_')
            for sufijo, valor in (('TASA_TRABAJADOR', r.tasa_trabajador), ('TASA_PATRONAL', r.tasa_patronal)):
                for nombre in (f'{base}_{sufijo}', f'IPS_{sufijo}' if base.startswith('IPS') else None):
                    if nombre and nombre not in variables:
                        variables[nombre] = valor
                        detalle.append({'codigo': nombre, 'nombre': f'{r.nombre} ({sufijo.replace("_", " ").lower()})',
                                        'valor': f'{valor.normalize():f} %', 'unidad': '%', 'referencia': r.referencia_fuente,
                                        'conjunto': str(conjunto), 'conjunto_id': conjunto.pk, 'estado': conjunto.estado,
                                        'global': conjunto.empresa_id is None})
                        usado = True
        if usado and aviso:
            advertencias.append(aviso)
    return {'variables': variables, 'detalle': sorted(detalle, key=lambda d: d['codigo']), 'advertencias': advertencias}


# --------------------------------------------------------------- ciclo de vida
def revisar(conjunto, usuario):
    if conjunto.estado != ConjuntoReglas.BORRADOR:
        raise ValidationError('Solo se revisa un borrador.')
    if not conjunto.parametros.exists() and not conjunto.regimenes.exists():
        raise ValidationError('El conjunto no tiene parámetros ni regímenes.')
    conjunto.estado = ConjuntoReglas.REVISADO
    conjunto.revisado_por = usuario
    conjunto.revisado_en = timezone.now()
    conjunto.save(update_fields=['estado', 'revisado_por', 'revisado_en', 'modificado'])
    return conjunto


def volver_a_borrador(conjunto, usuario):
    if conjunto.estado != ConjuntoReglas.REVISADO:
        raise ValidationError('Solo un conjunto revisado (todavía sin aprobar) vuelve a borrador.')
    conjunto.estado = ConjuntoReglas.BORRADOR
    conjunto.revisado_por = None
    conjunto.revisado_en = None
    conjunto.modificado_por = usuario
    conjunto.save(update_fields=['estado', 'revisado_por', 'revisado_en', 'modificado_por', 'modificado'])
    return conjunto


@transaction.atomic
def aprobar(conjunto, usuario):
    """Lo aprueba otra persona que la que lo revisó (cuatro ojos). Si la
    versión anterior aprobada del mismo código no tenía fin, se cierra el día
    anterior al inicio de esta; si se superpone de otra forma, no se aprueba."""
    conjunto = ConjuntoReglas.objects.select_for_update().get(pk=conjunto.pk)
    if conjunto.estado != ConjuntoReglas.REVISADO:
        raise ValidationError('Primero tiene que estar revisado.')
    if conjunto.revisado_por_id == usuario.pk:
        raise ValidationError('Lo aprueba una persona distinta de la que lo revisó.')
    cerradas = []
    otras = ConjuntoReglas.objects.select_for_update().filter(
        codigo=conjunto.codigo, empresa=conjunto.empresa, estado=ConjuntoReglas.APROBADO).exclude(pk=conjunto.pk)
    for otra in otras:
        fin_otra = otra.vigente_hasta
        if fin_otra is not None and fin_otra < conjunto.vigente_desde:
            continue
        if conjunto.vigente_hasta is not None and conjunto.vigente_hasta < otra.vigente_desde:
            continue
        if fin_otra is None and otra.vigente_desde < conjunto.vigente_desde:
            otra.vigente_hasta = conjunto.vigente_desde - timedelta(days=1)
            otra.modificado_por = usuario
            otra.save(update_fields=['vigente_hasta', 'modificado_por', 'modificado'])
            cerradas.append(otra)
            continue
        raise ValidationError(f'Se superpone con "{otra}", ya aprobado. Ajustá las fechas o retirá el anterior.')
    conjunto.estado = ConjuntoReglas.APROBADO
    conjunto.aprobado_por = usuario
    conjunto.aprobado_en = timezone.now()
    conjunto.save(update_fields=['estado', 'aprobado_por', 'aprobado_en', 'modificado'])
    return conjunto, cerradas


@transaction.atomic
def nueva_version(conjunto, usuario, vigente_desde):
    """Copia el conjunto (con sus parámetros y regímenes) como borrador de la versión siguiente."""
    if conjunto.estado == ConjuntoReglas.BORRADOR:
        raise ValidationError('Es un borrador: editalo directamente.')
    if vigente_desde < conjunto.vigente_desde:
        raise ValidationError({'vigente_desde': 'La versión nueva no puede empezar antes que la anterior.'})
    ultima = ConjuntoReglas.objects.filter(codigo=conjunto.codigo, empresa=conjunto.empresa).order_by('-version').first()
    nuevo = ConjuntoReglas.objects.create(
        empresa=conjunto.empresa, codigo=conjunto.codigo, nombre=conjunto.nombre, version=ultima.version + 1,
        version_anterior=conjunto, pais=conjunto.pais, regimen=conjunto.regimen, vigente_desde=vigente_desde,
        fuente_nombre=conjunto.fuente_nombre, fuente_numero=conjunto.fuente_numero, fuente_url=conjunto.fuente_url,
        notas=conjunto.notas, creado_por=usuario, modificado_por=usuario)
    ParametroLegal.objects.bulk_create([ParametroLegal(
        conjunto=nuevo, codigo=p.codigo, nombre=p.nombre, valor_numerico=p.valor_numerico, valor_texto=p.valor_texto,
        valor_json=p.valor_json, unidad=p.unidad, referencia_fuente=p.referencia_fuente) for p in conjunto.parametros.all()])
    RegimenSeguridadSocial.objects.bulk_create([RegimenSeguridadSocial(
        conjunto=nuevo, codigo=r.codigo, nombre=r.nombre, tasa_trabajador=r.tasa_trabajador, tasa_patronal=r.tasa_patronal,
        base=r.base, referencia_fuente=r.referencia_fuente) for r in conjunto.regimenes.all()])
    return nuevo


def retirar(conjunto, usuario, motivo):
    """Deja de valer (no se borra). PROPUESTA: la fase 10 impedirá retirar uno usado por una nómina cerrada."""
    if conjunto.estado == ConjuntoReglas.RETIRADO:
        raise ValidationError('Ya está retirado.')
    conjunto.estado = ConjuntoReglas.RETIRADO
    conjunto.motivo_retiro = motivo[:250]
    conjunto.modificado_por = usuario
    conjunto.save(update_fields=['estado', 'motivo_retiro', 'modificado_por', 'modificado'])
    return conjunto
