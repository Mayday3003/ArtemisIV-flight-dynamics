"""Motor de funciones físicas puras para el ascenso atmosférico de Artemis IV.

Todas las funciones de este módulo son puras (sin efectos secundarios ni estado global)
y operan sobre arreglos o escalares con precisión float64 en el Sistema Internacional (SI):
- Longitud / posición / altitud: metros (m)
- Tiempo: segundos (s)
- Velocidad: metros por segundo (m/s)
- Aceleración: metros por segundo al cuadrado (m/s^2)
- Masa: kilogramos (kg)
- Fuerza / empuje / arrastre: newtons (N)
- Presión: pascales (Pa)
- Densidad: kg/m^3
- Parámetro gravitacional: m^3/s^2
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from artemis_sim.constants import G0_M_S2

# Valores de la atmósfera al nivel del mar (US Standard Atmosphere 1976)
RHO0_KG_M3: float = 1.225  # Densidad a nivel del mar (US Standard Atmosphere 1976)

P0_PA: float = 101325.0  # Presión a nivel del mar estándar (Pa)


def compute_gravity(
    position: npt.ArrayLike,
    mu: float,
) -> npt.NDArray[np.float64]:
    """Calcula la aceleración gravitacional geocéntrica de masa puntual.

    Modelo newtoniano esférico: a_g = -mu * r / |r|^3.
    Apunta directamente hacia el centro de atracción gravitacional.
    TODO: Implementar armónicos zonales (J2, J3, J4) en fases posteriores
    para modelar la oblatitud terrestre.

    Parámetros
    ----------
    position : ArrayLike (3,)
        Vector de posición geocéntrica [x, y, z] en metros (m).
    mu : float
        Parámetro gravitacional estándar mu = G * M en m^3/s^2.

    Retorna
    -------
    NDArray[np.float64] (3,)
        Vector de aceleración gravitacional [ax, ay, az] en m/s^2.
    """
    pos = np.asarray(position, dtype=np.float64)
    r = float(np.linalg.norm(pos))
    if r == 0.0:
        raise ValueError("La posición no puede ser el origen r = 0 en el cálculo de gravedad.")
    return -mu * pos / (r**3)


def compute_altitude(
    position: npt.ArrayLike,
    radius_equatorial: float,
) -> float:
    """Calcula la altitud geocéntrica sobre una esfera de referencia de radio R_E.

    Documentación de modelo:
    h = ||r|| - R_E.
    Se asume una esfera perfecta de radio ecuatorial R_E.
    TODO: Considerar el elipsoide WGS84 para altitud geodésica estricta
    cuando se incorpore el modelo de gravedad perturbada.

    Parámetros
    ----------
    position : ArrayLike (3,)
        Vector de posición geocéntrica [x, y, z] en metros (m).
    radius_equatorial : float
        Radio ecuatorial de referencia del cuerpo central en metros (m).

    Retorna
    -------
    float
        Altitud sobre el radio ecuatorial en metros (m).
    """
    pos = np.asarray(position, dtype=np.float64)
    r = float(np.linalg.norm(pos))
    return r - radius_equatorial


def compute_atmospheric_density(
    altitude_m: float,
) -> float:
    """Densidad de la US Standard Atmosphere 1976 por capas: ρ = p / (R T).

    Usa la presión hidrostática de `compute_atmospheric_pressure` y la temperatura de
    `compute_atmospheric_temperature` (la misma tabla de capas). Antes era un modelo
    exponencial con H = 8,5 km, que se equivocaba ~20 % por encima de 30 km.
    Para h < 0 se satura en el valor del nivel del mar (1,225 kg/m³).

    Parámetros
    ----------
    altitude_m : float
        Altitud sobre la superficie esférica en metros (m).

    Retorna
    -------
    float
        Densidad atmosférica en kg/m^3.
    """
    return compute_atmospheric_pressure(altitude_m) / (
        R_AIR_J_KG_K * compute_atmospheric_temperature(altitude_m)
    )


def compute_atmospheric_pressure(
    altitude_m: float,
) -> float:
    """Presión estática de la US Standard Atmosphere 1976 por capas (equilibrio hidrostático).

    En cada capa b, con T = T_b + L_b (h − h_b):
        L_b ≠ 0:  p = p_b (T / T_b)^(−g0 / (R L_b))
        L_b = 0:  p = p_b exp(−g0 (h − h_b) / (R T_b))
    Por encima de la última capa (84,852 km) se sigue la isoterma de la mesopausa.
    Como `compute_atmospheric_temperature`, toma la altitud como geopotencial (error < 1,4 %
    en la altitud a 86 km). Para h < 0 se satura en p0 = 101 325 Pa.

    Parámetros
    ----------
    altitude_m : float
        Altitud sobre la superficie esférica en metros (m).

    Retorna
    -------
    float
        Presión atmosférica en pascales (Pa).
    """
    h = max(0.0, float(altitude_m))
    k = 0
    while k + 1 < len(_US76_LAYERS) and h >= _US76_LAYERS[k + 1][0]:
        k += 1
    base_h, base_t, lapse = _US76_LAYERS[k]
    return _US76_BASE_PRESSURE[k] * _layer_pressure_ratio(h - base_h, base_t, lapse)


def _layer_pressure_ratio(dh: float, base_t: float, lapse: float) -> float:
    """p/p_b dentro de una capa, a una distancia dh de su base."""
    if lapse == 0.0:
        return float(np.exp(-G0_M_S2 * dh / (R_AIR_J_KG_K * base_t)))
    return float(((base_t + lapse * dh) / base_t) ** (-G0_M_S2 / (R_AIR_J_KG_K * lapse)))


def compute_relative_velocity(
    position: npt.ArrayLike,
    velocity: npt.ArrayLike,
    omega_earth: float,
) -> npt.NDArray[np.float64]:
    """Calcula la velocidad relativa del vehículo respecto a la atmósfera en rotación.

    En marco inercial ECI (J2000), suponiendo que la atmósfera rota rígidamente con la Tierra:
    v_atm = omega_E x r
    v_rel = v - omega_E x r

    Donde el vector de velocidad angular terrestre es omega_vec = [0, 0, omega_earth].
    El producto vectorial resulta en:
    omega x r = [-omega_earth * y, omega_earth * x, 0].

    Parámetros
    ----------
    position : ArrayLike (3,)
        Posición [x, y, z] en ECI (m).
    velocity : ArrayLike (3,)
        Velocidad inercial [vx, vy, vz] en ECI (m/s).
    omega_earth : float
        Velocidad angular terrestre escalar en rad/s.

    Retorna
    -------
    NDArray[np.float64] (3,)
        Velocidad relativa al aire [vx_rel, vy_rel, vz_rel] en m/s.
    """
    pos = np.asarray(position, dtype=np.float64)
    vel = np.asarray(velocity, dtype=np.float64)

    v_wind = np.array(
        [-omega_earth * pos[1], omega_earth * pos[0], 0.0],
        dtype=np.float64,
    )
    return vel - v_wind


def compute_aerodynamic_drag(
    velocity_rel: npt.ArrayLike,
    altitude_m: float,
    drag_coeff: float,
    area_m2: float,
) -> npt.NDArray[np.float64]:
    """Calcula el vector de fuerza de arrastre aerodinámico en coordenadas ECI.

    F_drag = -0.5 * rho(h) * Cd * A * ||v_rel|| * v_rel

    Propiedades:
    - Actúa siempre en sentido colineal opuesto a la velocidad relativa v_rel.
    - Si ||v_rel|| == 0, devuelve exactamente el vector nulo [0, 0, 0] sin divisiones por cero.
    - Para h > 100 000 m (línea de Kármán / espacio), la fuerza es nula.

    Parámetros
    ----------
    velocity_rel : ArrayLike (3,)
        Vector de velocidad relativa [vx_rel, vy_rel, vz_rel] en m/s.
    altitude_m : float
        Altitud sobre el radio ecuatorial en metros (m).
    drag_coeff : float
        Coeficiente de arrastre aerodinámico adimensional (Cd).
    area_m2 : float
        Área aerodinámica de referencia en metros cuadrados (m^2).

    Retorna
    -------
    NDArray[np.float64] (3,)
        Vector de fuerza de arrastre [Fx, Fy, Fz] en Newtons (N).
    """
    if altitude_m > 100_000.0:
        return np.zeros(3, dtype=np.float64)

    v_rel = np.asarray(velocity_rel, dtype=np.float64)
    v_norm = float(np.linalg.norm(v_rel))
    if v_norm == 0.0:
        return np.zeros(3, dtype=np.float64)

    rho = compute_atmospheric_density(altitude_m)
    # Magnitud escalar = 0.5 * rho * Cd * A * v_norm^2
    # Vector: -0.5 * rho * Cd * A * v_norm * v_rel
    drag_factor = 0.5 * rho * drag_coeff * area_m2 * v_norm
    return -drag_factor * v_rel


def compute_thrust(
    thrust_vac_n: float,
    exit_area_m2: float,
    pressure_pa: float,
) -> float:
    """Calcula el empuje efectivo del motor adaptado a la presión ambiental.

    Ecuación de empuje de tobera:
    T = T_vac - p_a * A_e

    Propiedades:
    - A nivel del mar (p_a = 101325 Pa), el empuje es menor que en el vacío debido
      a la contrapresión ejercida por la atmósfera sobre el plano de salida de la tobera.
    - A gran altitud (p_a -> 0), el empuje converge asintóticamente a T_vac.
    - Se satura a T >= 0.0 para evitar empujes negativos no físicos.

    Parámetros
    ----------
    thrust_vac_n : float
        Empuje nominal en el vacío en Newtons (N).
    exit_area_m2 : float
        Área total de salida de las toberas en metros cuadrados (m^2).
    pressure_pa : float
        Presión ambiental estática en pascales (Pa).

    Retorna
    -------
    float
        Empuje efectivo resultante en Newtons (N).
    """
    thrust_eff = thrust_vac_n - pressure_pa * exit_area_m2
    return max(0.0, float(thrust_eff))


def compute_mass_flow(
    thrust_vac_n: float,
    isp_vac_s: float,
    g0: float,
) -> float:
    """Calcula la derivada temporal de masa (dm/dt) debida al consumo de propelente.

    dm/dt = -T_vac / (Isp_vac * g0)

    Documentación física:
    El gasto másico o flujo de propelente de un motor cohete de combustible líquido
    o sólido que opera a régimen nominal es fijado por las turbobombas / presión de cámara
    y garganta sónica. Por tanto, el flujo másico es CONSTANTE y NO depende de la altitud
    ni de la contrapresión atmosférica externa (lo que varía con la altitud es el empuje T,
    a través del término de presión en la tobera).
    Retorna un valor negativo correspondiente a la disminución de masa con el tiempo.

    Parámetros
    ----------
    thrust_vac_n : float
        Empuje en el vacío en Newtons (N).
    isp_vac_s : float
        Impulso específico en el vacío en segundos (s).
    g0 : float
        Aceleración gravitacional estándar en m/s^2 (9.80665).

    Retorna
    -------
    float
        Derivada de masa dm/dt en kg/s (valor estrictamente negativo <= 0).
    """
    if thrust_vac_n == 0.0:
        return 0.0
    return -thrust_vac_n / (isp_vac_s * g0)


def compute_coriolis_centrifugal_accel(
    position: npt.ArrayLike,
    velocity: npt.ArrayLike,
    omega_earth: float,
) -> npt.NDArray[np.float64]:
    """Calcula las aceleraciones ficticias (Coriolis y centrífuga) para el marco rotante ECEF.

    a_ficticias = -2 * (omega x v_ecef) - omega x (omega x r)

    Documentación de marco:
    Esta función es una utilidad pura para análisis o integraciones formuladas en el marco
    terrestre rotante ECEF (Earth-Centered, Earth-Fixed).
    ¡ATENCIÓN! En la integración del ascenso en marco inercial ECI (J2000), estas aceleraciones
    NO deben sumarse a las ecuaciones de movimiento, ya que el marco ECI es inercial y sumarlas
    constituiría un doble conteo erróneo de las fuerzas de inercia.

    Parámetros
    ----------
    position : ArrayLike (3,)
        Posición [x, y, z] en marco ECEF (m).
    velocity : ArrayLike (3,)
        Velocidad [vx, vy, vz] en marco ECEF (m/s).
    omega_earth : float
        Velocidad angular de la Tierra en rad/s.

    Retorna
    -------
    NDArray[np.float64] (3,)
        Aceleración ficticia total [ax, ay, az] en m/s^2.
    """
    pos = np.asarray(position, dtype=np.float64)
    vel = np.asarray(velocity, dtype=np.float64)
    omega_vec = np.array([0.0, 0.0, omega_earth], dtype=np.float64)

    # Aceleración de Coriolis: -2 * (omega x vel)
    a_coriolis = -2.0 * np.cross(omega_vec, vel)

    # Aceleración centrífuga: - omega x (omega x pos)
    a_centrifugal = -np.cross(omega_vec, np.cross(omega_vec, pos))

    return a_coriolis + a_centrifugal


# =============================================================================
# TERMODINÁMICA ATMOSFÉRICA Y AERODINÁMICA DEPENDIENTE DE MACH
# =============================================================================

GAMMA_AIR: float = 1.4  # Razón de calores específicos del aire seco
R_AIR_J_KG_K: float = 287.05287  # Constante específica del aire seco (US Standard Atmosphere 1976)

# Capas de la US Standard Atmosphere 1976: (altitud base [m], temperatura base [K], gradiente [K/m])
_US76_LAYERS: tuple[tuple[float, float, float], ...] = (
    (0.0, 288.15, -0.0065),
    (11_000.0, 216.65, 0.0),
    (20_000.0, 216.65, 0.001),
    (32_000.0, 228.65, 0.0028),
    (47_000.0, 270.65, 0.0),
    (51_000.0, 270.65, -0.0028),
    (71_000.0, 214.65, -0.002),
    (84_852.0, 186.946, 0.0),
)

# Presión en la base de cada capa, integrando la hidrostática desde p0 (≈ 22 632 Pa a 11 km,
# 5 475 Pa a 20 km, 868 Pa a 32 km, …, 0,373 Pa a 84,852 km, como la tabla oficial).
_US76_BASE_PRESSURE: tuple[float, ...] = tuple(
    float(v)
    for v in np.cumprod(
        [P0_PA]
        + [
            _layer_pressure_ratio(_US76_LAYERS[k + 1][0] - _US76_LAYERS[k][0], *_US76_LAYERS[k][1:])
            for k in range(len(_US76_LAYERS) - 1)
        ]
    )
)

# Tabla Cd(Mach) representativa de un lanzador esbelto a ángulo de ataque nulo.
# Reproduce el pico transónico de arrastre de onda (M ≈ 1.0 - 1.2) y el decaimiento supersónico.
# Fuente cualitativa: Sutton & Biblarz (2017), cap. 4; perfiles típicos de Saturn V / Space Shuttle.
_CD_MACH_TABLE: tuple[tuple[float, ...], tuple[float, ...]] = (
    (0.0, 0.6, 0.8, 0.95, 1.05, 1.2, 1.5, 2.0, 3.0, 5.0, 10.0),
    (0.30, 0.30, 0.34, 0.45, 0.55, 0.53, 0.46, 0.40, 0.32, 0.26, 0.24),
)


def compute_atmospheric_temperature(altitude_m: float) -> float:
    """Temperatura estática de la US Standard Atmosphere 1976 (capas lineales, h <= 86 km).

    T(h) = T_b + L_b * (h - h_b) en la capa b que contiene a h. Para h < 0 se satura en
    288.15 K y por encima de 84.852 km (altitud geopotencial) se mantiene la temperatura
    de la mesopausa (186.95 K), suficiente para el cálculo de Mach en el ascenso.

    Parámetros
    ----------
    altitude_m : float
        Altitud sobre la superficie en metros (m).

    Retorna
    -------
    float
        Temperatura en kelvin (K).
    """
    h = max(0.0, float(altitude_m))
    base_h, base_t, lapse = _US76_LAYERS[0]
    for layer in _US76_LAYERS:
        if h >= layer[0]:
            base_h, base_t, lapse = layer
        else:
            break
    return base_t + lapse * (h - base_h)


def compute_speed_of_sound(altitude_m: float) -> float:
    """Velocidad del sonido a = sqrt(gamma * R * T(h)) en m/s."""
    return float(np.sqrt(GAMMA_AIR * R_AIR_J_KG_K * compute_atmospheric_temperature(altitude_m)))


def compute_mach_number(speed_rel_m_s: float, altitude_m: float) -> float:
    """Número de Mach M = ||v_rel|| / a(h) (adimensional)."""
    return float(speed_rel_m_s) / compute_speed_of_sound(altitude_m)


def compute_drag_coefficient(mach: float) -> float:
    """Coeficiente de arrastre Cd(M) por interpolación lineal en la tabla representativa.

    Fuera del rango tabulado se mantiene constante el valor del extremo correspondiente.
    """
    return float(np.interp(mach, _CD_MACH_TABLE[0], _CD_MACH_TABLE[1]))


def compute_dynamic_pressure(speed_rel_m_s: float, altitude_m: float) -> float:
    """Presión dinámica q = 0.5 * rho(h) * ||v_rel||^2 en pascales (Pa)."""
    return 0.5 * compute_atmospheric_density(altitude_m) * float(speed_rel_m_s) ** 2
