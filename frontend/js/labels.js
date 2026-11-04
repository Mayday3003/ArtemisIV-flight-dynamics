// Etiquetas HTML sobre la escena: se proyectan cada cuadro, se ocultan detrás de los cuerpos y
// ceden el lugar a las de mayor prioridad cuando se solapan.
import * as THREE from "three";

export function createLabels(container, camera) {
  const items = [];
  const ndc = new THREE.Vector3();
  const toPoint = new THREE.Vector3();
  const toCenter = new THREE.Vector3();

  function add(text, { priority = 1, kind = "" } = {}) {
    const el = document.createElement("div");
    el.className = `label ${kind}`;
    el.textContent = text;
    container.appendChild(el);
    const item = { el, priority, pos: new THREE.Vector3(), active: true, w: 0 };
    items.push(item);
    items.sort((a, b) => b.priority - a.priority);
    return item;
  }

  /** ¿La esfera tapa el punto? occluder = { center, radius }. */
  function hidden(point, { center, radius }) {
    toPoint.copy(point).sub(camera.position);
    toCenter.copy(center).sub(camera.position);
    const along = toCenter.dot(toPoint.clone().normalize());
    if (along < 0 || along > toPoint.length()) return false;
    // Esfera algo menor que el cuerpo: lo que está sobre la superficie cerca del limbo sigue visible
    return toCenter.lengthSq() - along * along < radius * radius * 0.98;
  }

  function update(enabled, occluders) {
    const W = container.clientWidth;
    const H = container.clientHeight;
    const placed = [];
    for (const it of items) {
      let show = enabled && it.active;
      if (show) {
        ndc.copy(it.pos).project(camera);
        show = ndc.z < 1 && Math.abs(ndc.x) < 0.98 && Math.abs(ndc.y) < 0.96;
      }
      if (show) show = !occluders.some((o) => o !== it.body && hidden(it.pos, o));
      if (show) {
        const x = ((ndc.x + 1) / 2) * W;
        const y = ((1 - ndc.y) / 2) * H;
        it.w ||= it.el.offsetWidth || 60;
        const box = [x, y - 10, x + it.w + 12, y + 10];
        show = !placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]);
        if (show) {
          placed.push(box);
          it.el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
        }
      }
      it.el.classList.toggle("on", show);
    }
  }
  return { add, update, hidden };
}
