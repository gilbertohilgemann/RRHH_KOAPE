#!/usr/bin/env bash
# ============================================================================
# Koape RR. HH. — 1. Preparar el servidor Fedora Cloud
#
# Se corre UNA vez, como root (sudo), porque instala paquetes y toca el
# sistema. Pregunta:
#   - con qué base de datos arrancar: SQLite (simple, un archivo) o
#     PostgreSQL (recomendado para el uso diario). Si se elige SQLite, más
#     adelante se pasa a PostgreSQL con 4-migrar-a-postgres.sh, sin perder datos;
#   - si el sistema tiene que iniciar solo cada vez que arranca el servidor.
#
# Se corre desde adentro del proyecto ya clonado por el usuario de la
# aplicación (ej. /home/webuser/RRHH_KOAPE): esa carpeta es la que se usa.
#
# Deja listo: paquetes, permisos de la carpeta del proyecto,
# servicio systemd "koape-rrhh" (gunicorn en 127.0.0.1:PUERTO_GUNICORN),
# nginx para el dominio (solo la app y la API), el admin aparte en
# https://<ip>:PUERTO_ADMIN/admin/ con certificado propio, firewall, SELinux,
# backup diario y sudo sin clave SOLO para manejar el servicio.
#
# Uso:
#   sudo bash 1-preparar-servidor.sh <usuario-limitado> [dominio] [ip-pública]
#   ej.: sudo bash 1-preparar-servidor.sh koape hhrr.koapesystem.com 2.25.106.83
# ============================================================================
set -euo pipefail
# shellcheck source=comun.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun.sh"

USUARIO="${1:-${SUDO_USER:-}}"
DOMINIO="${2:-hhrr.koapesystem.com}"
IP_ADMIN="${3:-2.25.106.83}"

[ "$(id -u)" -eq 0 ] || falla "Este script se corre como root: sudo bash $0 <usuario-limitado> [dominio] [ip-pública]"
[ -n "$USUARIO" ] || falla "Indicá el usuario limitado: sudo bash $0 <usuario-limitado> [dominio] [ip-pública]"
id "$USUARIO" >/dev/null 2>&1 || falla "No existe el usuario '$USUARIO'. Crealo primero: useradd -m $USUARIO"
grep -qi fedora /etc/os-release || aviso "No parece Fedora: el script usa dnf y puede fallar."

echo ""
echo "============================================================"
echo "  Koape RR. HH. — preparar el servidor"
echo "============================================================"
echo "  Usuario de la aplicación: $USUARIO"
echo "  Dominio (app y API):      $DOMINIO"
echo "  Admin (solo por IP):      https://${IP_ADMIN}:${PUERTO_ADMIN}/admin/"
echo "  Carpeta:                  $DIR_APP"
echo ""
echo "  Revisando que los puertos no los use otro programa..."
puerto_libre_o_nuestro "$PUERTO_GUNICORN" gunicorn
puerto_libre_o_nuestro "$PUERTO_ADMIN" nginx
echo ""
echo "  Base de datos:"
echo "    1) SQLite     — un archivo, nada que configurar. Ideal para empezar o probar."
echo "                    Después se pasa a PostgreSQL con 4-migrar-a-postgres.sh."
echo "    2) PostgreSQL — recomendado para el uso diario (varios usuarios a la vez)."
read -r -p "  Elegí 1 o 2 [1]: " OPCION_BD
case "${OPCION_BD:-1}" in
    2) MOTOR="postgres" ;;
    *) MOTOR="sqlite" ;;
esac
echo ""
if preguntar_si "  ¿El sistema tiene que iniciar solo cada vez que arranca el servidor?" s; then
    AUTOARRANQUE="si"
else
    AUTOARRANQUE="no"
fi
echo ""
echo "  ¿Desde qué IPs se puede entrar al admin (puerto ${PUERTO_ADMIN})?"
echo "  Separadas por espacio (ej. 181.120.10.5 190.104.0.0/16). Enter = desde cualquiera."
read -r -p "  IPs permitidas: " IPS_ADMIN
echo ""

