"""Pruebas de las correcciones físicas de la revisión (balance de masa, Cd(M), CR3BP)."""

import numpy as np
import pytest
from scipy.integrate import quad

from artemis_sim.ascent_solver import (
    AscentConfig,
    AscentPhase,
    initial_state_on_pad,
    make_ascent_derivatives,
    make_core_burnout_event,
    make_srb_burnout_event,
    simulate_full_ascent,
    srb_thrust_fraction,
    srb_thrust_scale,
)
from artemis_sim.constants import EARTH, G0_M_S2, MOON
from artemis_sim.ephemeris import DEFAULT_LUNAR_CONFIG
from artemis_sim.physics_engine import (
    compute_atmospheric_temperature,
    compute_drag_coefficient,
    compute_speed_of_sound,
)
from artemis_sim.state import ArtemisState
from artemis_sim.symplectic_solver import (
    circular_orbit_state,
    compute_jacobi_constant,
    compute_system_energy,
    propagate_rk4,
    propagate_verlet,
)


class TestSrbMassBalance:
    def test_srb_burn_consumes_exactly_its_propellant(self) -> None:
        """La integral del flujo másico de los SRB debe igualar su masa de propelente."""
        cfg = AscentConfig()
        k = srb_thrust_scale(cfg.srb_spec, cfg.t_burn_srb_s)
        m_dot_peak = k * cfg.srb_spec.thrust_vac_n / (cfg.srb_spec.isp_vac_s * G0_M_S2)
        burned, _ = quad(
            lambda t: m_dot_peak * srb_thrust_fraction(t, cfg.t_burn_srb_s),
            0.0,
            cfg.t_burn_srb_s,
            limit=200,
        )
        assert burned == pytest.approx(cfg.srb_spec.propellant_mass_kg, rel=1e-6)
        # Coherencia de datos: el pico nominal (16 MN) apenas requiere reescalado
        assert 0.95 < k < 1.05

    def test_srb_thrust_zero_after_burnout(self) -> None:
        assert srb_thrust_fraction(126.0, 126.0) == 0.0
        assert srb_thrust_fraction(-1.0, 126.0) == 0.0
        assert srb_thrust_fraction(5.0, 126.0) == 1.0

    def test_event_factories_use_config(self) -> None:
        cfg = AscentConfig(t_burn_srb_s=100.0, upper_mass_kg=150_000.0, phase=AscentPhase.CORE_ONLY)
        ev_srb = make_srb_burnout_event(cfg)
        ev_core = make_core_burnout_event(cfg)
        y = np.zeros(7)
        assert ev_srb(100.0, y) == 0.0
        y[6] = cfg.core_spec.dry_mass_kg + 150_000.0
        assert ev_core(0.0, y) == 0.0

    def test_full_ascent_reaches_meco(self) -> None:
        """Ascenso nominal: separación SRB a 126 s, MECO por agotamiento, h ≈ 160 km."""
        res = simulate_full_ascent()
        assert res.meco_reached
        assert res.t_srb_separation_s == pytest.approx(126.0)
        cfg = AscentConfig(phase=AscentPhase.CORE_ONLY)
        assert res.y[6, -1] == pytest.approx(cfg.cutoff_mass_kg, rel=1e-6)
        alt = np.linalg.norm(res.y[0:3, -1]) - EARTH.equatorial_radius_m
        assert 140e3 < alt < 180e3
        assert np.all(np.diff(res.t) >= 0.0)

    def test_mass_monotonic_during_ascent(self) -> None:
        cfg = AscentConfig()
        f = make_ascent_derivatives(cfg)
        y0 = initial_state_on_pad(28.627, -80.621, cfg).to_array()
        for t in [0.0, 50.0, 110.0, 125.9]:
            assert f(t, y0)[6] < 0.0


class TestAtmosphere:
    def test_us76_temperature_layers(self) -> None:
        assert compute_atmospheric_temperature(0.0) == pytest.approx(288.15)
        assert compute_atmospheric_temperature(11_000.0) == pytest.approx(216.65)
        assert compute_atmospheric_temperature(15_000.0) == pytest.approx(216.65)
        assert compute_atmospheric_temperature(-50.0) == pytest.approx(288.15)

    def test_speed_of_sound_sea_level(self) -> None:
        assert compute_speed_of_sound(0.0) == pytest.approx(340.29, abs=0.1)

    def test_drag_coefficient_transonic_peak(self) -> None:
        cd_sub = compute_drag_coefficient(0.5)
        cd_trans = compute_drag_coefficient(1.05)
        cd_sup = compute_drag_coefficient(4.0)
        assert cd_trans > cd_sub
        assert cd_trans > cd_sup


class TestCR3BP:
    def test_mean_motion_is_keplerian(self) -> None:
        d = DEFAULT_LUNAR_CONFIG.orbital_radius_m
        n = DEFAULT_LUNAR_CONFIG.mean_motion_rad_s
        assert n**2 * d**3 == pytest.approx(EARTH.mu_m3_s2 + MOON.mu_m3_s2, rel=1e-12)

    def test_jacobi_conserved_with_moon(self) -> None:
        """La integral de Jacobi se conserva con Verlet aunque la energía geocéntrica no."""
        st0 = ArtemisState(position=[2.0e8, 0.0, 0.0], velocity=[0.0, 1300.0, 50.0], mass=1.0)
        traj = propagate_verlet(st0, 5 * 86400.0, dt=30.0, sample_every=100)
        ej = np.array([compute_jacobi_constant(s) for s in traj])
        en = np.array([compute_system_energy(s, s.t) for s in traj])
        jac_var = np.max(np.abs(ej - ej[0])) / abs(ej[0])
        en_var = np.max(np.abs(en - en[0])) / abs(en[0])
        assert jac_var < 1e-6
        assert en_var > 100.0 * jac_var

    def test_rk4_drift_vs_verlet_bounded(self) -> None:
        """Con paso grueso, la energía RK4 deriva secularmente; la de Verlet queda acotada."""
        st = circular_orbit_state(7.0e6)
        period = 2.0 * np.pi * np.sqrt(7.0e6**3 / EARTH.mu_m3_s2)
        dt = period / 60.0
        e0 = compute_system_energy(st, 0.0, include_moon=False)
        rk = propagate_rk4(st, 40 * period, dt, include_moon=False)
        vv = propagate_verlet(st, 40 * period, dt, include_moon=False)
        err_rk = [abs(compute_system_energy(s, s.t, include_moon=False) / e0 - 1) for s in rk]
        err_vv = [abs(compute_system_energy(s, s.t, include_moon=False) / e0 - 1) for s in vv]
        half = len(err_rk) // 2
        # RK4: el error crece (deriva); Verlet: el máximo de la 2a mitad ≈ el de la 1a mitad
        assert err_rk[-1] > 1.5 * max(err_rk[:half // 2])
        assert max(err_vv[half:]) < 2.0 * max(err_vv[:half])
