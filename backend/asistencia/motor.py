"""Motor de asistencia (fase 6; §7 de la especificación).

Para cada empleado y día calcula, con el horario, el feriado y las marcas
VIGENTES ESE DÍA (no los actuales), los minutos trabajados, de descanso, de
tardanza, de salida anticipada, ordinarios, extra candidatos y autorizados,
nocturnos y en feriado, y el estado del día. Cada número queda explicado en
`DiaAsistencia.explicacion`. Nunca inventa marcas: lo que falta se informa
como incidencia.

Reglas (todas visibles en la explicación de cada día):
- Día de trabajo de una marca: el día cuyo horario la "cubre" (desde 4 h antes
  del primer tramo hasta 8 h después del último); si dos días la cubren (turnos
  de noche), el del borde de tramo más cercano. Sin horario, el día calendario.
- Emparejado: entrada → salida en orden de hora; una marca "sin determinar"
  (CSV) cierra un par abierto o abre uno nuevo. Entrada sin salida o salida sin
  entrada = marca faltante (incidencia), y ese tramo no suma horas.
- Trabajado = suma de los pares, menos el descanso programado no marcado: el
  hueco entre tramos (ej. 12–13) y el descanso de cada tramo si no es pago.
- Tardanza: entrada después del inicio del tramo + tolerancia del horario
  (se cuenta desde el inicio). Salida anticipada: salida antes del fin del
  tramo, desde los minutos mínimos configurados.
- Ordinario = hasta lo programado. Lo que pasa de lo programado (desde los
  minutos mínimos) es extra CANDIDATO; en franco o feriado, todo lo trabajado.
  Extra AUTORIZADO = lo candidato hasta lo aprobado en autorizaciones (§7: una
  marca no es hora extra pagable).
- Nocturno: minutos dentro del horario nocturno configurado.
- Licencia aprobada de día completo: el día queda "licencia" (no es ausencia
  ni genera incidencias). Un permiso por horas aprobado corre el inicio o el
  fin del tramo para la tardanza y la salida anticipada (fase 7).
- Los días de una nómina cerrada no se recalculan (fase 10)."""
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from asistencia.models import (AutorizacionHorasExtra, ConfiguracionMarcacion, DiaAsistencia, IncidenciaAsistencia,
                               Marcacion)
from jornada.models import AsignacionHorario, DiaFeriado

MARGEN_ANTES = timedelta(hours=4)
MARGEN_DESPUES = timedelta(hours=8)


