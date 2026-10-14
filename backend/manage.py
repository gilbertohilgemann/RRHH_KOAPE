#!/usr/bin/env python
"""Comandos de administración de Django (migrate, test, restablecer_perfiles…)."""
import os
import sys


def main():
    """Ejecuta el comando de administración indicado."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            'No se pudo importar Django. ¿Está instalado y disponible en el PYTHONPATH? '
            '¿Se activó el entorno virtual (venv)?'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
