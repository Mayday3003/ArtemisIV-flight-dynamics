"""Gravedad lunar en armónicos esféricos (modelo GRGM1200A de GRAIL) sin singularidad polar.

Potencial en el marco fijo a la Luna (ejes principales, PA):
    U(r, φ, λ) = (μ/r) Σ_{n=0}^{N} (R/r)^n Σ_{m=0}^{n} P̄_nm(sin φ) (C̄_nm cos mλ + S̄_nm sin mλ)

La forma en (r, φ, λ) tiene derivadas con 1/cos φ: explota justo en el polo sur, donde
aterrizamos. Por eso se usa la formulación de Pines (1973) con los cosenos directores
    s = x/r,  t = y/r,  u = z/r,
y los polinomios de Helmholtz Ā_nm(u) = N_nm dᵐP_n/duᵐ, que cumplen
    P̄_nm(sin φ) cos mλ = Ā_nm(u) Re[(s + i t)ᵐ],   P̄_nm(sin φ) sin mλ = Ā_nm(u) Im[(s + i t)ᵐ].
Todo es polinómico en (s, t, u): no hay divisiones por cos φ.

Recurrencia estable por columnas (la misma que la de los P̄_nm, porque el factor cosᵐφ se
cancela), con Ā_00 = 1, Ā_11 = √3 y, para n ≥ 2, Ā_nn = √((2n+1)/(2n)) Ā_{n−1,n−1}:
    Ā_nm = a_nm u Ā_{n−1,m} − b_nm Ā_{n−2,m},
    a_nm = √((2n+1)(2n−1) / ((n−m)(n+m))),
    b_nm = √((2n+1)(n+m−1)(n−m−1) / ((2n−3)(n+m)(n−m))).
Derivada: dĀ_nm/du = √((2−δ_m0)/2 · (n−m)(n+m+1)) Ā_{n,m+1}.

Gradiente, tratando U como función de (r, s, t, u) independientes:
    a = (U_s, U_t, U_u)/r + [U_r − (s U_s + t U_t + u U_u)/r] ê_r.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "grgm1200a_n100.npz"


@lru_cache(maxsize=8)
def _recurrence_coefficients(n_max: int) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Coeficientes a_nm, b_nm, diagonal y de derivada (dependen solo del grado máximo)."""
    a = np.zeros((n_max + 2, n_max + 2))
    b = np.zeros((n_max + 2, n_max + 2))
    diag = np.zeros(n_max + 2)
    deriv = np.zeros((n_max + 2, n_max + 2))
    for n in range(n_max + 2):
        diag[n] = 1.0 if n == 0 else np.sqrt(3.0) if n == 1 else np.sqrt((2 * n + 1) / (2 * n))
        for m in range(n):
            a[n, m] = np.sqrt((2 * n + 1) * (2 * n - 1) / ((n - m) * (n + m)))
            if n >= 2:
                b[n, m] = np.sqrt(
                    (2 * n + 1) * (n + m - 1) * (n - m - 1) / ((2 * n - 3) * (n + m) * (n - m))
                )
        for m in range(n + 1):
            deriv[n, m] = np.sqrt((2.0 - (m == 0)) / 2.0 * (n - m) * (n + m + 1))
    return a, b, diag, deriv


def helmholtz_polynomials(u: float, n_max: int) -> FloatArray:
    """Ā_nm(u) para 0 ≤ m ≤ n ≤ n_max + 1 (la fila extra sirve para las derivadas)."""
    a, b, diag, _ = _recurrence_coefficients(n_max)
    out = np.zeros((n_max + 2, n_max + 2))
    out[0, 0] = 1.0
    for n in range(1, n_max + 2):
        out[n, n] = diag[n] * out[n - 1, n - 1]
        out[n, :n] = a[n, :n] * u * out[n - 1, :n]
        if n >= 2:
            out[n, : n - 1] -= b[n, : n - 1] * out[n - 2, : n - 1]
    return out


