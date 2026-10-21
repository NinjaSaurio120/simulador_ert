@echo off
REM ==================================================================
REM  Instala (o repara) el entorno "ert" para el laboratorio ERT.
REM  No necesita Anaconda ni permisos de administrador: todo queda en
REM  %USERPROFILE%\micromamba. Tarda unos 5-10 minutos.
REM
REM  IMPORTANTE: cierra JupyterLab (y la ventana de abrir_laboratorio.bat)
REM  antes de correr esto. Si el entorno esta en uso, Windows bloquea sus
REM  archivos y la instalacion puede quedar a medias.
REM ==================================================================
set "MAMBA_ROOT_PREFIX=%USERPROFILE%\micromamba"
set "MM=%MAMBA_ROOT_PREFIX%\micromamba.exe"
set "ENV=%MAMBA_ROOT_PREFIX%\envs\ert"
set "PAQUETES=python=3.11 pygimli=1.5.5 numpy=1.26 matplotlib=3.8 libblas=*=*openblas pandas jupyterlab ipykernel ipywidgets tetgen"

echo.
echo  Antes de seguir: CIERRA JupyterLab y la ventana de abrir_laboratorio.bat
echo.
pause

if not exist "%MAMBA_ROOT_PREFIX%" mkdir "%MAMBA_ROOT_PREFIX%"

if not exist "%MM%" (
    echo Descargando micromamba...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64' -OutFile '%MM%'"
)

if exist "%ENV%\conda-meta" (
    echo.
    echo El entorno "ert" ya existe: se actualiza sin borrarlo...
    "%MM%" install -y -n ert -c gimli -c conda-forge %PAQUETES%
) else (
    if exist "%ENV%" (
        echo.
        echo Hay una carpeta "ert" danada ^(sin conda-meta^). Se elimina y se crea de nuevo...
        rmdir /s /q "%ENV%"
    )
    echo.
    echo Creando el entorno "ert"...
    "%MM%" create -y -n ert -c gimli -c conda-forge %PAQUETES%
)
if errorlevel 1 goto :error

REM El pyzmq de conda-forge para Windows trae un bug (zeromq "Bad file
REM descriptor ... epoll.cpp") que impide arrancar el kernel de Jupyter.
REM El de PyPI trae su propia libzmq y funciona.
echo.
echo Corrigiendo pyzmq...
"%MM%" run -n ert python -m pip install -q --force-reinstall --no-deps pyzmq
if errorlevel 1 goto :error

echo.
echo Verificando...
"%MM%" run -n ert python -c "import numpy as np, pygimli as pg; np.linalg.inv(np.eye(3)); print('OK  pygimli', pg.__version__, ' numpy', np.__version__)"
if errorlevel 1 goto :error

echo.
echo ==============================================================
echo  Listo. Ahora abre el laboratorio con abrir_laboratorio.bat
echo ==============================================================
pause
exit /b 0

:error
echo.
echo Algo fallo. Copia el mensaje de arriba y pidele ayuda a Claude.
pause
exit /b 1
