"""Pruebas unitarias para la clase de estado orbital ArtemisState."""

import numpy as np
import pytest

from artemis_sim.constants import EARTH
from artemis_sim.state import ArtemisState


class TestArtemisState:
    """Conjunto de pruebas para ArtemisState."""

    def test_initialization_and_properties(self) -> None:
        """Verifica la asignación correcta y cálculo de magnitudes cinemáticas."""
        # Órbita circular baja LEO a 400 km de altitud
        r_orbit = EARTH.equatorial_radius_m + 400_000.0
        v_orbit = np.sqrt(EARTH.mu_m3_s2 / r_orbit)  # ~7672 m/s
        mass = 120_000.0  # kg

        pos = [r_orbit, 0.0, 0.0]
        vel = [0.0, v_orbit, 0.0]
        state = ArtemisState(position=pos, velocity=vel, mass=mass, t=10.5)

        assert state.t == 10.5
        assert np.allclose(state.position, [r_orbit, 0.0, 0.0])
        assert np.allclose(state.velocity, [0.0, v_orbit, 0.0])
        assert state.mass == mass
        assert pytest.approx(state.radius, rel=1e-9) == r_orbit
        assert pytest.approx(state.speed, rel=1e-9) == v_orbit

    def test_to_array_and_from_array_roundtrip(self) -> None:
        """Verifica la fidelidad de serialización/deserialización en numpy.ndarray (7,)."""
        pos = np.array([6.5e6, 1.2e6, -3.4e5], dtype=np.float64)
        vel = np.array([120.0, 7500.0, 2300.0], dtype=np.float64)
        mass = 95000.0
        t = 125.0

        state = ArtemisState(position=pos, velocity=vel, mass=mass, t=t)
        arr = state.to_array()

        assert isinstance(arr, np.ndarray)
        assert arr.shape == (7,)
        assert arr.dtype == np.float64
        assert np.allclose(arr[0:3], pos)
        assert np.allclose(arr[3:6], vel)
        assert arr[6] == mass

        reconstructed = ArtemisState.from_array(arr, t=t)
        assert reconstructed.t == t
        assert np.allclose(reconstructed.position, pos)
        assert np.allclose(reconstructed.velocity, vel)
        assert reconstructed.mass == mass
        assert np.allclose(reconstructed.to_array(), arr)

    def test_copy(self) -> None:
        """Verifica que copy produzca una réplica exacta e independiente."""
        state1 = ArtemisState(
            position=[7e6, 0.0, 0.0],
            velocity=[0.0, 7.5e3, 0.0],
            mass=50000.0,
            t=0.0,
        )
        state2 = state1.copy()

        assert state1 is not state2
        assert np.allclose(state1.to_array(), state2.to_array())
        assert state1.t == state2.t

    def test_immutability_of_internal_data(self) -> None:
        """Garantiza que la modificación externa no corrompa el estado interno."""
        pos = np.array([7e6, 0.0, 0.0])
        vel = np.array([0.0, 7.5e3, 0.0])
        state = ArtemisState(position=pos, velocity=vel, mass=50000.0)

        # Modificar el array original no debe alterar state
        pos[0] = 999.0
        assert state.position[0] == 7e6

        # Modificar el array devuelto por to_array no debe alterar state
        arr = state.to_array()
        arr[0] = 123.0
        assert state.position[0] == 7e6

        # Escribir en state.position lanza ValueError por flags.writeable = False
        with pytest.raises(ValueError):
            state.position[0] = 123.0

    def test_repr_output(self) -> None:
        """Verifica que __repr__ sea legible y contenga las magnitudes y unidades."""
        state = ArtemisState(
            position=[7000000.0, 0.0, 0.0],
            velocity=[0.0, 7500.0, 0.0],
            mass=50000.0,
            t=5.0,
        )
        rep = repr(state)
        assert "ArtemisState" in rep
        assert "t=5.000 s" in rep
        assert "m/s" in rep
        assert "kg" in rep
        assert "radius=7000000.0 m" in rep

    def test_validations(self) -> None:
        """Verifica que entradas inválidas (NaN, inf, masa negativa, forma errónea) fallen."""
        valid_pos = [7e6, 0.0, 0.0]
        valid_vel = [0.0, 7.5e3, 0.0]

        # Forma incorrecta en posición
        with pytest.raises(ValueError, match="vector de posición debe tener exactamente 3"):
            ArtemisState(position=[1.0, 2.0], velocity=valid_vel, mass=100.0)

        # Forma incorrecta en velocidad
        with pytest.raises(ValueError, match="vector de velocidad debe tener exactamente 3"):
            ArtemisState(position=valid_pos, velocity=[1.0, 2.0, 3.0, 4.0], mass=100.0)

        # Masa negativa o cero
        with pytest.raises(ValueError, match="masa debe ser estrictamente positiva"):
            ArtemisState(position=valid_pos, velocity=valid_vel, mass=0.0)

        with pytest.raises(ValueError, match="masa debe ser estrictamente positiva"):
            ArtemisState(position=valid_pos, velocity=valid_vel, mass=-50.0)

        # Valores NaN o Infinitos
        with pytest.raises(ValueError, match="valores no finitos"):
            ArtemisState(
                position=[np.nan, 0.0, 0.0],
                velocity=valid_vel,
                mass=100.0,
            )

        with pytest.raises(ValueError, match="valores no finitos"):
            ArtemisState(
                position=valid_pos,
                velocity=[0.0, np.inf, 0.0],
                mass=100.0,
            )

        with pytest.raises(ValueError, match="tiempo de simulación debe ser finito"):
            ArtemisState(
                position=valid_pos,
                velocity=valid_vel,
                mass=100.0,
                t=float("nan"),
            )

        # from_array con forma incorrecta
        with pytest.raises(ValueError, match="vector plano de entrada debe tener forma"):
            ArtemisState.from_array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
