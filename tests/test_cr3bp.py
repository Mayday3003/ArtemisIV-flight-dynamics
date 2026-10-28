"""Pruebas del CR3BP adimensional (Etapa 3)."""

import math

import numpy as np
import pytest

from artemis_sim.cr3bp import (
    MU,
    UNITS,
    eci_to_rotating,
    jacobi_constant,
    lagrange_points,
    propagate,
    pseudo_potential_gradient,
    pseudo_potential_hessian,
    rotating_to_eci,
)
from artemis_sim.ephemeris import LunarOrbitConfig
from artemis_sim.symplectic_solver import compute_jacobi_constant

STATE = np.array([1.05, 0.02, -0.15, 0.01, -0.12, 0.03])
CFG = LunarOrbitConfig(inclination_rad=math.radians(28.6), raan_rad=1.0, initial_phase_rad=0.3)


class TestLagrangePoints:
    def test_collinear_points_match_published_values(self) -> None:
        """Tabla de NASA/JPL (mu = 0,012151): x_L1 = 0,83692, x_L2 = 1,15568.

        Nuestro mu (DE421 + WGS84) es 0,012156, por eso se compara a 1e-3.
        """
        lp = lagrange_points()
        assert lp["L1"][0] == pytest.approx(0.8369, abs=1e-3)
        assert lp["L2"][0] == pytest.approx(1.1557, abs=1e-3)
        assert lp["L3"][0] == pytest.approx(-1.0051, abs=1e-3)

    def test_gradient_vanishes_at_all_points(self) -> None:
        for name, r in lagrange_points().items():
            assert np.linalg.norm(pseudo_potential_gradient(r)) < 1e-12, name


class TestDerivatives:
    def test_hessian_matches_finite_differences(self) -> None:
        h = 1e-6
        num = np.column_stack(
            [
                (pseudo_potential_gradient(STATE[0:3] + h * e)
                 - pseudo_potential_gradient(STATE[0:3] - h * e)) / (2 * h)
                for e in np.eye(3)
            ]
        )  # fmt: skip
        assert np.allclose(pseudo_potential_hessian(STATE[0:3]), num, atol=1e-7)

    def test_stm_matches_finite_differences(self) -> None:
        """La STM integrada con DOP853 coincide con diferencias centrales (< 1e-6)."""
        tf = 1.0
        stm = propagate(STATE, tf, with_stm=True).stm
        assert stm is not None
        h = 1e-7
        num = np.empty((6, 6))
        for j in range(6):
            e = np.zeros(6)
            e[j] = h
            plus = propagate(STATE + e, tf).states[:, -1]
            minus = propagate(STATE - e, tf).states[:, -1]
            num[:, j] = (plus - minus) / (2 * h)
        assert np.max(np.abs(stm - num)) < 1e-6

    def test_jacobi_is_conserved(self) -> None:
        traj = propagate(STATE, 3.0, dense_points=50).states
        c = np.array([jacobi_constant(traj[:, i]) for i in range(traj.shape[1])])
        assert np.max(np.abs(c - c[0])) < 1e-10


class TestConversion:
    def test_roundtrip_eci(self) -> None:
        st = rotating_to_eci(STATE, 12345.0, CFG)
        assert np.allclose(eci_to_rotating(st, CFG), STATE, atol=1e-13)

    def test_moon_maps_to_moon(self) -> None:
        from artemis_sim.constants import MOON
        from artemis_sim.ephemeris import get_body_position

        st = rotating_to_eci(np.array([1.0 - MU, 0, 0, 0, 0, 0]), 5e4, CFG)
        assert np.allclose(st.position, get_body_position(MOON, 5e4, CFG), atol=1e-3)

    def test_jacobi_matches_geocentric_model(self) -> None:
        """Mismo modelo, otras coordenadas: E_J = −(L n)² C / 2."""
        st = rotating_to_eci(STATE, 7.7e4, CFG)
        e_j = compute_jacobi_constant(st, CFG)
        c_from_geo = -2.0 * e_j / UNITS.velocity_m_s**2
        assert c_from_geo == pytest.approx(jacobi_constant(STATE), rel=1e-11)