def _min(delta):
    return max(int(delta.total_seconds() // 60), 0)


def _hhmm(minutos):
    return f'{minutos // 60}:{minutos % 60:02d}'


def _hora(momento, zona):
    return momento.astimezone(zona).strftime('%H:%M')


class _Contexto:
    """Todo lo que hace falta para calcular un rango de días de un empleado, cargado una sola vez."""

    def __init__(self, empleado, desde, hasta):
        self.empleado = empleado
        self.empresa = empleado.empresa
        self.zona = ZoneInfo(self.empresa.zona_horaria or 'America/Asuncion')
        self.config = ConfiguracionMarcacion.de(self.empresa)
        inicio = datetime.combine(desde - timedelta(days=1), datetime.min.time(), tzinfo=self.zona)
        fin = datetime.combine(hasta + timedelta(days=2), datetime.min.time(), tzinfo=self.zona)
        self.marcas = list(Marcacion.objects.filter(empleado=empleado, anulada=False, fecha_hora__gte=inicio,
                                                    fecha_hora__lt=fin).order_by('fecha_hora', 'id'))
        self.asignaciones = list(AsignacionHorario.objects.select_related('horario__regimen').prefetch_related('horario__tramos')
                                 .filter(empleado=empleado, vigente_desde__lte=hasta + timedelta(days=1))
                                 .filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=desde - timedelta(days=1))))
        self.feriados = {d.fecha: d.nombre for d in DiaFeriado.objects.filter(
            fecha__gte=desde - timedelta(days=1), fecha__lte=hasta + timedelta(days=1), calendario__activo=True,
        ).filter(Q(calendario__empresa__isnull=True) | Q(calendario__empresa=self.empresa))}
        from licencias.models import SolicitudLicencia
        self.licencias = list(SolicitudLicencia.objects.select_related('tipo').filter(
            empleado=empleado, estado=SolicitudLicencia.APROBADA, fecha_desde__lte=hasta, fecha_hasta__gte=desde))
        self.autorizados = defaultdict(int)
        for fila in AutorizacionHorasExtra.objects.filter(empleado=empleado, estado=AutorizacionHorasExtra.APROBADA,
                                                          fecha__gte=desde, fecha__lte=hasta).values('fecha').annotate(t=Sum('minutos_aprobados')):
            self.autorizados[fila['fecha']] = fila['t'] or 0
        self._tramos = {}

    def licencia_del_dia(self, fecha):
        """(licencia de día completo, [permisos por horas]) aprobados ese día."""
        completa, por_horas = None, []
        for licencia in self.licencias:
            if licencia.fecha_desde <= fecha <= licencia.fecha_hasta:
                if licencia.por_horas:
                    por_horas.append(licencia)
                else:
                    completa = licencia
        return completa, por_horas

    def horario(self, fecha):
        for asignacion in self.asignaciones:
            if asignacion.vigente_desde <= fecha and (asignacion.vigente_hasta is None or fecha <= asignacion.vigente_hasta):
                return asignacion.horario
        return None

    def tramos(self, fecha):
        """[(inicio, fin, descanso, tolerancia)] programados ese día, en hora de la empresa."""
        if fecha not in self._tramos:
            horario = self.horario(fecha)
            lista = []
            if horario is not None:
                for t in sorted(horario.tramos_del_dia(fecha.weekday()), key=lambda x: (x.orden, x.hora_inicio)):
                    inicio = datetime.combine(fecha, t.hora_inicio, tzinfo=self.zona)
                    fin = datetime.combine(fecha, t.hora_fin, tzinfo=self.zona)
                    if fin <= inicio:
                        fin += timedelta(days=1)
                    lista.append((inicio, fin, t.descanso_minutos, horario.tolerancia_minutos))
            self._tramos[fecha] = lista
        return self._tramos[fecha]

    def ventana(self, fecha):
        tramos = self.tramos(fecha)
        if tramos:
            return min(t[0] for t in tramos) - MARGEN_ANTES, max(t[1] for t in tramos) + MARGEN_DESPUES
        inicio = datetime.combine(fecha, datetime.min.time(), tzinfo=self.zona)
        return inicio, inicio + timedelta(days=1)

    def dia_de(self, momento):
        """El día de trabajo al que pertenece una marca."""
        local = momento.astimezone(self.zona).date()
        candidatos = []
        for fecha in (local - timedelta(days=1), local):
            inicio, fin = self.ventana(fecha)
            if inicio <= momento < fin:
                candidatos.append(fecha)
        if not candidatos:
            return local
        if len(candidatos) == 1:
            return candidatos[0]

        def distancia(fecha):
            tramos = self.tramos(fecha)
            if not tramos:
                return timedelta(days=99)  # un día programado gana a uno sin horario
            return min(min(abs(momento - t[0]), abs(momento - t[1])) for t in tramos)
        return min(candidatos, key=distancia)


def _pares(marcas):
    """[(entrada, salida)] y la cantidad de marcas faltantes."""
    pares, abierta, faltantes = [], None, 0
    for marca in marcas:
        tipo = marca.tipo
        if tipo == Marcacion.DESCONOCIDO:
            tipo = Marcacion.SALIDA if abierta else Marcacion.ENTRADA
        if tipo == Marcacion.ENTRADA:
            if abierta is not None:
                faltantes += 1  # la entrada anterior quedó sin salida
            abierta = marca
        elif tipo == Marcacion.SALIDA:
            if abierta is None:
                faltantes += 1  # salida sin entrada
            else:
                pares.append((abierta.fecha_hora, marca.fecha_hora))
                abierta = None
    if abierta is not None:
        faltantes += 1
    return pares, faltantes


def _solapado(intervalos, inicio, fin):
    """Minutos de los intervalos que caen dentro de [inicio, fin]."""
    return sum(_min(min(b, fin) - max(a, inicio)) for a, b in intervalos if min(b, fin) > max(a, inicio))


def _nocturnos(pares, config, zona):
    if config.inicio_nocturno == config.fin_nocturno:
        return 0
    total = 0
    for entrada, salida in pares:
        dia = entrada.astimezone(zona).date() - timedelta(days=1)
        while datetime.combine(dia, config.inicio_nocturno, tzinfo=zona) < salida:
            inicio = datetime.combine(dia, config.inicio_nocturno, tzinfo=zona)
            fin = datetime.combine(dia, config.fin_nocturno, tzinfo=zona)
            if fin <= inicio:
                fin += timedelta(days=1)
            total += _min(min(salida, fin) - max(entrada, inicio)) if min(salida, fin) > max(entrada, inicio) else 0
            dia += timedelta(days=1)
    return total


