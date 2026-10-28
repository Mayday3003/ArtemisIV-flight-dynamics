"""Pruebas de las órbitas de halo y la NRHO 9:2 (Etapa 3)."""

import numpy as np
import pytest

from artemis_sim.cr3bp import propagate
from artemis_sim.periodic_orbits import (
    SEED_NRHO,
    PeriodicOrbit,
    continue_family,
    correct_halo,
    find_nrho,
    perilune_altitude_m,
)


@pytest.fixture(scope="module")
def nrho() -> PeriodicOrbit:
    return find_nrho()


class TestCorrection:
    def test_corrected_halo_closes(self) -> None:
        """|x(T) − x(0)| < 1e-9 tras un periodo completo."""
        orbit = correct_halo(SEED_NRHO)
        end = propagate(orbit.state0, orbit.period).states[:, -1]
        assert np.max(np.abs(end - orbit.state0)) < 1e-9

    def test_rejects_unknown_parameter(self) -> None:
        with pytest.raises(ValueError):
            correct_halo(SEED_NRHO, fixed="y")


class TestNrho:
    def test_period_is_9_to_2_resonance(self, nrho: PeriodicOrbit) -> None:
        assert nrho.period_days == pytest.approx(6.56, abs=0.01)

    def test_perilune_and_apolune(self, nrho: PeriodicOrbit) -> None:
        """Gateway: perilunio ≈ 3 000–3 500 km del centro lunar, apolunio ≈ 70 000 km."""
        peri, apo = nrho.moon_distance_range_m()
        assert 3.0e6 < peri < 3.5e6
        assert 6.5e7 < apo < 7.5e7
        assert perilune_altitude_m(nrho) > 1.0e6  # más de 1 000 km sobre la superficie

    def test_southern_family(self, nrho: PeriodicOrbit) -> None:
        """Familia sur: el apolunio queda bajo el plano de la órbita lunar (z < 0)."""
        assert nrho.state0[2] < 0.0

    def test_nearly_stable(self, nrho: PeriodicOrbit) -> None:
        assert 1.0 <= nrho.stability_index < 2.0

    def test_monodromy_is_volume_preserving(self, nrho: PeriodicOrbit) -> None:
        """div(f) = 0 ⇒ det Φ(T) = 1, y los autovalores vienen en pares (λ, 1/λ)."""
        assert np.linalg.det(nrho.monodromy) == pytest.approx(1.0, abs=1e-8)
        lam = np.sort(np.abs(nrho.eigenvalues))
        assert lam[0] * lam[-1] == pytest.approx(1.0, abs=1e-6)


class TestFamily:
    def test_continuation_toward_l2_increases_period(self, nrho: PeriodicOrbit) -> None:
        family = continue_family(nrho, 0.01, 4, parameter="x")
        assert len(family) == 5
        periods = [o.period_days for o in family]
        assert all(b > a for a, b in zip(periods, periods[1:], strict=False))
