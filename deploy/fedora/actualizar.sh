#!/usr/bin/env bash
# ============================================================================
# Koape RR. HH. — Actualizar a la última versión
#
# Se corre con el usuario limitado, en la carpeta del proyecto: baja los cambios
# del repositorio, actualiza dependencias, aplica migraciones y permisos de
# los perfiles, recompila la aplicación y reinicia el servicio.
# Antes de migrar hace un backup de la base (por las dudas).
#
# Uso:
#   cd /home/webuser/HHRR_KOAPE && bash deploy/fedora/actualizar.sh
# ============================================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=comun.sh
source "$RAIZ/deploy/fedora/comun.sh"

[ "$(id -u)" -ne 0 ] || { echo "Corré este script con el usuario limitado, no como root."; exit 1; }
cd "$RAIZ"

echo "==> Backup previo..."
/usr/local/bin/koape-rrhh-backup && echo "✔ Backup hecho en /var/backups/koape-rrhh."

echo "==> Bajando la última versión..."
git pull --ff-only

echo "==> Backend..."
cd "$RAIZ/backend"
venv/bin/pip install -r requirements.txt >/dev/null
venv/bin/python manage.py migrate --noinput
venv/bin/python manage.py restablecer_perfiles
venv/bin/python manage.py collectstatic --noinput >/dev/null

echo "==> Aplicación (frontend)..."
cd "$RAIZ/frontend"
npm ci --no-audit --no-fund >/dev/null
npm run build >/dev/null

echo "==> Reiniciando..."
etiquetar_selinux
sudo systemctl restart "$SERVICIO"
sleep 2
sudo systemctl is-active "$SERVICIO" >/dev/null && echo "✔ Actualizado y funcionando." \
    || { echo "✘ El servicio no arrancó: sudo journalctl -u $SERVICIO -n 50"; exit 1; }
