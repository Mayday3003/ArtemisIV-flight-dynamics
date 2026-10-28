"""Problema restringido circular de tres cuerpos (CR3BP) Tierra–Luna en forma adimensional.

Unidades canónicas (derivadas de nuestro propio modelo, no de una tabla externa):
    longitud  L  = d (radio de la órbita lunar de `LunarOrbitConfig`, 384 400 km)
    tiempo    TU = 1 / n (con n = sqrt((mu_E + mu_M) / d^3), el movimiento medio kepleriano)
    masa      mu = mu_M / (mu_E + mu_M) ≈ 0.012155

Marco rotante baricéntrico: x de la Tierra a la Luna, z normal al plano lunar. La Tierra está
en (−mu, 0, 0) y la Luna en (1 − mu, 0, 0). Ecuaciones de movimiento:
    x'' − 2 y' = Ω_x,   y'' + 2 x' = Ω_y,   z'' = Ω_z,
    Ω = (x² + y²)/2 + (1 − mu)/r1 + mu/r2.
Es el mismo modelo que el geocéntrico con término indirecto de `symplectic_solver`: solo
cambian las coordenadas (lo comprueba la prueba de la constante de Jacobi).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import numpy.typing as npt
from scipy.integrate import solve_ivp

from artemis_sim.constants import EARTH, MOON
from artemis_sim.ephemeris import DEFAULT_LUNAR_CONFIG, LunarOrbitConfig
from artemis_sim.state import ArtemisState

FloatArray = npt.NDArray[np.float64]

MU: Final[float] = MOON.mu_m3_s2 / (EARTH.mu_m3_s2 + MOON.mu_m3_s2)
RTOL: Final[float] = 1e-12
ATOL: Final[float] = 1e-12


@dataclass(frozen=True, slots=True)
class CanonicalUnits:
    """Factores de conversión adimensional ↔ SI para una órbita lunar dada."""

    length_m: float
    time_s: float

    @property
    def velocity_m_s(self) -> float:
        return self.length_m / self.time_s

    @classmethod
    def from_lunar_config(cls, config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG) -> CanonicalUnits:
        return cls(length_m=config.orbital_radius_m, time_s=1.0 / config.mean_motion_rad_s)


UNITS: Final[CanonicalUnits] = CanonicalUnits.from_lunar_config()


def primary_distances(r: FloatArray, mu: float = MU) -> tuple[float, float]:
    """Distancias r1 (a la Tierra) y r2 (a la Luna) en unidades adimensionales."""
    r1 = float(np.sqrt((r[0] + mu) ** 2 + r[1] ** 2 + r[2] ** 2))
    r2 = float(np.sqrt((r[0] - 1.0 + mu) ** 2 + r[1] ** 2 + r[2] ** 2))
    return r1, r2


def pseudo_potential(r: FloatArray, mu: float = MU) -> float:
    """Ω(x, y, z) = (x² + y²)/2 + (1 − mu)/r1 + mu/r2."""
    r1, r2 = primary_distances(r, mu)
    return float(0.5 * (r[0] ** 2 + r[1] ** 2) + (1.0 - mu) / r1 + mu / r2)


def pseudo_potential_gradient(r: FloatArray, mu: float = MU) -> FloatArray:
    """(Ω_x, Ω_y, Ω_z)."""
    x, y, z = r
    r1, r2 = primary_distances(r, mu)
    a, b = (1.0 - mu) / r1**3, mu / r2**3
    return np.array(
        [x - a * (x + mu) - b * (x - 1.0 + mu), y - (a + b) * y, -(a + b) * z],
        dtype=np.float64,
    )


def pseudo_potential_hessian(r: FloatArray, mu: float = MU) -> FloatArray:
    """Matriz 3×3 de segundas derivadas Ω_rr (simétrica)."""
    r1, r2 = primary_distances(r, mu)
    d1 = np.array([r[0] + mu, r[1], r[2]])
    d2 = np.array([r[0] - 1.0 + mu, r[1], r[2]])
    h = (
        -(1.0 - mu) / r1**3 * np.eye(3)
        + 3.0 * (1.0 - mu) / r1**5 * np.outer(d1, d1)
        - mu / r2**3 * np.eye(3)
        + 3.0 * mu / r2**5 * np.outer(d2, d2)
    )
    h[0, 0] += 1.0
    h[1, 1] += 1.0
    return np.asarray(h, dtype=np.float64)


def jacobi_constant(state: FloatArray, mu: float = MU) -> float:
    """C = 2Ω − |v|² (adimensional)."""
    return 2.0 * pseudo_potential(state[0:3], mu) - float(np.dot(state[3:6], state[3:6]))


def equations_of_motion(_t: float, s: FloatArray, mu: float = MU) -> FloatArray:
    """Derivada del estado [x, y, z, vx, vy, vz]."""
    g = pseudo_potential_gradient(s[0:3], mu)
    return np.array([s[3], s[4], s[5], g[0] + 2.0 * s[4], g[1] - 2.0 * s[3], g[2]])


_J = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 0.0]])


def variational_matrix(r: FloatArray, mu: float = MU) -> FloatArray:
    """A(t) = [[0, I], [Ω_rr, 2J]] del sistema linealizado δs' = A δs."""
    a = np.zeros((6, 6))
    a[0:3, 3:6] = np.eye(3)
    a[3:6, 0:3] = pseudo_potential_hessian(r, mu)
    a[3:6, 3:6] = 2.0 * _J
    return a


