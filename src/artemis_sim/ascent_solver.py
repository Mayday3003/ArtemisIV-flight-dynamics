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
    compute_gravity,
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
        Coeficiente de arrastre aerodinámico medio.
        # TODO: verificar, placeholder (en vuelo real Cd varía fuertemente con el número de Mach).
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
    drag_coeff: float = 0.35  # TODO: verificar, placeholder (depende de Mach y ángulo de ataque)
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
      Si la masa actual alcanza la masa de corte (sin propelente utilizable), los motores se apagan.
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
    srb_mass_flow = (
        compute_mass_flow(
            config.srb_spec.thrust_vac_n,
            config.srb_spec.isp_vac_s,
            G0_M_S2,
        )
        if config.phase == AscentPhase.BOOSTERS_AND_CORE
        else 0.0
    )

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
            if config.phase == AscentPhase.BOOSTERS_AND_CORE and t < config.t_burn_srb_s:
                t_srb = compute_thrust(
                    config.srb_spec.thrust_vac_n,
                    config.srb_exit_area_m2,
                    p_a,
                )
                t_thrust_total += t_srb
                dm_dt += srb_mass_flow

        # 3. Dirección unitaria del empuje
        u_thrust = config.thrust_direction_fn(t, pos, v_rel)

        # 4. Arrastre aerodinámico
        f_drag = compute_aerodynamic_drag(
            v_rel,
            h,
            config.drag_coeff,
            config.reference_area_m2,
        )

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


def event_srb_burnout(t: float, state_vec: npt.NDArray[np.float64]) -> float:
    """Evento solve_ivp: apagado por tiempo nominal de los boosters SRB (126 s)."""
    return float(126.0 - t)


event_srb_burnout.terminal = True  # type: ignore[attr-defined]
event_srb_burnout.direction = -1  # type: ignore[attr-defined]


def event_karman_crossing(t: float, state_vec: npt.NDArray[np.float64]) -> float:
    """Evento solve_ivp: cruce de la altitud de 100 km (línea de Kármán)."""
    pos = state_vec[0:3]
    h = compute_altitude(pos, EARTH.equatorial_radius_m)
    return h - 100_000.0


event_karman_crossing.terminal = False  # type: ignore[attr-defined]
event_karman_crossing.direction = 1  # type: ignore[attr-defined]


def event_core_burnout(t: float, state_vec: npt.NDArray[np.float64]) -> float:
    """Evento solve_ivp: agotamiento completo del propelente del Core Stage."""
    m = state_vec[6]
    # Masa seca del Core + masa inerte superior
    cutoff_mass = SLS_B1B_CORE_STAGE.dry_mass_kg + 180000.0
    return float(m - cutoff_mass)


event_core_burnout.terminal = True  # type: ignore[attr-defined]
event_core_burnout.direction = -1  # type: ignore[attr-defined]


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
