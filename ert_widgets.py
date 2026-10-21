"""Laboratorio 2 ERT - interfaz web (ipywidgets) para Jupyter/Binder.

Uso en un notebook:
    %matplotlib inline
    from ert_widgets import lanzar
    ui = lanzar()
Usa el mismo motor que la aplicacion de escritorio (ert_motor.py).
"""
import numpy as np
import pandas as pd
import ipywidgets as w
import matplotlib.pyplot as plt
from IPython.display import FileLink, clear_output, display

from ert_motor import MAX_CAPAS, MAX_OBJ, calc_capas, calc_geo, dibujar_capas, dibujar_geo

ESTILO = {"description_width": "170px"}
ANCHO = w.Layout(width="440px")


def _lineal(desc, v, a, b, paso):
    return w.FloatSlider(value=v, min=a, max=b, step=paso, description=desc, style=ESTILO,
                         layout=ANCHO, continuous_update=False)


def _log(desc, v, a=1, b=5000):
    return w.FloatLogSlider(value=v, base=10, min=np.log10(a), max=np.log10(b), step=0.02,
                            description=desc, style=ESTILO, layout=ANCHO,
                            continuous_update=False, readout_format=".3g")


def _lista(desc, opciones, v):
    return w.Dropdown(options=opciones, value=v, description=desc, style=ESTILO, layout=ANCHO)


def _redondear(v):
    return float("%.3g" % v)


