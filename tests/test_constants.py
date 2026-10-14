"""Pruebas unitarias para el motor de constantes físicas de Artemis IV."""

from dataclasses import FrozenInstanceError

import pytest

from artemis_sim.constants import (
    EARTH,
    EARTH_ROTATION,
    G0_M_S2,
    MOON,
    SLS_B1B_CORE_STAGE,
    SLS_B1B_EUS,
    SLS_B1B_SRB_PAIR,
    SLS_B1B_SRB_SINGLE,
    CelestialBody,
    EarthRotation,
    StageSpec,
)


class TestCelestialBodies:
    """Pruebas para dataclass CelestialBody e instancias astronómicas."""

    def test_earth_constants_and_physics_consistency(self) -> None:
        """Verifica la aceleración superficial gravitacional de la Tierra."""
        # g_superficie = mu / r^2 ≈ 9.798 - 9.82 m/s^2
        g_surface = EARTH.mu_m3_s2 / (EARTH.equatorial_radius_m**2)
        assert pytest.approx(g_surface, rel=1e-2) == 9.80

    def test_moon_constants_and_physics_consistency(self) -> None:
        """Verifica la aceleración superficial gravitacional lunar."""
        # g_luna = mu / r^2 ≈ 1.62 m/s^2
        g_moon = MOON.mu_m3_s2 / (MOON.equatorial_radius_m**2)
        assert pytest.approx(g_moon, rel=1e-2) == 1.62

    def test_immutability(self) -> None:
        """Verifica que las instancias de CelestialBody sean inmutables (frozen)."""
        with pytest.raises(FrozenInstanceError):
            setattr(EARTH, "mu_m3_s2", 1.0)

    def test_validation_invalid_values(self) -> None:
        """Verifica que valores no positivos o nombres vacíos lancen ValueError."""
        with pytest.raises(ValueError, match="El nombre del cuerpo celeste no puede estar vacío"):
            CelestialBody(name="", mu_m3_s2=1.0, mass_kg=1.0, equatorial_radius_m=1.0)

        with pytest.raises(ValueError, match="parámetro gravitacional mu debe ser positivo"):
            CelestialBody(name="Mars", mu_m3_s2=-1.0, mass_kg=1.0, equatorial_radius_m=1.0)

        with pytest.raises(ValueError, match="masa debe ser positiva"):
            CelestialBody(name="Mars", mu_m3_s2=1.0, mass_kg=0.0, equatorial_radius_m=1.0)

        with pytest.raises(ValueError, match="radio ecuatorial debe ser positivo"):
            CelestialBody(name="Mars", mu_m3_s2=1.0, mass_kg=1.0, equatorial_radius_m=-100.0)


class TestEarthRotation:
    """Pruebas para EarthRotation."""

    def test_default_rotation_value(self) -> None:
        assert pytest.approx(EARTH_ROTATION.omega_rad_s, rel=1e-6) == 7.2921150e-5

    def test_immutability(self) -> None:
        with pytest.raises(FrozenInstanceError):
            setattr(EARTH_ROTATION, "omega_rad_s", 0.0)

    def test_validation(self) -> None:
        with pytest.raises(ValueError, match="velocidad angular debe ser positiva"):
            EarthRotation(omega_rad_s=-1.0)


class TestStageSpec:
    """Pruebas para StageSpec y etapas de SLS Block 1B."""

    def test_stage_physics_consistency(self) -> None:
        """Verifica que m_dot * Isp * g0 sea exactamente igual al empuje en vacío."""
        stages = [
            SLS_B1B_CORE_STAGE,
            SLS_B1B_SRB_SINGLE,
            SLS_B1B_SRB_PAIR,
            SLS_B1B_EUS,
        ]
        for stage in stages:
            recomputed_thrust = stage.mass_flow_rate_kg_s * stage.isp_vac_s * G0_M_S2
            assert pytest.approx(recomputed_thrust, rel=1e-9) == stage.thrust_vac_n
            assert stage.total_mass_kg == stage.dry_mass_kg + stage.propellant_mass_kg

    def test_stage_immutability(self) -> None:
        with pytest.raises(FrozenInstanceError):
            setattr(SLS_B1B_CORE_STAGE, "dry_mass_kg", 50000.0)

    def test_stage_validation_invalid_values(self) -> None:
        with pytest.raises(ValueError, match="nombre de la etapa no puede estar vacío"):
            StageSpec(
                name="",
                dry_mass_kg=100.0,
                propellant_mass_kg=1000.0,
                thrust_vac_n=5000.0,
                isp_vac_s=300.0,
            )

        with pytest.raises(ValueError, match="masa en seco debe ser positiva"):
            StageSpec(
                name="TestStage",
                dry_mass_kg=-10.0,
                propellant_mass_kg=1000.0,
                thrust_vac_n=5000.0,
                isp_vac_s=300.0,
            )

        with pytest.raises(ValueError, match="masa de propelente debe ser positiva"):
            StageSpec(
                name="TestStage",
                dry_mass_kg=100.0,
                propellant_mass_kg=0.0,
                thrust_vac_n=5000.0,
                isp_vac_s=300.0,
            )

        with pytest.raises(ValueError, match="empuje en vacío debe ser positivo"):
            StageSpec(
                name="TestStage",
                dry_mass_kg=100.0,
                propellant_mass_kg=1000.0,
                thrust_vac_n=0.0,
                isp_vac_s=300.0,
            )

        with pytest.raises(ValueError, match="Isp en vacío debe ser positivo"):
            StageSpec(
                name="TestStage",
                dry_mass_kg=100.0,
                propellant_mass_kg=1000.0,
                thrust_vac_n=5000.0,
                isp_vac_s=-20.0,
            )

        with pytest.raises(ValueError, match="empuje a nivel del mar debe ser positivo"):
            StageSpec(
                name="TestStage",
                dry_mass_kg=100.0,
                propellant_mass_kg=1000.0,
                thrust_vac_n=5000.0,
                isp_vac_s=300.0,
                thrust_sea_level_n=-1.0,
            )
