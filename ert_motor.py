"""Laboratorio 2 ERT - motor de calculo y figuras (sin interfaz).

Lo usan la aplicacion de escritorio (ert_interactivo.py) y el notebook interactivo
(ERT_interactivo.ipynb). Funciones principales:
    calc_capas(...)  -> modelo de varias capas con varios objetos
    calc_geo(...)    -> geometria circular, triangular o esferica (3D)
    dibujar_capas(fig, r), dibujar_geo(fig, r) -> dibujan el resultado en una Figure
"""
import time

import matplotlib
import matplotlib.cm
import matplotlib.patches as mpatches
import matplotlib.ticker
import numpy as np
from matplotlib.colors import LogNorm
from matplotlib.path import Path

import pygimli as pg
import pygimli.meshtools as mt
from pygimli.physics import ert

pg.setLogLevel(40)
X_ELEC = (-15.0, 15.0)          # la linea mide siempre 30 m
NOISE_ABS = 1e-6
SEED = 1337
MAX_CAPAS = 5                   # capas sobre el basamento
MAX_OBJ = 4
TICKS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000]
MALLAS_INV = {"gruesa": dict(paraDX=1.0, paraMaxCellSize=10.0),
              "media": dict(paraDX=0.33, paraMaxCellSize=1.0),
              "fina": dict(paraDX=0.2, paraMaxCellSize=0.25)}
MALLAS_DIR = {"gruesa": dict(q2=30, area_obj2=0.5, area2=0.0, q3=1.5, area_obj3=1.0),
              "media": dict(q2=34, area_obj2=0.05, area2=0.0, q3=1.3, area_obj3=0.3),
              "fina": dict(q2=34, area_obj2=0.01, area2=1.0, q3=1.2, area_obj3=0.1)}
GEO = {"circular": dict(dim=2, tipo="circulo", centro=(0.0, -3.0), radio=1.5),
       "triangular": dict(dim=2, tipo="poligono",
                          vertices=[(-2.0, -1.8), (2.0, -1.8), (0.0, -5.3)]),
       "esférico": dict(dim=3, tipo="circulo", centro=(0.0, -3.0), radio=1.5)}


# ======================================================================
# Calculo (sin graficar; corre en un hilo aparte)
# ======================================================================
def media_geom(v):
    v = np.asarray(v)
    return float(np.exp(np.mean(np.log(v)))) if v.size else float("nan")


def esquema(n_elec, arreglo):
    return ert.createData(elecs=np.linspace(X_ELEC[0], X_ELEC[1], n_elec), schemeName=arreglo)


def asignar_error(data, ruido):
    """Sin ruido (0 %) PyGIMLi no asigna error y la inversion lo exige: se asume 0.1 %."""
    if ruido == 0:
        data["err"] = pg.Vector(data.size(), 0.001)


def invertir(data, lam, malla_inv, para_depth):
    data = pg.DataContainerERT(data)
    for i in range(data.sensorCount()):                     # electrodos en (x, 0)
        data.setSensorPosition(i, [data.sensorPosition(i)[0], 0.0, 0.0])
    data["k"] = pg.core.geometricFactors(data, dim=3)        # k analitico para 2D
    imesh = ert.createInversionMesh(data, quality=33, paraDepth=para_depth,
                                    **MALLAS_INV[malla_inv])
    mgr = ert.ERTManager(data)
    modelo = np.array(mgr.paraModel(mgr.invert(data, mesh=imesh, lam=lam, verbose=False)))
    return mgr, modelo


def geometria_objeto(o, marker):
    """Caja (x0, x1, zb, zt), PLC (con su marcador de region) y funcion 'dentro'."""
    x, z, tam = o["x"], o["z"], o["tam"]
    if o["forma"] == "círculo":
        caja = (x - tam, x + tam, z - tam, z + tam)
        plc = mt.createCircle(pos=[x, z], radius=tam, nSegments=48, marker=marker,
                              boundaryMarker=10, area=0.05)
        dentro = lambda xx, zz: (xx - x) ** 2 + (zz - z) ** 2 <= tam ** 2
    else:
        ancho, alto = (2 * tam, tam) if o["forma"] == "tabular" else (0.6 * tam, 2.5 * tam)
        caja = (x - ancho / 2, x + ancho / 2, z - alto / 2, z + alto / 2)
        plc = mt.createRectangle(start=[caja[0], caja[3]], end=[caja[1], caja[2]],
                                 marker=marker, boundaryMarker=10, area=0.05)
        dentro = lambda xx, zz: (caja[0] <= xx <= caja[1]) and (caja[2] <= zz <= caja[3])
    return caja, plc, dentro


