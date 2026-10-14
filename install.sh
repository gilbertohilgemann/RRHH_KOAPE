#!/usr/bin/env bash
# ============================================================================
# Koape RR. HH. — Instalador para Fedora Cloud
#
# Prepara el servidor: revisa/instala las librerías del sistema que hacen
# falta (pidiendo permiso antes), arma el entorno virtual de Python, instala
# las dependencias del backend y del frontend, y deja el sistema funcionando
# sobre SQLite (simple, sin nada extra que configurar).
#
# PostgreSQL NO es obligatorio acá: una vez que el sistema esté arriba, andá
# a /admin/ → "Migración de Base de Datos" (o corré
# `manage.py migrate_to_postgres`) para pasar a Postgres cuando quieras,
# sin perder los datos que ya cargaste en SQLite.
#
# Se corre con un usuario común (no root): solo los pasos que tocan el
# sistema (dnf, firewall, systemd) usan sudo, y siempre preguntando antes.
#
# Uso:
#   chmod +x install.sh start.sh
#   ./install.sh
# ============================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
SERVICE_NAME="koape-rrhh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}==>${NC} $1"; }
ok()   { echo -e "${GREEN}✔${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✘${NC} $1"; }

ask_yes_no() {
    # $1 = pregunta. Devuelve 0 (sí) o 1 (no). Por defecto: No.
    local answer
    read -r -p "$1 [s/N]: " answer
    [[ "$answer" =~ ^([sS]|[yY])$ ]]
}

port_in_use() {
    # $1 = puerto. Devuelve 0 (verdadero) si algo ya está escuchando ahí.
    if command -v ss >/dev/null 2>&1; then
        ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[.:]$1\$"
    elif command -v netstat >/dev/null 2>&1; then
        netstat -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[.:]$1\$"
    else
        return 1
    fi
}

echo ""
echo "============================================================"
echo "  Koape RR. HH. — Instalación (Fedora Cloud)"
echo "============================================================"
echo ""

if [ "$(id -u)" -eq 0 ]; then
    warn "Estás corriendo el instalador como root. Conviene usar un usuario común:"
    warn "el sistema va a correr con ese usuario, y sudo se pide solo donde hace falta."
    ask_yes_no "¿Continuar igual como root?" || { err "Instalación cancelada."; exit 1; }
fi

if [ -f /etc/os-release ] && ! grep -qi fedora /etc/os-release; then
    warn "No parece ser Fedora — este script usa 'dnf', puede fallar en otras distros."
    ask_yes_no "¿Continuar de todas formas?" || { err "Instalación cancelada."; exit 1; }
fi

# ----------------------------------------------------------------------------
# 1. Revisar qué falta instalar en el sistema
# ----------------------------------------------------------------------------
log "Revisando librerías del sistema..."

declare -A CMD_TO_PKG=(
    [python3]="python3"
    [pip3]="python3-pip"
    [gcc]="gcc python3-devel"
    [node]="nodejs"
    [npm]="nodejs-npm"
)

MISSING_PKGS=()
MISSING_CMDS=()
for cmd in "${!CMD_TO_PKG[@]}"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        MISSING_CMDS+=("$cmd")
        for pkg in ${CMD_TO_PKG[$cmd]}; do
            MISSING_PKGS+=("$pkg")
        done
    fi
done

