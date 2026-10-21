# Laboratorio 2 — Tomografía de Resistividad Eléctrica (ERT)

Simulador interactivo de ERT 2D con [PyGIMLi](https://www.pygimli.org): se construye un
subsuelo sintético (varias capas y objetos), se simula la medición con ruido, se invierte
y se compara el modelo invertido con el verdadero.

Maestría en Ciencias – Geofísica · Universidad Nacional de Colombia
Milton Daniel Díaz Barrera · Daniela Liseth Saballet Franco

## Usarlo en el navegador (Binder, sin instalar nada)

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/NinjaSaurio120/simulador_ert/HEAD?urlpath=lab/tree/ERT_interactivo.ipynb)

1. Clic en el botón **launch binder** (o abre https://mybinder.org/v2/gh/NinjaSaurio120/simulador_ert/HEAD?urlpath=lab/tree/ERT_interactivo.ipynb). La primera vez tarda **10–20 minutos** en preparar el
   entorno; después suele abrir en 1–2 minutos.
2. Se abre `ERT_interactivo.ipynb`. Ejecuta la celda (▶ o **Run → Run All Cells**).
3. Elige la pestaña, mueve los controles y pulsa **Simular e invertir**. Cada corrida se
   agrega al historial.

Binder borra la sesión tras unos 10 minutos sin uso: descarga lo que quieras conservar
(botón **Guardar CSV** del historial, o clic derecho sobre un archivo → *Download*).

## Usarlo en un computador con Windows

1. `instalar_entorno.bat` (una sola vez; instala todo en `%USERPROFILE%\micromamba`).
2. `abrir_interactivo.bat`: abre la aplicación de escritorio, con los mismos controles.

## Archivos

| Archivo | Qué es |
|---|---|
| `ERT_interactivo.ipynb` | Simulador interactivo para el navegador (Binder / JupyterLab) |
| `ert_widgets.py` | Interfaz web del simulador (ipywidgets) |
| `ert_interactivo.py` | Aplicación de escritorio (ventana propia, Windows) |
| `ert_motor.py` | Motor común: modelado, inversión, métricas y figuras |
| `Anexo_Laboratorio_2_ERT.ipynb` | Código y resultados del informe del laboratorio |
| `prueba_rapida.ipynb` | Prueba de 1 minuto: confirma que la inversión funciona |
| `environment.yml` | Receta de instalación que usa Binder |

## Qué se puede variar

- **Modelo con capas:** de 1 a 5 capas (espesor y resistividad) más el basamento, y de 0 a 4
  objetos (círculo, tabular o dique) con resistividad, posición, profundidad y tamaño propios.
- **Geometrías:** objeto circular (cilindro 2.5D), triangular (prisma 2.5D) o esférico (3D).
- **Adquisición e inversión:** número de electrodos, arreglo (dipolo-dipolo, Wenner,
  Schlumberger), ruido, λ, malla de simulación y malla de inversión.

Métricas: χ², rRMS, contraste recuperado de cada objeto (fracción en escala logarítmica) y,
en geometrías, anomalía máxima en ρa y resistividad máxima recuperada.
