"""Corre la misión Artemis IV completa y genera de una vez todo lo que depende de ella.

Uso (desde la raíz del repositorio):
    python scripts/run_mission.py          # todo (~8 min)
    python scripts/run_mission.py --quick  # solo la misión, sus figuras y mission.json

Salidas:
1. Figuras de las Fases 1–3 y docs/paper/final/results.tex (`generate_figures.py`).
2. Figura de la familia de halos (`nrho_figures.py`).
3. Figuras de las Fases 4–5:
     fig10_transferencia_nrho  ·  fig11_descenso  ·  fig12_mascons
   (PDF para LaTeX en docs/paper/final/figures, PNG en docs/figures).
4. docs/paper/final/results_mission.tex (macros \\RM…) y la clave "mission" en results.json.
5. frontend/data/mission.json para el visualizador (`export_mission.py`).
"""

from __future__ import annotations

import json
import runpy
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.integrate import solve_ivp  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import export_mission  # noqa: E402
import nrho_figures  # noqa: E402

from artemis_sim.cr3bp import MU, UNITS  # noqa: E402
from artemis_sim.descent_solver import MoonFixedDynamics, throttle_history  # noqa: E402
from artemis_sim.lunar_gravity import LunarGravityField  # noqa: E402
from artemis_sim.pipeline import MissionRun, run_mission  # noqa: E402

PDF_DIR = ROOT / "docs" / "paper" / "final" / "figures"
PNG_DIR = ROOT / "docs" / "figures"
RESULTS_TEX = ROOT / "docs" / "paper" / "final" / "results_mission.tex"

# Misma paleta y estilo que generate_figures.py
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
EARTH_FILL, MOON_FILL = "#86b6ef", "#bdbcb6"
STYLE = {
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    "mathtext.fontset": "cm",
    "font.size": 9,
    "axes.titlesize": 9.5,
    "axes.titlepad": 10,
    "axes.labelsize": 9,
    "axes.edgecolor": INK2,
    "axes.labelcolor": INK,
    "axes.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "legend.frameon": False,
    "lines.linewidth": 1.6,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
}


def save(fig: plt.Figure, name: str) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(PDF_DIR / f"{name}.pdf")
    fig.savefig(PNG_DIR / f"{name}.png")
    plt.close(fig)
    print(f"  -> {name}.pdf / .png")


def fig_transfer(run: MissionRun) -> None:
    """Transferencia TLI → OPF → NRI en el marco rotante Tierra–Luna."""
    s4 = run.summary.phases_1_to_4
    tr, nrho = s4.transfer, s4.nrho
    t, y = tr.dense()
    km = UNITS.length_m / 1e3
    t_flyby = tr.flyby_time
    before = t <= t_flyby
    orbit = nrho.sample(600)
    moon_x = 1.0 - MU

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(7.2, 3.4), width_ratios=[1.35, 1])
    ax_a.plot(y[0, before] * km / 1e3, y[1, before] * km / 1e3, color=C1, label="TLI → OPF")
    ax_a.plot(y[0, ~before] * km / 1e3, y[1, ~before] * km / 1e3, color=C2, label="OPF → NRI")
    ax_a.plot(orbit[0] * km / 1e3, orbit[1] * km / 1e3, color=C3, lw=1.0, label="NRHO 9:2")
    ax_a.add_patch(plt.Circle((-MU * km / 1e3, 0), 6.378, color=EARTH_FILL, zorder=3))
    ax_a.add_patch(plt.Circle((moon_x * km / 1e3, 0), 1.737, color=MOON_FILL, zorder=3))
    ax_a.set_xlabel("x rotante [10³ km]")
    ax_a.set_ylabel("y rotante [10³ km]")
    ax_a.set_aspect("equal")
    ax_a.set_title("(a) Tierra → Luna (marco rotante)", loc="left")
    ax_a.legend(loc="lower left")

    rel = lambda s: (s[0] - moon_x) * km / 1e3  # noqa: E731
    near = np.linalg.norm(y[0:3] - np.array([[moon_x], [0], [0]]), axis=0) * km < 80e3
    ax_b.plot(rel(y[:, near & before]), y[2, near & before] * km / 1e3, ".", ms=1.2, color=C1)
    ax_b.plot(rel(y[:, near & ~before]), y[2, near & ~before] * km / 1e3, color=C2)
    ax_b.plot(rel(orbit), orbit[2] * km / 1e3, color=C3, lw=1.0)
    opf = tr.nodes[tr.flyby_node]
    ax_b.plot(rel(opf), opf[2] * km / 1e3, "o", color=INK, ms=4)
    ax_b.annotate(f"OPF {s4.dv_opf_m_s:.0f} m/s", (rel(opf), opf[2] * km / 1e3),
                  xytext=(8, -12), textcoords="offset points", fontsize=7.5)  # fmt: skip
    ax_b.plot(rel(tr.arrival), tr.arrival[2] * km / 1e3, "s", color=INK, ms=4)
    ax_b.annotate(f"NRI {s4.dv_nri_m_s:.0f} m/s", (rel(tr.arrival), tr.arrival[2] * km / 1e3),
                  xytext=(8, 4), textcoords="offset points", fontsize=7.5)  # fmt: skip
    ax_b.add_patch(plt.Circle((0, 0), 1.737, color=MOON_FILL, zorder=3))
    ax_b.set_xlabel("x − x_Luna [10³ km]")
    ax_b.set_ylabel("z [10³ km]")
    ax_b.set_aspect("equal")
    ax_b.set_title("(b) Llegada (vista lateral, centrada en la Luna)", loc="left")
    fig.tight_layout()
    save(fig, "fig10_transferencia_nrho")


