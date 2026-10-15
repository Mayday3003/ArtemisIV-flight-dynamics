"""Genera las figuras y la tabla de resultados del informe técnico de Artemis IV.

Uso (desde la raíz del repositorio):
    .venv/bin/python scripts/generate_figures.py

Salidas:
- docs/paper/final/figures/*.pdf  (vectoriales, para LaTeX)
- docs/figures/*.png              (rasterizadas a 300 dpi, para README / web)
- docs/paper/final/results.tex    (macros LaTeX con los valores numéricos calculados)
- docs/figures/results.json       (los mismos valores en formato legible por máquina)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.integrate import solve_ivp  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from artemis_sim.ascent_solver import (  # noqa: E402
    AscentConfig,
    AscentPhase,
    linear_tangent_direction,
    make_ascent_derivatives,
    simulate_full_ascent,
    srb_thrust_scale,
)
from artemis_sim.constants import (  # noqa: E402
    EARTH,
    EARTH_ROTATION,
    G0_M_S2,
    MOON,
    SLS_B1B_EUS,
)
from artemis_sim.ephemeris import DEFAULT_LUNAR_CONFIG, get_body_position  # noqa: E402
from artemis_sim.physics_engine import (  # noqa: E402
    compute_dynamic_pressure,
    compute_gravity,
    compute_mach_number,
    compute_relative_velocity,
)
from artemis_sim.shooting_method import (  # noqa: E402
    kepler_transfer_geometry,
    make_dop853_propagator,
    moon_relative_target,
    solve_tli_shooting,
)
from artemis_sim.state import ArtemisState  # noqa: E402
from artemis_sim.symplectic_solver import (  # noqa: E402
    circular_orbit_state,
    compute_jacobi_constant,
    compute_system_energy,
    impulsive_burn,
    propagate_rk4,
    propagate_verlet,
)

PDF_DIR = ROOT / "docs" / "paper" / "final" / "figures"
PNG_DIR = ROOT / "docs" / "figures"
PDF_DIR.mkdir(parents=True, exist_ok=True)
PNG_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Estilo: paleta categórica validada (orden fijo), tinta neutra, rejilla recesiva
# ---------------------------------------------------------------------------
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"  # azul, naranja, aqua
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
EARTH_FILL, MOON_FILL = "#86b6ef", "#bdbcb6"

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["DejaVu Serif"],
        "mathtext.fontset": "cm",
        "font.size": 9,
        "axes.titlesize": 9.5,
        "axes.titlepad": 14,
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
        "figure.dpi": 110,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.formatter.use_mathtext": True,
    }
)

RESULTS: dict[str, float] = {}


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(PDF_DIR / f"{name}.pdf")
    fig.savefig(PNG_DIR / f"{name}.png")
    plt.close(fig)
    print(f"  -> {name}.pdf / .png")


def mark_events(ax: plt.Axes, events: list[tuple[float, str]], label: bool = False) -> None:
    for t_ev, txt in events:
        ax.axvline(t_ev, color=INK2, lw=0.7, ls=(0, (3, 3)), zorder=0)
        if label:
            ax.text(
                t_ev,
                1.01,
                txt,
                transform=ax.get_xaxis_transform(),
                ha="center",
                va="bottom",
                fontsize=7.5,
                color=INK2,
            )


# ===========================================================================
# 1. ASCENSO ATMOSFÉRICO COMPLETO
# ===========================================================================
print("[1/6] Ascenso atmosférico (SRB + Core hasta MECO)")
lat, lon = 28.627, -80.621
guidance = linear_tangent_direction()
asc = simulate_full_ascent(lat, lon, thrust_direction_fn=guidance, max_step_s=0.5)
t = asc.t
pos, vel, mass = asc.y[0:3], asc.y[3:6], asc.y[6]
n_seg1 = int(np.searchsorted(t, asc.t_srb_separation_s, side="left")) + 1

cfg1 = AscentConfig(thrust_direction_fn=guidance, phase=AscentPhase.BOOSTERS_AND_CORE)
cfg2 = AscentConfig(thrust_direction_fn=guidance, phase=AscentPhase.CORE_ONLY)
f1, f2 = make_ascent_derivatives(cfg1), make_ascent_derivatives(cfg2)

omega = EARTH_ROTATION.omega_rad_s
r_e = EARTH.equatorial_radius_m
alt = np.linalg.norm(pos, axis=0) - r_e
speed_inertial = np.linalg.norm(vel, axis=0)
v_rel = np.array([compute_relative_velocity(pos[:, i], vel[:, i], omega) for i in range(t.size)]).T
speed_rel = np.linalg.norm(v_rel, axis=0)
q = np.array([compute_dynamic_pressure(speed_rel[i], alt[i]) for i in range(t.size)])
mach = np.array([compute_mach_number(speed_rel[i], max(alt[i], 0.0)) for i in range(t.size)])

# Aceleración sensada (no gravitacional) = a_total - g, en unidades de g0
sensed_g = np.empty(t.size)
for i in range(t.size):
    f = f1 if i < n_seg1 else f2
    a_tot = f(t[i], asc.y[:, i])[3:6]
    sensed_g[i] = np.linalg.norm(a_tot - compute_gravity(pos[:, i], EARTH.mu_m3_s2)) / G0_M_S2
# En el último punto (m = m_corte) el modelo ya apaga motores: se usa el valor previo a MECO
sensed_g[-1] = sensed_g[-2]


# Alcance sobre la superficie en el marco terrestre rotante (ECEF)
def to_ecef(r: np.ndarray, time: float) -> np.ndarray:
    c, s = np.cos(-omega * time), np.sin(-omega * time)
    return np.array([c * r[0] - s * r[1], s * r[0] + c * r[1], r[2]])


r0_ecef = to_ecef(pos[:, 0], 0.0)
downrange = np.array(
    [
        r_e
        * np.arccos(
            np.clip(
                np.dot(to_ecef(pos[:, i], t[i]), r0_ecef)
                / (np.linalg.norm(pos[:, i]) * np.linalg.norm(r0_ecef)),
                -1.0,
                1.0,
            )
        )
        for i in range(t.size)
    ]
)

i_maxq = int(np.argmax(q))
i_mach1 = int(np.argmax(mach >= 1.0))
r_meco, v_meco = pos[:, -1], vel[:, -1]
fpa_meco = np.degrees(
    np.arcsin(np.dot(r_meco, v_meco) / (np.linalg.norm(r_meco) * speed_inertial[-1]))
)
v_circ_meco = np.sqrt(EARTH.mu_m3_s2 / np.linalg.norm(r_meco))
RESULTS.update(
    {
        "liftoff_mass_t": mass[0] / 1e3,
        "srb_scale": srb_thrust_scale(cfg1.srb_spec, cfg1.t_burn_srb_s),
        "t_mach1_s": t[i_mach1],
        "h_mach1_km": alt[i_mach1] / 1e3,
        "t_maxq_s": t[i_maxq],
        "maxq_kpa": q[i_maxq] / 1e3,
        "h_maxq_km": alt[i_maxq] / 1e3,
        "mach_maxq": mach[i_maxq],
        "t_srb_sep_s": asc.t_srb_separation_s,
        "h_srb_sep_km": alt[n_seg1 - 1] / 1e3,
        "v_srb_sep_kms": speed_inertial[n_seg1 - 1] / 1e3,
        "t_meco_s": asc.t_meco_s,
        "h_meco_km": alt[-1] / 1e3,
        "v_meco_kms": speed_inertial[-1] / 1e3,
        "fpa_meco_deg": fpa_meco,
        "downrange_meco_km": downrange[-1] / 1e3,
        "max_g": float(np.max(sensed_g)),
        "v_circ_meco_kms": v_circ_meco / 1e3,
        "mass_meco_t": mass[-1] / 1e3,
    }
)
events = [(asc.t_srb_separation_s, "Sep. SRB"), (asc.t_meco_s, "MECO")]

fig, axs = plt.subplots(3, 2, figsize=(7.0, 7.4), sharex=True)
ax = axs[0, 0]
ax.plot(t, alt / 1e3, color=C1)
ax.axhline(100, color=INK2, lw=0.7, ls=":")
ax.text(8, 104, "Línea de Kármán", fontsize=7.5, color=INK2)
ax.set_ylabel("Altitud $h$ (km)")
ax.set_title("(a) Altitud geométrica", loc="left")
mark_events(ax, events, label=True)

ax = axs[0, 1]
ax.plot(t, speed_inertial / 1e3, color=C1, label="Inercial $|\\mathbf{v}|$")
ax.plot(t, speed_rel / 1e3, color=C2, label="Relativa al aire $|\\mathbf{v}_{rel}|$")
ax.set_ylabel("Velocidad (km/s)")
ax.set_title("(b) Velocidad", loc="left")
ax.legend(loc="upper left")
mark_events(ax, events, label=True)

ax = axs[1, 0]
ax.plot(t, q / 1e3, color=C1)
ax.plot(t[i_maxq], q[i_maxq] / 1e3, "o", ms=5, color=C1, mec="white", mew=1.2)
ax.annotate(
    f"Max-Q = {q[i_maxq] / 1e3:.1f} kPa\n$t$ = {t[i_maxq]:.0f} s, M = {mach[i_maxq]:.2f}",
    (t[i_maxq], q[i_maxq] / 1e3),
    xytext=(30, -8),
    textcoords="offset points",
    fontsize=7.5,
    color=INK,
    arrowprops={"arrowstyle": "-", "color": INK2, "lw": 0.6},
)
ax.set_ylabel("Presión dinámica $q$ (kPa)")
ax.set_title("(c) Presión dinámica", loc="left")
mark_events(ax, events)

ax = axs[1, 1]
ax.plot(t, mach, color=C1)
ax.axhline(1.0, color=INK2, lw=0.7, ls=":")
ax.set_ylabel("Número de Mach")
ax.set_title("(d) Mach relativo a la atmósfera", loc="left")
mark_events(ax, events)

ax = axs[2, 0]
ax.plot(t, mass / 1e3, color=C1)
ax.set_ylabel("Masa $m$ (t)")
ax.set_xlabel("Tiempo desde el despegue (s)")
ax.set_title("(e) Masa (salto = masa seca SRB)", loc="left")
mark_events(ax, events)

ax = axs[2, 1]
ax.plot(t, sensed_g, color=C1)
ax.set_ylabel("Aceleración sensada ($g_0$)")
ax.set_xlabel("Tiempo desde el despegue (s)")
ax.set_title("(f) Factor de carga axial", loc="left")
mark_events(ax, events)
fig.align_ylabels()
fig.tight_layout()
save(fig, "fig01_ascenso_perfil")

fig, ax = plt.subplots(figsize=(7.0, 2.6))
ax.plot(downrange / 1e3, alt / 1e3, color=C1)
for t_ev, txt in events + [(t[i_maxq], "Max-Q")]:
    j = int(np.argmin(np.abs(t - t_ev)))
    ax.plot(downrange[j] / 1e3, alt[j] / 1e3, "o", ms=5, color=C1, mec="white", mew=1.2)
    ax.annotate(
        txt,
        (downrange[j] / 1e3, alt[j] / 1e3),
        xytext=(6, -12),
        textcoords="offset points",
        fontsize=7.5,
        color=INK,
    )
ax.set_xlabel("Alcance sobre la superficie (km)")
ax.set_ylabel("Altitud (km)")
ax.set_title("Trayectoria de ascenso en el plano de vuelo (marco ECEF)", loc="left")
fig.tight_layout()
save(fig, "fig02_ascenso_trayectoria")

# Presupuesto de Δv de la EUS (ecuación de Tsiolkovsky)
m_upper0 = cfg2.upper_mass_kg
payload = m_upper0 - SLS_B1B_EUS.total_mass_kg
dv_insertion = v_circ_meco - speed_inertial[-1]  # γ ≈ 0: maniobra prógrada de circularización
ve_eus = SLS_B1B_EUS.isp_vac_s * G0_M_S2
dv_eus_total = ve_eus * np.log(m_upper0 / (SLS_B1B_EUS.dry_mass_kg + payload))
RESULTS.update(
    {
        "eus_payload_t": payload / 1e3,
        "dv_insertion_kms": dv_insertion / 1e3,
        "dv_eus_total_kms": dv_eus_total / 1e3,
    }
)

# ===========================================================================
# 2. INTEGRADORES: VERLET vs RK4 vs DOP853 (problema de Kepler)
# ===========================================================================
print("[2/6] Conservación: Verlet vs RK4 vs DOP853")
r_orb = EARTH.equatorial_radius_m + 400e3
st_c = circular_orbit_state(r_orb)
period = 2.0 * np.pi * np.sqrt(r_orb**3 / EARTH.mu_m3_s2)
n_orb = 200
dt_cmp = period / 40.0
e0 = compute_system_energy(st_c, 0.0, include_moon=False)
h0 = np.linalg.norm(np.cross(st_c.position, st_c.velocity))


def errors(traj: list[ArtemisState]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    tt = np.array([s.t for s in traj]) / period
    ee = np.array([abs(compute_system_energy(s, s.t, include_moon=False) / e0 - 1) for s in traj])
    hh = np.array([abs(np.linalg.norm(np.cross(s.position, s.velocity)) / h0 - 1) for s in traj])
    return tt, ee, hh


tv, ev, hv = errors(propagate_verlet(st_c, n_orb * period, dt_cmp, include_moon=False))
tr, er, hr = errors(propagate_rk4(st_c, n_orb * period, dt_cmp, include_moon=False))

y0 = np.concatenate([st_c.position, st_c.velocity])
t_eval = np.linspace(0, n_orb * period, 4000)
sol_d = solve_ivp(
    lambda _t, y: np.concatenate([y[3:], compute_gravity(y[:3], EARTH.mu_m3_s2)]),
    (0, n_orb * period),
    y0,
    method="DOP853",
    rtol=1e-10,
    atol=1e-6,
    t_eval=t_eval,
)
traj_d = [ArtemisState(sol_d.y[:3, k], sol_d.y[3:, k], 1.0, sol_d.t[k]) for k in range(t_eval.size)]
td, ed, hd = errors(traj_d)

RESULTS.update(
    {
        "verlet_max_dE": float(ev.max()),
        "rk4_final_dE": float(er[-1]),
        "dop853_final_dE": float(ed[-1]),
        "verlet_max_dh": float(hv.max()),
        "n_orbits_cmp": n_orb,
        "steps_per_orbit_cmp": 40,
    }
)

floor = 1e-16
fig, (ax_e, ax_h) = plt.subplots(2, 1, figsize=(7.0, 5.0), sharex=True)
env_k = np.floor(tv).astype(int)
tv_env = np.unique(env_k)
ev_env = np.array([ev[env_k == k].max() for k in tv_env])
ax_e.fill_between(tv, np.maximum(ev, floor), floor, color=C1, alpha=0.15, lw=0)
ax_e.plot(
    tv_env + 0.5,
    ev_env,
    color=C1,
    lw=1.4,
    label="Velocity Verlet (orden 2, simpléctico): envolvente por órbita",
)
ax_e.plot(
    tr, np.maximum(er, floor), color=C2, lw=1.4, label="RK4 clásico (orden 4, no simpléctico)"
)
ax_e.plot(td, np.maximum(ed, floor), color=C3, lw=1.4, label="DOP853 adaptativo, rtol = $10^{-10}$")
ax_e.set_yscale("log")
ax_e.set_ylabel(r"$|E(t)/E_0 - 1|$")
ax_e.set_title(
    f"(a) Error relativo de energía, paso fijo $\\Delta t = T/40$, {n_orb} órbitas a 400 km",
    loc="left",
)
ax_e.legend(loc="lower right")
ax_h.plot(tv, np.maximum(hv, floor), color=C1, lw=1.0, label="Velocity Verlet")
ax_h.plot(tr, np.maximum(hr, floor), color=C2, lw=1.4, label="RK4")
ax_h.plot(td, np.maximum(hd, floor), color=C3, lw=1.4, label="DOP853")
ax_h.set_yscale("log")
ax_h.set_ylabel(r"$|h(t)/h_0 - 1|$")
ax_h.set_xlabel("Número de órbitas")
ax_h.set_title("(b) Error relativo del momento angular específico", loc="left")
ax_h.legend(loc="center right")
fig.align_ylabels()
fig.tight_layout()
save(fig, "fig03_conservacion_integradores")

# ===========================================================================
# 3. ORDEN DE CONVERGENCIA (solución analítica de la órbita circular)
# ===========================================================================
print("[3/6] Orden de convergencia")
steps = np.array([25, 50, 100, 200, 400, 800, 1600])
err_v, err_r = [], []
r_exact = st_c.position  # tras una órbita completa vuelve al punto inicial
for nstep in steps:
    dt_k = period / nstep
    err_v.append(
        np.linalg.norm(
            propagate_verlet(st_c, period, dt_k, sample_every=10**9, include_moon=False)[
                -1
            ].position
            - r_exact
        )
    )
    err_r.append(
        np.linalg.norm(
            propagate_rk4(st_c, period, dt_k, sample_every=10**9, include_moon=False)[-1].position
            - r_exact
        )
    )
dts = period / steps
err_v, err_r = np.array(err_v), np.array(err_r)
p_v = np.polyfit(np.log(dts[2:]), np.log(err_v[2:]), 1)[0]
mask = err_r > 1e-6
p_r = np.polyfit(np.log(dts[mask][1:]), np.log(err_r[mask][1:]), 1)[0]
RESULTS.update({"order_verlet": p_v, "order_rk4": p_r})

fig, ax = plt.subplots(figsize=(4.6, 3.4))
ax.loglog(
    dts, err_v, "o-", color=C1, ms=5, mec="white", mew=1.0, label=f"Verlet, pendiente {p_v:.2f}"
)
ax.loglog(dts, err_r, "s-", color=C2, ms=5, mec="white", mew=1.0, label=f"RK4, pendiente {p_r:.2f}")
ref = err_v[3] * (dts / dts[3]) ** 2
ax.loglog(dts, ref, color=INK2, lw=0.8, ls=":", label=r"$\mathcal{O}(\Delta t^2)$")
ref4 = err_r[1] * (dts / dts[1]) ** 4
ax.loglog(dts, ref4, color=INK2, lw=0.8, ls="--", label=r"$\mathcal{O}(\Delta t^4)$")
ax.set_xlabel(r"Paso temporal $\Delta t$ (s)")
ax.set_ylabel(r"Error de posición tras 1 órbita (m)")
ax.set_title("Verificación del orden de convergencia", loc="left")
ax.legend(loc="upper left")
fig.tight_layout()
save(fig, "fig04_orden_convergencia")

# ===========================================================================
# 4. TLI: TARGETING POR MÉTODO DEL DISPARO
# ===========================================================================
print("[4/6] TLI + método del disparo (puede tardar ~1 min)")
h_park = 160e3
r_park = EARTH.equatorial_radius_m + h_park
t_flight = 4.0 * 86400.0
h_flyby = 4000e3
target_pos = moon_relative_target([0.0, MOON.equatorial_radius_m + h_flyby, 0.0], t_flight)
# Semilla kepleriana: elipse que alcanza |r_obj| en t_flight; el encendido se sitúa a una
# anomalía nu "detrás" del punto objetivo para que el apogeo quede alineado con la llegada.
geo = kepler_transfer_geometry(r_park, float(np.linalg.norm(target_pos)), t_flight)
phase_burn = float(np.arctan2(target_pos[1], target_pos[0])) - geo.transfer_angle_rad
st_park = circular_orbit_state(r_park, phase_rad=phase_burn, mass_kg=cfg2.upper_mass_kg)
dv_guess = (geo.perigee_speed_m_s - st_park.speed) * st_park.velocity / st_park.speed
res = solve_tli_shooting(
    st_park,
    target_pos,
    t_flight,
    dv_guess,
    propagator=make_dop853_propagator(include_moon=True),
    tol_m=1.0,
    max_iter=20,
)
print("   ", res.message, f"|Δv| = {res.delta_v_norm:.2f} m/s")
mass_after_tli = cfg2.upper_mass_kg * np.exp(-(dv_insertion + res.delta_v_norm) / ve_eus)
RESULTS.update(
    {
        "h_park_km": h_park / 1e3,
        "tli_dv_ms": res.delta_v_norm,
        "tli_guess_dv_ms": float(np.linalg.norm(dv_guess)),
        "tli_iterations": res.iterations,
        "tli_final_residual_m": res.final_residual,
        "tli_initial_residual_km": res.residual_history[0] / 1e3,
        "tli_flight_days": t_flight / 86400.0,
        "tli_flyby_alt_km": h_flyby / 1e3,
        "tli_transfer_angle_deg": float(np.degrees(geo.transfer_angle_rad)),
        "tli_apogee_kkm": geo.apogee_radius_m / 1e6,
        "eus_prop_remaining_t": (mass_after_tli - SLS_B1B_EUS.dry_mass_kg - payload) / 1e3,
        "tli_converged": float(res.converged),
    }
)

st_tli = impulsive_burn(st_park, res.delta_v)
traj = propagate_verlet(st_tli, t_flight, dt=1.0, sample_every=60, include_moon=True)
T = np.array([s.t for s in traj])
R = np.array([s.position for s in traj])
RM = np.array([get_body_position(MOON, ti) for ti in T])
d_moon_end = np.linalg.norm(R[-1] - RM[-1])
RESULTS["verlet_arrival_alt_km"] = (d_moon_end - MOON.equatorial_radius_m) / 1e3
RESULTS["verlet_target_miss_km"] = np.linalg.norm(R[-1] - target_pos) / 1e3

# Marco rotante Tierra-Luna (eje x apuntando a la Luna)
n_moon = DEFAULT_LUNAR_CONFIG.mean_motion_rad_s
th = n_moon * T
Xr = np.cos(th) * R[:, 0] + np.sin(th) * R[:, 1]
Yr = -np.sin(th) * R[:, 0] + np.cos(th) * R[:, 1]

fig, (ax_i, ax_r) = plt.subplots(1, 2, figsize=(7.2, 3.8))
for a in (ax_i, ax_r):
    a.set_aspect("equal")
ax_i.add_patch(plt.Circle((0, 0), EARTH.equatorial_radius_m / 1e6 * 4, color=EARTH_FILL, zorder=2))
ax_i.plot(
    RM[:, 0] / 1e6,
    RM[:, 1] / 1e6,
    color=INK2,
    lw=0.9,
    ls=(0, (4, 3)),
    label="Órbita lunar (arco de vuelo)",
)
ax_i.plot(R[:, 0] / 1e6, R[:, 1] / 1e6, color=C1, label="Trayectoria translunar")
ax_i.add_patch(plt.Circle((RM[0, 0] / 1e6, RM[0, 1] / 1e6), 6, color=MOON_FILL, zorder=2))
ax_i.add_patch(
    plt.Circle((RM[-1, 0] / 1e6, RM[-1, 1] / 1e6), 6, color=MOON_FILL, ec=INK2, lw=0.6, zorder=2)
)
ax_i.annotate(
    "Luna, $t=0$",
    (RM[0, 0] / 1e6, RM[0, 1] / 1e6),
    xytext=(8, -12),
    textcoords="offset points",
    fontsize=7.5,
)
ax_i.annotate(
    "Luna, $t=4$ d",
    (RM[-1, 0] / 1e6, RM[-1, 1] / 1e6),
    xytext=(-75, -4),
    textcoords="offset points",
    fontsize=7.5,
)
ax_i.set_xlabel(r"$x_{\mathrm{ECI}}$ ($10^3$ km)")
ax_i.set_ylabel(r"$y_{\mathrm{ECI}}$ ($10^3$ km)")
ax_i.set_title("(a) Marco inercial geocéntrico", loc="left")
ax_i.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=7)

ax_r.add_patch(plt.Circle((0, 0), EARTH.equatorial_radius_m / 1e6 * 4, color=EARTH_FILL, zorder=2))
ax_r.add_patch(
    plt.Circle((DEFAULT_LUNAR_CONFIG.orbital_radius_m / 1e6, 0), 6, color=MOON_FILL, zorder=2)
)
ax_r.plot(Xr / 1e6, Yr / 1e6, color=C1)
ax_r.annotate(
    "Luna (fija)",
    (DEFAULT_LUNAR_CONFIG.orbital_radius_m / 1e6, 0),
    xytext=(-30, 12),
    textcoords="offset points",
    fontsize=7.5,
)
ax_r.set_xlabel(r"$x_{\mathrm{rot}}$ ($10^3$ km)")
ax_r.set_ylabel(r"$y_{\mathrm{rot}}$ ($10^3$ km)")
ax_r.set_title("(b) Marco rotante Tierra-Luna", loc="left")
ax_r.text(
    0.02,
    1.0,
    "Radios de Tierra y Luna\nexagerados para visibilidad",
    transform=ax_r.transAxes,
    fontsize=6.5,
    color=INK2,
)
fig.tight_layout()
save(fig, "fig05_trayectoria_tli")

# Acercamiento al encuentro (selenocéntrico)
fig, ax = plt.subplots(figsize=(4.4, 3.8))
ax.set_aspect("equal")
k0 = int(np.argmax(np.linalg.norm(R - RM, axis=1) < 60e6))
rel = (R[k0:] - RM[k0:]) / 1e6
ax.add_patch(plt.Circle((0, 0), MOON.equatorial_radius_m / 1e6, color=MOON_FILL, zorder=2))
ax.add_patch(
    plt.Circle(
        (0, 0), (MOON.equatorial_radius_m + h_flyby) / 1e6, fill=False, ec=INK2, lw=0.6, ls=":"
    )
)
ax.plot(rel[:, 0], rel[:, 1], color=C1)
tgt = (target_pos - RM[-1]) / 1e6
ax.plot(tgt[0], tgt[1], marker="+", ms=10, mew=1.4, color=C2, ls="none", label="Punto objetivo")
ax.plot(
    rel[-1, 0],
    rel[-1, 1],
    "o",
    ms=5,
    color=C1,
    mec="white",
    mew=1.0,
    ls="none",
    label="Llegada ($t = 4$ d)",
)
ax.set_xlabel(r"$x - x_L$ ($10^3$ km)")
ax.set_ylabel(r"$y - y_L$ ($10^3$ km)")
ax.set_title("Aproximación lunar (centrado en la Luna)", loc="left")
ax.legend(loc="lower left")
fig.tight_layout()
save(fig, "fig06_encuentro_lunar")

# ===========================================================================
# 5. CONVERGENCIA DEL MÉTODO DEL DISPARO
# ===========================================================================
print("[5/6] Convergencia de Newton-Raphson")
fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(7.0, 2.8))
it = np.arange(len(res.residual_history))
ax_a.semilogy(it, res.residual_history, "o-", color=C1, ms=5, mec="white", mew=1.0)
ax_a.axhline(1.0, color=INK2, lw=0.7, ls=":")
ax_a.text(it[-1], 1.3, "tolerancia 1 m", ha="right", fontsize=7.5, color=INK2)
ax_a.set_xlabel("Iteración de Newton")
ax_a.set_ylabel(r"$\|\mathbf{F}(\Delta\mathbf{v})\|$ (m)")
ax_a.set_title("(a) Residuo de posición", loc="left")
ax_a.set_xticks(it)
ic = np.arange(1, len(res.condition_number_history) + 1)
ax_b.semilogy(ic, res.condition_number_history, "s-", color=C1, ms=5, mec="white", mew=1.0)
ax_b.set_xlabel("Iteración de Newton")
ax_b.set_ylabel(r"$\kappa(\mathbf{J})$")
ax_b.set_title("(b) Número de condición del Jacobiano", loc="left")
ax_b.set_xticks(ic)
fig.tight_layout()
save(fig, "fig07_convergencia_disparo")
RESULTS["cond_max"] = float(max(res.condition_number_history))

# ===========================================================================
# 6. INVARIANTE DE JACOBI vs ENERGÍA GEOCÉNTRICA EN EL TRÁNSITO
# ===========================================================================
print("[6/6] Integral de Jacobi")
traj_j = propagate_verlet(st_tli, t_flight, dt=1.0, sample_every=60, include_moon=True)
TJ = np.array([s.t for s in traj_j]) / 86400.0
EJ = np.array([compute_jacobi_constant(s) for s in traj_j])
EG = np.array([compute_system_energy(s, s.t) for s in traj_j])
dEJ = np.abs(EJ / EJ[0] - 1)
dEG = np.abs(EG / EG[0] - 1)
RESULTS.update({"jacobi_max_rel": float(dEJ.max()), "geo_energy_max_rel": float(dEG.max())})

fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(7.0, 4.2), sharex=True)
ax_a.plot(TJ, EG / 1e6, color=C2)
ax_a.set_ylabel(r"$\varepsilon_{geo}$ (km$^2$/s$^2$)")
ax_a.set_title(
    r"(a) Energía específica geocéntrica: no conservada ($\partial H/\partial t \neq 0$)",
    loc="left",
)
ax_b.semilogy(TJ, np.maximum(dEJ, 1e-16), color=C1, lw=1.0)
ax_b.set_ylabel(r"$|E_J(t)/E_J(0) - 1|$")
ax_b.set_ylim(1e-9, 1e-4)
ax_b.set_xlabel("Tiempo desde la TLI (días)")
ax_b.set_title(r"(b) Integral de Jacobi del CR3BP con Verlet, $\Delta t = 1$ s", loc="left")
fig.align_ylabels()
fig.tight_layout()
save(fig, "fig08_jacobi")

# ===========================================================================
# EXPORTAR RESULTADOS
# ===========================================================================
(PNG_DIR / "results.json").write_text(json.dumps(RESULTS, indent=2))


def latex_sci(x: float, digits: int = 1) -> str:
    m, e = f"{x:.{digits}e}".split("e")
    return f"\\num{{{m}e{int(e)}}}"


fmt = {
    "liftoff_mass_t": "{:,.0f}",
    "srb_scale": "{:.4f}",
    "t_mach1_s": "{:.1f}",
    "h_mach1_km": "{:.1f}",
    "t_maxq_s": "{:.1f}",
    "maxq_kpa": "{:.1f}",
    "h_maxq_km": "{:.1f}",
    "mach_maxq": "{:.2f}",
    "t_srb_sep_s": "{:.0f}",
    "h_srb_sep_km": "{:.1f}",
    "v_srb_sep_kms": "{:.2f}",
    "t_meco_s": "{:.1f}",
    "h_meco_km": "{:.1f}",
    "v_meco_kms": "{:.3f}",
    "fpa_meco_deg": "{:.2f}",
    "downrange_meco_km": "{:,.0f}",
    "max_g": "{:.2f}",
    "v_circ_meco_kms": "{:.3f}",
    "mass_meco_t": "{:.1f}",
    "eus_payload_t": "{:.1f}",
    "dv_insertion_kms": "{:.3f}",
    "dv_eus_total_kms": "{:.3f}",
    "order_verlet": "{:.2f}",
    "order_rk4": "{:.2f}",
    "h_park_km": "{:.0f}",
    "tli_dv_ms": "{:,.1f}",
    "tli_guess_dv_ms": "{:,.1f}",
    "tli_iterations": "{:.0f}",
    "tli_initial_residual_km": "{:,.0f}",
    "tli_flight_days": "{:.0f}",
    "tli_flyby_alt_km": "{:,.0f}",
    "tli_transfer_angle_deg": "{:.1f}",
    "tli_apogee_kkm": "{:.0f}",
    "eus_prop_remaining_t": "{:.1f}",
    "verlet_arrival_alt_km": "{:,.0f}",
    "verlet_target_miss_km": "{:.2f}",
    "n_orbits_cmp": "{:.0f}",
    "steps_per_orbit_cmp": "{:.0f}",
}
sci = [
    "verlet_max_dE",
    "rk4_final_dE",
    "dop853_final_dE",
    "verlet_max_dh",
    "tli_final_residual_m",
    "jacobi_max_rel",
    "geo_energy_max_rel",
    "cond_max",
]

lines = ["% Archivo autogenerado por scripts/generate_figures.py. NO EDITAR A MANO."]
for key, val in RESULTS.items():
    name = "R" + "".join(part.capitalize() for part in key.split("_"))
    name = "".join(ch for ch in name if ch.isalpha() or ch.isdigit())
    name = name.replace("0", "Zero").replace("1", "One").replace("4", "Four").replace("8", "Eight")
    name = name.replace("3", "Three").replace("5", "Five")
    if key in sci:
        txt = latex_sci(val)
    elif key in fmt:
        txt = fmt[key].format(val).replace(",", "\\,")
    else:
        continue
    lines.append(f"\\newcommand{{\\{name}}}{{{txt}}}")
(ROOT / "docs" / "paper" / "final" / "results.tex").write_text("\n".join(lines) + "\n")
print("Resultados exportados:")
for k_, v_ in RESULTS.items():
    print(f"  {k_:28s} {v_:.6g}")
