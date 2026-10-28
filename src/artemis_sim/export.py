"""Exportación de trayectorias de misión a JSON por columnas para el visualizador web.

El simulador trabaja en SI estricto (m, kg, s). El archivo exportado usa unidades cómodas
para la escena 3D (km, km/s, t). Esta conversión ocurre únicamente en `to_json`.

Formato (schema_version = 1):
{
  "schema_version": 1,
  "units": {"length": "km", "time": "s", "velocity": "km/s", "mass": "t"},
  "frame": "ECI_J2000",
  "bodies": {...},                  # radios, rotación terrestre y órbita lunar
  "phases": [{"id", "name", "t_start", "t_end"}],
  "events": [{"t", "label"}],
  "samples": {"t", "x", "y", "z", "vx", "vy", "vz", "m", "phase_index"},
  "checkpoints": [...],             # estados exactos en instantes fuera de la malla
  "nrho": {...}                     # opcional: NRHO en el marco rotante geocéntrico (km)
}
Las columnas permiten cargar cada arreglo directamente como Float32Array/Float64Array.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from artemis_sim.constants import EARTH, EARTH_ROTATION, MOON
from artemis_sim.ephemeris import DEFAULT_LUNAR_CONFIG, LunarOrbitConfig

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class MissionPhase:
    """Tramo de la misión con el mismo régimen físico (s)."""

    id: str
    name: str
    t_start: float
    t_end: float


@dataclass(frozen=True, slots=True)
class MissionEvent:
    """Suceso puntual de la misión (s)."""

    t: float
    label: str


@dataclass(slots=True)
class MissionTrajectory:
    """Trayectoria completa en SI: t (N,) en s y y (7, N) = [x, y, z, vx, vy, vz, m]."""

    t: npt.NDArray[np.float64]
    y: npt.NDArray[np.float64]
    phases: list[MissionPhase]
    events: list[MissionEvent] = field(default_factory=list)
    lunar_config: LunarOrbitConfig = DEFAULT_LUNAR_CONFIG

    def __post_init__(self) -> None:
        if self.y.shape != (7, self.t.size):
            raise ValueError(f"y debe tener forma (7, {self.t.size}); recibido {self.y.shape}.")
        if self.t.size >= 2 and not np.all(np.diff(self.t) > 0.0):
            raise ValueError("Los instantes t deben ser estrictamente crecientes.")


def concatenate_segments(
    segments: list[tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Une tramos (t, y) consecutivos; ante instantes repetidos conserva el último.

    En una discontinuidad física (separación de etapas, encendido impulsivo) el mismo instante
    aparece al final de un tramo y al inicio del siguiente; se conserva el estado posterior.
    """
    t_all = np.concatenate([seg[0] for seg in segments])
    y_all = np.concatenate([seg[1] for seg in segments], axis=1)
    order = np.argsort(t_all, kind="stable")
    t_all, y_all = t_all[order], y_all[:, order]
    keep = np.ones(t_all.size, dtype=bool)
    keep[:-1] = np.diff(t_all) > 0.0  # de cada grupo de instantes iguales queda el último
    return t_all[keep], y_all[:, keep]


