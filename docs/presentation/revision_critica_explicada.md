# Revisión crítica: errores encontrados y corregidos

**Guía de estudio para la diapositiva 22.** Para cada error se explica qué es cada constante, dónde está en el código, cuál era el problema, qué se hizo para corregirlo, cómo se verifica y de dónde salen los datos con que se comparó.

> Los enlaces apuntan a líneas del código. Ábrelos desde VS Code con Ctrl + clic.
> En el informe ([main.pdf](../paper/final/main.pdf)) todo esto está resumido en la **sección 5, página 7**.

---

## Idea general: por qué hicimos una revisión crítica

Que un programa corra sin errores no significa que esté bien. Puede dar números que parecen razonables y aun así violar una ley física. Por eso, antes de presentar resultados, revisamos cada parte con tres preguntas:

1. **¿Respeta las leyes físicas?** (conservación de la masa, de la energía y leyes de Kepler)
2. **¿El resultado tiene sentido?** (¿el cohete llega a órbita?, ¿los valores se parecen a los del SLS real?)
3. **¿El código es robusto?** (si cambio un dato, ¿todo se actualiza solo?)

Encontramos **7 problemas**. Mostrarlos no es admitir un fracaso: es **evidencia de rigor**. Es lo mismo que hace la NASA en sus revisiones de diseño antes de volar.

---

## Error 1: Balance de masa de los SRB (el más importante)

