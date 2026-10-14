"""Motor de constantes físicas y astronómicas para la misión Artemis IV.

Todas las magnitudes emplean estrictamente unidades del Sistema Internacional (SI):
- Longitud / posición: metros (m)
- Masa: kilogramos (kg)
- Tiempo: segundos (s)
- Ángulo: radianes (rad)
- Fuerza / empuje: newtons (N)
- Parámetro gravitacional: m^3 / s^2

Convenciones de marco de referencia:
- Coordenadas espaciales expresadas en ECI (Earth-Centered Inertial, marco J2000).
- La rotación terrestre se define a través del vector de velocidad angular orientado en el eje Z.
"""

from dataclasses import dataclass
from typing import Final

# Aceleración gravitacional estándar en la superficie terrestre (NIST / CODATA)
G0_M_S2: Final[float] = 9.80665


@dataclass(frozen=True, slots=True)
class CelestialBody:
    """Representación inmutable de un cuerpo celeste esférico/elipsoidal.

    Parámetros
    ----------
    name : str
        Nombre del cuerpo celeste (por ejemplo 'Earth' o 'Moon').
    mu_m3_s2 : float
        Parámetro gravitacional estándar mu = G * M en m^3 / s^2.
    mass_kg : float
        Masa de referencia del cuerpo en kg.
    equatorial_radius_m : float
        Radio ecuatorial (o medio para la Luna) en metros.
    """

    name: str
    mu_m3_s2: float
    mass_kg: float
    equatorial_radius_m: float

    def __post_init__(self) -> None:
        """Valida que las magnitudes físicas sean estrictamente positivas."""
        if not self.name or not self.name.strip():
            raise ValueError("El nombre del cuerpo celeste no puede estar vacío.")
        if self.mu_m3_s2 <= 0.0:
            raise ValueError(
                f"El parámetro gravitacional mu debe ser positivo (> 0). "
                f"Valor recibido: {self.mu_m3_s2}"
            )
        if self.mass_kg <= 0.0:
            raise ValueError(
                f"La masa debe ser positiva (> 0). Valor recibido: {self.mass_kg}"
            )
        if self.equatorial_radius_m <= 0.0:
            raise ValueError(
                f"El radio ecuatorial debe ser positivo (> 0). "
                f"Valor recibido: {self.equatorial_radius_m}"
            )


@dataclass(frozen=True, slots=True)
class EarthRotation:
    """Parámetros cinemáticos de rotación de la Tierra.

    Documentación de uso:
    Sirve como base para transformar vectores y tensores entre el marco inercial ECI (J2000)
    y el marco terrestre rotante ECEF (Earth-Centered, Earth-Fixed).
    TODO (Fase 2): Implementar formalmente las matrices de transformación ECI <-> ECEF
    considerando precesión, nutación y ángulo de rotación terrestre aparente / sidéreo.

    Parámetros
    ----------
    omega_rad_s : float
        Velocidad angular de rotación de la Tierra en rad/s.
        Fuente: Estándar WGS84 y convenciones IERS (International Earth Rotation and
        Reference Systems Service). Valor nominal = 7.2921150e-5 rad/s.
    """

    omega_rad_s: float = 7.2921150e-5

    def __post_init__(self) -> None:
        """Valida que la velocidad angular sea estrictamente positiva."""
        if self.omega_rad_s <= 0.0:
            raise ValueError(
                f"La velocidad angular debe ser positiva (> 0). Valor recibido: {self.omega_rad_s}"
            )


