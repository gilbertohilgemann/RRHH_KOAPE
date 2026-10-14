# ============================================================================
# Koape RRHH - Instalador para Windows (desarrollo local)
#
# Arma el entorno virtual de Python y node_modules, crea backend\.env con una
# SECRET_KEY real generada en el momento, crea las tablas en SQLite, deja el
# usuario admin fijo y prepara el frontend. Es idempotente: correrlo de nuevo
# no rompe nada (solo reinstala dependencias y confirma el usuario admin).
#
# No instala nada a nivel sistema: si falta Python o Node, avisa y se frena.
# PostgreSQL es aparte y opcional (panel "Migracion de Base de Datos").
#
# Uso:  install.bat     (o .\install.ps1)
# ============================================================================
$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot 'backend'
$FrontendDir = Join-Path $ProjectRoot 'frontend'

function Paso([string]$Texto) { Write-Host "==> $Texto" -ForegroundColor Cyan }
function Ok([string]$Texto) { Write-Host "OK  $Texto" -ForegroundColor Green }
function Aviso([string]$Texto) { Write-Host "!!  $Texto" -ForegroundColor Yellow }
function Falla([string]$Texto) { Write-Host "XX  $Texto" -ForegroundColor Red; exit 1 }

# Corre un ejecutable externo y corta la instalacion si falla (los comandos
# nativos no disparan $ErrorActionPreference por si solos).
function Ejecutar([string]$Descripcion, [scriptblock]$Comando) {
    & $Comando
    if ($LASTEXITCODE -ne 0) { Falla "$Descripcion fallo (codigo $LASTEXITCODE). Revisa el mensaje de arriba." }
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  Koape RRHH - Instalacion (Windows)"
Write-Host "============================================================"
Write-Host ""

# ----------------------------------------------------------------------------
# 1. Requisitos del sistema (solo se revisan, nunca se instalan solos)
# ----------------------------------------------------------------------------
Paso "Revisando requisitos..."
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Falla "No se encontro Python. Instalalo desde https://www.python.org/downloads/ (marca 'Add python.exe to PATH') y volve a correr este instalador." }
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) { Falla "No se encontro Node.js/npm. Instalalo desde https://nodejs.org/ (version LTS) y volve a correr este instalador." }
Ok "Python: $(python --version)"
Ok "Node:   $(node --version)"

# ----------------------------------------------------------------------------
# 2. Backend (Django)
# ----------------------------------------------------------------------------
Paso "Configurando el backend..."
Set-Location $BackendDir

if (-not (Test-Path 'venv')) {
    Ejecutar 'Crear el entorno virtual' { python -m venv venv }
    Ok "Entorno virtual creado."
} else {
    Ok "Entorno virtual ya existia."
}

$py = Join-Path $BackendDir 'venv\Scripts\python.exe'
Ejecutar 'Actualizar pip' { & $py -m pip install --upgrade pip --quiet }
Ejecutar 'Instalar dependencias de Python' { & $py -m pip install -r requirements.txt --quiet }
Ok "Dependencias de Python instaladas."

$envPath = Join-Path $BackendDir '.env'
if (-not (Test-Path $envPath)) {
    $secretKey = & $py -c "import secrets; print(secrets.token_urlsafe(50))"
    $lineas = Get-Content (Join-Path $BackendDir '.env.example') | ForEach-Object {
        if ($_ -like 'SECRET_KEY=*') { "SECRET_KEY=$secretKey" } else { $_ }
    }
    $lineas += 'DB_ENGINE=sqlite'
    # Sin BOM: python-dotenv leeria el BOM como parte del primer nombre de variable.
    [System.IO.File]::WriteAllLines($envPath, [string[]]$lineas)
    Ok "backend\.env creado (con una SECRET_KEY nueva)."
} else {
    Ok "backend\.env ya existia, no se toca."
}

# Clave con la que se cifran los numeros de cuenta bancaria. Se genera UNA
# sola vez: si ya existe nunca se toca (cambiarla haria ilegibles los datos
# ya cifrados).
if (-not (Select-String -Path $envPath -Pattern '^CLAVE_CIFRADO=' -Quiet)) {
    $clave = & $py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    [System.IO.File]::AppendAllText($envPath, "CLAVE_CIFRADO=$clave`n")
    Ok "Clave de cifrado generada (backend\.env)."
}

# En Windows se trabaja en desarrollo: si se agrego o cambio algun modelo, se
# generan sus migraciones aca. En el servidor (install.sh) nunca se generan:
# se usan las que vienen con el codigo.
Ejecutar 'Generar migraciones' { & $py manage.py makemigrations }
Ejecutar 'Aplicar migraciones' { & $py manage.py migrate --noinput }
Ok "Base de datos lista (tablas creadas)."

Ejecutar 'Crear el usuario admin' { & $py manage.py crear_admin }

# ----------------------------------------------------------------------------
# 3. Frontend (React)
# ----------------------------------------------------------------------------
Paso "Configurando el frontend..."
Set-Location $FrontendDir
Ejecutar 'npm install' { npm.cmd install }
Ok "Dependencias de Node instaladas."

$envFront = Join-Path $FrontendDir '.env'
if (-not (Test-Path $envFront)) {
    Copy-Item (Join-Path $FrontendDir '.env.example') $envFront
    Ok "frontend\.env creado (VITE_API_URL vacia: la URL de la API se arma sola)."
}

Set-Location $ProjectRoot

Write-Host ""
Write-Host "============================================================"
Ok "Instalacion completa."
Write-Host "============================================================"
Write-Host ""
Write-Host "  Usuario admin: admin"
Write-Host "  Contrasena:    Admin*2026   (cambiala desde /admin/ apenas entres)"
Write-Host ""
Write-Host "  Base de datos actual: SQLite"
Write-Host "  Para levantar el sistema: start.bat"
Write-Host ""