### Qué son las constantes involucradas
Los **SRB** (*Solid Rocket Boosters*) son los dos propulsores sólidos laterales. Sus datos están en [constants.py, línea 223](../../src/artemis_sim/constants.py#L223) (`SLS_B1B_SRB_SINGLE`):

| Constante | Valor | Qué significa | Línea |
|---|---|---|---|
| `propellant_mass_kg` | 628 680 kg | Combustible sólido de **cada** SRB | [226](../../src/artemis_sim/constants.py#L226) |
| `thrust_vac_n` | 16 000 000 N | Empuje **máximo** en vacío de cada SRB (16 MN) | [227](../../src/artemis_sim/constants.py#L227) |
| `isp_vac_s` | 268 s | Impulso específico, la eficiencia del motor | [228](../../src/artemis_sim/constants.py#L228) |

El par de SRB (dos unidades) está en `SLS_B1B_SRB_PAIR`, [línea 234](../../src/artemis_sim/constants.py#L234). El **tiempo de combustión** es `t_burn_srb_s = 126 s` y está en la configuración del ascenso, [ascent_solver.py, línea 245](../../src/artemis_sim/ascent_solver.py#L245).

### Cuál era el problema
El código original suponía que **cada SRB empujaba siempre con 16 MN**, de forma constante. Con eso, el consumo de combustible es:

$$\dot m = \frac{T}{I_{sp}\, g_0} = \frac{2 \times 16\,000\,000}{268 \times 9{,}80665} \approx 12\,176\ \text{kg/s}$$

Y el combustible del par (2 × 628 680 = 1 257 360 kg) se acaba en:

$$t = \frac{1\,257\,360}{12\,176} \approx 103\ \text{s}$$

**Pero el código mantenía los SRB encendidos hasta los 126 s.** Durante esos 23 segundos de más, el programa seguía restando masa al cohete, y como los SRB ya no tenían combustible, **le quitaba esa masa al combustible de la etapa central** (unas 280 toneladas).

### Por qué es grave
Viola la **conservación de la masa**: un motor estaba quemando combustible que no le pertenecía. Además, ese error afecta todo lo que sigue: la masa en el MECO, la velocidad final y el combustible disponible para el resto del vuelo.

### Qué se hizo para corregirlo
En la realidad, el empuje de un SRB **no es constante**. Depende de la forma en que se talla el combustible sólido dentro del cilindro (el "grano"): empuja fuerte al despegar, baja un poco cerca de Max-Q para reducir el esfuerzo aerodinámico, sube otra vez y al final se apaga gradualmente.

Se hicieron tres cambios:

1. **Perfil de empuje realista**, `SRB_THRUST_PROFILE`, [ascent_solver.py, línea 128](../../src/artemis_sim/ascent_solver.py#L128): una tabla que dice qué fracción del empuje máximo da el SRB en cada segundo (100 % al inicio, 85 % en Max-Q, 0 % a los 126 s).
2. **Función que lee ese perfil**, `srb_thrust_fraction()`, [línea 134](../../src/artemis_sim/ascent_solver.py#L134): devuelve la fracción f(t) para cualquier instante, y **0 después de los 126 s**.
3. **Factor de ajuste por conservación de masa**, `srb_thrust_scale()`, [línea 142](../../src/artemis_sim/ascent_solver.py#L142): calcula un número k que garantiza que el combustible quemado en los 126 s sea **exactamente** el que tienen los SRB:

$$k = \frac{m_p\, I_{sp}\, g_0}{T_{pico}\int_0^{126} f(t)\,dt} = 1{,}0033$$

El factor se aplica en las ecuaciones del ascenso, [línea 299](../../src/artemis_sim/ascent_solver.py#L299).

### Por qué el resultado k = 1,0033 es importante
Si los datos públicos fueran incoherentes, k habría salido muy distinto de 1 (por ejemplo 0,7 o 1,5). Que salga **1,0033**, apenas un 0,3 % de ajuste, demuestra que **el empuje máximo, el Isp, la masa de combustible y el tiempo de combustión publicados son consistentes entre sí**. El error estaba en suponer empuje constante, no en los datos.

### Cómo se verifica
Prueba `test_srb_burn_consumes_exactly_its_propellant`, [test_physics_corrections.py, línea 36](../../tests/test_physics_corrections.py#L36): integra numéricamente el flujo de masa durante los 126 s y comprueba que da **exactamente** la masa de combustible, con error menor que 0,0001 %. Otra prueba ([línea 51](../../tests/test_physics_corrections.py#L51)) verifica que el empuje sea cero después de los 126 s.

### De dónde salen los datos de comparación
- **Tiempo de combustión de ~126 s y empuje máximo de ~16 MN (3,6 millones de libras-fuerza):** datos públicos del fabricante de los propulsores, **Northrop Grumman**, y de la **NASA SLS Fact Sheet (2023)**, que está en [docs/paper/articles/](../paper/articles/).
- **Forma del perfil (empuje regresivo):** es el comportamiento estándar de los motores sólidos, descrito en **Sutton & Biblarz, *Rocket Propulsion Elements***, también en esa carpeta.

> **Frase para exponer:** "El error más grave violaba la conservación de la masa: con empuje constante, los propulsores sólidos se quedaban sin combustible a los 103 segundos, pero el código los mantenía encendidos hasta los 126 y les quitaba masa a la etapa central. Lo corregimos con un perfil de empuje realista ajustado para quemar exactamente su combustible. El ajuste necesario fue de solo 0,3 %, lo que confirma que los datos de la NASA son coherentes."

---

## Error 2: La trayectoria de ascenso se estrellaba

### Qué son los conceptos involucrados
- **Guiado:** la regla que decide hacia dónde apunta el motor en cada instante.
- **Pitch kick:** una pequeña inclinación inicial, poco después del despegue, para que el cohete empiece a curvarse hacia el este.
- **Giro por gravedad (*gravity turn*):** después del pitch kick, el motor apunta en la dirección en que se mueve el cohete, y la gravedad lo va curvando solo. Así el ángulo de ataque es cero y el aire no empuja de lado sobre el cohete.

La función original es `pitch_kick_direction()`, [ascent_solver.py, línea 72](../../src/artemis_sim/ascent_solver.py#L72).

### Cuál era el problema
El código original usaba **solo** giro por gravedad, con un pitch kick de **0,035 rad (unos 2°)**. Cuando probamos la simulación completa, **el cohete se estrellaba contra el suelo a los 388 segundos**. El giro por gravedad puro es muy sensible al ángulo inicial: un poco de más o de menos y el cohete se acuesta demasiado o sube casi vertical.

Además, la demostración original **solo simulaba hasta los 126 s**, sin separar los SRB ni continuar con la etapa central. No era un ascenso completo.

### Qué se hizo para corregirlo
1. **Guiado en tres tramos**, `linear_tangent_direction()`, [línea 155](../../src/artemis_sim/ascent_solver.py#L155):
   - 0 a 10 s: subida vertical.
   - 10 a 126 s: pitch kick + giro por gravedad (en la atmósfera, donde importa no cargar la estructura).
   - 126 s al MECO: **ley de tangente lineal**, fuera de la atmósfera.

$$\tan\theta(t) = \tan\theta_0 + (\tan\theta_f - \tan\theta_0)\,\frac{t - t_{sep}}{t_{MECO} - t_{sep}}$$

   Esta ley es **la óptima** (da la máxima velocidad final) para empujar en el vacío, y es la base del guiado que usaba el transbordador espacial.
2. **Los parámetros θ₀ = 0,4915 rad y θ_f = 0,1548 rad** ([línea 160](../../src/artemis_sim/ascent_solver.py#L160)) se obtuvieron **resolviendo un sistema de ecuaciones** con `fsolve` para que el MECO quede a **160 km de altura** y con **ángulo de trayectoria 0** (volando horizontal).
3. **Simulación completa**, `simulate_full_ascent()`, [línea 544](../../src/artemis_sim/ascent_solver.py#L544): SRB + etapa central → separación de SRB (`jettison_boosters()`, [línea 417](../../src/artemis_sim/ascent_solver.py#L417)) → solo etapa central → MECO. Incluye un evento que detecta si el cohete toca el suelo (`event_ground_impact()`, [línea 402](../../src/artemis_sim/ascent_solver.py#L402)).

### Cómo se verifica
Prueba `test_full_ascent_reaches_meco`, [test_physics_corrections.py, línea 65](../../tests/test_physics_corrections.py#L65): comprueba que se llega al MECO, que la separación ocurre a los 126 s, que la masa final es la correcta y que la altura está entre 140 y 180 km.

### De dónde salen los datos de comparación
- **MECO a unos 8 minutos:** el cálculo independiente es tiempo = combustible / flujo = 987 460 kg / 2 055 kg/s ≈ **480 s**, y la simulación da 480,5 s. ✓
- **Ley de tangente lineal:** **Curtis, *Orbital Mechanics for Engineering Students*** y la literatura del guiado PEG del transbordador.

> **Frase:** "Con el programa original el cohete se estrellaba a los 388 segundos. Implementamos un guiado en tres tramos como el de los lanzadores reales, con la ley de tangente lineal, que es la óptima en el vacío, y resolvimos sus parámetros para llegar a 160 km volando horizontal."

---

## Error 3: Eventos con números fijos en el código

### Qué es un "evento"
`solve_ivp`, el integrador de SciPy, permite definir **eventos**: condiciones que, al cumplirse, detienen la simulación. Por ejemplo, "detente cuando t = 126 s" (separación de SRB) o "detente cuando la masa llegue al mínimo" (MECO).

### Cuál era el problema
Los eventos originales tenían los valores **escritos directamente en el código**:
- La separación de los SRB, fija en **126 s**.
- El MECO, con una masa superior fija de **180 000 kg**.

Si alguien cambiaba la configuración del cohete (otra carga útil, otro tiempo de combustión), **los eventos no se enteraban**, y la simulación se detenía en el momento equivocado sin avisar. En programación esto se llama **"números mágicos"**.

### Qué se hizo para corregirlo
Se crearon **"fábricas" de eventos** que leen los valores desde la configuración del cohete (`AscentConfig`, [línea 212](../../src/artemis_sim/ascent_solver.py#L212)):
- `make_srb_burnout_event(config)`, [línea 365](../../src/artemis_sim/ascent_solver.py#L365): usa `config.t_burn_srb_s`.
- `make_core_burnout_event(config)`, [línea 376](../../src/artemis_sim/ascent_solver.py#L376): calcula la masa de corte a partir de la masa seca de la etapa central y la carga superior.

Los nombres antiguos se mantienen ([líneas 413–414](../../src/artemis_sim/ascent_solver.py#L413)) para no romper el código que ya los usaba.

### Cómo se verifica
Prueba `test_event_factories_use_config`, [línea 56](../../tests/test_physics_corrections.py#L56): crea un cohete con **otros** valores (100 s y 150 t) y comprueba que los eventos los respetan.

> **Frase:** "Algunos valores estaban escritos a mano dentro de los eventos, así que cambiar el cohete no los actualizaba. Ahora se leen desde la configuración, y el código es robusto ante cambios."

---

## Error 4: El movimiento de la Luna era inconsistente

### Qué son las constantes involucradas
En [ephemeris.py](../../src/artemis_sim/ephemeris.py) la Luna se modela dando vueltas a la Tierra en un círculo:

| Constante | Valor | Qué significa | Línea |
|---|---|---|---|
| `LUNAR_ORBITAL_RADIUS_M` | 384 400 000 m | Distancia media Tierra–Luna | [29](../../src/artemis_sim/ephemeris.py#L29) |
| `LUNAR_MEAN_MOTION_RAD_S` | 2,6653 × 10⁻⁶ rad/s | Qué tan rápido gira la Luna (velocidad angular n) | [35](../../src/artemis_sim/ephemeris.py#L35) |
| `EARTH.mu_m3_s2` | 3,986 × 10¹⁴ m³/s² | μ_E = G·M_Tierra | [constants.py, 172](../../src/artemis_sim/constants.py#L172) |
| `MOON.mu_m3_s2` | 4,905 × 10¹² m³/s² | μ_L = G·M_Luna | [constants.py, 183](../../src/artemis_sim/constants.py#L183) |

### Cuál era el problema
El código usaba n = 2,6617 × 10⁻⁶ rad/s, el valor **observado** de la Luna real (un mes sidéreo de 27,32 días). Pero en nuestro modelo la Luna gira en un círculo perfecto bajo la gravedad de la Tierra y la Luna solamente, y en ese caso la **tercera ley de Kepler** exige:

$$n = \sqrt{\frac{\mu_E + \mu_L}{d^3}} = 2{,}6653 \times 10^{-6}\ \text{rad/s}\quad(27{,}28\ \text{días})$$

La diferencia es solo de **0,14 %**, pero hace que el modelo sea **internamente inconsistente**: la Luna giraba a una velocidad que su propia gravedad no puede sostener. La consecuencia práctica es que la **integral de Jacobi** (error 5) no se conservaba, así que perdíamos nuestra mejor herramienta para verificar el simulador.

**¿Por qué la Luna real gira a 2,6617?** Porque en la realidad también actúan el **Sol** y la **excentricidad** de la órbita, que nuestro modelo no incluye. El valor observado incluye esos efectos; el valor kepleriano es el correcto **para nuestro modelo**.

### Qué se hizo para corregirlo
Se calcula n con la tercera ley de Kepler, [ephemeris.py, línea 35](../../src/artemis_sim/ephemeris.py#L35), y es el valor por defecto de `LunarOrbitConfig` ([línea 59](../../src/artemis_sim/ephemeris.py#L59)). El comentario del código explica la diferencia con el valor observado.

### Cómo se verifica
Prueba `test_mean_motion_is_keplerian`, [test_physics_corrections.py, línea 103](../../tests/test_physics_corrections.py#L103): comprueba que n²·d³ = μ_E + μ_L con precisión de 10⁻¹².

### De dónde salen los datos de comparación
- **Mes sidéreo de 27,32 días y distancia de 384 400 km:** **NASA Moon Fact Sheet**.
- **μ_E:** estándar **WGS84 / IERS**. **μ_L:** efemérides **JPL DE421**.

> **Frase:** "La velocidad de la Luna en el modelo era la observada, pero no era coherente con la tercera ley de Kepler usando solo la Tierra y la Luna. La diferencia era pequeña, 0,14 %, pero rompía la conservación de la integral de Jacobi. Ahora se calcula con Kepler, así que el modelo es consistente."

---

## Error 5: Se medía una "energía" que no debía conservarse

### Qué son los conceptos involucrados
- **Energía mecánica específica:** ε = ½v² − μ_E/r − μ_L/|r − r_L|, la energía cinética más la potencial por kilo. Está en `compute_system_energy()`, [symplectic_solver.py, línea 248](../../src/artemis_sim/symplectic_solver.py#L248).
- **Integral de Jacobi:** la cantidad que **sí** se conserva en el problema de la Tierra, la Luna y la nave. Es la energía medida desde un sistema que **gira junto con la Luna**. Está en `compute_jacobi_constant()`, [línea 435](../../src/artemis_sim/symplectic_solver.py#L435).

### Cuál era el problema
Para comprobar que el integrador Verlet funcionaba, se medía si la **energía** se conservaba. Pero cuando la Luna está presente, **la energía no tiene por qué conservarse**: la Luna se mueve, así que la fuerza que ejerce sobre la nave cambia con el tiempo, y un sistema así intercambia energía. Es el mismo efecto de una **asistencia gravitatoria**, cuando una sonda gana velocidad al pasar cerca de un planeta.

El documento además afirmaba que Verlet "conserva exactamente la energía del sistema Tierra-Luna-nave", lo cual es **falso**.

**Analogía:** es como juzgar a un arquero por cuántos goles le meten cuando juega de delantero. La medida era la equivocada.

### Qué se hizo para corregirlo
Se implementó la **integral de Jacobi**:

$$E_J = \tfrac12\|\mathbf v_{rot}\|^2 - \tfrac12 n^2(x_b^2 + y_b^2) - \frac{\mu_E}{r_1} - \frac{\mu_L}{r_2}$$

En un sistema que gira con la Luna, la Tierra y la Luna quedan **quietas**, el problema ya no depende del tiempo y aparece esta cantidad que se conserva. Es el invariante clásico del **problema restringido de tres cuerpos**.

**Resultado:** durante el viaje a la Luna, la energía geocéntrica cambia un **77 %** (y es correcto que cambie), mientras que la integral de Jacobi se mantiene con un error de solo **0,001 %** (9,7 × 10⁻⁶).

### Cómo se verifica
Prueba `test_jacobi_conserved_with_moon`, [test_physics_corrections.py, línea 108](../../tests/test_physics_corrections.py#L108): simula 5 días y comprueba que Jacobi varía menos de 10⁻⁶, mientras que la energía varía al menos 100 veces más.

### De dónde salen los datos de comparación
**Szebehely, *Theory of Orbits* (1967)**, la referencia clásica del problema restringido de tres cuerpos, y **Hairer, Lubich & Wanner, *Geometric Numerical Integration* (2006)** para la conservación con integradores simplécticos.

> **Frase:** "Con la Luna presente la energía no se conserva, porque la Luna se mueve; verificar el integrador con la energía era usar la medida equivocada. Implementamos la integral de Jacobi, que sí es constante, y Verlet la conserva con un error del 0,001 %."

---

## Error 6: El método del disparo no convergía

### Qué son los conceptos involucrados
- **Método del disparo:** para saber con qué velocidad salir hacia la Luna, se prueba una velocidad, se simulan los 4 días de viaje, se mide qué tan lejos se quedó del objetivo y se corrige. `solve_tli_shooting()`, [shooting_method.py, línea 303](../../src/artemis_sim/shooting_method.py#L303).
- **Newton-Raphson:** el método que decide cómo corregir en cada intento. Converge muy rápido, pero **solo si el primer intento está cerca de la solución**.
- **Semilla (primer intento):** antes se calculaba con `initial_guess_vis_viva()`, [línea 217](../../src/artemis_sim/shooting_method.py#L217).

### Cuál era el problema
La semilla vis-viva calculaba **cuánta** velocidad hacía falta para llegar a la distancia de la Luna, pero **no hacia dónde**. El punto más lejano de la órbita quedaba al lado opuesto del encendido, y **la Luna no estaba ahí** cuando llegaba la nave (la Luna se mueve unos 52° en 4 días). El primer intento quedaba a **677 000 km** del objetivo, casi el doble de la distancia a la Luna, y Newton no lograba converger ni en 20 intentos.

### Qué se hizo para corregirlo
Se creó `kepler_transfer_geometry()`, [shooting_method.py, línea 491](../../src/artemis_sim/shooting_method.py#L491), que resuelve la **ecuación de Kepler** para saber dónde encender:

$$t = \sqrt{\frac{a^3}{\mu_E}}\,(E - e\sin E) = t_{vuelo}$$

1. Busca la elipse que llega a la distancia del objetivo **justo en 4 días** (con el método de Brent).
2. Calcula el ángulo que recorre la nave en ese viaje (**176,9°**).
3. Ubica el punto de encendido **176,9° por detrás** de donde estará la Luna. Esto se hace en [generate_figures.py, líneas 455–456](../../scripts/generate_figures.py#L455).

**Resultado:** el error inicial bajó de 677 000 km a **23 930 km**, y lo que queda se debe solo a la gravedad de la Luna, que la fórmula de Kepler no considera. Newton converge en **5 iteraciones**, con un error final de **0,4 mm**.

### Cómo se verifica
Las pruebas de [test_shooting_method.py](../../tests/test_shooting_method.py) verifican la convergencia del método. El Δv final de **3 150 m/s** coincide con el valor de referencia.

### De dónde salen los datos de comparación
- **Δv de TLI de 3,1 a 3,2 km/s:** valor clásico de los libros de mecánica orbital (**Curtis, *Orbital Mechanics***). Las misiones Apolo usaban valores en ese rango.
- **Ecuación de Kepler y método de Brent:** mecánica orbital clásica y análisis numérico estándar.

> **Frase:** "El método del disparo no convergía porque el primer intento apuntaba a donde la Luna no iba a estar: quedaba a 677 000 km. Resolvimos la ecuación de Kepler para elegir el punto de encendido correcto, y ahora converge en 5 iteraciones con un Δv de 3 150 m/s, que coincide con el valor clásico."

---

## Error 7: Errores de física en el documento

El borrador del informe tenía cuatro afirmaciones incorrectas. Todas se corrigieron en [main.tex](../paper/final/main.tex):

| Error del borrador | Por qué estaba mal | Corrección |
|---|---|---|
| La ecuación del ascenso incluía **Coriolis y centrífuga** | Esas fuerzas solo aparecen en un sistema que **gira** (ECEF). El código usa un sistema **inercial** (ECI), donde no existen. Ponerlas sería contar la rotación de la Tierra dos veces. | Ecuación reescrita en ECI. La rotación entra por v_rel = v − ω×r, en `compute_relative_velocity()` de [physics_engine.py](../../src/artemis_sim/physics_engine.py). |
| Se usaba RK45 "por la **rigidez** (*stiffness*) del problema" | RK45 es un método **explícito**, que justamente **no sirve** para problemas rígidos. Además, el ascenso no es rígido. | La justificación correcta es su **paso adaptativo** y la **detección de eventos**. |
| Verlet "conserva exactamente la energía" | Con la Luna moviéndose, la energía no se conserva (error 5). | Se explica el hamiltoniano modificado y la integral de Jacobi. |
| Faltaba el **término indirecto** en la gravedad | En coordenadas centradas en la Tierra, la Tierra también es atraída por la Luna, y hay que restar esa aceleración. El código sí lo tenía. | Ecuación corregida, coherente con `compute_n_body_acceleration()`, [symplectic_solver.py, línea 44](../../src/artemis_sim/symplectic_solver.py#L44). |

Además se movieron al **trabajo futuro** cosas que el borrador presentaba como hechas (la órbita NRHO, la gravedad lunar con mascons y el descenso del HLS), y se reemplazó una referencia bibliográfica que no se pudo verificar por documentos oficiales de la NASA.

> **Frase:** "También corregimos el documento: mezclaba un sistema de referencia que gira con uno que no gira, justificaba RK45 con un argumento incorrecto y afirmaba una conservación de energía que no ocurre. Ahora el documento describe exactamente lo que hace el código."

---

## Resumen: fuentes de los datos de comparación

| Dato de referencia | Valor | Fuente | ¿En el repo? |
|---|---|---|---|
| Parámetros del SLS (masas, motores) | Tabla de la diapositiva 4 | NASA SLS Fact Sheet (2023); NASA SLS Lift Capabilities (2018) | ✅ [docs/paper/articles/](../paper/articles/) |
| Combustión de los SRB y empuje pico | ~126 s, ~16 MN | NASA / Northrop Grumman | Parcial (Fact Sheet) |
| Teoría de motores cohete (empuje, Isp, perfil del grano) | — | Sutton & Biblarz, *Rocket Propulsion Elements* | ✅ docs/paper/articles/ |
| Plan del programa Artemis | — | NASA Artemis Plan (2020) | ✅ docs/paper/articles/ |
| μ de la Tierra, radio y rotación | 3,986 × 10¹⁴ m³/s² | WGS84 / IERS | — |
| μ de la Luna y mes sidéreo | 4,905 × 10¹² m³/s², 27,32 días | JPL DE421 / NASA Moon Fact Sheet | — |
| Atmósfera y velocidad del sonido | 340,3 m/s al nivel del mar | U.S. Standard Atmosphere 1976 | — |
| Δv de la TLI | 3,1–3,2 km/s | Curtis, *Orbital Mechanics* | — |
| Integral de Jacobi | — | Szebehely, *Theory of Orbits* | — |
| Integradores simplécticos | — | Hairer, Lubich & Wanner (2006) | — |

> ⚠️ **Sobre Max-Q:** decimos que 27,5 kPa es "del orden" de los valores de lanzadores pesados (entre 25 y 35 kPa). **No afirmes un valor exacto del SLS real**, porque no tenemos esa cifra de una fuente oficial en el repositorio. Si te preguntan, responde: *"Es del mismo orden de magnitud que los valores publicados para lanzadores pesados como el transbordador."*

---

## Cómo argumentar la diapositiva completa (60 segundos)

> "Antes de presentar resultados hicimos una revisión crítica, verificando tres cosas: que se respeten las leyes físicas, que los resultados tengan sentido y que el código sea robusto. Encontramos siete problemas.
> El más grave violaba la **conservación de la masa**: los propulsores sólidos quemaban combustible que ya no tenían. Lo corregimos con un perfil de empuje realista, y el ajuste necesario fue de solo 0,3 %, lo que confirma que los datos de la NASA son coherentes.
> También encontramos que el cohete **se estrellaba**, y agregamos un guiado como el de los lanzadores reales; que el método del disparo **no convergía**, y lo resolvimos con la ecuación de Kepler; y que verificábamos el integrador con una **energía que no debía conservarse**, así que pasamos a la integral de Jacobi.
> Cada corrección tiene una **prueba automática** que garantiza que el error no vuelva a aparecer."
