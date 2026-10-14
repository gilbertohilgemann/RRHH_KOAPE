#!/usr/bin/env bash
# ============================================================================
# Koape RR. HH. — funciones y valores comunes de los scripts de
# deploy/fedora. No se corre solo: lo cargan los demás con "source".
# ============================================================================

# La carpeta del proyecto se calcula sola (donde se clonó el repositorio, ej.
# /home/webuser/RRHH_KOAPE): nunca una ruta escrita a mano.
DIR_APP="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIR_CONF="/etc/koape-rrhh"
DIR_BACKUP="/var/backups/koape-rrhh"
SERVICIO="koape-rrhh"
BASE="koape_rrhh"
ROL_BD="koape_rrhh"
# gunicorn escucha solo por dentro del servidor; nginx le pasa los pedidos.
PUERTO_GUNICORN=8014
# El admin de la plataforma se publica SOLO en https://<ip>:PUERTO_ADMIN/admin/,
# nunca en el dominio (pedido del cliente, 02/10/2026).
PUERTO_ADMIN=8006

VERDE='\033[0;32m'; AMARILLO='\033[1;33m'; AZUL='\033[0;34m'; ROJO='\033[0;31m'; NORMAL='\033[0m'
paso()  { echo -e "${AZUL}==>${NORMAL} $1"; }
ok()    { echo -e "${VERDE}✔${NORMAL} $1"; }
aviso() { echo -e "${AMARILLO}⚠${NORMAL} $1"; }
falla() { echo -e "${ROJO}✘${NORMAL} $1"; exit 1; }

# preguntar_si "¿Pregunta?" s|n  → devuelve 0 si la respuesta es sí.
# El segundo parámetro es la respuesta por defecto (Enter).
preguntar_si() {
    local pregunta="$1" defecto="${2:-n}" opciones respuesta
    [ "$defecto" = "s" ] && opciones="[S/n]" || opciones="[s/N]"
    read -r -p "$pregunta $opciones: " respuesta
    respuesta="${respuesta:-$defecto}"
    [[ "$respuesta" =~ ^[sSyY] ]]
}

# etiquetar_selinux: vuelve a aplicar las etiquetas de SELinux a la carpeta
# del proyecto. Hace falta después de cada compilación o instalación: los
# archivos nuevos heredan la etiqueta de la carpeta de usuario y nginx no
# podría leerlos (ni systemd ejecutar gunicorn). Las reglas las deja
# 1-preparar-servidor.sh.
etiquetar_selinux() {
    command -v restorecon >/dev/null || return 0
    command -v getenforce >/dev/null && [ "$(getenforce)" = "Disabled" ] && return 0
    restorecon -R "$DIR_APP" 2>/dev/null \
        || aviso "No se pudieron aplicar las etiquetas de SELinux. Como root: restorecon -R $DIR_APP"
}

# puerto_libre_o_nuestro <puerto> <proceso-esperado>
# Regla de no interferencia: si el puerto ya lo usa OTRO programa, se frena
# con un mensaje claro (nunca se lo pisa ni se lo mata). Si lo usa el proceso
# esperado (ej. nginx o gunicorn de una instalación anterior), sigue.
puerto_libre_o_nuestro() {
    local puerto="$1" esperado="$2" uso
    uso="$(ss -ltnpH "sport = :${puerto}" 2>/dev/null || true)"
    if [ -z "$uso" ]; then
        ok "Puerto ${puerto} libre."
    elif grep -q "\"${esperado}\"" <<<"$uso"; then
        ok "Puerto ${puerto} ya lo usa ${esperado} (instalación anterior): se reutiliza."
    else
        falla "El puerto ${puerto} lo está usando otro programa:
${uso}
No se toca. Liberalo o cambiá el puerto en deploy/fedora/comun.sh y volvé a correr."
    fi
}

# Instala e inicializa PostgreSQL y crea la base y el usuario de la
# aplicación con una clave aleatoria, que queda en $DIR_CONF/db.env (legible
# solo por root y el usuario de la aplicación). Se corre como root.
preparar_postgres() {
    local usuario="$1"
    dnf install -y postgresql-server postgresql >/dev/null
    if [ -z "$(ls -A /var/lib/pgsql/data 2>/dev/null)" ]; then
        postgresql-setup --initdb >/dev/null
    fi
    # Conexiones por 127.0.0.1 con usuario y clave (Fedora trae "ident", que
    # no sirve para la aplicación). Las locales por socket quedan como estaban.
    sed -i -E 's/^(host\s+all\s+all\s+(127\.0\.0\.1\/32|::1\/128)\s+)ident/\1scram-sha-256/' /var/lib/pgsql/data/pg_hba.conf
    systemctl enable --now postgresql >/dev/null
    systemctl reload postgresql

    mkdir -p "$DIR_CONF"
    if [ -f "$DIR_CONF/db.env" ]; then
        ok "PostgreSQL ya estaba configurado ($DIR_CONF/db.env)."
        return
    fi
    local clave
    clave="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    su - postgres -c "psql -v ON_ERROR_STOP=1 -q" <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${ROL_BD}') THEN
    CREATE ROLE ${ROL_BD} LOGIN PASSWORD '${clave}';
  ELSE
    ALTER ROLE ${ROL_BD} WITH LOGIN PASSWORD '${clave}';
  END IF;
END \$\$;
SQL
    su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='${BASE}'\"" | grep -q 1 \
        || su - postgres -c "createdb -O ${ROL_BD} ${BASE}"
    cat > "$DIR_CONF/db.env" <<EOF
DB_ENGINE=postgres
DB_NAME=${BASE}
DB_USER=${ROL_BD}
DB_PASSWORD=${clave}
DB_HOST=127.0.0.1
DB_PORT=5432
EOF
    chown root:"$usuario" "$DIR_CONF/db.env"
    chmod 640 "$DIR_CONF/db.env"
    ok "PostgreSQL listo: base '${BASE}' y usuario '${ROL_BD}' (clave en $DIR_CONF/db.env)."
}