def validar(interfaces, objetos):
    """Cada objeto dentro de una sola capa y sin tocar a los demas. Devuelve la capa de cada uno."""
    bordes = [0.0] + interfaces + [-1e9]
    capas_obj = []
    for i, o in enumerate(objetos, 1):
        x0, x1, zb, zt = o["caja"]
        if zt > -0.2:
            raise ValueError("El objeto %d sobresale de la superficie (techo en %.1f m)." % (i, zt))
        if x0 < -14 or x1 > 14:
            raise ValueError("El objeto %d se sale de la zona de la línea (|x| ≤ 14 m)." % i)
        capa = None
        for k in range(len(bordes) - 1):
            if zt < bordes[k] - 0.1 and zb > bordes[k + 1] + 0.1:
                capa = k
        if capa is None:
            raise ValueError("El objeto %d cruza una interfaz (va de %.1f a %.1f m). Cada objeto "
                             "debe quedar completamente dentro de una capa." % (i, zt, zb))
        capas_obj.append(capa)
    for i in range(len(objetos)):
        for j in range(i + 1, len(objetos)):
            a, b = objetos[i]["caja"], objetos[j]["caja"]
            if not (a[1] + 0.2 < b[0] or b[1] + 0.2 < a[0] or a[3] + 0.2 < b[2]
                    or b[3] + 0.2 < a[2]):
                raise ValueError("Los objetos %d y %d se tocan o se superponen." % (i + 1, j + 1))
    return capas_obj


def calc_capas(capas, rho_basam, objetos, n_elec, arreglo, ruido, lam, malla_inv, x_perfil):
    """capas: [(espesor, rho), ...] de arriba hacia abajo; objetos: [dict(forma, rho, x, z, tam)]."""
    t0 = time.time()
    interfaces = list(-np.cumsum([e for e, _ in capas]))
    for i, o in enumerate(objetos):
        o["marker"] = 10 + i              # capas: 1..N+1 (de arriba hacia abajo)
        o["caja"], o["plc"], o["dentro"] = geometria_objeto(o, o["marker"])
    capa_de = validar(interfaces, objetos)

    if interfaces:
        geom = mt.createWorld(start=[-50, 0], end=[50, -50], layers=interfaces,
                              worldMarker=True)
    else:
        geom = mt.createWorld(start=[-50, 0], end=[50, -50], worldMarker=True)
    rhomap = [[k + 1, r] for k, (_, r) in enumerate(capas)] + [[len(capas) + 1, rho_basam]]
    for o in objetos:
        geom = geom + o["plc"]
        rhomap.append([o["marker"], o["rho"]])
    scheme = esquema(n_elec, arreglo)
    for p in scheme.sensors():                    # nodos en los electrodos (singularidad)
        geom.createNode(p)
        geom.createNode(p - [0, 0.1])
    mesh = mt.createMesh(geom, quality=34)
    data = ert.simulate(mesh, scheme=scheme, res=rhomap, noiseLevel=ruido / 100,
                        noiseAbs=NOISE_ABS, seed=SEED, verbose=False)
    data.remove(data["rhoa"] < 0)
    asignar_error(data, ruido)

    fondo = min([0.0] + interfaces + [o["caja"][2] for o in objetos])
    para_depth = min(max(12.0, -fondo + 2), 25.0)
    mgr, modelo = invertir(data, lam, malla_inv, para_depth)
    pd_ = mgr.paraDomain
    xc = np.array([c.center()[0] for c in pd_.cells()])
    zc = np.array([c.center()[1] for c in pd_.cells()])
    bordes = [0.0] + interfaces + [-1e9]
    capa_celda = np.array([next(k for k in range(len(bordes) - 1)
                                if bordes[k] >= z > bordes[k + 1]) for z in zc])
    en_algun_obj = np.zeros(len(xc), bool)
    mascaras = []
    for o in objetos:
        m = np.array([o["dentro"](x, z) for x, z in zip(xc, zc)])
        mascaras.append(m)
        en_algun_obj |= m
    recs = []
    for o, m, k in zip(objetos, mascaras, capa_de):
        rho_host = rho_basam if k == len(capas) else capas[k][1]
        enc = (capa_celda == k) & ~en_algun_obj & (np.abs(xc) <= 12)
        if m.sum() == 0 or enc.sum() == 0 or abs(np.log(o["rho"] / rho_host)) < 1e-9:
            recs.append(None)
            continue
        c_rec = media_geom(modelo[m]) / media_geom(modelo[enc])
        recs.append(round(100 * np.log(c_rec) / np.log(o["rho"] / rho_host)))

    zs = np.linspace(-0.1, -min(para_depth, 20), 200)
    perf = []
    for z in zs:
        c = pd_.findCell(pg.Pos(x_perfil, z))
        perf.append(modelo[c.id()] if c is not None else np.nan)
    rhos = [r for _, r in capas] + [rho_basam] + [o["rho"] for o in objetos]

    nombre_capa = lambda k: "basamento" if k == len(capas) else "capa %d" % (k + 1)
    met = dict(pestaña="capas",
               capas=" / ".join("%g m·%g" % (e, r) for e, r in capas) + " / bas·%g" % rho_basam,
               objetos="; ".join("%s %g Ω·m en %s" % (o["forma"], o["rho"], nombre_capa(k))
                                 for o, k in zip(objetos, capa_de)) or "ninguno",
               electrodos=n_elec, arreglo=arreglo, ruido_pct=ruido, lam=lam,
               malla_inv=malla_inv, datos=data.size(), celdas_inv=pd_.cellCount(),
               chi2=round(mgr.inv.chi2(), 2), rrms_pct=round(float(mgr.inv.relrms()), 2),
               recuperacion_pct=" | ".join("O%d: %s" % (i + 1, "-" if r is None else r)
                                           for i, r in enumerate(recs)) or "-",
               tiempo_s=round(time.time() - t0, 1))
    return dict(tipo="capas", mesh=mesh, rhomap=rhomap, pd=pd_, modelo=modelo,
                interfaces=interfaces, objetos=objetos, zs=zs, perf=np.array(perf),
                capas=capas, rho_basam=rho_basam, rhos=rhos, para_depth=para_depth,
                x_perfil=x_perfil, lam=lam, chi2=mgr.inv.chi2(),
                rrms=float(mgr.inv.relrms()), met=met)


