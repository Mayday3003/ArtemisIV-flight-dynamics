"""Módulo de solución y programación del ascenso atmosférico para Artemis IV.

Integra numéricamente el ascenso de la configuración SLS Block 1B desde la plataforma de
lanzamiento (LC-39B en ECI) pasando por la fase de combustión atmosférica, separación
de boosters (SRB) y cruce de la línea de 100 km de altitud.

Marco de referencia: ECI (Earth-Centered Inertial, equinoccio J2000).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np
import numpy.typing as npt

from artemis_sim.constants import (
    EARTH,
    EARTH_ROTATION,
    G0_M_S2,
    SLS_B1B_CORE_STAGE,
    SLS_B1B_SRB_PAIR,
    StageSpec,
)
from artemis_sim.physics_engine import (
    compute_aerodynamic_drag,
    compute_altitude,
    compute_atmospheric_pressure,
    compute_drag_coefficient,
    compute_gravity,
    compute_mach_number,
    compute_mass_flow,
    compute_relative_velocity,
    compute_thrust,
)
from artemis_sim.state import ArtemisState


class ThrustDirection(Protocol):
    """Protocolo formal para funciones que determinan la orientación del vector unitario de empuje.

    Firma: (t, position, v_rel) -> vector_unitario (3,)
    """

    def __call__(
        self,
        t: float,
        position: npt.NDArray[np.float64],
        v_rel: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]: ...


def radial_direction(
    t: float,
    position: npt.NDArray[np.float64],
    v_rel: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Programa de dirección vertical local (radial outward).

    Orienta el empuje a lo largo del vector de posición geocéntrico r / ||r||.
    Apropiado para el despegue inmediato y despeje de la torre de lanzamiento.
    """
    pos_norm = float(np.linalg.norm(position))
    if pos_norm == 0.0:
        return np.array([0.0, 0.0, 1.0], dtype=np.float64)
    return position / pos_norm


