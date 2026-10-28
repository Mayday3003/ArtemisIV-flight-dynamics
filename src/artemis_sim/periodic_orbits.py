"""Órbitas de halo L2 y la NRHO 9:2 de Gateway en el CR3BP Tierra–Luna.

Método (Howell, 1984):
1. Simetría: una halo es simétrica respecto al plano xz. Se parte de (x0, 0, z0, 0, vy0, 0),
   se integra hasta el siguiente cruce con y = 0 (medio periodo) y se exige vx = vz = 0 ahí.
2. Corrección diferencial: Newton 2×2 sobre (x0, vy0) con z0 fijo, o sobre (z0, vy0) con x0
   fijo, usando la STM y la corrección por el cambio del instante de cruce:
       δvx_f = (Φ_{4j} − ax/vy · Φ_{2j}) δq_j,   δvz_f = (Φ_{6j} − az/vy · Φ_{2j}) δq_j.
3. Continuación natural a lo largo de la familia sur de L2. Cerca de las NRHO se avanza en z0;
   hacia L2 la familia tiene un pliegue en z0 (|z0| máximo ≈ 0,2), así que allí se avanza en x0.
4. `find_nrho`: método de la secante sobre z0 hasta que el periodo sea el pedido (6,56 d).

Semilla: un miembro NRHO de la base de datos "Three-Body Periodic Orbits" de NASA/JPL
(ssd-api.jpl.nasa.gov, familia halo L2 sur). Como nuestro mu difiere ligeramente del de JPL,
la semilla no es periódica en nuestro modelo: la corrección diferencial la ajusta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from artemis_sim.constants import MOON
from artemis_sim.cr3bp import (
    MU,
    UNITS,
    FloatArray,
    equations_of_motion,
    jacobi_constant,
    propagate,
)

SEED_NRHO: Final[FloatArray] = np.array(
    [1.0206705225108048, 0.0, -0.18114902142523231, 0.0, -0.10029449708871041, 0.0]
)
NRHO_PERIOD_DAYS: Final[float] = 6.56  # 9:2 con el mes sinódico: 2 · 29,53 d / 9


@dataclass(frozen=True, slots=True)
class PeriodicOrbit:
    """Órbita periódica simétrica (adimensional) y sus propiedades."""

    state0: FloatArray
    period: float
    jacobi: float
    monodromy: FloatArray
    iterations: int

    @property
    def period_days(self) -> float:
        return self.period * UNITS.time_s / 86400.0

    @property
    def eigenvalues(self) -> FloatArray:
        return np.asarray(np.linalg.eigvals(self.monodromy))

    @property
    def stability_index(self) -> float:
        """ν = (|λ_max| + 1/|λ_max|) / 2. ν ≈ 1: casi estable (como la NRHO de Gateway)."""
        lam = float(np.max(np.abs(self.eigenvalues)))
        return 0.5 * (lam + 1.0 / lam)

    def sample(self, n: int = 400, mu: float = MU) -> FloatArray:
        """Estados (6, n) equiespaciados en un periodo."""
        return propagate(self.state0, self.period, dense_points=n, mu=mu).states

    def moon_distance_range_m(self, mu: float = MU) -> tuple[float, float]:
        """(perilunio, apolunio) en metros, medidos desde el centro de la Luna."""
        s = self.sample(2000, mu)
        d = np.linalg.norm(s[0:3] - np.array([[1.0 - mu], [0.0], [0.0]]), axis=0)
        return float(d.min()) * UNITS.length_m, float(d.max()) * UNITS.length_m


def _half_period_crossing(state0: FloatArray, mu: float) -> tuple[float, FloatArray, FloatArray]:
    """Integra hasta el siguiente cruce con y = 0. Devuelve (t, estado, STM)."""

    def crossing(_t: float, s: FloatArray, _mu: float) -> float:
        return float(s[1])

    crossing.terminal = True  # type: ignore[attr-defined]
    crossing.direction = -float(np.sign(state0[4]))  # type: ignore[attr-defined]
    prop = propagate(state0, 10.0, with_stm=True, events=crossing, mu=mu)
    if not prop.t_events or prop.t_events[0].size == 0:
        raise RuntimeError("La órbita no volvió a cruzar el plano y = 0.")
    assert prop.stm is not None
    return float(prop.t[-1]), prop.states[:, -1], prop.stm


def correct_halo(
    state0: FloatArray,
    tol: float = 1e-11,
    max_iter: int = 30,
    fixed: str = "z",
    mu: float = MU,
) -> PeriodicOrbit:
    """Corrección diferencial: con `fixed="z"` ajusta (x0, vy0); con `fixed="x"`, (z0, vy0).

    Busca vx = vz = 0 en el cruce con y = 0 (medio periodo).
    """
    if fixed not in ("x", "z"):
        raise ValueError(f"fixed debe ser 'x' o 'z'; recibido {fixed!r}.")
    free = 2 if fixed == "x" else 0
    s0 = np.array(state0, dtype=np.float64)
    s0[[1, 3, 5]] = 0.0
    for it in range(1, max_iter + 1):
        t_half, sf, phi = _half_period_crossing(s0, mu)
        if abs(sf[3]) < tol and abs(sf[5]) < tol:
            break
        acc = equations_of_motion(0.0, sf, mu)
        vy = sf[4]
        cols = [free, 4]
        jac = np.array(
            [
                [phi[3, j] - acc[3] / vy * phi[1, j] for j in cols],
                [phi[5, j] - acc[5] / vy * phi[1, j] for j in cols],
            ]
        )
        dq = np.linalg.solve(jac, -np.array([sf[3], sf[5]]))
        s0[free] += dq[0]
        s0[4] += dq[1]
    else:
        raise RuntimeError(f"La corrección diferencial no convergió en {max_iter} iteraciones.")

    period = 2.0 * t_half
    monodromy = propagate(s0, period, with_stm=True, mu=mu).stm
    assert monodromy is not None
    return PeriodicOrbit(s0, period, jacobi_constant(s0, mu), monodromy, it)


def continue_family(
    orbit: PeriodicOrbit,
    step: float,
    steps: int,
    parameter: str = "z",
    max_jump: float = 0.05,
    mu: float = MU,
) -> list[PeriodicOrbit]:
    """Continuación natural en z0 (`parameter="z"`) o en x0 (`parameter="x"`).

    Se extrapola linealmente desde las dos últimas órbitas. Se detiene si la corrección falla o
    si el estado inicial salta más de `max_jump` (señal de haber caído en otra familia).
    """
    idx = 2 if parameter == "z" else 0
    family = [orbit]
    for _ in range(steps):
        prev = family[-1].state0
        guess = prev.copy()
        if len(family) >= 2:
            guess += prev - family[-2].state0  # extrapolación secante
        guess[idx] = prev[idx] + step
        try:
            new = correct_halo(guess, fixed=parameter, mu=mu)
        except (RuntimeError, np.linalg.LinAlgError):
            break
        if np.linalg.norm(new.state0 - prev) > max_jump:
            break
        family.append(new)
    return family


def find_nrho(
    period_days: float = NRHO_PERIOD_DAYS,
    seed: FloatArray = SEED_NRHO,
    tol_days: float = 1e-6,
    mu: float = MU,
) -> PeriodicOrbit:
    """NRHO de la familia halo L2 sur con el periodo pedido (secante sobre z0)."""
    a = correct_halo(seed, mu=mu)
    guess = a.state0.copy()
    guess[2] += 1e-3
    b = correct_halo(guess, mu=mu)
    for _ in range(30):
        fa, fb = a.period_days - period_days, b.period_days - period_days
        if abs(fb) < tol_days:
            return b
        z_new = b.state0[2] - fb * (b.state0[2] - a.state0[2]) / (fb - fa)
        guess = b.state0 + (b.state0 - a.state0) * (z_new - b.state0[2]) / (
            b.state0[2] - a.state0[2]
        )
        guess[2] = z_new
        a, b = b, correct_halo(guess, mu=mu)
    raise RuntimeError("find_nrho no alcanzó el periodo pedido.")


def perilune_altitude_m(orbit: PeriodicOrbit, mu: float = MU) -> float:
    """Altitud del perilunio sobre la superficie lunar (m)."""
    return orbit.moon_distance_range_m(mu)[0] - MOON.equatorial_radius_m
