"""Laboratorio 2 ERT - aplicacion interactiva de escritorio (para mostrar en clase).

Abrir con abrir_interactivo.bat (doble clic). Prueba automatica: python ert_interactivo.py --prueba <carpeta>
"""
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")
import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from ert_motor import (MAX_CAPAS, MAX_OBJ, calc_capas, calc_geo, dibujar_capas, dibujar_geo)


# ======================================================================
# Ventana
# ======================================================================
class Control:
    """Fila con etiqueta + control; .valor() devuelve el valor; .mostrar(bool) la oculta."""

    def __init__(self, padre, fila, texto, tipo, **kw):
        self.widgets = [ttk.Label(padre, text=texto)]
        self.widgets[0].grid(row=fila, column=0, sticky="e", padx=(4, 6), pady=2)
        self.tipo = tipo
        if tipo == "lineal":
            self.var = tk.DoubleVar(value=kw["v"])
            s = tk.Scale(padre, variable=self.var, from_=kw["a"], to=kw["b"],
                         resolution=kw["paso"], orient="horizontal", length=210, showvalue=True)
            s.grid(row=fila, column=1, sticky="w")
            self.widgets.append(s)
        elif tipo == "log":
            self.var = tk.DoubleVar(value=np.log10(kw["v"]))
            self.lbl = ttk.Label(padre, width=7)
            s = tk.Scale(padre, variable=self.var, from_=np.log10(kw["a"]), to=np.log10(kw["b"]),
                         resolution=0.01, orient="horizontal", length=210, showvalue=False,
                         command=lambda _: self._rotulo())
            s.grid(row=fila, column=1, sticky="w")
            self.lbl.grid(row=fila, column=2, sticky="w")
            self.widgets += [s, self.lbl]
            self._rotulo()
        else:   # lista
            self.var = tk.StringVar(value=str(kw["v"]))
            cb = ttk.Combobox(padre, textvariable=self.var, values=[str(o) for o in kw["opciones"]],
                              state="readonly", width=18)
            cb.grid(row=fila, column=1, sticky="w", pady=2)
            self.widgets.append(cb)
            self.conv = kw.get("conv", str)

    def _rotulo(self):
        self.lbl.config(text="%.3g" % self.valor())

    def valor(self):
        if self.tipo == "lineal":
            return float(self.var.get())
        if self.tipo == "log":
            return float("%.3g" % 10 ** self.var.get())
        return self.conv(self.var.get())

    def fijar(self, v):
        self.var.set(np.log10(v) if self.tipo == "log" else v)
        if self.tipo == "log":
            self._rotulo()

    def mostrar(self, si):
        for w_ in self.widgets:
            w_.grid() if si else w_.grid_remove()


class Desplazable(ttk.Frame):
    """Marco con barra de desplazamiento vertical (y rueda del mouse)."""

    def __init__(self, padre, alto=640):
        super().__init__(padre)
        self.canvas = tk.Canvas(self, highlightthickness=0, height=alto, width=420)
        barra_v = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.interior = ttk.Frame(self.canvas)
        self.interior.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self.canvas.configure(yscrollcommand=barra_v.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        barra_v.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all(
            "<MouseWheel>", lambda ev: self.canvas.yview_scroll(int(-ev.delta / 120), "units")))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))


