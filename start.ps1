# ============================================================================
# Koape RRHH - Arranque del sistema (Windows, desarrollo local)
#
# Levanta el backend (Django) y el frontend (Vite) en segundo plano de
# verdad -- sin abrir ventanas nuevas -- con su salida redirigida a
# logs\backend.log / logs\frontend.log. Mismo espiritu que start.sh en
# Linux: PID guardado en .run\, para poder frenar/ver el estado despues.
#
# Uso:
#   .\start.ps1            # levanta todo
#   .\start.ps1 stop       # frena todo
#   .\start.ps1 status     # muestra si esta corriendo
#   .\start.ps1 restart
#   .\start.ps1 logs       # sigue los logs en vivo (Ctrl+C para salir)
# ============================================================================
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'restart', 'logs')]
    [string]$Action = 'start'
)

$ProjectRoot = $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot 'backend'
$FrontendDir = Join-Path $ProjectRoot 'frontend'
$RunDir = Join-Path $ProjectRoot '.run'
$LogDir = Join-Path $ProjectRoot 'logs'
$BackendPidFile = Join-Path $RunDir 'backend.pid'
$FrontendPidFile = Join-Path $RunDir 'frontend.pid'
# Puertos propios (no los tipicos 8000/5173) para no chocar con otras
# aplicaciones. Si se cambian, cambiar tambien frontend\src\services\api.ts
# y frontend\vite.config.ts.
$BackendPort = 8004
$FrontendPort = 5204

New-Item -ItemType Directory -Force -Path $RunDir, $LogDir | Out-Null

function Test-ProcesoCorriendo([string]$PidFile) {
    if (-not (Test-Path $PidFile)) { return $false }
    $procId = Get-Content $PidFile -ErrorAction SilentlyContinue
    if (-not $procId) { return $false }
    return [bool](Get-Process -Id $procId -ErrorAction SilentlyContinue)
}

function Test-PuertoOcupado([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Get-IpLocal {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
        Select-Object -First 1 -ExpandProperty IPAddress
}

function Start-Proceso([string]$Name, [string]$PidFile, [int]$Port, [string]$FilePath, [string[]]$ArgList, [string]$WorkDir, [string]$LogFile) {
    if (Test-ProcesoCorriendo $PidFile) {
        Write-Host "$Name ya estaba corriendo (PID $(Get-Content $PidFile))." -ForegroundColor Yellow
        return
    }
    if (Test-PuertoOcupado $Port) {
        Write-Host "El puerto $Port ya lo esta usando otro proceso (no nuestro, segun $PidFile)." -ForegroundColor Red
        Write-Host "No arranco $Name ahi para no interferir con lo que ya este corriendo." -ForegroundColor Red
        return
    }

    $outLog = Join-Path $LogDir "$LogFile.log"
    $errLog = Join-Path $LogDir "$LogFile-error.log"
    $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgList -WorkingDirectory $WorkDir `
        -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
    Start-Sleep -Milliseconds 500
    if ($proc.HasExited) {
        Write-Host "$Name no arranco -- revisa $errLog" -ForegroundColor Red
        return
    }
    $proc.Id | Out-File -FilePath $PidFile -Encoding ascii
    Write-Host "$Name arriba (PID $($proc.Id))." -ForegroundColor Green
}

function Start-Todo {
    if (-not (Test-Path (Join-Path $BackendDir 'venv'))) {
        Write-Host "No existe backend\venv -- corre install.bat primero." -ForegroundColor Red
        return
    }
    if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
        Write-Host "No existe frontend\node_modules -- corre install.bat primero." -ForegroundColor Red
        return
    }

    $pythonExe = Join-Path $BackendDir 'venv\Scripts\python.exe'

    if (-not (Test-ProcesoCorriendo $BackendPidFile)) {
        Write-Host "Aplicando migraciones pendientes..."
        Push-Location $BackendDir
        & $pythonExe manage.py migrate --noinput | Out-Null
        Pop-Location
    }

    Start-Proceso -Name 'Backend' -PidFile $BackendPidFile -Port $BackendPort `
        -FilePath $pythonExe -ArgList @('manage.py', 'runserver', "0.0.0.0:$BackendPort") `
        -WorkDir $BackendDir -LogFile 'backend'

    Start-Proceso -Name 'Frontend' -PidFile $FrontendPidFile -Port $FrontendPort `
        -FilePath 'npm.cmd' -ArgList @('run', 'dev', '--', '--host', '--port', "$FrontendPort", '--strictPort') `
        -WorkDir $FrontendDir -LogFile 'frontend'

    $lanIp = Get-IpLocal
    Write-Host ""
    Write-Host "  Aplicacion: http://localhost:$FrontendPort"
    Write-Host "  Admin:        http://127.0.0.1:$BackendPort/admin/"
    if ($lanIp) {
        Write-Host "  Celular (misma red Wi-Fi): http://$($lanIp):$FrontendPort"
    }
    Write-Host ""
    Write-Host "  Logs:          .\start.ps1 logs"
    Write-Host "  Estado:        .\start.ps1 status"
    Write-Host "  Frenar todo:   .\start.ps1 stop"
}

function Stop-Todo {
    foreach ($svc in @(
        @{ Name = 'Backend'; File = $BackendPidFile },
        @{ Name = 'Frontend'; File = $FrontendPidFile }
    )) {
        if (Test-ProcesoCorriendo $svc.File) {
            $procId = Get-Content $svc.File
            # El autoreload de Django y npm.cmd encadenan varios procesos
            # hijos (hasta 3-4 niveles) -- taskkill /T mata todo el arbol de
            # una sola vez; matar solo el PID guardado deja huerfanos
            # ocupando el puerto.
            taskkill /PID $procId /T /F *> $null
            Remove-Item $svc.File -Force
            Write-Host "$($svc.Name) detenido." -ForegroundColor Green
        } else {
            Write-Host "$($svc.Name) ya estaba detenido." -ForegroundColor Yellow
            Remove-Item $svc.File -Force -ErrorAction SilentlyContinue
        }
    }
}

function Show-Estado {
    foreach ($svc in @(
        @{ Name = 'Backend'; File = $BackendPidFile; Port = $BackendPort },
        @{ Name = 'Frontend'; File = $FrontendPidFile; Port = $FrontendPort }
    )) {
        if (Test-ProcesoCorriendo $svc.File) {
            Write-Host "$($svc.Name): corriendo (PID $(Get-Content $svc.File), puerto $($svc.Port))" -ForegroundColor Green
        } else {
            Write-Host "$($svc.Name): detenido" -ForegroundColor Yellow
        }
    }
}

function Show-Logs {
    $files = @((Join-Path $LogDir 'backend.log'), (Join-Path $LogDir 'backend-error.log'), (Join-Path $LogDir 'frontend.log')) |
        Where-Object { Test-Path $_ }
    if (-not $files) {
        Write-Host "Todavia no hay logs -- corre '.\start.ps1' primero." -ForegroundColor Yellow
        return
    }
    Write-Host "Siguiendo los logs en vivo (Ctrl+C para salir)..." -ForegroundColor Cyan
    Get-Content -Path $files -Wait -Tail 20
}

switch ($Action) {
    'start' { Start-Todo }
    'stop' { Stop-Todo }
    'status' { Show-Estado }
    'restart' { Stop-Todo; Start-Sleep -Seconds 1; Start-Todo }
    'logs' { Show-Logs }
}
