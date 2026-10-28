# Artemis IV · Simulador de dinámica de vuelo

Simulador numérico en Python de las primeras fases de la misión **Artemis IV** de la NASA con el cohete **SLS Block 1B**: ascenso atmosférico, tránsito Tierra–Luna e inyección translunar (TLI).

Proyecto del Programa de Computación Científica, Universidad de Medellín.
Autores: Mariana Lopera Correa, Juan José Becerra Bedoya y Daniel Santiago Machado.

| Fase | Física | Método numérico | Resultado |
|---|---|---|---|
| 1 · Ascenso (LC-39B → MECO) | Empuje, arrastre con Cd(Mach), masa variable | Dormand–Prince RK45 con eventos | Max-Q 27,5 kPa · MECO a 160 km con 6,60 km/s |
| 2 · Tránsito Tierra–Luna | Problema restringido de tres cuerpos | Velocity Verlet (simpléctico) | Integral de Jacobi conservada a ~1e-5 |
| 3 · TLI | Problema de valores en la frontera | Método del disparo + Newton-Raphson | Δv = 3 150 m/s en 5 iteraciones |
| NRHO de Gateway (base de la Fase 4) | CR3BP adimensional + matriz de transición de estados | Corrección diferencial + continuación | NRHO 9:2: periodo 6,56 d, perilunio 3 248 km |

El visualizador 3D (Three.js) en [frontend/](frontend/) reproduce las Fases 1–3. Las fases 4 (inserción en la NRHO de Gateway) y 5 (descenso lunar) están planificadas en [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Instalación

Requiere Python 3.11 o superior.

```bash
git clone <url-del-repositorio>
cd ArtemisIV-flight-dynamics
python -m venv .venv
source .venv/bin/activate        # fish: source .venv/bin/activate.fish · Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

| Tarea | Comando | Resultado |
|---|---|---|
| Correr las pruebas | `python -m pytest` | 75 pruebas en ~30 s |
| Generar figuras y resultados | `python scripts/generate_figures.py` | `docs/figures/*.png`, `docs/paper/final/figures/*.pdf`, `results.json`, `results.tex` |
| Familia de halos y NRHO | `python scripts/nrho_figures.py` | `docs/figures/fig09_familia_halo.png` |
| Exportar la misión para la web | `python scripts/export_mission.py` | `frontend/data/mission.json` (Fases 1–3 + NRHO, ~0,6 MB) |
| Compilar el informe | `cd docs/paper/final && pdflatex main.tex && pdflatex main.tex` | `main.pdf` |
| Regenerar la presentación | `cd docs/presentation && npm install && npm run build` | `Artemis_IV_UdeM.pptx` |
| Abrir el visualizador 3D | `python -m http.server 8000 -d frontend` → http://localhost:8000 | Misión de las Fases 1–3 en el navegador |
| Pruebas del visualizador | `node --test frontend/tests/*.test.mjs` | Marcos, interpolación y línea de tiempo |
| Revisar estilo y tipos | `ruff check src tests scripts && mypy src` | Sin errores |

### Ejemplo: ascenso completo

```python
from artemis_sim import simulate_full_ascent
import numpy as np

result = simulate_full_ascent()          # LC-39B, guiado nominal de tangente lineal
r, v = result.y[0:3, -1], result.y[3:6, -1]
print(f"MECO a t = {result.t_meco_s:.1f} s")
print(f"Altitud: {(np.linalg.norm(r) - 6_378_137) / 1e3:.1f} km · velocidad: {np.linalg.norm(v):.0f} m/s")
```

### Ejemplo: órbita circular con Verlet

```python
from artemis_sim import circular_orbit_state, propagate_verlet, compute_system_energy

state = circular_orbit_state(6_778_137.0)               # 400 km de altitud
traj = propagate_verlet(state, t_final=5_554.0, dt=10.0, include_moon=False)
e0 = compute_system_energy(traj[0], 0.0, include_moon=False)
e1 = compute_system_energy(traj[-1], traj[-1].t, include_moon=False)
print(f"Error relativo de energía tras una órbita: {abs(e1 / e0 - 1):.1e}")
```

---

## Estructura del repositorio

```text
ArtemisIV-flight-dynamics/
├── src/artemis_sim/        # Paquete del simulador (ver docs/architecture.md)
├── tests/                  # 75 pruebas automáticas (pytest)
├── scripts/
│   ├── generate_figures.py # Figuras y números del informe
│   └── export_mission.py   # Trayectoria de la misión → frontend/data/mission.json
├── docs/
│   ├── ROADMAP.md          # Hoja de ruta: mejoras, Fases 4–5 y visualización 3D
│   ├── architecture.md     # Arquitectura y decisiones de diseño
│   ├── figures/            # Figuras PNG + results.json
│   ├── paper/final/        # Informe LaTeX (main.tex, main.pdf)
│   ├── paper/articles/     # Fuentes de la NASA y bibliografía
│   └── presentation/       # Presentación (.pptx, .pdf) y su generador
└── frontend/               # Visualizador 3D (Three.js, sin compilador): js/, css/, data/, tests/
```

## Convenciones

- **Unidades SI estrictas** en el código (m, kg, s, rad, N), con la unidad en el nombre del atributo: `mu_m3_s2`, `dry_mass_kg`, `thrust_vac_n`.
- **Marco de referencia ECI J2000** (geocéntrico inercial). Origen en el centro de la Tierra; +Z hacia el polo norte; +X hacia el equinoccio vernal. Como el marco es inercial, **no** se suman Coriolis ni centrífuga; la rotación terrestre entra por la velocidad relativa al aire, `v_rel = v − ω_E × r`.
- **Parámetro gravitacional μ = GM** como magnitud primaria (WGS84 / IERS para la Tierra, DE421 para la Luna).
- **Toda función física nueva** debe tener una prueba que la compare contra un valor analítico, publicado o un caso límite.

## Documentación

- Informe técnico: [docs/paper/final/main.pdf](docs/paper/final/main.pdf)
- Arquitectura: [docs/architecture.md](docs/architecture.md)
- Hoja de ruta: [docs/ROADMAP.md](docs/ROADMAP.md)

## Licencia

Ver [LICENSE](LICENSE).
