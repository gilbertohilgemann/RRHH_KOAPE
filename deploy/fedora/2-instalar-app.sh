#!/usr/bin/env bash
# ============================================================================
# Koape RR. HH. — 2. Instalar la aplicación
#
# Se corre con el USUARIO LIMITADO (no root), dentro de la carpeta del
# proyecto (ej. /home/webuser/RRHH_KOAPE), después de 1-preparar-servidor.sh:
#
#   - entorno virtual de Python y dependencias;
#   - backend/.env de producción (la base elegida al preparar el servidor:
#     PostgreSQL si existe /etc/koape-rrhh/db.env, si no SQLite; dominio;
#     clave secreta);
#   - tablas, estáticos, usuario admin y permisos de los perfiles;
#   - compilación de la aplicación (frontend) apuntando al dominio;
#   - reinicio del servicio.
#
# Se puede volver a correr sin problema (no pisa un .env ya armado).
#
# Uso:
#   cd /home/webuser/RRHH_KOAPE && bash deploy/fedora/2-instalar-app.sh
# ============================================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=comun.sh
source "$RAIZ/deploy/fedora/comun.sh"

[ "$(id -u)" -ne 0 ] || falla "Corré este script con el usuario limitado, no como root."
[ -r "$DIR_CONF/dominio.env" ] || falla "No encuentro $DIR_CONF/dominio.env: primero hay que correr (como root) deploy/fedora/1-preparar-servidor.sh."
# shellcheck disable=SC1091
source "$DIR_CONF/dominio.env"
URL="https://${DOMINIO}"
[ -n "${IP_ADMIN:-}" ] || falla "Falta IP_ADMIN en $DIR_CONF/dominio.env: volvé a correr (como root) 1-preparar-servidor.sh."
PUERTO_ADMIN="${PUERTO_ADMIN:-8006}"
URL_ADMIN="https://${IP_ADMIN}:${PUERTO_ADMIN}"
if [ -r "$DIR_CONF/db.env" ]; then MOTOR="PostgreSQL"; else MOTOR="SQLite"; fi

# ----------------------------------------------------------------------------
paso "1/5 Backend: entorno virtual y dependencias..."
cd "$RAIZ/backend"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install --upgrade pip >/dev/null
venv/bin/pip install -r requirements.txt >/dev/null
ok "Dependencias de Python instaladas."

# ----------------------------------------------------------------------------
paso "2/5 Configuración de producción (backend/.env)..."
if [ ! -f .env ]; then
    CLAVE="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
    # Clave Fernet de los datos cifrados (cuentas bancarias, códigos fijos): se genera UNA vez y no se cambia
    # nunca. Si se pierde, esos datos no se pueden leer: viaja en el backup completo (backend/.env).
    CIFRADO="$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
    {
        echo "# Generado por deploy/fedora/2-instalar-app.sh — producción."
        echo "DEBUG=False"
        echo "SECRET_KEY=${CLAVE}"
        echo "# NO CAMBIAR NI PERDER: sin esta clave no se leen las cuentas bancarias ni los códigos fijos."
        echo "CLAVE_CIFRADO=${CIFRADO}"
        echo "ALLOWED_HOSTS=${DOMINIO},${IP_ADMIN},localhost,127.0.0.1"
        echo "CSRF_TRUSTED_ORIGINS=${URL},${URL_ADMIN}"
        echo "CORS_ALLOWED_ORIGINS=${URL}"
        echo "URL_APP=${URL}"
        echo "# El admin responde SOLO pedido por estas direcciones (el dominio y ip:puerto); por otra, 404."
        echo "ADMIN_HOSTS=${DOMINIO},${IP_ADMIN}:${PUERTO_ADMIN}"
        echo "# Hasta tener el certificado (3-certificado.sh) queda en False; ese script lo pasa a True."
        echo "SECURE_SSL_REDIRECT=False"
        if [ "$MOTOR" = "PostgreSQL" ]; then
            cat "$DIR_CONF/db.env"
        else
            echo "# Base SQLite (backend/db.sqlite3). Para pasar a PostgreSQL: 4-migrar-a-postgres.sh"
            echo "DB_ENGINE=sqlite"
        fi
    } > .env
    chmod 600 .env
    ok "backend/.env creado (${MOTOR}, ${DOMINIO})."
else
    ok "backend/.env ya existía: no se toca."
    # Instalaciones anteriores al admin en el dominio: se suma el dominio a ADMIN_HOSTS (lo demás no se toca).
    if grep -q '^ADMIN_HOSTS=' .env && ! grep -q "^ADMIN_HOSTS=.*${DOMINIO}" .env; then
        sed -i "s|^ADMIN_HOSTS=|ADMIN_HOSTS=${DOMINIO},|" .env
        ok "Admin habilitado también en https://${DOMINIO}/admin/ (ADMIN_HOSTS)."
    fi
fi
grep -q '^CLAVE_CIFRADO=' .env || falla "backend/.env no tiene CLAVE_CIFRADO: agregala (la misma de siempre si ya hay datos cifrados)."
mkdir -p privado media
chmod 700 privado   # documentos del legajo, fotos e importaciones: solo los entrega la aplicación

# ----------------------------------------------------------------------------
paso "3/5 Base de datos, estáticos, admin y perfiles..."
venv/bin/python manage.py migrate --noinput
venv/bin/python manage.py collectstatic --noinput >/dev/null
venv/bin/python manage.py crear_admin
venv/bin/python manage.py restablecer_perfiles
ok "Base lista."

# ----------------------------------------------------------------------------
paso "4/5 Aplicación (frontend)..."
cd "$RAIZ/frontend"
# La API va en el mismo dominio (/api): lo dice frontend/.env.production, que está en el repositorio.
rm -f .env
npm ci --no-audit --no-fund >/dev/null
npm run build >/dev/null
ok "Aplicación compilada (frontend/dist) para ${URL}."

# ----------------------------------------------------------------------------
paso "5/5 Reiniciando el servicio..."
etiquetar_selinux
sudo systemctl restart "$SERVICIO"
sleep 2
if sudo systemctl is-active "$SERVICIO" >/dev/null; then
    ok "Servicio ${SERVICIO} funcionando."
else
    falla "El servicio no arrancó. Mirá el error con: sudo journalctl -u ${SERVICIO} -n 50"
fi

echo ""
echo "============================================================"
ok "Aplicación instalada."
echo "============================================================"
echo ""
echo "  Aplicación:  http://${DOMINIO}   (https cuando esté el certificado)"
echo "  Admin:       ${URL_ADMIN}/admin/   usuario admin (cambiá la contraseña al entrar)"
echo "               (certificado propio: el navegador avisa la primera vez, se acepta)"
echo ""
echo "  Falta el certificado HTTPS (root): sudo bash ${RAIZ}/deploy/fedora/3-certificado.sh"
echo "  Para actualizar más adelante:      bash ${RAIZ}/deploy/fedora/actualizar.sh"
echo ""