_cache = {}


def simular_geo(geo, n_elec, malla_dir, ruido, rho_f, rho_o):
    """Datos sinteticos (con cache: cambiar lambda o la malla de inversion no re-simula)."""
    clave = (geo, n_elec, malla_dir, ruido, rho_f, rho_o)
    if clave in _cache:
        return _cache[clave]
    g, m = GEO[geo], MALLAS_DIR[malla_dir]
    scheme = esquema(n_elec, "dd")
    if g["dim"] == 2:
        if g["tipo"] == "circulo":
            obj = mt.createCircle(pos=list(g["centro"]), radius=g["radio"], nSegments=48,
                                  marker=2, boundaryMarker=10, area=m["area_obj2"])
        else:
            obj = mt.createPolygon(g["vertices"], isClosed=True, marker=2, boundaryMarker=10,
                                   area=m["area_obj2"])
        geom = mt.createWorld(start=[-50, 0], end=[50, -50], worldMarker=True) + obj
        for p in scheme.sensors():
            geom.createNode(p)
            geom.createNode(p - [0, 0.1])
        mesh = mt.createMesh(geom, quality=m["q2"], area=m["area2"])
        sr = True
    else:
        d = 2 * g["radio"]                # createSphere usa size (diametro), no radius
        obj = mt.createSphere(pos=[0, 0, g["centro"][1]], size=[d, d, d], nSegments=32,
                              nRings=16, marker=2, boundaryMarker=10, area=m["area_obj3"])
        geom = mt.createWorld(start=[-50, -50, 0], end=[50, 50, -50], worldMarker=True) + obj
        for p in scheme.sensors():
            geom.createNode(p)
            geom.createNode(p - [0, 0, 0.1])
        mesh = mt.createMesh(geom, quality=m["q3"])
        sr = False
        hom = ert.simulate(mesh, scheme=scheme, res=1.0, sr=False, calcOnly=True, verbose=False)
        scheme["k"] = 1.0 / hom["u"]          # factor geometrico numerico
    rhomap = [[1, rho_f], [2, rho_o]]
    limpio = ert.simulate(mesh, scheme=scheme, res=rhomap, sr=sr, noiseLevel=0, verbose=False)
    data = ert.simulate(mesh, scheme=scheme, res=rhomap, sr=sr, noiseLevel=ruido / 100,
                        noiseAbs=NOISE_ABS, seed=SEED, verbose=False)
    data.remove(data["rhoa"] < 0)
    asignar_error(data, ruido)
    anom = 100 * float(np.max(np.abs(np.array(limpio["rhoa"]) / rho_f - 1)))
    _cache[clave] = (data, anom, mesh.cellCount())
    return _cache[clave]


