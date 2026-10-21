@echo off
setlocal EnableDelayedExpansion
title Gymsis - Control de Gimnasio
cls

echo ========================================================
echo         GYMSIS - CONTROL DE ACCESO Y GESTION
echo ========================================================
echo.

REM 1. Activar servicio de Tarjeta Inteligente de Windows para el lector NFC
sc.exe start SCardSvr >nul 2>&1
net start SCardSvr >nul 2>&1

REM Si existe la version compilada nativa, ejecutarla directamente en 1 clic
if exist "Gymsis.exe" (
    echo [INFO] Iniciando Gymsis Desktop Nativo (Gymsis.exe)...
    set "GYMSIS_RUN_MODE=desktop"
    start "" "Gymsis.exe"
    exit /b 0
)
if exist "dist\Gymsis.exe" (
    echo [INFO] Iniciando Gymsis Desktop Nativo (dist\Gymsis.exe)...
    set "GYMSIS_RUN_MODE=desktop"
    start "" "dist\Gymsis.exe"
    exit /b 0
)

REM 2. Detectar Python o entorno virtual existente
set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    goto PYTHON_READY
)

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
    goto PYTHON_READY
)

REM Buscar Python en PATH
where python >nul 2>&1
if not errorlevel 1 (
    set "BASE_PYTHON=python"
    goto CREAR_VENV
)

where py >nul 2>&1
if not errorlevel 1 (
    set "BASE_PYTHON=py -3"
    goto CREAR_VENV
)

REM Buscar en ubicaciones estandar de Windows (AppData / Program Files)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%D\python.exe" (
        set "BASE_PYTHON=%%D\python.exe"
        goto CREAR_VENV
    )
)
for /d %%D in ("%LOCALAPPDATA%\Python\*") do (
    if exist "%%D\python.exe" (
        set "BASE_PYTHON=%%D\python.exe"
        goto CREAR_VENV
    )
)
for /d %%D in ("%ProgramFiles%\Python*") do (
    if exist "%%D\python.exe" (
        set "BASE_PYTHON=%%D\python.exe"
        goto CREAR_VENV
    )
)

echo.
echo [ERROR CRITICO] No se encontro Python instalado en esta computadora.
echo Para ejecutar Gymsis, por favor descarga e instala Python desde:
echo    https://www.python.org/downloads/
echo.
echo IMPORTANTE: Durante la instalacion, marca la casilla:
echo    [X] Add Python to PATH (Agregar Python a las variables de entorno)
echo.
pause
exit /b 1

:CREAR_VENV
echo [1/3] Creando entorno virtual local (.venv)...
%BASE_PYTHON% -m venv .venv
if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo crear el entorno virtual con %BASE_PYTHON%.
    pause
    exit /b 1
)
set "PYTHON_EXE=.venv\Scripts\python.exe"

:PYTHON_READY
echo [1/3] Verificando dependencias de escritorio y drivers...

REM 3. Verificar e instalar librerias requeridas
%PYTHON_EXE% -c "import flet, flet_desktop, openpyxl, edge_tts" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando dependencias de Gymsis (esto se hace solo la primera vez)...
    %PYTHON_EXE% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Ocurrio un fallo al descargar las librerias.
        echo Verifica tu conexion a internet e intenta nuevamente.
        pause
        exit /b 1
    )
)

REM 4. Liberar puertos o instancias previas huerfanas
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8550" 2^>nul') do (
    if not "%%a"=="" taskkill /F /PID %%a >nul 2>&1
)

echo.
echo [2/2] Iniciando Gymsis como Aplicacion de Escritorio Nativa...
set "GYMSIS_RUN_MODE=desktop"
%PYTHON_EXE% main.py

if errorlevel 1 (
    echo.
    echo ========================================================
    echo  [AVISO] La aplicacion se cerro con error.
    echo  Revisa el mensaje de arriba para mas detalles.
    echo ========================================================
    pause
)
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
