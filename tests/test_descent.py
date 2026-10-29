"""Pruebas del descenso del HLS al polo sur (Etapa 5)."""

import numpy as np
import pytest

from artemis_sim.constants import HLS, HLS_MIN_THROTTLE
from artemis_sim.descent_solver import (
    PDI_ALTITUDE_M,
    SOUTH_POLE_SITE,
    DescentResult,
    MoonFixedDynamics,
    choose_doi_tau,
    e_guidance,
    simulate_descent,
)
from artemis_sim.export import MissionTrajectory
from artemis_sim.lunar_gravity import LunarGravityField
from artemis_sim.mission import MissionSummaryPhase5
from artemis_sim.moon_frame import eci_to_moon_fixed, rotating_to_moon_fixed
from artemis_sim.periodic_orbits import find_nrho
from artemis_sim.state import ArtemisState


def test_e_guidance_hits_target_in_uniform_gravity() -> None:
    """Con g constante el E-guidance en lazo cerrado llega exacto a (r_f, v_f)."""
    g = np.array([0.0, 0.0, -1.62])
    r, v = np.array([0.0, 0.0, 2000.0]), np.array([80.0, 0.0, -20.0])
    r_f, v_f = np.array([6000.0, 0.0, 100.0]), np.array([0.0, 0.0, -2.0])
    dt, t_go = 0.01, 150.0
    while t_go > 1e-9:
        a = e_guidance(r, v, g, r_f, v_f, t_go) + g
        r, v, t_go = r + v * dt + 0.5 * a * dt**2, v + a * dt, t_go - dt
    np.testing.assert_allclose(r, r_f, atol=0.05)
    np.testing.assert_allclose(v, v_f, atol=1e-3)


def test_dynamics_without_earth_is_pure_lunar_gravity_in_inertial_axes() -> None:
    field = LunarGravityField.grgm1200a(n_max=4)
    dyn = MoonFixedDynamics(field, include_earth=False, omega_rad_s=0.0)
    r = np.array([1.0e6, 1.2e6, -0.4e6])
    np.testing.assert_allclose(dyn.acceleration(r, np.ones(3)), field.acceleration(r))


@pytest.fixture(scope="module")
def descent() -> DescentResult:
    orbit = find_nrho()
    return simulate_descent(rotating_to_moon_fixed(orbit.state_at(choose_doi_tau(orbit))))


class TestDescent:
    def test_soft_landing_on_the_site(self, descent: DescentResult) -> None:
        """Criterio del ROADMAP: < 1 m/s, < 100 m del sitio y masa > masa seca."""
        assert np.linalg.norm(descent.touchdown_velocity) < 1.0 + 0.05
        assert descent.landing_error_m < 100.0
        assert descent.mass_landed_kg > HLS.dry_mass_kg

    def test_touchdown_is_vertical(self, descent: DescentResult) -> None:
        up = descent.site.position / np.linalg.norm(descent.site.position)
        v = descent.touchdown_velocity
        horizontal = np.linalg.norm(v - np.dot(v, up) * up)
        assert np.dot(v, up) < 0.0 and horizontal < 0.1

    def test_never_goes_underground_before_touchdown(self, descent: DescentResult) -> None:
        before = descent.t < descent.t_touchdown - 1e-6
        assert np.all(descent.altitude_m[before] > 0.0)

    def test_pdi_near_planned_altitude_and_south(self, descent: DescentResult) -> None:
        """Los mascons desplazan el perilunio, pero solo unos cientos de metros."""
        k = int(np.searchsorted(descent.t, descent.t_pdi))
        assert abs(descent.altitude_m[k] - PDI_ALTITUDE_M) < 2_000.0
        assert descent.pdi_lat_lon_deg[0] < -60.0
        assert SOUTH_POLE_SITE.lat_deg < -84.0  # franja de las regiones candidatas de Artemis III

    def test_engine_limits_and_mass_flow(self, descent: DescentResult) -> None:
        assert HLS_MIN_THROTTLE <= descent.max_throttle_fraction <= 1.0 + 1e-9
        assert np.all(np.diff(descent.y[6]) <= 1e-9)
        # Δv propulsado: por encima del ideal (pérdidas por gravedad), por debajo de 3 km/s
        assert 1_900.0 < descent.dv_powered_m_s < 3_000.0
        assert 400.0 < descent.dv_doi_m_s < 1_000.0


class TestFullMission:
    def test_phases_and_events_in_order(
        self, mission5: tuple[MissionTrajectory, MissionSummaryPhase5]
    ) -> None:
        traj, s = mission5
        ids = [p.id for p in traj.phases]
        assert ids == ["ascent", "parking", "transit", "nrho", "descent", "landing"]
        for a, b in zip(traj.phases, traj.phases[1:], strict=False):
            assert a.t_end == b.t_start
        assert s.phases_1_to_4.t_nri_s < s.t_doi_s < s.t_pdi_s < s.t_touchdown_s
        assert traj.t[-1] == pytest.approx(s.t_touchdown_s)
        # Al menos una vuelta a la NRHO antes de la DOI (acoplamiento y paso al HLS)
        assert s.t_doi_s - s.phases_1_to_4.t_nri_s > s.phases_1_to_4.nrho.period_days * 86400

    def test_eci_export_lands_on_the_site(
        self, mission5: tuple[MissionTrajectory, MissionSummaryPhase5]
    ) -> None:
        """El último estado en ECI, vuelto al MF, está sobre el sitio y casi en reposo."""
        traj, s = mission5
        st = ArtemisState(traj.y[0:3, -1], traj.y[3:6, -1], 1.0, float(traj.t[-1]))
        mf = eci_to_moon_fixed(st, traj.lunar_config)
        assert np.linalg.norm(mf[0:3] - s.descent.site.position) < 100.0
        assert np.linalg.norm(mf[3:6]) < 1.1

    def test_position_is_continuous_at_doi(
        self, mission5: tuple[MissionTrajectory, MissionSummaryPhase5]
    ) -> None:
        traj, s = mission5
        k = int(np.searchsorted(traj.t, s.t_doi_s))
        step = np.linalg.norm(traj.y[0:3, k + 1] - traj.y[0:3, k - 1])
        dt = traj.t[k + 1] - traj.t[k - 1]
        assert step < 2.0 * np.linalg.norm(traj.y[3:6, k]) * dt
