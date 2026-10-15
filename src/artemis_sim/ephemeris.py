"""Modelo analítico de efemérides para el sistema Tierra-Luna.

Todas las magnitudes emplean unidades del Sistema Internacional (SI):
- Posición / distancia: metros (m)
- Velocidad: metros por segundo (m/s)
- Tiempo: segundos (s)
- Ángulos: radianes (rad)
- Velocidad angular: radianes por segundo (rad/s)

Marco de referencia: ECI (Earth-Centered Inertial, marco J2000).
Simplificaciones del modelo (Fase 3):
- La órbita lunar se aproxima como circular coplanar en el plano ecuatorial inercial (XY).
  TODO: En fases posteriores incorporar la inclinación real (~5.145° respecto a la eclíptica,
  u oscilación entre 18.3° y 28.6° respecto al ecuador terrestre), excentricidad (e ≈ 0.0549)
  y precesión nodal/apsidal mediante efemérides JPL DE421 / SPICE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from artemis_sim.constants import EARTH, MOON, CelestialBody

# Radio orbital medio de la Luna (m) y movimiento medio kepleriano autoconsistente.
LUNAR_ORBITAL_RADIUS_M: Final[float] = 384_400_000.0
# n = sqrt((mu_E + mu_M) / d^3): única velocidad angular compatible con una órbita circular
# relativa Tierra-Luna bajo gravedad newtoniana (tercera ley de Kepler). Con ella el modelo
# es exactamente el Problema Restringido Circular de Tres Cuerpos (CR3BP) y la constante de
# Jacobi es una integral del movimiento. El movimiento medio sidéreo observado (2.6617e-6 rad/s)
# difiere un 0.14 % por las perturbaciones solares y la excentricidad, ausentes en el modelo.
LUNAR_MEAN_MOTION_RAD_S: Final[float] = float(
    np.sqrt((EARTH.mu_m3_s2 + MOON.mu_m3_s2) / LUNAR_ORBITAL_RADIUS_M**3)
)


@dataclass(frozen=True, slots=True)
class LunarOrbitConfig:
    """Configuración inmutable de la órbita lunar simplificada.

    Parámetros
    ----------
    orbital_radius_m : float
        Semieje mayor / radio orbital medio de la Luna en metros (384,400,000.0 m).
        Fuente: NASA Moon Fact Sheet (distancia media centro a centro).
    mean_motion_rad_s : float
        Velocidad angular media en rad/s. Por defecto el valor kepleriano autoconsistente
        n = sqrt((mu_E + mu_M) / d^3) ≈ 2.6653e-6 rad/s (periodo ≈ 27.28 días), en lugar del
        sidéreo observado 2.6617e-6 rad/s (27.32 días), para que el CR3BP sea dinámicamente
        consistente (ver LUNAR_MEAN_MOTION_RAD_S).
    initial_phase_rad : float
        Fase o anomalía angular inicial de la Luna en t = 0 s (por defecto 0.0 rad, eje +X).
    """

    orbital_radius_m: float = LUNAR_ORBITAL_RADIUS_M
    mean_motion_rad_s: float = LUNAR_MEAN_MOTION_RAD_S
    initial_phase_rad: float = 0.0

    def __post_init__(self) -> None:
        """Valida valores físicos positivos."""
        if self.orbital_radius_m <= 0.0:
            raise ValueError(
                f"El radio orbital debe ser positivo (> 0). Valor recibido: {self.orbital_radius_m}"
            )
        if self.mean_motion_rad_s <= 0.0:
            raise ValueError(
                f"La velocidad angular debe ser positiva (> 0). Valor: {self.mean_motion_rad_s}"
            )


DEFAULT_LUNAR_CONFIG: Final[LunarOrbitConfig] = LunarOrbitConfig()


def get_body_position(
    body: CelestialBody,
    t: float,
    config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> npt.NDArray[np.float64]:
    """Calcula la posición geocéntrica [x, y, z] del cuerpo celeste en el instante t en ECI.

    Parámetros
    ----------
    body : CelestialBody
        Cuerpo celeste cuya posición se solicita ('Earth' o 'Moon').
    t : float
        Tiempo transcurrido en segundos (s).
    config : LunarOrbitConfig, opcional
        Parámetros orbitales para la Luna.

    Retorna
    -------
    NDArray[np.float64] (3,)
        Vector de posición geocéntrica [x, y, z] en metros (m).
    """
    b_name = body.name.strip().lower()
    if b_name == "earth":
        return np.zeros(3, dtype=np.float64)
    if b_name == "moon":
        theta = config.mean_motion_rad_s * t + config.initial_phase_rad
        d = config.orbital_radius_m
        return np.array([d * np.cos(theta), d * np.sin(theta), 0.0], dtype=np.float64)

    raise ValueError(
        f"Cuerpo celeste desconocido: '{body.name}'. Se soporta únicamente 'Earth' y 'Moon'."
    )


def get_body_velocity(
    body: CelestialBody,
    t: float,
    config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> npt.NDArray[np.float64]:
    """Calcula la velocidad geocéntrica [vx, vy, vz] del cuerpo celeste en el instante t en ECI.

    Derivada analítica temporal exacta de la posición:
    vx = -d * w * sin(w * t + phi0)
    vy =  d * w * cos(w * t + phi0)
    vz =  0.0

    Parámetros
    ----------
    body : CelestialBody
        Cuerpo celeste cuya velocidad se solicita ('Earth' o 'Moon').
    t : float
        Tiempo transcurrido en segundos (s).
    config : LunarOrbitConfig, opcional
        Parámetros orbitales para la Luna.

    Retorna
    -------
    NDArray[np.float64] (3,)
        Vector de velocidad inercial [vx, vy, vz] en metros por segundo (m/s).
    """
    b_name = body.name.strip().lower()
    if b_name == "earth":
        return np.zeros(3, dtype=np.float64)
    if b_name == "moon":
        w = config.mean_motion_rad_s
        d = config.orbital_radius_m
        theta = w * t + config.initial_phase_rad
        return np.array([-d * w * np.sin(theta), d * w * np.cos(theta), 0.0], dtype=np.float64)

    raise ValueError(
        f"Cuerpo celeste desconocido: '{body.name}'. Se soporta únicamente 'Earth' y 'Moon'."
    )