# ----------------------------------------------------------------------------
paso "1/9 Instalando paquetes del sistema..."
dnf install -y python3 python3-devel python3-pip gcc git nodejs npm nginx openssl \
    certbot python3-certbot-nginx policycoreutils-python-utils tar gzip sqlite iproute >/dev/null
ok "Paquetes instalados (Python $(python3 --version | cut -d' ' -f2), Node $(node --version))."

# ----------------------------------------------------------------------------
paso "2/9 Base de datos ($MOTOR)..."
mkdir -p "$DIR_CONF"
if [ "$MOTOR" = "postgres" ]; then
    preparar_postgres "$USUARIO"
else
    ok "SQLite: la base es un archivo dentro de la aplicación (backend/db.sqlite3). Nada que instalar."
fi
cat > "$DIR_CONF/dominio.env" <<EOF
DOMINIO=${DOMINIO}
USUARIO=${USUARIO}
IP_ADMIN=${IP_ADMIN}
PUERTO_ADMIN=${PUERTO_ADMIN}
DIR_APP=${DIR_APP}
EOF
chown -R root:"$USUARIO" "$DIR_CONF"
chmod 750 "$DIR_CONF"; chmod 640 "$DIR_CONF"/*.env

# ----------------------------------------------------------------------------
paso "3/9 Carpeta de la aplicación..."
# El proyecto ya está clonado (este script corre desde adentro) y es del
# usuario de la aplicación.
[ "$(stat -c %U "$DIR_APP")" = "$USUARIO" ] \
    || falla "$DIR_APP no es de $USUARIO. Corregilo con: chown -R $USUARIO:$USUARIO $DIR_APP"
mkdir -p "$DIR_BACKUP"
chown "$USUARIO":"$USUARIO" "$DIR_BACKUP"
# nginx (otro usuario) tiene que poder entrar a leer la app compilada, los
# estáticos y los logos; las fotos privadas (backend/privado, 700) quedan
# fuera de nginx: solo las entrega la aplicación, con permisos. Si el
# proyecto está dentro de un /home, nginx necesita poder ATRAVESAR la carpeta
# del usuario (o+x: pasar, no listar ni leer lo que hay).
chmod 755 "$DIR_APP"
DIR_PADRE="$(dirname "$DIR_APP")"
case "$DIR_PADRE" in
    /home/*) chmod o+x "$DIR_PADRE"; ok "$DIR_PADRE: nginx puede atravesarla (o+x), no listarla." ;;
esac
ok "$DIR_APP lista (dueño: $USUARIO)."

# ----------------------------------------------------------------------------
paso "4/9 SELinux..."
if command -v getenforce >/dev/null && [ "$(getenforce)" != "Disabled" ]; then
    setsebool -P httpd_can_network_connect 1   # nginx → gunicorn en 127.0.0.1:PUERTO_GUNICORN
    # nginx tiene que poder escuchar en el puerto del admin.
    semanage port -a -t http_port_t -p tcp "$PUERTO_ADMIN" 2>/dev/null \
        || semanage port -m -t http_port_t -p tcp "$PUERTO_ADMIN" 2>/dev/null || true
    case "$DIR_APP" in
        # Dentro de un /home: nginx necesita entrar a la carpeta del usuario.
        /home/*) setsebool -P httpd_enable_homedirs 1 ;;
    esac
    # Todo el proyecto legible por nginx (lo que no debe ver lo cierran los
    # permisos y la configuración de nginx), y el venv ejecutable por
    # systemd: sin eso, gunicorn no arranca desde un /home (error 203/EXEC).
    semanage fcontext -a -t httpd_sys_content_t "${DIR_APP}(/.*)?" 2>/dev/null \
        || semanage fcontext -m -t httpd_sys_content_t "${DIR_APP}(/.*)?" 2>/dev/null || true
    semanage fcontext -a -t bin_t "${DIR_APP}/backend/venv/bin(/.*)?" 2>/dev/null \
        || semanage fcontext -m -t bin_t "${DIR_APP}/backend/venv/bin(/.*)?" 2>/dev/null || true
    restorecon -R "$DIR_APP" 2>/dev/null || true
    ok "SELinux: nginx puede leer la app, escuchar en ${PUERTO_ADMIN} y conectarse a gunicorn."
else
    ok "SELinux desactivado: nada que ajustar."
fi

# ----------------------------------------------------------------------------
paso "5/9 Servicio systemd ($SERVICIO)..."
cat > "/etc/systemd/system/${SERVICIO}.service" <<EOF
[Unit]
Description=Koape RR. HH. - backend Django con gunicorn
After=network.target postgresql.service

[Service]
Type=simple
User=${USUARIO}
Group=${USUARIO}
WorkingDirectory=${DIR_APP}/backend
ExecStart=${DIR_APP}/backend/venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:${PUERTO_GUNICORN} --workers 3 --timeout 120 --access-logfile - --error-logfile -
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
if [ "$AUTOARRANQUE" = "si" ]; then
    systemctl enable "$SERVICIO" >/dev/null
    ok "Servicio creado: inicia solo cada vez que arranca el servidor."
else
    systemctl disable "$SERVICIO" >/dev/null 2>&1 || true
    ok "Servicio creado, SIN inicio automático (se inicia con: sudo systemctl start $SERVICIO)."
fi

# ----------------------------------------------------------------------------
paso "6/9 nginx para ${DOMINIO}..."
cat > "/etc/nginx/conf.d/${SERVICIO}.conf" <<EOF
# Koape RR. HH.. certbot agrega acá el bloque HTTPS.
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMINIO};

    # Fotos y adjuntos de hasta 20 MB.
    client_max_body_size 25M;

    # Aplicación (React compilada): las rutas de la app caen en index.html.
    root ${DIR_APP}/frontend/dist;
    index index.html;
    location / {
        try_files \$uri \$uri/ /index.html;
    }
    # index.html sin caché: así cada versión nueva llega al recargar (los
    # archivos de /assets/ cambian de nombre en cada compilación).
    location = /index.html {
        add_header Cache-Control "no-cache";
    }
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # API → gunicorn.
    location ^~ /api/ {
        proxy_pass http://127.0.0.1:${PUERTO_GUNICORN};
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 180s;
    }

    # El admin NO se publica en el dominio: solo en https://<ip>:${PUERTO_ADMIN}/admin/
    # (archivo ${SERVICIO}-admin.conf). Django también lo rechaza (ADMIN_HOSTS).
    location ~ ^/admin(/|\$) {
        return 404;
    }

    # Estáticos del admin y logos (las fotos privadas NO se sirven acá).
    location /static/ {
        alias ${DIR_APP}/backend/staticfiles/;
        expires 30d;
    }
    location /media/ {
        alias ${DIR_APP}/backend/media/;
        expires 7d;
    }
}
EOF

# Admin de la plataforma: solo por IP y puerto propio, con https. Let's
# Encrypt no da certificados comunes para una IP, así que se usa uno propio
# (autofirmado, 10 años): el navegador avisa la primera vez y se acepta.
CERT_ADMIN="/etc/pki/tls/certs/${SERVICIO}-admin.crt"
CLAVE_ADMIN="/etc/pki/tls/private/${SERVICIO}-admin.key"
if [ ! -f "$CERT_ADMIN" ] || [ ! -f "$CLAVE_ADMIN" ]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -keyout "$CLAVE_ADMIN" -out "$CERT_ADMIN" \
        -subj "/CN=${IP_ADMIN}" -addext "subjectAltName=IP:${IP_ADMIN}" >/dev/null 2>&1
    chmod 600 "$CLAVE_ADMIN"
    restorecon "$CERT_ADMIN" "$CLAVE_ADMIN" 2>/dev/null || true
fi
REGLAS_IP=""
if [ -n "${IPS_ADMIN// /}" ]; then
    for ip in $IPS_ADMIN; do REGLAS_IP+="    allow ${ip};"$'\n'; done
    REGLAS_IP+="    deny all;"
fi
cat > "/etc/nginx/conf.d/${SERVICIO}-admin.conf" <<EOF
# Koape RR. HH. — admin de la plataforma, solo por IP.
server {
    listen ${PUERTO_ADMIN} ssl;
    listen [::]:${PUERTO_ADMIN} ssl;
    server_name _;

    ssl_certificate     ${CERT_ADMIN};
    ssl_certificate_key ${CLAVE_ADMIN};
    # Si alguien entra con http:// a este puerto, se lo pasa a https://.
    error_page 497 =301 https://\$host:\$server_port\$request_uri;

    client_max_body_size 25M;
${REGLAS_IP}

    location = / {
        return 302 /admin/;
    }
    location ~ ^/(admin|static|media)/ {
        proxy_pass http://127.0.0.1:${PUERTO_GUNICORN};
        # Con el puerto incluido: Django compara el origen del login (CSRF)
        # y ADMIN_HOSTS con "ip:puerto".
        proxy_set_header Host \$http_host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;   # el backup completo puede tardar
    }
    location / {
        return 404;
    }
}
EOF
nginx -t >/dev/null 2>&1 || falla "La configuración de nginx tiene errores: corré 'nginx -t' para verlos."
# nginx siempre arranca solo: si el sistema está detenido, muestra un aviso en vez de no responder.
systemctl enable --now nginx >/dev/null
systemctl reload nginx
ok "nginx configurado: app y API en ${DOMINIO}; admin solo en https://${IP_ADMIN}:${PUERTO_ADMIN}/admin/."

# ----------------------------------------------------------------------------
paso "7/9 Firewall..."
if command -v firewall-cmd >/dev/null && systemctl is-active --quiet firewalld; then
    # firewall-cmd no acepta --add-service y --add-port en la misma llamada.
    firewall-cmd --permanent --add-service=http --add-service=https >/dev/null
    firewall-cmd --permanent --add-port="${PUERTO_ADMIN}/tcp" >/dev/null
    firewall-cmd --reload >/dev/null
    ok "Abiertos http (80), https (443) y el admin (${PUERTO_ADMIN})."
else
    aviso "firewalld no está activo: si el proveedor tiene firewall propio, abrí ahí los puertos 80, 443 y ${PUERTO_ADMIN}."
fi

# ----------------------------------------------------------------------------
paso "8/9 Backup diario..."
cat > /usr/local/bin/koape-rrhh-backup <<'EOF'
#!/usr/bin/env bash
# Backup diario de Koape RR. HH.: la base (PostgreSQL o SQLite, según
# cuál use) y los archivos subidos (fotos privadas y logos). Se guardan 14 días.
set -euo pipefail
source /etc/koape-rrhh/dominio.env
APP="$DIR_APP/backend"
DESTINO=/var/backups/koape-rrhh
FECHA=$(date +%Y-%m-%d_%H%M)
if grep -q '^DB_ENGINE=postgres' "$APP/.env" 2>/dev/null; then
    set -a; source /etc/koape-rrhh/db.env; set +a
    PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -U "$DB_USER" -Fc "$DB_NAME" > "$DESTINO/base_$FECHA.dump"
elif [ -f "$APP/db.sqlite3" ]; then
    # .backup hace una copia consistente aunque el sistema esté usando la base.
    sqlite3 "$APP/db.sqlite3" ".backup '$DESTINO/base_$FECHA.sqlite3'"
fi
tar -czf "$DESTINO/archivos_$FECHA.tar.gz" -C "$APP" privado media 2>/dev/null || true
find "$DESTINO" -type f -mtime +14 -delete
EOF
chmod 755 /usr/local/bin/koape-rrhh-backup
cat > "/etc/systemd/system/${SERVICIO}-backup.service" <<EOF
[Unit]
Description=Backup de Koape RR. HH.

[Service]
Type=oneshot
User=${USUARIO}
ExecStart=/usr/local/bin/koape-rrhh-backup
EOF
cat > "/etc/systemd/system/${SERVICIO}-backup.timer" <<EOF
[Unit]
Description=Backup diario de Koape RR. HH.

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now "${SERVICIO}-backup.timer" >/dev/null
ok "Backup todos los días a las 03:30 en $DIR_BACKUP (se guardan 14 días)."

# Cálculo nocturno de la asistencia del día anterior: así aparecen las ausencias de los días sin marcas
# (lo demás se recalcula solo al marcar, importar o aprobar).
cat > "/etc/systemd/system/${SERVICIO}-asistencia.service" <<EOF
[Unit]
Description=Koape RR. HH. - cálculo de la asistencia del día anterior

[Service]
Type=oneshot
User=${USUARIO}
WorkingDirectory=${DIR_APP}/backend
ExecStart=${DIR_APP}/backend/venv/bin/python manage.py calcular_asistencia --ayer
EOF
cat > "/etc/systemd/system/${SERVICIO}-asistencia.timer" <<EOF
[Unit]
Description=Koape RR. HH. - asistencia de ayer, todas las noches

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now "${SERVICIO}-asistencia.timer" >/dev/null
ok "Asistencia del día anterior: se calcula todas las noches a las 02:00."

# ----------------------------------------------------------------------------
paso "9/9 Permiso para manejar el servicio sin ser root..."
SC=/usr/bin/systemctl
cat > "/etc/sudoers.d/${SERVICIO}" <<EOF
# El usuario de la aplicación puede manejar SOLO este servicio (iniciar,
# detener, reiniciar, ver su estado y registros, y activar o quitar el inicio
# automático).
${USUARIO} ALL=(root) NOPASSWD: ${SC} start ${SERVICIO}, ${SC} stop ${SERVICIO}, ${SC} restart ${SERVICIO}, ${SC} status ${SERVICIO}, ${SC} is-active ${SERVICIO}, ${SC} enable ${SERVICIO}, ${SC} disable ${SERVICIO}, /usr/bin/journalctl -u ${SERVICIO} *
EOF
chmod 440 "/etc/sudoers.d/${SERVICIO}"
visudo -cf "/etc/sudoers.d/${SERVICIO}" >/dev/null || { rm -f "/etc/sudoers.d/${SERVICIO}"; falla "La regla de sudo quedó mal y se borró."; }
ok "${USUARIO} puede hacer: sudo systemctl start|stop|restart|status|enable|disable ${SERVICIO}."

echo ""
echo "============================================================"
ok "Servidor preparado (base: $MOTOR · inicio automático: $AUTOARRANQUE)."
echo "============================================================"
echo ""
echo "  Admin (cuando la app esté instalada): https://${IP_ADMIN}:${PUERTO_ADMIN}/admin/"
echo "  Si el proveedor de la nube tiene firewall propio, abrí ahí el puerto ${PUERTO_ADMIN}."
echo ""
echo "  Siguiente paso, con el usuario ${USUARIO} (no root):"
echo "    sudo -iu ${USUARIO} bash -c 'cd ${DIR_APP} && bash deploy/fedora/2-instalar-app.sh'"
echo ""
echo "  Después, el certificado HTTPS (root):"
echo "    sudo bash ${DIR_APP}/deploy/fedora/3-certificado.sh [correo]"
if [ "$MOTOR" = "sqlite" ]; then
    echo ""
    echo "  Cuando quieras pasar a PostgreSQL (root, sin perder datos):"
    echo "    sudo bash ${DIR_APP}/deploy/fedora/4-migrar-a-postgres.sh"
fi
echo ""
