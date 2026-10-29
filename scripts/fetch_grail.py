"""Descarga los coeficientes de gravedad lunar GRGM1200A (misión GRAIL) truncados en grado N.

Fuente: NASA Planetary Data System, nodo de Geociencias,
    https://pds-geosciences.wustl.edu/grail/grail-l-lgrs-5-rdr-v1/grail_1001/shadr/
    archivo gggrx_1200a_sha.tab (Goossens et al., 2016).
El archivo está ordenado por grado, así que basta leer las primeras líneas: no se baja entero.

Formato (SHADR): la primera línea trae R_ref [km], GM [km³/s²], σ(GM), grado máximo, orden
máximo, indicador de normalización y longitud/latitud de referencia. Cada línea siguiente es
    n, m, C̄_nm, S̄_nm, σ(C̄_nm), σ(S̄_nm)
con coeficientes totalmente normalizados (4π). El marco es el de ejes principales (PA) lunar.

Uso (desde la raíz del repositorio):
    python scripts/fetch_grail.py [N]
Escribe data/grgm1200a_n{N}.npz con C, S (matrices (N+1)×(N+1)), R [m], GM [m³/s²] y la fuente.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
URL = (
    "https://pds-geosciences.wustl.edu/grail/grail-l-lgrs-5-rdr-v1/grail_1001/shadr/"
    "gggrx_1200a_sha.tab"
)


def main(n_max: int = 100) -> None:
    n_lines = 1 + sum(n + 1 for n in range(1, n_max + 1))
    with urllib.request.urlopen(URL, timeout=60) as resp:
        lines = [resp.readline().decode("ascii") for _ in range(n_lines)]

    header = [f.strip() for f in lines[0].split(",")]
    radius_m, gm_m3_s2 = float(header[0]) * 1e3, float(header[1]) * 1e9
    c = np.zeros((n_max + 1, n_max + 1))
    s = np.zeros((n_max + 1, n_max + 1))
    c[0, 0] = 1.0
    for line in lines[1:]:
        f = line.split(",")
        n, m = int(f[0]), int(f[1])
        c[n, m], s[n, m] = float(f[2]), float(f[3])

    out = ROOT / "data" / f"grgm1200a_n{n_max}.npz"
    out.parent.mkdir(exist_ok=True)
    np.savez_compressed(out, C=c, S=s, radius_m=radius_m, gm_m3_s2=gm_m3_s2, source=np.array(URL))
    print(f"GRGM1200A hasta n = {n_max}: R = {radius_m:.0f} m, GM = {gm_m3_s2:.6e} m³/s²")
    print(f"C̄20 = {c[2, 0]:.6e}, C̄22 = {c[2, 2]:.6e} → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
