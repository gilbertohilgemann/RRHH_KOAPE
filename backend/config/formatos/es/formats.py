"""Formato de fechas del sistema (decidido 01/10/2026): siempre dd/mm/aaaa
(y dd/mm/aaaa hh:mm), en el admin y en todo lo que Django muestre. Sin esto,
el castellano de Django muestra "1 de octubre de 2026" en los listados.
Se activa con FORMAT_MODULE_PATH en settings.py."""

DATE_FORMAT = 'd/m/Y'
SHORT_DATE_FORMAT = 'd/m/Y'
DATETIME_FORMAT = 'd/m/Y H:i'
SHORT_DATETIME_FORMAT = 'd/m/Y H:i'
TIME_FORMAT = 'H:i'
MONTH_DAY_FORMAT = 'd/m'
YEAR_MONTH_FORMAT = 'm/Y'

# Lo que se acepta al escribir una fecha en el admin (la primera es la que se muestra).
DATE_INPUT_FORMATS = ['%d/%m/%Y', '%Y-%m-%d']
DATETIME_INPUT_FORMATS = ['%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']

DECIMAL_SEPARATOR = ','
THOUSAND_SEPARATOR = '.'
FIRST_DAY_OF_WEEK = 1  # lunes