@dataclass(frozen=True, slots=True)
class StageSpec:
    """Especificación física y propulsiva de una etapa o conjunto propulsor.

    Parámetros
    ----------
    name : str
        Nombre identificativo de la etapa.
    dry_mass_kg : float
        Masa en seco de la estructura y sistemas en kg.
    propellant_mass_kg : float
        Masa de propelente utilizable en kg.
    thrust_vac_n : float
        Empuje total nominal en el vacío en Newtons (N).
    isp_vac_s : float
        Impulso específico nominal en el vacío en segundos (s).
    thrust_sea_level_n : float | None
        Empuje total opcional a nivel del mar en Newtons (N).
    status : str
        Estado de verificación del dato ('nominal', 'aproximado' o 'pendiente de verificar').
    """

    name: str
    dry_mass_kg: float
    propellant_mass_kg: float
    thrust_vac_n: float
    isp_vac_s: float
    thrust_sea_level_n: float | None = None
    status: str = "nominal"

    def __post_init__(self) -> None:
        """Valida coherencia de las propiedades de la etapa."""
        if not self.name or not self.name.strip():
            raise ValueError("El nombre de la etapa no puede estar vacío.")
        if self.dry_mass_kg <= 0.0:
            raise ValueError(
                f"La masa en seco debe ser positiva (> 0). Valor: {self.dry_mass_kg} kg"
            )
        if self.propellant_mass_kg <= 0.0:
            raise ValueError(
                f"La masa de propelente debe ser positiva (> 0). "
                f"Valor: {self.propellant_mass_kg} kg"
            )
        if self.thrust_vac_n <= 0.0:
            raise ValueError(
                f"El empuje en vacío debe ser positivo (> 0). Valor: {self.thrust_vac_n} N"
            )
        if self.isp_vac_s <= 0.0:
            raise ValueError(
                f"El Isp en vacío debe ser positivo (> 0). Valor: {self.isp_vac_s} s"
            )
        if self.thrust_sea_level_n is not None and self.thrust_sea_level_n <= 0.0:
            raise ValueError(
                f"El empuje a nivel del mar debe ser positivo si se especifica. "
                f"Valor: {self.thrust_sea_level_n} N"
            )

    @property
    def total_mass_kg(self) -> float:
        """Masa total de la etapa cargada de propelente (en kg)."""
        return self.dry_mass_kg + self.propellant_mass_kg

    @property
    def mass_flow_rate_kg_s(self) -> float:
        """Flujo másico nominal de consumo de propelente en vacío (en kg/s).

        Calculado a partir de la ecuación del cohete ideal:
        m_dot = Empuje_vac / (Isp_vac * g0)
        """
        return self.thrust_vac_n / (self.isp_vac_s * G0_M_S2)


# =============================================================================
# INSTANCIAS DE CUERPOS CELESTES
# =============================================================================

# Tierra:
# mu = 3.986004418e14 m^3/s^2 (WGS84 / IERS Numerical Standards)
# masa = 5.97216849e24 kg (derivada de GM / G_CODATA con G = 6.67430e-11 m^3/(kg s^2))
# radio ecuatorial a = 6378137.0 m (Elipsoide WGS84)
EARTH: Final[CelestialBody] = CelestialBody(
    name="Earth",
    mu_m3_s2=3.986004418e14,
    mass_kg=5.97216849e24,
    equatorial_radius_m=6378137.0,
)

# Luna:
# mu = 4.9048695e12 m^3/s^2 (NASA Planetary Fact Sheet / DE421)
# masa = 7.342e22 kg (NASA Planetary Fact Sheet)
# radio medio = 1737400.0 m (IAU/NASA Planetary Fact Sheet)
MOON: Final[CelestialBody] = CelestialBody(
    name="Moon",
    mu_m3_s2=4.9048695e12,
    mass_kg=7.342e22,
    equatorial_radius_m=1737400.0,
)

# Constante de rotación terrestre IERS / WGS84
EARTH_ROTATION: Final[EarthRotation] = EarthRotation()


# =============================================================================
# INSTANCIAS DE ETAPAS SLS BLOCK 1B
# =============================================================================

# 1. SLS Block 1B Core Stage (4 motores RS-25D/E alimentados por LOX/LH2)
# Fuentes públicas: NASA SLS Reference Guide / Fact Sheets (Boeing/Aerojet Rocketdyne)
# - Masa en seco: ~85,275 kg (aproximado / nominal según SLS Mission Planners Guide)
# - Propelente: ~987,460 kg (2.2 millones de libras de LOX/LH2 utilizable)
# - Empuje total en vacío: 4 x ~2,278,800 N (RS-25 al 109% de nivel de potencia) = 9,115,200 N
# - Empuje a nivel del mar: 4 x ~1,859,350 N = 7,437,400 N
# - Isp en vacío: 452.3 s (RS-25 especificación de vacío)
SLS_B1B_CORE_STAGE: Final[StageSpec] = StageSpec(
    name="SLS Block 1B Core Stage",
    dry_mass_kg=85275.0,  # nominal / aproximado público
    propellant_mass_kg=987460.0,  # nominal (NASA SLS Mission Planner's Guide)
    thrust_vac_n=9115200.0,  # 4x RS-25 a 109% de potencia en vacío
    isp_vac_s=452.3,  # nominal en vacío (Aerojet Rocketdyne RS-25)
    thrust_sea_level_n=7437400.0,  # 4x RS-25 a 109% nivel del mar
    status="nominal",
)

