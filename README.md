# Artemis IV - Simulador de Dinámica de Vuelo (Fase 1)

Simulador de dinámica de vuelo para la misión Artemis IV de la NASA (SLS Block 1B con etapa de exploración superior EUS, nave Orion y módulo Gateway).

Este repositorio implementa el proyecto por fases. La **Fase 1** establece la arquitectura de datos fundamental, el vector de estado cinemático/dinámico (`ArtemisState`) y el motor de constantes físicas y de astronáutica (`constants.py`).

---

## Convenciones Obligatorias

### 1. Sistema de Unidades (SI Estricto)
Se emplean estrictamente unidades del Sistema Internacional:
- **Longitud / posición / altitud / radio:** metros ($\text{m}$). *Prohibido el uso de kilómetros ($\text{km}$) en firmas, cálculos y almacenamiento.*
- **Masa:** kilogramos ($\text{kg}$).
- **Tiempo:** segundos ($\text{s}$).
- **Velocidad:** metros por segundo ($\text{m/s}$).
- **Fuerza / empuje:** newtons ($\text{N}$).
- **Ángulo / velocidad angular:** radianes ($\text{rad}$) y radianes por segundo ($\text{rad/s}$).
- **Parámetro gravitacional estándar:** $\mu = GM$ en metros cúbicos sobre segundo al cuadrado ($\text{m}^3/\text{s}^2$).

Cada constante y campo lleva su unidad explícita en su nombre de atributo (p. ej., `mu_m3_s2`, `dry_mass_kg`, `thrust_vac_n`) o documentada en su docstring y firma.

### 2. Marco de Referencia
- **ECI (Earth-Centered Inertial, marco J2000):** El vector de estado del vehículo se expresa en este marco inercial centrado en la Tierra:
  - Origen: Centro de masas de la Tierra.
  - Plano fundamental: Plano ecuatorial medio en la época estándar J2000.0 (1 de enero de 2000, 12:00 TT).
  - Eje $+X$: Orientado hacia el equinoccio vernal medio (punto Aries).
  - Eje $+Z$: Normal al plano ecuatorial, orientado hacia el Polo Norte celeste medio J2000.
  - Eje $+Y$: Completa la terna ortonormal derecha ($+Y = +Z \times +X$).
- **Rotación Terrestre y Transformación a ECEF:** La velocidad angular de la Tierra $\omega_E$ se almacena en `EarthRotation` ($\approx 7.2921150 \times 10^{-5}\ \text{rad/s}$, estándar IERS/WGS84). Permite calcular en fases posteriores la matriz de rotación dependiente del tiempo para convertir entre ECI y el marco rotante ECEF (Earth-Centered, Earth-Fixed). *Nota: Las transformaciones completas (precesión, nutación y ángulo de rotación sideral) quedan documentadas como TODO para la Fase 2.*

### 3. Parámetro Gravitacional $\mu$
Para Tierra y Luna se utiliza como magnitud primaria el parámetro gravitacional estándar $\mu = GM$ ($\text{m}^3/\text{s}^2$), garantizando máxima precisión según los estándares WGS84, IERS y NASA DE421. Las masas en $\text{kg}$ se incluyen como datos derivados/referenciales.

---

## Arquitectura de Software (Layout `src`)

```text
ArtemisIV-flight-dynamics/
├── pyproject.toml            # Configuración de paquete Python (>=3.11), dependencias y linters
├── README.md                 # Documentación técnica, convenciones y guía de ejecución
├── src/
│   └── artemis_sim/
│       ├── __init__.py       # Exportaciones públicas de la biblioteca
│       ├── constants.py      # Dataclasses inmutables (CelestialBody, StageSpec, EarthRotation)
│       └── state.py          # Clase ArtemisState (vector de estado optimizado en NumPy)
└── tests/
    ├── test_constants.py     # Tests de inmutabilidad, coherencia física y validaciones
    └── test_state.py         # Tests de conversiones to_array/from_array, copias y protecciones
```

### Justificación de `ArtemisState`
El estado interno del vehículo se almacena en un arreglo continuo plano `numpy.ndarray` de dimensiones `(7,)` y tipo `float64` (`[x, y, z, vx, vy, vz, m]`), protegido contra escritura directa externa:
- **Compatibilidad con Integradores Numéricos:** Permite pasarlo directamente a solucionadores numéricos (como `scipy.integrate.solve_ivp` o algoritmos RK4/RK78 en Fase 2) sin copias innecesarias.
- **Rendimiento:** Cero sobrecarga de deserialización durante millones de iteraciones de integración orbital.
- **Interfaz Orientada a Objetos:** Expone propiedades semánticas (`position`, `velocity`, `mass`, `radius`, `speed`) y validación rigurosa de finitud (sin NaN ni infinitos) y masa positiva.

