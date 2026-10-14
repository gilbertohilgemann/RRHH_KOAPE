"""Motor de nómina (fase 10; §8 de la especificación).

`calcular(corrida, usuario)` liquida a todos los empleados de la empresa que
trabajaron en el período. Es reproducible (mismos datos y reglas = mismo
resultado) y recalcular reemplaza las liquidaciones de la corrida: no duplica
conceptos, novedades ni cuotas (se marcan "aplicadas" recién al cerrar).

Para cada empleado:
1. Contrato y sueldo aprobado vigentes (sin ellos: error que bloquea la
   aprobación). Días activos en el período (ingreso, egreso, contrato).
2. Asistencia del período (fase 6): días trabajados, ausencias no
   justificadas, licencias no pagas, horas extra AUTORIZADAS (las de un día
   nocturno van como extra nocturna; las de un feriado o día de descanso,
   como trabajo en feriado), horas nocturnas ordinarias.
3. Variables: los parámetros legales vigentes al fin del período
   (`legal/servicios.vigentes`) + los datos del empleado (VALOR_DIA,
   VALOR_HORA, DIAS_PAGADOS… según la base de su esquema salarial).
4. Haberes: conceptos automáticos con su regla, conceptos fijos y novedades
   aprobadas. Con ellos, BASE_IPS y el bruto.
5. Descuentos y aportes: conceptos automáticos (IPS, ausencias), conceptos
   fijos, novedades, descuentos autorizados y cuotas de anticipos/préstamos.
6. Neto = haberes − descuentos − aportes del trabajador. El aporte del
   empleador suma al costo del empleador y nunca se resta del neto.

Si algo usa reglas sin aprobar (legales o de cálculo), la corrida queda como
SIMULACIÓN y no se puede aprobar (§9)."""
from calendar import monthrange
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from legal import servicios as legal
from legal.models import ConjuntoReglas
from nomina import expresiones, redondeo
from nomina.models import (ConceptoNomina, ConceptoRecurrente, CorridaNomina, LineaNomina, LiquidacionEmpleado,
                           ReglaConcepto)

CERO = Decimal('0')
SIGNO = {ConceptoNomina.HABER: 1, ConceptoNomina.DESCUENTO: -1, ConceptoNomina.APORTE_TRABAJADOR: -1,
         ConceptoNomina.APORTE_PATRONAL: 0, ConceptoNomina.INFORMATIVO: 0}


def _gs(valor):
    return f'{Decimal(valor):,.0f}'.replace(',', '.')


def _num(valor):
    valor = Decimal(valor)
    return _gs(valor) if valor == valor.to_integral() and abs(valor) >= 1000 else f'{valor.normalize():f}'


class _Contexto:
    """Lo común a todos los empleados de la corrida, cargado una sola vez."""

    def __init__(self, corrida):
        self.corrida = corrida
        self.empresa = corrida.empresa
        self.periodo = corrida.periodo
        self.desde, self.hasta = self.periodo.fecha_desde, self.periodo.fecha_hasta
        resueltos = legal.vigentes(self.empresa, self.hasta, simulacion=True)
        self.legales = resueltos['variables']
        self.estado_legal = {d['codigo']: d['estado'] for d in resueltos['detalle']}
        self.simulacion = False
        self.advertencias = []
        self.origen = corrida.corrida_origen
        conceptos = {}
        for c in ConceptoNomina.objects.filter(Q(empresa__isnull=True) | Q(empresa=self.empresa), activo=True).order_by('orden'):
            if c.codigo not in conceptos or c.empresa_id:
                conceptos[c.codigo] = c
        self.conceptos = conceptos
        self.automaticos = [c for c in conceptos.values() if c.aplicacion == 'automatica']
        self.de_aguinaldo = [c for c in conceptos.values() if c.aplicacion == 'aguinaldo']
        self.de_final = [c for c in conceptos.values() if c.aplicacion == 'liquidacion_final']
        self.final = None
        if corrida.tipo == 'liquidacion_final':
            from nomina.models import LiquidacionFinal
            # La de la corrida, o la de la original si esta es su rectificación.
            self.final = LiquidacionFinal.objects.filter(corrida__in=[corrida.pk, corrida.corrida_origen_id]).select_related('empleado').first()
        reglas = defaultdict(list)
        for r in ReglaConcepto.objects.filter(Q(empresa__isnull=True) | Q(empresa=self.empresa)).exclude(
                estado=ReglaConcepto.RETIRADA).filter(vigente_desde__lte=self.hasta).filter(
                Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=self.hasta)).select_related('conjunto_legal'):
            reglas[r.concepto.codigo].append(r)
        # Aprobadas antes que borradores; las de la empresa antes que las globales; después, la prioridad.
        for lista in reglas.values():
            lista.sort(key=lambda r: (r.estado != ReglaConcepto.APROBADA, r.empresa_id is None, r.prioridad, -r.vigente_desde.toordinal()))
        self.reglas = reglas

    def avisar(self, texto):
        if texto not in self.advertencias:
            self.advertencias.append(texto)