class App:
    def __init__(self, root):
        self.root = root
        root.title("Laboratorio 2 ERT — interactivo")
        root.geometry("1550x930")
        self.cola = queue.Queue()
        self.historial = []
        self.ocupado = False

        izq = ttk.Frame(root, padding=6)
        izq.pack(side="left", fill="y")
        der = ttk.Frame(root, padding=6)
        der.pack(side="left", fill="both", expand=True)

        self.tabs = ttk.Notebook(izq)
        self.tabs.pack(fill="both", expand=True)
        d1 = Desplazable(self.tabs)
        t1 = d1.interior
        t2 = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(d1, text="Modelo con capas")
        self.tabs.add(t2, text="Geometrías")
        elec = dict(opciones=[11, 16, 21, 31, 41], v=21, conv=int)

        def sec(padre, texto, fila):
            ttk.Label(padre, text=texto, font=("Segoe UI", 10, "bold")).grid(
                row=fila, column=0, columnspan=3, sticky="w", pady=(8, 2))

        # ---------------- capas ----------------
        f = 0
        sec(t1, "Capas (de arriba hacia abajo)", f); f += 1
        self.n_capas = Control(t1, f, "Número de capas", "lista",
                               opciones=list(range(1, MAX_CAPAS + 1)), v=2, conv=int); f += 1
        self.n_capas.var.trace_add("write", lambda *a: self.actualizar_visibles())
        espesores = [1.0, 6.0, 4.0, 4.0, 4.0]
        rhos = [100, 50, 300, 80, 500]
        self.capas = []
        for i in range(MAX_CAPAS):
            e = Control(t1, f, "Capa %d: espesor (m)" % (i + 1), "lineal",
                        v=espesores[i], a=0.5, b=10.0, paso=0.25); f += 1
            r = Control(t1, f, "Capa %d: ρ (Ω·m)" % (i + 1), "log", v=rhos[i], a=1, b=5000); f += 1
            self.capas.append((e, r))
        self.rho_basam = Control(t1, f, "Basamento: ρ (Ω·m)", "log", v=200, a=1, b=5000); f += 1

        # ---------------- objetos ----------------
        sec(t1, "Objetos (cada uno dentro de una sola capa)", f); f += 1
        self.n_obj = Control(t1, f, "Número de objetos", "lista",
                             opciones=list(range(0, MAX_OBJ + 1)), v=1, conv=int); f += 1
        self.n_obj.var.trace_add("write", lambda *a: self.actualizar_visibles())
        self.nb_obj = ttk.Notebook(t1)
        self.nb_obj.grid(row=f, column=0, columnspan=3, sticky="we", pady=4); f += 1
        defecto = [dict(forma="círculo", rho=500, x=0.0, z=-3.0, tam=1.5),
                   dict(forma="tabular", rho=5, x=-8.0, z=-4.0, tam=1.5),
                   dict(forma="dique", rho=1000, x=8.0, z=-4.0, tam=1.0),
                   dict(forma="círculo", rho=10, x=-4.0, z=-9.0, tam=1.0)]
        self.objetos = []
        for i in range(MAX_OBJ):
            fr = ttk.Frame(self.nb_obj, padding=4)
            self.nb_obj.add(fr, text="Objeto %d" % (i + 1))
            dv = defecto[i]
            self.objetos.append(dict(
                forma=Control(fr, 0, "Forma", "lista", opciones=["círculo", "tabular", "dique"],
                              v=dv["forma"]),
                rho=Control(fr, 1, "ρ (Ω·m)", "log", v=dv["rho"], a=1, b=5000),
                x=Control(fr, 2, "Posición x (m)", "lineal", v=dv["x"], a=-12, b=12, paso=0.5),
                z=Control(fr, 3, "Profundidad del centro (m)", "lineal", v=dv["z"], a=-20,
                          b=-0.5, paso=0.25),
                tam=Control(fr, 4, "Tamaño (m)", "lineal", v=dv["tam"], a=0.5, b=3.0,
                            paso=0.25)))
        ttk.Label(t1, text="Tamaño: radio del círculo; el tabular mide 2×tamaño de ancho\n"
                           "y 1×tamaño de alto; el dique, 0.6×tamaño de ancho y 2.5×de alto.",
                  foreground="#666").grid(row=f, column=0, columnspan=3, sticky="w"); f += 1

        # ---------------- adquisicion e inversion ----------------
        sec(t1, "Adquisición e inversión", f); f += 1
        self.c = {}
        for k, txt, tipo, kw in [
                ("n_elec", "Electrodos", "lista", elec),
                ("arreglo", "Arreglo", "lista", dict(opciones=["dd", "wa", "slm"], v="dd")),
                ("ruido", "Ruido (%)", "lineal", dict(v=1.0, a=0.0, b=5.0, paso=0.5)),
                ("lam", "λ", "log", dict(v=20, a=1, b=1000)),
                ("malla_inv", "Malla de inversión", "lista",
                 dict(opciones=["gruesa", "media", "fina"], v="media")),
                ("x_perfil", "Perfil vertical en x (m)", "lineal",
                 dict(v=9.0, a=-14.0, b=14.0, paso=0.5))]:
            self.c[k] = Control(t1, f, txt, tipo, **kw); f += 1
        ttk.Label(t1, text="Arreglo: dd = dipolo-dipolo, wa = Wenner, slm = Schlumberger",
                  foreground="#666").grid(row=f, column=0, columnspan=3, sticky="w")
        self.actualizar_visibles()

        # ---------------- pestaña geometrias ----------------
        self.g = {}
        filas2 = [("geo", "Geometría", "lista",
                   dict(opciones=["circular", "triangular", "esférico"], v="circular")),
                  ("rho_f", "ρ medio (Ω·m)", "log", dict(v=50, a=1, b=5000)),
                  ("rho_o", "ρ objeto (Ω·m)", "log", dict(v=500, a=1, b=5000)),
                  ("n_elec", "Electrodos", "lista", dict(elec)),
                  ("ruido", "Ruido (%)", "lineal", dict(v=1.0, a=0.0, b=5.0, paso=0.5)),
                  ("lam", "λ", "log", dict(v=20, a=1, b=1000)),
                  ("malla_dir", "Malla de simulación", "lista",
                   dict(opciones=["gruesa", "media", "fina"], v="media")),
                  ("malla_inv", "Malla de inversión", "lista",
                   dict(opciones=["gruesa", "media", "fina"], v="media"))]
        for i, (k, txt, tipo, kw) in enumerate(filas2):
            self.g[k] = Control(t2, i, txt, tipo, **kw)
        ttk.Label(t2, text="La esfera se simula en 3D: tarda ≈ 10 s.",
                  foreground="#666").grid(row=len(filas2), column=0, columnspan=3, sticky="w",
                                          pady=6)

        self.boton = ttk.Button(izq, text="▶  Simular e invertir", command=self.ejecutar)
        self.boton.pack(fill="x", pady=(10, 4), ipady=6)
        self.estado = ttk.Label(izq, text="Listo.", wraplength=420, foreground="#1f4e79")
        self.estado.pack(fill="x")

        self.fig = Figure(figsize=(12, 5.2), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=der)
        NavigationToolbar2Tk(self.canvas, der).pack(side="top", fill="x")
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

        caja = ttk.Frame(der)
        caja.pack(side="top", fill="both", expand=False, pady=(6, 0))
        barra_h = ttk.Frame(caja)
        barra_h.pack(fill="x")
        ttk.Label(barra_h, text="Historial de corridas", font=("Segoe UI", 10, "bold")).pack(
            side="left")
        ttk.Button(barra_h, text="Exportar CSV", command=self.exportar).pack(side="right")
        ttk.Button(barra_h, text="Limpiar", command=self.limpiar).pack(side="right", padx=4)
        self.cols = ["#", "pestaña", "capas", "objetos", "electrodos", "arreglo", "ruido_pct",
                     "lam", "malla_dir", "malla_inv", "datos", "celdas_inv",
                     "anomalia_rhoa_pct", "rho_max_rec", "chi2", "rrms_pct", "recuperacion_pct",
                     "tiempo_s"]
        anchos = {"#": 35, "capas": 200, "objetos": 260, "recuperacion_pct": 170}
        self.tabla = ttk.Treeview(caja, columns=self.cols, show="headings", height=7)
        for col in self.cols:
            self.tabla.heading(col, text=col)
            self.tabla.column(col, width=anchos.get(col, 62), anchor="center", stretch=False)
        hs = ttk.Scrollbar(caja, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(xscrollcommand=hs.set)
        self.tabla.pack(fill="both", expand=True)
        hs.pack(fill="x")
        self.root.after(100, self.revisar_cola)

    # --------------------------------------------------------------
    def actualizar_visibles(self):
        try:
            n, m = self.n_capas.valor(), self.n_obj.valor()
        except (ValueError, AttributeError):
            return
        for i, (e, r) in enumerate(self.capas):
            e.mostrar(i < n)
            r.mostrar(i < n)
        if hasattr(self, "nb_obj"):
            for i in range(MAX_OBJ):
                self.nb_obj.tab(i, state="normal" if i < m else "hidden")
            if m == 0:
                self.nb_obj.grid_remove()
            else:
                self.nb_obj.grid()
                actual = self.nb_obj.select()          # "" si no hay pestaña seleccionada
                if not actual or self.nb_obj.index(actual) >= m:
                    self.nb_obj.select(0)

    def params_capas(self):
        n, m = self.n_capas.valor(), self.n_obj.valor()
        p = {k: v.valor() for k, v in self.c.items()}
        p["capas"] = [(e.valor(), r.valor()) for e, r in self.capas[:n]]
        p["rho_basam"] = self.rho_basam.valor()
        p["objetos"] = [{k: c.valor() for k, c in o.items()} for o in self.objetos[:m]]
        return p

    def parametros(self):
        if self.tabs.index("current") == 0:
            return calc_capas, dibujar_capas, self.params_capas()
        return calc_geo, dibujar_geo, {k: v.valor() for k, v in self.g.items()}

    def ejecutar(self):
        if self.ocupado:
            return
        calc, dibujar, p = self.parametros()
        self.ocupado = True
        self.boton.state(["disabled"])
        self.estado.config(text="Calculando...  (simulación + inversión)")

        def trabajo():
            try:
                self.cola.put(("ok", dibujar, calc(**p), p))
            except Exception as e:          # se muestra en la ventana
                self.cola.put(("error", None, e, p))

        threading.Thread(target=trabajo, daemon=True).start()

    def revisar_cola(self):
        try:
            estado, dibujar, r, p = self.cola.get_nowait()
        except queue.Empty:
            self.root.after(100, self.revisar_cola)
            return
        self.ocupado = False
        self.boton.state(["!disabled"])
        if estado == "error":
            self.estado.config(text="No se pudo calcular.")
            messagebox.showwarning("Parámetros no válidos", str(r))
        else:
            self.mostrar(dibujar, r, p)
        self.root.after(100, self.revisar_cola)

    def mostrar(self, dibujar, r, p):
        dibujar(self.fig, r)
        self.canvas.draw()
        m = r["met"]
        txt = ("χ² = %.2f   |   rRMS = %.2f %%   |   contraste recuperado (%%): %s   |   "
               "%d datos   |   %.1f s" % (m["chi2"], m["rrms_pct"], m["recuperacion_pct"],
                                         m["datos"], m["tiempo_s"]))
        if p.get("ruido") == 0:
            txt += "\nRuido 0 %: datos sin ruido; la inversión asume un error de 0.1 %."
        self.estado.config(text=txt)
        self.historial.append(m)
        fila = [len(self.historial)] + [m.get(c, "") if m.get(c) is not None else ""
                                        for c in self.cols[1:]]
        self.tabla.insert("", "end", values=fila)
        self.tabla.yview_moveto(1)

    def limpiar(self):
        self.historial.clear()
        self.tabla.delete(*self.tabla.get_children())

    def exportar(self):
        if not self.historial:
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")],
                                            initialfile="historial_ert.csv")
        if ruta:
            pd.DataFrame(self.historial).to_csv(ruta, index=False, encoding="utf-8-sig")


