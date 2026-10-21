@echo off
title Gymsis - Control de Gimnasio
cls

echo ========================================================
echo         GYMSIS - CONTROL DE ACCESO Y GESTION
echo ========================================================
echo.

REM 1. Detectar Python o entorno virtual
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [1/3] Verificando entorno de ejecucion...
%PYTHON_EXE% --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] No se encontro Python en el sistema.
    echo Por favor instale Python 3.11 o 3.12 desde python.org
    echo Recuerde marcar la casilla: Add Python to PATH al instalarlo.
    echo.
    pause
    exit /b 1
)

REM 2. Matar procesos viejos para liberar puertos y evitar conflictos
echo [INFO] Verificando y liberando instancias previas de Gymsis...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8550" 2^>nul') do (
    if not "%%a"=="" taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Gymsis*" >nul 2>&1

REM 3. Preparar entorno virtual en Windows si no existe
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creando entorno virtual local en Windows...
    %PYTHON_EXE% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    set "PYTHON_EXE=.venv\Scripts\python.exe"
)

REM 4. Asegurar dependencias de escritorio
%PYTHON_EXE% -c "import flet_desktop" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando librerias de escritorio (Flet)...
    %PYTHON_EXE% -m pip install -r requirements.txt
)

echo.
echo ========================================================
echo  MODO DE EJECUCION:
echo  1. Ventana de Escritorio (App Nativa - Recomendado)
echo  2. Modo Navegador Web (http://localhost:8550)
echo ========================================================
set /p OPCION="Seleccione una opcion [1 o 2] (Enter para 1): "

if "%OPCION%"=="2" (
    goto MODO_WEB
) else (
    goto MODO_DESKTOP
)

:MODO_DESKTOP
echo.
echo [2/3] Iniciando Gymsis como App de Escritorio...
set "GYMSIS_RUN_MODE=desktop"
%PYTHON_EXE% main.py
goto FIN

:MODO_WEB
echo.
echo [2/3] Iniciando servidor Gymsis en http://localhost:8550...
set "GYMSIS_RUN_MODE=web"
set "GYMSIS_HOST=0.0.0.0"
set "GYMSIS_PORT=8550"
set "GYMSIS_WEB_RENDERER=auto"

start "" %PYTHON_EXE% main.py

echo [3/3] Abriendo panel en su navegador...
timeout /t 3 /nobreak >nul
start http://localhost:8550/

echo.
echo ========================================================
echo  Servidor web activo en: http://localhost:8550/
echo  Para cerrar el servidor, presione cualquier tecla.
echo ========================================================
pause >nul
goto FIN

:FIN
echo.
echo Cerrando procesos de Gymsis y liberando recursos...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8550" 2^>nul') do (
    if not "%%a"=="" taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Gymsis*" >nul 2>&1
echo Gracias por usar Gymsis.
timeout /t 2 /nobreak >nul
