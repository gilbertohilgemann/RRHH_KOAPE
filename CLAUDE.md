# Koape RR. HH. — guía para Claude

Sistema multiempresa de RR. HH. y nómina para Paraguay (Django + DRF en `backend/`,
React + Vite + TS + Tailwind v4 en `frontend/`). Todo en castellano.

## Leer antes de trabajar
- `README.md` — estructura, modelos y **patrones importantes** (aislamiento
  `core/alcance.py`, perfiles, auditoría, bajas lógicas).
- `docs/plan-fases.md` — diagnóstico, decisiones tomadas, fases y pendientes con el cliente.
- `Koape_RRHH_Paquete_Tecnico/Especificacion_Tecnica_Koape_RRHH.md` — especificación funcional.
- `Convenciones-de-Proyecto.txt` — convenciones obligatorias de Koape.
- **`docs/bitacora.md` — qué se cambió, cuándo y por qué.**
- Proyecto de referencia: `C:\proyectos_claude\KOAPE-PORCINO` (mismos patrones).

## Reglas de trabajo
- **Nombres en castellano** (decidido por el cliente, 13/10/2026): `Empleado`,
  `fecha_ingreso`, PK `id`. La especificación usa nombres en inglés
  (`Employee`, `internalId`): se traducen, conservando la semántica.
- **Todo cambio se documenta en el mismo trabajo**: entrada en `docs/bitacora.md`
  y, si corresponde, README, `docs/plan-fases.md` y manuales.
- Cada sección nueva del admin suma su entrada al manual
  (`backend/migracion/templates/admin/migracion/manual.html`); cada pantalla de
  la app, al de `frontend/src/pages/Manual.tsx`.
- Cada modelo nuevo: `ruta_empresa` (y `ruta_sucursal` / `ruta_empleado` si
  corresponde), sus permisos en `cuentas/perfiles.py` y pruebas de acceso en
  `cuentas/tests.py` (los tres perfiles + otra empresa).
- **Reglas legales nunca como constantes**: van versionadas, con fuente y
  aprobación; sin verificar quedan en borrador y bloquean la liquidación real (§9).
- **Históricos cerrados no se modifican**: correcciones = registro nuevo enlazado, con motivo.
- No inventar funcionalidades de negocio: lo no definido se marca PROPUESTA.
- Pruebas: `cd backend && venv\Scripts\python manage.py test` — tienen que pasar
  todas. Después de tocar modelos: `manage.py makemigrations --check --dry-run`
  (tiene que decir "No changes detected"). Frontend: `npm run build` sin errores.
- No usar contraseñas que el cliente pegue en el chat.

## Detalles de esta PC de desarrollo (Windows)
- Python base: `C:\Users\Dell\AppData\Local\Programs\Python\Python312`.
- `pip` falla con error de certificado (intercepción TLS): exportar las raíces de
  Windows (`Cert:\LocalMachine\Root`, `Cert:\CurrentUser\Root`, `Cert:\LocalMachine\CA`)
  a un `.pem` y usar `pip install --cert <archivo>`; para npm, `NODE_EXTRA_CA_CERTS=<archivo>`.
- `git` no está en el PATH (el de GitHub Desktop está en
  `%LOCALAPPDATA%\GitHubDesktop\app-*\resources\app\git\cmd\git.exe`). Repositorio:
  `github.com/gilbertohilgemann/RRHH_KOAPE` (con guion bajo; privado). Se sube por SSH con el alias
  `github-koape-rrhh` (clave `~/.ssh/id_ed25519_koape_rrhh_push`, deploy key con escritura); el repo
  ya tiene `core.sshCommand` apuntando al OpenSSH de Windows. Commitear y subir solo cuando el cliente lo pide.
- Puertos: backend **8004**, frontend **5204** (los demás sistemas usan 8000–8003, 8100, 5173/5174/5183/5201/5203).
- Base local con la demo (`cargar_datos_demo` y después `simular_demo`, 3 años de historia ficticia; la demo
  entra por `/demo`): usuarios `admin_demo`, `gestor_demo`, `empleado_demo`. Cada corrida regenera la clave de la terminal
  demo (la imprime) y deja sin efecto la anterior.
- **Probar desde el celular**: la PC usa la red WiFi Casa 2 (192.168.1.x; el 14/10/2026
  la IP pasó de .36 a .45 por DHCP; a veces también está en Ingenio-Gilgemann = 192.168.2.3).
  El QR de la terminal usa `URL_APP` del `backend/.env` (hoy `http://192.168.1.45:5204`;
  `start.ps1` muestra la IP actual en "Celular"):
  si cambia la IP (DHCP) o la red, actualizarlo y reiniciar el backend. Regla de
  firewall de Windows "Koape RRHH (red local)" (puertos 5204 y 8004, solo red local).
  **El firewall que manda es el de AVG Antivirus**: bloquea las redes "Públicas";
  "WiFi Casa 2" quedó como red Privada en Windows y así el celular entra. Si el
  celular dice "no se puede acceder", revisar primero eso (y AVG).
  La cámara dentro del navegador del celular exige HTTPS: por HTTP se escanea con
  la cámara del teléfono, que abre `/marcar/<token>`.
