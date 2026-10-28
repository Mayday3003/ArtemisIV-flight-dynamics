"""Exporta la misión (Fases 1–4: despegue → NRHO) a frontend/data/mission.json para la web.

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
from artemis_sim.mission import build_mission_phases_1_to_4  # noqa: E402
from artemis_sim.periodic_orbits import PeriodicOrbit  # noqa: E402

OUT = ROOT / "frontend" / "data" / "mission.json"

# Paso de muestreo por fase (s): fino donde la nave cambia rápido, grueso en el tránsito.
DT_BY_PHASE = {"ascent": 1.0, "parking": 20.0, "transit": 60.0, "nrho": 60.0}


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
    print("Construyendo la misión (ascenso → aparcamiento → TLI → OPF → NRI → NRHO)…")
    raw, summary = build_mission_phases_1_to_4()
    s3 = summary.phases_1_to_3
    print(f"  MECO          t = {s3.t_meco_s:8.1f} s")
    print(f"  Inserción     Δv = {s3.dv_insertion_m_s:7.1f} m/s")
    print(f"  Inclinación   i = {np.degrees(s3.parking_inclination_rad):6.2f}°")
    print(f"  TLI (EUS)     t = {summary.t_tli_s:8.1f} s   Δv = {summary.dv_tli_m_s:7.1f} m/s")
    print(
        f"  OPF (Orion)   +{(summary.t_opf_s - summary.t_tli_s) / 86400:.2f} d   "
        f"Δv = {summary.dv_opf_m_s:6.1f} m/s   altitud {summary.opf_altitude_m / 1e3:.0f} km"
    )
    print(
        f"  NRI (Orion)   +{(summary.t_nri_s - summary.t_tli_s) / 86400:.2f} d   "
        f"Δv = {summary.dv_nri_m_s:6.1f} m/s"
    )
    print(
        f"  Orion + I-Hab {summary.mass_after_tli_kg / 1e3:.1f} t → "
        f"{summary.mass_in_nrho_kg / 1e3:.1f} t  (capacidad del ESM: "
        f"{summary.orion_dv_capability_m_s:.0f} m/s)"
    )

    traj = resample(raw, DT_BY_PHASE)

    # Puntos de control fuera de la malla (para validar la interpolación del navegador)
    rng = np.random.default_rng(42)
    t_cp = np.sort(rng.uniform(raw.t[0], raw.t[-1], 5))
    checkpoints = MissionTrajectory(
        t=t_cp, y=hermite_interpolate(raw.t, raw.y, t_cp), phases=raw.phases
    )

    nrho = summary.nrho
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
