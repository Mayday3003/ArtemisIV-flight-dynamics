"""Módulo de targeting y corrección de la inyección translunar (TLI) con disparo.

Implementa un algoritmo de Newton-Raphson multivariable con cálculo de Jacobiano numérico
por diferencias finitas centrales, región de confianza (trust-region) simple y búsqueda lineal
con retroceso (backtracking line-search).

Alcance y suposiciones físicas (Fase 4):
- Propagación balística en el vacío (Tierra + Luna como masas puntuales, órbita circular plana).
- Maniobra de TLI modelada como una variación impulsiva instantánea de velocidad (delta-v).
- Tiempo de vuelo (t_flight) fijo y posición espacial objetivo prefijada en marco ECI.

Aviso pedagógico y limitaciones del modelo:
- Este modelo simplificado no representa trayectorias operativas reales de Artemis (NRHO).
- Sirve como herramienta de diseño preliminar de misiones, análisis de sensibilidad y docencia.
- TODO: En fases posteriores abordar optimizaciones de combustible, tiempo de vuelo libre,
  perturbación solar, armónicos zonales terrestres/lunares y targeting a NRHO.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from artemis_sim.constants import EARTH, MOON
from artemis_sim.ephemeris import (
    DEFAULT_LUNAR_CONFIG,
    LunarOrbitConfig,
    get_body_position,
)
from artemis_sim.state import ArtemisState
from artemis_sim.symplectic_solver import (
    impulsive_burn,
    propagate_reference_dop853,
    propagate_verlet,
)

# Alias de tipo para propagadores orbitales: (estado_inicial, t_flight) -> estado_final
Propagator = Callable[[ArtemisState, float], ArtemisState]


def make_dop853_propagator(
    rtol: float = 1e-12,
    atol: float = 1e-6,
    include_moon: bool = True,
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> Propagator:
    """Crea un propagador basado en el integrador adaptativo DOP853 de alta precisión."""

    def _propagate(state0: ArtemisState, t_flight: float) -> ArtemisState:
        t_final = state0.t + t_flight
        return propagate_reference_dop853(
            state0,
            t_final=t_final,
            include_moon=include_moon,
            rtol=rtol,
            atol=atol,
            lunar_config=lunar_config,
        )

    return _propagate


def make_verlet_propagator(
    dt: float = 1.0,
    include_moon: bool = True,
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> Propagator:
    """Crea un propagador basado en el integrador simpléctico Velocity Verlet."""

    def _propagate(state0: ArtemisState, t_flight: float) -> ArtemisState:
        t_final = state0.t + t_flight
        traj = propagate_verlet(
            state0,
            t_final=t_final,
            dt=dt,
            sample_every=int(1e9),  # Muestrear solo los extremos
            include_moon=include_moon,
            lunar_config=lunar_config,
        )
        return traj[-1]

    return _propagate


@dataclass(frozen=True, slots=True)
class ShootingResult:
    """Resultado del algoritmo de targeting por método del disparo.

    Parámetros
    ----------
    delta_v : NDArray[float64] (3,)
        Vector de incremento de velocidad convergido [dv_x, dv_y, dv_z] en m/s.
    delta_v_norm : float
        Norma euclídea ||delta_v|| en m/s.
    converged : bool
        Indica si el algoritmo alcanzó la tolerancia de posición requerida.
    iterations : int
        Número de iteraciones completadas de Newton-Raphson.
    residual_history : list[float]
        Historial de normas del residuo de posición (m) en cada iteración.
    final_residual : float
        Norma euclídea del residuo de posición final ||r_final - target_pos|| en metros (m).
    condition_number_history : list[float]
        Historial del número de condición de la matriz Jacobiana en cada iteración.
    message : str
        Mensaje explicativo del estado final del algoritmo.
    """

    delta_v: npt.NDArray[np.float64]
    delta_v_norm: float
    converged: bool
    iterations: int
    residual_history: list[float]
    final_residual: float
    condition_number_history: list[float]
    message: str


def shooting_residual(
    delta_v: npt.ArrayLike,
    state0: ArtemisState,
    target_pos: npt.ArrayLike,
    t_flight: float,
    propagator: Propagator,
) -> npt.NDArray[np.float64]:
    """Calcula el vector residuo de posición al final del tiempo de vuelo especificado.

    F(delta_v) = r_final(delta_v, t_flight) - target_pos

    Garantiza:
    - Función pura: no modifica en absoluto el estado `state0`.
    - Retorna un arreglo unidimensional float64 de tamaño (3,) con unidades de metros (m).

    Parámetros
    ----------
    delta_v : ArrayLike (3,)
        Vector de velocidad impulsiva aplicado a state0 en m/s.
    state0 : ArtemisState
        Estado orbital en el punto de encendido.
    target_pos : ArrayLike (3,)
        Posición espacial objetivo en ECI en metros (m).
    t_flight : float
        Tiempo de vuelo en segundos (s, > 0).
    propagator : Propagator
        Función que propaga (estado, t_flight) -> estado_final.

    Retorna
    -------
    NDArray[np.float64] (3,)
        Vector de discrepancia de posición en metros (m).
    """
    dv = np.asarray(delta_v, dtype=np.float64)
    target = np.asarray(target_pos, dtype=np.float64)

    # impulsive_burn devuelve un nuevo objeto sin mutar state0
    burned_state = impulsive_burn(state0, dv)
    final_state = propagator(burned_state, t_flight)

    return final_state.position - target


def numerical_jacobian(
    func: Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
    x: npt.NDArray[np.float64],
    h: float = 1e-2,
) -> npt.NDArray[np.float64]:
    """Calcula la matriz Jacobiana dF/dx por diferencias finitas centrales.

    J[:, j] = (func(x + h * e_j) - func(x - h * e_j)) / (2 * h)

    Justificación del paso de diferenciación h = 1e-2 m/s:
    Para problemas de dinámica orbital con perturbaciones gravitacionales,
    la aceleración es no lineal y la propagación acumula efectos durante varios días.
    Un paso de velocidad de h = 0.01 m/s (1 cm/s) representa un compromiso óptimo:
    - Evita el error de cancelación catastrófica por precisión de punto flotante doble
      (epsilon_mach^(1/3) * ||v|| ≈ 1e-16^(1/3) * 1e3 ≈ 6e-6 * 1e3 ≈ 6e-3 m/s).
    - Mantiene el error de truncamiento cuadrático O(h^2) bajo milímetros en posición.

    Parámetros
    ----------
    func : Callable[[NDArray[float64]], NDArray[float64]]
        Función vectorial a diferenciar.
    x : NDArray[float64] (n,)
        Punto de evaluación.
    h : float, opcional
        Paso de perturbación finita (por defecto 1e-2).

    Retorna
    -------
    NDArray[np.float64] (m, n)
        Matriz Jacobiana evaluada en x.
    """
    n = len(x)
    f0 = func(x)
    m = len(f0)

    jacobian = np.empty((m, n), dtype=np.float64)

    for j in range(n):
        x_plus = x.copy()
        x_minus = x.copy()
        x_plus[j] += h
        x_minus[j] -= h

        f_plus = func(x_plus)
        f_minus = func(x_minus)

        jacobian[:, j] = (f_plus - f_minus) / (2.0 * h)

    return jacobian


def initial_guess_vis_viva(
    state0: ArtemisState,
    target_distance_m: float,
) -> npt.NDArray[np.float64]:
    """Estima el delta-v prógrado inicial para alcanzar una distancia geocéntrica dada.

    Aproximación kepleriana analítica de dos cuerpos (vis-viva):
    Asume una órbita circular de aparcamiento en r1 = ||r0|| y una elipse de transferencia
    con perigeo en r1 y apogeo en r2 = target_distance_m.
    - Semieje mayor: a = (r1 + r2) / 2
    - Velocidad requerida en el perigeo: v_trans = sqrt(mu_E * (2/r1 - 1/a))
    - Velocidad circular previa: v_circ = sqrt(mu_E / r1)
    - delta-v prógrado = (v_trans - v_circ) * (v0 / ||v0||)

    Documentación de modelo:
    Esta aproximación ignora por completo la gravedad de la Luna y las no coplanaridades,
    proporcionando exclusivamente una semilla inicial cualitativa para el solver numérico.

    Parámetros
    ----------
    state0 : ArtemisState
        Estado orbital en el punto de encendido.
    target_distance_m : float
        Distancia geocéntrica del apogeo deseado en metros (m).

    Retorna
    -------
    NDArray[np.float64] (3,)
        Vector delta-v inicial estimado en m/s.
    """
    r1 = state0.radius
    r2 = float(target_distance_m)

    if r2 <= r1:
        raise ValueError(
            f"La distancia objetivo r2 ({r2} m) debe ser mayor que el radio r1 ({r1} m)."
        )

    mu = EARTH.mu_m3_s2
    a = (r1 + r2) / 2.0
    v_trans = np.sqrt(mu * (2.0 / r1 - 1.0 / a))
    v0_norm = state0.speed

    if v0_norm == 0.0:
        raise ValueError("La velocidad de state0 no puede ser cero en la estimación vis-viva.")

    delta_v_mag = v_trans - v0_norm
    u_vel = state0.velocity / v0_norm

    return np.asarray(delta_v_mag * u_vel, dtype=np.float64)


def moon_relative_target(
    offset_m: npt.ArrayLike,
    t_arrival: float,
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG,
) -> npt.NDArray[np.float64]:
    """Calcula la posición objetivo en marco ECI referenciada al centro de la Luna.

    target_pos = r_Luna(t_arrival) + offset_m

    Permite formular misiones de aproximación lunar (sobrevuelo por el lado iluminado,
    oculto o paso por el periselenio) sin depender de coordenadas fijas geocéntricas.

    Parámetros
    ----------
    offset_m : ArrayLike (3,)
        Desplazamiento relativo [dx, dy, dz] en metros respecto al centro lunar.
    t_arrival : float
        Tiempo geocéntrico estimado de llegada a la Luna en segundos (s).
    lunar_config : LunarOrbitConfig, opcional
        Parámetros orbitales para la Luna.

    Retorna
    -------
    NDArray[np.float64] (3,)
        Posición objetivo en coordenadas ECI en metros (m).
    """
    offset = np.asarray(offset_m, dtype=np.float64)
    if offset.shape != (3,):
        raise ValueError(f"offset_m debe tener tamaño (3,), forma recibida: {offset.shape}")

    r_moon = get_body_position(MOON, t_arrival, config=lunar_config)
    return r_moon + offset


def solve_tli_shooting(
    state0: ArtemisState,
    target_pos: npt.ArrayLike,
    t_flight: float,
    dv_guess: npt.ArrayLike,
    propagator: Propagator | None = None,
    tol_m: float = 1.0,
    max_iter: int = 30,
    fd_step: float = 1e-2,
    max_step_ms: float = 500.0,
) -> ShootingResult:
    """Resuelve el problema de dos puntos de frontera (targeting) mediante Newton-Raphson.

    Estrategia de convergencia:
    1. Calcula el residuo vectorial F(dv) = r_final - target_pos y el Jacobiano numérico J.
    2. Resuelve el sistema lineal J * d = -F para hallar la dirección de corrección d.
       Si J es numéricamente singular (LinAlgError), aborta limpiamente sin excepción.
    3. Acota la norma de corrección ||d|| <= max_step_ms (región de confianza simple).
    4. Búsqueda lineal con retroceso (backtracking): divide el paso a la mitad hasta 8 veces
       si la norma del residuo no disminuye estrictamente.
    5. Criterio de parada: ||F|| < tol_m o se agotan las iteraciones `max_iter`.
    6. Monitoreo de condicionamiento: calcula cond(J) y emite un warning si cond > 1e10.

    Parámetros
    ----------
    state0 : ArtemisState
        Estado inicial de partida (antes del encendido de TLI).
    target_pos : ArrayLike (3,)
        Posición cartesiana objetivo en marco ECI en metros (m).
    t_flight : float
        Tiempo de vuelo en segundos (estrictamente > 0).
    dv_guess : ArrayLike (3,)
        Suposición inicial del vector de encendido [dv_x, dv_y, dv_z] en m/s.
    propagator : Propagator, opcional
        Propagador orbital a utilizar. Si es None, utiliza DOP853 de alta precisión.
    tol_m : float, opcional
        Tolerancia máxima permitida en el residuo de posición (por defecto 1.0 m).
    max_iter : int, opcional
        Número máximo de iteraciones de Newton-Raphson (por defecto 30).
    fd_step : float, opcional
        Paso de diferenciación finita en m/s (por defecto 1e-2).
    max_step_ms : float, opcional
        Paso máximo por iteración en m/s para región de confianza (por defecto 500.0 m/s).

    Retorna
    -------
    ShootingResult
        Estructura inmutable con el vector convergido, residuos, número de condición y diagnósticos.
    """
    if t_flight <= 0.0:
        raise ValueError(
            f"El tiempo de vuelo debe ser estrictamente positivo (> 0). Valor: {t_flight}"
        )
    if tol_m <= 0.0:
        raise ValueError(f"La tolerancia tol_m debe ser positiva (> 0). Valor: {tol_m}")
    target_arr = np.asarray(target_pos, dtype=np.float64)
    if target_arr.shape != (3,):
        raise ValueError(f"target_pos debe tener forma (3,), forma recibida: {target_arr.shape}")

    prop = propagator if propagator is not None else make_dop853_propagator()

    current_dv = np.asarray(dv_guess, dtype=np.float64).copy()
    if current_dv.shape != (3,):
        raise ValueError(f"dv_guess debe tener forma (3,), forma recibida: {current_dv.shape}")

    residual_history: list[float] = []
    condition_history: list[float] = []

    # Evaluación inicial del residuo
    res_vec = shooting_residual(current_dv, state0, target_arr, t_flight, prop)
    res_norm = float(np.linalg.norm(res_vec))
    residual_history.append(res_norm)

    if res_norm < tol_m:
        return ShootingResult(
            delta_v=current_dv,
            delta_v_norm=float(np.linalg.norm(current_dv)),
            converged=True,
            iterations=0,
            residual_history=residual_history,
            final_residual=res_norm,
            condition_number_history=[],
            message="Convergencia inmediata: la suposición inicial ya satisface la tolerancia.",
        )

    for it in range(1, max_iter + 1):
        # 1. Jacobiano numérico
        def _f_wrap(dv_val: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
            return shooting_residual(dv_val, state0, target_arr, t_flight, prop)

        jac = numerical_jacobian(_f_wrap, current_dv, h=fd_step)

        # 2. Número de condición y aviso
        cond_num = float(np.linalg.cond(jac))
        condition_history.append(cond_num)

        if cond_num > 1e10:
            warnings.warn(
                f"Número de condición elevado en iteración {it}: cond(J) = {cond_num:.2e} > 1e10. "
                f"El Jacobiano puede estar mal condicionado.",
                UserWarning,
                stacklevel=2,
            )

        # 3. Solución del sistema lineal J * step = -res_vec
        try:
            step = np.linalg.solve(jac, -res_vec)
        except np.linalg.LinAlgError as err:
            return ShootingResult(
                delta_v=current_dv,
                delta_v_norm=float(np.linalg.norm(current_dv)),
                converged=False,
                iterations=it,
                residual_history=residual_history,
                final_residual=res_norm,
                condition_number_history=condition_history,
                message=f"Fallo algebraico: matriz Jacobiana singular o no invertible ({err}).",
            )

        # 4. Región de confianza (trust-region simple)
        step_norm = float(np.linalg.norm(step))
        if step_norm > max_step_ms:
            step = step * (max_step_ms / step_norm)

        # 5. Búsqueda lineal con retroceso (backtracking)
        alpha = 1.0
        new_dv = current_dv + step
        new_res_vec = shooting_residual(new_dv, state0, target_arr, t_flight, prop)
        new_res_norm = float(np.linalg.norm(new_res_vec))

        backtrack_count = 0
        while backtrack_count < 8:
            if new_res_norm < res_norm:
                break
            alpha *= 0.5
            new_dv = current_dv + alpha * step
            new_res_vec = shooting_residual(new_dv, state0, target_arr, t_flight, prop)
            new_res_norm = float(np.linalg.norm(new_res_vec))
            backtrack_count += 1

        current_dv = new_dv
        res_vec = new_res_vec
        res_norm = new_res_norm
        residual_history.append(res_norm)

        if res_norm < tol_m:
            return ShootingResult(
                delta_v=current_dv,
                delta_v_norm=float(np.linalg.norm(current_dv)),
                converged=True,
                iterations=it,
                residual_history=residual_history,
                final_residual=res_norm,
                condition_number_history=condition_history,
                message=f"Convergencia exitosa en {it} iteraciones. Residuo: {res_norm:.3e} m.",
            )

    return ShootingResult(
        delta_v=current_dv,
        delta_v_norm=float(np.linalg.norm(current_dv)),
        converged=False,
        iterations=max_iter,
        residual_history=residual_history,
        final_residual=res_norm,
        condition_number_history=condition_history,
        message=f"Máximo de iteraciones alcanzado ({max_iter}) sin alcanzar tol_m = {tol_m} m.",
    )