---

## Ejemplo Mínimo de Uso

El siguiente script ilustra cómo inicializar el estado del vehículo en una órbita circular baja terrestre (LEO) a una altitud de $400\ \text{km}$ y consultar sus propiedades físicas:

```python
import numpy as np
from artemis_sim.constants import EARTH
from artemis_sim.state import ArtemisState

# 1. Definir la altitud y radio orbital en metros (SI estricto)
altitude_m = 400_000.0  # 400 km expresados en m
r_orbit_m = EARTH.equatorial_radius_m + altitude_m

# 2. Calcular la velocidad circular orbital: v = sqrt(mu / r)
v_orbit_m_s = np.sqrt(EARTH.mu_m3_s2 / r_orbit_m)

# 3. Vector de posición y velocidad en marco inercial ECI J2000
position_eci = [r_orbit_m, 0.0, 0.0]
velocity_eci = [0.0, v_orbit_m_s, 0.0]

# 4. Masa de la etapa o vehículo (ej. SLS Block 1B + Orion en LEO)
vehicle_mass_kg = 135_000.0

# 5. Instanciar el estado
state = ArtemisState(
    position=position_eci,
    velocity=velocity_eci,
    mass=vehicle_mass_kg,
    t=0.0
)

print(state)
print(f"Radio geocéntrico : {state.radius:.2f} m")
print(f"Velocidad orbital : {state.speed:.2f} m/s")
print(f"Vector plano (7,) : {state.to_array()}")
```

Salida esperada:
```text
ArtemisState(t=0.000 s, pos=[6778137., 0., 0.] m, vel=[0., 7672.634, 0.] m/s, mass=135000.00 kg, radius=6778137.0 m, speed=7672.63 m/s)
Radio geocéntrico : 6778137.00 m
Velocidad orbital : 7672.63 m/s
Vector plano (7,) : [6.778137e+06 0.000000e+00 0.000000e+00 0.000000e+00 7.672634e+03 0.000000e+00 1.350000e+05]
```

---

## Verificación y Calidad de Código

### Ejecución de Pruebas Unitarias (`pytest`)
```bash
pytest tests/test_constants.py tests/test_state.py -v
```

### Verificación de Tipado Estático (`mypy --strict`)
```bash
mypy --strict src/artemis_sim tests/test_constants.py tests/test_state.py
```

### Verificación de Estilo y Linting (`ruff`)
```bash
ruff check src/artemis_sim tests/test_constants.py tests/test_state.py
```

---

## Fase 2: Ascenso Atmosférico

La Fase 2 modela el ascenso atmosférico del lanzador SLS Block 1B desde la plataforma de lanzamiento (LC-39B en Kennedy Space Center) hasta el cruce de los 100 km de altitud (línea de Kármán) y la separación de los SRB.

### Marco de Referencia y Fuerzas
- **Integración en ECI:** El estado se integra exclusivamente en coordenadas inerciales ECI (J2000).
  - La rotación de la Tierra entra únicamente mediante la velocidad relativa al aire:
    $$\mathbf{v}_{\text{rel}} = \mathbf{v} - \boldsymbol{\omega}_E \times \mathbf{r}$$
  - En las derivadas de ascenso (`ascent_derivatives`), **no se suman Coriolis ni aceleración centrífuga** para evitar un doble conteo erróneo de las fuerzas ficticias.
  - La función `compute_coriolis_centrifugal_accel` se proporciona como utilidad pura para análisis o integraciones formuladas en el marco rotante ECEF, y su equivalencia física con la integración en ECI se verifica formalmente en `tests/test_physics.py`.
- **Aerodinámica:** Modelo exponencial con $\rho_0 = 1.225\ \text{kg/m}^3$ y $H_\rho = 8500\ \text{m}$. La fuerza de arrastre:
  $$\mathbf{F}_{\text{drag}} = -\frac{1}{2}\rho(h) C_d A \|\mathbf{v}_{\text{rel}}\| \mathbf{v}_{\text{rel}}$$
  Devuelve el vector nulo si $\|\mathbf{v}_{\text{rel}}\| = 0$ sin indeterminaciones, y se anula por encima de los $100\ \text{km}$.
