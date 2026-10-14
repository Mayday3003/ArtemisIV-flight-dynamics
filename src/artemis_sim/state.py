"""Gestión del vector de estado del vehículo en simulación orbital.

Justificación del diseño de almacenamiento interno:
---------------------------------------------------
Se ha seleccionado un único `numpy.ndarray` unidimensional de tamaño (7,) y tipo `float64`
como contenedor de datos interno (`_data`).
Razones de esta decisión de diseño:
1. Compatibilidad directa con integradores numéricos estándar de la Fase 2
   (como `scipy.integrate.solve_ivp` o implementaciones personalizadas de Runge-Kutta).
   Estos integradores requieren un vector plano de estado unidimensional `y` en cada evaluación
   de la derivada `f(t, y)`.
2. Máxima eficiencia de memoria y rendimiento en operaciones vectorizadas, evitando la creación
   de nuevos objetos o conversiones continuas entre tuplas/listas/objetos y arrays durante
   cientos de miles de pasos de integración.
3. API orientada a objetos expresiva: se exponen propiedades de alto nivel (`position`, `velocity`,
   `mass`, `speed`, `radius`), combinando la robustez y semántica de un objeto inmutable/controlado
   con el rendimiento de NumPy.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt


class ArtemisState:
    """Vector de estado cinemático y dinámico del vehículo en coordenadas ECI J2000.

    El estado espacial comprende posición y velocidad respecto al centro de la Tierra en el
    marco inercial ECI (Earth-Centered Inertial, equinoccio J2000), junto con la masa instantánea
    y la marca de tiempo de simulación `t`.

    Estructura interna del vector de datos:
        [0]: Posición X en ECI (m)
        [1]: Posición Y en ECI (m)
        [2]: Posición Z en ECI (m)
        [3]: Velocidad Vx en ECI (m/s)
        [4]: Velocidad Vy en ECI (m/s)
        [5]: Velocidad Vz en ECI (m/s)
        [6]: Masa instantánea del vehículo m (kg)
    """

    __slots__ = ("_data", "_t")

    def __init__(
        self,
        position: npt.ArrayLike,
        velocity: npt.ArrayLike,
        mass: float,
        t: float = 0.0,
    ) -> None:
        """Inicializa una instancia de ArtemisState a partir de sus componentes físicas.

        Parámetros
        ----------
        position : ArrayLike (3,)
            Vector de posición [x, y, z] en metros en marco ECI J2000.
        velocity : ArrayLike (3,)
            Vector de velocidad [vx, vy, vz] en metros por segundo en marco ECI J2000.
        mass : float
            Masa instantánea del vehículo en kilogramos (estrictamente > 0).
        t : float, opcional
            Tiempo de simulación transcurrido en segundos (por defecto 0.0).
        """
        pos_arr = np.asarray(position, dtype=np.float64)
        vel_arr = np.asarray(velocity, dtype=np.float64)
        m_val = float(mass)
        t_val = float(t)

        if pos_arr.shape != (3,):
            raise ValueError(
                f"El vector de posición debe tener exactamente 3 elementos, "
                f"forma recibida: {pos_arr.shape}"
            )
        if vel_arr.shape != (3,):
            raise ValueError(
                f"El vector de velocidad debe tener exactamente 3 elementos, "
                f"forma recibida: {vel_arr.shape}"
            )

        data = np.empty(7, dtype=np.float64)
        data[0:3] = pos_arr
        data[3:6] = vel_arr
        data[6] = m_val

        self._validate_and_assign(data, t_val)

    def _validate_and_assign(self, data: npt.NDArray[np.float64], t: float) -> None:
        """Valida rigurosamente la finitud numérica y la coherencia del estado."""
        if data.shape != (7,):
            raise ValueError(
                f"El vector de estado debe tener forma (7,), forma recibida: {data.shape}"
            )
        if not np.all(np.isfinite(data)):
            raise ValueError(
                "El vector de estado contiene valores no finitos (NaN o Infinito)."
            )
        if not np.isfinite(t):
            raise ValueError(f"El tiempo de simulación debe ser finito. Valor recibido: {t}")
        if data[6] <= 0.0:
            raise ValueError(
                f"La masa debe ser estrictamente positiva (> 0 kg). Valor recibido: {data[6]}"
            )

        # Copia inmutable / desacoplada para evitar modificaciones externas no deseadas
        self._data: npt.NDArray[np.float64] = data.copy()
        self._data.flags.writeable = False
        self._t: float = t

    @property
    def t(self) -> float:
        """Tiempo de simulación transcurrido en segundos (s)."""
        return self._t

    @property
    def position(self) -> npt.NDArray[np.float64]:
        """Vector de posición [x, y, z] en ECI J2000 en metros (m)."""
        return self._data[0:3]

    @property
    def velocity(self) -> npt.NDArray[np.float64]:
        """Vector de velocidad [vx, vy, vz] en ECI J2000 en metros por segundo (m/s)."""
        return self._data[3:6]

    @property
    def mass(self) -> float:
        """Masa instantánea del vehículo en kilogramos (kg)."""
        return float(self._data[6])

    @property
    def speed(self) -> float:
        """Magnitud de la velocidad orbital ||v|| en m/s."""
        return float(np.linalg.norm(self._data[3:6]))

    @property
    def radius(self) -> float:
        """Distancia geocéntrica ||r|| desde el centro de la Tierra en metros (m)."""
        return float(np.linalg.norm(self._data[0:3]))

    def to_array(self) -> npt.NDArray[np.float64]:
        """Devuelve una copia del vector de estado plano de 7 elementos.

        Formato del array: [x, y, z, vx, vy, vz, m]
        Dtype: float64
        Forma: (7,)
        """
        return self._data.copy()

    @classmethod
    def from_array(
        cls,
        arr: npt.ArrayLike,
        t: float = 0.0,
    ) -> ArtemisState:
        """Crea una instancia de ArtemisState a partir de un arreglo plano de 7 elementos.

        Parámetros
        ----------
        arr : ArrayLike (7,)
            Vector de estado [x, y, z, vx, vy, vz, m].
        t : float, opcional
            Tiempo de simulación transcurrido en segundos (por defecto 0.0).

        Retorna
        -------
        ArtemisState
            Nueva instancia validada con los datos del arreglo.
        """
        arr_np = np.asarray(arr, dtype=np.float64)
        if arr_np.shape != (7,):
            raise ValueError(
                f"El vector plano de entrada debe tener forma (7,), forma recibida: {arr_np.shape}"
            )
        pos = arr_np[0:3]
        vel = arr_np[3:6]
        mass = float(arr_np[6])
        return cls(position=pos, velocity=vel, mass=mass, t=t)

    def copy(self) -> ArtemisState:
        """Crea una copia profunda de la instancia actual."""
        return ArtemisState.from_array(self._data, t=self._t)

    def __repr__(self) -> str:
        """Representación legible de la instancia con unidades explícitas."""
        pos_str = np.array2string(self._data[0:3], precision=3, separator=", ")
        vel_str = np.array2string(self._data[3:6], precision=3, separator=", ")
        return (
            f"ArtemisState("
            f"t={self._t:.3f} s, "
            f"pos={pos_str} m, "
            f"vel={vel_str} m/s, "
            f"mass={self.mass:.2f} kg, "
            f"radius={self.radius:.1f} m, "
            f"speed={self.speed:.2f} m/s)"
        )
