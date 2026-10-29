"""Pruebas del disparo múltiple y de la transferencia TLI → NRHO (Etapa 4)."""

import numpy as np
import pytest

from artemis_sim.constants import G0_M_S2, ORION, SLS_B1B_EUS
from artemis_sim.cr3bp import UNITS, propagate, rotating_to_eci
from artemis_sim.export import MissionTrajectory
from artemis_sim.mission import MissionSummaryPhase4, MissionSummaryPhase5
from artemis_sim.multiple_shooting import MultipleShooting, newton_min_norm
from artemis_sim.shooting_method import make_dop853_propagator

KEPLER_MU = 0.0  # con mu = 0 el CR3BP es un problema de dos cuerpos visto desde un marco rotante


def circular_state(phase: float) -> np.ndarray:
    """Órbita circular inercial de radio 0,5 y n = sqrt(1/r³), vista en el marco rotante (ω = 1)."""
    r, n = 0.5, np.sqrt(1.0 / 0.5**3)
    c, s = np.cos(phase), np.sin(phase)
    pos = np.array([r * c, r * s, 0.0])
    v_in = r * n * np.array([-s, c, 0.0])
    return np.concatenate([pos, v_in - np.cross([0.0, 0.0, 1.0], pos)])


class TestMultipleShooting:
    def test_circular_orbit_in_four_segments_converges(self) -> None:
        """Cuatro nodos perturbados de una órbita circular: Newton recupera la continuidad."""
        n_rot = np.sqrt(1.0 / 0.5**3) - 1.0  # velocidad angular aparente en el marco rotante
        period = 2.0 * np.pi / n_rot
        ms = MultipleShooting(4, mu=KEPLER_MU)
        rng = np.random.default_rng(1)
        nodes = np.array([circular_state(k * np.pi / 2) for k in range(4)])
        nodes += 1e-3 * rng.standard_normal(nodes.shape)
        z0 = ms.pack(nodes, np.full(4, period / 4) * (1 + 1e-3 * rng.standard_normal(4)))
        z, _ = newton_min_norm(ms.continuity, ms.continuity_jacobian, z0, tol=1e-12)
        assert np.max(np.abs(ms.continuity(z))) < 1e-12

    def test_block_jacobian_matches_finite_differences(self) -> None:
        ms = MultipleShooting(3, burn_nodes=(1,), mu=0.0121)
        base = np.array([[1.05, 0.02, -0.1, 0.0, -0.1, 0.0]] * 3)
        nodes = base + 0.01 * np.arange(18).reshape(3, 6)
        z = ms.pack(nodes, np.array([0.3, 0.4, 0.2]))
        jac = ms.continuity_jacobian(z)
        h = 1e-7
        num = np.column_stack(
            [
                (ms.continuity(z + h * e) - ms.continuity(z - h * e)) / (2 * h)
                for e in np.eye(z.size)
            ]
        )
        assert jac.shape == (9, 21)  # 3 filas (posición) en el nodo de encendido + 6
        assert np.max(np.abs(jac - num)) < 1e-6

    def test_burn_nodes_must_be_interior(self) -> None:
        with pytest.raises(ValueError):
            MultipleShooting(3, burn_nodes=(0,))


@pytest.fixture(scope="module")
def mission4(
    mission5: tuple[MissionTrajectory, MissionSummaryPhase5],
) -> tuple[MissionTrajectory, MissionSummaryPhase4]:
    """Fases 1–4 de la misión completa: todo lo anterior a la DOI del HLS."""
    traj, s = mission5
    before = traj.t < s.t_doi_s
    return (
        MissionTrajectory(
            traj.t[before], traj.y[:, before], traj.phases[:4], traj.events, traj.lunar_config
        ),
        s.phases_1_to_4,
    )


class TestNrhoTransfer:
    def test_arrives_in_independent_geocentric_model(self, mission4) -> None:  # type: ignore[no-untyped-def]
        """Cada nodo, propagado en el modelo ECI geocéntrico (no en el CR3BP), cae en el
        siguiente: < 1 km y < 1 m/s, incluida la llegada a la NRHO."""
        traj, s = mission4
        tr, lunar = s.transfer, traj.lunar_config
        prop = make_dop853_propagator(include_moon=True, lunar_config=lunar)
        t = s.t_tli_s + np.concatenate([[0.0], np.cumsum(tr.durations)]) * UNITS.time_s
        targets = list(tr.nodes[1:]) + [tr.arrival]
        for i, (x, target) in enumerate(zip(tr.nodes, targets, strict=True)):
            st0 = rotating_to_eci(x, float(t[i]), lunar)
            end = prop(st0, float(t[i + 1] - t[i]))  # el propagador recibe una duración
            ref = rotating_to_eci(target, float(t[i + 1]), lunar)
            assert np.linalg.norm(end.position - ref.position) < 1e3, f"tramo {i}"
            if i + 1 != tr.flyby_node:  # en el OPF la velocidad cambia a propósito
                assert np.linalg.norm(end.velocity - ref.velocity) < 1.0, f"tramo {i}"

    def test_nri_puts_spacecraft_on_the_nrho(self, mission4) -> None:  # type: ignore[no-untyped-def]
        _, s = mission4
        after = s.transfer.arrival.copy()
        after[3:6] += s.transfer.dv_nri
        one_rev = propagate(after, s.nrho.period).states[:, -1]
        assert np.max(np.abs(one_rev - after)) < 1e-6  # vuelve a sí mismo tras un periodo

    def test_delta_v_budget(self, mission4) -> None:  # type: ignore[no-untyped-def]
        """Orden de magnitud de Artemis I (OPF ≈ 180 m/s; inserción en DRO ≈ 110–150 m/s)
        y dentro de lo que el ESM de Orion puede dar llevando el I-Hab."""
        _, s = mission4
        assert 3.0e3 < s.dv_tli_m_s < 3.4e3
        assert 50.0 < s.dv_opf_m_s < 600.0
        assert 20.0 < s.dv_nri_m_s < 400.0
        assert s.dv_opf_m_s + s.dv_nri_m_s < s.orion_dv_capability_m_s
        assert s.opf_altitude_m >= 100e3 - 1.0

    def test_eus_has_propellant_for_tli(self, mission4) -> None:  # type: ignore[no-untyped-def]
        traj, s = mission4
        m_before = float(traj.y[6, np.searchsorted(traj.t, s.t_tli_s) - 1])
        used = m_before * (1 - np.exp(-s.dv_tli_m_s / (SLS_B1B_EUS.isp_vac_s * G0_M_S2)))
        assert used < SLS_B1B_EUS.propellant_mass_kg

    def test_mission_is_continuous_and_ordered(self, mission4) -> None:  # type: ignore[no-untyped-def]
        traj, s = mission4
        assert [p.id for p in traj.phases] == ["ascent", "parking", "transit", "nrho"]
        for a, b in zip(traj.phases, traj.phases[1:], strict=False):
            assert a.t_end == b.t_start
        assert s.t_tli_s < s.t_opf_s < s.t_nri_s
        assert np.all(np.diff(traj.y[6]) <= 1e-9)  # la masa nunca aumenta
        # Ningún salto de posición mayor que lo que se recorre entre muestras
        step = np.linalg.norm(np.diff(traj.y[0:3], axis=1), axis=0)
        speed = np.linalg.norm(traj.y[3:6, 1:], axis=0)
        assert np.all(step <= 2.0 * speed * np.diff(traj.t) + 1.0)
        assert ORION.isp_vac_s == 316.0