- **Propulsión y Presión:** El empuje efectivo varía según la contrapresión barométrica ambiental:
  $$T(h) = \max(0, T_{\text{vac}} - p_a(h) A_e)$$
  El flujo másico es estrictamente constante durante la combustión activa:
  $$\frac{dm}{dt} = -\frac{T_{\text{vac}}}{I_{\text{sp,vac}} g_0}$$
- **Separación de Boosters (SRB):** `jettison_boosters(state, config)` aplica una discontinuidad de masa instantánea restando la masa seca inerte de los dos SRB, permitiendo continuar la integración en la fase `CORE_ONLY`.

### Ejemplo de Simulación de Ascenso
```python
from scipy.integrate import solve_ivp
from artemis_sim.ascent_solver import (
    AscentConfig,
    AscentPhase,
    initial_state_on_pad,
    make_ascent_derivatives,
    pitch_kick_direction,
    event_srb_burnout,
    event_karman_crossing,
    jettison_boosters,
)
from artemis_sim.state import ArtemisState

# Configuración con guiado de cabeceo por gravedad (pitch kick hacia el Este)
config_boosters = AscentConfig(
    thrust_direction_fn=pitch_kick_direction(t_kick=10.0, pitch_angle_rad=0.035),
    phase=AscentPhase.BOOSTERS_AND_CORE
)

# Estado inicial en reposo en LC-39B (28.627° N, -80.621° O)
state_0 = initial_state_on_pad(28.627, -80.621, config_boosters)
deriv_fn = make_ascent_derivatives(config_boosters)

# Integración de la fase con Boosters
sol = solve_ivp(
    deriv_fn,
    (0.0, 126.0),
    state_0.to_array(),
    method="RK45",
    events=[event_srb_burnout, event_karman_crossing],
    rtol=1e-8,
    atol=1e-8
)

state_burnout = ArtemisState.from_array(sol.y[:, -1], t=sol.t[-1])
print(f"Estado antes de separación: {state_burnout}")

# Descarte de boosters y reinicio de fase
state_core_only = jettison_boosters(state_burnout, config_boosters)
print(f"Estado tras separación SRB: {state_core_only}")
```

---

## Fase 3: Tránsito en el Vacío (N Cuerpos e Integración Simpléctica)

La Fase 3 modela la propagación balística en el vacío (sin empuje, sin arrastre y con masa constante) en el sistema gravitacional Tierra-Luna (modelo restringido de 3 cuerpos).

### Aviso Físico sobre Conservación de Energía
> [!WARNING]
> Con la Luna en una trayectoria prescrita dependiente del tiempo $\mathbf{r}_M(t)$, el hamiltoniano geocéntrico depende explícitamente de $t$. Por consiguiente, la **energía mecánica específica respecto a la Tierra NO es una cantidad conservada** cuando la perturbación lunar está activa (`include_moon=True`).
> La conservación rigurosa de la energía orbital y del momento angular específico solo se exige y verifica en el problema de dos cuerpos autónomo (`include_moon=False`).

### Término Indirecto en Marco Geocéntrico
Al formular las ecuaciones en el marco acelerado centrado en la Tierra (ECI), la aceleración de caída libre que sufre la Tierra por la atracción gravitatoria lunar debe restarse al vector de aceleración de la nave espacial:
$$\mathbf{a} = -\frac{\mu_E \mathbf{r}}{\|\mathbf{r}\|^3} + \mu_M \left[ \frac{\mathbf{r}_M(t) - \mathbf{r}}{\|\mathbf{r}_M(t) - \mathbf{r}\|^3} - \frac{\mathbf{r}_M(t)}{\|\mathbf{r}_M(t)\|^3} \right]$$
El término indirecto $-\mu_M \mathbf{r}_M / \|\mathbf{r}_M\|^3$ garantiza que en el centro de masas de la Tierra ($\mathbf{r} = \mathbf{0}$) la aceleración relativa neta debida a la Luna sea idénticamente nula.

### Integrador Simpléctico Velocity Verlet (Orden 2)
Implementa el esquema kick-drift-kick:
$$\mathbf{v}_{1/2} = \mathbf{v}_0 + \frac{1}{2}\mathbf{a}(\mathbf{r}_0, t_0)\Delta t$$
$$\mathbf{r}_1 = \mathbf{r}_0 + \mathbf{v}_{1/2}\Delta t$$
$$\mathbf{v}_1 = \mathbf{v}_{1/2} + \frac{1}{2}\mathbf{a}(\mathbf{r}_1, t_0 + \Delta t)\Delta t$$

