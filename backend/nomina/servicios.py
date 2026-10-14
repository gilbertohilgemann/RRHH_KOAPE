"""Operaciones de los conceptos y sus reglas: probar una fórmula con valores
de ejemplo, aprobar y retirar reglas, aprobar y finalizar conceptos fijos."""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils import timezone

from legal import servicios as legal
from legal.models import ConjuntoReglas
from nomina import expresiones, variables
from nomina.models import ReglaConcepto


def _separacion(objeto, usuario):
    """Si la empresa exige separar funciones, no aprueba quien lo cargó o lo cambió último."""
    from asistencia.models import ConfiguracionMarcacion
    empresa = objeto.empresa
    if empresa is not None and ConfiguracionMarcacion.de(empresa).exigir_aprobador_distinto \
            and usuario.pk in (objeto.creado_por_id, objeto.modificado_por_id):
        raise ValidationError('La empresa exige que lo apruebe otra persona (no quien lo cargó o modificó).')


def variables_de_prueba(regla, empresa, fecha, propias=None):
    """Parámetros legales (también borradores, es una simulación) + ejemplos + los valores que mande el usuario."""
    advertencias = []
    if regla.conjunto_legal_id:
        conjunto = regla.conjunto_legal
        valores = {p.codigo: p.valor() for p in conjunto.parametros.all() if p.vigente_en(fecha)}
        for r in conjunto.regimenes.all():
            base = r.codigo.replace('-', '_')
            valores.update({f'{base}_TASA_TRABAJADOR': r.tasa_trabajador, f'{base}_TASA_PATRONAL': r.tasa_patronal})
            if base.startswith('IPS'):
                valores.setdefault('IPS_TASA_TRABAJADOR', r.tasa_trabajador)
                valores.setdefault('IPS_TASA_PATRONAL', r.tasa_patronal)
        if conjunto.estado != ConjuntoReglas.APROBADO:
            advertencias.append(f'"{conjunto}" está {conjunto.get_estado_display().lower()}: sirve para probar, no para liquidar.')
    else:
        resueltos = legal.vigentes(empresa, fecha, simulacion=True)
        valores, advertencias = resueltos['variables'], resueltos['advertencias']
    datos = {**variables.ejemplos(), **valores}
    for codigo, valor in (propias or {}).items():
        try:
            datos[str(codigo).upper()] = Decimal(str(valor))
        except (InvalidOperation, ValueError):
            raise ValidationError({'variables': f'{codigo}: "{valor}" no es un número.'})
    return datos, advertencias


def probar(regla, empresa, fecha, propias=None):
    """Resultado de la regla con valores de ejemplo, explicado paso a paso."""
    datos, advertencias = variables_de_prueba(regla, empresa, fecha, propias)
    usadas = sorted(regla.variables())
    faltan = [v for v in usadas if v not in datos]
    lineas = [f'{v} = {datos[v]:,}'.replace(',', '.') if isinstance(datos[v], Decimal) else f'{v} = {datos[v]}'
              for v in usadas if v in datos]
    if faltan:
        return {'resultado': None, 'faltan': faltan, 'advertencias': advertencias,
                'texto': f'Faltan valores para: {", ".join(faltan)}. No son parámetros legales vigentes ni variables conocidas de la liquidación.'}
    try:
        importe = regla.calcular(datos)
    except expresiones.ErrorFormula as e:
        return {'resultado': None, 'faltan': [], 'advertencias': advertencias, 'texto': f'Error: {e}'}
    if importe is None:
        resultado = 'La condición no se cumple con estos valores: el concepto no se aplica.'
    else:
        resultado = f'Resultado: {importe:,.0f}'.replace(',', '.') + f' ({regla.get_redondeo_display().lower()}).'
    texto = '\n'.join(['Valores usados (ejemplos y parámetros legales):', *lineas, '', resultado, *advertencias])
    return {'resultado': importe, 'faltan': [], 'advertencias': advertencias, 'texto': texto}


def aprobar_regla(regla, usuario):
    if regla.estado != ReglaConcepto.BORRADOR:
        raise ValidationError('Solo se aprueba una regla en borrador.')
    _separacion(regla, usuario)
    regla.full_clean()
    regla.estado = ReglaConcepto.APROBADA
    regla.aprobado_por = usuario
    regla.aprobado_en = timezone.now()
    regla.save(update_fields=['estado', 'aprobado_por', 'aprobado_en', 'modificado'])
    return regla


def retirar_regla(regla, usuario):
    if regla.estado == ReglaConcepto.RETIRADA:
        raise ValidationError('Ya está retirada.')
    regla.estado = ReglaConcepto.RETIRADA
    regla.modificado_por = usuario
    regla.save(update_fields=['estado', 'modificado_por', 'modificado'])
    return regla


def aprobar_recurrente(recurrente, usuario):
    if recurrente.aprobado:
        raise ValidationError('Ya está aprobado.')
    if not recurrente.activo:
        raise ValidationError('Está finalizado.')
    _separacion(recurrente, usuario)
    recurrente.aprobado_por = usuario
    recurrente.aprobado_en = timezone.now()
    recurrente.save(update_fields=['aprobado_por', 'aprobado_en', 'modificado'])
    return recurrente


def finalizar_recurrente(recurrente, usuario, fecha, motivo):
    """Le pone fin (no se borra): deja de aplicarse después de esa fecha."""
    if not recurrente.activo:
        raise ValidationError('Ya está finalizado.')
    if fecha < recurrente.vigente_desde:
        raise ValidationError({'vigente_hasta': 'No puede terminar antes de empezar.'})
    recurrente.vigente_hasta = fecha
    recurrente.activo = False
    recurrente.motivo_fin = motivo[:250]
    recurrente.modificado_por = usuario
    recurrente.save(update_fields=['vigente_hasta', 'activo', 'motivo_fin', 'modificado_por', 'modificado'])
    return recurrente


def recurrente_al_crear(recurrente, usuario):
    """Si el concepto no exige aprobación, queda aprobado al cargarse."""
    if not recurrente.concepto.requiere_aprobacion:
        recurrente.aprobado_por = usuario
        recurrente.aprobado_en = timezone.now()
        recurrente.save(update_fields=['aprobado_por', 'aprobado_en'])
    return recurrente
