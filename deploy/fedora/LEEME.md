# Instalación en Fedora Cloud — rrhh.koapesystem.com

Adaptado de los scripts de KOAPE-PORCINO (mismo esquema). La IP `2.25.106.83` de los ejemplos es la del
VPS de PORCINO: si Koape RR. HH. va en otro servidor, usá la suya.

nginx sirve la aplicación en el dominio y pasa `/api/` a gunicorn (puerto
interno **8014**), con HTTPS de Let's Encrypt. Cada empresa entra por su dirección propia
(`rrhh.koapesystem.com/delacosta`): nginx manda esas rutas a la aplicación, que muestra su ingreso personalizado. La aplicación corre con un
**usuario limitado**; root solo se usa para preparar el servidor, sacar el
certificado y pasar a PostgreSQL.

**El admin** se entra por **`https://rrhh.koapesystem.com/admin/`** (pedido del cliente, 14/10/2026) y
también por **`https://2.25.106.83:8006/admin/`**, con un certificado propio (el navegador avisa la primera
vez y se acepta; si se entra con `http://`, se pasa solo a `https://`). Django solo lo atiende por las
direcciones de `ADMIN_HOSTS` en `backend/.env` (el dominio y la ip:puerto). Al preparar el servidor se puede
limitar el puerto 8006 a ciertas IPs (el acceso por el dominio no se limita por IP). Los puertos
están en `comun.sh` (`PUERTO_GUNICORN`, `PUERTO_ADMIN`); en el VPS de PORCINO, el 8001, 8002 y 8012
son de las otras aplicaciones.

**Clave de cifrado:** `2-instalar-app.sh` genera una sola vez `CLAVE_CIFRADO` en `backend/.env` (cuentas
bancarias y códigos fijos de marcación). **No se cambia ni se pierde nunca**: sin ella esos datos no se leen. Va
dentro del backup completo; guardá además una copia aparte en un lugar seguro.

**Tareas automáticas:** backup diario (03:30) y cálculo de la asistencia del día anterior (02:00), para que
aparezcan las ausencias de los días sin marcas.

**Base de datos:** al preparar el servidor se elige **SQLite** (un archivo, nada
que configurar: ideal para empezar) o **PostgreSQL** (recomendado para el uso
diario). Si se empieza con SQLite, después se pasa a PostgreSQL con
`4-migrar-a-postgres.sh`, **sin perder datos**.

**Inicio automático:** el mismo script pregunta si el sistema tiene que iniciar
solo cada vez que arranca el servidor. Se puede cambiar cuando se quiera:
`sudo systemctl enable koape-rrhh` (activar) o `sudo systemctl disable koape-rrhh` (quitar).

| Script | Quién lo corre | Qué hace |
|---|---|---|
| `1-preparar-servidor.sh` | root, una vez | Pregunta la base (SQLite o PostgreSQL) y el inicio automático; paquetes, servicio systemd, nginx, firewall, SELinux, backup diario y permiso para manejar el servicio sin ser root |
| `2-instalar-app.sh` | usuario limitado | Entorno de Python, `.env` de producción, migraciones, admin, perfiles, compilación de la app y arranque |
| `3-certificado.sh` | root, una vez | Certificado HTTPS, redirección a https y renovación automática |
| `4-migrar-a-postgres.sh` | root, cuando se quiera | Pasa de SQLite a un PostgreSQL ya instalado (puede ser compartido): backup completo, pide la clave del administrador de PostgreSQL, crea base y usuario propios, copia, **verifica** y cambia la configuración. No toca `pg_hba.conf` ni otras bases |
| `backup-completo.sh` | root, cuando se quiera | Un `.tar.gz` con el proyecto, la base y la configuración del servidor (nginx, servicio, certificado del admin) en `/var/backups/koape-rrhh/completo_*.tar.gz` |
| `actualizar.sh` | usuario limitado | Backup, `git pull`, dependencias, migraciones, perfiles, compilación y reinicio |
| `comun.sh` | — | Funciones compartidas (lo cargan los demás) |

## Antes de empezar

- El subdominio `rrhh.koapesystem.com` tiene que apuntar (registro A) a la IP del servidor.
- El proveedor de la nube tiene que permitir los puertos **80**, **443** y **8006** (admin), además del 22 para SSH.
- Los puertos **8014** (interno) y **8006** no tienen que estar usados por otro programa: el script lo revisa y, si lo están, se frena sin tocar nada.
- La aplicación es del usuario **`webuser`** y vive en **`/home/webuser/HHRR_KOAPE`**. Los
  scripts toman la carpeta sola (donde esté clonado el proyecto) y se corren desde root
  (los de root) o con `sudo -iu webuser` (los del usuario).
- Al estar dentro de `/home`, el script 1 deja que nginx **atraviese** `/home/webuser`
  (`o+x`: pasar, no listar) y ajusta SELinux (`httpd_enable_homedirs`, etiquetas del
  proyecto y del `venv`). `2-instalar-app.sh` y `actualizar.sh` vuelven a aplicar las
  etiquetas después de cada compilación.

## Paso a paso (entrando como root)

### 1. Bajar el proyecto (como webuser)

El repositorio es privado: `webuser` necesita una **clave de despliegue** (solo lectura).
Se usa el alias `github-rrhh` para no cambiar cómo `webuser` se conecta a GitHub para
otras aplicaciones.

```bash
dnf install -y git
sudo -iu webuser bash -c 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && ssh-keygen -t ed25519 -C "servidor-rrhh" -f ~/.ssh/koape_rrhh -N "" && cat ~/.ssh/koape_rrhh.pub'
```

