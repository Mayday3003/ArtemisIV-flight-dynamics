"""Pruebas de la exportación de trayectorias y de la misión encadenada (Etapa 1)."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from artemis_sim.constants import EARTH, MOON
from artemis_sim.ephemeris import LunarOrbitConfig, get_body_position, get_body_velocity
from artemis_sim.export import (
    MissionPhase,
    MissionTrajectory,
    concatenate_segments,
    from_json,
    hermite_interpolate,
    phase_index,
    resample,
    to_json,
)
from artemis_sim.mission import build_mission_phases_1_to_3
from artemis_sim.state import ArtemisState
from artemis_sim.symplectic_solver import compute_jacobi_constant, propagate_verlet

R_LEO = EARTH.equatorial_radius_m + 400e3
N_LEO = math.sqrt(EARTH.mu_m3_s2 / R_LEO**3)


def circular_samples(t: np.ndarray) -> np.ndarray:
    """Órbita circular ecuatorial exacta (estado 7 x N, masa constante)."""
    v = N_LEO * R_LEO
    return np.vstack(
        [
            R_LEO * np.cos(N_LEO * t),
            R_LEO * np.sin(N_LEO * t),
            np.zeros_like(t),
            -v * np.sin(N_LEO * t),
            v * np.cos(N_LEO * t),
            np.zeros_like(t),
            np.full_like(t, 1000.0),
        ]
    )


class TestInterpolation:
    def test_hermite_reproduces_circular_orbit(self) -> None:
        """Con muestras cada 60 s en LEO, el error a mitad de intervalo es < 10 m."""
        t = np.arange(0.0, 5400.0 + 1, 60.0)
        tq = t[:-1] + 30.0
        err = np.linalg.norm(
            hermite_interpolate(t, circular_samples(t), tq)[0:3] - circular_samples(tq)[0:3], axis=0
        )
        assert err.max() < 10.0

    def test_hermite_is_exact_at_nodes(self) -> None:
        t = np.arange(0.0, 600.0, 60.0)
        y = circular_samples(t)
        assert np.allclose(hermite_interpolate(t, y, t), y)

    def test_out_of_range_raises(self) -> None:
        t = np.array([0.0, 1.0])
        with pytest.raises(ValueError):
            hermite_interpolate(t, circular_samples(t), np.array([2.0]))


class TestSegmentsAndResample:
    def test_concatenate_keeps_later_state_at_discontinuity(self) -> None:
        t1, t2 = np.array([0.0, 1.0]), np.array([1.0, 2.0])
        y1, y2 = np.ones((7, 2)), np.full((7, 2), 2.0)
        t, y = concatenate_segments([(t1, y1), (t2, y2)])
        assert list(t) == [0.0, 1.0, 2.0]
        assert y[6, 1] == 2.0  # en t = 1 queda el estado posterior (p. ej. tras separar etapas)

    def test_resample_includes_phase_bounds_and_is_increasing(self) -> None:
        t = np.linspace(0.0, 1000.0, 2001)
        phases = [MissionPhase("a", "A", 0.0, 333.3), MissionPhase("b", "B", 333.3, 1000.0)]
        traj = resample(MissionTrajectory(t, circular_samples(t), phases), {"a": 10.0, "b": 100.0})
        assert {0.0, 333.3, 1000.0} <= set(np.round(traj.t, 6))
        assert np.all(np.diff(traj.t) > 0)
        idx = phase_index(traj)
        assert idx[0] == 0 and idx[-1] == 1

    def test_trajectory_rejects_non_increasing_time(self) -> None:
        with pytest.raises(ValueError):
            MissionTrajectory(np.array([0.0, 0.0]), np.zeros((7, 2)), [])


class TestJson:
    def test_roundtrip_error_below_one_meter(self, tmp_path: Path) -> None:
        t = np.arange(0.0, 6000.0, 30.0)
        traj = MissionTrajectory(t, circular_samples(t), [MissionPhase("p", "P", 0.0, t[-1])])
        back = from_json(to_json(traj, tmp_path / "m.json"))
        assert np.max(np.abs(back.y[0:3] - traj.y[0:3])) < 1.0  # posición: m
        assert np.max(np.abs(back.y[3:6] - traj.y[3:6])) < 1e-3  # velocidad: m/s
        assert np.allclose(back.t, traj.t)

    def test_json_is_strict_and_columnar(self, tmp_path: Path) -> None:
        t = np.arange(0.0, 100.0, 10.0)
        traj = MissionTrajectory(t, circular_samples(t), [MissionPhase("p", "P", 0.0, t[-1])])
        data = json.loads(to_json(traj, tmp_path / "m.json").read_text())
        assert data["schema_version"] == 1
        assert data["units"]["length"] == "km"
        assert len(data["samples"]["x"]) == t.size
        assert data["samples"]["x"][0] == pytest.approx(R_LEO / 1e3, abs=1e-4)


class TestInclinedMoon:
    cfg = LunarOrbitConfig(inclination_rad=math.radians(28.6), raan_rad=1.0, initial_phase_rad=0.3)

    def test_moon_stays_in_its_plane_at_constant_distance(self) -> None:
        _, _, h = self.cfg.plane_basis()
        for t in (0.0, 1e5, 1e6):
            r = get_body_position(MOON, t, self.cfg)
            assert np.linalg.norm(r) == pytest.approx(self.cfg.orbital_radius_m, rel=1e-12)
            assert abs(np.dot(r, h)) < 1e-3

    def test_velocity_is_derivative_of_position(self) -> None:
        t, dt = 2e5, 1.0
        num = (
            get_body_position(MOON, t + dt, self.cfg) - get_body_position(MOON, t - dt, self.cfg)
        ) / (2 * dt)
        assert np.allclose(get_body_velocity(MOON, t, self.cfg), num, rtol=1e-8)

    def test_jacobi_conserved_with_inclined_moon(self) -> None:
        st = ArtemisState([2.0e8, 1.0e7, 3.0e7], [0.0, 1200.0, 300.0], 1.0)
        traj = propagate_verlet(st, 3 * 86400.0, dt=30.0, sample_every=100, lunar_config=self.cfg)
        ej = np.array([compute_jacobi_constant(s, self.cfg) for s in traj])
        assert np.max(np.abs(ej / ej[0] - 1.0)) < 1e-6


class TestMission:
    def test_mission_phases_1_to_3_reach_the_moon(self) -> None:
        """La misión encadenada converge y llega cerca del objetivo de 4 000 km de altitud."""
        traj, summary = build_mission_phases_1_to_3()
        assert summary.shooting.converged
        assert 3.0e3 < summary.dv_tli_m_s < 3.3e3
        assert summary.flyby_altitude_m == pytest.approx(4_000e3, abs=20e3)
        # Fases contiguas y que cubren toda la trayectoria
        assert traj.phases[0].t_start == 0.0
        for a, b in zip(traj.phases, traj.phases[1:], strict=False):
            assert a.t_end == b.t_start
        assert traj.phases[-1].t_end == pytest.approx(traj.t[-1])
        # La masa nunca aumenta
        assert np.all(np.diff(traj.y[6]) <= 1e-9)
