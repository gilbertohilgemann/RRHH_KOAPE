#!/usr/bin/env bash
# ============================================================================
# Koape RR. HH. — Arranque del sistema (Linux)
#
# Levanta el backend (Django, vía gunicorn) y el frontend (build de
# producción, vía `vite preview`) en segundo plano. Corré `./install.sh`
# primero si todavía no instalaste nada.
#
# Uso:
#   ./start.sh            # levanta todo
#   ./start.sh stop       # frena todo
#   ./start.sh status     # muestra si está corriendo
#   ./start.sh restart
#   ./start.sh update     # después de sobrescribir el código: reinstala
#                         # dependencias, migra, rearma el build y reinicia
# ============================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
RUN_DIR="$PROJECT_ROOT/.run"
LOG_DIR="$PROJECT_ROOT/logs"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"

# Puertos propios (no los típicos 8000/5173) para no chocar con otras
# aplicaciones del mismo servidor. Si se cambian, cambiar también
# frontend/src/services/api.ts y frontend/vite.config.ts.
BACKEND_PORT="${BACKEND_PORT:-8004}"
FRONTEND_PORT="${FRONTEND_PORT:-5204}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}==>${NC} $1"; }
ok()   { echo -e "${GREEN}✔${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✘${NC} $1"; }

is_running() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

port_in_use() {
    # $1 = puerto. Verdadero si algo ya está escuchando ahí (nuestro o ajeno).
    if command -v ss >/dev/null 2>&1; then
        ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[.:]$1\$"
    elif command -v netstat >/dev/null 2>&1; then
        netstat -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[.:]$1\$"
    else
        return 1
    fi
}

mkdir -p "$RUN_DIR" "$LOG_DIR"

status() {
    if is_running "$BACKEND_PID_FILE"; then
        ok "Backend corriendo (PID $(cat "$BACKEND_PID_FILE")) — puerto $BACKEND_PORT"
    else
        warn "Backend detenido."
    fi
    if is_running "$FRONTEND_PID_FILE"; then
        ok "Frontend corriendo (PID $(cat "$FRONTEND_PID_FILE")) — puerto $FRONTEND_PORT"
    else
        warn "Frontend detenido."
    fi
}

stop_all() {
    if is_running "$BACKEND_PID_FILE"; then
        kill "$(cat "$BACKEND_PID_FILE")" && ok "Backend detenido." || warn "No se pudo detener el backend."
        rm -f "$BACKEND_PID_FILE"
    else
        warn "El backend ya estaba detenido."
    fi
    if is_running "$FRONTEND_PID_FILE"; then
        # npm lanza vite como proceso hijo: se mata el grupo completo para no
        # dejar huérfanos ocupando el puerto.
        local pid
        pid="$(cat "$FRONTEND_PID_FILE")"
        kill -- -"$pid" 2>/dev/null || kill "$pid"
        ok "Frontend detenido."
        rm -f "$FRONTEND_PID_FILE"
    else
        warn "El frontend ya estaba detenido."
    fi
}

