@echo off
setlocal EnableDelayedExpansion
title Gymsis - Servidor Web
cls

echo ========================================================
echo         GYMSIS - MODO SERVIDOR WEB
echo ========================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

REM Liberar puerto 8550
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8550" 2^>nul') do (
    if not "%%a"=="" taskkill /F /PID %%a >nul 2>&1
)

set "GYMSIS_RUN_MODE=web"
set "GYMSIS_HOST=0.0.0.0"
set "GYMSIS_PORT=8550"
set "GYMSIS_WEB_RENDERER=auto"

echo [1/2] Iniciando servidor web en http://localhost:8550...
start "" %PYTHON_EXE% main.py

echo [2/2] Abriendo navegador...
timeout /t 3 /nobreak >nul
start http://localhost:8550/

echo.
echo ========================================================
echo  Servidor activo en: http://localhost:8550/
echo  Para cerrar el servidor, presione cualquier tecla.
echo ========================================================
pause >nul

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8550" 2^>nul') do (
    if not "%%a"=="" taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Gymsis*" >nul 2>&1
echo Servidor cerrado.
