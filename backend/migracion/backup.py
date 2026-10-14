"""Arma un backup completo del proyecto (código + datos) en un .zip descargable.

Incluye todo el código fuente (backend y frontend), los archivos subidos
(media), la base SQLite tal cual esté, y un volcado SQL listo para restaurar
si el sistema está corriendo sobre PostgreSQL.

Deja afuera cualquier rastro de con qué repositorio (GitHub u otro) está
vinculada la instalación: la carpeta `.git` completa (con el remoto, historial
y credenciales que pueda tener guardadas) y los archivos sueltos de control de
versiones (`.gitignore`, `.gitattributes`, `.gitmodules`, `.github/`). Ver
EXCLUDED_DIR_NAMES / EXCLUDED_FILE_NAMES más abajo.
"""
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings

# Carpetas que no tiene sentido respaldar: se regeneran solas (dependencias
# instaladas, cachés, builds, PIDs/logs de los scripts de arranque) o son
# control de versiones.
EXCLUDED_DIR_NAMES = {
    'venv', 'node_modules', '.git', '__pycache__',
    'dist', '.vite', 'staticfiles', '.github',
    '.run', 'logs',
}

# Archivos sueltos que, aunque no son la carpeta .git, siguen siendo datos de
# control de versiones: no deben viajar en el backup, sea cual sea el
# repositorio que se use (GitHub, GitLab u otro).
EXCLUDED_FILE_NAMES = {'.gitignore', '.gitattributes', '.gitmodules'}

PREFIJO = 'koape-rrhh-backup'


def _project_root():
    # BASE_DIR es la carpeta "backend"; el proyecto completo es su padre.
    return Path(settings.BASE_DIR).parent


def _find_pg_dump():
    """Busca el ejecutable pg_dump: primero en el PATH (así funciona tal cual
    en Linux/el VPS), y si no, en las rutas típicas de instalación en Windows."""
    found = shutil.which('pg_dump')
    if found:
        return found

    for candidate in sorted(Path('C:/Program Files/PostgreSQL').glob('*/bin/pg_dump.exe'), reverse=True):
        return str(candidate)

    return None


def _add_directory_to_zip(zf, source_dir, arc_prefix):
    for path in source_dir.rglob('*'):
        if path.is_dir():
            continue
        if path.name in EXCLUDED_FILE_NAMES:
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.relative_to(source_dir).parts):
            continue
        arcname = f'{arc_prefix}/{path.relative_to(source_dir).as_posix()}'
        zf.write(path, arcname)


def build_backup_zip(log):
    """Crea el .zip en un archivo temporal y devuelve su ruta.
    Quien llama es responsable de borrarlo después de enviarlo."""
    root = _project_root()
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')

    fd, zip_path = tempfile.mkstemp(prefix=f'{PREFIJO}-{timestamp}-', suffix='.zip')
    os.close(fd)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        log('Comprimiendo el código del proyecto...')
        _add_directory_to_zip(zf, root, PREFIJO)

        from django.db import connection
        if connection.vendor == 'postgresql':
            log('Generando el volcado (dump) de PostgreSQL...')
            pg_dump = _find_pg_dump()
            if not pg_dump:
                log('⚠ No se encontró pg_dump: el backup no incluye el volcado SQL de Postgres.')
            else:
                db = connection.settings_dict
                dump_fd, dump_path = tempfile.mkstemp(suffix='.sql')
                os.close(dump_fd)
                try:
                    env = {**os.environ, 'PGPASSWORD': db['PASSWORD']}
                    result = subprocess.run(
                        [
                            pg_dump,
                            '-h', db['HOST'] or 'localhost',
                            '-p', str(db['PORT'] or '5432'),
                            '-U', db['USER'],
                            '-d', db['NAME'],
                            '-f', dump_path,
                            '--no-owner', '--no-privileges',
                        ],
                        env=env, capture_output=True, text=True, timeout=300,
                    )
                    if result.returncode == 0:
                        zf.write(dump_path, 'postgres_dump.sql')
                        log('Volcado de PostgreSQL incluido en el backup.')
                    else:
                        log(f'⚠ pg_dump falló: {result.stderr.strip()[:300]}')
                finally:
                    os.unlink(dump_path)

    return zip_path
