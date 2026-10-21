@echo off
title Compilador Gymsis para Windows (.EXE)
cls

echo ========================================================
echo        COMPILADOR DE GYMSIS PARA WINDOWS (.EXE)
echo ========================================================
echo.

REM 1. Detectar Python
set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
    ) else (
        where py >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_CMD=py"
        )
    )
)

if "%PYTHON_CMD%"=="" (
    echo.
    echo [ERROR] No se encontro Python en tu sistema.
    echo Por favor instala Python 3.11 o 3.12 desde https://www.python.org/
    echo IMPORTANTE: Al instalar, marca la casilla "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo [1/4] Python detectado:
%PYTHON_CMD% --version

REM 2. Crear entorno virtual local si no existe
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [2/4] Creando entorno virtual local (.venv)...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo [AVISO] No se pudo crear .venv. Se continuara con Python del sistema.
    ) else (
        set "PYTHON_CMD=.venv\Scripts\python.exe"
    )
) else (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
)

REM 3. Asegurar pip, PyInstaller y dependencias
echo.
echo [3/4] Instalando dependencias y PyInstaller con pip...
%PYTHON_CMD% -m pip install --upgrade pip >nul 2>&1
%PYTHON_CMD% -m pip install pyinstaller -r requirements.txt
if errorlevel 1 (
    echo [AVISO] Reintentando instalacion de PyInstaller...
    %PYTHON_CMD% -m pip install pyinstaller
)

REM Verificar que PyInstaller este instalado
%PYTHON_CMD% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    %PYTHON_CMD% -c "import pyinstaller" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [ERROR CRITICO] PyInstaller no se pudo instalar automaticamente.
        echo Ejecuta manualmente en tu consola CMD:
        echo    %PYTHON_CMD% -m pip install pyinstaller
        echo.
        pause
        exit /b 1
    )
)

REM 4. Compilar ejecutable con PyInstaller
echo.
echo [4/4] Compilando Gymsis.exe con PyInstaller...
echo Esto puede tomar entre 1 y 3 minutos, por favor espera...
echo.

if exist ".venv\Scripts\pyinstaller.exe" (
    .venv\Scripts\pyinstaller.exe packaging\gymsis.spec --noconfirm --clean
) else (
    %PYTHON_CMD% -m PyInstaller packaging\gymsis.spec --noconfirm --clean
)

if errorlevel 1 (
    echo.
    echo [ERROR] Hubo un error durante la compilacion.
    echo Revisa el mensaje de error de PyInstaller mostrado arriba.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo  COMPILACION COMPLETADA CON EXITO!
echo  Tu ejecutable se encuentra en:
echo     dist\Gymsis.exe
echo ========================================================
echo.
pause
