@echo off
:: Arranca el sistema en segundo plano (backend + frontend), sin abrir
:: ventanas nuevas -- ver start.ps1, que hace el trabajo real.
:: Uso: start.bat [start|stop|status|restart|logs]  (por defecto: start)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if "%~1"=="" pause