# 2. SLS Solid Rocket Booster (SRB) de 5 segmentos (Northrop Grumman)
# Cada cohete propulsor sólido:
# Fuentes: NASA SLS Fact Sheets / Northrop Grumman 5-segment booster spec
# - Masa en seco individual: ~99,790 kg (aproximado, estructura e inertes)
# - Propelente sólido individual: ~628,680 kg (polibutadieno acrilonitrilo PBAN)
# - Empuje individual en vacío: ~16,000,000 N (pico ~3.6 millones lbf)
# - Empuje individual nivel del mar: ~14,234,000 N
# - Isp en vacío: ~268.0 s (promedio de combustión en vacío)
SLS_B1B_SRB_SINGLE: Final[StageSpec] = StageSpec(
    name="SLS 5-Segment SRB (Single)",
    dry_mass_kg=99790.0,  # nominal (NASA / Northrop Grumman)
    propellant_mass_kg=628680.0,  # nominal (Northrop Grumman PBAN grain)
    thrust_vac_n=16000000.0,  # aproximado (promedio de empuje efectivo)
    isp_vac_s=268.0,  # nominal (Northrop Grumman spec)
    thrust_sea_level_n=14234000.0,  # aproximado a nivel del mar
    status="aproximado",
)

# Par conjunto de boosters (2x SRB que actúan en paralelo al despegue):
SLS_B1B_SRB_PAIR: Final[StageSpec] = StageSpec(
    name="SLS 5-Segment SRB (Pair)",
    dry_mass_kg=SLS_B1B_SRB_SINGLE.dry_mass_kg * 2.0,
    propellant_mass_kg=SLS_B1B_SRB_SINGLE.propellant_mass_kg * 2.0,
    thrust_vac_n=SLS_B1B_SRB_SINGLE.thrust_vac_n * 2.0,
    isp_vac_s=SLS_B1B_SRB_SINGLE.isp_vac_s,
    thrust_sea_level_n=(
        SLS_B1B_SRB_SINGLE.thrust_sea_level_n * 2.0
        if SLS_B1B_SRB_SINGLE.thrust_sea_level_n is not None
        else None
    ),
    status="aproximado",
)

# 3. SLS Exploration Upper Stage (EUS) para Block 1B
# 4 motores RL10C-3 (Aerojet Rocketdyne) alimentados por LOX/LH2
# Fuentes: NASA SLS Mission Planner's Guide ESD 30000 / Boeing EUS Fact Sheets
# - Masa en seco: ~13,600 kg
#   # TODO: verificar valor exacto final de masa seca con CDR de Boeing EUS
# - Masa de propelente: ~129,000 kg (nominal reportado: ~128,800 - 129,200 kg)
# - Empuje total en vacío: 4 x ~108,000 N (RL10C-3 nominal ~24,300 lbf c/u) = 432,000 N
#   # TODO: verificar empuje certificado específico de variante RL10C-3 para Artemis IV
# - Isp en vacío: 448.5 s (nominal de variante RL10C-3)
#   # TODO: verificar si la variante adopta toberas RL10C-3-1 (Isp ~453.8 s)
SLS_B1B_EUS: Final[StageSpec] = StageSpec(
    name="SLS Exploration Upper Stage (EUS)",
    dry_mass_kg=13600.0,  # TODO: verificar con reporte de masa CDR de Boeing EUS
    propellant_mass_kg=129000.0,  # nominal (NASA ESD 30000)
    thrust_vac_n=432000.0,  # TODO: verificar empuje exacto certificado de 4x RL10C-3
    isp_vac_s=448.5,  # TODO: verificar variante final de motor RL10C-3 vs RL10C-3-1
    thrust_sea_level_n=None,  # No opera en atmósfera densa; sólo vacío/alta altitud
    status="pendiente de verificar",
)
