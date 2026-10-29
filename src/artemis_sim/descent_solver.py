"""Descenso del HLS desde la NRHO hasta el polo sur lunar (Fase 5).

Todo se integra en el marco fijo a la Luna (`moon_frame`), que rota con ω = n ẑ. Ahí sí hay
fuerzas ficticias, al revés que en el ascenso (ECI):
    r̈ = ∇U_L(r) + μ_E [(r_E − r)/|r_E − r|³ − r_E/|r_E|³] − 2 ω × ṙ − ω × (ω × r) + T/m,
    ṁ = −|T| / (Isp g0),
con U_L el campo GRGM1200A (`lunar_gravity`) y r_E = (d, 0, 0) la Tierra. El término de marea
de la Tierra es el mismo término indirecto del CR3BP: el modelo es coherente con la NRHO.

Perfil (como el del Apolo, adaptado a la NRHO):
1. DOI (descent orbit insertion) poco antes del perilunio norte de la NRHO: maniobra
   impulsiva que deja una elipse con perilunio a 15 km media vuelta más allá, sobre el sur,
   ~480 km antes del sitio (`choose_doi_tau`).
2. Planeo de ~1,5 h por la elipse con la gravedad completa (los mascons la deforman).
3. Descenso propulsado (PDI) en el perilunio, con E-guidance en tres tramos:
   frenado → "high gate" → aproximación → "low gate" (100 m sobre el sitio) → descenso final
   vertical hasta tocar el suelo a ~1 m/s.

E-guidance (guiado de energía mínima con tiempo final fijo, la familia del guiado del LM):
con t_go el tiempo que falta y g la aceleración no propulsiva (supuesta constante),
    ZEM = r_f − (r + v t_go + ½ g t_go²),   ZEV = v_f − (v + g t_go),
    a_T = 6 ZEM / t_go² − 2 ZEV / t_go.
Es la aceleración que llega al objetivo con la mínima ∫|a_T|² dt; se recalcula en cada
instante (lazo cerrado), así que corrige las perturbaciones de los mascons. El empuje se
satura entre el mínimo y el máximo del motor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from artemis_sim.constants import EARTH, G0_M_S2, HLS, HLS_MIN_THROTTLE, MOON, StageSpec
from artemis_sim.cr3bp import UNITS, FloatArray
from artemis_sim.ephemeris import LUNAR_MEAN_MOTION_RAD_S
from artemis_sim.lunar_gravity import LunarGravityField
from artemis_sim.moon_frame import latitude_longitude_deg, rotating_to_moon_fixed, surface_point
from artemis_sim.periodic_orbits import PeriodicOrbit

PDI_ALTITUDE_M: Final[float] = 15e3
TOUCHDOWN_SPEED_M_S: Final[float] = 1.0


@dataclass(frozen=True, slots=True)
class LandingSite:
    """Sitio de alunizaje sobre la esfera de radio medio lunar."""

    name: str
    lat_deg: float
    lon_deg: float
    radius_m: float = MOON.equatorial_radius_m

    @property
    def position(self) -> FloatArray:
        return surface_point(self.lat_deg, self.lon_deg, self.radius_m)


# Punto más austral de la traza que deja la NRHO 9:2 sin cambio de plano (su inclinación es
# ~93°, así que la traza llega hasta 86,8° S). La NRHO es periódica en el marco rotante, y por
# tanto también en el MF: su geometría, y este punto, no dependen de la fecha. Está dentro de la
# franja de 6° alrededor del polo sur donde la NASA ubicó las regiones candidatas de Artemis III.
SOUTH_POLE_SITE: Final[LandingSite] = LandingSite("Región polar sur", -86.8, 179.0)

# Distancia sobre el suelo del PDI a la "high gate" (en el Apolo, ~480 km del PDI al sitio).
BRAKING_RANGE_M: Final[float] = 480e3
HIGH_GATE_BACK_M: Final[float] = 6_000.0


class MoonFixedDynamics:
    """Aceleración no propulsiva en el MF: gravedad lunar + marea terrestre + fuerzas ficticias."""

    def __init__(
        self,
        gravity: LunarGravityField,
        include_earth: bool = True,
        omega_rad_s: float = LUNAR_MEAN_MOTION_RAD_S,
    ) -> None:
        self.gravity = gravity
        self.include_earth = include_earth
        self.omega = np.array([0.0, 0.0, omega_rad_s])
        self.r_earth = np.array([UNITS.length_m, 0.0, 0.0])

    def acceleration(self, r: FloatArray, v: FloatArray) -> FloatArray:
        a = self.gravity.acceleration(r)
        if self.include_earth:
            d = self.r_earth - r
            a = a + EARTH.mu_m3_s2 * (
                d / np.linalg.norm(d) ** 3 - self.r_earth / np.linalg.norm(self.r_earth) ** 3
            )
        return a - 2.0 * np.cross(self.omega, v) - np.cross(self.omega, np.cross(self.omega, r))

    def derivatives(self, _t: float, y: FloatArray) -> FloatArray:
        """Planeo sin empuje: y = [r, v] (6)."""
        return np.concatenate([y[3:6], self.acceleration(y[0:3], y[3:6])])


def descent_orbit_insertion(
    state_mf: FloatArray,
    dynamics: MoonFixedDynamics,
    periapsis_radius_m: float,
) -> FloatArray:
    """Δv (MF) de la DOI: velocidad inercial horizontal de una elipse kepleriana cuyo apoapsis
    es la posición actual y cuyo periapsis está a `periapsis_radius_m`."""
    r, v = state_mf[0:3], state_mf[3:6]
    v_in = v + np.cross(dynamics.omega, r)
    r_a = float(np.linalg.norm(r))
    horizontal = v_in - np.dot(v_in, r) / r_a**2 * r
    gm = dynamics.gravity.gm
    v_a = np.sqrt(2.0 * gm * periapsis_radius_m / (r_a * (r_a + periapsis_radius_m)))
    return np.asarray(v_a * horizontal / np.linalg.norm(horizontal) - v_in)


def e_guidance(
    r: FloatArray, v: FloatArray, g: FloatArray, r_f: FloatArray, v_f: FloatArray, t_go: float
) -> FloatArray:
    """Aceleración de empuje del E-guidance (ver la cabecera del módulo)."""
    zem = r_f - (r + v * t_go + 0.5 * g * t_go**2)
    zev = v_f - (v + g * t_go)
    return np.asarray(6.0 * zem / t_go**2 - 2.0 * zev / t_go)


def choose_doi_tau(orbit: PeriodicOrbit, site: LandingSite = SOUTH_POLE_SITE) -> float:
    """Fase τ ∈ [0, 1) de la NRHO en la que hacer la DOI.

    Tras una DOI horizontal el punto de la maniobra es el apolunio de la elipse y el periapsis
    (el PDI) queda en su antípoda. Se busca, poco antes del perilunio de la NRHO (τ = 0,5), el
    punto cuya antípoda está a `BRAKING_RANGE_M` + `HIGH_GATE_BACK_M` del sitio sobre el suelo.
    """
    target = (BRAKING_RANGE_M + HIGH_GATE_BACK_M) / site.radius_m
    p = site.position / site.radius_m

    def miss(tau: float) -> float:
        r = rotating_to_moon_fixed(orbit.state_at(tau))[0:3]
        return float(np.arccos(np.clip(np.dot(-r / np.linalg.norm(r), p), -1.0, 1.0))) - target

    return float(brentq(miss, 0.3, 0.5, xtol=1e-10))


@dataclass(frozen=True, slots=True)
class GuidancePhase:
    """Tramo de guiado: llega a (r_f, v_f) en el instante absoluto t_end."""

    name: str
    t_end: float
    r_f: FloatArray
    v_f: FloatArray


@dataclass(frozen=True, slots=True)
class DescentResult:
    """Trayectoria del descenso en el MF (SI) y sus valores clave.

    `t` empieza en 0 en la DOI; `y` es (7, N) = [r, v, m].
    """

    t: FloatArray
    y: FloatArray
    site: LandingSite
    t_pdi: float
    t_touchdown: float
    gate_times: dict[str, float]
    dv_doi_m_s: float
    dv_powered_m_s: float
    mass_initial_kg: float
    mass_at_pdi_kg: float
    mass_landed_kg: float
    touchdown_velocity: FloatArray
    landing_error_m: float
    pdi_lat_lon_deg: tuple[float, float]
    max_throttle_fraction: float
    phases: list[GuidancePhase] = field(default_factory=list)

    @property
    def dv_total_m_s(self) -> float:
        return self.dv_doi_m_s + self.dv_powered_m_s

    @property
    def altitude_m(self) -> FloatArray:
        return np.asarray(np.linalg.norm(self.y[0:3], axis=0) - self.site.radius_m)


def _site_frame(site: FloatArray, pdi_r: FloatArray) -> tuple[FloatArray, FloatArray]:
    """(û, ĥ): vertical del sitio y dirección horizontal del avance (desde el PDI al sitio)."""
    up = site / np.linalg.norm(site)
    d = up - pdi_r / np.linalg.norm(pdi_r)
    h = d - np.dot(d, up) * up
    return up, h / np.linalg.norm(h)


def guidance_phases(
    pdi_state: FloatArray,
    t_pdi: float,
    site: LandingSite,
    high_gate: tuple[float, float, float, float] = (HIGH_GATE_BACK_M, 2_000.0, 80.0, -20.0),
    approach_s: float = 150.0,
    terminal_s: float = 70.0,
) -> list[GuidancePhase]:
    """Objetivos de los tres tramos.

    `high_gate` = (distancia antes del sitio, altura, velocidad horizontal, velocidad vertical).
    El tiempo de frenado se elige para que la desaceleración horizontal sea uniforme:
    distancia = (v_PDI + v_HG)/2 · t.
    """
    r0, v0 = pdi_state[0:3], pdi_state[3:6]
    p = site.position
    up, h = _site_frame(p, r0)
    back, height, v_h, v_up = high_gate

    r_hg = p + height * up - back * h
    # distancia de frenado: arco sobre la superficie entre el PDI y la high gate
    cos_arc = np.dot(r0 / np.linalg.norm(r0), r_hg / np.linalg.norm(r_hg))
    ground = site.radius_m * float(np.arccos(np.clip(cos_arc, -1.0, 1.0)))
    v_pdi = float(np.linalg.norm(v0 - np.dot(v0, r0) / np.dot(r0, r0) * r0))
    t_braking = 2.0 * ground / (v_pdi + v_h)

    t_hg = t_pdi + t_braking
    t_lg = t_hg + approach_s
    return [
        GuidancePhase("Frenado", t_hg, r_hg, v_h * h + v_up * up),
        GuidancePhase("Aproximación", t_lg, p + 100.0 * up, -2.0 * up),
        GuidancePhase("Descenso final", t_lg + terminal_s, p, -TOUCHDOWN_SPEED_M_S * up),
    ]


def _powered_rhs(
    dynamics: MoonFixedDynamics,
    phase: GuidancePhase,
    engine: StageSpec,
    min_throttle: float,
    hold_s: float = 5.0,
) -> Callable[[float, FloatArray], FloatArray]:
    """Derivadas con empuje guiado. En los últimos `hold_s` de cada tramo el E-guidance se
    vuelve singular (t_go → 0): se pasa a mantener la velocidad objetivo."""
    ve = engine.isp_vac_s * G0_M_S2
    t_min, t_max = min_throttle * engine.thrust_vac_n, engine.thrust_vac_n

    def rhs(t: float, y: FloatArray) -> FloatArray:
        r, v, m = y[0:3], y[3:6], y[6]
        g = dynamics.acceleration(r, v)
        t_go = phase.t_end - t
        if t_go > hold_s:
            a_cmd = e_guidance(r, v, g, phase.r_f, phase.v_f, t_go)
        else:
            a_cmd = -g + (phase.v_f - v) / 2.0
        norm = float(np.linalg.norm(a_cmd))
        thrust = float(np.clip(m * norm, t_min, t_max))
        a_thrust = thrust / m * a_cmd / max(norm, 1e-12)
        return np.concatenate([v, g + a_thrust, [-thrust / ve]])

    return rhs


def throttle_history(
    t: FloatArray, y: FloatArray, dynamics: MoonFixedDynamics, phases: list[GuidancePhase]
) -> FloatArray:
    """Fracción de empuje máximo en cada muestra del tramo propulsado (a partir de ṁ)."""
    out = np.zeros(t.size)
    for k in range(t.size):
        phase = next((p for p in phases if t[k] <= p.t_end), phases[-1])
        rhs = _powered_rhs(dynamics, phase, HLS, HLS_MIN_THROTTLE)
        out[k] = -rhs(float(t[k]), y[:, k])[6] * HLS.isp_vac_s * G0_M_S2 / HLS.thrust_vac_n
    return out


def simulate_descent(
    doi_state_mf: FloatArray,
    site: LandingSite = SOUTH_POLE_SITE,
    gravity: LunarGravityField | None = None,
    mass_kg: float = HLS.total_mass_kg,
    coast_dt_s: float = 10.0,
    powered_dt_s: float = 1.0,
) -> DescentResult:
    """DOI desde la NRHO → planeo → descenso propulsado → contacto.

    Parámetros
    ----------
    doi_state_mf : estado MF (SI) del HLS en la NRHO en el instante de la DOI
        (ver `choose_doi_tau`).
    site : sitio de alunizaje.
    gravity : campo gravitatorio (por defecto GRGM1200A hasta grado 100).
    mass_kg : masa del HLS en la NRHO.
    """
    gravity = gravity or LunarGravityField.grgm1200a()
    dyn = MoonFixedDynamics(gravity)
    ve = HLS.isp_vac_s * G0_M_S2

    # 1. DOI impulsiva (Tsiolkovsky)
    dv_doi = descent_orbit_insertion(doi_state_mf, dyn, site.radius_m + PDI_ALTITUDE_M)
    y0 = doi_state_mf.copy()
    y0[3:6] += dv_doi
    m_doi = mass_kg * float(np.exp(-np.linalg.norm(dv_doi) / ve))

    # 2. Planeo hasta el perilunio (r·v pasa de negativo a positivo)
    def perilune(t: float, y: FloatArray) -> float:
        return float(np.dot(y[0:3], y[3:6])) if t > 600.0 else -1.0

    perilune.terminal = True  # type: ignore[attr-defined]
    perilune.direction = 1.0  # type: ignore[attr-defined]
    coast = solve_ivp(
        dyn.derivatives, (0.0, 6.0 * 3600.0), y0, method="DOP853",
        rtol=1e-10, atol=1e-6, events=perilune, dense_output=True,
    )  # fmt: skip
    if coast.status != 1:
        raise RuntimeError("El planeo de la DOI no llegó al perilunio.")
    t_pdi = float(coast.t_events[0][0])
    pdi = coast.y_events[0][0]
    t_coast = np.append(np.arange(0.0, t_pdi, coast_dt_s), t_pdi)
    y_coast = np.vstack([coast.sol(t_coast), np.full(t_coast.size, m_doi)])

    # 3. Descenso propulsado por tramos
    phases = guidance_phases(pdi, t_pdi, site)

    def touchdown(_t: float, y: FloatArray) -> float:
        return float(np.linalg.norm(y[0:3]) - site.radius_m)

    touchdown.terminal = True  # type: ignore[attr-defined]
    touchdown.direction = -1.0  # type: ignore[attr-defined]

    ts, ys = [t_coast], [y_coast]
    state = np.concatenate([pdi, [m_doi]])
    t0, t_touch = t_pdi, None
    gate_times: dict[str, float] = {}
    for k, phase in enumerate(phases):
        last = k == len(phases) - 1
        t_end = phase.t_end + (60.0 if last else 0.0)  # margen para llegar al suelo
        sol = solve_ivp(
            _powered_rhs(dyn, phase, HLS, HLS_MIN_THROTTLE), (t0, t_end), state,
            method="DOP853", rtol=1e-9, atol=1e-6, max_step=1.0,
            events=touchdown if last else None, dense_output=True,
        )  # fmt: skip
        if sol.status == -1:
            raise RuntimeError(f"Fallo de integración en el tramo «{phase.name}»: {sol.message}")
        t_stop = float(sol.t[-1])
        tk = np.append(np.arange(t0, t_stop, powered_dt_s)[1:], t_stop)
        ts.append(tk)
        ys.append(sol.sol(tk))
        state, t0 = sol.y[:, -1], t_stop
        gate_times[phase.name] = t_stop
        if last:
            if sol.status != 1:
                raise RuntimeError("El HLS no llegó al suelo.")
            t_touch = t_stop

    assert t_touch is not None
    t_all, y_all = np.concatenate(ts), np.hstack(ys)
    v_td = state[3:6]
    p = site.position
    r_td = state[0:3] * site.radius_m / np.linalg.norm(state[0:3])
    m_pdi, m_land = float(y_coast[6, -1]), float(state[6])
    powered = t_all >= t_pdi
    throttle = throttle_history(t_all[powered], y_all[:, powered], dyn, phases)
    return DescentResult(
        t=t_all,
        y=y_all,
        site=site,
        t_pdi=t_pdi,
        t_touchdown=t_touch,
        gate_times=gate_times,
        dv_doi_m_s=float(np.linalg.norm(dv_doi)),
        dv_powered_m_s=ve * float(np.log(m_pdi / m_land)),
        mass_initial_kg=mass_kg,
        mass_at_pdi_kg=m_pdi,
        mass_landed_kg=m_land,
        touchdown_velocity=v_td,
        landing_error_m=float(np.linalg.norm(r_td - p)),
        pdi_lat_lon_deg=latitude_longitude_deg(pdi[0:3]),
        max_throttle_fraction=float(np.max(throttle)),
        phases=phases,
    )
