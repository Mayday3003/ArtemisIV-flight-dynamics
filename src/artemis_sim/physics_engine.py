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

# Constantes estándar para el modelo atmosférico exponencial
RHO0_KG_M3: float = 1.225  # Densidad a nivel del mar (US Standard Atmosphere 1976)
H_RHO_M: float = 8500.0  # Altura de escala de densidad (m)

P0_PA: float = 101325.0  # Presión a nivel del mar estándar (Pa)
H_P_M: float = 7200.0  # Altura de escala de presión barométrica (m)


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
    """Calcula la densidad atmosférica según un modelo exponencial isotérmico.

    rho(h) = rho0 * exp(-h / H)
    - rho0 = 1.225 kg/m^3 (nivel medio del mar).
    - H = 8500.0 m (altura de escala aproximada).

    Rango de validez y saturación:
    - Válido como primera aproximación para la troposfera y estratosfera (0 <= h <= 100 km).
    - Para altitudes negativas (h < 0, p. ej. depresiones o ligeras fluctuaciones numéricas),
      se satura a rho0 (o se evalúa en h >= 0) para evitar densidades hiper-bajas o anomalías.
      Si h < 0, devuelve rho0 = 1.225 kg/m^3.
    - Para h > 100 km, la densidad cae a menos de 1e-5 kg/m^3, haciendo que el arrastre sea
      despreciable frente al empuje y la gravedad.

    Parámetros
    ----------
    altitude_m : float
        Altitud sobre la superficie esférica en metros (m).

    Retorna
    -------
    float
        Densidad atmosférica en kg/m^3.
    """
    if altitude_m < 0.0:
        return RHO0_KG_M3
    return float(RHO0_KG_M3 * np.exp(-altitude_m / H_RHO_M))


def compute_atmospheric_pressure(
    altitude_m: float,
) -> float:
    """Calcula la presión atmosférica estática ambiental según un modelo exponencial.

    p(h) = p0 * exp(-h / H_p)
    - p0 = 101325.0 Pa (1 atm estándar a nivel del mar).
    - H_p = 7200.0 m.
      Justificación: La altura de escala barométrica típica para la atmósfera inferior media
      (R_aire * T_media / g0 ≈ 287 * 250 / 9.80665 ≈ 7300 m) se aproxima en 7200 m para
      reproducir razonablemente la caída de presión en los primeros 30 km de ascenso.
      NOTA: Es una aproximación analítica gruesa frente a la US Standard Atmosphere 1976 por capas.

    Saturación:
    - Para h < 0 m, satura a p0 = 101325.0 Pa.

    Parámetros
    ----------
    altitude_m : float
        Altitud sobre la superficie esférica en metros (m).

    Retorna
    -------
    float
        Presión atmosférica en pascales (Pa).
    """
    if altitude_m < 0.0:
        return P0_PA
    return float(P0_PA * np.exp(-altitude_m / H_P_M))


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
