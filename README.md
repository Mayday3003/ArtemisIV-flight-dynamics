# Artemis IV · Simulador de dinámica de vuelo

Simulador numérico en Python de la misión **Artemis IV** de la NASA con el cohete **SLS Block 1B**, desde el despegue hasta el alunizaje en el polo sur: ascenso atmosférico, inyección translunar (TLI), llegada a la NRHO de Gateway y descenso del HLS.

Proyecto del Programa de Computación Científica, Universidad de Medellín.
Autores: Mariana Lopera Correa, Juan José Becerra Bedoya y Daniel Santiago Machado.

| Fase | Física | Método numérico | Resultado |
|---|---|---|---|
| 1 · Ascenso (LC-39B → MECO) | Empuje, arrastre con Cd(Mach), masa variable | Dormand–Prince RK45 con eventos | Max-Q 29,6 kPa · MECO a 160 km con 6,60 km/s |
| 2 · Tránsito Tierra–Luna | Problema restringido de tres cuerpos | Velocity Verlet (simpléctico) | Integral de Jacobi conservada a ~1e-5 |
| 3 · TLI | Problema de valores en la frontera | Método del disparo + Newton-Raphson | Δv = 3 150 m/s en 5 iteraciones |
| NRHO de Gateway | CR3BP adimensional + matriz de transición de estados | Corrección diferencial + continuación | NRHO 9:2: periodo 6,56 d, perilunio 3 248 km |
| 4 · TLI → NRHO | Sobrevuelo lunar propulsado (OPF) + inserción (NRI) con Orion | Disparo múltiple + SLSQP | OPF 291 m/s + NRI 172 m/s |
| 5 · Descenso del HLS al polo sur | Gravedad lunar GRGM1200A (grado 100, Pines) en el marco fijo a la Luna, masa variable | DOP853 con eventos + E-guidance | DOI 702 m/s + descenso 2 297 m/s; contacto a 1 m/s y a 1 cm del sitio (86,8° S) |

El visualizador 3D (Three.js) en [frontend/](frontend/) reproduce la misión completa (Fases 1–5), con presentación guiada, explicación de cada evento y presupuesto de Δv. La hoja de ruta está en [docs/ROADMAP.md](docs/ROADMAP.md).

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
| Correr las pruebas | `python -m pytest` | 132 pruebas |
| Generar figuras y resultados | `python scripts/generate_figures.py` | `docs/figures/*.png`, `docs/paper/final/figures/*.pdf`, `results.json`, `results.tex` |
| **Todo de una vez** | `python scripts/run_mission.py` | Figuras fig01–fig12, `results*.tex`, `results.json` y `mission.json` (~8 min) |
| Familia de halos y NRHO | `python scripts/nrho_figures.py` | `docs/figures/fig09_familia_halo.png` |
| Coeficientes de gravedad lunar (ya incluidos) | `python scripts/fetch_grail.py [N]` | `data/grgm1200a_n100.npz` (GRGM1200A del PDS de la NASA) |
| Exportar la misión para la web | `python scripts/export_mission.py` | `frontend/data/mission.json` (Fases 1–5, ~2,2 MB; tarda ~4 min) |
| Compilar el informe | `cd docs/paper/final && pdflatex main.tex && pdflatex main.tex` | `main.pdf` |
| Regenerar la presentación | `cd docs/presentation && npm install && npm run build` | `Artemis_IV_UdeM.pptx` |
| Recapturar imágenes del visualizador | `cd docs/presentation && CHROME=/ruta/a/chrome npm run capture` (con el visualizador en el puerto 8000) | `docs/figures/viz_*.png` |
| Abrir el visualizador 3D | `python -m http.server 8000 -d frontend` → http://localhost:8000 | Misión completa (Fases 1–5) en el navegador |
| Pruebas del visualizador | `node --test frontend/tests/*.test.mjs` | Marcos, interpolación, línea de tiempo, telemetría y cifras contra `results.json` |
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
├── tests/                  # 132 pruebas automáticas (pytest)
├── scripts/
│   ├── run_mission.py      # Un solo comando: misión, figuras, informe y visualizador
│   ├── generate_figures.py # Figuras y números de las Fases 1–3
│   ├── nrho_figures.py     # Familia de halos y NRHO
│   ├── fetch_grail.py      # Descarga los coeficientes GRGM1200A
│   └── export_mission.py   # Trayectoria de la misión → frontend/data/mission.json
├── data/                   # Coeficientes de gravedad lunar GRGM1200A (grado 100)
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