def calc_geo(geo, rho_f, rho_o, n_elec, ruido, lam, malla_dir, malla_inv):
    t0 = time.time()
    data, anom, ncel = simular_geo(geo, n_elec, malla_dir, ruido, rho_f, rho_o)
    mgr, modelo = invertir(data, lam, malla_inv, 8.0)
    pd_ = mgr.paraDomain
    xc = np.array([c.center()[0] for c in pd_.cells()])
    zc = np.array([c.center()[1] for c in pd_.cells()])
    g = GEO[geo]
    if g["tipo"] == "circulo":
        en = (xc - g["centro"][0]) ** 2 + (zc - g["centro"][1]) ** 2 <= g["radio"] ** 2
    else:
        en = Path(g["vertices"]).contains_points(np.c_[xc, zc])
    cerca = (np.abs(xc) <= 10) & (zc >= -7)
    c_real = np.log(rho_o / rho_f)
    rec = (np.log(media_geom(modelo[en]) / media_geom(modelo[cerca & ~en])) / c_real
           if abs(c_real) > 1e-9 else np.nan)
    rho_max = float(modelo[(np.abs(xc) <= 5) & (zc >= -7)].max())
    met = dict(pestaña="geometrías", objetos="%s %g Ω·m en %g Ω·m" % (geo, rho_o, rho_f),
               electrodos=n_elec, ruido_pct=ruido, lam=lam, malla_dir=malla_dir,
               malla_inv=malla_inv, datos=data.size(), celdas_inv=pd_.cellCount(),
               anomalia_rhoa_pct=round(anom, 1), chi2=round(mgr.inv.chi2(), 2),
               rrms_pct=round(float(mgr.inv.relrms()), 2),
               rho_max_rec=round(rho_max),
               recuperacion_pct=round(100 * rec) if np.isfinite(rec) else "-",
               tiempo_s=round(time.time() - t0, 1))
    return dict(tipo="geo", geo=geo, pd=pd_, modelo=modelo, anom=anom, rho_f=rho_f, rho_o=rho_o,
                n_elec=n_elec, lam=lam, chi2=mgr.inv.chi2(), rrms=float(mgr.inv.relrms()),
                rho_max=rho_max, met=met)


# ======================================================================
# Graficos (en el hilo principal, sobre la figura de la ventana)
# ======================================================================
def barra(fig, axes, lo, hi):
    sm = matplotlib.cm.ScalarMappable(norm=LogNorm(lo, hi), cmap="Spectral_r")
    cb = fig.colorbar(sm, ax=axes, shrink=0.85, pad=0.02, label="ρ (Ω·m)")
    t = [x for x in TICKS if lo <= x <= hi]
    cb.set_ticks(t)
    cb.set_ticklabels([str(x) for x in t])


def contorno(ax, geo, **kw):
    g = GEO[geo]
    estilo = dict(fill=False, ec="k", ls="--", lw=1.2)
    estilo.update(kw)
    if g["tipo"] == "circulo":
        ax.add_patch(mpatches.Circle(g["centro"], g["radio"], **estilo))
    else:
        ax.add_patch(mpatches.Polygon(g["vertices"], closed=True, **estilo))