def _calcular(ctx, fecha):
    """Valores del día (sin guardar) + incidencias a generar."""
    zona, config = ctx.zona, ctx.config
    horario = ctx.horario(fecha)
    tramos = ctx.tramos(fecha)
    feriado = ctx.feriados.get(fecha, '')
    marcas = [m for m in ctx.marcas if ctx.dia_de(m.fecha_hora) == fecha]
    pares, faltantes = _pares(marcas)
    explicacion, incidencias = [], []
    v = dict.fromkeys(['minutos_programados', 'minutos_trabajados', 'minutos_descanso', 'minutos_tardanza',
                       'minutos_salida_anticipada', 'minutos_ordinarios', 'minutos_extra_candidatos',
                       'minutos_extra_autorizados', 'minutos_nocturnos', 'minutos_feriado'], 0)

    if horario is None:
        explicacion.append('Sin horario asignado ese día: no hay horas programadas, tardanzas ni ausencias.')
    else:
        v['minutos_programados'] = horario.minutos_dia(fecha.weekday()) if not feriado else 0
        if tramos:
            explicacion.append(f'Horario "{horario}": ' + ', '.join(f'{_hora(a, zona)}–{_hora(b, zona)}' for a, b, _, _ in tramos)
                               + f' ({_hhmm(horario.minutos_dia(fecha.weekday()))} h programadas, tolerancia {horario.tolerancia_minutos} min).')
        else:
            explicacion.append(f'Horario "{horario}": este día no tiene tramos (franco).')
    if feriado:
        explicacion.append(f'Feriado: {feriado}. No hay horas programadas; lo trabajado cuenta como trabajo en feriado.')
    explicacion.append(f'Marcas del día: {len(marcas)}' + (f' ({", ".join(_hora(m.fecha_hora, zona) + " " + m.get_tipo_display().lower() for m in marcas)}).' if marcas else '.'))

    bruto = sum(_min(b - a) for a, b in pares)
    pausas = [(pares[i][1], pares[i + 1][0]) for i in range(len(pares) - 1)]
    descanso_real = sum(_min(b - a) for a, b in pausas)
    # Descanso programado no marcado:
    # - del hueco entre tramos (ej. 12–13, nunca pago), lo que se trabajó dentro de él;
    # - del descanso dentro de un tramo (si no es pago), lo que falte de pausa
    #   marcada en ese tramo, solo si se trabajó ese tramo.
    descuento = 0
    for i in range(len(tramos) - 1):
        descuento += _solapado(pares, tramos[i][1], tramos[i + 1][0])
    if horario and not horario.descanso_pagado:
        for inicio, fin, descanso, _ in tramos:
            if descanso and _solapado(pares, inicio, fin) > descanso:
                descuento += max(descanso - _solapado(pausas, inicio, fin), 0)
    v['minutos_trabajados'] = max(bruto - descuento, 0)
    v['minutos_descanso'] = descanso_real + descuento
    if pares:
        explicacion.append(f'Pares entrada–salida: {", ".join(f"{_hora(a, zona)}–{_hora(b, zona)}" for a, b in pares)} = {_hhmm(bruto)} h.'
                           + (f' Menos {descuento} min de descanso programado no marcado.' if descuento else ''))
    if faltantes:
        explicacion.append(f'{faltantes} marca(s) faltante(s): ese tramo no suma horas hasta que se corrija.')
        incidencias.append((IncidenciaAsistencia.MARCA_FALTANTE, f'{faltantes} marca(s) faltante(s) (entrada o salida sin su par).', faltantes))

    licencia, permisos = ctx.licencia_del_dia(fecha)
    if licencia:
        explicacion.append(f'Licencia aprobada: {licencia.tipo} ({"paga" if licencia.tipo.es_paga else "no paga"}), '
                           f'del {licencia.fecha_desde:%d/%m} al {licencia.fecha_hasta:%d/%m}. No es ausencia.')
    franjas = []
    for permiso in permisos:
        franjas.append((datetime.combine(fecha, permiso.hora_desde, tzinfo=zona), datetime.combine(fecha, permiso.hora_hasta, tzinfo=zona)))
        explicacion.append(f'Permiso aprobado de {permiso.hora_desde:%H:%M} a {permiso.hora_hasta:%H:%M} ({permiso.tipo}): '
                           'justifica la llegada tarde o la salida anticipada en esa franja.')

    # Tardanzas y salidas anticipadas, tramo por tramo (un permiso por horas corre el inicio o el fin).
    if tramos and not feriado and not licencia:
        for inicio_programado, fin_programado, _, tolerancia in tramos:
            inicio, fin = inicio_programado, fin_programado
            for desde_permiso, hasta_permiso in franjas:
                if desde_permiso <= inicio < hasta_permiso:
                    inicio = hasta_permiso
                if desde_permiso < fin <= hasta_permiso:
                    fin = desde_permiso
            entradas = [a for a, _ in pares if inicio - MARGEN_ANTES <= a <= fin]
            if entradas and min(entradas) > inicio + timedelta(minutes=tolerancia):
                tarde = _min(min(entradas) - inicio)
                v['minutos_tardanza'] += tarde
                explicacion.append(f'Llegó {_hora(min(entradas), zona)} al tramo de {_hora(inicio, zona)}: {tarde} min tarde (tolerancia {tolerancia}).')
            salidas = [b for _, b in pares if inicio <= b <= fin + MARGEN_DESPUES]
            if salidas and max(salidas) < fin - timedelta(minutes=config.minimos_tardanza):
                antes = _min(fin - max(salidas))
                v['minutos_salida_anticipada'] += antes
                explicacion.append(f'Salió {_hora(max(salidas), zona)} del tramo que termina {_hora(fin, zona)}: {antes} min antes.')
        if v['minutos_tardanza']:
            incidencias.append((IncidenciaAsistencia.TARDANZA, f'Llegada tarde: {v["minutos_tardanza"]} min.', v['minutos_tardanza']))
        if v['minutos_salida_anticipada']:
            incidencias.append((IncidenciaAsistencia.SALIDA_ANTICIPADA, f'Salida anticipada: {v["minutos_salida_anticipada"]} min.',
                                v['minutos_salida_anticipada']))

    laborable = bool(tramos) and not feriado and not licencia
    trabajado = v['minutos_trabajados']
    if licencia:
        pass  # día de licencia: sin ordinarias ni extras (si marcó igual, queda en la explicación y las marcas)
    elif laborable:
        v['minutos_ordinarios'] = min(trabajado, v['minutos_programados'])
        excedente = trabajado - v['minutos_programados']
        if excedente >= config.minimos_extra:
            v['minutos_extra_candidatos'] = excedente
            explicacion.append(f'Trabajó {_hhmm(excedente)} h más que lo programado: horas extra candidatas.')
        elif excedente > 0:
            explicacion.append(f'{excedente} min por encima de lo programado: menos que el mínimo de {config.minimos_extra} min, no cuentan como extra.')
    elif trabajado:
        v['minutos_extra_candidatos'] = trabajado if trabajado >= config.minimos_extra else 0
        if feriado:
            v['minutos_feriado'] = trabajado
        motivo = 'feriado' if feriado else 'día sin horario de trabajo' if horario is None else 'día franco'
        explicacion.append(f'Trabajó {_hhmm(trabajado)} h en {motivo}: todo cuenta como hora extra candidata.')
        if horario is not None:
            incidencias.append((IncidenciaAsistencia.TRABAJO_EN_DESCANSO, f'Trabajó {_hhmm(trabajado)} h en {motivo}.', trabajado))

    autorizado = ctx.autorizados.get(fecha, 0)
    v['minutos_extra_autorizados'] = min(v['minutos_extra_candidatos'], autorizado)
    if v['minutos_extra_candidatos']:
        explicacion.append(f'Horas extra autorizadas: {_hhmm(v["minutos_extra_autorizados"])} h de {_hhmm(v["minutos_extra_candidatos"])} h candidatas'
                           f' (aprobado ese día: {_hhmm(autorizado)} h).')
        sin_autorizar = v['minutos_extra_candidatos'] - v['minutos_extra_autorizados']
        if sin_autorizar:
            incidencias.append((IncidenciaAsistencia.EXTRA_SIN_AUTORIZAR, f'{_hhmm(sin_autorizar)} h extra sin autorización.', sin_autorizar))

    v['minutos_nocturnos'] = _nocturnos(pares, config, zona)
    if v['minutos_nocturnos']:
        explicacion.append(f'{_hhmm(v["minutos_nocturnos"])} h dentro del horario nocturno ({config.inicio_nocturno:%H:%M}–{config.fin_nocturno:%H:%M}).')

    if licencia:
        estado = DiaAsistencia.LICENCIA
    elif horario is None and not marcas:
        estado = DiaAsistencia.SIN_HORARIO
    elif not marcas:
        if feriado:
            estado = DiaAsistencia.FERIADO
        elif laborable:
            estado = DiaAsistencia.AUSENTE
            incidencias.append((IncidenciaAsistencia.AUSENCIA, 'Sin marcas en un día laborable.', v['minutos_programados']))
            explicacion.append('Día laborable sin marcas: ausente.')
        else:
            estado = DiaAsistencia.FRANCO
    else:
        estado = DiaAsistencia.INCOMPLETO if faltantes else DiaAsistencia.PRESENTE

    v.update(
        horario=horario, horario_resumen=horario.resumen() if horario else '', feriado=feriado, es_laborable=laborable,
        primera_entrada=min((a for a, _ in pares), default=None), ultima_salida=max((b for _, b in pares), default=None),
        marcas_faltantes=faltantes, estado=estado, explicacion=explicacion, licencia=licencia,
    )
    return v, incidencias


