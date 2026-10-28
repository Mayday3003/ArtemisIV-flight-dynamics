"""Exporta la misión (Fases 1–3) a frontend/data/mission.json para el visualizador 3D.

Uso (desde la raíz del repositorio):
    python scripts/export_mission.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from artemis_sim.cr3bp import MU, UNITS  # noqa: E402
from artemis_sim.export import MissionTrajectory, hermite_interpolate, resample, to_json  # noqa: E402
from artemis_sim.mission import build_mission_phases_1_to_3  # noqa: E402
from artemis_sim.periodic_orbits import PeriodicOrbit, find_nrho  # noqa: E402

OUT = ROOT / "frontend" / "data" / "mission.json"

# Paso de muestreo por fase (s): fino donde la nave cambia rápido, grueso en el tránsito.
DT_BY_PHASE = {"ascent": 1.0, "parking": 20.0, "transit": 60.0}


def nrho_payload(orbit: PeriodicOrbit, points: int = 600) -> dict[str, object]:
    """NRHO en el marco rotante geocéntrico (el "rot" del visualizador): origen en la Tierra,
    x hacia la Luna, z normal al plano lunar. Se muestra fija respecto de la Luna."""
    s = orbit.sample(points)
    km = UNITS.length_m / 1e3
    peri, apo = orbit.moon_distance_range_m()
    return {
        "nrho": {
            "name": "NRHO 9:2 L2 sur (Gateway)",
            "frame": "EARTH_MOON_ROTATING_GEOCENTRIC",
            "period_s": round(orbit.period * UNITS.time_s, 3),
            "perilune_km": round(peri / 1e3, 3),
            "apolune_km": round(apo / 1e3, 3),
            "stability_index": round(orbit.stability_index, 6),
            "x": [round(float(v), 4) for v in (s[0] + MU) * km],
            "y": [round(float(v), 4) for v in s[1] * km],
            "z": [round(float(v), 4) for v in s[2] * km],
        }
    }


def main() -> None:
    print("Construyendo la misión (ascenso → aparcamiento → TLI → tránsito)…")
    raw, summary = build_mission_phases_1_to_3()
    print(f"  MECO          t = {summary.t_meco_s:8.1f} s")
    print(f"  Inserción     Δv = {summary.dv_insertion_m_s:7.1f} m/s")
    print(f"  Inclinación   i = {np.degrees(summary.parking_inclination_rad):6.2f}°")
    print(
        f"  TLI           t = {summary.t_tli_s:8.1f} s   Δv = {summary.dv_tli_m_s:7.1f} m/s"
        f"   ({summary.shooting.iterations} iteraciones)"
    )
    print(f"  Llegada       h_Luna = {summary.flyby_altitude_m / 1e3:8.1f} km")

    traj = resample(raw, DT_BY_PHASE)

    # Puntos de control fuera de la malla (para validar la interpolación del navegador)
    rng = np.random.default_rng(42)
    t_cp = np.sort(rng.uniform(raw.t[0], raw.t[-1], 5))
    checkpoints = MissionTrajectory(
        t=t_cp, y=hermite_interpolate(raw.t, raw.y, t_cp), phases=raw.phases
    )

    nrho = find_nrho()
    print(
        f"  NRHO 9:2      P = {nrho.period_days:.3f} d   perilunio/apolunio = "
        + " / ".join(f"{d / 1e3:,.0f} km" for d in nrho.moon_distance_range_m())
    )

    path = to_json(traj, OUT, checkpoints=checkpoints, extra=nrho_payload(nrho))
    print(
        f"Exportado: {path.relative_to(ROOT)}  ({traj.t.size} muestras, "
        f"{path.stat().st_size / 1e6:.2f} MB)"
    )


if __name__ == "__main__":
    main()