Esa clave pública se carga en GitHub → repositorio → *Settings → Deploy keys → Add deploy key* (sin permiso de escritura). Después:

```bash
sudo -iu webuser bash -c 'printf "\nHost github-rrhh\n    HostName github.com\n    User git\n    IdentityFile ~/.ssh/koape_rrhh\n    IdentitiesOnly yes\n" >> ~/.ssh/config && chmod 600 ~/.ssh/config'
sudo -iu webuser bash -c 'cd ~ && git clone git@github-rrhh:gilbertohilgemann/RRHH_KOAPE.git ~/HHRR_KOAPE'
```

### 2. Preparar el servidor (root)

```bash
bash /home/webuser/HHRR_KOAPE/deploy/fedora/1-preparar-servidor.sh webuser rrhh.koapesystem.com 2.25.106.83
```

Pregunta tres cosas: la base de datos (`1` SQLite / `2` PostgreSQL), si el sistema
inicia solo al arrancar el servidor (`S`/`n`) y desde qué IPs se puede entrar al
admin (Enter = desde cualquiera).

### 3. Instalar la aplicación (como webuser)

```bash
sudo -iu webuser bash -c 'cd ~/HHRR_KOAPE && bash deploy/fedora/2-instalar-app.sh'
```

Al terminar, la app ya responde en `http://rrhh.koapesystem.com`.

### 4. Certificado HTTPS (root)

```bash
bash /home/webuser/HHRR_KOAPE/deploy/fedora/3-certificado.sh correo@ejemplo.com
```

### (Más adelante) Pasar de SQLite a PostgreSQL (root)

```bash
bash /home/webuser/HHRR_KOAPE/deploy/fedora/4-migrar-a-postgres.sh
```

Requiere un PostgreSQL ya funcionando en el servidor (en este VPS, el compartido con las otras aplicaciones).
Hace un backup completo, pide el usuario y la contraseña del **administrador de PostgreSQL** (se escriben en la
consola: no se muestran ni se guardan), crea la base `koape_rrhh` con su usuario y una clave aleatoria
(`/etc/koape-rrhh/db.env`), detiene el sistema, copia todos los datos, **verifica** que la copia sea igual
(cantidad de registros por tabla y permisos de cada grupo) y recién ahí cambia `backend/.env` y lo vuelve a iniciar.
No toca `pg_hba.conf` ni otras bases: si la aplicación no puede entrar con usuario y clave por `127.0.0.1`, se frena
y lo avisa. Si algo falla antes del cambio de configuración, el sistema sigue con SQLite sin cambios. El archivo
SQLite queda como `backend/db.sqlite3.antes-de-postgres`; al final muestra cómo volver atrás.

### Backup completo (root, cuando se quiera)

```bash
bash /home/webuser/HHRR_KOAPE/deploy/fedora/backup-completo.sh
```

Un solo `.tar.gz` (solo para root) con el proyecto (sin `venv`, `node_modules`, `dist` ni `.git`), la base
(copia consistente de SQLite o `pg_dump`) y la configuración del servidor. Para bajarlo a la PC:
`scp root@2.25.106.83:/var/backups/koape-rrhh/completo_*.tar.gz .`

### 5. Primer ingreso

Entrá a `https://rrhh.koapesystem.com/admin/` (o `https://2.25.106.83:8006/admin/`) con el usuario `admin` y
**cambiá la contraseña**.
El manual del administrador está en el menú del admin; el de cada perfil, en el botón *Manual* de la aplicación.
Después, en *Empresas*, cargá cada empresa con su **Dirección de acceso** (ej. `delacosta`).

## Uso diario

| Para | Comando (como root; o como webuser, con `sudo`) |
|---|---|
| Actualizar a la última versión | `sudo -iu webuser bash -c 'cd ~/HHRR_KOAPE && bash deploy/fedora/actualizar.sh'` |
| Reiniciar | `sudo systemctl restart koape-rrhh` |
| Detener / iniciar | `sudo systemctl stop koape-rrhh` / `sudo systemctl start koape-rrhh` |
| Activar / quitar el inicio automático | `sudo systemctl enable koape-rrhh` / `sudo systemctl disable koape-rrhh` |
| Ver si está funcionando | `sudo systemctl status koape-rrhh` |
| Ver los registros (errores) | `sudo journalctl -u koape-rrhh -n 100` |
| Backups | `/var/backups/koape-rrhh` (todos los días a las 03:30, se guardan 14 días) |

> ⚠ `2-instalar-app.sh` vuelve a dejar la contraseña inicial del usuario `admin` (para no perder nunca el acceso).
> Para actualizar usá siempre `actualizar.sh`, que no la toca.

## Restaurar un backup

Con **SQLite** (`base_….sqlite3`):

```bash
sudo systemctl stop koape-rrhh
cp /var/backups/koape-rrhh/base_AAAA-MM-DD_HHMM.sqlite3 /home/webuser/HHRR_KOAPE/backend/db.sqlite3
tar -xzf /var/backups/koape-rrhh/archivos_AAAA-MM-DD_HHMM.tar.gz -C /home/webuser/HHRR_KOAPE/backend
sudo systemctl start koape-rrhh
```

Con **PostgreSQL** (`base_….dump`):

```bash
source /etc/koape-rrhh/db.env
PGPASSWORD="$DB_PASSWORD" pg_restore -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" --clean --if-exists /var/backups/koape-rrhh/base_AAAA-MM-DD_HHMM.dump
tar -xzf /var/backups/koape-rrhh/archivos_AAAA-MM-DD_HHMM.tar.gz -C /home/webuser/HHRR_KOAPE/backend
sudo systemctl restart koape-rrhh
```
