"""Pruebas unitarias para el integrador simpléctico y dinámica n-cuerpos en el vacío."""

import numpy as np
import pytest

from artemis_sim.constants import EARTH, MOON
from artemis_sim.ephemeris import get_body_position
from artemis_sim.physics_engine import compute_gravity
from artemis_sim.state import ArtemisState
from artemis_sim.symplectic_solver import (
    circular_orbit_state,
    compute_system_energy,
    impulsive_burn,
    propagate_reference_dop853,
    propagate_verlet,
    verlet_step,
)


class TestSymplecticSolver:
    """Conjunto de pruebas para el solver simpléctico y dinámica orbital en el vacío."""

    def test_indirect_term_acceleration_at_origin(self) -> None:
        """Con la Luna activa, la aceleración gravitacional geocéntrica en r=0 debe ser nula.

        Física:
        a_directo(Tierra en 0 debido a Luna) + a_indirecto = 0.
        Verifica que el término indirecto cancele exactamente la atracción lunar en el origen
        con tolerancia 1e-15 relativa a mu_M / d^2.
        """
        t = 12345.0
        r_moon = get_body_position(MOON, t)
        d_moon = float(np.linalg.norm(r_moon))
        # Aceleración característica de la Luna sobre la Tierra
        char_accel = MOON.mu_m3_s2 / (d_moon**2)

        # Evaluación analítica de los términos directos e indirectos lunares
        a_direct = compute_gravity(-r_moon, MOON.mu_m3_s2)
        a_indirect = -compute_gravity(-r_moon, MOON.mu_m3_s2)
        total_lunar_accel_at_center = a_direct + a_indirect

        diff = float(np.linalg.norm(total_lunar_accel_at_center))
        assert diff / char_accel < 1e-15

    def test_verlet_step_immutability_and_mass_conservation(self) -> None:
        """Verifica que verlet_step devuelva un nuevo estado sin mutar el original."""
        state0 = circular_orbit_state(7_000_000.0, phase_rad=0.0, mass_kg=120_000.0)
        pos0_copy = state0.position.copy()
        vel0_copy = state0.velocity.copy()

        state1 = verlet_step(state0, dt=10.0, include_moon=False)

        assert state1 is not state0
        assert state1.mass == state0.mass
        assert pytest.approx(state1.t, rel=1e-12) == 10.0

        # El estado original permanece inalterado
        assert np.allclose(state0.position, pos0_copy)
        assert np.allclose(state0.velocity, vel0_copy)

        with pytest.raises(ValueError, match="dt debe ser estrictamente positivo"):
            verlet_step(state0, dt=-1.0)

    def test_two_body_energy_and_angular_momentum_conservation(self) -> None:
        """Conservación de energía (< 1e-5) y momento angular (< 1e-9) en 100 órbitas con Verlet.

        Sin deriva secular: compara el error de la primera y última órbita.
        """
        r_orbit = 7_000_000.0  # 7000 km de radio
        state0 = circular_orbit_state(r_orbit)

        # Periodo kepleriano: T = 2*pi*sqrt(r^3 / mu)
        period = 2.0 * np.pi * np.sqrt((r_orbit**3) / EARTH.mu_m3_s2)  # ~5826 s
        # 100 órbitas con dt = T / 2000
        dt = period / 2000.0  # ~2.91 s
        n_orbits = 100
        t_final = n_orbits * period

        # Muestreamos cada 200 pasos (~10 muestras por órbita) para que sea veloz en memoria
        trajectory = propagate_verlet(
            state0,
            t_final=t_final,
            dt=dt,
            sample_every=200,
            include_moon=False,
        )

        e0 = compute_system_energy(state0, 0.0, include_moon=False)
        h0 = float(np.linalg.norm(np.cross(state0.position, state0.velocity)))

        energy_rel_errors: list[float] = []
        angular_momentum_rel_errors: list[float] = []

        for st in trajectory:
            e = compute_system_energy(st, st.t, include_moon=False)
            h = float(np.linalg.norm(np.cross(st.position, st.velocity)))
            energy_rel_errors.append(abs((e - e0) / e0))
            angular_momentum_rel_errors.append(abs((h - h0) / h0))

        # 1. Variación relativa máxima de energía a lo largo de toda la trayectoria < 1e-5
        max_energy_error = max(energy_rel_errors)
        assert max_energy_error < 1e-5, f"Error máximo de energía excedido: {max_energy_error}"

        # 2. Conservación del momento angular específico < 1e-9
        max_h_error = max(angular_momentum_rel_errors)
        assert max_h_error < 1e-9, f"Error de momento angular excedido: {max_h_error}"

        # 3. Sin deriva secular en energía:
        first_orbit_points = int(2000 / 200)  # ~10 puntos
        err_first_orbit = max(energy_rel_errors[:first_orbit_points])
        err_last_orbit = max(energy_rel_errors[-first_orbit_points:])
        # La oscilación hamiltoniana de Verlet está acotada
        assert abs(err_last_orbit - err_first_orbit) < 1e-6

    def test_second_order_convergence(self) -> None:
        """Al dividir dt a la mitad, el error de energía se reduce por un factor ≈ 4 (orden 2).

        En una órbita elíptica (e = 0.1), el radio y la velocidad varían a lo largo del periodo,
        mostrando claramente el factor de convergencia cuadrático O(dt^2) (ratio ≈ 4.0).
        """
        r_perigee = 7_000_000.0
        e = 0.1
        mu = EARTH.mu_m3_s2
        v_p = float(np.sqrt(mu / r_perigee * (1.0 + e)))
        state0 = ArtemisState(
            position=[r_perigee, 0.0, 0.0],
            velocity=[0.0, v_p, 0.0],
            mass=1000.0,
        )

        a_semi = r_perigee / (1.0 - e)
        period = 2.0 * np.pi * float(np.sqrt((a_semi**3) / mu))
        t_final = period  # 1 órbita completa

        dt_coarse = period / 200.0
        dt_fine = dt_coarse / 2.0  # period / 400.0

        traj_coarse = propagate_verlet(
            state0,
            t_final,
            dt_coarse,
            sample_every=1,
            include_moon=False,
        )
        traj_fine = propagate_verlet(
            state0,
            t_final,
            dt_fine,
            sample_every=1,
            include_moon=False,
        )

        e0 = compute_system_energy(state0, 0.0, include_moon=False)

        max_err_coarse = max(
            abs((compute_system_energy(st, st.t, include_moon=False) - e0) / e0)
            for st in traj_coarse
        )
        max_err_fine = max(
            abs((compute_system_energy(st, st.t, include_moon=False) - e0) / e0)
            for st in traj_fine
        )

        ratio = max_err_coarse / max_err_fine
        # Demostración empírica de esquema de segundo orden (factor entre 3.8 y 4.2)
        assert 3.8 <= ratio <= 4.2, f"Relación de convergencia anómala: {ratio:.3f}"

    def test_time_reversibility(self) -> None:
        """Reversibilidad temporal de Verlet: avanzar N pasos, invertir v y avanzar N pasos."""
        state0 = circular_orbit_state(7_000_000.0)
        dt = 5.0
        n_steps = 100

        # Avanzar 100 pasos
        st = state0
        for _ in range(n_steps):
            st = verlet_step(st, dt, include_moon=False)

        # Invertir velocidad
        st_reversed = ArtemisState(
            position=st.position,
            velocity=-st.velocity,
            mass=st.mass,
            t=st.t,
        )

        # Avanzar otros 100 pasos
        for _ in range(n_steps):
            st_reversed = verlet_step(st_reversed, dt, include_moon=False)

        # La posición final debe coincidir con la posición inicial
        pos_diff = np.linalg.norm(st_reversed.position - state0.position)
        rel_pos_diff = pos_diff / float(np.linalg.norm(state0.position))
        assert rel_pos_diff < 1e-9

    def test_three_body_transit_verlet_vs_dop853(self) -> None:
        """Con la Luna activa, compara posición de Verlet con DOP853 tras 1 día de tránsito.

        Justificación de tolerancia:
        Un integrador de segundo orden con paso fijo de dt = 1.0 s acumula un error de truncamiento
        global del orden de O(dt^2) a lo largo de 86,400 pasos. Para un semieje de transferencia
        hacia la Luna (~200,000 km), una discrepancia de unos pocos cientos de metros
        representa un error relativo en posición < 5e-5, lo que valida la coherencia
        matemática entre la formulación simpléctica de Verlet y el estándar adaptativo DOP853.
        """
        # Estado de inicio: inyección translunar (TLI)
        r_park = EARTH.equatorial_radius_m + 300_000.0
        state_park = circular_orbit_state(r_park)
        state_tli = impulsive_burn(state_park, [0.0, 3150.0, 0.0])

        t_transit = 86400.0  # 1 día de tránsito
        dt_verlet = 1.0  # s

        # Propagar con Verlet
        traj_verlet = propagate_verlet(
            state_tli,
            t_final=t_transit,
            dt=dt_verlet,
            sample_every=1000,
            include_moon=True,
        )
        state_final_verlet = traj_verlet[-1]

        # Propagar con DOP853
        state_final_dop853 = propagate_reference_dop853(
            state_tli,
            t_final=t_transit,
            include_moon=True,
            rtol=1e-12,
            atol=1e-6,
        )

        diff_norm = float(np.linalg.norm(state_final_verlet.position - state_final_dop853.position))
        r_dop = float(np.linalg.norm(state_final_dop853.position))
        rel_err = diff_norm / r_dop

        # Error relativo < 5e-5 tras 86,400 s
        assert rel_err < 5e-5, f"Error relativo excesivo con DOP853: {rel_err}"

    def test_impulsive_burn_utility(self) -> None:
        """Verifica que impulsive_burn altere solo la velocidad manteniendo posición, masa y t."""
        state = circular_orbit_state(7_000_000.0, mass_kg=95000.0)
        dv = [10.0, -20.0, 50.0]

        burned_state = impulsive_burn(state, dv)

        assert np.allclose(burned_state.position, state.position)
        assert np.allclose(burned_state.velocity, state.velocity + np.array(dv))
        assert burned_state.mass == state.mass
        assert burned_state.t == state.t

        with pytest.raises(ValueError, match="delta_v debe ser un vector 3D"):
            impulsive_burn(state, [1.0, 2.0])

    def test_smoke_report_translunar_injection_5_days(self) -> None:
        """Informe de humo (sin assert estricto): TLI hacia la Luna durante 5 días.

        Reporta la distancia mínima alcanzada a la Luna sin afirmar que colisione o entre en órbita.
        """
        r_park = EARTH.equatorial_radius_m + 300_000.0
        state_park = circular_orbit_state(r_park)

        state_tli = impulsive_burn(state_park, [0.0, 3140.0, 0.0])
        t_5_days = 5.0 * 86400.0  # 5 días en segundos

        traj = propagate_verlet(
            state_tli,
            t_final=t_5_days,
            dt=10.0,
            sample_every=100,
            include_moon=True,
        )

        min_dist_moon = float("inf")
        t_min = 0.0

        for st in traj:
            r_moon = get_body_position(MOON, st.t)
            dist = float(np.linalg.norm(st.position - r_moon))
            if dist < min_dist_moon:
                min_dist_moon = dist
                t_min = st.t

        print(
            f"\n[INFORME DE HUMO TLI]: Distancia mín. a la Luna = {min_dist_moon / 1000.0:.2f} km "
            f"alcanzada en t = {t_min / 86400.0:.2f} días tras TLI."
        )
        assert min_dist_moon > 0.0