def equations_with_stm(_t: float, s: FloatArray, mu: float = MU) -> FloatArray:
    """Estado (6) + STM Φ (36, por filas): 42 ecuaciones, Φ' = A Φ."""
    phi = s[6:].reshape(6, 6)
    out = np.empty(42)
    out[0:6] = equations_of_motion(_t, s[0:6], mu)
    out[6:] = (variational_matrix(s[0:3], mu) @ phi).ravel()
    return out


@dataclass(frozen=True, slots=True)
class Propagation:
    """Resultado de propagar: tiempos, estados (6, N) y STM final (o None)."""

    t: FloatArray
    states: FloatArray
    stm: FloatArray | None
    t_events: list[FloatArray]


def propagate(
    state0: FloatArray,
    t_final: float,
    with_stm: bool = False,
    events: Any = None,
    dense_points: int | None = None,
    mu: float = MU,
) -> Propagation:
    """Integra con DOP853 (rtol = atol = 1e-12). Si hay evento terminal, se detiene ahí."""
    y0 = np.concatenate([state0, np.eye(6).ravel()]) if with_stm else np.asarray(state0, float)
    rhs = equations_with_stm if with_stm else equations_of_motion
    t_eval = np.linspace(0.0, t_final, dense_points) if dense_points else None
    sol = solve_ivp(
        rhs, (0.0, t_final), y0, method="DOP853", rtol=RTOL, atol=ATOL,
        events=events, t_eval=t_eval, args=(mu,),
    )  # fmt: skip
    if sol.status == -1:
        raise RuntimeError(f"Fallo de integración en el CR3BP: {sol.message}")
    t_arr, states = sol.t, sol.y  # con evento terminal, el último punto es el del evento
    stm = states[6:, -1].reshape(6, 6) if with_stm else None
    return Propagation(t_arr, states[0:6], stm, list(sol.t_events or []))


def lagrange_points(mu: float = MU) -> dict[str, FloatArray]:
    """L1, L2, L3 (raíces colineales de Ω_x = 0, por Newton) y L4, L5 (triangulares)."""

    def omega_x(x: float) -> float:
        return float(pseudo_potential_gradient(np.array([x, 0.0, 0.0]), mu)[0])

    def omega_xx(x: float) -> float:
        return float(pseudo_potential_hessian(np.array([x, 0.0, 0.0]), mu)[0, 0])

    guess_r = (mu / 3.0) ** (1.0 / 3.0)  # distancia de Hill a la Luna
    seeds = {"L1": 1.0 - mu - guess_r, "L2": 1.0 - mu + guess_r, "L3": -1.0 - 5.0 * mu / 12.0}
    points: dict[str, FloatArray] = {}
    for name, x in seeds.items():
        for _ in range(50):
            step = omega_x(x) / omega_xx(x)
            x -= step
            if abs(step) < 1e-15:
                break
        points[name] = np.array([x, 0.0, 0.0])
    points["L4"] = np.array([0.5 - mu, np.sqrt(3.0) / 2.0, 0.0])
    points["L5"] = np.array([0.5 - mu, -np.sqrt(3.0) / 2.0, 0.0])
    return points


def rotating_to_eci(
    state: FloatArray,
    t_s: float,
    config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
    mu: float = MU,
) -> ArtemisState:
    """Convierte un estado adimensional rotante baricéntrico a ECI geocéntrico (SI) en t_s.

    Con θ = n t + φ0 y la base del plano lunar (p, q, h):
        e1 = cos θ p + sin θ q (hacia la Luna),  e2 = −sin θ p + cos θ q,  e3 = h
        r = L [(x + mu) e1 + y e2 + z e3]
        v = (L/TU) (vx e1 + vy e2 + vz e3) + n h × r
    """
    units = CanonicalUnits.from_lunar_config(config)
    basis = rotating_basis(t_s, config)
    rel = np.array([state[0] + mu, state[1], state[2]])
    r = units.length_m * basis.T @ rel
    v = units.velocity_m_s * basis.T @ state[3:6] + np.cross(config.mean_motion_rad_s * basis[2], r)
    return ArtemisState(r, v, 1.0, t_s)


def eci_to_rotating(
    st: ArtemisState,
    config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
    mu: float = MU,
) -> FloatArray:
    """Inversa de `rotating_to_eci`."""
    units = CanonicalUnits.from_lunar_config(config)
    basis = rotating_basis(st.t, config)
    v_rot = st.velocity - np.cross(config.mean_motion_rad_s * basis[2], st.position)
    rel = basis @ st.position / units.length_m
    return np.concatenate([[rel[0] - mu, rel[1], rel[2]], basis @ v_rot / units.velocity_m_s])


def rotating_basis(t_s: float, config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG) -> FloatArray:
    """Matriz 3×3 cuyas filas son (e1, e2, e3) del marco rotante expresadas en ECI."""
    theta = config.mean_motion_rad_s * t_s + config.initial_phase_rad
    p, q, h = config.plane_basis()
    c, s = np.cos(theta), np.sin(theta)
    return np.vstack([c * p + s * q, -s * p + c * q, h])