def pitch_kick_direction(
    t_kick: float = 10.0,
    pitch_angle_rad: float = 0.035,  # ~2 grados de cabeceo inicial
    azimuth_rad: float = 1.5707963267948966,  # 90 grados (Este / lanzamiento hacia el Atlántico)
) -> ThrustDirection:
    """Genera una función de dirección de cabeceo con transición a giro por gravedad (gravity turn).

    Comportamiento:
    - Para t < t_kick: Ascenso vertical puro colineal a r.
    - Para t_kick <= t < t_kick + 5.0 s: Realiza la maniobra de cabeceo ('pitch kick')
      inclinando suavemente el empuje en dirección este/azimut.
    - Para t >= t_kick + 5.0 s: Alinea el empuje con el vector de velocidad relativa al aire v_rel,
      manteniendo un ángulo de ataque casi nulo (alfa ≈ 0) para minimizar cargas aerodinámicas.
    """

    def _direction_func(
        t: float,
        position: npt.NDArray[np.float64],
        v_rel: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        pos_norm = float(np.linalg.norm(position))
        r_unit = position / pos_norm if pos_norm > 0.0 else np.array([0.0, 0.0, 1.0])

        if t < t_kick:
            return r_unit

        v_norm = float(np.linalg.norm(v_rel))
        # Si todavía no hay velocidad relativa apreciable, usamos la inclinación programada
        if v_norm < 10.0 or t < t_kick + 5.0:
            # Construir sistema local: Up (r_unit), East (vector normal a z y Up)
            z_axis = np.array([0.0, 0.0, 1.0], dtype=np.float64)
            east = np.cross(z_axis, r_unit)
            east_norm = float(np.linalg.norm(east))
            if east_norm > 1e-6:
                east = east / east_norm
            else:
                east = np.array([0.0, 1.0, 0.0], dtype=np.float64)
            north = np.cross(r_unit, east)

            # Vector horizontal hacia el azimut deseado
            h_dir = np.cos(azimuth_rad) * north + np.sin(azimuth_rad) * east
            # Combinación vertical e inclinación de cabeceo
            u_dir = np.cos(pitch_angle_rad) * r_unit + np.sin(pitch_angle_rad) * h_dir
            u_norm = float(np.linalg.norm(u_dir))
            return u_dir / u_norm if u_norm > 0.0 else r_unit

        # Gravity turn continuo: empuje alineado con la velocidad relativa
        return v_rel / v_norm

    return _direction_func


# Perfil normalizado de empuje de un SRB de 5 segmentos: (t [s], fracción del empuje pico).
# El grano de PBAN se diseña con un empuje regresivo: alto en el despegue, reducido en la
# región de máxima presión dinámica (Max-Q) y con una cola de apagado progresiva.
# Forma representativa de la curva pública de Northrop Grumman (QM-1/QM-2).
SRB_THRUST_PROFILE: tuple[tuple[float, ...], tuple[float, ...]] = (
    (0.0, 20.0, 50.0, 80.0, 105.0, 115.0, 126.0),
    (1.0, 1.0, 0.85, 0.90, 0.80, 0.35, 0.0),
)


def srb_thrust_fraction(t: float, t_burn_s: float) -> float:
    """Fracción f(t) in [0, 1] del empuje pico de los SRB (perfil escalado a t_burn_s)."""
    if t < 0.0 or t >= t_burn_s:
        return 0.0
    t_nodes = np.asarray(SRB_THRUST_PROFILE[0]) * (t_burn_s / SRB_THRUST_PROFILE[0][-1])
    return float(np.interp(t, t_nodes, SRB_THRUST_PROFILE[1]))


def srb_thrust_scale(spec: StageSpec, t_burn_s: float) -> float:
    """Factor k que hace que el perfil consuma exactamente la masa de propelente de los SRB.

    Conservación de masa: integral_0^tb m_dot dt = m_p, con m_dot = k f(t) T_vac / (Isp g0).
    Por tanto k = m_p Isp g0 / (T_vac integral_0^tb f(t) dt). Con los datos nominales
    k ≈ 1.00, lo que confirma la coherencia entre empuje pico, Isp, masa y tiempo de combustión.
    """
    t_nodes = np.asarray(SRB_THRUST_PROFILE[0]) * (t_burn_s / SRB_THRUST_PROFILE[0][-1])
    integral_f = float(np.trapezoid(SRB_THRUST_PROFILE[1], t_nodes))
    total_impulse = spec.propellant_mass_kg * spec.isp_vac_s * G0_M_S2
    return total_impulse / (spec.thrust_vac_n * integral_f)


def linear_tangent_direction(
    t_kick: float = 10.0,
    pitch_angle_rad: float = 0.02,
    t_guidance: float = 126.0,
    t_final: float = 480.0,
    theta_start_rad: float = 0.4915,
    theta_end_rad: float = 0.1548,
    azimuth_rad: float = 1.5707963267948966,
) -> ThrustDirection:
    """Programa de guiado de dos tramos: giro por gravedad atmosférico + ley de tangente lineal.

    - t < t_guidance: idéntico a `pitch_kick_direction` (ascenso vertical, pitch kick y giro
      por gravedad con ángulo de ataque nulo, que minimiza las cargas aerodinámicas).
    - t >= t_guidance (fuera de la atmósfera densa, tras separar los SRB): el ángulo de
      cabeceo theta respecto al horizonte local sigue la ley de tangente lineal
          tan(theta(t)) = tan(theta_0) + (tan(theta_f) - tan(theta_0)) * tau,
          tau = (t - t_guidance) / (t_final - t_guidance) in [0, 1],
      que es la solución óptima (máximo de velocidad final) para empuje en vacío y gravedad
      uniforme (problema de Lawden / guiado PEG del Space Shuttle).
      El plano de vuelo se define con la dirección horizontal de la velocidad relativa.

    Los valores por defecto de theta_0 y theta_f se obtuvieron resolviendo (fsolve) las
    condiciones de MECO h = 160 km y ángulo de trayectoria gamma = 0 con la configuración
    nominal (ver scripts/generate_figures.py).
    """
    atmospheric = pitch_kick_direction(t_kick, pitch_angle_rad, azimuth_rad)
    tan_0 = float(np.tan(theta_start_rad))
    tan_f = float(np.tan(theta_end_rad))

    def _direction_func(
        t: float,
        position: npt.NDArray[np.float64],
        v_rel: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        if t < t_guidance:
            return atmospheric(t, position, v_rel)
        r_unit = position / float(np.linalg.norm(position))
        v_horiz = v_rel - float(np.dot(v_rel, r_unit)) * r_unit
        h_norm = float(np.linalg.norm(v_horiz))
        if h_norm == 0.0:
            return r_unit
        h_unit = v_horiz / h_norm
        tau = min(1.0, max(0.0, (t - t_guidance) / (t_final - t_guidance)))
        theta = float(np.arctan(tan_0 + (tan_f - tan_0) * tau))
        return np.cos(theta) * h_unit + np.sin(theta) * r_unit

    return _direction_func


class AscentPhase(Enum):
    """Fases operativas de la propulsión durante el ascenso atmosférico."""

    BOOSTERS_AND_CORE = "BOOSTERS_AND_CORE"  # Core Stage + 2x SRB
    CORE_ONLY = "CORE_ONLY"  # Solo Core Stage (post-separación de SRB)


@dataclass(frozen=True, slots=True)
class AscentConfig:
    """Configuración física y operacional para la simulación de ascenso atmosférico.

    Parámetros
    ----------
    srb_spec : StageSpec
        Especificación del conjunto propulsor de boosters sólidos (típicamente el par 2x SRB).
    core_spec : StageSpec
        Especificación del Core Stage de SLS.
    upper_mass_kg : float
        Masa inerte superior en kg (EUS en seco + propelente de EUS + Orion + Gateway cargo).
    t_burn_srb_s : float
        Tiempo nominal de agotamiento / separación de los SRB en segundos (~126 s).
    drag_coeff : float
        Coeficiente de arrastre constante; solo se usa si `use_mach_cd` es False.
    use_mach_cd : bool
        Si es True, Cd se interpola de la tabla Cd(Mach) (pico transónico incluido).
    reference_area_m2 : float
        Área de referencia aerodinámica de la sección transversal del SLS (m^2).
        Diámetro Core Stage ~8.4 m -> A ≈ pi * (4.2)^2 ≈ 55.4 m^2.
    core_exit_area_m2 : float
        Área total de salida de toberas de 4 motores RS-25 (~4 x 4.0 m^2 = 16.0 m^2).
    srb_exit_area_m2 : float
        Área total de salida de toberas de los 2 SRB (~2 x 10.5 m^2 = 21.0 m^2).
    thrust_direction_fn : ThrustDirection
        Función que determina el vector unitario de empuje.
    phase : AscentPhase
        Fase actual del ascenso ('BOOSTERS_AND_CORE' o 'CORE_ONLY').
    """

    srb_spec: StageSpec = SLS_B1B_SRB_PAIR
    core_spec: StageSpec = SLS_B1B_CORE_STAGE
    upper_mass_kg: float = 180000.0  # EUS cargado (~142.6 t) + Orion (~26 t) + cofa/Gateway payload
    t_burn_srb_s: float = 126.0  # Duración nominal de combustión de los boosters de 5 segmentos
    drag_coeff: float = 0.35  # Valor constante de respaldo (use_mach_cd=False)
    use_mach_cd: bool = True
    reference_area_m2: float = 55.4  # Sección transversal nominal de 8.4 m de diámetro
    core_exit_area_m2: float = 16.0  # TODO: verificar área de salida acumulada de 4x RS-25
    srb_exit_area_m2: float = 21.0  # TODO: verificar área de salida acumulada de 2x 5-segment SRB
    thrust_direction_fn: ThrustDirection = radial_direction
    phase: AscentPhase = AscentPhase.BOOSTERS_AND_CORE

    @property
    def cutoff_mass_kg(self) -> float:
        """Masa mínima por debajo de la cual no puede descender el vehículo en esta fase."""
        if self.phase == AscentPhase.BOOSTERS_AND_CORE:
            return (
                self.core_spec.dry_mass_kg
                + self.srb_spec.dry_mass_kg
                + self.upper_mass_kg
            )
        return self.core_spec.dry_mass_kg + self.upper_mass_kg


def make_ascent_derivatives(
    config: AscentConfig,
) -> Callable[[float, npt.NDArray[np.float64]], npt.NDArray[np.float64]]:
    """Construye y retorna la función de derivadas temporales para `scipy.integrate.solve_ivp`.

    Firma de retorno: (t: float, state_vec: NDArray[float64]) -> deriv: NDArray[float64] (7,)
    Estado: [x, y, z, vx, vy, vz, m]
    Derivada: [vx, vy, vz, ax, ay, az, dm_dt]

    Detalles de física:
    - Altitud: h = ||r|| - R_E.
    - Presión y densidad: modelos exponenciales según la altitud h.
    - Velocidad relativa: v_rel = v - omega_E x r.
    - Empuje: se computa según los motores activos en la fase (SRB + Core o solo Core).
      Los SRB siguen el perfil regresivo `SRB_THRUST_PROFILE`, escalado para que la masa
      consumida en t_burn_srb_s sea exactamente su propelente (conservación de masa).
      Si la masa actual alcanza la masa de corte (sin propelente utilizable), los motores se apagan.
    - Cd: tabla Cd(Mach) con Mach = ||v_rel|| / a(h) (US Standard Atmosphere 1976).
    - Arrastre: F_drag = -0.5 * rho * Cd * A * ||v_rel|| * v_rel (nulo si h > 100 000 m).
    - Gravedad: masa puntual pura -mu * r / ||r||^3.
    - Aceleración: a = (T_total * u + F_drag) / m + g.
    """
    mu_earth = EARTH.mu_m3_s2
    r_earth = EARTH.equatorial_radius_m
    omega_e = EARTH_ROTATION.omega_rad_s

    cutoff_mass = config.cutoff_mass_kg
    core_mass_flow = compute_mass_flow(
        config.core_spec.thrust_vac_n,
        config.core_spec.isp_vac_s,
        G0_M_S2,
    )
    srb_active_phase = config.phase == AscentPhase.BOOSTERS_AND_CORE
    srb_scale = srb_thrust_scale(config.srb_spec, config.t_burn_srb_s)

    def _derivatives(
        t: float,
        state_vec: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        pos = state_vec[0:3]
        vel = state_vec[3:6]
        m = state_vec[6]

        # 1. Cinemática y magnitudes geodésicas / atmosféricas
        h = compute_altitude(pos, r_earth)
        p_a = compute_atmospheric_pressure(h)
        v_rel = compute_relative_velocity(pos, vel, omega_e)

        # 2. Empuje y gasto másico de etapas
        t_thrust_total = 0.0
        dm_dt = 0.0

        if m > cutoff_mass:
            # Core Stage activo
            t_core = compute_thrust(
                config.core_spec.thrust_vac_n,
                config.core_exit_area_m2,
                p_a,
            )
            t_thrust_total += t_core
            dm_dt += core_mass_flow

            # Boosters (SRB) activos solo si estamos en la fase respectiva y t < t_burn_srb
            if srb_active_phase:
                srb_vac = srb_scale * srb_thrust_fraction(t, config.t_burn_srb_s) * (
                    config.srb_spec.thrust_vac_n
                )
                if srb_vac > 0.0:
                    t_thrust_total += compute_thrust(srb_vac, config.srb_exit_area_m2, p_a)
                    dm_dt += compute_mass_flow(srb_vac, config.srb_spec.isp_vac_s, G0_M_S2)

        # 3. Dirección unitaria del empuje
        u_thrust = config.thrust_direction_fn(t, pos, v_rel)

        # 4. Arrastre aerodinámico
        if config.use_mach_cd:
            cd = compute_drag_coefficient(compute_mach_number(float(np.linalg.norm(v_rel)), h))
        else:
            cd = config.drag_coeff
        f_drag = compute_aerodynamic_drag(v_rel, h, cd, config.reference_area_m2)

        # 5. Gravedad central pura
        a_grav = compute_gravity(pos, mu_earth)

        # 6. Aceleración inercial en ECI
        a_total = (t_thrust_total * u_thrust + f_drag) / m + a_grav

        deriv = np.empty(7, dtype=np.float64)
        deriv[0:3] = vel
        deriv[3:6] = a_total
        deriv[6] = dm_dt
        return deriv

    return _derivatives


EventFn = Callable[[float, npt.NDArray[np.float64]], float]


def make_srb_burnout_event(config: AscentConfig) -> EventFn:
    """Evento terminal solve_ivp: fin de combustión de los SRB en t = config.t_burn_srb_s."""

    def _event(t: float, state_vec: npt.NDArray[np.float64]) -> float:
        return float(config.t_burn_srb_s - t)

    _event.terminal = True  # type: ignore[attr-defined]
    _event.direction = -1  # type: ignore[attr-defined]
    return _event


def make_core_burnout_event(config: AscentConfig) -> EventFn:
    """Evento terminal solve_ivp: agotamiento del propelente del Core (MECO).

    Usa la masa de corte de la configuración (Core seco + masa superior), no constantes fijas.
    """
    cutoff_mass = config.core_spec.dry_mass_kg + config.upper_mass_kg

    def _event(t: float, state_vec: npt.NDArray[np.float64]) -> float:
        return float(state_vec[6] - cutoff_mass)

    _event.terminal = True  # type: ignore[attr-defined]
    _event.direction = -1  # type: ignore[attr-defined]
    return _event


def event_karman_crossing(t: float, state_vec: npt.NDArray[np.float64]) -> float:
    """Evento solve_ivp: cruce de la altitud de 100 km (línea de Kármán)."""
    pos = state_vec[0:3]
    h = compute_altitude(pos, EARTH.equatorial_radius_m)
    return h - 100_000.0


event_karman_crossing.terminal = False  # type: ignore[attr-defined]
event_karman_crossing.direction = 1  # type: ignore[attr-defined]


def event_ground_impact(t: float, state_vec: npt.NDArray[np.float64]) -> float:
    """Evento terminal solve_ivp: el vehículo vuelve a la superficie (h = 0) tras despegar."""
    if t < 1.0:
        return 1.0
    return compute_altitude(state_vec[0:3], EARTH.equatorial_radius_m)


event_ground_impact.terminal = True  # type: ignore[attr-defined]
event_ground_impact.direction = -1  # type: ignore[attr-defined]

# Eventos por defecto (configuración nominal), conservados por compatibilidad.
event_srb_burnout = make_srb_burnout_event(AscentConfig())
event_core_burnout = make_core_burnout_event(AscentConfig(phase=AscentPhase.CORE_ONLY))


def jettison_boosters(
    state: ArtemisState,
    config: AscentConfig,
) -> ArtemisState:
    """Descarta la masa seca de los cohetes propulsores sólidos (SRB).

    Aplica una discontinuidad o salto de masa físico instantáneo (m_nueva = m_actual - m_seca_srb)
    preservando exactamente la posición, velocidad y tiempo cinemático del vehículo.
    Permite reiniciar la integración continua en la fase `CORE_ONLY`.

    Parámetros
    ----------
    state : ArtemisState
        Estado orbital en el momento de la separación de los boosters.
    config : AscentConfig
        Configuración del vehículo que contiene la especificación de los SRB.

    Retorna
    -------
    ArtemisState
        Nuevo estado con la masa reducida en la masa inerte/seca de los SRB.
    """
    srb_dry_mass = config.srb_spec.dry_mass_kg
    new_mass = state.mass - srb_dry_mass
    if new_mass <= 0.0:
        raise ValueError(
            f"Masa resultante inválida tras separación de SRB: {new_mass} kg."
        )
    return ArtemisState(
        position=state.position,
        velocity=state.velocity,
        mass=new_mass,
        t=state.t,
    )


def initial_state_on_pad(
    latitude_deg: float,
    longitude_deg: float,
    config: AscentConfig,
) -> ArtemisState:
    """Genera el estado inercial ECI inicial de reposo sobre la plataforma.

    Geometría esférica:
    - latitud phi, longitud lambda.
    - r = R_E * [cos(phi)*cos(lambda), cos(phi)*sin(lambda), sin(phi)].
    - v = omega_E x r = [-omega_E * y, omega_E * x, 0].
    En reposo sobre la plataforma terrestre, la velocidad relativa al aire v_rel es idénticamente 0.

    Ejemplo de coordenadas:
    Plataforma LC-39B en Kennedy Space Center (KSC):
    - Latitud: ~28.627° N
    - Longitud: ~-80.621° O (-80.621 grados)

    Parámetros
    ----------
    latitude_deg : float
        Latitud geocéntrica en grados decimales (-90 a 90).
    longitude_deg : float
        Longitud geocéntrica en grados decimales (-180 a 180).
    config : AscentConfig
        Configuración del vehículo que determina la masa total cargada al despegue.

    Retorna
    -------
    ArtemisState
        Estado inicial exacto en coordenadas ECI J2000 en t = 0 s.
    """
    lat_rad = np.radians(latitude_deg)
    lon_rad = np.radians(longitude_deg)

    r_e = EARTH.equatorial_radius_m
    omega_e = EARTH_ROTATION.omega_rad_s

    # Posición cartesiana geocéntrica
    x = r_e * np.cos(lat_rad) * np.cos(lon_rad)
    y = r_e * np.cos(lat_rad) * np.sin(lon_rad)
    z = r_e * np.sin(lat_rad)
    pos = np.array([x, y, z], dtype=np.float64)

    # Velocidad inercial debida a la rotación de la Tierra (omega x r)
    vx = -omega_e * y
    vy = omega_e * x
    vz = 0.0
    vel = np.array([vx, vy, vz], dtype=np.float64)

    # Masa total al despegue
    total_mass = (
        config.core_spec.total_mass_kg
        + config.srb_spec.total_mass_kg
        + config.upper_mass_kg
    )

    return ArtemisState(
        position=pos,
        velocity=vel,
        mass=total_mass,
        t=0.0,
    )


@dataclass(frozen=True, slots=True)
class AscentResult:
    """Trayectoria completa del ascenso (SRB + Core) concatenada en ambos tramos.

    Parámetros
    ----------
    t : NDArray (N,)
        Instantes de muestreo en segundos desde el despegue (s).
    y : NDArray (7, N)
        Estados [x, y, z, vx, vy, vz, m] en ECI (SI). Incluye el salto de masa por
        separación de los SRB entre los dos tramos.
    t_srb_separation_s : float
        Instante de separación de los SRB (s).
    t_meco_s : float
        Instante de apagado del Core Stage (MECO) o de fin de integración (s).
    meco_reached : bool
        True si el Core agotó su propelente (evento de MECO detectado).
    """

    t: npt.NDArray[np.float64]
    y: npt.NDArray[np.float64]
    t_srb_separation_s: float
    t_meco_s: float
    meco_reached: bool


def simulate_full_ascent(
    latitude_deg: float = 28.627,
    longitude_deg: float = -80.621,
    thrust_direction_fn: ThrustDirection | None = None,
    base_config: AscentConfig | None = None,
    t_max_s: float = 900.0,
    rtol: float = 1e-9,
    atol: float = 1e-6,
    max_step_s: float = 1.0,
) -> AscentResult:
    """Integra el ascenso completo: SRB + Core -> separación de SRB -> solo Core -> MECO.

    Tramo 1 (BOOSTERS_AND_CORE): RK45 en [0, t_burn_srb] con evento de fin de combustión.
    Discontinuidad: `jettison_boosters` descarta la masa seca de los SRB (posición y velocidad
    continuas, salto de masa).
    Tramo 2 (CORE_ONLY): RK45 hasta el evento de MECO (masa de corte del Core).
    En ambos tramos se vigila el impacto contra el suelo.
    """
    from scipy.integrate import solve_ivp

    cfg_base = base_config if base_config is not None else AscentConfig()
    # Por defecto: guiado nominal (giro por gravedad + tangente lineal hasta MECO a 160 km)
    direction = (
        thrust_direction_fn if thrust_direction_fn is not None else linear_tangent_direction()
    )
    cfg_1 = AscentConfig(
        srb_spec=cfg_base.srb_spec,
        core_spec=cfg_base.core_spec,
        upper_mass_kg=cfg_base.upper_mass_kg,
        t_burn_srb_s=cfg_base.t_burn_srb_s,
        drag_coeff=cfg_base.drag_coeff,
        use_mach_cd=cfg_base.use_mach_cd,
        reference_area_m2=cfg_base.reference_area_m2,
        core_exit_area_m2=cfg_base.core_exit_area_m2,
        srb_exit_area_m2=cfg_base.srb_exit_area_m2,
        thrust_direction_fn=direction,
        phase=AscentPhase.BOOSTERS_AND_CORE,
    )
    cfg_2 = AscentConfig(
        srb_spec=cfg_1.srb_spec,
        core_spec=cfg_1.core_spec,
        upper_mass_kg=cfg_1.upper_mass_kg,
        t_burn_srb_s=cfg_1.t_burn_srb_s,
        drag_coeff=cfg_1.drag_coeff,
        use_mach_cd=cfg_1.use_mach_cd,
        reference_area_m2=cfg_1.reference_area_m2,
        core_exit_area_m2=cfg_1.core_exit_area_m2,
        srb_exit_area_m2=cfg_1.srb_exit_area_m2,
        thrust_direction_fn=direction,
        phase=AscentPhase.CORE_ONLY,
    )

    state_0 = initial_state_on_pad(latitude_deg, longitude_deg, cfg_1)
    sol_1 = solve_ivp(
        make_ascent_derivatives(cfg_1),
        (0.0, cfg_1.t_burn_srb_s),
        state_0.to_array(),
        method="RK45",
        rtol=rtol,
        atol=atol,
        max_step=max_step_s,
        events=[event_ground_impact],
    )
    if not sol_1.success or sol_1.t[-1] < cfg_1.t_burn_srb_s - 1e-9:
        raise RuntimeError("El tramo SRB + Core no alcanzó la separación de los boosters.")

    state_sep = ArtemisState.from_array(sol_1.y[:, -1], t=float(sol_1.t[-1]))
    state_post = jettison_boosters(state_sep, cfg_1)

    sol_2 = solve_ivp(
        make_ascent_derivatives(cfg_2),
        (state_post.t, t_max_s),
        state_post.to_array(),
        method="RK45",
        rtol=rtol,
        atol=atol,
        max_step=max_step_s,
        events=[make_core_burnout_event(cfg_2), event_ground_impact],
    )
    meco_reached = bool(sol_2.t_events[0].size > 0)

    t_all = np.concatenate([sol_1.t, sol_2.t])
    y_all = np.concatenate([sol_1.y, sol_2.y], axis=1)
    return AscentResult(
        t=t_all,
        y=y_all,
        t_srb_separation_s=float(sol_1.t[-1]),
        t_meco_s=float(sol_2.t[-1]),
        meco_reached=meco_reached,
    )
