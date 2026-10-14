"""Pruebas unitarias para el modelo de efemérides analíticas de Artemis IV."""

import numpy as np
import pytest

from artemis_sim.constants import EARTH, MOON, CelestialBody
from artemis_sim.ephemeris import (
    DEFAULT_LUNAR_CONFIG,
    LunarOrbitConfig,
    get_body_position,
    get_body_velocity,
)


class TestEphemeris:
    """Conjunto de pruebas para efemérides terrestres y lunares."""

    def test_lunar_orbit_radius_constancy(self) -> None:
        """Verifica que |r_Luna| = 384_400_000 m (rtol 1e-12) para varios instantes de tiempo."""
        d_expected = DEFAULT_LUNAR_CONFIG.orbital_radius_m
        times = [0.0, 100.0, 3600.0, 86400.0, 1e6, 2.36e6]

        for t in times:
            pos = get_body_position(MOON, t)
            r_norm = float(np.linalg.norm(pos))
            assert pytest.approx(r_norm, rel=1e-12) == d_expected
            assert pos[2] == 0.0  # Plano XY coplanar

    def test_lunar_period_and_periodicity(self) -> None:
        """Verifica que el periodo sidéreo T=2*pi/w esté entre 27.2 y 27.4 días y r(T) == r(0)."""
        w = DEFAULT_LUNAR_CONFIG.mean_motion_rad_s
        period_s = 2.0 * np.pi / w
        period_days = period_s / 86400.0

        assert 27.2 <= period_days <= 27.4

        pos_0 = get_body_position(MOON, 0.0)
        pos_t = get_body_position(MOON, period_s)
        assert np.allclose(pos_0, pos_t, rtol=1e-12, atol=1e-4)

    def test_lunar_velocity_matches_numerical_derivative(self) -> None:
        """Verifica que get_body_velocity coincida con la derivada numérica de la posición."""
        times = [100.0, 45000.0, 500000.0]
        dt = 0.1  # paso para diferencias finitas centrales

        for t in times:
            vel_analytic = get_body_velocity(MOON, t)
            pos_plus = get_body_position(MOON, t + dt)
            pos_minus = get_body_position(MOON, t - dt)
            vel_numeric = (pos_plus - pos_minus) / (2.0 * dt)

            # Error relativo muy estricto (< 1e-8)
            assert np.allclose(vel_analytic, vel_numeric, rtol=1e-8, atol=1e-6)

    def test_earth_position_and_velocity(self) -> None:
        """Verifica que la Tierra esté fija en el origen inercial ECI."""
        assert np.allclose(get_body_position(EARTH, 1000.0), [0.0, 0.0, 0.0])
        assert np.allclose(get_body_velocity(EARTH, 1000.0), [0.0, 0.0, 0.0])

    def test_unknown_body_raises_value_error(self) -> None:
        """Verifica que un cuerpo celeste desconocido lance ValueError."""
        mars = CelestialBody(
            name="Mars",
            mu_m3_s2=4.282837e13,
            mass_kg=6.4171e23,
            equatorial_radius_m=3396200.0,
        )
        with pytest.raises(ValueError, match="Cuerpo celeste desconocido"):
            get_body_position(mars, 0.0)

        with pytest.raises(ValueError, match="Cuerpo celeste desconocido"):
            get_body_velocity(mars, 0.0)

    def test_config_validation(self) -> None:
        """Verifica la validación de magnitudes positivas en LunarOrbitConfig."""
        with pytest.raises(ValueError, match="El radio orbital debe ser positivo"):
            LunarOrbitConfig(orbital_radius_m=-100.0)

        with pytest.raises(ValueError, match="La velocidad angular debe ser positiva"):
            LunarOrbitConfig(mean_motion_rad_s=0.0)