class _Liquidador:
    def __init__(self, ctx, empleado):
        self.ctx = ctx
        self.empleado = empleado
        self.lineas = []
        self.advertencias = []
        self.errores = []
        self.variables = dict(ctx.legales)

    # ----------------------------------------------------------------- líneas
    def agregar(self, concepto, importe, explicacion, origen, origen_id=None, regla=None, cantidad=None, tasa=None, base=None):
        importe = redondeo.redondear(importe, regla.redondeo if regla else redondeo.ENTERO)
        if importe == 0:
            return None
        if importe < 0:
            self.errores.append(f'{concepto.codigo}: dio un importe negativo ({_gs(importe)}); revisá la fórmula o los datos.')
            return None
        signo = SIGNO[concepto.tipo] if concepto.afecta_neto else 0
        linea = LineaNomina(
            empresa=self.ctx.empresa, concepto=concepto, codigo=concepto.codigo, nombre=concepto.nombre, tipo=concepto.tipo,
            cantidad=cantidad, tasa=tasa, base=base, importe=importe, importe_con_signo=importe * signo, regla=regla,
            explicacion=explicacion, origen=origen, origen_id=origen_id, secuencia=concepto.orden, afecta_neto=concepto.afecta_neto)
        self.lineas.append(linea)
        return linea

    def por_regla(self, concepto):
        reglas = self.ctx.reglas.get(concepto.codigo, [])
        if not reglas:
            if concepto.codigo == 'SUELDO':
                self.errores.append('No hay una regla de cálculo vigente para SUELDO.')
            return
        for regla in reglas:
            try:
                if regla.condicion.strip() and not expresiones.evaluar(regla.condicion, self.variables):
                    continue
                importe = regla.calcular({**self.variables})
            except expresiones.ErrorFormula as e:
                self.errores.append(f'{concepto.codigo}: {e}')
                return
            if importe is None:
                continue
            usadas = sorted(regla.variables())
            if regla.estado != ReglaConcepto.APROBADA:
                self.ctx.simulacion = True
                self.ctx.avisar(f'La regla de {concepto.codigo} está en borrador: la liquidación es una simulación.')
            for v in usadas:
                estado = self.ctx.estado_legal.get(v)
                if estado and estado != ConjuntoReglas.APROBADO:
                    self.ctx.simulacion = True
                    self.ctx.avisar(f'El parámetro legal {v} está sin aprobar: la liquidación es una simulación.')
            valores = ', '.join(f'{v} = {_num(self.variables[v])}' for v in usadas if v in self.variables)
            return self.agregar(concepto, importe, f'{regla.expresion} → con {valores}', 'regla', regla.pk, regla)
        return None

    def _importe_fijo(self, recurrente):
        concepto = recurrente.concepto
        if recurrente.monto is not None:
            return recurrente.monto, f'Monto fijo de {_gs(recurrente.monto)}'
        if recurrente.cantidad is not None and recurrente.tasa is not None:
            return recurrente.cantidad * recurrente.tasa, f'{_num(recurrente.cantidad)} × {_num(recurrente.tasa)}'
        tasa = recurrente.tasa if recurrente.tasa is not None else concepto.tasa_por_defecto
        if tasa is not None:
            base = self.variables['SALARIO_BASE']
            return base * tasa / 100, f'{_num(tasa)} % de {_gs(base)} (sueldo)'
        return None, ''

    # ----------------------------------------------------------- liquidación
    def liquidar(self):
        ctx, empleado = self.ctx, self.empleado
        if ctx.corrida.tipo == 'aguinaldo':
            return self.liquidar_aguinaldo()
        from contratos.models import ContratoEmpleado, sueldo_vigente
        contratos = ContratoEmpleado.objects.filter(
            empleado=empleado, estado__in=(ContratoEmpleado.VIGENTE, ContratoEmpleado.FINALIZADO),
            fecha_inicio__lte=ctx.hasta).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=ctx.desde)).order_by('-fecha_inicio')
        contrato = contratos.first()
        activo_desde = max(ctx.desde, empleado.fecha_ingreso, contrato.fecha_inicio if contrato else ctx.desde)
        activo_hasta = min(ctx.hasta, empleado.fecha_egreso or ctx.hasta, (contrato.fecha_fin if contrato and contrato.fecha_fin else ctx.hasta),
                           ctx.final.fecha_egreso if ctx.final else ctx.hasta)
        if activo_hasta < activo_desde:
            activo_hasta = activo_desde
        liq = LiquidacionEmpleado(empresa=ctx.empresa, corrida=ctx.corrida, empleado=empleado, contrato=contrato,
                                  centro_costo=empleado.centro_costo, creado_por=None)
        sueldo = sueldo_vigente(empleado, activo_hasta) if contrato else None
        if contrato is None:
            self.errores.append('No tiene un contrato vigente en el período.')
        elif sueldo is None:
            self.errores.append(f'No tiene un sueldo aprobado vigente al {activo_hasta:%d/%m/%Y}.')
        if self.errores:
            return self._terminar(liq)

        base = sueldo.esquema_salarial.base_calculo
        liq.salario_base, liq.base_calculo = sueldo.salario_base, base
        for necesario in ('DIVISOR_MENSUAL_DIAS', 'HORAS_JORNADA_DIURNA'):
            if necesario not in self.variables:
                self.errores.append(f'Falta el parámetro legal {necesario}.')
        if self.errores:
            return self._terminar(liq)
        divisor = Decimal(self.variables['DIVISOR_MENSUAL_DIAS'])
        horas_dia = Decimal(self.variables['HORAS_JORNADA_DIURNA'])

        # --- asistencia del período
        from asistencia.models import DiaAsistencia, IncidenciaAsistencia
        dias = list(DiaAsistencia.objects.filter(empleado=empleado, fecha__gte=activo_desde, fecha__lte=activo_hasta)
                    .select_related('licencia__tipo'))
        justificadas = set(IncidenciaAsistencia.objects.filter(
            empleado=empleado, fecha__gte=activo_desde, fecha__lte=activo_hasta, tipo=IncidenciaAsistencia.AUSENCIA,
            estado='justificada').values_list('fecha', flat=True))
        dias_activos = (activo_hasta - activo_desde).days + 1
        if len(dias) < dias_activos:
            self.advertencias.append(f'Hay {dias_activos - len(dias)} día(s) del período sin asistencia calculada: '
                                     'calculá la asistencia antes de liquidar.')
        trabajados = sum(1 for d in dias if d.estado in (DiaAsistencia.PRESENTE, DiaAsistencia.INCOMPLETO))
        ausencias = sum(1 for d in dias if d.estado == DiaAsistencia.AUSENTE and d.fecha not in justificadas)
        licencia_paga = [d for d in dias if d.estado == DiaAsistencia.LICENCIA and d.minutos_programados and d.licencia_id
                         and d.licencia.tipo.es_paga]
        licencia_no_paga = sum(1 for d in dias if d.estado == DiaAsistencia.LICENCIA and d.minutos_programados and d.licencia_id
                               and not d.licencia.tipo.es_paga)
        feriados_laborables = sum(1 for d in dias if d.estado == DiaAsistencia.FERIADO and d.horario_id)
        extra_diurna = extra_nocturna = feriado = nocturnas = Decimal('0')
        for d in dias:
            autorizado = Decimal(d.minutos_extra_autorizados)
            if not d.es_laborable and d.estado != DiaAsistencia.LICENCIA:
                feriado += autorizado  # feriado o día de descanso: todo lo autorizado va como trabajo en feriado
                continue
            noct_extra = min(autorizado, Decimal(d.minutos_nocturnos))
            extra_nocturna += noct_extra
            extra_diurna += autorizado - noct_extra
            nocturnas += max(Decimal(d.minutos_nocturnos) - noct_extra, 0)
        liq.dias_trabajados = trabajados
        liq.minutos_ordinarios = sum(d.minutos_ordinarios for d in dias)
        liq.minutos_extra = sum(d.minutos_extra_autorizados for d in dias)

        # --- valor del día y días pagados según la base del esquema
        salario = Decimal(sueldo.salario_base)
        completo = activo_desde == ctx.desde and activo_hasta == ctx.hasta
        dias_mes = monthrange(ctx.hasta.year, ctx.hasta.month)[1]
        periodo_es_mes = ctx.desde.day == 1 and ctx.hasta.day == dias_mes and ctx.desde.month == ctx.hasta.month
        ausencias_no_pagas = Decimal(ausencias + licencia_no_paga)
        explicacion_dias = ''
        if base in ('mes', 'comision', 'destajo', 'mixta'):
            valor_dia = salario / divisor
            pagados = divisor if completo and periodo_es_mes else min(Decimal(dias_activos), divisor)
            explicacion_dias = f'sueldo mensual {_gs(salario)} / {_num(divisor)} días'
            if base != 'mes':
                self.advertencias.append('Esquema con parte variable: el sueldo fijo se liquida como mensual; '
                                         'la comisión o la producción entra como novedad.')
        elif base == 'quincena':
            valor_dia = salario / 15
            pagados = Decimal(15) if completo else Decimal(min(dias_activos, 15))
            explicacion_dias = f'sueldo quincenal {_gs(salario)} / 15 días'
        elif base == 'semana':
            valor_dia = salario / 7
            pagados = Decimal(dias_activos)
            explicacion_dias = f'sueldo semanal {_gs(salario)} / 7 días'
        elif base == 'dia':
            valor_dia = Decimal(sueldo.tarifa_dia or salario)
            pagados = Decimal(trabajados + len(licencia_paga) + feriados_laborables)
            ausencias_no_pagas = CERO  # al jornalero se le paga lo trabajado: las ausencias no se descuentan aparte
            explicacion_dias = f'jornal {_gs(valor_dia)}; días pagados = {trabajados} trabajados + {len(licencia_paga)} de licencia paga + {feriados_laborables} feriados'
            if feriados_laborables:
                self.advertencias.append('Se pagaron feriados al jornalero (a verificar con la norma vigente).')
        else:  # hora
            valor_hora = Decimal(sueldo.tarifa_hora or salario)
            valor_dia = valor_hora * horas_dia
            minutos_pagados = Decimal(liq.minutos_ordinarios + sum(d.minutos_programados for d in licencia_paga))
            pagados = (minutos_pagados / 60 / horas_dia).quantize(Decimal('0.0001'))
            ausencias_no_pagas = CERO
            explicacion_dias = f'tarifa por hora {_gs(valor_hora)}; {_num(minutos_pagados / 60)} horas pagadas'
        valor_hora = Decimal(sueldo.tarifa_hora) if sueldo.tarifa_hora else valor_dia / horas_dia
        liq.dias_pagados = pagados
        liq.dias_no_pagados = ausencias_no_pagas
        self.variables.update({
            'SALARIO_BASE': salario, 'VALOR_DIA': valor_dia.quantize(Decimal('0.01')), 'VALOR_HORA': valor_hora.quantize(Decimal('0.01')),
            'DIAS_PAGADOS': pagados, 'DIAS_TRABAJADOS': Decimal(trabajados), 'DIAS_AUSENCIA_NO_PAGA': ausencias_no_pagas,
            'HORAS_EXTRA_DIURNAS': extra_diurna / 60, 'HORAS_EXTRA_NOCTURNAS': extra_nocturna / 60,
            'HORAS_NOCTURNAS': nocturnas / 60, 'HORAS_FERIADO': feriado / 60, 'TOTAL_REMUNERACIONES_ANIO': CERO,
            'CANTIDAD': CERO, 'TASA': CERO, 'MONTO': CERO,
        })
        self.explicacion_dias = explicacion_dias

        # --- haberes
        novedades, cuotas = self._novedades_y_cuotas()
        fijos = self._conceptos_fijos()
        ya_cobrado = ctx.final is not None and self._salario_ya_liquidado()
        if ya_cobrado:
            self.advertencias.append('Los sueldos hasta el egreso ya se liquidaron en una nómina cerrada: solo van los conceptos del egreso.')
            fijos, novedades = [], [n for n in novedades if n.concepto.tipo != ConceptoNomina.HABER]
        for concepto in ([] if ya_cobrado else ctx.automaticos):
            if concepto.tipo == ConceptoNomina.HABER:
                linea_antes = len(self.lineas)
                self.por_regla(concepto)
                if concepto.codigo == 'SUELDO' and len(self.lineas) > linea_antes:
                    self.lineas[-1].explicacion = f'{explicacion_dias}. ' + self.lineas[-1].explicacion
                    self.lineas[-1].cantidad, self.lineas[-1].tasa = pagados, self.variables['VALOR_DIA']
        self._fijos_y_novedades(fijos, novedades, ConceptoNomina.HABER)
        if ctx.final is not None:
            self._conceptos_del_egreso()

        haberes = [l for l in self.lineas if l.tipo == ConceptoNomina.HABER]
        self.variables['BASE_IPS'] = sum((l.importe for l in haberes if l.concepto.afecta_base_ips), CERO)

        # --- descuentos y aportes
        for concepto in ctx.automaticos:
            if concepto.tipo != ConceptoNomina.HABER:
                self.por_regla(concepto)
        for linea in self.lineas:
            if linea.tipo in (ConceptoNomina.APORTE_TRABAJADOR, ConceptoNomina.APORTE_PATRONAL):
                linea.base = self.variables['BASE_IPS']  # en el recibo se ve sobre qué base se aportó
        self._fijos_y_novedades(fijos, novedades, ConceptoNomina.DESCUENTO)
        self._descuentos_autorizados()
        for cuota in cuotas:
            origen = f'anticipo del {cuota.anticipo.fecha:%d/%m/%Y}' if cuota.anticipo_id else f'préstamo del {cuota.prestamo.fecha:%d/%m/%Y}'
            self.agregar(cuota.concepto, cuota.monto, f'Cuota {cuota.numero} del {origen} (mes {cuota.mes:%m/%Y})', 'cuota', cuota.pk)

        return self._totales(liq)

    def _totales(self, liq):
        ctx, empleado = self.ctx, self.empleado
        haberes = [l for l in self.lineas if l.tipo == ConceptoNomina.HABER]
        bruto = sum((l.importe for l in haberes), CERO)
        liq.bruto = bruto
        liq.descuentos = sum((l.importe for l in self.lineas if l.tipo == ConceptoNomina.DESCUENTO and l.afecta_neto), CERO)
        liq.aportes_trabajador = sum((l.importe for l in self.lineas if l.tipo == ConceptoNomina.APORTE_TRABAJADOR and l.afecta_neto), CERO)
        liq.neto = sum((l.importe_con_signo for l in self.lineas), CERO)
        liq.aportes_patronales = sum((l.importe for l in self.lineas if l.tipo == ConceptoNomina.APORTE_PATRONAL), CERO)
        otros = sum((l.importe for l in self.lineas if l.tipo == ConceptoNomina.INFORMATIVO and l.concepto.afecta_costo_patronal), CERO)
        liq.otros_costos = otros
        liq.costo_empleador = bruto + liq.aportes_patronales + otros
        divisor_aguinaldo = self.variables.get('AGUINALDO_DIVISOR')
        if divisor_aguinaldo and ctx.corrida.tipo in (CorridaNomina.REGULAR, CorridaNomina.RECTIFICACION):
            base_aguinaldo = sum((l.importe for l in haberes if l.concepto.afecta_base_aguinaldo), CERO)
            liq.provision_aguinaldo = redondeo.redondear(base_aguinaldo / Decimal(divisor_aguinaldo))
        if liq.neto < 0:
            self.errores.append(f'Los descuentos superan a los haberes (neto {_gs(liq.neto)}).')
        tope = self.variables.get('TOPE_DESCUENTOS_PORCENTAJE')
        voluntarios = sum((l.importe for l in self.lineas if l.origen in ('descuento', 'cuota', 'novedad', 'concepto_fijo')
                           and l.tipo == ConceptoNomina.DESCUENTO), CERO)
        if tope is not None and bruto and voluntarios > bruto * Decimal(tope) / 100:
            self.advertencias.append(f'Los descuentos ({_gs(voluntarios)}) superan el {_num(tope)} % del bruto.')
        if ctx.origen is not None:
            anterior = ctx.origen.liquidaciones.filter(empleado=empleado).first()
            liq.neto_anterior = anterior.neto if anterior else CERO
        return self._terminar(liq)

    def _terminar(self, liq):
        liq.advertencias = self.errores + self.advertencias
        liq.estado_calculo = (LiquidacionEmpleado.ERROR if self.errores
                              else LiquidacionEmpleado.ADVERTENCIA if self.advertencias else LiquidacionEmpleado.OK)
        return liq, self.lineas

    # ----------------------------------------------------- fuentes de datos
    def _novedades_y_cuotas(self):
        from novedades.models import CuotaRecuperacion, Novedad
        ctx = self.ctx
        estado_novedad = Q(estado=Novedad.APROBADA)
        estado_cuota = Q(estado=CuotaRecuperacion.PENDIENTE)
        if ctx.origen is not None:  # rectificación: rehace también lo que aplicó la corrida rectificada
            estado_novedad |= Q(estado=Novedad.APLICADA, corrida=ctx.origen.pk)
            estado_cuota |= Q(estado=CuotaRecuperacion.APLICADA, corrida=ctx.origen.pk)
        novedades = list(Novedad.objects.filter(estado_novedad, empleado=self.empleado, periodo_desde__lte=ctx.hasta,
                                                periodo_hasta__gte=ctx.desde).select_related('concepto'))
        cuotas = CuotaRecuperacion.objects.filter(estado_cuota, empleado=self.empleado).select_related('concepto', 'anticipo', 'prestamo')
        if ctx.final is None:
            cuotas = cuotas.filter(mes__lte=ctx.hasta, mes__gte=ctx.desde.replace(day=1))
        else:
            # Al egreso se descuenta todo lo que falta recuperar (con aviso: verificar el tope legal).
            if cuotas.filter(mes__gt=ctx.hasta).exists():
                self.advertencias.append('Se descuenta el saldo completo de anticipos y préstamos: verificá el tope legal de descuentos al egreso.')
        return novedades, list(cuotas)

    # --------------------------------------------------- aguinaldo y egreso
    def _remuneraciones_del_anio(self, desde, hasta):
        """(computable para el aguinaldo, aguinaldo ya pagado) de las nóminas cerradas (sin las rectificadas) entre esas fechas."""
        cerradas = LineaNomina.objects.filter(
            liquidacion__empleado=self.empleado, liquidacion__corrida__estado=CorridaNomina.CERRADA,
            liquidacion__corrida__rectificada=False, liquidacion__corrida__periodo__fecha_hasta__gte=desde,
            liquidacion__corrida__periodo__fecha_hasta__lte=hasta)
        if self.ctx.origen is not None:
            cerradas = cerradas.exclude(liquidacion__corrida=self.ctx.origen)
        computable = sum((l.importe for l in cerradas.filter(tipo=ConceptoNomina.HABER, concepto__afecta_base_aguinaldo=True)), CERO)
        pagado = sum((l.importe for l in cerradas.filter(concepto__aplicacion='aguinaldo')), CERO)
        return computable, pagado

    def _aguinaldo(self, computable, pagado, explicacion):
        """Aplica los conceptos de aguinaldo con su regla y descuenta lo ya pagado en el año."""
        self.variables.update({'TOTAL_REMUNERACIONES_ANIO': computable, 'AGUINALDO_PAGADO': pagado})
        for concepto in self.ctx.de_aguinaldo:
            linea = self.por_regla(concepto)
            if linea is None:
                continue
            linea.base = computable
            linea.explicacion = f'{explicacion} {linea.explicacion}'
            if pagado:
                restante = linea.importe - pagado
                self.lineas.remove(linea)
                if restante > 0:
                    nueva = self.agregar(concepto, restante, f'{linea.explicacion}; menos {_gs(pagado)} ya pagado en el año',
                                         'regla', linea.regla_id, linea.regla)
                    if nueva is not None:
                        nueva.base = computable

    def liquidar_aguinaldo(self):
        ctx = self.ctx
        liq = LiquidacionEmpleado(empresa=ctx.empresa, corrida=ctx.corrida, empleado=self.empleado, centro_costo=self.empleado.centro_costo)
        computable, pagado = self._remuneraciones_del_anio(ctx.desde, ctx.hasta)
        meses = CorridaNomina.objects.filter(
            liquidaciones__empleado=self.empleado, estado=CorridaNomina.CERRADA, rectificada=False,
            tipo__in=(CorridaNomina.REGULAR, CorridaNomina.RECTIFICACION), periodo__fecha_hasta__gte=ctx.desde,
            periodo__fecha_hasta__lte=ctx.hasta).values('periodo__fecha_hasta__month').distinct().count()
        activo_desde = max(ctx.desde, self.empleado.fecha_ingreso)
        activo_hasta = min(ctx.hasta, self.empleado.fecha_egreso or ctx.hasta)
        meses_esperados = (activo_hasta.year - activo_desde.year) * 12 + activo_hasta.month - activo_desde.month + 1
        if meses < meses_esperados:
            self.advertencias.append(f'Tiene {meses} de {meses_esperados} meses con nómina cerrada en el año: '
                                     'el aguinaldo toma solo lo liquidado y cerrado.')
        self._aguinaldo(computable, pagado, f'Remuneraciones del año que cuentan para el aguinaldo: {_gs(computable)}.')
        return self._totales(liq)

    def _salario_ya_liquidado(self):
        """¿Una nómina regular cerrada ya le pagó hasta (o después de) la fecha de egreso?"""
        return LiquidacionEmpleado.objects.filter(
            empleado=self.empleado, corrida__estado=CorridaNomina.CERRADA, corrida__rectificada=False,
            corrida__tipo__in=(CorridaNomina.REGULAR, CorridaNomina.RECTIFICACION),
            corrida__periodo__fecha_hasta__gte=self.ctx.final.fecha_egreso).exists()

    def _conceptos_del_egreso(self):
        """Vacaciones no gozadas, preaviso e indemnización (según la causal y las reglas legales) y aguinaldo proporcional."""
        from licencias.models import saldo_vacaciones
        final, empleado = self.ctx.final, self.empleado
        egreso, ingreso = final.fecha_egreso, empleado.fecha_ingreso
        anios = egreso.year - ingreso.year - ((egreso.month, egreso.day) < (ingreso.month, ingreso.day))
        meses_resto = (egreso.year - ingreso.year) * 12 + egreso.month - ingreso.month - anios * 12 - (egreso.day < ingreso.day)
        faltan = [p for p in ('PREAVISO_DIAS', 'CAUSALES_PREAVISO', 'CAUSALES_INDEMNIZACION', 'INDEMNIZACION_FRACCION_MESES')
                  if p not in self.variables]
        if faltan:
            self.errores.append(f'Faltan parámetros legales para el egreso: {", ".join(faltan)}.')
            return
        tabla = self.variables['PREAVISO_DIAS']
        dias_preaviso = next((Decimal(str(t['dias'])) for t in tabla if t['desde_anios'] <= anios
                              and (t.get('hasta_anios') is None or anios < t['hasta_anios'])), CERO)
        corresponde_preaviso = final.causal in self.variables['CAUSALES_PREAVISO'] and not final.preaviso_otorgado
        corresponde_indemnizacion = final.causal in self.variables['CAUSALES_INDEMNIZACION']
        anios_indemnizacion = anios + (1 if meses_resto >= Decimal(self.variables['INDEMNIZACION_FRACCION_MESES']) else 0)
        saldo = saldo_vacaciones(empleado)
        if saldo < 0:
            self.advertencias.append(f'El saldo de vacaciones es negativo ({saldo} días): no se pagan vacaciones.')
            saldo = CERO
        self.variables.update({
            'ANIOS_ANTIGUEDAD': Decimal(anios) + (Decimal(meses_resto) / 12).quantize(Decimal('0.01')),
            'ANIOS_INDEMNIZACION': Decimal(anios_indemnizacion), 'DIAS_PREAVISO': dias_preaviso,
            'CORRESPONDE_PREAVISO': Decimal(int(corresponde_preaviso)), 'CORRESPONDE_INDEMNIZACION': Decimal(int(corresponde_indemnizacion)),
            'SALDO_VACACIONES': saldo,
        })
        self.advertencias.append(
            f'{final.get_causal_display()}, antigüedad {anios} año(s) y {meses_resto} mes(es): preaviso '
            f'{"sí" if corresponde_preaviso else "no"} corresponde, indemnización {"sí" if corresponde_indemnizacion else "no"} '
            '(según las reglas legales vigentes).')
        for concepto in self.ctx.de_final:
            linea = self.por_regla(concepto)
            if linea is not None and concepto.codigo == 'VACACIONES_CAUSADAS':
                linea.cantidad = saldo
        computable, pagado = self._remuneraciones_del_anio(egreso.replace(month=1, day=1), egreso)
        de_esta = sum((l.importe for l in self.lineas if l.tipo == ConceptoNomina.HABER and l.concepto.afecta_base_aguinaldo), CERO)
        self._aguinaldo(computable + de_esta, pagado,
                        f'Aguinaldo proporcional: remuneraciones del año {_gs(computable)} + de esta liquidación {_gs(de_esta)}.')

    def _conceptos_fijos(self):
        ctx = self.ctx
        fijos = ConceptoRecurrente.objects.filter(
            empleado=self.empleado, activo=True, aprobado_en__isnull=False, vigente_desde__lte=ctx.hasta).filter(
            Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=ctx.desde)).select_related('concepto')
        ultimo_dia_mes = monthrange(ctx.hasta.year, ctx.hasta.month)[1]
        # "Una vez por mes": solo en el período que cierra el mes.
        return [f for f in fijos if f.frecuencia != 'mensual' or ctx.hasta.day == ultimo_dia_mes]

    def _fijos_y_novedades(self, fijos, novedades, tipo):
        for fijo in fijos:
            if fijo.concepto.tipo == tipo:
                importe, como = self._importe_fijo(fijo)
                if importe is not None:
                    self.agregar(fijo.concepto, importe, f'Concepto fijo: {como} ({fijo.motivo})', 'concepto_fijo', fijo.pk,
                                 cantidad=fijo.cantidad, tasa=fijo.tasa)
        for novedad in novedades:
            if novedad.concepto.tipo == tipo:
                importe = novedad.importe()
                como = f'{_num(novedad.cantidad)} × {_num(novedad.tasa)}{" %" if novedad.monto is None and novedad.origen == "comision" else ""}' \
                    if novedad.monto is None else _gs(novedad.monto)
                self.agregar(novedad.concepto, importe, f'Novedad: {novedad.descripcion} ({como})', 'novedad', novedad.pk,
                             cantidad=novedad.cantidad, tasa=novedad.tasa)

    def _descuentos_autorizados(self):
        from novedades.models import DescuentoAutorizado
        ctx = self.ctx
        vigentes = DescuentoAutorizado.objects.filter(
            empleado=self.empleado, estado=DescuentoAutorizado.VIGENTE, fecha_desde__lte=ctx.hasta).filter(
            Q(fecha_hasta__isnull=True) | Q(fecha_hasta__gte=ctx.desde)).select_related('concepto').order_by('prioridad')
        for d in vigentes:
            if d.monto_cuota is not None:
                importe, como = d.monto_cuota, f'{_gs(d.monto_cuota)} por liquidación'
            else:
                importe = self.variables['SALARIO_BASE'] * d.porcentaje / 100
                como = f'{_num(d.porcentaje)} % de {_gs(self.variables["SALARIO_BASE"])}'
            if d.monto_total is not None:
                ya = LineaNomina.objects.filter(origen='descuento', origen_id=d.pk, liquidacion__corrida__estado=CorridaNomina.CERRADA,
                                                liquidacion__corrida__rectificada=False)
                if ctx.origen is not None:
                    ya = ya.exclude(liquidacion__corrida=ctx.origen)
                descontado = sum((l.importe for l in ya), CERO)
                restante = d.monto_total - descontado
                if restante <= 0:
                    continue
                if importe > restante:
                    importe, como = restante, f'{como}; queda {_gs(restante)} del total de {_gs(d.monto_total)}'
            self.agregar(d.concepto, importe, f'{d.get_tipo_display()}: {como}', 'descuento', d.pk)