def fig_descent(run: MissionRun, gravity: LunarGravityField) -> None:
    """Perfil del descenso propulsado: altitud, velocidades, empuje y masa."""
    d = run.summary.descent
    powered = d.t >= d.t_pdi
    t = d.t[powered] - d.t_pdi
    y = d.y[:, powered]
    up = y[0:3] / np.linalg.norm(y[0:3], axis=0)
    v_up = np.sum(y[3:6] * up, axis=0)
    v_h = np.linalg.norm(y[3:6] - v_up * up, axis=0)
    throttle = throttle_history(d.t[powered], y, MoonFixedDynamics(gravity), d.phases)
    gates = [(d.gate_times["Frenado"] - d.t_pdi, "high gate"),
             (d.gate_times["Aproximación"] - d.t_pdi, "low gate")]  # fmt: skip

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.8), sharex=True)
    (a, b), (c, e) = axes
    a.plot(t, d.altitude_m[powered] / 1e3, color=C1)
    a.set_ylabel("Altitud [km]")
    a.set_title("(a) Altitud sobre el radio medio", loc="left")
    b.plot(t, v_h, color=C1, label="horizontal")
    b.plot(t, -v_up, color=C2, label="de descenso")
    b.set_yscale("symlog", linthresh=10)
    b.set_ylabel("Velocidad [m/s]")
    b.set_title("(b) Velocidad (marco fijo a la Luna)", loc="left")
    b.legend(loc="upper right")
    c.plot(t, 100 * throttle, color=C1)
    c.axhline(10, color=INK2, lw=0.7, ls=(0, (3, 3)))
    c.set_ylim(0, 105)
    c.set_ylabel("Empuje [% del máximo]")
    c.set_xlabel("Tiempo desde el PDI [s]")
    c.set_title("(c) Empuje del E-guidance (límites 10–100 %)", loc="left")
    e.plot(t, y[6] / 1e3, color=C1)
    e.axhline(120, color=INK2, lw=0.7, ls=(0, (3, 3)))
    e.text(5, 122, "masa seca", fontsize=7.5, color=INK2)
    e.set_ylabel("Masa [t]")
    e.set_xlabel("Tiempo desde el PDI [s]")
    e.set_title("(d) Masa del HLS", loc="left")
    for ax in axes.ravel():
        for tg, label in gates:
            ax.axvline(tg, color=INK2, lw=0.7, ls=(0, (3, 3)), zorder=0)
            ax.text(tg, 1.0, label, transform=ax.get_xaxis_transform(), fontsize=7,
                    color=INK2, ha="center", va="bottom")  # fmt: skip
    fig.tight_layout()
    save(fig, "fig11_descenso")


