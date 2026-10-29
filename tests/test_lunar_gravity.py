"""Pruebas del campo gravitatorio lunar GRGM1200A y del marco fijo a la Luna (Etapa 5)."""

from math import factorial

import numpy as np
import pytest
from scipy.integrate import solve_ivp
from scipy.special import lpmv

from artemis_sim.cr3bp import MU, UNITS
from artemis_sim.ephemeris import LunarOrbitConfig
from artemis_sim.lunar_gravity import LunarGravityField, helmholtz_polynomials
from artemis_sim.moon_frame import (
    eci_to_moon_fixed,
    latitude_longitude_deg,
    moon_fixed_to_eci,
    rotating_to_moon_fixed,
    surface_point,
)


@pytest.fixture(scope="module")
def field() -> LunarGravityField:
    return LunarGravityField.grgm1200a()


def numerical_gradient(f: LunarGravityField, r: np.ndarray, h: float = 1.0) -> np.ndarray:
    return np.array(
        [(f.potential(r + h * e) - f.potential(r - h * e)) / (2 * h) for e in np.eye(3)]
    )


class TestLegendre:
    @pytest.mark.parametrize("u", [-0.999, -0.4, 0.0, 0.3, 0.95])
    def test_normalized_legendre_match_scipy(self, u: float) -> None:
        """Ā_nm(u) cosᵐφ = P̄_nm(u); scipy usa la fase de Condon–Shortley (−1)ᵐ."""
        a = helmholtz_polynomials(u, 20)
        for n in range(21):
            for m in range(n + 1):
                norm = np.sqrt((2 - (m == 0)) * (2 * n + 1) * factorial(n - m) / factorial(n + m))
                ref = norm * (-1) ** m * lpmv(m, n, u)
                assert a[n, m] * (1 - u * u) ** (m / 2) == pytest.approx(ref, abs=1e-12)

    def test_recurrence_is_stable_at_high_degree(self) -> None:
        """Con la normalización completa los valores quedan acotados (no hay desbordes)."""
        a = helmholtz_polynomials(0.2, 100)
        assert np.all(np.isfinite(a))
        assert np.max(np.abs(a)) < 1e60  # sin normalizar, (2n−1)!! ~ 10^158 en n = 100


class TestPotential:
    def test_degree_zero_is_point_mass(self, field: LunarGravityField) -> None:
        f0 = LunarGravityField.grgm1200a(n_max=0)
        r = np.array([1.2e6, -0.9e6, 1.1e6])
        rn = np.linalg.norm(r)
        assert f0.potential(r) == pytest.approx(field.gm / rn, rel=1e-14)
        np.testing.assert_allclose(f0.acceleration(r), -field.gm * r / rn**3, rtol=1e-13)

    def test_j2_only_matches_analytic_formula(self, field: LunarGravityField) -> None:
        c = np.zeros((3, 3))
        c[0, 0], c[2, 0] = 1.0, field.c[2, 0]
        f = LunarGravityField(c, np.zeros((3, 3)), field.gm, field.radius)
        x, y, z = r = np.array([1.5e6, 0.7e6, -1.0e6])
        rn = np.linalg.norm(r)
        k = 1.5 * f.j2 * field.gm * field.radius**2 / rn**5
        zz = 5 * z**2 / rn**2
        ref = -field.gm * r / rn**3 - k * np.array([x * (1 - zz), y * (1 - zz), z * (3 - zz)])
        np.testing.assert_allclose(f.acceleration(r), ref, rtol=1e-12)
        assert f.j2 == pytest.approx(2.03e-4, rel=0.01)  # J₂ lunar publicado ≈ 2,03·10⁻⁴

    @pytest.mark.parametrize(
        "r",
        [
            np.array([1.75e6, 2e5, 3e5]),
            np.array([0.0, 0.0, -1.76e6]),  # justo sobre el polo sur: φ = −90°
            np.array([0.0, 0.0, 1.80e6]),  # polo norte
            np.array([1e-3, -2e-3, -1.76e6]),  # pegado al polo
        ],
    )
    def test_gradient_matches_finite_differences(
        self, field: LunarGravityField, r: np.ndarray
    ) -> None:
        a = field.acceleration(r)
        assert np.all(np.isfinite(a))
        np.testing.assert_allclose(a, numerical_gradient(field, r), atol=1e-8)

    def test_mascons_deform_a_low_orbit(self, field: LunarGravityField) -> None:
        """Órbita polar de 100 km, una vuelta (~2 h): grado 100 frente a solo J₂.
        Resultado de referencia: ~2,2 km (2,6 km frente a masa puntual)."""
        j2 = LunarGravityField.grgm1200a(n_max=2)
        r0 = field.radius + 100e3
        period = 2 * np.pi * np.sqrt(r0**3 / field.gm)
        y0 = np.array([r0, 0.0, 0.0, 0.0, 0.0, np.sqrt(field.gm / r0)])

        def run(f: LunarGravityField) -> np.ndarray:
            sol = solve_ivp(
                lambda _t, y: np.concatenate([y[3:], f.acceleration(y[:3])]),
                (0.0, period), y0, method="DOP853", rtol=1e-11, atol=1e-4,
                t_eval=np.linspace(0.0, period, 500),
            )  # fmt: skip
            return sol.y[0:3]

        dev = np.max(np.linalg.norm(run(field) - run(j2), axis=0))
        assert 500.0 < dev < 10_000.0


class TestMoonFrame:
    def test_round_trip_through_eci(self) -> None:
        cfg = LunarOrbitConfig(inclination_rad=0.5, raan_rad=1.1, initial_phase_rad=0.3)
        x = np.array([1.2e6, -3e5, -1.5e6, 250.0, 1400.0, -30.0])
        st = moon_fixed_to_eci(x, 7.3e5, cfg)
        np.testing.assert_allclose(eci_to_moon_fixed(st, cfg), x, rtol=1e-10, atol=1e-6)

    def test_moon_center_and_earth_direction(self) -> None:
        """El origen del MF es el centro de la Luna y +x apunta a la Tierra."""
        center = rotating_to_moon_fixed(np.array([1.0 - MU, 0.0, 0.0, 0.0, 0.0, 0.0]))
        np.testing.assert_allclose(center, 0.0, atol=1e-6)
        earth = rotating_to_moon_fixed(np.array([-MU, 0.0, 0.0, 0.0, 0.0, 0.0]))
        np.testing.assert_allclose(earth[0:3], [UNITS.length_m, 0.0, 0.0], atol=1e-6)

    def test_latitude_longitude(self) -> None:
        p = surface_point(-86.8, 179.0, 1.7374e6)
        lat, lon = latitude_longitude_deg(p)
        assert lat == pytest.approx(-86.8) and lon == pytest.approx(179.0)