def empleados_del_periodo(empresa, desde, hasta):
    from empleados.models import Empleado
    return Empleado.objects.filter(empresa=empresa, fecha_ingreso__lte=hasta).filter(
        Q(fecha_egreso__isnull=True) | Q(fecha_egreso__gte=desde)).select_related('centro_costo', 'empresa')


def _empleados(ctx):
    """Quiénes entran en la corrida según su tipo."""
    from empleados.models import Empleado
    from nomina.models import LiquidacionFinal
    tipo = ctx.corrida.tipo
    if tipo == 'liquidacion_final':
        return [ctx.final.empleado] if ctx.final else []
    if tipo == 'aguinaldo':
        ids = LineaNomina.objects.filter(
            empresa=ctx.empresa, concepto__afecta_base_aguinaldo=True, liquidacion__corrida__estado=CorridaNomina.CERRADA,
            liquidacion__corrida__rectificada=False, liquidacion__corrida__periodo__fecha_hasta__gte=ctx.desde,
            liquidacion__corrida__periodo__fecha_hasta__lte=ctx.hasta).values_list('liquidacion__empleado', flat=True).distinct()
        return Empleado.objects.filter(pk__in=list(ids)).select_related('centro_costo', 'empresa')
    # Regular o rectificación: quien tiene una liquidación final (no anulada) que egresa en el período o antes cobra en ella.
    con_final = LiquidacionFinal.objects.filter(empresa=ctx.empresa, fecha_egreso__lte=ctx.hasta).exclude(
        corrida__estado=CorridaNomina.ANULADA)
    if ctx.origen is not None:
        con_final = con_final.exclude(empleado__in=ctx.origen.liquidaciones.values('empleado'))
    excluidos = set(con_final.values_list('empleado_id', flat=True))
    if excluidos:
        ctx.avisar(f'{len(excluidos)} empleado(s) con liquidación final cobran en ella, no en esta nómina.')
    return [e for e in empleados_del_periodo(ctx.empresa, ctx.desde, ctx.hasta) if e.pk not in excluidos]