def fig_mascons(run: MissionRun, gravity: LunarGravityField) -> dict[str, float]:
    """(a) Anomalía radial de gravedad en la superficie (grado 3–100); (b) efecto en una LLO."""
    j2 = LunarGravityField.grgm1200a(n_max=2)
    point = LunarGravityField.grgm1200a(n_max=0)
    lat = np.linspace(-89.5, 89.5, 180)  # 1°: el grado 100 tiene detalle de ~1,8°
    lon = np.linspace(-179.5, 179.5, 360)
    anomaly = np.empty((lat.size, lon.size))
    r = gravity.radius
    for i, la in enumerate(np.radians(lat)):
        for k, lo in enumerate(np.radians(lon)):
            u = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
            anomaly[i, k] = -np.dot(gravity.acceleration(r * u) - j2.acceleration(r * u), u)
    anomaly_mgal = anomaly * 1e5  # 1 mGal = 1e-5 m/s²

    r0 = gravity.radius + 100e3
    period = 2 * np.pi * np.sqrt(r0**3 / gravity.gm)
    y0 = np.array([r0, 0.0, 0.0, 0.0, 0.0, np.sqrt(gravity.gm / r0)])
    tt = np.linspace(0.0, period, 600)

    def orbit(f: LunarGravityField) -> np.ndarray:
        sol = solve_ivp(
            lambda _t, s: np.concatenate([s[3:], f.acceleration(s[:3])]),
            (0.0, period), y0, method="DOP853", rtol=1e-11, atol=1e-4, t_eval=tt,
        )  # fmt: skip
        return sol.y[0:3]

    full = orbit(gravity)
    dev_point = np.linalg.norm(full - orbit(point), axis=0)
    dev_j2 = np.linalg.norm(full - orbit(j2), axis=0)

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(7.2, 3.0), width_ratios=[1.5, 1])
    lim = float(np.percentile(np.abs(anomaly_mgal), 99))
    mesh = ax_a.pcolormesh(lon, lat, anomaly_mgal, cmap="RdBu_r", vmin=-lim, vmax=lim,
                           shading="auto", rasterized=True)  # fmt: skip
    site = run.summary.descent.site
    ax_a.plot(site.lon_deg, site.lat_deg, "*", color=INK, ms=8)
    ax_a.annotate("sitio", (site.lon_deg, site.lat_deg), xytext=(-36, 8),
                  textcoords="offset points", fontsize=7.5)  # fmt: skip
    ax_a.set_xlabel("Longitud [°]")
    ax_a.set_ylabel("Latitud [°]")
    ax_a.set_title("(a) Anomalía radial, grados 3–100 [mGal]", loc="left")
    ax_a.grid(False)
    fig.colorbar(mesh, ax=ax_a, fraction=0.04, pad=0.02)
    ax_b.plot(tt / 60, dev_point / 1e3, color=C1, label="frente a masa puntual")
    ax_b.plot(tt / 60, dev_j2 / 1e3, color=C2, label="frente a solo J₂")
    ax_b.set_xlabel("Tiempo [min]")
    ax_b.set_ylabel("Separación [km]")
    ax_b.set_title("(b) Órbita polar de 100 km", loc="left")
    ax_b.legend(loc="upper left")
    fig.tight_layout()
    save(fig, "fig12_mascons")
    return {
        "mascon_dev_point_km": float(dev_point.max() / 1e3),
        "mascon_dev_jtwo_km": float(dev_j2.max() / 1e3),
        "mascon_anomaly_max_mgal": float(np.max(np.abs(anomaly_mgal))),
        "llo_period_min": period / 60,
    }


def write_results(numbers: dict[str, float]) -> None:
    """Macros \\RM<Clave> para el informe y la clave "mission" en results.json."""
    lines = ["% Archivo autogenerado por scripts/run_mission.py. NO EDITAR A MANO."]
    for key, val in numbers.items():
        name = "RM" + "".join(part.capitalize() for part in key.split("_"))
        if not name.isalpha():
            raise ValueError(f"Nombre de macro inválido para {key!r}: {name}")
        digits = 0 if abs(val) >= 100 else 1 if abs(val) >= 10 else 2
        txt = f"{val:,.{digits}f}".replace(",", "\\,")
        lines.append(f"\\newcommand{{\\{name}}}{{{txt}}}")
    RESULTS_TEX.write_text("\n".join(lines) + "\n")
    path = PNG_DIR / "results.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data["mission"] = numbers
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  -> {RESULTS_TEX.relative_to(ROOT)} ({len(numbers)} macros) y results.json")


def main(quick: bool = False) -> None:
    start = time.time()
    plt.rcParams.update(STYLE)
    if not quick:
        print("== Fases 1–3: figuras y results.tex (generate_figures.py)")
        runpy.run_path(str(ROOT / "scripts" / "generate_figures.py"), run_name="__main__")
        print("== Familia de halos (nrho_figures.py)")
        nrho_figures.main()
        plt.rcParams.update(STYLE)

    print("== Misión completa (run_mission)…")
    run = run_mission()
    gravity = LunarGravityField.grgm1200a()
    numbers = run.key_numbers()
    print("== Figuras de las Fases 4–5")
    fig_transfer(run)
    fig_descent(run, gravity)
    numbers.update(fig_mascons(run, gravity))
    write_results(numbers)
    print("== Visualizador (export_mission.py)")
    export_mission.main(run)
    print(f"Listo en {(time.time() - start) / 60:.1f} min.")


if __name__ == "__main__":
    main(quick="--quick" in sys.argv)
