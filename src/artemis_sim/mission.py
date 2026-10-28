"""Encadena las fases en una sola trayectoria continua: ascenso → aparcamiento → TLI → NRHO.

`build_mission_phases_1_to_3` llega hasta el sobrevuelo lunar de la Fase 3;
`build_mission_phases_1_to_4` sigue con el OPF y la inserción en la NRHO de Gateway.

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
from artemis_sim.constants import (
    EARTH,
    EARTH_ROTATION,
    G0_M_S2,
    I_HAB_MASS_KG,
    MOON,
    ORION,
    SLS_B1B_EUS,
)
from artemis_sim.cr3bp import MU, UNITS, eci_to_rotating, propagate, rotating_to_eci
from artemis_sim.ephemeris import LUNAR_MEAN_MOTION_RAD_S, LunarOrbitConfig, get_body_position
from artemis_sim.export import MissionEvent, MissionPhase, MissionTrajectory, concatenate_segments
from artemis_sim.nrho_transfer import (
    NrhoTransfer,
    departure_angle,
    optimize_nrho_transfer,
    refine_transfer,
)
from artemis_sim.periodic_orbits import PeriodicOrbit, find_nrho
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


@dataclass(frozen=True, slots=True)
class MissionSummaryPhase4:
    """Valores clave de la misión hasta la NRHO (SI)."""

    phases_1_to_3: MissionSummary
    t_tli_s: float
    t_opf_s: float
    t_nri_s: float
    dv_tli_m_s: float
    dv_opf_m_s: float
    dv_nri_m_s: float
    opf_altitude_m: float
    mass_after_tli_kg: float
    mass_in_nrho_kg: float
    orion_dv_capability_m_s: float
    transfer: NrhoTransfer
    nrho: PeriodicOrbit


def _rotating_segment(
    t_nd: npt.NDArray[np.float64],
    states: npt.NDArray[np.float64],
    t0_s: float,
    mass_kg: float,
    lunar: LunarOrbitConfig,
) -> Segment:
    """Tramo adimensional rotante → (t, y) en ECI SI con masa constante."""
    t = t0_s + t_nd * UNITS.time_s
    y = np.empty((7, t.size))
    for i in range(t.size):
        st = rotating_to_eci(states[:, i], float(t[i]), lunar)
        y[0:3, i], y[3:6, i], y[6, i] = st.position, st.velocity, mass_kg
    return t, y


def _orion_burn_mass(mass_kg: float, dv_m_s: float) -> float:
    return mass_kg * float(np.exp(-dv_m_s / (ORION.isp_vac_s * G0_M_S2)))


def build_mission_phases_1_to_4(
    nrho_revolutions: float = 1.0,
) -> tuple[MissionTrajectory, MissionSummaryPhase4]:
    """Misión continua despegue → aparcamiento → TLI → OPF → NRI → NRHO.

    1. Se construyen las Fases 1–3 (dan la TLI semilla y la geometría de la ventana).
    2. Se optimiza la transferencia TLI → OPF → NRI en el CR3BP (`optimize_nrho_transfer`).
    3. Ventana de lanzamiento: el α óptimo del punto de la TLI se consigue girando la fase
       inicial de la Luna, φ0' = φ0 + (α_semilla − α_óptimo); se repropaga el aparcamiento.
    4. Se refina la transferencia con el punto de partida real y se pasa todo a ECI.
    Tras la TLI la EUS se separa: queda Orion + I-Hab, y los encendidos usan el OMS-E.
    """
    traj3, summ3 = build_mission_phases_1_to_3()
    lunar0 = traj3.lunar_config
    t_meco, t_tli = summ3.t_meco_s, summ3.t_tli_s
    i_tli = int(np.searchsorted(traj3.t, t_tli))
    post = ArtemisState(traj3.y[0:3, i_tli], traj3.y[3:6, i_tli], 1.0, t_tli)
    pre = ArtemisState(post.position, post.velocity - summ3.shooting.delta_v, 1.0, t_tli)
    pre_rot, post_rot = eci_to_rotating(pre, lunar0), eci_to_rotating(post, lunar0)

    nrho = find_nrho()
    opt = optimize_nrho_transfer(pre_rot, post_rot, nrho)

    phase0 = lunar0.initial_phase_rad + departure_angle(pre_rot) - opt.departure_angle
    lunar = LunarOrbitConfig(
        inclination_rad=lunar0.inclination_rad,
        raan_rad=lunar0.raan_rad,
        initial_phase_rad=float(np.mod(phase0, 2.0 * np.pi)),
    )
    i_meco = int(np.searchsorted(traj3.t, t_meco, side="right")) - 1
    st_park0 = ArtemisState(traj3.y[0:3, i_meco], traj3.y[3:6, i_meco], traj3.y[6, i_meco], t_meco)
    coast = propagate_verlet(
        st_park0, t_tli, dt=1.0, sample_every=10, include_moon=True, lunar_config=lunar
    )
    burn_rot = eci_to_rotating(coast[-1], lunar)
    tr = refine_transfer(opt, burn_rot, nrho)

    # Masas: separación de la EUS tras la TLI; OPF y NRI con el OMS-E de Orion
    m_tli = ORION.dry_mass_kg + ORION.propellant_mass_kg + I_HAB_MASS_KG
    m_opf = _orion_burn_mass(m_tli, tr.dv_opf_m_s)
    m_nri = _orion_burn_mass(m_opf, tr.dv_nri_m_s)

    asc = traj3.t <= t_meco
    segments: list[Segment] = [(traj3.t[asc], traj3.y[:, asc]), _states_to_segment(coast)]
    t_nd = 0.0
    for i, (x, dt) in enumerate(zip(tr.nodes, tr.durations, strict=True)):
        prop = propagate(x, float(dt), dense_points=300)
        mass = m_tli if i < tr.flyby_node else m_opf
        segments.append(_rotating_segment(t_nd + prop.t, prop.states, t_tli, mass, lunar))
        t_nd += float(dt)
    t_opf = t_tli + tr.flyby_time * UNITS.time_s
    t_nri = t_tli + tr.time_of_flight * UNITS.time_s
    orbit_prop = propagate(tr.nrho_state, nrho_revolutions * nrho.period, dense_points=8000)
    segments.append(_rotating_segment(orbit_prop.t, orbit_prop.states, t_nri, m_nri, lunar))

    t_all, y_all = concatenate_segments(segments)
    phases = [
        MissionPhase("ascent", "Ascenso", 0.0, t_meco),
        MissionPhase("parking", "Órbita de aparcamiento", t_meco, t_tli),
        MissionPhase("transit", "Tránsito translunar", t_tli, t_nri),
        MissionPhase("nrho", "NRHO de Gateway", t_nri, float(t_all[-1])),
    ]
    keep = {"Max-Q", "Separación de SRB", "MECO y separación de la etapa central"}
    events = [e for e in traj3.events if e.label in keep] + [
        MissionEvent(t_meco, "Inserción en órbita (EUS)"),
        MissionEvent(t_tli, "Inyección translunar (TLI) y separación de la EUS"),
        MissionEvent(t_opf, "Sobrevuelo lunar propulsado (OPF)"),
        MissionEvent(t_nri, "Inserción en la NRHO (NRI)"),
        MissionEvent(float(t_all[-1]), f"Fin: {nrho_revolutions:g} vuelta(s) a la NRHO"),
    ]
    traj = MissionTrajectory(t_all, y_all, phases, events, lunar)

    moon = np.array([1.0 - MU, 0.0, 0.0])
    opf_alt = (
        float(np.linalg.norm(tr.nodes[tr.flyby_node, 0:3] - moon)) * UNITS.length_m
        - MOON.equatorial_radius_m
    )
    ve = ORION.isp_vac_s * G0_M_S2
    summary = MissionSummaryPhase4(
        phases_1_to_3=summ3,
        t_tli_s=t_tli,
        t_opf_s=t_opf,
        t_nri_s=t_nri,
        dv_tli_m_s=tr.dv_tli_m_s,
        dv_opf_m_s=tr.dv_opf_m_s,
        dv_nri_m_s=tr.dv_nri_m_s,
        opf_altitude_m=opf_alt,
        mass_after_tli_kg=m_tli,
        mass_in_nrho_kg=m_nri,
        orion_dv_capability_m_s=ve * float(np.log(m_tli / (m_tli - ORION.propellant_mass_kg))),
        transfer=tr,
        nrho=nrho,
    )
    return traj, summary
