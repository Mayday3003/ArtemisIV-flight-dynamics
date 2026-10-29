"""Pruebas unitarias para el motor de física pura de Artemis IV."""

import numpy as np
import numpy.typing as npt
import pytest
from scipy.integrate import solve_ivp

from artemis_sim.constants import EARTH, EARTH_ROTATION, G0_M_S2
from artemis_sim.physics_engine import (
    P0_PA,
    RHO0_KG_M3,
    compute_aerodynamic_drag,
    compute_altitude,
    compute_atmospheric_density,
    compute_atmospheric_pressure,
    compute_coriolis_centrifugal_accel,
    compute_gravity,
    compute_mass_flow,
    compute_relative_velocity,
    compute_thrust,
)


class TestPhysicsEngine:
    """Verificación de funciones físicas puras."""

    @pytest.mark.parametrize(
        ("h_m", "p_pa", "rho_kg_m3"),
        [  # Tabla oficial de la US Standard Atmosphere 1976 (altitud geopotencial)
            (0.0, 101_325.0, 1.2250),
            (11_000.0, 22_632.1, 0.36392),
            (20_000.0, 5_474.89, 0.088035),
            (32_000.0, 868.019, 0.013225),
            (47_000.0, 110.906, 0.0014275),
            (71_000.0, 3.95642, 6.4211e-5),
        ],
    )
    def test_us76_pressure_and_density(self, h_m: float, p_pa: float, rho_kg_m3: float) -> None:
        assert compute_atmospheric_pressure(h_m) == pytest.approx(p_pa, rel=2e-5)
        assert compute_atmospheric_density(h_m) == pytest.approx(rho_kg_m3, rel=2e-4)

    def test_atmosphere_saturates_below_sea_level(self) -> None:
        assert compute_atmospheric_density(-100.0) == pytest.approx(RHO0_KG_M3, rel=1e-6)
        assert compute_atmospheric_pressure(-50.0) == P0_PA

    def test_atmosphere_is_continuous_and_decreasing(self) -> None:
        h = np.linspace(0.0, 120e3, 2401)
        p = np.array([compute_atmospheric_pressure(x) for x in h])
        assert np.all(np.diff(p) < 0.0)
        assert np.max(np.abs(np.diff(np.log(p)))) < 0.01  # sin saltos entre capas

    def test_gravity_at_surface(self) -> None:
        """Gravedad en r=R_E: mu/R_E^2 ≈ 9.80 m/s^2 (tolerancia 0.02) hacia el origen."""
        r_e = EARTH.equatorial_radius_m
        mu = EARTH.mu_m3_s2

        # Prueba en el eje X
        pos_x = np.array([r_e, 0.0, 0.0], dtype=np.float64)
        g_vec = compute_gravity(pos_x, mu)

        g_mag = float(np.linalg.norm(g_vec))
        # mu / R_E^2 = 3.986004418e14 / (6378137.0^2) ≈ 9.798 m/s^2
        assert abs(g_mag - 9.80) < 0.02

        # Dirección debe ser estrictamente colineal opuesta a r (-x)
        unit_g = g_vec / g_mag
        assert np.allclose(unit_g, [-1.0, 0.0, 0.0])

        with pytest.raises(ValueError, match="no puede ser el origen"):
            compute_gravity([0.0, 0.0, 0.0], mu)

    def test_compute_altitude(self) -> None:
        """Verifica el cálculo de altitud sobre una esfera perfecta."""
        r_e = 6378137.0
        pos = [r_e + 5000.0, 0.0, 0.0]
        h = compute_altitude(pos, r_e)
        assert pytest.approx(h, rel=1e-9) == 5000.0

    def test_relative_velocity(self) -> None:
        """Verifica v_rel = v - omega x r en reposo sobre el ecuador."""
        r_e = EARTH.equatorial_radius_m
        omega_e = EARTH_ROTATION.omega_rad_s
        pos = np.array([r_e, 0.0, 0.0], dtype=np.float64)

        # Si el objeto co-rota perfectamente con la Tierra: v = omega x r = [0, omega*r_e, 0]
        v_rot = np.array([0.0, omega_e * r_e, 0.0], dtype=np.float64)
        v_rel = compute_relative_velocity(pos, v_rot, omega_e)
        assert np.allclose(v_rel, [0.0, 0.0, 0.0])

    def test_aerodynamic_drag(self) -> None:
        """Arrastre: opuesto a v_rel, proporcional a |v_rel|^2, nulo si v_rel=0 o h>100km."""
        v_rel = np.array([0.0, 200.0, 0.0], dtype=np.float64)
        h = 1000.0
        cd = 0.3
        area = 50.0

        drag_vec = compute_aerodynamic_drag(v_rel, h, cd, area)
        # Debe apuntar en dirección opuesta a v_rel (-y)
        assert drag_vec[1] < 0.0
        assert drag_vec[0] == 0.0
        assert drag_vec[2] == 0.0

        # Verificación de proporcionalidad con v^2
        v_rel_double = np.array([0.0, 400.0, 0.0], dtype=np.float64)
        drag_vec_double = compute_aerodynamic_drag(v_rel_double, h, cd, area)
        assert pytest.approx(float(np.linalg.norm(drag_vec_double)), rel=1e-6) == 4.0 * float(
            np.linalg.norm(drag_vec)
        )

        # Nulo en velocidad cero
        drag_zero = compute_aerodynamic_drag(np.zeros(3), h, cd, area)
        assert np.allclose(drag_zero, [0.0, 0.0, 0.0])

        # Nulo por encima de 100 km
        drag_karman = compute_aerodynamic_drag(v_rel, 100_001.0, cd, area)
        assert np.allclose(drag_karman, [0.0, 0.0, 0.0])

    def test_thrust_effective_and_mass_flow(self) -> None:
        """Empuje efectivo en superficie < vacío, tiende a vacío a gran altura, y dm/dt."""
        t_vac = 9_115_200.0  # N
        isp = 452.3  # s
        a_e = 16.0  # m^2

        p_sl = 101325.0  # Pa
        p_high = compute_atmospheric_pressure(80_000.0)  # Pa

        t_sl = compute_thrust(t_vac, a_e, p_sl)
        t_high = compute_thrust(t_vac, a_e, p_high)

        assert t_sl < t_vac
        assert t_sl == t_vac - p_sl * a_e
        assert t_high > t_sl
        assert pytest.approx(t_high, rel=1e-3) == t_vac

        # Flujo másico constante
        dm_dt = compute_mass_flow(t_vac, isp, G0_M_S2)
        assert dm_dt < 0.0
        expected_flow = -t_vac / (isp * G0_M_S2)
        assert pytest.approx(dm_dt, rel=1e-9) == expected_flow

        # Agotamiento de empuje
        assert compute_mass_flow(0.0, isp, G0_M_S2) == 0.0

    def test_coriolis_centrifugal_ecef_vs_eci_equivalence(self) -> None:
        """Demuestra equivalencia física entre integración en ECI vs ECEF con fuerzas ficticias.

        Caso simple: proyectil solo bajo gravedad central y aceleraciones ficticias
        durante 60 segundos. Al transformar la trayectoria de ECEF a ECI mediante la matriz
        de rotación R_z(omega * t), ambas trayectorias deben coincidir exactamente.
        """
        mu = EARTH.mu_m3_s2
        omega = EARTH_ROTATION.omega_rad_s
        r0 = EARTH.equatorial_radius_m + 300_000.0  # 300 km de altitud inicial
        t_span = (0.0, 60.0)

        # 1. Integración en ECI:
        pos_eci_0 = np.array([r0, 0.0, 0.0], dtype=np.float64)
        vel_eci_0 = np.array([0.0, 1000.0, 500.0], dtype=np.float64)
        y0_eci = np.concatenate([pos_eci_0, vel_eci_0])

        def deriv_eci(t: float, y: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
            pos = y[0:3]
            vel = y[3:6]
            a_g = compute_gravity(pos, mu)
            return np.concatenate([vel, a_g])

        sol_eci = solve_ivp(deriv_eci, t_span, y0_eci, method="RK45", rtol=1e-10, atol=1e-10)

        # 2. Integración en ECEF:
        pos_ecef_0 = pos_eci_0.copy()
        vel_ecef_0 = vel_eci_0 - np.cross([0.0, 0.0, omega], pos_ecef_0)
        y0_ecef = np.concatenate([pos_ecef_0, vel_ecef_0])

        def deriv_ecef(t: float, y: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
            pos = y[0:3]
            vel = y[3:6]
            a_g = compute_gravity(pos, mu)
            a_fict = compute_coriolis_centrifugal_accel(pos, vel, omega)
            return np.concatenate([vel, a_g + a_fict])

        sol_ecef = solve_ivp(deriv_ecef, t_span, y0_ecef, method="RK45", rtol=1e-10, atol=1e-10)

        # 3. Transformación del estado final ECEF a ECI en t = 60 s:
        t_final = sol_ecef.t[-1]
        theta = omega * t_final
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)
        r_z = np.array(
            [
                [cos_t, -sin_t, 0.0],
                [sin_t, cos_t, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

        pos_ecef_final = sol_ecef.y[0:3, -1]
        pos_transformed_to_eci = r_z @ pos_ecef_final
        pos_eci_final = sol_eci.y[0:3, -1]

        diff_pos = np.linalg.norm(pos_transformed_to_eci - pos_eci_final)
        assert diff_pos < 1e-3
