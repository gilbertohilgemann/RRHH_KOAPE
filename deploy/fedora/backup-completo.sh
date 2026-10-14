#!/usr/bin/env bash
# ============================================================================
# Koape RR. HH. — Backup COMPLETO del servidor
#
# Se corre como root. Arma un solo archivo con todo lo necesario para
# reconstruir la instalación en otro servidor:
#   - el proyecto (código, .env, fotos privadas, logos), sin lo que se
#     regenera solo (venv, node_modules, dist, staticfiles, __pycache__) ni el
#     repositorio (.git);
#   - la base: copia consistente de SQLite (aunque el sistema esté
#     funcionando) o pg_dump si ya usa PostgreSQL;
#   - la configuración del servidor: /etc/koape-rrhh, nginx
#     (koape-rrhh*.conf), el servicio systemd, el backup diario, la regla de
#     sudo y el certificado propio del admin.
# Queda en /var/backups/koape-rrhh/completo_AAAA-MM-DD_HHMM.tar.gz, legible
# solo por root (adentro van claves: .env, db.env, certificado).
#
# Uso:
#   bash /home/webuser/RRHH_KOAPE/deploy/fedora/backup-completo.sh
# ============================================================================
set -euo pipefail
# shellcheck source=comun.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun.sh"

[ "$(id -u)" -eq 0 ] || falla "Este script se corre como root: bash $0"
FECHA="$(date +%Y-%m-%d_%H%M)"
DESTINO="$DIR_BACKUP/completo_${FECHA}.tar.gz"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$DIR_BACKUP" "$TMP/base" "$TMP/servidor"

paso "1/3 Base de datos..."
if grep -q '^DB_ENGINE=postgres' "$DIR_APP/backend/.env" 2>/dev/null; then
    set -a; source "$DIR_CONF/db.env"; set +a
    PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -Fc "$DB_NAME" > "$TMP/base/base.dump"
    ok "PostgreSQL: pg_dump de ${DB_NAME}."
elif [ -f "$DIR_APP/backend/db.sqlite3" ]; then
    # .backup hace una copia consistente aunque el sistema la esté usando.
    sqlite3 "$DIR_APP/backend/db.sqlite3" ".backup '$TMP/base/db.sqlite3'"
    ok "SQLite: copia consistente de db.sqlite3."
else
    aviso "No encontré la base (ni PostgreSQL en .env ni db.sqlite3)."
fi

paso "2/3 Configuración del servidor..."
for f in "$DIR_CONF" /etc/nginx/conf.d/${SERVICIO}*.conf /etc/systemd/system/${SERVICIO}*.service \
         /etc/systemd/system/${SERVICIO}*.timer /usr/local/bin/koape-rrhh-backup /etc/sudoers.d/${SERVICIO} \
         /etc/pki/tls/certs/${SERVICIO}-admin.crt /etc/pki/tls/private/${SERVICIO}-admin.key; do
    [ -e "$f" ] && cp -a --parents "$f" "$TMP/servidor/"
done
ok "Configuración copiada."

paso "3/3 Armando el archivo..."
tar -czf "$DESTINO" \
    --exclude='backend/venv' --exclude='frontend/node_modules' --exclude='frontend/dist' \
    --exclude='backend/staticfiles' --exclude='__pycache__' --exclude='.git' --exclude='.github' \
    --exclude='backend/db.sqlite3' --exclude='.run' --exclude='logs' \
    -C "$(dirname "$DIR_APP")" "$(basename "$DIR_APP")" \
    -C "$TMP" base servidor
chmod 600 "$DESTINO"
ok "Backup completo: $DESTINO ($(du -h "$DESTINO" | cut -f1))."
echo ""
echo "  Para guardarlo fuera del servidor, desde tu PC:"
echo "    scp root@<ip-del-servidor>:$DESTINO ."
echo ""