def calcular(empleado, desde, hasta=None):
    """Calcula (o recalcula) los días del empleado entre `desde` y `hasta`
    (inclusive). Saltea los días fuera de su período laboral y los de nóminas
    cerradas. Devuelve la lista de DiaAsistencia."""
    from asistencia.importacion import periodo_cerrado
    hasta = hasta or desde
    desde = max(desde, empleado.fecha_ingreso)
    if empleado.fecha_egreso:
        hasta = min(hasta, empleado.fecha_egreso)
    if hasta < desde:
        return []
    ctx = _Contexto(empleado, desde, hasta)
    existentes = {d.fecha: d for d in DiaAsistencia.objects.filter(empleado=empleado, fecha__gte=desde, fecha__lte=hasta)}
    resultado = []
    ahora = timezone.now()
    fecha = desde
    with transaction.atomic():
        while fecha <= hasta:
            if periodo_cerrado(empleado.empresa, fecha):
                fecha += timedelta(days=1)
                continue
            valores, incidencias = _calcular(ctx, fecha)
            dia = existentes.get(fecha)
            if dia is None:
                dia = DiaAsistencia(empresa_id=empleado.empresa_id, empleado=empleado, fecha=fecha, version_calculo=1)
            else:
                cambio = any(getattr(dia, k) != v for k, v in valores.items() if k != 'explicacion')
                dia.version_calculo += 1
                if cambio:
                    dia.revisado_por = None
                    dia.revisado_en = None
            for campo, valor in valores.items():
                setattr(dia, campo, valor)
            dia.calculado_en = ahora
            dia.save()
            _regenerar_incidencias(empleado, fecha, incidencias)
            resultado.append(dia)
            fecha += timedelta(days=1)
    return resultado


