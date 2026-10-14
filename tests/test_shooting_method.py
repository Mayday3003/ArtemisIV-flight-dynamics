"""Pruebas unitarias para el algoritmo de targeting y método del disparo de Artemis IV."""

import numpy as np
import pytest

from artemis_sim.constants import MOON
from artemis_sim.ephemeris import get_body_position
from artemis_sim.shooting_method import (
    initial_guess_vis_viva,
    make_dop853_propagator,
    make_verlet_propagator,
    moon_relative_target,
    numerical_jacobian,
    shooting_residual,
    solve_tli_shooting,
)
from artemis_sim.state import ArtemisState
from artemis_sim.symplectic_solver import circular_orbit_state, impulsive_burn


class TestShootingMethod:
    """Conjunto de pruebas para el método del disparo y cálculo de targeting."""

    def test_numerical_jacobian_linear_function(self) -> None:
        """Verifica que el Jacobiano numérico sea exacto (rtol < 1e-9) para una función lineal."""
        a_matrix = np.array(
            [
                [2.5, -1.2, 0.4],
                [0.0, 3.1, -2.0],
                [-4.2, 1.0, 5.5],
            ],
            dtype=np.float64,
        )
        b_vec = np.array([10.0, -5.0, 3.0], dtype=np.float64)

        def linear_func(x: np.ndarray) -> np.ndarray:
            return np.asarray(a_matrix @ x + b_vec, dtype=np.float64)

        x_eval = np.array([1.5, -2.3, 4.1], dtype=np.float64)
        jac = numerical_jacobian(linear_func, x_eval, h=1e-3)

        assert jac.shape == (3, 3)
        assert np.allclose(jac, a_matrix, rtol=1e-9, atol=1e-9)

    def test_free_drift_propagator_jacobian(self) -> None:
        """Con deriva libre (r_f = r0 + v*t), el Jacobiano es exactamente t_flight * I."""
        state0 = circular_orbit_state(7_000_000.0)
        t_flight = 100.0
        target = np.array([1e7, 2e7, 3e7], dtype=np.float64)

        def free_drift_propagator(st: ArtemisState, tf: float) -> ArtemisState:
            new_pos = st.position + st.velocity * tf
            return ArtemisState(
                position=new_pos,
                velocity=st.velocity,
                mass=st.mass,
                t=st.t + tf,
            )

        def res_func(dv: np.ndarray) -> np.ndarray:
            return shooting_residual(dv, state0, target, t_flight, free_drift_propagator)

        dv_eval = np.array([10.0, -20.0, 30.0], dtype=np.float64)
        jac = numerical_jacobian(res_func, dv_eval, h=1e-2)

        expected_jac = t_flight * np.eye(3, dtype=np.float64)
        assert jac.shape == (3, 3)
        assert np.allclose(jac, expected_jac, rtol=1e-8, atol=1e-8)

    def test_twin_experiment_and_superlinear_convergence(self) -> None:
        """Experimento gemelo: recupera delta-v con residuo < 1 m y error de delta-v < 1e-2 m/s.

        Demuestra además convergencia monótona y cuadrática en las iteraciones finales.
        """
        r_orbit = 7_000_000.0
        state0 = circular_orbit_state(r_orbit)

        dv_true = initial_guess_vis_viva(state0, 300_000_000.0)
        t_flight = 4.0 * 86400.0  # 4 días

        dop_prop = make_dop853_propagator(rtol=1e-12, atol=1e-6, include_moon=True)

        state_tli_true = impulsive_burn(state0, dv_true)
        state_target = dop_prop(state_tli_true, t_flight)
        target_pos = state_target.position

        perturbation = np.array([20.0, -20.0, 15.0], dtype=np.float64)
        dv_guess = dv_true + perturbation

        result = solve_tli_shooting(
            state0=state0,
            target_pos=target_pos,
            t_flight=t_flight,
            dv_guess=dv_guess,
            propagator=dop_prop,
            tol_m=1.0,
            max_iter=15,
            fd_step=1e-2,
        )

        assert result.converged
        assert result.final_residual < 1.0
        assert np.linalg.norm(result.delta_v - dv_true) < 1e-2

        # Verificación de convergencia monótona
        res_hist = result.residual_history
        for i in range(len(res_hist) - 1):
            assert res_hist[i + 1] <= res_hist[i]

        # Comprobación de orden cuadrático
        c_quadratic = res_hist[-1] / (res_hist[-2] ** 2)
        assert c_quadratic < 1.0

    def test_robustness_bad_initial_guess(self) -> None:
        """Con una suposición inicial mala (500 m/s de error), no lanza excepción ni produce NaN."""
        state0 = circular_orbit_state(7_000_000.0)
        target = np.array([3e8, 1e8, 0.0], dtype=np.float64)
        t_flight = 2.0 * 86400.0

        bad_guess = np.array([-500.0, 500.0, 200.0], dtype=np.float64)

        result = solve_tli_shooting(
            state0=state0,
            target_pos=target,
            t_flight=t_flight,
            dv_guess=bad_guess,
            tol_m=1.0,
            max_iter=5,
        )

        assert isinstance(result.converged, bool)
        assert np.all(np.isfinite(result.delta_v))
        assert np.isfinite(result.final_residual)

    def test_singular_jacobian_handling(self) -> None:
        """Con un propagador artificial insensible (Jacobiano nulo), devuelve converged=False."""
        state0 = circular_orbit_state(7_000_000.0)
        target = np.array([1e8, 0.0, 0.0], dtype=np.float64)

        def dummy_propagator(st: ArtemisState, tf: float) -> ArtemisState:
            return ArtemisState(
                position=np.array([2e8, 0.0, 0.0]),
                velocity=np.zeros(3),
                mass=st.mass,
                t=st.t + tf,
            )

        result = solve_tli_shooting(
            state0=state0,
            target_pos=target,
            t_flight=100.0,
            dv_guess=[0.0, 0.0, 0.0],
            propagator=dummy_propagator,
            tol_m=1.0,
            max_iter=5,
        )

        assert not result.converged
        assert "Fallo algebraico" in result.message or "singular" in result.message

    def test_cross_validation_dop853_vs_verlet(self) -> None:
        """Validación cruzada: re-propaga delta_v con DOP853 y Verlet e informa diferencia."""
        state0 = circular_orbit_state(7_000_000.0)
        dv_true = initial_guess_vis_viva(state0, 250_000_000.0)
        t_flight = 1.0 * 86400.0

        dop_prop = make_dop853_propagator(include_moon=True)
        verlet_prop = make_verlet_propagator(dt=2.0, include_moon=True)

        target_pos = dop_prop(impulsive_burn(state0, dv_true), t_flight).position

        res = solve_tli_shooting(
            state0,
            target_pos,
            t_flight,
            dv_guess=dv_true + [5.0, -5.0, 0.0],
            propagator=dop_prop,
            tol_m=5.0,
            max_iter=10,
        )
        assert res.converged

        state_final_dop = dop_prop(impulsive_burn(state0, res.delta_v), t_flight)
        state_final_verlet = verlet_prop(impulsive_burn(state0, res.delta_v), t_flight)

        pos_diff_m = float(np.linalg.norm(state_final_dop.position - state_final_verlet.position))
        print(f"\n[VALIDACIÓN CRUZADA]: Discrepancia DOP vs Verlet (dt=2s) = {pos_diff_m:.2f} m")
        assert pos_diff_m < 5000.0

    def test_purity_of_shooting_residual(self) -> None:
        """Verifica que shooting_residual no mute en absoluto el estado inicial `state0`."""
        state0 = circular_orbit_state(7_000_000.0, mass_kg=120_000.0)
        pos_before = state0.position.copy()
        vel_before = state0.velocity.copy()
        t_before = state0.t
        mass_before = state0.mass

        prop = make_dop853_propagator(include_moon=False)
        _ = shooting_residual(
            delta_v=[100.0, 200.0, -50.0],
            state0=state0,
            target_pos=[8e6, 0.0, 0.0],
            t_flight=1000.0,
            propagator=prop,
        )

        assert np.allclose(state0.position, pos_before)
        assert np.allclose(state0.velocity, vel_before)
        assert state0.t == t_before
        assert state0.mass == mass_before

    def test_moon_relative_target_and_input_validations(self) -> None:
        """Verifica la función moon_relative_target y la validación rigurosa de entradas."""
        t_arr = 10000.0
        offset = [1000.0, -2000.0, 3000.0]
        pos_target = moon_relative_target(offset, t_arr)

        r_moon_actual = get_body_position(MOON, t_arr)
        assert np.allclose(pos_target, r_moon_actual + np.array(offset))

        state0 = circular_orbit_state(7_000_000.0)
        with pytest.raises(ValueError, match="tiempo de vuelo debe ser estrictamente positivo"):
            solve_tli_shooting(state0, [1e8, 0.0, 0.0], t_flight=-10.0, dv_guess=[0.0, 0.0, 0.0])

        with pytest.raises(ValueError, match="target_pos debe tener forma"):
            solve_tli_shooting(state0, [1e8, 0.0], t_flight=100.0, dv_guess=[0.0, 0.0, 0.0])

        with pytest.raises(ValueError, match="tol_m debe ser positiva"):
            solve_tli_shooting(
                state0,
                [1e8, 0.0, 0.0],
                t_flight=100.0,
                dv_guess=[0.0, 0.0, 0.0],
                tol_m=-1.0,
            )
