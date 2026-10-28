"""Disparo múltiple en el CR3BP adimensional.

La trayectoria se parte en N tramos. Cada tramo i empieza en un nodo X_i (6 componentes) y
dura ΔT_i. El vector de incógnitas es
    z = [X_0, …, X_{N−1}, ΔT_0, …, ΔT_{N−1}]            (7N valores)
y la continuidad exige  φ(X_i, ΔT_i) − X_{i+1} = 0  para i = 0 … N−2  (6(N−1) ecuaciones).
En un "nodo de encendido" k solo se exige continuidad de posición (3 ecuaciones): la diferencia
de velocidad X_k[3:6] − φ(X_{k−1}, ΔT_{k−1})[3:6] es una maniobra impulsiva.

Jacobiano por bloques (Φ_i = STM del tramo i, f = campo vectorial al final del tramo):
    ∂/∂X_i = Φ_i,   ∂/∂X_{i+1} = −I,   ∂/∂ΔT_i = f(φ(X_i, ΔT_i)).
Con tramos cortos cada propagación es poco sensible: por eso el método es más robusto que el
disparo simple cuando la trayectoria pasa cerca de la Luna.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from artemis_sim.cr3bp import MU, FloatArray, equations_of_motion, propagate


@dataclass(frozen=True, slots=True)
class Segment:
    """Resultado de propagar un tramo: estado final, STM y derivada temporal al final."""

    end: FloatArray
    stm: FloatArray
    f_end: FloatArray


class MultipleShooting:
    """Formulación de disparo múltiple con N nodos (adimensional)."""

    def __init__(self, n_nodes: int, burn_nodes: tuple[int, ...] = (), mu: float = MU) -> None:
        if n_nodes < 1:
            raise ValueError("Se necesita al menos un nodo.")
        if any(not 0 < k < n_nodes for k in burn_nodes):
            raise ValueError("Los nodos de encendido deben ser interiores (1 … N−1).")
        self.n = n_nodes
        self.burn_nodes = frozenset(burn_nodes)
        self.mu = mu
        self._cache_key: bytes | None = None
        self._cache: list[Segment] = []

    @property
    def size(self) -> int:
        return 7 * self.n

    def pack(self, nodes: FloatArray, durations: FloatArray) -> FloatArray:
        return np.concatenate([np.asarray(nodes, float).ravel(), np.asarray(durations, float)])

    def nodes(self, z: FloatArray) -> FloatArray:
        return np.asarray(z[: 6 * self.n]).reshape(self.n, 6)

    def durations(self, z: FloatArray) -> FloatArray:
        return np.asarray(z[6 * self.n : 7 * self.n])

    def node_slice(self, i: int) -> slice:
        return slice(6 * i, 6 * i + 6)

    def duration_index(self, i: int) -> int:
        return 6 * self.n + i

    def segments(self, z: FloatArray) -> list[Segment]:
        """Propaga cada tramo con su STM (con caché: SLSQP pide restricciones y jacobianos
        en el mismo punto varias veces)."""
        key = np.asarray(z, float).tobytes()
        if key != self._cache_key:
            out = []
            for x, dt in zip(self.nodes(z), self.durations(z), strict=True):
                prop = propagate(x, float(dt), with_stm=True, mu=self.mu)
                end = prop.states[:, -1]
                assert prop.stm is not None
                out.append(Segment(end, prop.stm, equations_of_motion(0.0, end, self.mu)))
            self._cache_key, self._cache = key, out
        return self._cache

    def _rows(self, i: int) -> int:
        """Ecuaciones de continuidad entre el tramo i y el nodo i+1 (3 si es de encendido)."""
        return 3 if (i + 1) in self.burn_nodes else 6

    def continuity(self, z: FloatArray) -> FloatArray:
        """Defectos φ(X_i, ΔT_i) − X_{i+1} (solo posición en los nodos de encendido)."""
        segs, x = self.segments(z), self.nodes(z)
        if self.n == 1:
            return np.zeros(0)
        return np.concatenate(
            [(segs[i].end - x[i + 1])[: self._rows(i)] for i in range(self.n - 1)]
        )

    def continuity_jacobian(self, z: FloatArray) -> FloatArray:
        """Jacobiano por bloques de `continuity`."""
        segs = self.segments(z)
        n_rows = sum(self._rows(i) for i in range(self.n - 1))
        jac = np.zeros((n_rows, self.size))
        r0 = 0
        for i in range(self.n - 1):
            k = self._rows(i)
            rows = slice(r0, r0 + k)
            jac[rows, self.node_slice(i)] = segs[i].stm[:k]
            jac[rows, self.node_slice(i + 1)] = -np.eye(6)[:k]
            jac[rows, self.duration_index(i)] = segs[i].f_end[:k]
            r0 += k
        return jac

    def burn(self, z: FloatArray, k: int) -> FloatArray:
        """Δv en el nodo de encendido k: X_k[3:6] − φ(X_{k−1}, ΔT_{k−1})[3:6]."""
        return np.asarray(self.nodes(z)[k, 3:6] - self.segments(z)[k - 1].end[3:6])

    def burn_gradient(self, z: FloatArray, k: int, unit: FloatArray) -> FloatArray:
        """Gradiente de  unit · Δv_k  respecto de z (para derivar |Δv_k|)."""
        seg = self.segments(z)[k - 1]
        g = np.zeros(self.size)
        g[6 * k + 3 : 6 * k + 6] = unit
        g[self.node_slice(k - 1)] -= unit @ seg.stm[3:6]
        g[self.duration_index(k - 1)] -= unit @ seg.f_end[3:6]
        return g


def newton_min_norm(
    residual: Callable[[FloatArray], FloatArray],
    jacobian: Callable[[FloatArray], FloatArray],
    z0: FloatArray,
    tol: float = 1e-11,
    max_iter: int = 30,
    max_step: float = 0.1,
) -> tuple[FloatArray, int]:
    """Newton para sistemas subdeterminados: paso de mínima norma δz = −J⁺ F (con `lstsq`).

    El paso se acota a `max_step` (norma infinito) para no saltar fuera de la región en la que
    la linealización es válida.
    """
    z = np.array(z0, dtype=float)
    for it in range(1, max_iter + 1):
        f = residual(z)
        if np.max(np.abs(f)) < tol:
            return z, it - 1
        dz = np.linalg.lstsq(jacobian(z), -f, rcond=None)[0]
        scale = min(1.0, max_step / max(np.max(np.abs(dz)), 1e-300))
        z = z + scale * dz
    if np.max(np.abs(residual(z))) < tol:
        return z, max_iter
    raise RuntimeError(f"Newton de mínima norma no convergió (|F| = {np.max(np.abs(f)):.2e}).")
