"""Punto de entrada único: la misión Artemis IV completa, del despegue al alunizaje.

    run_mission(MissionConfig()) → MissionRun(trajectory, summary)

Encadena las cinco fases; el estado final de cada una es el inicial de la siguiente:
1. Ascenso desde el LC-39B hasta el MECO (RK45 con eventos, `ascent_solver`).
2. Inserción de la EUS y órbita de aparcamiento (Verlet, `symplectic_solver`).
3. TLI por el método del disparo y ventana de lanzamiento (`shooting_method`).
4. Transferencia TLI → OPF → NRI a la NRHO 9:2 de Gateway (`nrho_transfer`, `periodic_orbits`).
5. DOI, planeo y descenso propulsado del HLS al polo sur (`descent_solver`, `lunar_gravity`).
La lógica de encadenado vive en `mission.py`; este módulo fija la configuración y resume.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from artemis_sim.export import MissionTrajectory
from artemis_sim.mission import MissionSummaryPhase5, build_mission_phases_1_to_5


@dataclass(frozen=True, slots=True)
class MissionConfig:
    """Parámetros de alto nivel de la misión.

    nrho_revolutions : vueltas completas en la NRHO antes de la DOI (acoplamiento con Gateway
        y paso de la tripulación al HLS).
    """

    nrho_revolutions: float = 1.0


@dataclass(frozen=True, slots=True)
class MissionRun:
    """Trayectoria continua (ECI, SI) y valores clave de todas las fases."""

    trajectory: MissionTrajectory
    summary: MissionSummaryPhase5

    def key_numbers(self) -> dict[str, float]:
        """Números de la misión en unidades de ingeniería (para el informe y la consola)."""
        s5 = self.summary
        s4 = s5.phases_1_to_4
        s3 = s4.phases_1_to_3
        d = s5.descent
        day = 86400.0
        return {
            "t_meco_s": s3.t_meco_s,
            "parking_inclination_deg": float(np.degrees(s3.parking_inclination_rad)),
            "dv_insertion_ms": s3.dv_insertion_m_s,
            "t_tli_h": s4.t_tli_s / 3600.0,
            "dv_tli_ms": s4.dv_tli_m_s,
            "dv_opf_ms": s4.dv_opf_m_s,
            "dv_nri_ms": s4.dv_nri_m_s,
            "opf_alt_km": s4.opf_altitude_m / 1e3,
            "opf_after_tli_d": (s4.t_opf_s - s4.t_tli_s) / day,
            "nri_after_tli_d": (s4.t_nri_s - s4.t_tli_s) / day,
            "orion_mass_tli_t": s4.mass_after_tli_kg / 1e3,
            "orion_mass_nrho_t": s4.mass_in_nrho_kg / 1e3,
            "orion_dv_capability_ms": s4.orion_dv_capability_m_s,
            "orion_dv_used_pct": 100.0
            * (s4.dv_opf_m_s + s4.dv_nri_m_s)
            / s4.orion_dv_capability_m_s,
            "nrho_period_d": s4.nrho.period_days,
            "nrho_stability": s4.nrho.stability_index,
            "dv_doi_ms": d.dv_doi_m_s,
            "coast_h": d.t_pdi / 3600.0,
            "pdi_lat_deg": d.pdi_lat_lon_deg[0],
            "dv_powered_ms": d.dv_powered_m_s,
            "powered_s": d.t_touchdown - d.t_pdi,
            "max_throttle_pct": 100.0 * d.max_throttle_fraction,
            "hls_mass_initial_t": d.mass_initial_kg / 1e3,
            "hls_mass_pdi_t": d.mass_at_pdi_kg / 1e3,
            "hls_mass_landed_t": d.mass_landed_kg / 1e3,
            "landing_error_m": d.landing_error_m,
            "touchdown_speed_ms": float(np.linalg.norm(d.touchdown_velocity)),
            "site_lat_deg": d.site.lat_deg,
            "site_lon_deg": d.site.lon_deg,
            "mission_days": float(self.trajectory.t[-1]) / day,
        }


def run_mission(config: MissionConfig | None = None) -> MissionRun:
    """Construye la misión completa (tarda ~4 min: la transferencia a la NRHO es lo caro)."""
    config = config or MissionConfig()
    trajectory, summary = build_mission_phases_1_to_5(config.nrho_revolutions)
    return MissionRun(trajectory, summary)