if [ ${#MISSING_CMDS[@]} -eq 0 ]; then
    ok "Ya está todo lo necesario instalado (python3, pip3, gcc, node, npm)."
else
    warn "Falta instalar: ${MISSING_CMDS[*]}"
    echo "    Paquetes a instalar: $(printf '%s ' "${MISSING_PKGS[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' ')"
    if ask_yes_no "¿Instalar todo lo que falta ahora (sudo dnf install)?"; then
        # shellcheck disable=SC2046
        sudo dnf install -y $(printf '%s\n' "${MISSING_PKGS[@]}" | sort -u)
        ok "Librerías del sistema instaladas."
    else
        err "No se puede continuar sin estas librerías. Instalalas y volvé a correr este script:"
        err "  sudo dnf install -y $(printf '%s ' "${MISSING_PKGS[@]}")"
        exit 1
    fi
fi

# ----------------------------------------------------------------------------
# 1.b PostgreSQL — no hace falta para arrancar (el sistema inicia en SQLite).
#     Se revisa igual para que esté listo cuando se quiera migrar.
# ----------------------------------------------------------------------------
log "Revisando PostgreSQL..."

if command -v psql >/dev/null 2>&1 && rpm -q postgresql-server >/dev/null 2>&1; then
    ok "PostgreSQL ya está instalado."
elif port_in_use 5432; then
    # Algo escucha en el puerto de Postgres aunque el paquete no esté (otro
    # contenedor, instalación manual...). No se toca nada para no interferir.
    ok "Ya hay algo escuchando en el puerto 5432 (probablemente PostgreSQL)."
    warn "No instalo nada para no interferir con lo que ya está corriendo."
else
    warn "PostgreSQL no está instalado ni corriendo. No hace falta para arrancar (el sistema usa SQLite),"
    warn "pero lo vas a necesitar si más adelante migrás a Postgres desde el panel de admin."
    if ask_yes_no "¿Instalar y dejar listo PostgreSQL ahora (sudo)?"; then
        sudo dnf install -y postgresql-server postgresql
        if [ -z "$(sudo ls -A /var/lib/pgsql/data 2>/dev/null)" ]; then
            sudo postgresql-setup --initdb
        fi
        sudo systemctl enable --now postgresql
        ok "PostgreSQL instalado, inicializado y corriendo."
        echo "    (La base del sistema se crea después, desde el panel 'Migración de Base de Datos'.)"
    else
        warn "OK, lo instalás más tarde (sudo dnf install postgresql-server postgresql)."
    fi
fi

echo ""
echo "  Python:  $(python3 --version)"
echo "  Node:    $(node --version)"
echo "  npm:     $(npm --version)"
echo ""

# ----------------------------------------------------------------------------
# 2. Backend (Django)
# ----------------------------------------------------------------------------
log "Configurando el backend..."
cd "$BACKEND_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    ok "Entorno virtual creado."
else
    ok "Entorno virtual ya existía."
fi

# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt
ok "Dependencias de Python instaladas."

# Pide el dominio/IP público y lo aplica a ALLOWED_HOSTS + CORS_ALLOWED_ORIGINS
# (y regenera SECRET_KEY solo si todavía tiene el valor de ejemplo). Sirve
# tanto para un .env recién creado como para uno restaurado de un backup.
configure_backend_host() {
    if grep -q "^SECRET_KEY=cambia-esta-clave" .env 2>/dev/null; then
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
        sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" .env
    fi

    echo ""
    read -r -p "Dominio o IP pública del servidor (ej: rrhh.miempresa.com o 1.2.3.4), separá varios con coma: " ALLOWED_HOSTS
    ALLOWED_HOSTS=${ALLOWED_HOSTS:-localhost,127.0.0.1}
    sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=$ALLOWED_HOSTS|" .env

    # Frontend (5204) y backend (8004) quedan en puertos distintos => son
    # orígenes distintos para el navegador. Sin esto, la app carga pero
    # todas las llamadas a la API fallan por CORS.
    CORS_ORIGINS=""
    IFS=',' read -ra HOSTS_ARR <<< "$ALLOWED_HOSTS"
    for h in "${HOSTS_ARR[@]}"; do
        h_trimmed=$(echo "$h" | xargs)
        [ -z "$h_trimmed" ] && continue
        [ "$h_trimmed" = "localhost" ] && continue
        [ "$h_trimmed" = "127.0.0.1" ] && continue
        CORS_ORIGINS="${CORS_ORIGINS}http://${h_trimmed}:5204,https://${h_trimmed}:5204,https://${h_trimmed},"
    done
    CORS_ORIGINS="${CORS_ORIGINS%,}"
    if [ -n "$CORS_ORIGINS" ]; then
        if grep -q "^CORS_ALLOWED_ORIGINS=" .env; then
            sed -i "s|^CORS_ALLOWED_ORIGINS=.*|CORS_ALLOWED_ORIGINS=$CORS_ORIGINS|" .env
        elif grep -q "^# CORS_ALLOWED_ORIGINS=" .env; then
            sed -i "s|^# CORS_ALLOWED_ORIGINS=.*|CORS_ALLOWED_ORIGINS=$CORS_ORIGINS|" .env
        else
            echo "CORS_ALLOWED_ORIGINS=$CORS_ORIGINS" >> .env
        fi
        ok "CORS_ALLOWED_ORIGINS configurado para: $CORS_ORIGINS"
    fi

    if ask_yes_no "¿Es un servidor de producción (DEBUG=False)?"; then
        sed -i "s|^DEBUG=.*|DEBUG=False|" .env
        if ! grep -q "^SECURE_SSL_REDIRECT=" .env && ask_yes_no "¿Todavía NO tenés HTTPS (certificado) configurado?"; then
            echo "SECURE_SSL_REDIRECT=False" >> .env
            warn "SECURE_SSL_REDIRECT=False: sacalo del .env apenas tengas el certificado."
        fi
    fi
}

if [ ! -f ".env" ]; then
    cp .env.example .env
    configure_backend_host
    if ! grep -q "^DB_ENGINE=" .env; then
        echo "DB_ENGINE=sqlite" >> .env
    fi
    ok "Archivo backend/.env creado."
else
    warn "backend/.env ya existía (por ejemplo, si restauraste un backup, trae el dominio/IP del servidor viejo)."
    if ask_yes_no "¿Actualizar dominio/IP (ALLOWED_HOSTS y CORS_ALLOWED_ORIGINS) para este servidor?"; then
        configure_backend_host
    else
        ok "backend/.env sin cambios."
    fi
fi

# Clave con la que se cifran los números de cuenta bancaria. Se genera UNA
# sola vez: si ya existe nunca se toca (cambiarla haría ilegibles los datos
# ya cifrados). Viaja en el backup junto con .env.
if ! grep -q "^CLAVE_CIFRADO=" .env; then
    CLAVE_CIFRADO=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    echo "CLAVE_CIFRADO=$CLAVE_CIFRADO" >> .env
    ok "Clave de cifrado generada (backend/.env)."
fi

python manage.py migrate --noinput
ok "Base de datos lista (tablas creadas)."

python manage.py collectstatic --noinput >/dev/null
ok "Archivos estáticos del admin recolectados."

# Usuario admin fijo (mismo en Linux y Windows) para no perder nunca el
# acceso al panel. Idempotente: lo crea o le resetea la contraseña.
python manage.py crear_admin

deactivate

# ----------------------------------------------------------------------------
# 3. Frontend (React)
# ----------------------------------------------------------------------------
log "Configurando el frontend..."
cd "$FRONTEND_DIR"

npm install
ok "Dependencias de Node instaladas."

configure_frontend_api_url() {
    echo ""
    echo "URL pública de la API del backend. Dejala vacía (Enter) si el backend queda en el"
    echo "mismo host, puerto 8004: la app la arma sola. Completala solo si va en otro host/puerto."
    read -r -p "VITE_API_URL (ej: https://api.miempresa.com/api): " API_URL
    sed -i "s|^VITE_API_URL=.*|VITE_API_URL=${API_URL}|" .env
}

if [ ! -f ".env" ]; then
    cp .env.example .env
    configure_frontend_api_url
    ok "Archivo frontend/.env creado."
else
    warn "frontend/.env ya existía."
    if ask_yes_no "¿Actualizar VITE_API_URL para este servidor?"; then
        configure_frontend_api_url
    else
        ok "frontend/.env sin cambios."
    fi
fi

npm run build
ok "Build de producción del frontend generado (frontend/dist)."

# ----------------------------------------------------------------------------
# 4. Firewall (opcional)
# ----------------------------------------------------------------------------
if command -v firewall-cmd >/dev/null 2>&1; then
    if ask_yes_no "¿Abrir los puertos 8004 (backend) y 5204 (frontend) en el firewall (sudo)?"; then
        sudo firewall-cmd --permanent --add-port=8004/tcp
        sudo firewall-cmd --permanent --add-port=5204/tcp
        sudo firewall-cmd --reload
        ok "Puertos abiertos."
    fi
fi

# ----------------------------------------------------------------------------
# 5. Arranque automático al reiniciar el servidor (opcional)
# ----------------------------------------------------------------------------
if command -v systemctl >/dev/null 2>&1; then
    if ask_yes_no "¿Querés que el sistema se active automáticamente al reiniciar el servidor (sudo)?"; then
        SERVICE_USER="$(whoami)"
        SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

        sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Koape RR. HH.
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=$SERVICE_USER
WorkingDirectory=$PROJECT_ROOT
ExecStart=$PROJECT_ROOT/start.sh start
ExecStop=$PROJECT_ROOT/start.sh stop

[Install]
WantedBy=multi-user.target
EOF

        sudo systemctl daemon-reload
        sudo systemctl enable "${SERVICE_NAME}.service"
        ok "Servicio '${SERVICE_NAME}' creado y habilitado — se levanta solo en cada reinicio."
        echo "    Para controlarlo a mano: sudo systemctl [start|stop|status] ${SERVICE_NAME}"
    else
        warn "OK, después de cada reinicio vas a tener que correr ./start.sh a mano."
    fi
fi

echo ""
echo "============================================================"
ok "Instalación completa."
echo "============================================================"
echo ""
echo "  Usuario admin: admin"
echo "  Contraseña:    Admin*2026   (cambiala desde /admin/ apenas entres)"
echo ""
echo "  Base de datos actual: SQLite"
echo "  Para pasar a PostgreSQL más adelante: /admin/ → 'Migración de Base de Datos', o:"
echo "    backend/venv/bin/python backend/manage.py migrate_to_postgres --help"
echo ""
echo "  Para levantar el sistema: ./start.sh"
echo ""
