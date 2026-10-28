"""Transferencia TLI → NRHO (Fase 4): disparo múltiple + SLSQP en el CR3BP adimensional.

Perfil de tres maniobras, como el de Orion en Artemis:
    TLI (EUS, en la órbita de aparcamiento)
    → OPF, *outbound powered flyby*: encendido en el máximo acercamiento a la Luna
    → NRI, inserción en la NRHO unos días después, en el punto τ de la órbita.
¿Por qué no insertar directamente en el perilunio? En el marco rotante una trayectoria que
viene de la Tierra llega con v∞ hacia −y, mientras que la NRHO sur pasa por el perilunio
moviéndose hacia +y: la inserción directa costaría más de 1,4 km/s.

Planteamiento (marco rotante baricéntrico, adimensional):
- Nodos X_0 … X_{N−1} y duraciones ΔT_i (ver `multiple_shooting`); el nodo del sobrevuelo es
  un nodo de encendido (solo continuidad de posición).
- Variables extra: τ (fase de la NRHO, 0 = apolunio) y α (punto de la TLI sobre la órbita de
  aparcamiento: equivale a elegir la ventana de lanzamiento, es decir, la fase de la Luna).
- Restricciones: X_0[0:3] = r_aparcamiento(α), continuidad, φ(X_{N−1}, ΔT_{N−1})[0:3] = r_NRHO(τ).
- Objetivo: |Δv_TLI| + |Δv_OPF| + |Δv_NRI| (normas suavizadas con ε para que el gradiente
  exista cuando un Δv vale 0).

Semilla (diseño hacia atrás, el método habitual para llegar a órbitas periódicas):
1. Tramo 2 (`backward_seeds`): desde puntos de la NRHO cerca del apolunio se aplica una NRI
   pequeña (50 m/s) en varias direcciones y se propaga HACIA ATRÁS. Algunas trayectorias
   rozan la Luna a 100–300 km de altitud 2–5 días antes: ese periapsis P será el OPF.
2. Tramo 1: la trayectoria tras la TLI de la Fase 3 se lleva con homotopía + Newton de mínima
   norma hasta P (el hueco en P se cierra gradualmente).
3. SLSQP minimiza el Δv total con los jacobianos analíticos de la STM y la restricción de
   altitud mínima en el sobrevuelo. Se prueban varias semillas y se queda la mejor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy.optimize import minimize

from artemis_sim.constants import MOON
from artemis_sim.cr3bp import MU, UNITS, FloatArray, equations_of_motion, propagate
from artemis_sim.multiple_shooting import MultipleShooting, newton_min_norm
from artemis_sim.periodic_orbits import PeriodicOrbit


@dataclass(frozen=True, slots=True)
class NrhoTransfer:
    """Transferencia optimizada (adimensional salvo los Δv, en m/s)."""

    nodes: FloatArray
    durations: FloatArray
    tau: float
    departure_angle: float  # α: punto de la TLI en la órbita de aparcamiento (marco rotante)
    dv_tli: FloatArray  # vectores adimensionales en ejes rotantes
    dv_opf: FloatArray
    dv_nri: FloatArray
    flyby_node: int
    arrival: FloatArray  # estado al llegar, antes de la NRI
    nrho_state: FloatArray  # estado de la NRHO en τ (tras la NRI)
    max_defect: float
    optimizer_message: str

    @property
    def time_of_flight(self) -> float:
        return float(self.durations.sum())

    @property
    def time_of_flight_days(self) -> float:
        return self.time_of_flight * UNITS.time_s / 86400.0

    @property
    def dv_tli_m_s(self) -> float:
        return float(np.linalg.norm(self.dv_tli)) * UNITS.velocity_m_s

    @property
    def dv_opf_m_s(self) -> float:
        return float(np.linalg.norm(self.dv_opf)) * UNITS.velocity_m_s

    @property
    def flyby_time(self) -> float:
        """Instante del sobrevuelo propulsado desde la TLI (adimensional)."""
        return float(self.durations[: self.flyby_node].sum())

    @property
    def dv_total_m_s(self) -> float:
        return self.dv_tli_m_s + self.dv_opf_m_s + self.dv_nri_m_s

    @property
    def dv_nri_m_s(self) -> float:
        return float(np.linalg.norm(self.dv_nri)) * UNITS.velocity_m_s

    def dense(self, points_per_segment: int = 200, mu: float = MU) -> tuple[FloatArray, FloatArray]:
        """(t, estados 6×M) a lo largo de la transferencia, t desde la TLI (adimensional)."""
        ts, ys, t0 = [], [], 0.0
        for x, dt in zip(self.nodes, self.durations, strict=True):
            prop = propagate(x, float(dt), dense_points=points_per_segment, mu=mu)
            ts.append(t0 + prop.t)
            ys.append(prop.states)
            t0 += float(dt)
        return np.concatenate(ts), np.hstack(ys)


class _NrhoPoint:
    """Estado de la NRHO en la fase τ, con caché (lo piden restricciones y gradientes)."""

    def __init__(self, orbit: PeriodicOrbit, mu: float) -> None:
        self.orbit, self.mu = orbit, mu
        self._tau: float | None = None
        self._state = orbit.state0

    def state(self, tau: float) -> FloatArray:
        if tau != self._tau:
            t = (tau % 1.0) * self.orbit.period
            self._state = (
                self.orbit.state0.copy()
                if t == 0.0
                else propagate(self.orbit.state0, t, mu=self.mu).states[:, -1]
            )
            self._tau = tau
        return self._state

    def derivative(self, tau: float) -> FloatArray:
        """d estado / dτ = T · f(estado)."""
        return self.orbit.period * equations_of_motion(0.0, self.state(tau), self.mu)


def parking_state(alpha: float, radius: float, mu: float = MU) -> tuple[FloatArray, FloatArray]:
    """Estado rotante de la órbita de aparcamiento circular (en el plano lunar z = 0).

    Con la Tierra en (−mu, 0, 0) y d = ρ (cos α, sin α, 0):
        r = (−mu, 0, 0) + d,   v_rot = v_c (−sin α, cos α, 0) − ẑ × d   (ω = 1).
    Devuelve (estado, d estado/dα).
    """
    c, s = np.cos(alpha), np.sin(alpha)
    vc = np.sqrt((1.0 - mu) / radius)
    pos = [-mu + radius * c, radius * s, 0.0]
    vel = [-vc * s + radius * s, vc * c - radius * c, 0.0]
    d_pos = [-radius * s, radius * c, 0.0]
    d_vel = [-vc * c + radius * c, -vc * s + radius * s, 0.0]
    state, d_state = np.array(pos + vel), np.array(d_pos + d_vel)
    return state, d_state


def departure_angle(state: FloatArray, mu: float = MU) -> float:
    """Ángulo α del punto de partida respecto de la Tierra en el marco rotante."""
    return float(np.arctan2(state[1], state[0] + mu))


EPS = 1e-9  # suavizado de |Δv| (adimensional, ≈ 1 µm/s)


def _norm(v: FloatArray) -> float:
    return float(np.sqrt(v @ v + EPS**2))


MIN_FLYBY_ALTITUDE_M: Final[float] = 100e3


@dataclass(frozen=True, slots=True)
class BackwardSeed:
    """Tramo NRHO → (hacia atrás) → periapsis lunar. Estados en orden temporal directo."""

    tau: float
    t: FloatArray  # desde el periapsis (0) hasta la NRI
    states: FloatArray
    flyby_altitude_m: float


def backward_seeds(
    orbit: PeriodicOrbit,
    dv_nri_m_s: float = 50.0,
    taus: tuple[float, ...] = (-0.12, -0.06, 0.0, 0.06, 0.12),
    max_days: float = 6.0,
    altitude_range_m: tuple[float, float] = (100e3, 400e3),
    days_range: tuple[float, float] = (2.0, 5.0),
    mu: float = MU,
) -> list[BackwardSeed]:
    """Propaga hacia atrás desde la NRHO con una NRI pequeña y devuelve los tramos que pasan
    cerca de la Luna, ordenados por altitud del periapsis."""
    moon = np.array([1.0 - mu, 0.0, 0.0])
    r_moon = MOON.equatorial_radius_m / UNITS.length_m
    dirs: list[FloatArray] = []
    for th in np.linspace(0.0, np.pi, 7):
        for ph in np.linspace(0.0, 2.0 * np.pi, 12, endpoint=False):
            d = np.array([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)])
            if not any(np.allclose(d, e) for e in dirs):
                dirs.append(d)

    def impact(_t: float, s: FloatArray, _mu: float) -> float:
        return float(np.linalg.norm(s[0:3] - moon) - r_moon)

    impact.terminal = True  # type: ignore[attr-defined]
    seeds = []
    for tau in taus:
        s0 = orbit.state_at(tau, mu)
        for d in dirs:
            s = s0.copy()
            s[3:6] += d * dv_nri_m_s / UNITS.velocity_m_s
            prop = propagate(s, -max_days * 86400.0 / UNITS.time_s, events=impact, mu=mu)
            dist = np.linalg.norm(prop.states[0:3] - moon[:, None], axis=0)
            i = int(np.argmin(dist))
            alt = (dist[i] - r_moon) * UNITS.length_m
            days = -prop.t[i] * UNITS.time_s / 86400.0
            if altitude_range_m[0] <= alt <= altitude_range_m[1] and (
                days_range[0] <= days <= days_range[1]
            ):
                t_fwd = prop.t[: i + 1][::-1] - prop.t[i]
                seeds.append(BackwardSeed(tau, t_fwd, prop.states[:, : i + 1][:, ::-1], alt))
    seeds.sort(key=lambda b: b.flyby_altitude_m)
    return seeds


def design_transfer(
    burn_state: FloatArray,
    post_tli_state: FloatArray,
    orbit: PeriodicOrbit,
    seed: BackwardSeed,
    n_before: int = 6,
    n_after: int = 6,
    free_departure: bool = True,
    homotopy_steps: int = 12,
    mu: float = MU,
) -> NrhoTransfer:
    """Diseña la transferencia TLI → OPF → NRI a partir de una semilla hacia atrás.

    burn_state: estado rotante en el punto de la TLI, ANTES del encendido.
    post_tli_state: estado rotante justo DESPUÉS de una TLI semilla (la de la Fase 3).
    free_departure: si es False, el punto de partida es exactamente `burn_state`.
    """
    moon = np.array([1.0 - mu, 0.0, 0.0])
    # Tramo 1: de la TLI al máximo acercamiento de la trayectoria de la Fase 3
    p1 = propagate(post_tli_state, 6.0 * 86400.0 / UNITS.time_s, dense_points=3000, mu=mu)
    i_fb = int(np.argmin(np.linalg.norm(p1.states[0:3] - moon[:, None], axis=0)))
    t1, y1 = p1.t[: i_fb + 1], p1.states[:, : i_fb + 1]
    s1 = np.linspace(0.0, 1.0, n_before + 1)[:-1]
    idx1 = np.searchsorted(t1, t1[-1] * (1.0 - (1.0 - s1) ** 2))
    # Tramo 2: del periapsis a la NRI (semilla hacia atrás, exacta)
    s2 = np.linspace(0.0, 1.0, n_after + 1)[:-1]
    idx2 = np.searchsorted(seed.t, seed.t[-1] * s2**2)
    nodes = np.vstack([y1[:, idx1].T, seed.states[:, idx2].T])
    durations = np.concatenate(
        [np.diff(np.append(t1[idx1], t1[-1])), np.diff(np.append(seed.t[idx2], seed.t[-1]))]
    )
    n_nodes, k_fb = n_before + n_after, n_before
    ms = MultipleShooting(n_nodes, burn_nodes=(k_fb,), mu=mu)
    z = ms.pack(nodes, durations)

    nrho = _NrhoPoint(orbit, mu)
    tau0 = seed.tau
    radius = float(np.hypot(burn_state[0] + mu, burn_state[1]))
    last = n_nodes - 1
    r_min = (MOON.equatorial_radius_m + MIN_FLYBY_ALTITUDE_M) / UNITS.length_m

    def departure(alpha: float) -> tuple[FloatArray, FloatArray]:
        if free_departure:
            return parking_state(alpha, radius, mu)
        return burn_state, np.zeros(6)

    def end_position_jac(zz: FloatArray) -> FloatArray:
        seg = ms.segments(zz)[last]
        jac = np.zeros((3, ms.size))
        jac[:, ms.node_slice(last)] = seg.stm[0:3]
        jac[:, ms.duration_index(last)] = seg.f_end[0:3]
        return jac

    start_jac = np.zeros((3, ms.size))
    start_jac[:, 0:3] = np.eye(3)
    alpha0 = departure_angle(burn_state, mu)

    # 1. Factibilidad con homotopía: el hueco de posición en el periapsis se cierra poco a poco
    r_start = departure(alpha0)[0][0:3]
    r_goal = nrho.state(tau0)[0:3]
    gap_rows = slice(6 * (k_fb - 1), 6 * (k_fb - 1) + 3)  # filas de posición del nodo k_fb
    gap0 = ms.continuity(z)[gap_rows].copy()
    for s in np.linspace(0.0, 1.0, homotopy_steps + 1)[1:]:
        offset = np.zeros_like(ms.continuity(z))
        offset[gap_rows] = (1.0 - s) * gap0

        def residual(zz: FloatArray, offset: FloatArray = offset) -> FloatArray:
            return np.concatenate(
                [
                    zz[0:3] - r_start,
                    ms.continuity(zz) - offset,
                    ms.segments(zz)[last].end[0:3] - r_goal,
                ]
            )

        def jacobian(zz: FloatArray) -> FloatArray:
            return np.vstack([start_jac, ms.continuity_jacobian(zz), end_position_jac(zz)])

        z, _ = newton_min_norm(residual, jacobian, z, tol=1e-10, max_step=0.05)

    def flyby_radius(w: FloatArray) -> FloatArray:
        x = ms.nodes(w[:-2])[k_fb]
        return np.array([np.linalg.norm(x[0:3] - moon) - r_min])

    def flyby_radius_jac(w: FloatArray) -> FloatArray:
        x = ms.nodes(w[:-2])[k_fb]
        g = np.zeros((1, w.size))
        g[0, 6 * k_fb : 6 * k_fb + 3] = (x[0:3] - moon) / np.linalg.norm(x[0:3] - moon)
        return g

    # 2. Optimización del Δv total con SLSQP; w = [z, τ, α]
    def split(w: FloatArray) -> tuple[FloatArray, float, float]:
        return w[:-2], float(w[-2]), float(w[-1])

    def dv_vectors(w: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
        zz, tau, alpha = split(w)
        dep = departure(alpha)[0]
        return (
            zz[3:6] - dep[3:6],
            ms.burn(zz, k_fb),
            nrho.state(tau)[3:6] - ms.segments(zz)[last].end[3:6],
        )

    def objective(w: FloatArray) -> float:
        return sum(_norm(v) for v in dv_vectors(w))

    def objective_grad(w: FloatArray) -> FloatArray:
        zz, tau, alpha = split(w)
        a, f, b = dv_vectors(w)
        ua, uf, ub = a / _norm(a), f / _norm(f), b / _norm(b)
        seg = ms.segments(zz)[last]
        g = np.zeros(w.size)
        g[3:6] = ua
        g[:-2] += ms.burn_gradient(zz, k_fb, uf)
        g[ms.node_slice(last)] -= ub @ seg.stm[3:6]
        g[ms.duration_index(last)] -= ub @ seg.f_end[3:6]
        g[-2] = ub @ nrho.derivative(tau)[3:6]
        g[-1] = -ua @ departure(alpha)[1][3:6]
        return g

    def constraints(w: FloatArray) -> FloatArray:
        zz, tau, alpha = split(w)
        return np.concatenate(
            [
                zz[0:3] - departure(alpha)[0][0:3],
                ms.continuity(zz),
                ms.segments(zz)[last].end[0:3] - nrho.state(tau)[0:3],
            ]
        )

    def constraints_jac(w: FloatArray) -> FloatArray:
        zz, tau, alpha = split(w)
        top = np.vstack([start_jac, ms.continuity_jacobian(zz), end_position_jac(zz)])
        extra = np.zeros((top.shape[0], 2))
        extra[0:3, 1] = -departure(alpha)[1][0:3]
        extra[-3:, 0] = -nrho.derivative(tau)[0:3]
        return np.hstack([top, extra])

    w0 = np.concatenate([z, [tau0, alpha0]])
    bounds = (
        [(None, None)] * (6 * n_nodes)
        + [(1e-3, None)] * n_nodes
        + [(tau0 - 0.25, tau0 + 0.25)]
        + [(alpha0 - np.pi, alpha0 + np.pi) if free_departure else (alpha0, alpha0)]
    )
    res = minimize(
        objective,
        w0,
        jac=objective_grad,
        method="SLSQP",
        constraints=[
            {"type": "eq", "fun": constraints, "jac": constraints_jac},
            {"type": "ineq", "fun": flyby_radius, "jac": flyby_radius_jac},
        ],
        bounds=bounds,
        options={"maxiter": 300, "ftol": 1e-12},
    )
    # Pulido final de la factibilidad (SLSQP deja defectos del orden de su tolerancia)
    _, tau, alpha = split(res.x)
    z_final, _ = newton_min_norm(
        lambda zz: constraints(np.concatenate([zz, [tau, alpha]])),
        lambda zz: constraints_jac(np.concatenate([zz, [tau, alpha]]))[:, :-2],
        res.x[:-2],
        tol=1e-12,
    )
    w = np.concatenate([z_final, [tau, alpha]])
    a, f, b = dv_vectors(w)
    return NrhoTransfer(
        nodes=ms.nodes(z_final).copy(),
        durations=ms.durations(z_final).copy(),
        tau=tau % 1.0,
        departure_angle=alpha,
        dv_tli=a,
        dv_opf=f,
        dv_nri=b,
        flyby_node=k_fb,
        arrival=ms.segments(z_final)[last].end.copy(),
        nrho_state=nrho.state(tau).copy(),
        max_defect=float(np.max(np.abs(constraints(w)))),
        optimizer_message=str(res.message),
    )


def optimize_nrho_transfer(
    burn_state: FloatArray,
    post_tli_state: FloatArray,
    orbit: PeriodicOrbit,
    max_seeds: int = 4,
    free_departure: bool = True,
    mu: float = MU,
) -> NrhoTransfer:
    """Prueba las mejores semillas hacia atrás y devuelve la transferencia de menor Δv total."""
    best: NrhoTransfer | None = None
    for seed in backward_seeds(orbit, mu=mu)[:max_seeds]:
        try:
            tr = design_transfer(
                burn_state, post_tli_state, orbit, seed, free_departure=free_departure, mu=mu
            )
        except (RuntimeError, np.linalg.LinAlgError):
            continue
        if tr.max_defect < 1e-9 and (best is None or tr.dv_total_m_s < best.dv_total_m_s):
            best = tr
    if best is None:
        raise RuntimeError("Ninguna semilla produjo una transferencia factible a la NRHO.")
    return best


def refine_transfer(
    transfer: NrhoTransfer,
    burn_state: FloatArray,
    orbit: PeriodicOrbit,
    mu: float = MU,
) -> NrhoTransfer:
    """Recalcula la transferencia con el punto de partida REAL (τ fijo, sin optimizar).

    Tras elegir la fase de la Luna con el α óptimo, la órbita de aparcamiento real (con la
    perturbación lunar) deja la nave a unos metros del círculo ideal: basta un Newton de mínima
    norma desde la solución optimizada.
    """
    n = transfer.nodes.shape[0]
    k_fb, last = transfer.flyby_node, n - 1
    ms = MultipleShooting(n, burn_nodes=(k_fb,), mu=mu)
    r_end = orbit.state_at(transfer.tau, mu)[0:3]

    def residual(zz: FloatArray) -> FloatArray:
        return np.concatenate(
            [zz[0:3] - burn_state[0:3], ms.continuity(zz), ms.segments(zz)[last].end[0:3] - r_end]
        )

    def jacobian(zz: FloatArray) -> FloatArray:
        start = np.zeros((3, ms.size))
        start[:, 0:3] = np.eye(3)
        seg = ms.segments(zz)[last]
        end = np.zeros((3, ms.size))
        end[:, ms.node_slice(last)] = seg.stm[0:3]
        end[:, ms.duration_index(last)] = seg.f_end[0:3]
        return np.vstack([start, ms.continuity_jacobian(zz), end])

    z, _ = newton_min_norm(
        residual, jacobian, ms.pack(transfer.nodes, transfer.durations), tol=1e-12
    )
    nrho_state = orbit.state_at(transfer.tau, mu)
    arrival = ms.segments(z)[last].end.copy()
    return NrhoTransfer(
        nodes=ms.nodes(z).copy(),
        durations=ms.durations(z).copy(),
        tau=transfer.tau,
        departure_angle=departure_angle(burn_state, mu),
        dv_tli=ms.nodes(z)[0, 3:6] - burn_state[3:6],
        dv_opf=ms.burn(z, k_fb),
        dv_nri=nrho_state[3:6] - arrival[3:6],
        flyby_node=k_fb,
        arrival=arrival,
        nrho_state=nrho_state,
        max_defect=float(np.max(np.abs(residual(z)))),
        optimizer_message="refinado con el punto de partida real",
    )
