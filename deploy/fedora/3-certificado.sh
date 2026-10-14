#!/usr/bin/env bash
# ============================================================================
# Koape RR. HH. — 3. Certificado HTTPS (Let's Encrypt)
#
# Se corre como root, cuando el dominio ya apunta a este servidor y la
# aplicación está instalada. certbot agrega el bloque HTTPS a nginx, redirige
# http → https y deja la renovación automática. Después activa la
# redirección segura en Django (SECURE_SSL_REDIRECT=True) y reinicia.
#
# Uso:
#   sudo bash deploy/fedora/3-certificado.sh [correo-para-avisos]
# ============================================================================
set -euo pipefail

# shellcheck source=comun.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun.sh"
CORREO="${1:-}"

[ "$(id -u)" -eq 0 ] || { echo "Correr como root: sudo bash $0 [correo]"; exit 1; }
# shellcheck disable=SC1091
source /etc/koape-rrhh/dominio.env

echo "==> Verificando que ${DOMINIO} apunte a este servidor..."
IP_DOMINIO="$(getent hosts "$DOMINIO" | awk '{print $1}' | head -n1 || true)"
echo "    ${DOMINIO} → ${IP_DOMINIO:-sin resolver}"

if [ -n "$CORREO" ]; then
    certbot --nginx -d "$DOMINIO" --redirect --agree-tos -m "$CORREO" --non-interactive
else
    # Sin correo, Let's Encrypt no puede avisar si el certificado está por vencer.
    certbot --nginx -d "$DOMINIO" --redirect --agree-tos --register-unsafely-without-email --non-interactive
fi
systemctl enable --now certbot-renew.timer >/dev/null 2>&1 || true

# Con HTTPS listo, Django redirige a https y marca las cookies como seguras.
sed -i 's/^SECURE_SSL_REDIRECT=.*/SECURE_SSL_REDIRECT=True/' "$DIR_APP/backend/.env"
systemctl restart "$SERVICIO"

echo ""
echo "✔ HTTPS listo: https://${DOMINIO}  (se renueva solo)."
