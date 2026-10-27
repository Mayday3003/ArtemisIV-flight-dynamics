"""Encadena las Fases 1–3 en una sola trayectoria continua: ascenso → aparcamiento → TLI.

Secuencia física:
1. Ascenso real desde el LC-39B hasta el MECO (`simulate_full_ascent`).
2. Separación de la etapa central en el MECO: queda la masa superior (EUS + carga útil).
3. Inserción impulsiva de la EUS: maniobra prógrada hasta la velocidad circular local
   (en el MECO el ángulo de trayectoria es ~0, así que la órbita resultante es casi circular).
4. Órbita de aparcamiento hasta el punto de encendido de la TLI.
5. TLI calculada con el método del disparo (DOP853) y tránsito de 4 días con Verlet.

Ventana de lanzamiento: desde Florida la órbita de aparcamiento queda inclinada ~28.6°.
En lugar de pagar un cambio de plano, se elige la geometría de la Luna (inclinación, nodo y
fase en t = 0) para que su órbita contenga el plano de aparcamiento y la Luna esté donde
debe estar al llegar, como se hace al planificar una ventana de lanzamiento real.
La masa se actualiza con Tsiolkovsky en cada encendido impulsivo de la EUS.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from artemis_sim.ascent_solver import AscentConfig, simulate_full_ascent
from artemis_sim.constants import EARTH, EARTH_ROTATION, G0_M_S2, MOON, SLS_B1B_EUS
from artemis_sim.ephemeris import LUNAR_MEAN_MOTION_RAD_S, LunarOrbitConfig, get_body_position
from artemis_sim.export import MissionEvent, MissionPhase, MissionTrajectory, concatenate_segments
from artemis_sim.physics_engine import compute_dynamic_pressure, compute_relative_velocity
from artemis_sim.shooting_method import (
    ShootingResult,
    kepler_transfer_geometry,
    make_dop853_propagator,
    solve_tli_shooting,
)
from artemis_sim.state import ArtemisState
from artemis_sim.symplectic_solver import propagate_verlet

Segment = tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]


@dataclass(frozen=True, slots=True)
class MissionSummary:
    """Valores clave de la misión construida (SI)."""

    t_meco_s: float
    t_tli_s: float
    t_arrival_s: float
    dv_insertion_m_s: float
    dv_tli_m_s: float
    parking_inclination_rad: float
    flyby_altitude_m: float
    shooting: ShootingResult


def _states_to_segment(states: list[ArtemisState]) -> Segment:
    t = np.array([s.t for s in states])
    y = np.vstack([np.concatenate([s.position, s.velocity, [s.mass]]) for s in states]).T
    return t, y


def _impulsive_burn_with_mass(state: ArtemisState, dv: npt.NDArray[np.float64]) -> ArtemisState:
    """Encendido impulsivo de la EUS: cambia v y descuenta propelente (Tsiolkovsky)."""
    ve = SLS_B1B_EUS.isp_vac_s * G0_M_S2
    m_after = state.mass * float(np.exp(-np.linalg.norm(dv) / ve))
    return ArtemisState(state.position, state.velocity + dv, m_after, state.t)


def build_mission_phases_1_to_3(
    parking_orbits_before_tli: float = 1.5,
    t_flight_s: float = 4.0 * 86400.0,
    flyby_altitude_m: float = 4_000e3,
    transit_dt_s: float = 1.0,
) -> tuple[MissionTrajectory, MissionSummary]:
    """Construye la trayectoria continua despegue → MECO → aparcamiento → TLI → llegada.

    Parámetros
    ----------
    parking_orbits_before_tli : float
        Vueltas en la órbita de aparcamiento antes de la TLI (las misiones reales hacen 1–2).
    t_flight_s : float
        Tiempo de vuelo de la TLI hasta el punto objetivo cerca de la Luna (s).
    flyby_altitude_m : float
        Altitud del punto objetivo sobre la superficie lunar (m).
    transit_dt_s : float
        Paso de Verlet durante el tránsito (s).
    """
    mu = EARTH.mu_m3_s2
    cfg = AscentConfig()

    # 1. Ascenso real hasta el MECO
    asc = simulate_full_ascent(max_step_s=0.5)
    segments: list[Segment] = [(asc.t, asc.y.copy())]
    t_meco = asc.t_meco_s
    r_meco, v_meco = asc.y[0:3, -1], asc.y[3:6, -1]

    # Max-Q y Mach 1 para los eventos
    alt = np.linalg.norm(asc.y[0:3], axis=0) - EARTH.equatorial_radius_m
    v_rel = np.array(
        [
            compute_relative_velocity(asc.y[0:3, i], asc.y[3:6, i], EARTH_ROTATION.omega_rad_s)
            for i in range(asc.t.size)
        ]
    )
    q = np.array(
        [
            compute_dynamic_pressure(float(np.linalg.norm(v_rel[i])), alt[i])
            for i in range(asc.t.size)
        ]
    )
    t_maxq = float(asc.t[int(np.argmax(q))])

    # 2–3. Separación de la etapa central + inserción prógrada de la EUS
    m_upper = cfg.upper_mass_kg
    r_norm = float(np.linalg.norm(r_meco))
    v_circ = np.sqrt(mu / r_norm)
    dv_ins = (v_circ - float(np.linalg.norm(v_meco))) * v_meco / np.linalg.norm(v_meco)
    st_park0 = _impulsive_burn_with_mass(ArtemisState(r_meco, v_meco, m_upper, t_meco), dv_ins)

    # Plano de la órbita de aparcamiento
    h_vec = np.cross(st_park0.position, st_park0.velocity)
    h_hat = h_vec / np.linalg.norm(h_vec)
    inclination = float(np.arccos(np.clip(h_hat[2], -1.0, 1.0)))
    raan = float(np.arctan2(h_hat[0], -h_hat[1]))
    plane = LunarOrbitConfig(inclination_rad=inclination, raan_rad=raan)
    p_hat, q_hat, _ = plane.plane_basis()

    def arg_latitude(r: npt.NDArray[np.float64]) -> float:
        return float(np.arctan2(np.dot(r, q_hat), np.dot(r, p_hat)))

    # 4. Ventana: TLI tras N vueltas; se elige la fase lunar para que la Luna esté a punto
    n_park = np.sqrt(mu / r_norm**3)
    t_tli = t_meco + parking_orbits_before_tli * 2.0 * np.pi / n_park
    u_tli = arg_latitude(st_park0.position) + n_park * (t_tli - t_meco)
    d_moon = plane.orbital_radius_m
    off = MOON.equatorial_radius_m + flyby_altitude_m
    r_target_norm = float(np.hypot(d_moon, off))
    geo = kepler_transfer_geometry(r_norm, r_target_norm, t_flight_s)
    # El objetivo va `off` por delante de la Luna en su plano: ángulo extra atan(off / d)
    phase0 = (
        u_tli
        + geo.transfer_angle_rad
        - np.arctan2(off, d_moon)
        - LUNAR_MEAN_MOTION_RAD_S * (t_tli + t_flight_s)
    )
    phase0 = float(np.mod(phase0, 2.0 * np.pi))
    lunar = LunarOrbitConfig(inclination_rad=inclination, raan_rad=raan, initial_phase_rad=phase0)

    coast = propagate_verlet(
        st_park0, t_tli, dt=1.0, sample_every=10, include_moon=True, lunar_config=lunar
    )
    segments.append(_states_to_segment(coast))
    st_burn = coast[-1]

    # 5. TLI por el método del disparo
    t_arr = t_tli + t_flight_s
    r_moon_arr = get_body_position(MOON, t_arr, config=lunar)
    _, _, h_moon = lunar.plane_basis()
    along = np.cross(h_moon, r_moon_arr / np.linalg.norm(r_moon_arr))
    target = r_moon_arr + off * along
    v_hat = st_burn.velocity / st_burn.speed
    dv_guess = (geo.perigee_speed_m_s - st_burn.speed) * v_hat
    shot = solve_tli_shooting(
        st_burn,
        target,
        t_flight_s,
        dv_guess,
        propagator=make_dop853_propagator(include_moon=True, lunar_config=lunar),
        tol_m=1.0,
        max_iter=20,
    )
    if not shot.converged:
        raise RuntimeError(f"El método del disparo no convergió: {shot.message}")
    st_tli = _impulsive_burn_with_mass(st_burn, shot.delta_v)

    transit = propagate_verlet(
        st_tli, t_arr, dt=transit_dt_s, sample_every=10, include_moon=True, lunar_config=lunar
    )
    segments.append(_states_to_segment(transit))

    t_all, y_all = concatenate_segments(segments)
    phases = [
        MissionPhase("ascent", "Ascenso", 0.0, t_meco),
        MissionPhase("parking", "Órbita de aparcamiento", t_meco, t_tli),
        MissionPhase("transit", "Tránsito translunar", t_tli, t_arr),
    ]
    events = [
        MissionEvent(t_maxq, "Max-Q"),
        MissionEvent(asc.t_srb_separation_s, "Separación de SRB"),
        MissionEvent(t_meco, "MECO y separación de la etapa central"),
        MissionEvent(t_meco, "Inserción en órbita (EUS)"),
        MissionEvent(t_tli, "Inyección translunar (TLI)"),
        MissionEvent(t_arr, "Llegada a la Luna"),
    ]
    traj = MissionTrajectory(t_all, y_all, phases, events, lunar)
    final_alt = float(np.linalg.norm(transit[-1].position - r_moon_arr)) - MOON.equatorial_radius_m
    summary = MissionSummary(
        t_meco_s=t_meco,
        t_tli_s=t_tli,
        t_arrival_s=t_arr,
        dv_insertion_m_s=float(np.linalg.norm(dv_ins)),
        dv_tli_m_s=shot.delta_v_norm,
        parking_inclination_rad=inclination,
        flyby_altitude_m=final_alt,
        shooting=shot,
    )
    return traj, summary