- **Conservación Simpléctica:** Preserva la estructura simpléctica del espacio de fases, manteniendo la energía acotada sin deriva secular durante cientos de órbitas.
- **Reversibilidad Temporal:** Exacta bajo inversión de velocidad $\mathbf{v} \to -\mathbf{v}$.
- **Rendimiento:** Reutiliza $\mathbf{a}_1$ como $\mathbf{a}_0$ en el paso siguiente, logrando una única evaluación de aceleración por iteración.

### Ejemplo de Propagación Translunar (TLI)
```python
from artemis_sim.constants import EARTH
from artemis_sim.symplectic_solver import (
    circular_orbit_state,
    impulsive_burn,
    propagate_verlet,
    compute_system_energy,
)

# 1. Órbita de aparcamiento circular a 300 km de altitud
r_park = EARTH.equatorial_radius_m + 300_000.0
state_park = circular_orbit_state(r_park)

# 2. Encendido impulsivo TLI (+3150 m/s prógrado)
state_tli = impulsive_burn(state_park, [0.0, 3150.0, 0.0])

# 3. Propagación simpléctica de 3 días con la Luna activa (dt = 5 s)
trajectory = propagate_verlet(
    state_tli,
    t_final=3.0 * 86400.0,
    dt=5.0,
    sample_every=100,
    include_moon=True,
)

print(f"Estado inicial TLI: {trajectory[0]}")
print(f"Estado a los 3 días: {trajectory[-1]}")
```

---

## Fase 4: Targeting de la Inyección Translunar (Método del Disparo)

La Fase 4 implementa el algoritmo de targeting de frontera de dos puntos (two-point boundary value problem) para calcular el vector impulsivo $\Delta \mathbf{v}$ de inyección translunar (TLI) desde la órbita de aparcamiento terrestre.

> [!NOTE]
> **Aviso de Modelado y Alcance:**
> Este modelo está concebido para análisis de misión conceptual, estudios preliminares y docencia. No modela trayectorias operativas completas de Artemis (como inserciones de halo casi rectilíneo NRHO alrededor de la Luna, optimización de combustible multietapa o correcciones de trayectoria en ruta TCM).

### Algoritmo Newton-Raphson Multivariable
Dado un estado inicial $\mathbf{s}_0$, un tiempo de vuelo $t_{\text{flight}}$ y una posición cartesiana objetivo $\mathbf{r}_{\text{target}}$:
1. **Residuo:** $\mathbf{F}(\Delta \mathbf{v}) = \mathbf{r}(t_{\text{flight}}; \mathbf{s}_0, \Delta \mathbf{v}) - \mathbf{r}_{\text{target}}$.
2. **Jacobiano Numérico:** Por diferencias finitas centrales con $h = 0.01\ \text{m/s}$ (óptimo frente al error de redondeo y truncamiento).
3. **Región de Confianza (Trust Region):** Limita la norma de corrección $\|\mathbf{d}\| \le 500\ \text{m/s}$ por iteración.
4. **Búsqueda Lineal con Retroceso (Backtracking):** Reduce el paso $\alpha \leftarrow \alpha / 2$ si el residuo no disminuye estrictamente.
5. **Monitoreo de Condicionamiento:** Advierte si $\text{cond}(\mathbf{J}) > 10^{10}$.

### Ejemplo de Uso del Disparo
```python
import numpy as np
from artemis_sim.shooting_method import (
    circular_orbit_state,
    initial_guess_vis_viva,
    make_dop853_propagator,
    moon_relative_target,
    solve_tli_shooting,
)

# 1. Estado en órbita de aparcamiento circular a 300 km de altitud
r_park = 6_378_137.0 + 300_000.0
state0 = circular_orbit_state(r_park)

# 2. Objetivo relativo a la Luna a los 4 días (paso a 5,000 km en el eje Y)
t_flight = 4.0 * 86400.0
target_pos = moon_relative_target(offset_m=[0.0, 5_000_000.0, 0.0], t_arrival=t_flight)

# 3. Suposición inicial analítica mediante vis-viva (dos cuerpos)
dv_guess = initial_guess_vis_viva(state0, target_distance_m=384_400_000.0)

# 4. Solución del disparo con DOP853
result = solve_tli_shooting(
    state0=state0,
    target_pos=target_pos,
    t_flight=t_flight,
    dv_guess=dv_guess,
    tol_m=1.0,
    max_iter=20,
)

print(f"Convergido: {result.converged} en {result.iterations} iteraciones")
print(f"Delta-V requerido: {result.delta_v} m/s (norma: {result.delta_v_norm:.2f} m/s)")
print(f"Residuo de posición final: {result.final_residual:.3e} m")
```