class LunarGravityField:
    """Campo gravitatorio lunar truncado en grado N (posiciones en el marco PA, en metros).

    Usa el GM y el radio de referencia del propio modelo GRGM1200A (no los de `MOON`): los
    coeficientes solo son válidos con los valores con los que se ajustaron.
    """

    def __init__(
        self,
        c: FloatArray,
        s: FloatArray,
        gm_m3_s2: float,
        radius_m: float,
        n_max: int | None = None,
    ) -> None:
        n_avail = c.shape[0] - 1
        self.n_max = n_avail if n_max is None else n_max
        if not 0 <= self.n_max <= n_avail:
            raise ValueError(f"Grado máximo fuera de rango (0 … {n_avail}): {self.n_max}")
        k = self.n_max + 1
        self.c = np.array(c[:k, :k], dtype=np.float64)
        self.s = np.array(s[:k, :k], dtype=np.float64)
        self.gm = gm_m3_s2
        self.radius = radius_m
        self._m = np.arange(k, dtype=np.float64)
        self._n = np.arange(k, dtype=np.float64)

    @classmethod
    def grgm1200a(cls, n_max: int = 100, path: Path = DATA_FILE) -> LunarGravityField:
        """Carga los coeficientes descargados con `scripts/fetch_grail.py`."""
        data = np.load(path)
        return cls(data["C"], data["S"], float(data["gm_m3_s2"]), float(data["radius_m"]), n_max)

    @property
    def j2(self) -> float:
        """J₂ = −√5 C̄₂₀ (coeficiente no normalizado)."""
        return float(-np.sqrt(5.0) * self.c[2, 0]) if self.n_max >= 2 else 0.0

    def _terms(self, r_vec: FloatArray) -> tuple[float, FloatArray, FloatArray, FloatArray]:
        r = float(np.linalg.norm(r_vec))
        s, t, u = r_vec / r
        # Re y Im de (s + i t)^m para m = 0 … N
        z = (s + 1j * t) ** self._m
        return r, np.real(z), np.imag(z), np.array([u])

    def potential(self, r_vec: FloatArray) -> float:
        """U [m²/s²] (positivo, convenio geodésico: a = ∇U)."""
        r, re, im, (u,) = self._terms(r_vec)
        k = self.n_max + 1
        a_nm = helmholtz_polynomials(u, self.n_max)[:k, :k]
        rho = (self.radius / r) ** self._n
        inner = np.sum(a_nm * (self.c * re + self.s * im), axis=1)
        return float(self.gm / r * np.dot(rho, inner))

    def acceleration(self, r_vec: FloatArray) -> FloatArray:
        """∇U [m/s²], válido en cualquier dirección (incluidos los polos)."""
        r, re, im, (u,) = self._terms(r_vec)
        s, t = r_vec[0] / r, r_vec[1] / r
        k = self.n_max + 1
        full = helmholtz_polynomials(u, self.n_max)
        _, _, _, deriv = _recurrence_coefficients(self.n_max)
        a_nm = full[:k, :k]
        da_nm = deriv[:k, :k] * full[:k, 1 : k + 1]  # dĀ_nm/du = d_nm Ā_{n,m+1}

        # (s + i t)^{m−1} con m (el término m = 0 no contribuye)
        re_prev = np.concatenate([[0.0], re[:-1]])
        im_prev = np.concatenate([[0.0], im[:-1]])
        m = self._m
        rho = (self.radius / r) ** self._n
        scale = self.gm / r

        d_nm = self.c * re + self.s * im
        u_r = -scale / r * np.dot(rho * (self._n + 1.0), np.sum(a_nm * d_nm, axis=1))
        u_u = scale * np.dot(rho, np.sum(da_nm * d_nm, axis=1))
        u_s = scale * np.dot(rho, np.sum(a_nm * m * (self.c * re_prev + self.s * im_prev), axis=1))
        u_t = scale * np.dot(rho, np.sum(a_nm * m * (self.s * re_prev - self.c * im_prev), axis=1))

        e_r = np.array([s, t, u])
        radial = u_r - (s * u_s + t * u_t + u * u_u) / r
        return np.asarray(np.array([u_s, u_t, u_u]) / r + radial * e_r, dtype=np.float64)