def _regenerar_incidencias(empleado, fecha, incidencias):
    """Las automáticas pendientes se rehacen; las resueltas o justificadas se respetan (no se duplican)."""
    IncidenciaAsistencia.objects.filter(empleado=empleado, fecha=fecha, automatica=True,
                                        estado=IncidenciaAsistencia.PENDIENTE).delete()
    cerradas = set(IncidenciaAsistencia.objects.filter(empleado=empleado, fecha=fecha, automatica=True)
                   .values_list('tipo', flat=True))
    IncidenciaAsistencia.objects.bulk_create([
        IncidenciaAsistencia(empresa_id=empleado.empresa_id, empleado=empleado, fecha=fecha, tipo=tipo,
                             descripcion=descripcion[:250], minutos=minutos, automatica=True)
        for tipo, descripcion, minutos in incidencias if tipo not in cerradas
    ])


def marcas_del_dia(empleado, fecha):
    """Las marcas que pertenecen a ese día de trabajo, incluidas las anuladas (para mostrarlas señaladas)."""
    ctx = _Contexto(empleado, fecha, fecha)
    inicio, fin = ctx.ventana(fecha)
    candidatas = Marcacion.objects.select_related('terminal', 'reloj').filter(
        empleado=empleado, fecha_hora__gte=inicio - timedelta(days=1), fecha_hora__lt=fin + timedelta(days=1)).order_by('fecha_hora', 'id')
    return [m for m in candidatas if ctx.dia_de(m.fecha_hora) == fecha]


def recalcular_por_momentos(empleado, momentos):
    """Después de marcas nuevas, anuladas o importadas: recalcula los días que
    pueden contenerlas (el día local y el anterior, por los turnos de noche)."""
    if not momentos:
        return
    zona = ZoneInfo(empleado.empresa.zona_horaria or 'America/Asuncion')
    fechas = sorted({m.astimezone(zona).date() for m in momentos})
    calcular(empleado, fechas[0] - timedelta(days=1), min(fechas[-1], timezone.localdate()))


def recalcular_despues(empleado, momentos):
    """Igual que `recalcular_por_momentos`, pero cuando la transacción en curso se confirma."""
    momentos = list(momentos)
    transaction.on_commit(lambda: recalcular_por_momentos(empleado, momentos))
