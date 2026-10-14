#!/usr/bin/env bash
# ============================================================================
# Koape RR. HH. — 4. Pasar de SQLite a PostgreSQL
#
# Se corre como root, en un servidor que ya tiene PostgreSQL funcionando
# (puede ser compartido con otras aplicaciones: este script NO toca
# pg_hba.conf, ni la configuración de PostgreSQL, ni otras bases).
# Reescrito el 02/10/2026 para el VPS, donde PostgreSQL pide contraseña
# también al usuario postgres.
#
#   1. backup completo (backup-completo.sh);
#   2. pide usuario y contraseña del administrador de PostgreSQL (se escriben
#      acá, no se muestran ni se guardan) y prueba la conexión;
#   3. crea el usuario y la base de la aplicación (koape_rrhh) con una
#      clave aleatoria, que queda en /etc/koape-rrhh/db.env;
#   4. detiene el sistema, crea las tablas, copia todos los datos y VERIFICA
#      que la copia sea igual (cantidades por tabla y permisos de los grupos);
#   5. cambia backend/.env a PostgreSQL (el SQLite queda como
#      db.sqlite3.antes-de-postgres);
#   6. inicia el sistema y comprueba el stock y que responda.
# Si algo falla antes del paso 5, el sistema sigue con SQLite, sin cambios.
#
# Uso:
#   bash /home/webuser/RRHH_KOAPE/deploy/fedora/4-migrar-a-postgres.sh
# ============================================================================
set -euo pipefail
# shellcheck source=comun.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun.sh"

[ "$(id -u)" -eq 0 ] || falla "Este script se corre como root: bash $0"
[ -r "$DIR_CONF/dominio.env" ] || falla "No encuentro $DIR_CONF/dominio.env: ¿se preparó el servidor con 1-preparar-servidor.sh?"
# shellcheck disable=SC1091
source "$DIR_CONF/dominio.env"
ENV_APP="$DIR_APP/backend/.env"
[ -f "$ENV_APP" ] || falla "No encuentro $ENV_APP: primero hay que instalar la aplicación (2-instalar-app.sh)."
if grep -q '^DB_ENGINE=postgres' "$ENV_APP"; then
    ok "La aplicación ya usa PostgreSQL: no hay nada que migrar."
    exit 0
fi
[ -f "$DIR_APP/backend/db.sqlite3" ] || falla "No encuentro la base SQLite ($DIR_APP/backend/db.sqlite3)."
command -v psql >/dev/null || falla "No está psql (cliente de PostgreSQL). Instalalo con: dnf install -y postgresql"

como_usuario() { sudo -u "$USUARIO" bash -c "cd '$DIR_APP/backend' && $1"; }
PG_HOST=127.0.0.1
PG_PORT=5432

echo ""
echo "  Se van a pasar TODOS los datos de SQLite a PostgreSQL ($PG_HOST:$PG_PORT),"
echo "  en una base nueva '${BASE}' con su propio usuario '${ROL_BD}'."
echo "  No se toca ninguna otra base ni la configuración de PostgreSQL."
echo "  El sistema se detiene unos minutos durante la copia."
preguntar_si "  ¿Continuar?" n || { echo "Cancelado."; exit 0; }

# ----------------------------------------------------------------------------
paso "1/6 Backup completo..."
bash "$DIR_APP/deploy/fedora/backup-completo.sh"

