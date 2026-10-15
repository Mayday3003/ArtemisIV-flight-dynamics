"""Pruebas unitarias para el solver de ascenso atmosférico de Artemis IV."""

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from artemis_sim.ascent_solver import (
    AscentConfig,
    AscentPhase,
    event_karman_crossing,
    event_srb_burnout,
    initial_state_on_pad,
    jettison_boosters,
    make_ascent_derivatives,
    pitch_kick_direction,
    radial_direction,
    srb_thrust_scale,
)
from artemis_sim.constants import EARTH, EARTH_ROTATION, G0_M_S2
from artemis_sim.physics_engine import (
    compute_atmospheric_pressure,
    compute_relative_velocity,
    compute_thrust,
)
from artemis_sim.state import ArtemisState


class TestAscentSolver:
    """Conjunto de pruebas para el módulo de ascenso atmosférico."""

    def test_thrust_to_weight_ratio_at_liftoff(self) -> None:
        """Verifica que la relación empuje/peso (T/W) con todos los motores al despegue sea > 1.

        Si T/W <= 1, el cohete no despegaría de la plataforma, señalando una inconsistencia
        en las masas o empujes de la Fase 1.
        """
        config = AscentConfig()
        # Coordenadas LC-39B
        pad_state = initial_state_on_pad(28.627, -80.621, config)

        p_sl = compute_atmospheric_pressure(0.0)
        t_core_sl = compute_thrust(config.core_spec.thrust_vac_n, config.core_exit_area_m2, p_sl)
        t_srb_sl = compute_thrust(config.srb_spec.thrust_vac_n, config.srb_exit_area_m2, p_sl)
        total_thrust_sl = t_core_sl + t_srb_sl

        # Peso a nivel del mar
        weight_n = pad_state.mass * G0_M_S2
        twr = total_thrust_sl / weight_n

        assert twr > 1.0, f"Error: T/W al despegue es {twr:.3f} <= 1.0"
        # T/W típico de SLS Block 1B está entre 1.4 y 1.7
        assert 1.2 <= twr <= 2.0

    def test_initial_state_on_pad_relative_velocity_zero(self) -> None:
        """En la plataforma de lanzamiento terrestre, la velocidad relativa al aire debe ser ~0."""
        config = AscentConfig()
        state = initial_state_on_pad(28.627, -80.621, config)

        v_rel = compute_relative_velocity(
            state.position,
            state.velocity,
            EARTH_ROTATION.omega_rad_s,
        )
        assert np.allclose(v_rel, [0.0, 0.0, 0.0], atol=1e-10)
        assert pytest.approx(state.radius, rel=1e-9) == EARTH.equatorial_radius_m

    def test_jettison_boosters(self) -> None:
        """Verifica que jettison_boosters reduzca la masa exactamente en la masa seca de los SRB."""
        config = AscentConfig()
        state = initial_state_on_pad(28.627, -80.621, config)
        initial_mass = state.mass

        state_after_jettison = jettison_boosters(state, config)
        expected_mass = initial_mass - config.srb_spec.dry_mass_kg

        assert pytest.approx(state_after_jettison.mass, rel=1e-9) == expected_mass
        assert np.allclose(state_after_jettison.position, state.position)
        assert np.allclose(state_after_jettison.velocity, state.velocity)
        assert state_after_jettison.t == state.t

        # Rechazo de masa inconsistente
        invalid_state = ArtemisState(
            position=[7e6, 0.0, 0.0],
            velocity=[0.0, 0.0, 0.0],
            mass=1000.0,  # menor que masa de SRB
        )
        with pytest.raises(ValueError, match="Masa resultante inválida"):
            jettison_boosters(invalid_state, config)

    def test_thrust_direction_programs(self) -> None:
        """Verifica los programas de dirección radial y pitch kick."""
        pos = np.array([EARTH.equatorial_radius_m, 0.0, 0.0], dtype=np.float64)
        v_rel = np.array([0.0, 100.0, 0.0], dtype=np.float64)

        u_rad = radial_direction(0.0, pos, v_rel)
        assert np.allclose(u_rad, [1.0, 0.0, 0.0])
        assert pytest.approx(float(np.linalg.norm(u_rad)), rel=1e-9) == 1.0

        kick_fn = pitch_kick_direction(t_kick=10.0, pitch_angle_rad=0.05)
        # Antes del kick: debe ser radial
        u_pre = kick_fn(5.0, pos, v_rel)
        assert np.allclose(u_pre, [1.0, 0.0, 0.0])

        # Después del kick y con velocidad establecida: debe alinearse con v_rel
        u_post = kick_fn(25.0, pos, v_rel)
        assert np.allclose(u_post, [0.0, 1.0, 0.0])

    def test_ascent_derivatives_consistency_and_cutoff(self) -> None:
        """Verifica coherencia de la derivada temporal y corte por masa mínima."""
        config = AscentConfig(phase=AscentPhase.BOOSTERS_AND_CORE)
        derivatives_fn = make_ascent_derivatives(config)

        state = initial_state_on_pad(28.627, -80.621, config)
        state_vec = state.to_array()

        deriv = derivatives_fn(0.0, state_vec)
        assert deriv.shape == (7,)
        assert np.all(np.isfinite(deriv))

        # Derivada de posición debe ser la velocidad
        assert np.allclose(deriv[0:3], state_vec[3:6])
        # dm/dt debe ser estrictamente negativo
        assert deriv[6] < 0.0

        # Prueba de corte de masa: si m <= cutoff_mass, dm/dt = 0 y empuje = 0
        state_empty_vec = state_vec.copy()
        state_empty_vec[6] = config.cutoff_mass_kg - 100.0  # por debajo del corte
        deriv_empty = derivatives_fn(0.0, state_empty_vec)
        assert deriv_empty[6] == 0.0  # motores apagados

    def test_smoke_solve_ivp_first_10_seconds(self) -> None:
        """Prueba de humo: integra con solve_ivp (RK45, rtol=1e-8) los primeros 10 segundos."""
        config = AscentConfig(
            phase=AscentPhase.BOOSTERS_AND_CORE,
            thrust_direction_fn=radial_direction,
        )
        deriv_fn = make_ascent_derivatives(config)
        state_0 = initial_state_on_pad(28.627, -80.621, config)
        y0 = state_0.to_array()

        sol = solve_ivp(
            deriv_fn,
            (0.0, 10.0),
            y0,
            method="RK45",
            rtol=1e-8,
            atol=1e-8,
            events=[event_srb_burnout, event_karman_crossing],
        )

        assert sol.success
        assert len(sol.t) > 5
        assert sol.t[-1] == 10.0

        final_state = ArtemisState.from_array(sol.y[:, -1], t=10.0)

        # Tras 10 s de ascenso vertical con T/W > 1.4:
        # 1. Altitud debe haber aumentado (radio final > radio inicial)
        assert final_state.radius > state_0.radius
        alt_gain = final_state.radius - state_0.radius
        assert alt_gain > 50.0  # Al menos decenas de metros ganados

        # 2. Velocidad debe haber aumentado
        v_rel_final = compute_relative_velocity(
            final_state.position,
            final_state.velocity,
            EARTH_ROTATION.omega_rad_s,
        )
        assert np.linalg.norm(v_rel_final) > 20.0  # m/s

        # 3. La masa debe haber disminuido por el consumo de propelente
        assert final_state.mass < state_0.mass
        # Durante 0-20 s el perfil SRB está al 100 % del pico (escalado por conservación de masa)
        srb_scale = srb_thrust_scale(config.srb_spec, config.t_burn_srb_s)
        expected_mass_loss = (
            abs(config.core_spec.mass_flow_rate_kg_s)
            + srb_scale * abs(config.srb_spec.mass_flow_rate_kg_s)
        ) * 10.0
        assert pytest.approx(state_0.mass - final_state.mass, rel=1e-3) == expected_mass_loss
