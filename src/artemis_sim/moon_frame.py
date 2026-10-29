"""Marco selenocéntrico fijo a la Luna (MF) y conversiones con ECI.

La Luna rota de forma sincrónica: tarda en girar sobre su eje lo mismo que en dar una vuelta
a la Tierra. En nuestro modelo (órbita lunar circular con movimiento medio n) eso significa que
el marco fijo a la Luna gira con la misma ω = n ĥ que el marco rotante Tierra–Luna del CR3BP.
Ejes del MF:
    x̂ hacia la Tierra media (meridiano 0),  ẑ = ĥ (polo norte),  ŷ = ẑ × x̂.
Respecto del marco rotante del CR3BP (x̂ de la Tierra a la Luna) es un giro de 180° en z:
    r_MF = L (−(x − 1 + μ), −y, z),   v_MF = V (−v_x, −v_y, v_z).
La velocidad del MF ya es la relativa a un marco que rota, igual que la del CR3BP.

Simplificación documentada: el eje de rotación real de la Luna está inclinado ~6,7° respecto a
la normal de su órbita y los ejes del modelo GRGM1200A son los principales de inercia (PA), que
difieren ~1 km de los de la Tierra media. Aquí ambos se identifican con este marco.
"""

from __future__ import annotations

from typing import Final

import numpy as np

from artemis_sim.cr3bp import MU, UNITS, FloatArray, eci_to_rotating, rotating_to_eci
from artemis_sim.ephemeris import DEFAULT_LUNAR_CONFIG, LunarOrbitConfig
from artemis_sim.state import ArtemisState

_FLIP: Final[FloatArray] = np.array([-1.0, -1.0, 1.0])


def rotating_to_moon_fixed(state: FloatArray, mu: float = MU) -> FloatArray:
    """Estado adimensional rotante del CR3BP → estado MF en SI (selenocéntrico)."""
    rel = np.array([state[0] - 1.0 + mu, state[1], state[2]])
    return np.concatenate(
        [_FLIP * rel * UNITS.length_m, _FLIP * np.asarray(state[3:6]) * UNITS.velocity_m_s]
    )


def moon_fixed_to_rotating(state_mf: FloatArray, mu: float = MU) -> FloatArray:
    """Inversa de `rotating_to_moon_fixed`."""
    rel = _FLIP * np.asarray(state_mf[0:3]) / UNITS.length_m
    return np.concatenate(
        [
            [rel[0] + 1.0 - mu, rel[1], rel[2]],
            _FLIP * np.asarray(state_mf[3:6]) / UNITS.velocity_m_s,
        ]
    )


def moon_fixed_to_eci(
    state_mf: FloatArray, t_s: float, config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG
) -> ArtemisState:
    """Estado MF (SI) en t_s → ECI geocéntrico (masa 1; el llamador pone la real)."""
    return rotating_to_eci(moon_fixed_to_rotating(state_mf), t_s, config)


def eci_to_moon_fixed(
    st: ArtemisState, config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG
) -> FloatArray:
    """ECI geocéntrico → estado MF (SI)."""
    return rotating_to_moon_fixed(eci_to_rotating(st, config))


def latitude_longitude_deg(r_mf: FloatArray) -> tuple[float, float]:
    """Latitud y longitud selenográficas (grados) de una posición MF."""
    r = float(np.linalg.norm(r_mf))
    return (
        float(np.degrees(np.arcsin(r_mf[2] / r))),
        float(np.degrees(np.arctan2(r_mf[1], r_mf[0]))),
    )


def surface_point(lat_deg: float, lon_deg: float, radius_m: float) -> FloatArray:
    """Posición MF de un punto de latitud/longitud dadas a una distancia `radius_m` del centro."""
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    return radius_m * np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