def hermite_interpolate(
    t: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    t_query: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Interpola el estado en t_query.

    Posición: Hermite cúbico usando la velocidad como derivada (error O(h^4)), suficientemente
    preciso para muestrear órbitas con pasos de minutos. Velocidad y masa: interpolación lineal.
    """
    tq = np.asarray(t_query, dtype=np.float64)
    if np.any(tq < t[0]) or np.any(tq > t[-1]):
        raise ValueError("t_query fuera del intervalo de la trayectoria.")
    k = np.clip(np.searchsorted(t, tq, side="right") - 1, 0, t.size - 2)
    t0, t1 = t[k], t[k + 1]
    h = t1 - t0
    s = (tq - t0) / h
    h00 = 2 * s**3 - 3 * s**2 + 1
    h10 = s**3 - 2 * s**2 + s
    h01 = -2 * s**3 + 3 * s**2
    h11 = s**3 - s**2

    out = np.empty((7, tq.size), dtype=np.float64)
    p0, p1 = y[0:3, k], y[0:3, k + 1]
    v0, v1 = y[3:6, k], y[3:6, k + 1]
    out[0:3] = h00 * p0 + h10 * h * v0 + h01 * p1 + h11 * h * v1
    out[3:7] = (1 - s) * y[3:7, k] + s * y[3:7, k + 1]
    return out


def resample(
    traj: MissionTrajectory,
    dt_by_phase: dict[str, float],
) -> MissionTrajectory:
    """Remuestrea cada fase con su propio paso, incluyendo siempre los extremos de cada fase."""
    times: list[npt.NDArray[np.float64]] = []
    for ph in traj.phases:
        dt = dt_by_phase.get(ph.id)
        if dt is None or dt <= 0.0:
            raise ValueError(f"Falta un paso de muestreo positivo para la fase '{ph.id}'.")
        grid = np.arange(ph.t_start, ph.t_end, dt)
        times.append(np.append(grid, ph.t_end))
    tq = np.unique(np.concatenate(times))
    return MissionTrajectory(
        t=tq,
        y=hermite_interpolate(traj.t, traj.y, tq),
        phases=traj.phases,
        events=traj.events,
        lunar_config=traj.lunar_config,
    )


def phase_index(traj: MissionTrajectory) -> npt.NDArray[np.int64]:
    """Índice de fase de cada muestra (en los bordes se asigna la fase que empieza)."""
    idx = np.zeros(traj.t.size, dtype=np.int64)
    for i, ph in enumerate(traj.phases):
        idx[traj.t >= ph.t_start] = i
    return idx


def to_dict(
    traj: MissionTrajectory,
    checkpoints: MissionTrajectory | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convierte la trayectoria al diccionario del formato JSON (km, km/s, t).

    `extra` agrega claves opcionales de nivel superior (p. ej. "nrho") sin cambiar el esquema.
    """
    km = 1e-3
    lc = traj.lunar_config

    def col(values: npt.NDArray[np.float64], decimals: int) -> list[float]:
        return [round(float(v), decimals) for v in values]

    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "units": {"length": "km", "time": "s", "velocity": "km/s", "mass": "t", "angle": "rad"},
        "frame": "ECI_J2000",
        "bodies": {
            "earth": {
                "radius_km": EARTH.equatorial_radius_m * km,
                "rotation_rate_rad_s": EARTH_ROTATION.omega_rad_s,
            },
            "moon": {
                "radius_km": MOON.equatorial_radius_m * km,
                "orbit_radius_km": lc.orbital_radius_m * km,
                "mean_motion_rad_s": lc.mean_motion_rad_s,
                "phase0_rad": lc.initial_phase_rad,
                "inclination_rad": lc.inclination_rad,
                "raan_rad": lc.raan_rad,
            },
        },
        "phases": [
            {"id": p.id, "name": p.name, "t_start": round(p.t_start, 3), "t_end": round(p.t_end, 3)}
            for p in traj.phases
        ],
        "events": [{"t": round(e.t, 3), "label": e.label} for e in traj.events],
        "samples": {
            "t": col(traj.t, 3),
            "x": col(traj.y[0] * km, 4),
            "y": col(traj.y[1] * km, 4),
            "z": col(traj.y[2] * km, 4),
            "vx": col(traj.y[3] * km, 7),
            "vy": col(traj.y[4] * km, 7),
            "vz": col(traj.y[5] * km, 7),
            "m": col(traj.y[6] * 1e-3, 4),
            "phase_index": [int(i) for i in phase_index(traj)],
        },
    }
    if checkpoints is not None:
        data["checkpoints"] = [
            {
                "t": round(float(checkpoints.t[i]), 3),
                "r_km": [round(float(v) * km, 4) for v in checkpoints.y[0:3, i]],
                "v_km_s": [round(float(v) * km, 7) for v in checkpoints.y[3:6, i]],
            }
            for i in range(checkpoints.t.size)
        ]
    if extra:
        data.update(extra)
    return data


def to_json(
    traj: MissionTrajectory,
    path: str | Path,
    checkpoints: MissionTrajectory | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Escribe la trayectoria en JSON compacto (sin NaN ni infinitos)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = to_dict(traj, checkpoints, extra)
    out.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return out


def from_json(path: str | Path) -> MissionTrajectory:
    """Lee un archivo exportado y lo devuelve en SI (para pruebas y análisis)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Versión de formato no soportada: {data.get('schema_version')}")
    smp = data["samples"]
    y = np.vstack(
        [np.asarray(smp[k], dtype=np.float64) * 1e3 for k in ("x", "y", "z", "vx", "vy", "vz", "m")]
    )
    moon = data["bodies"]["moon"]
    return MissionTrajectory(
        t=np.asarray(smp["t"], dtype=np.float64),
        y=y,
        phases=[MissionPhase(**p) for p in data["phases"]],
        events=[MissionEvent(**e) for e in data["events"]],
        lunar_config=LunarOrbitConfig(
            orbital_radius_m=moon["orbit_radius_km"] * 1e3,
            mean_motion_rad_s=moon["mean_motion_rad_s"],
            initial_phase_rad=moon["phase0_rad"],
            inclination_rad=moon["inclination_rad"],
            raan_rad=moon["raan_rad"],
        ),
    )
