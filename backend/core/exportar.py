"""Exportación de tablas a CSV o XLSX, para reportes y planillas.

Los textos que empiezan con = + - @ (o tabulador) se escapan con un apóstrofo
para que Excel no los tome como fórmulas (§12: "proteger CSV injection"). Los
números se exportan como números."""
import csv
import io
from datetime import date, datetime
from decimal import Decimal

from django.http import HttpResponse


def seguro(valor):
    if valor is None:
        return ''
    if isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
        return valor
    if isinstance(valor, datetime):
        return valor.strftime('%d/%m/%Y %H:%M')
    if isinstance(valor, date):
        return valor.strftime('%d/%m/%Y')
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    texto = str(valor)
    return "'" + texto if texto[:1] in ('=', '+', '-', '@', '\t', '\r') else texto


def tabla(encabezado, filas, formato='csv', titulo='Datos'):
    """(contenido, tipo MIME, extensión)."""
    if formato == 'xlsx':
        from openpyxl import Workbook
        libro = Workbook()
        hoja = libro.active
        hoja.title = titulo[:31]
        hoja.append(list(encabezado))
        for fila in filas:
            hoja.append([float(v) if isinstance(v, Decimal) else v for v in map(seguro, fila)])
        salida = io.BytesIO()
        libro.save(salida)
        return salida.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx'
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=';')
    escritor.writerow(encabezado)
    for fila in filas:
        escritor.writerow([str(v).replace('.', ',') if isinstance(v, (Decimal, float)) else v for v in map(seguro, fila)])
    return ('﻿' + salida.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8', 'csv'


def respuesta(encabezado, filas, formato, nombre, titulo='Datos'):
    contenido, tipo, extension = tabla(encabezado, filas, formato, titulo)
    resp = HttpResponse(contenido, content_type=tipo)
    resp['Content-Disposition'] = f'attachment; filename="{nombre}.{extension}"'
    return resp