# ======================================================================
def prueba(app, carpeta):
    """Corre casos sin intervencion, guarda las figuras y prueba las validaciones."""
    os.makedirs(carpeta, exist_ok=True)

    def correr(nombre):
        calc, dibujar, p = app.parametros()
        r = calc(**p)
        app.mostrar(dibujar, r, p)
        app.fig.savefig(os.path.join(carpeta, "app_%s.png" % nombre), dpi=90)
        print("OK", nombre, "| chi2", r["met"]["chi2"], "| recup", r["met"]["recuperacion_pct"],
              "| t", r["met"]["tiempo_s"])

    app.tabs.select(0)
    correr("base_2capas_1obj")
    app.n_capas.fijar(4)
    app.n_obj.fijar(4)
    app.root.update()
    correr("4capas_4obj")
    app.n_capas.fijar(1)
    app.n_obj.fijar(0)
    app.root.update()
    correr("1capa_0obj")
    app.tabs.select(1)
    correr("geometria")
    # validaciones
    app.tabs.select(0)
    app.n_capas.fijar(2)
    app.n_obj.fijar(2)
    o2 = app.objetos[1]
    o2["x"].fijar(1.0); o2["z"].fijar(-3.0)
    try:
        calc_capas(**app.params_capas())
        print("FALLO: superposicion no detectada")
    except ValueError as e:
        print("OK validacion superposicion:", str(e)[:50])
    o2["x"].fijar(-8.0); o2["z"].fijar(-7.0)
    try:
        calc_capas(**app.params_capas())
        print("FALLO: cruce de interfaz no detectado")
    except ValueError as e:
        print("OK validacion interfaz:", str(e)[:50])
    print("filas en historial:", len(app.tabla.get_children()))


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    if "--prueba" in sys.argv:
        root.update()
        prueba(app, sys.argv[sys.argv.index("--prueba") + 1])
        root.destroy()
    else:
        root.mainloop()