start_all() {
    if [ ! -d "$BACKEND_DIR/venv" ]; then
        err "No existe backend/venv — corré ./install.sh primero."
        exit 1
    fi
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        err "No existe frontend/node_modules — corré ./install.sh primero."
        exit 1
    fi

    # --- Backend ---
    if is_running "$BACKEND_PID_FILE"; then
        warn "El backend ya está corriendo (PID $(cat "$BACKEND_PID_FILE")), no lo reinicio."
    elif port_in_use "$BACKEND_PORT"; then
        err "El puerto $BACKEND_PORT ya lo está usando otro proceso (no nuestro, según $BACKEND_PID_FILE)."
        err "No arranco el backend ahí para no interferir con lo que ya esté corriendo."
        err "Elegí otro puerto: BACKEND_PORT=8001 ./start.sh"
        exit 1
    else
        log "Aplicando migraciones pendientes..."
        (cd "$BACKEND_DIR" && venv/bin/python manage.py migrate --noinput)

        log "Levantando el backend (gunicorn) en el puerto $BACKEND_PORT..."
        cd "$BACKEND_DIR"
        venv/bin/gunicorn config.wsgi:application \
            --bind "0.0.0.0:$BACKEND_PORT" \
            --workers 3 \
            --daemon \
            --pid "$BACKEND_PID_FILE" \
            --access-logfile "$LOG_DIR/backend-access.log" \
            --error-logfile "$LOG_DIR/backend-error.log"
        cd "$PROJECT_ROOT"

        # gunicorn con --daemon tarda un instante en escribir el pidfile.
        sleep 1
        if is_running "$BACKEND_PID_FILE"; then
            ok "Backend arriba en el puerto $BACKEND_PORT"
        else
            err "El backend no arrancó — revisá $LOG_DIR/backend-error.log"
            exit 1
        fi
    fi

    # --- Frontend ---
    if is_running "$FRONTEND_PID_FILE"; then
        warn "El frontend ya está corriendo (PID $(cat "$FRONTEND_PID_FILE")), no lo reinicio."
    elif port_in_use "$FRONTEND_PORT"; then
        err "El puerto $FRONTEND_PORT ya lo está usando otro proceso (no nuestro, según $FRONTEND_PID_FILE)."
        err "No arranco el frontend ahí para no interferir con lo que ya esté corriendo."
        err "Elegí otro puerto: FRONTEND_PORT=5174 ./start.sh"
        exit 1
    else
        log "Levantando el frontend en el puerto $FRONTEND_PORT..."
        cd "$FRONTEND_DIR"
        # setsid: el proceso queda como líder de su propio grupo, así stop
        # puede matar a npm y a su hijo vite juntos.
        setsid nohup npm run preview -- --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort \
            > "$LOG_DIR/frontend.log" 2>&1 &
        echo $! > "$FRONTEND_PID_FILE"
        cd "$PROJECT_ROOT"

        sleep 1
        if is_running "$FRONTEND_PID_FILE"; then
            ok "Frontend arriba en el puerto $FRONTEND_PORT"
        else
            err "El frontend no arrancó — revisá $LOG_DIR/frontend.log"
            exit 1
        fi
    fi

    echo ""
    echo "  Aplicacion: http://<ip-o-dominio>:$FRONTEND_PORT"
    echo "  Admin:        http://<ip-o-dominio>:$BACKEND_PORT/admin/"
    echo ""
    echo "  Para frenar todo:   ./start.sh stop"
    echo "  Para ver el estado: ./start.sh status"
}

# Para cuando ya se sobrescribió el código (git pull, rsync, backup nuevo...)
# y hay que ponerlo en producción: reinstala dependencias por si cambiaron,
# aplica migraciones, rearma estáticos y el build del frontend, y reinicia
# los procesos — sobrescribir los archivos solos no alcanza porque gunicorn y
# `vite preview` ya tienen el código viejo cargado.
update_all() {
    if [ ! -d "$BACKEND_DIR/venv" ] || [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        err "No está instalado todavía — corré ./install.sh primero."
        exit 1
    fi

    log "Backend: instalando dependencias (por si cambiaron)..."
    "$BACKEND_DIR/venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" --quiet
    ok "Dependencias de Python al día."

    log "Backend: aplicando migraciones pendientes..."
    (cd "$BACKEND_DIR" && venv/bin/python manage.py migrate --noinput)
    ok "Base de datos al día."

    log "Backend: recolectando archivos estáticos del admin..."
    (cd "$BACKEND_DIR" && venv/bin/python manage.py collectstatic --noinput >/dev/null)
    ok "Estáticos al día."

    log "Frontend: instalando dependencias (por si cambiaron)..."
    (cd "$FRONTEND_DIR" && npm install)
    ok "Dependencias de Node al día."

    log "Frontend: generando build de producción nuevo..."
    (cd "$FRONTEND_DIR" && npm run build)
    ok "Build de producción al día."

    log "Reiniciando los servicios para que tomen el código nuevo..."
    stop_all
    sleep 1
    start_all
}

case "${1:-start}" in
    start)   start_all ;;
    stop)    stop_all ;;
    status)  status ;;
    restart) stop_all; sleep 1; start_all ;;
    update)  update_all ;;
    *)
        echo "Uso: $0 [start|stop|status|restart|update]"
        exit 1
        ;;
esac
