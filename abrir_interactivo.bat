@echo off
REM ==================================================================
REM  Abre la aplicacion interactiva del Laboratorio 2 ERT (ventana propia,
REM  sin Jupyter ni VS Code). Doble clic y listo.
REM  Esta ventana negra muestra mensajes; no la cierres mientras usas la app.
REM ==================================================================
set "MAMBA_ROOT_PREFIX=%USERPROFILE%\micromamba"
set "MM=%MAMBA_ROOT_PREFIX%\micromamba.exe"

if not exist "%MM%" (
    echo No encuentro el entorno. Corre primero instalar_entorno.bat
    pause
    exit /b 1
)

cd /d "%~dp0"
echo Abriendo la aplicacion interactiva...
"%MM%" run -n ert python ert_interactivo.py
if errorlevel 1 pause
