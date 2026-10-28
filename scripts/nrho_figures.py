"""Figura de la familia de halos L2 sur y la NRHO 9:2 (Etapa 3).

Uso (desde la raíz del repositorio):
    python scripts/nrho_figures.py
Escribe docs/figures/fig09_familia_halo.png.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from artemis_sim.constants import MOON  # noqa: E402
from artemis_sim.cr3bp import MU, UNITS, lagrange_points  # noqa: E402
from artemis_sim.periodic_orbits import continue_family, find_nrho  # noqa: E402

OUT = ROOT / "docs" / "figures" / "fig09_familia_halo.png"


def main() -> None:
    nrho = find_nrho()
    family = continue_family(nrho, 0.004, 80, parameter="x")[::4]
    print(
        f"NRHO 9:2: P = {nrho.period_days:.3f} d, ν = {nrho.stability_index:.3f}; "
        f"familia: {len(family)} órbitas, P de {family[0].period_days:.2f} "
        f"a {family[-1].period_days:.2f} d"
    )

    km = UNITS.length_m / 1e3
    moon_x = 1.0 - MU
    x_l2 = lagrange_points()["L2"][0]
    norm = Normalize(family[0].period_days, family[-1].period_days)
    cmap = plt.get_cmap("viridis")

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), constrained_layout=True)
    views = [(0, 2, "x [km]", "z [km]"), (1, 2, "y [km]", "z [km]"), (0, 1, "x [km]", "y [km]")]
    for ax, (i, j, xl, yl) in zip(axes, views, strict=True):
        for orbit in family[1:]:
            s = orbit.sample(400)
            s[0] -= moon_x
            ax.plot(s[i] * km, s[j] * km, color=cmap(norm(orbit.period_days)), lw=0.8)
        s = nrho.sample(600)
        s[0] -= moon_x
        ax.plot(s[i] * km, s[j] * km, color="#e8702a", lw=2.2, label="NRHO 9:2 (6,56 d)")
        ax.add_patch(plt.Circle((0, 0), MOON.equatorial_radius_m / 1e3, color="0.55", zorder=3))
        if i == 0:
            ax.plot((x_l2 - moon_x) * km, 0, "k+", ms=10, mew=1.5, label="L2")
        ax.set_xlabel(xl)
        ax.set_ylabel(yl)
        ax.set_aspect("equal")
        ax.grid(alpha=0.3)
    axes[0].legend(loc="lower left", fontsize=8)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axes, label="Periodo [días]")
    fig.suptitle("Familia de órbitas de halo L2 sur (marco rotante, centrado en la Luna)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=200)
    print(f"Figura: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