class InterfazERT:
    def __init__(self):
        self.historial = []
        self.salida = w.Output()
        self.tabla = w.Output()
        self.estado = w.HTML("Listo.")

        # ---------------- capas ----------------
        self.n_capas = _lista("Número de capas", list(range(1, MAX_CAPAS + 1)), 2)
        espesores, rhos = [1.0, 6.0, 4.0, 4.0, 4.0], [100, 50, 300, 80, 500]
        self.capas = [(_lineal("Capa %d: espesor (m)" % (i + 1), espesores[i], 0.5, 10.0, 0.25),
                       _log("Capa %d: ρ (Ω·m)" % (i + 1), rhos[i])) for i in range(MAX_CAPAS)]
        self.cajas_capa = [w.VBox(list(c)) for c in self.capas]
        self.rho_basam = _log("Basamento: ρ (Ω·m)", 200)

        # ---------------- objetos ----------------
        self.n_obj = _lista("Número de objetos", list(range(0, MAX_OBJ + 1)), 1)
        defecto = [dict(forma="círculo", rho=500, x=0.0, z=-3.0, tam=1.5),
                   dict(forma="tabular", rho=5, x=-8.0, z=-4.0, tam=1.5),
                   dict(forma="dique", rho=1000, x=8.0, z=-4.0, tam=1.0),
                   dict(forma="círculo", rho=10, x=-4.0, z=-9.0, tam=1.0)]
        self.objetos = []
        for dv in defecto:
            self.objetos.append(dict(
                forma=_lista("Forma", ["círculo", "tabular", "dique"], dv["forma"]),
                rho=_log("ρ (Ω·m)", dv["rho"]),
                x=_lineal("Posición x (m)", dv["x"], -12, 12, 0.5),
                z=_lineal("Profundidad del centro (m)", dv["z"], -20, -0.5, 0.25),
                tam=_lineal("Tamaño (m)", dv["tam"], 0.5, 3.0, 0.25)))
        self.paneles_obj = [w.VBox(list(o.values())) for o in self.objetos]
        self.tabs_obj = w.Tab()

        # ---------------- adquisicion e inversion ----------------
        elec = [11, 16, 21, 31, 41]
        self.c = dict(
            n_elec=_lista("Electrodos", elec, 21),
            arreglo=_lista("Arreglo", [("dipolo-dipolo", "dd"), ("Wenner", "wa"),
                                       ("Schlumberger", "slm")], "dd"),
            ruido=_lineal("Ruido (%)", 1.0, 0.0, 5.0, 0.5),
            lam=_log("λ", 20, 1, 1000),
            malla_inv=_lista("Malla de inversión", ["gruesa", "media", "fina"], "media"),
            x_perfil=_lineal("Perfil vertical en x (m)", 9.0, -14.0, 14.0, 0.5))

        # ---------------- geometrias ----------------
        self.g = dict(
            geo=_lista("Geometría", ["circular", "triangular", "esférico"], "circular"),
            rho_f=_log("ρ medio (Ω·m)", 50),
            rho_o=_log("ρ objeto (Ω·m)", 500),
            n_elec=_lista("Electrodos", elec, 21),
            ruido=_lineal("Ruido (%)", 1.0, 0.0, 5.0, 0.5),
            lam=_log("λ", 20, 1, 1000),
            malla_dir=_lista("Malla de simulación", ["gruesa", "media", "fina"], "media"),
            malla_inv=_lista("Malla de inversión", ["gruesa", "media", "fina"], "media"))

        titulo = lambda t: w.HTML("<b>%s</b>" % t)
        nota = lambda t: w.HTML("<span style='color:#666;font-size:90%%'>%s</span>" % t)
        pestana_capas = w.VBox(
            [titulo("Capas (de arriba hacia abajo)"), self.n_capas] + self.cajas_capa
            + [self.rho_basam, titulo("Objetos (cada uno dentro de una sola capa)"), self.n_obj,
               self.tabs_obj,
               nota("Tamaño: radio del círculo; tabular 2×tamaño de ancho y 1× de alto; "
                    "dique 0.6× de ancho y 2.5× de alto."),
               titulo("Adquisición e inversión")] + list(self.c.values()))
        pestana_geo = w.VBox(list(self.g.values())
                             + [nota("La esfera se simula en 3D: tarda ≈ 10–20 s.")])
        self.tabs = w.Tab(children=[pestana_capas, pestana_geo])
        self.tabs.set_title(0, "Modelo con capas")
        self.tabs.set_title(1, "Geometrías")

        self.boton = w.Button(description="Simular e invertir", button_style="primary",
                              icon="play", layout=w.Layout(width="440px", height="40px"))
        self.boton.on_click(lambda _: self.ejecutar())
        b_limpiar = w.Button(description="Limpiar historial", icon="trash")
        b_limpiar.on_click(lambda _: self.limpiar())
        b_csv = w.Button(description="Guardar CSV", icon="download")
        b_csv.on_click(lambda _: self.guardar_csv())
        self.enlace = w.Output()

        self.n_capas.observe(lambda _: self.actualizar(), names="value")
        self.n_obj.observe(lambda _: self.actualizar(), names="value")
        self.actualizar()

        izquierda = w.VBox([self.tabs, self.boton, self.estado],
                           layout=w.Layout(width="470px"))
        self.vista = w.VBox([
            w.HBox([izquierda, self.salida]),
            w.HTML("<h4>Historial de corridas</h4>"),
            w.HBox([b_limpiar, b_csv, self.enlace]),
            self.tabla])

    # --------------------------------------------------------------
    def actualizar(self):
        n, m = self.n_capas.value, self.n_obj.value
        for i, caja in enumerate(self.cajas_capa):
            caja.layout.display = "flex" if i < n else "none"
        self.tabs_obj.children = self.paneles_obj[:m]
        for i in range(m):
            self.tabs_obj.set_title(i, "Objeto %d" % (i + 1))
        self.tabs_obj.layout.display = "flex" if m > 0 else "none"

    def params_capas(self):
        n, m = self.n_capas.value, self.n_obj.value
        p = {k: (_redondear(c.value) if isinstance(c, w.FloatLogSlider) else c.value)
             for k, c in self.c.items()}
        p["capas"] = [(e.value, _redondear(r.value)) for e, r in self.capas[:n]]
        p["rho_basam"] = _redondear(self.rho_basam.value)
        p["objetos"] = [{k: (_redondear(c.value) if isinstance(c, w.FloatLogSlider) else c.value)
                         for k, c in o.items()} for o in self.objetos[:m]]
        return p

    def params_geo(self):
        return {k: (_redondear(c.value) if isinstance(c, w.FloatLogSlider) else c.value)
                for k, c in self.g.items()}

    def ejecutar(self, pestana=None):
        pestana = self.tabs.selected_index if pestana is None else pestana
        if pestana == 0:
            calc, dibujar, p = calc_capas, dibujar_capas, self.params_capas()
        else:
            calc, dibujar, p = calc_geo, dibujar_geo, self.params_geo()
        self.boton.disabled = True
        self.estado.value = "<i>Calculando... (simulación + inversión)</i>"
        try:
            r = calc(**p)
        except Exception as e:
            self.estado.value = "<b style='color:#b00'>No se pudo calcular:</b> %s" % e
            self.boton.disabled = False
            return None
        fig = plt.figure(figsize=(13, 6))
        dibujar(fig, r)
        with self.salida:
            clear_output(wait=True)
            display(fig)
        plt.close(fig)
        m = r["met"]
        txt = ("χ² = %.2f &nbsp;|&nbsp; rRMS = %.2f %% &nbsp;|&nbsp; contraste recuperado (%%): "
               "%s &nbsp;|&nbsp; %d datos &nbsp;|&nbsp; %.1f s"
               % (m["chi2"], m["rrms_pct"], m["recuperacion_pct"], m["datos"], m["tiempo_s"]))
        if p.get("ruido") == 0:
            txt += "<br>Ruido 0 %: datos sin ruido; la inversión asume un error de 0.1 %."
        self.estado.value = txt
        self.historial.append(m)
        with self.tabla:
            clear_output(wait=True)
            display(pd.DataFrame(self.historial).fillna(""))
        self.boton.disabled = False
        return r

    def limpiar(self):
        self.historial.clear()
        with self.tabla:
            clear_output()

    def guardar_csv(self):
        if not self.historial:
            return
        pd.DataFrame(self.historial).to_csv("historial_ert.csv", index=False,
                                            encoding="utf-8-sig")
        with self.enlace:
            clear_output()
            display(FileLink("historial_ert.csv", result_html_prefix="Descargar: "))


def lanzar():
    ui = InterfazERT()
    display(ui.vista)
    return ui