def dibujar_capas(fig, r):
    fig.clear()
    gs = fig.add_gridspec(2, 2, width_ratios=[3, 1], hspace=0.45, wspace=0.25)
    ax1, ax2 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[:, 1])
    lo, hi = min(r["rhos"]) * 0.7, max(r["rhos"]) * 1.3
    kw = dict(hold=True, cMap="Spectral_r", logScale=True, colorBar=False, cMin=lo, cMax=hi)
    # un valor por celda: con una lista [[marcador, rho], ...] de 2x2, pg.show la toma
    # por un campo vectorial y dibuja lineas de flujo
    mapa = dict(r["rhomap"])
    pg.show(r["mesh"], np.array([mapa[m] for m in r["mesh"].cellMarkers()]), ax=ax1, **kw)
    pg.show(r["pd"], r["modelo"], ax=ax2, **kw)
    zmax = min(r["para_depth"], 20)
    for ax, t in ((ax1, "Modelo verdadero"),
                  (ax2, "Inversión (λ = %g, χ² = %.2f, rRMS = %.2f %%)"
                   % (r["lam"], r["chi2"], r["rrms"]))):
        ax.set_xlim(-16, 16)
        ax.set_ylim(-zmax, 0)
        ax.set_title(t)
        ax.set_xlabel("x (m)")
        ax.set_ylabel("z (m)")
        for zi in r["interfaces"]:
            ax.axhline(zi, c="k", ls=":", lw=0.8)
        ax.axvline(r["x_perfil"], c="#2962FF", ls="--", lw=0.8)
    for i, o in enumerate(r["objetos"], 1):
        x0, x1, zb, zt = o["caja"]
        if o["forma"] == "círculo":
            ax2.add_patch(mpatches.Circle((o["x"], o["z"]), o["tam"], fill=False, ec="k", ls="--"))
        else:
            ax2.add_patch(mpatches.Rectangle((x0, zb), x1 - x0, zt - zb, fill=False, ec="k", ls="--"))
        for ax in (ax1, ax2):
            ax.text(o["x"], zt + 0.15, "O%d" % i, ha="center", va="bottom", fontsize=8,
                    fontweight="bold")
    zs = r["zs"]
    bordes = [0.0] + r["interfaces"]
    rho_capas = [rr for _, rr in r["capas"]]
    verdadero = np.full_like(zs, r["rho_basam"])
    for k in range(len(r["interfaces"]) - 1, -1, -1):
        verdadero[zs > r["interfaces"][k]] = rho_capas[k]
    ax3.semilogx(verdadero, zs, "k-", label="verdadero (sin objetos)")
    ax3.semilogx(r["perf"], zs, "-", c="#2962FF", lw=2, label="invertido")
    ax3.set_title("Perfil en x = %g m" % r["x_perfil"])
    ax3.set_xlabel("ρ (Ω·m)")
    t = [x for x in TICKS if lo <= x <= hi]
    if len(t) > 4:                     # eje angosto: una marca si y una no
        t = t[::2]
    ax3.set_xticks(t)
    ax3.set_xticklabels([str(x) for x in t])
    ax3.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax3.legend(loc="lower left", fontsize=8)
    ax3.grid(alpha=0.3)
    barra(fig, [ax1, ax2], lo, hi)


def dibujar_geo(fig, r):
    fig.clear()
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    fig.subplots_adjust(hspace=0.6)
    geo = r["geo"]
    lo, hi = min(r["rho_f"], r["rho_o"]) * 0.6, max(r["rho_f"], r["rho_o"]) * 1.2
    norm = LogNorm(lo, hi)
    ax1.set_facecolor(matplotlib.colormaps["Spectral_r"](norm(r["rho_f"])))
    contorno(ax1, geo, fill=True, fc=matplotlib.colormaps["Spectral_r"](norm(r["rho_o"])), ls="-")
    xe = np.linspace(X_ELEC[0], X_ELEC[1], r["n_elec"])
    ax1.plot(xe, np.full_like(xe, -0.15), "kv", ms=4)
    ax1.set_title("Verdadero: %s%s  ·  anomalía máxima en ρa: %.0f %%"
                  % (geo, " (corte de la esfera 3D)" if GEO[geo]["dim"] == 3 else "", r["anom"]))
    pg.show(r["pd"], r["modelo"], ax=ax2, hold=True, cMap="Spectral_r", logScale=True,
            colorBar=False, cMin=lo, cMax=hi)
    contorno(ax2, geo)
    ax2.set_title("Inversión (λ = %g, χ² = %.2f, rRMS = %.2f %%)  ·  ρ máx = %.0f Ω·m"
                  % (r["lam"], r["chi2"], r["rrms"], r["rho_max"]))
    for ax in (ax1, ax2):
        ax.set_xlim(-14, 14)
        ax.set_ylim(-8, 0)
        ax.set_aspect("equal")
        ax.set_ylabel("z (m)")
    ax2.set_xlabel("x (m)")
    barra(fig, [ax1, ax2], lo, hi)


