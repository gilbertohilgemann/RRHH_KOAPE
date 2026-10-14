@echo off
:: Instalador para Windows (desarrollo local) -- ver install.ps1, que hace
:: el trabajo real. Se corre una sola vez, o de nuevo al actualizar el codigo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
