"""Renderiza las fórmulas de la presentación a PNG transparentes (matplotlib mathtext)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).parent / "assets"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"mathtext.fontset": "cm", "font.family": "serif"})

FORMULAS = {
    "eq_asc_r": r"$\dot{\mathbf{r}} = \mathbf{v}$",
    "eq_asc_v": r"$\dot{\mathbf{v}} = \dfrac{T(t,h)}{m}\,\hat{\mathbf{u}} + \dfrac{\mathbf{D}}{m} - \dfrac{\mu_E}{\|\mathbf{r}\|^3}\,\mathbf{r}$",
    "eq_asc_m": r"$\dot{m} = -\sum_k \dfrac{T_{vac,k}(t)}{I_{sp,k}\,g_0}$",
    "eq_vrel": r"$\mathbf{v}_{rel} = \mathbf{v} - \boldsymbol{\omega}_E \times \mathbf{r}$",
    "eq_thrust": r"$T = T_{vac} - p_a(h)\,A_e$",
    "eq_srb": r"$T_{SRB}(t) = k\,f(t)\,T_{pico}$",
    "eq_k": r"$k = \dfrac{m_{p}\,I_{sp}\,g_0}{T_{pico}\int_0^{t_b} f(t)\,dt} = 1.0033$",
    "eq_sound": r"$a = \sqrt{\gamma R T(h)}, \qquad M = \dfrac{\|\mathbf{v}_{rel}\|}{a}$",
    "eq_drag": r"$\mathbf{D} = -\frac{1}{2}\,\rho(h)\,C_D(M)\,A_{ref}\,\|\mathbf{v}_{rel}\|\,\mathbf{v}_{rel}$",
    "eq_rho": r"$\rho(h) = \rho_0\,e^{-h/H_\rho}$",
    "eq_lintan": r"$\tan\theta(t) = \tan\theta_0 + (\tan\theta_f - \tan\theta_0)\,\dfrac{t - t_{sep}}{t_{MECO} - t_{sep}}$",
    "eq_cr3bp": r"$\ddot{\mathbf{r}} = -\mu_E\dfrac{\mathbf{r}}{\|\mathbf{r}\|^3} + \mu_L\left[\dfrac{\mathbf{r}_L - \mathbf{r}}{\|\mathbf{r}_L - \mathbf{r}\|^3} - \dfrac{\mathbf{r}_L}{\|\mathbf{r}_L\|^3}\right]$",
    "eq_n": r"$n = \sqrt{\dfrac{\mu_E + \mu_L}{d^3}} = 2.6653\times10^{-6}\ \mathrm{rad/s}$",
    "eq_verlet": r"$\mathbf{v}_{n+\frac{1}{2}} = \mathbf{v}_n + \frac{\Delta t}{2}\mathbf{a}_n \quad \mathbf{r}_{n+1} = \mathbf{r}_n + \Delta t\,\mathbf{v}_{n+\frac{1}{2}} \quad \mathbf{v}_{n+1} = \mathbf{v}_{n+\frac{1}{2}} + \frac{\Delta t}{2}\mathbf{a}_{n+1}$",
    "eq_hmod": r"$\tilde{H} = H + \mathcal{O}(\Delta t^2)\ \Rightarrow\ |E(t) - E_0| \leq C\,\Delta t^2$",
    "eq_jacobi": r"$E_J = \frac{1}{2}\|\mathbf{v}_{rot}\|^2 - \frac{1}{2}n^2(x_b^2 + y_b^2) - \dfrac{\mu_E}{r_1} - \dfrac{\mu_L}{r_2}$",
    "eq_shoot": r"$\mathbf{F}(\Delta\mathbf{v}) = \mathbf{r}(t_f;\ \mathbf{r}_0,\ \mathbf{v}_0 + \Delta\mathbf{v}) - \mathbf{r}_{obj} = \mathbf{0}$",
    "eq_newton": r"$J\,\mathbf{d} = -\mathbf{F}, \qquad J_{:,j} = \dfrac{\mathbf{F}(\Delta\mathbf{v} + h\mathbf{e}_j) - \mathbf{F}(\Delta\mathbf{v} - h\mathbf{e}_j)}{2h}$",
    "eq_kepler": r"$t(r_a) = \sqrt{a^3/\mu_E}\,(E - e\sin E) = t_f$",
    "eq_tsiol": r"$\Delta v = I_{sp}\,g_0\,\ln\dfrac{m_0}{m_f}$",
}

for name, tex in FORMULAS.items():
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.text(0, 0, tex, fontsize=26, color="#0b1d3a")
    fig.savefig(OUT / f"{name}.png", dpi=220, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
print(f"{len(FORMULAS)} fórmulas renderizadas en {OUT}")