# ----------------------------------------------------------------------------
paso "2/6 Conexión a PostgreSQL como administrador..."
read -r -p "  Usuario administrador de PostgreSQL [postgres]: " PG_ADMIN
PG_ADMIN="${PG_ADMIN:-postgres}"
read -r -s -p "  Contraseña de ${PG_ADMIN} (no se muestra ni se guarda): " PG_ADMIN_CLAVE
echo ""
psql_admin() { PGPASSWORD="$PG_ADMIN_CLAVE" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_ADMIN" -v ON_ERROR_STOP=1 -tAq "$@"; }
psql_admin -d postgres -c 'SELECT 1' >/dev/null \
    || falla "No se pudo entrar a PostgreSQL como ${PG_ADMIN} por ${PG_HOST}. Revisá la contraseña. No se cambió nada."
ok "Conectado como ${PG_ADMIN}."

# ----------------------------------------------------------------------------
paso "3/6 Usuario y base de la aplicación..."
if [ "$(psql_admin -d postgres -c "SELECT 1 FROM pg_database WHERE datname='${BASE}'")" = "1" ]; then
    TABLAS="$(psql_admin -d "$BASE" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
    [ "$TABLAS" = "0" ] || falla "La base '${BASE}' ya existe y tiene ${TABLAS} tablas: no se pisa. No se cambió nada."
fi
CLAVE_APP="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
if [ "$(psql_admin -d postgres -c "SELECT 1 FROM pg_roles WHERE rolname='${ROL_BD}'")" = "1" ]; then
    psql_admin -d postgres -c "ALTER ROLE ${ROL_BD} WITH LOGIN PASSWORD '${CLAVE_APP}'"
else
    psql_admin -d postgres -c "CREATE ROLE ${ROL_BD} WITH LOGIN PASSWORD '${CLAVE_APP}'"
fi
if [ "$(psql_admin -d postgres -c "SELECT 1 FROM pg_database WHERE datname='${BASE}'")" != "1" ]; then
    psql_admin -d postgres -c "CREATE DATABASE ${BASE} OWNER ${ROL_BD} ENCODING 'UTF8'"
fi
unset PG_ADMIN_CLAVE
# La aplicación tiene que poder entrar con su usuario y clave por TCP.
PGPASSWORD="$CLAVE_APP" psql -h "$PG_HOST" -p "$PG_PORT" -U "$ROL_BD" -d "$BASE" -tAq -c 'SELECT 1' >/dev/null \
    || falla "El usuario ${ROL_BD} no puede entrar con clave por ${PG_HOST} (revisá las reglas 'host' de pg_hba.conf para 127.0.0.1: tienen que ser scram-sha-256 o md5). El sistema sigue con SQLite."
cat > "$DIR_CONF/db.env" <<EOF
DB_ENGINE=postgres
DB_NAME=${BASE}
DB_USER=${ROL_BD}
DB_PASSWORD=${CLAVE_APP}
DB_HOST=${PG_HOST}
DB_PORT=${PG_PORT}
EOF
chown root:"$USUARIO" "$DIR_CONF/db.env"
chmod 640 "$DIR_CONF/db.env"
ok "Base '${BASE}' y usuario '${ROL_BD}' listos (clave en $DIR_CONF/db.env)."

# ----------------------------------------------------------------------------
paso "4/6 Deteniendo el sistema, copiando y verificando los datos..."
systemctl stop "$SERVICIO"
if ! como_usuario "venv/bin/python manage.py migrate_to_postgres --host '$PG_HOST' --port '$PG_PORT' --dbname '$BASE' --user '$ROL_BD' --password '$CLAVE_APP'"; then
    systemctl start "$SERVICIO"
    falla "La copia falló o no coincide: el sistema sigue con SQLite, sin cambios. Revisá el mensaje de arriba."
fi
ok "Datos copiados a PostgreSQL y verificados."

# ----------------------------------------------------------------------------
paso "5/6 Cambiando la configuración a PostgreSQL..."
# Como el usuario de la aplicación, para que el .env siga siendo suyo.
como_usuario "sed -i -E '/^(# *)?(DB_ENGINE|DB_NAME|DB_USER|DB_PASSWORD|DB_HOST|DB_PORT)=/d; /^# Base SQLite/d' .env && cat '$DIR_CONF/db.env' >> .env && mv db.sqlite3 db.sqlite3.antes-de-postgres"
ok "backend/.env usa PostgreSQL (el SQLite quedó como db.sqlite3.antes-de-postgres)."

# ----------------------------------------------------------------------------
paso "6/6 Iniciando y comprobando..."
systemctl start "$SERVICIO"
sleep 3
systemctl is-active --quiet "$SERVICIO" || falla "El sistema no arrancó: journalctl -u $SERVICIO -n 50 (para volver a SQLite, ver abajo)."
como_usuario "venv/bin/python manage.py verificar_stock"
CODIGO="$(curl -sk -o /dev/null -w '%{http_code}' "https://${IP_ADMIN}:${PUERTO_ADMIN}/admin/login/" || true)"
[ "$CODIGO" = "200" ] && ok "El admin responde (200)." || aviso "El admin respondió ${CODIGO}: revisá journalctl -u $SERVICIO -n 50."
ok "Funcionando con PostgreSQL."
echo ""
echo "  Para volver a SQLite si algo no anda (como root):"
echo "    systemctl stop $SERVICIO"
echo "    sudo -u $USUARIO mv $DIR_APP/backend/db.sqlite3.antes-de-postgres $DIR_APP/backend/db.sqlite3"
echo "    sudo -u $USUARIO sed -i 's/^DB_ENGINE=postgres/DB_ENGINE=sqlite/' $ENV_APP"
echo "    systemctl start $SERVICIO"
echo "  (lo cargado después de migrar queda solo en PostgreSQL)."
echo ""
