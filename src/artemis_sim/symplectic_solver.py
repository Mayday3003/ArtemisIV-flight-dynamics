"""Integrador simpléctico y dinámica n-cuerpos en el vacío para Artemis IV.

Alcance y suposiciones físicas (Fase 3):
- Propagación balística en el vacío (sin empuje, sin arrastre atmosférico, masa constante).
- Sistema gravitacional de 2 o 3 cuerpos: Tierra y Luna como masas puntuales.
- Marco de referencia: ECI (geocéntrico inercial J2000). Al utilizar coordenadas
  centradas en la Tierra en presencia de la atracción gravitacional de la Luna,
  la Tierra sufre una aceleración de caída libre debida a la Luna. Por tanto, para
  describir el movimiento relativo respecto al centro de la Tierra es OBLIGATORIO
  incluir el "término indirecto":
      a_indirecto = - a_grav(Tierra debido a Luna) = - mu_M * r_M / |r_M|^3
  Así, la aceleración total geocéntrica de la nave es:
      a = -mu_E * r / |r|^3 + mu_M * [ (r_M - r) / |r_M - r|^3 - r_M / |r_M|^3 ]

AVISO FÍSICO FUNDAMENTAL:
Cuando la Luna está activa (`include_moon=True`), el potencial gravitacional lunar depende
explícitamente del tiempo r_M(t). En consecuencia, el hamiltoniano dependiente del tiempo
hace que la energía mecánica específica del vehículo respecto a la Tierra NO sea constante.
La conservación estricta de la energía mecánica se aplica única y exclusivamente al problema
de dos cuerpos puro (`include_moon=False`).

TODO: Futuras fases considerarán perturbación por la gravedad solar (4 cuerpos), oblatitud
terrestre J2, presión de radiación solar (SRP) y cambio a marco selenocéntrico dentro
de la esfera de influencia de la Luna (SOI).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

from artemis_sim.constants import EARTH, MOON
from artemis_sim.ephemeris import (
    DEFAULT_LUNAR_CONFIG,
    LunarOrbitConfig,
    get_body_position,
    get_body_velocity,
)
from artemis_sim.physics_engine import compute_gravity
from artemis_sim.state import ArtemisState


def compute_n_body_acceleration(
    position: npt.ArrayLike,
    t: float,
    include_moon: bool = True,
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> npt.NDArray[np.float64]:
    """Calcula la aceleración inercial geocéntrica del vehículo en el vacío.

    a = a_directo_Tierra + [a_directo_Luna + a_indirecto_Luna]

    Signos y términos:
    - a_Tierra = -mu_E * r / |r|^3 = compute_gravity(r, mu_E)
    - Vector hacia la nave desde la Luna: (r - r_M).
      Fuerza directa de la Luna sobre la nave atrae hacia la Luna:
      a_directo_Luna = compute_gravity(r - r_M, mu_M) = -mu_M * (r - r_M)/|r - r_M|^3
                     = mu_M * (r_M - r) / |r_M - r|^3
    - Aceleración de la Tierra debida a la Luna:
      a_Tierra_por_Luna = compute_gravity(-r_M, mu_M) = mu_M * r_M / |r_M|^3
    - Término indirecto (restar aceleración del origen de coordenadas):
      a_indirecto = - a_Tierra_por_Luna = - compute_gravity(-r_M, mu_M) = - mu_M * r_M / |r_M|^3

    Parámetros
    ----------
    position : ArrayLike (3,)
        Vector de posición geocéntrica [x, y, z] en metros (m).
    t : float
        Tiempo de simulación en segundos (s).
    include_moon : bool, opcional
        Indica si se incluye la perturbación gravitacional de la Luna (por defecto True).
    lunar_config : LunarOrbitConfig, opcional
        Configuración de las efemérides lunares.

    Retorna
    -------
    NDArray[np.float64] (3,)
        Aceleración neta geocéntrica [ax, ay, az] en m/s^2.
    """
    pos = np.asarray(position, dtype=np.float64)

    # 1. Aceleración geocéntrica central de la Tierra
    # Si pos == 0, compute_gravity lanzará ValueError
    a_earth = compute_gravity(pos, EARTH.mu_m3_s2)

    if not include_moon:
        return a_earth

    # 2. Posición de la Luna respecto a la Tierra
    r_moon = get_body_position(MOON, t, config=lunar_config)

    # 3. Término directo de la Luna sobre el vehículo:
    # Vector relativo desde la Luna hacia la nave: r_rel = pos - r_moon
    # La atracción apunta hacia la Luna: compute_gravity(pos - r_moon, MOON.mu_m3_s2)
    a_moon_direct = compute_gravity(pos - r_moon, MOON.mu_m3_s2)

    # 4. Término indirecto debido a la aceleración del marco geocéntrico provocada por la Luna:
    # Aceleración de la Tierra provocada por la Luna = compute_gravity(-r_moon, MOON.mu_m3_s2)
    # Por tanto, la aceleración indirecta restada al marco es - a_Tierra_por_Luna:
    a_indirect = -compute_gravity(-r_moon, MOON.mu_m3_s2)

    return a_earth + a_moon_direct + a_indirect


def verlet_step(
    state: ArtemisState,
    dt: float,
    include_moon: bool = True,
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> ArtemisState:
    """Ejecuta un único paso de integración simpléctica Velocity Verlet (orden 2).

    Esquema kick-drift-kick:
        v_half = v0 + 0.5 * a(r0, t0) * dt
        r1     = r0 + v_half * dt
        v1     = v_half + 0.5 * a(r1, t0 + dt) * dt

    Garantiza:
    - Retorna una nueva instancia `ArtemisState` con t = t0 + dt.
    - La masa se mantiene exactamente inalterada.
    - El estado de entrada original es inmutable y no se modifica.

    Parámetros
    ----------
    state : ArtemisState
        Estado inicial en el instante t0.
    dt : float
        Paso temporal en segundos (s).
    include_moon : bool, opcional
        Indica si se incluye la perturbación gravitacional de la Luna.
    lunar_config : LunarOrbitConfig, opcional
        Configuración de las efemérides lunares.

    Retorna
    -------
    ArtemisState
        Nuevo estado integrado en t0 + dt.
    """
    if dt <= 0.0:
        raise ValueError(f"El paso temporal dt debe ser estrictamente positivo (> 0). Valor: {dt}")

    r0 = state.position
    v0 = state.velocity
    t0 = state.t

    a0 = compute_n_body_acceleration(r0, t0, include_moon=include_moon, lunar_config=lunar_config)

    v_half = v0 + 0.5 * a0 * dt
    r1 = r0 + v_half * dt
    t1 = t0 + dt

    a1 = compute_n_body_acceleration(r1, t1, include_moon=include_moon, lunar_config=lunar_config)
    v1 = v_half + 0.5 * a1 * dt

    return ArtemisState(position=r1, velocity=v1, mass=state.mass, t=t1)


def propagate_verlet(
    state: ArtemisState,
    t_final: float,
    dt: float,
    sample_every: int = 1,
    include_moon: bool = True,
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> list[ArtemisState]:
    """Propaga el estado del vehículo usando Velocity Verlet con reutilización de aceleraciones.

    Optimización de rendimiento:
    El bucle interno opera directamente sobre arreglos NumPy y números float64 nativos.
    La aceleración final del paso k (`a1`) es la aceleración inicial del paso k+1 (`a0`),
    reduciendo el coste de cómputo a una sola evaluación de aceleración por paso.
    Las instancias de `ArtemisState` se generan únicamente en los pasos seleccionados
    por `sample_every`.

    Parámetros
    ----------
    state : ArtemisState
        Estado inicial de la propagación.
    t_final : float
        Tiempo final de integración en segundos (s). Debe ser mayor que state.t.
    dt : float
        Paso de integración fijo en segundos (s, estrictamente > 0).
    sample_every : int, opcional
        Frecuencia de muestreo (guardar 1 de cada N pasos, por defecto 1).
    include_moon : bool, opcional
        Indica si se incluye la atracción lunar.
    lunar_config : LunarOrbitConfig, opcional
        Configuración de las efemérides lunares.

    Retorna
    -------
    list[ArtemisState]
        Lista de estados muestreados a lo largo de la trayectoria.
    """
    if dt <= 0.0:
        raise ValueError(f"El paso temporal dt debe ser estrictamente positivo (> 0). Valor: {dt}")
    if sample_every < 1:
        raise ValueError(
            f"sample_every debe ser un entero positivo (>= 1). Valor: {sample_every}"
        )
    if t_final <= state.t:
        raise ValueError(
            f"t_final ({t_final} s) debe ser estrictamente mayor que t_inicial ({state.t} s)."
        )

    # Estado de arrays crudos
    r = state.position.copy()
    v = state.velocity.copy()
    t = state.t
    mass = state.mass

    # Calcular aceleración inicial una única vez
    a = compute_n_body_acceleration(r, t, include_moon=include_moon, lunar_config=lunar_config)

    trajectory: list[ArtemisState] = [state.copy()]
    step_count = 0

    # Bucle rápido con control de tiempo restante
    while t < t_final - 1e-12:
        current_dt = min(dt, t_final - t)

        # Kick-drift-kick
        v_half = v + 0.5 * a * current_dt
        r = r + v_half * current_dt
        t_next = t + current_dt

        # Nueva aceleración
        a_next = compute_n_body_acceleration(
            r,
            t_next,
            include_moon=include_moon,
            lunar_config=lunar_config,
        )
        v = v_half + 0.5 * a_next * current_dt

        # Avanzar punteros
        t = t_next
        a = a_next
        step_count += 1

        if step_count % sample_every == 0 or t >= t_final - 1e-12:
            trajectory.append(ArtemisState(position=r.copy(), velocity=v.copy(), mass=mass, t=t))

    return trajectory


def compute_system_energy(
    state: ArtemisState,
    t: float,
    include_moon: bool = True,
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> float:
    """Calcula la energía mecánica específica en marco geocéntrico (J/kg o m^2/s^2).

    epsilon = 0.5 * |v|^2 - mu_E / |r|  - [ mu_M / |r - r_M(t)| ]

    Documentación de conservación:
    - En el problema de dos cuerpos puro (`include_moon=False`), la energía mecánica específica
      es una constante exacta del movimiento hamiltoniano autónomo.
    - Cuando la Luna está presente (`include_moon=True`), el potencial gravitacional depende
      explícitamente del tiempo r_M(t). Por tanto, la energía mecánica instantánea respecto
      a la Tierra NO se conserva (el vehículo experimenta intercambio de momento y energía
      con el sistema Tierra-Luna, análogo a una asistencia gravitatoria o perturbación marea).

    Parámetros
    ----------
    state : ArtemisState
        Estado orbital del vehículo.
    t : float
        Instante de tiempo correspondiente en segundos (s).
    include_moon : bool, opcional
        Indica si se incluye la energía potencial gravitatoria lunar.
    lunar_config : LunarOrbitConfig, opcional
        Configuración orbital de la Luna.

    Retorna
    -------
    float
        Energía mecánica específica instantánea en m^2/s^2.
    """
    v_norm = state.speed
    r_norm = state.radius
    kinetic_energy = 0.5 * (v_norm**2)
    potential_earth = -EARTH.mu_m3_s2 / r_norm

    if not include_moon:
        return kinetic_energy + potential_earth

    r_moon = get_body_position(MOON, t, config=lunar_config)
    dist_moon = float(np.linalg.norm(state.position - r_moon))
    potential_moon = -MOON.mu_m3_s2 / dist_moon

    return kinetic_energy + potential_earth + potential_moon


def propagate_reference_dop853(
    state: ArtemisState,
    t_final: float,
    include_moon: bool = True,
    rtol: float = 1e-12,
    atol: float = 1e-6,
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> ArtemisState:
    """Propaga el estado del vehículo con el integrador adaptativo DOP853 (Runge-Kutta orden 8).

    Sirve como estándar de referencia de máxima precisión numérica para contrastar
    la fidelidad de integradores simplécticos y evaluar errores de discretización.

    Parámetros
    ----------
    state : ArtemisState
        Estado inicial en t0.
    t_final : float
        Tiempo final en segundos (s).
    include_moon : bool, opcional
        Indica si se incluye la perturbación gravitacional de la Luna.
    rtol : float, opcional
        Tolerancia relativa para solve_ivp (por defecto 1e-12).
    atol : float, opcional
        Tolerancia absoluta para solve_ivp (por defecto 1e-6).
    lunar_config : LunarOrbitConfig, opcional
        Configuración de las efemérides lunares.

    Retorna
    -------
    ArtemisState
        Estado final del vehículo en t_final.
    """
    if t_final <= state.t:
        raise ValueError(f"t_final ({t_final} s) debe ser mayor que state.t ({state.t} s).")

    # Vector 6D [x, y, z, vx, vy, vz]
    y0 = np.concatenate([state.position, state.velocity])

    def _ode_func(t: float, y_vec: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        pos = y_vec[0:3]
        vel = y_vec[3:6]
        accel = compute_n_body_acceleration(
            pos,
            t,
            include_moon=include_moon,
            lunar_config=lunar_config,
        )
        return np.concatenate([vel, accel])

    sol = solve_ivp(
        _ode_func,
        (state.t, t_final),
        y0,
        method="DOP853",
        rtol=rtol,
        atol=atol,
    )

    if not sol.success:
        raise RuntimeError(f"Fallo en la integración DOP853: {sol.message}")

    final_pos = sol.y[0:3, -1]
    final_vel = sol.y[3:6, -1]
    return ArtemisState(position=final_pos, velocity=final_vel, mass=state.mass, t=t_final)


def circular_orbit_state(
    radius_m: float,
    phase_rad: float = 0.0,
    mass_kg: float = 135_000.0,
) -> ArtemisState:
    """Crea un estado orbital circular no perturbado en el plano ecuatorial inercial (XY).

    v = sqrt(mu_E / r), orientado tangencialmente en sentido antihorario.
    t = 0.0 s.

    Parámetros
    ----------
    radius_m : float
        Radio geocéntrico de la órbita circular en metros (m).
    phase_rad : float, opcional
        Ángulo o anomalía de posición inicial en el plano XY (por defecto 0.0 rad, eje +X).
    mass_kg : float, opcional
        Masa total del vehículo en kg (por defecto 135,000.0 kg).

    Retorna
    -------
    ArtemisState
        Estado inicial circular perfectamente equilibrado.
    """
    if radius_m <= 0.0:
        raise ValueError(f"El radio orbital debe ser positivo (> 0). Valor recibido: {radius_m} m")

    v_circ = float(np.sqrt(EARTH.mu_m3_s2 / radius_m))

    pos = np.array([radius_m * np.cos(phase_rad), radius_m * np.sin(phase_rad), 0.0])
    vel = np.array([-v_circ * np.sin(phase_rad), v_circ * np.cos(phase_rad), 0.0])

    return ArtemisState(position=pos, velocity=vel, mass=mass_kg, t=0.0)


def impulsive_burn(
    state: ArtemisState,
    delta_v: npt.ArrayLike,
) -> ArtemisState:
    """Aplica una variación instantánea e impulsiva de velocidad (delta-v) al vehículo.

    Idealización física:
    Se modela como un encendido de empuje infinito en un lapso de tiempo nulo (dt -> 0).
    La posición cartesiana, el tiempo y la masa permanecen estrictamente inalterados.
    Útil para configurar órbitas de transferencia translunar (TLI) o maniobras impulsivas.

    Parámetros
    ----------
    state : ArtemisState
        Estado previo a la maniobra.
    delta_v : ArrayLike (3,)
        Incremento vectorial de velocidad [dv_x, dv_y, dv_z] en m/s.

    Retorna
    -------
    ArtemisState
        Nuevo estado con la velocidad actualizada: v_nueva = v_actual + delta_v.
    """
    dv_arr = np.asarray(delta_v, dtype=np.float64)
    if dv_arr.shape != (3,):
        raise ValueError(f"delta_v debe ser un vector 3D (3,), forma recibida: {dv_arr.shape}")

    new_vel = state.velocity + dv_arr
    return ArtemisState(
        position=state.position,
        velocity=new_vel,
        mass=state.mass,
        t=state.t,
    )


def compute_jacobi_constant(
    state: ArtemisState,
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> float:
    """Calcula la integral de Jacobi del CR3BP Tierra-Luna (energía en el marco rotante).

    Con la Luna en órbita circular de movimiento medio n, el sistema geocéntrico con término
    indirecto es equivalente al Problema Restringido Circular de Tres Cuerpos. En el marco
    baricéntrico que rota con velocidad angular omega = n z, el hamiltoniano es autónomo y
        E_J = 0.5 |v_rot|^2 - 0.5 n^2 (x_b^2 + y_b^2) - mu_E / r_1 - mu_M / r_2
    es una constante exacta del movimiento (C_J = -2 E_J es la constante de Jacobi clásica).

    Transformación desde el estado geocéntrico inercial (r, v):
    - Baricentro: R_b = mu_M / (mu_E + mu_M) * r_M(t),  V_b = mu_M / (mu_E + mu_M) * v_M(t).
    - rho = r - R_b,  rho_dot = v - V_b  (inercial baricéntrico).
    - v_rot = rho_dot - omega x rho;  |omega x rho|^2 = n^2 (x_b^2 + y_b^2).

    La conservación es exacta solo si n = sqrt((mu_E + mu_M) / d^3), que es el valor por
    defecto de `LunarOrbitConfig`.

    Retorna
    -------
    float
        Energía de Jacobi específica E_J en m^2/s^2.
    """
    mu_e = EARTH.mu_m3_s2
    mu_m = MOON.mu_m3_s2
    n = lunar_config.mean_motion_rad_s
    r_moon = get_body_position(MOON, state.t, config=lunar_config)
    v_moon = get_body_velocity(MOON, state.t, config=lunar_config)
    frac = mu_m / (mu_e + mu_m)

    rho = state.position - frac * r_moon
    rho_dot = state.velocity - frac * v_moon
    omega = np.array([0.0, 0.0, n], dtype=np.float64)
    v_rot = rho_dot - np.cross(omega, rho)

    r1 = float(np.linalg.norm(state.position))
    r2 = float(np.linalg.norm(state.position - r_moon))
    return float(
        0.5 * np.dot(v_rot, v_rot)
        - 0.5 * n**2 * (rho[0] ** 2 + rho[1] ** 2)
        - mu_e / r1
        - mu_m / r2
    )


def propagate_rk4(
    state: ArtemisState,
    t_final: float,
    dt: float,
    sample_every: int = 1,
    include_moon: bool = True,
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> list[ArtemisState]:
    """Propaga con Runge-Kutta clásico de orden 4 y paso fijo (método NO simpléctico).

    Se incluye como referencia comparativa: con el mismo paso dt, RK4 tiene menor error local
    que Verlet (O(dt^5) frente a O(dt^3)), pero su error de energía crece secularmente
    (deriva disipativa), mientras que el de Verlet permanece acotado (conserva un
    hamiltoniano modificado, Hairer-Lubich-Wanner 2006, cap. IX).
    """
    if dt <= 0.0:
        raise ValueError(f"El paso temporal dt debe ser estrictamente positivo (> 0). Valor: {dt}")
    if sample_every < 1:
        raise ValueError(
            f"sample_every debe ser un entero positivo (>= 1). Valor: {sample_every}"
        )
    if t_final <= state.t:
        raise ValueError(
            f"t_final ({t_final} s) debe ser estrictamente mayor que t_inicial ({state.t} s)."
        )

    def _f(t: float, y: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        acc = compute_n_body_acceleration(
            y[0:3], t, include_moon=include_moon, lunar_config=lunar_config
        )
        return np.concatenate([y[3:6], acc])

    y = np.concatenate([state.position, state.velocity])
    t = state.t
    trajectory: list[ArtemisState] = [state.copy()]
    step_count = 0
    while t < t_final - 1e-12:
        h = min(dt, t_final - t)
        k1 = _f(t, y)
        k2 = _f(t + 0.5 * h, y + 0.5 * h * k1)
        k3 = _f(t + 0.5 * h, y + 0.5 * h * k2)
        k4 = _f(t + h, y + h * k3)
        y = y + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        t += h
        step_count += 1
        if step_count % sample_every == 0 or t >= t_final - 1e-12:
            trajectory.append(
                ArtemisState(position=y[0:3].copy(), velocity=y[3:6].copy(), mass=state.mass, t=t)
            )
    return trajectory
