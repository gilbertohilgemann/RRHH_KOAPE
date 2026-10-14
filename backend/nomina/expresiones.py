"""Evaluador seguro de las fórmulas de los conceptos (§4.4: "motor de reglas
seguro; nunca `eval` ni SQL arbitrario").

La fórmula se analiza con `ast` y solo se aceptan:
- números (siempre se calcula con Decimal, sin errores de coma flotante);
- variables en MAYÚSCULAS (parámetros legales y datos de la liquidación, ej.
  `SALARIO_BASE`, `RECARGO_EXTRA_DIURNA`);
- `+ - * / %`, comparaciones (`< <= > >= == !=`), `and`, `or`, `not`;
- `A if CONDICION else B`;
- las funciones `min`, `max`, `abs` y `redondear(x, decimales)`.

Nada más: ni atributos, ni índices, ni textos, ni potencias, ni otras
funciones. Fórmulas de hasta 1.000 caracteres y 200 elementos."""
import ast
import re
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation

MAXIMO_CARACTERES = 1000
MAXIMO_NODOS = 200
VARIABLE = re.compile(r'^[A-Z][A-Z0-9_]*$')


class ErrorFormula(Exception):
    """La fórmula no es válida o no se pudo calcular (mensaje legible)."""


def _redondear(valor, decimales=Decimal('0')):
    return Decimal(valor).quantize(Decimal(1).scaleb(-int(decimales)), rounding=ROUND_HALF_UP)


FUNCIONES = {'min': min, 'max': max, 'abs': abs, 'redondear': _redondear}
_OPERADORES = {
    ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b, ast.Mod: lambda a, b: a % b,
}
_COMPARACIONES = {
    ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
}
_PERMITIDOS = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Constant, ast.Name,
               ast.Call, ast.Load, ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd, *_OPERADORES, *_COMPARACIONES)


def analizar(formula):
    """Valida la fórmula y devuelve (árbol, variables que usa). Lanza ErrorFormula."""
    formula = (formula or '').strip()
    if not formula:
        raise ErrorFormula('La fórmula está vacía.')
    if len(formula) > MAXIMO_CARACTERES:
        raise ErrorFormula(f'La fórmula supera los {MAXIMO_CARACTERES} caracteres.')
    try:
        arbol = ast.parse(formula, mode='eval')
    except SyntaxError as e:
        raise ErrorFormula(f'Fórmula mal escrita (cerca de la posición {e.offset or "?"}): revisá paréntesis y operadores.')
    nodos = list(ast.walk(arbol))
    if len(nodos) > MAXIMO_NODOS:
        raise ErrorFormula('La fórmula es demasiado larga.')
    variables = set()
    for nodo in nodos:
        if not isinstance(nodo, _PERMITIDOS):
            raise ErrorFormula(f'No se permite "{type(nodo).__name__}" en una fórmula.')
        if isinstance(nodo, ast.Constant) and not isinstance(nodo.value, (int, float, bool)):
            raise ErrorFormula('Solo se permiten números (sin textos).')
        if isinstance(nodo, ast.Call):
            if not isinstance(nodo.func, ast.Name) or nodo.func.id not in FUNCIONES:
                raise ErrorFormula(f'Función no permitida. Se puede usar: {", ".join(FUNCIONES)}.')
            if nodo.keywords or not nodo.args:
                raise ErrorFormula(f'{nodo.func.id}(): indicá los valores separados por coma.')
        if isinstance(nodo, ast.Name):
            es_funcion = any(isinstance(p, ast.Call) and p.func is nodo for p in nodos)
            if es_funcion:
                continue
            if not VARIABLE.match(nodo.id):
                raise ErrorFormula(f'"{nodo.id}": las variables van en MAYÚSCULAS (ej. SALARIO_BASE).')
            variables.add(nodo.id)
    return arbol, variables


def _numero(valor, nombre):
    if isinstance(valor, bool):
        return Decimal(int(valor))
    if isinstance(valor, (int, Decimal)):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ErrorFormula(f'{nombre} no es un número ({valor!r}).')


def _evaluar(nodo, variables):
    if isinstance(nodo, ast.Expression):
        return _evaluar(nodo.body, variables)
    if isinstance(nodo, ast.Constant):
        return nodo.value if isinstance(nodo.value, bool) else _numero(nodo.value, 'número')
    if isinstance(nodo, ast.Name):
        if nodo.id not in variables:
            raise ErrorFormula(f'Falta el valor de {nodo.id}.')
        return _numero(variables[nodo.id], nodo.id)
    if isinstance(nodo, ast.BinOp):
        a, b = _evaluar(nodo.left, variables), _evaluar(nodo.right, variables)
        try:
            return _OPERADORES[type(nodo.op)](_numero(a, 'valor'), _numero(b, 'valor'))
        except (DivisionByZero, ZeroDivisionError, InvalidOperation):
            raise ErrorFormula('División por cero.')
    if isinstance(nodo, ast.UnaryOp):
        valor = _evaluar(nodo.operand, variables)
        if isinstance(nodo.op, ast.Not):
            return not valor
        return -_numero(valor, 'valor') if isinstance(nodo.op, ast.USub) else _numero(valor, 'valor')
    if isinstance(nodo, ast.BoolOp):
        if isinstance(nodo.op, ast.And):
            return all(_evaluar(v, variables) for v in nodo.values)
        return any(_evaluar(v, variables) for v in nodo.values)
    if isinstance(nodo, ast.Compare):
        izquierda = _evaluar(nodo.left, variables)
        for operador, siguiente in zip(nodo.ops, nodo.comparators):
            derecha = _evaluar(siguiente, variables)
            if not _COMPARACIONES[type(operador)](izquierda, derecha):
                return False
            izquierda = derecha
        return True
    if isinstance(nodo, ast.IfExp):
        return _evaluar(nodo.body if _evaluar(nodo.test, variables) else nodo.orelse, variables)
    if isinstance(nodo, ast.Call):
        argumentos = [_numero(_evaluar(a, variables), 'valor') for a in nodo.args]
        try:
            return FUNCIONES[nodo.func.id](*argumentos)
        except TypeError:
            raise ErrorFormula(f'{nodo.func.id}(): cantidad de valores incorrecta.')
    raise ErrorFormula('Elemento no permitido.')  # no se llega: analizar() ya lo rechazó


def evaluar(formula, variables):
    """Valor (Decimal o booleano) de la fórmula con esas variables."""
    arbol, _ = analizar(formula)
    return _evaluar(arbol, variables)