@transaction.atomic
def calcular(corrida, usuario):
    """Calcula (o recalcula) la corrida. Lanza ValueError si no se puede recalcular."""
    corrida = CorridaNomina.objects.select_for_update().select_related('periodo', 'empresa', 'corrida_origen').get(pk=corrida.pk)
    if not corrida.editable:
        raise ValueError('Solo se recalcula una liquidación calculada o revisada (no aprobada ni cerrada).')
    ctx = _Contexto(corrida)
    if not ctx.legales:
        ctx.avisar('No hay parámetros legales vigentes al fin del período (ni siquiera en borrador).')
    corrida.liquidaciones.all().delete()
    totales = defaultdict(lambda: CERO)
    cantidad = 0
    for empleado in _empleados(ctx):
        liq, lineas = _Liquidador(ctx, empleado).liquidar()
        liq.creado_por = liq.modificado_por = usuario
        liq.save()
        for linea in lineas:
            linea.liquidacion = liq
        LineaNomina.objects.bulk_create(lineas)
        cantidad += 1
        for campo in ('bruto', 'descuentos', 'aportes_trabajador', 'neto', 'aportes_patronales', 'otros_costos', 'costo_empleador'):
            totales[campo] += getattr(liq, campo)
    errores = corrida.liquidaciones.filter(estado_calculo=LiquidacionEmpleado.ERROR).count()
    if errores:
        ctx.avisar(f'{errores} empleado(s) con errores: no se puede aprobar hasta corregirlos.')
    corrida.cantidad_empleados = cantidad
    corrida.total_bruto, corrida.total_descuentos = totales['bruto'], totales['descuentos']
    corrida.total_aportes_trabajador, corrida.total_neto = totales['aportes_trabajador'], totales['neto']
    corrida.total_aportes_patronales, corrida.total_otros_costos = totales['aportes_patronales'], totales['otros_costos']
    corrida.total_costo_empleador = totales['costo_empleador']
    corrida.es_simulacion = ctx.simulacion
    corrida.advertencias = ctx.advertencias
    corrida.version_calculo += 1
    corrida.estado = CorridaNomina.CALCULADA
    corrida.revisado_por = None
    corrida.revisado_en = None
    corrida.calculado_por = usuario
    corrida.calculado_en = timezone.now()
    corrida.modificado_por = usuario
    corrida.save()
    return corrida
