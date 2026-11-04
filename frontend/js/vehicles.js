// Siluetas de los vehículos: sprites de tamaño fijo en pantalla (a escala real serían invisibles).
import * as THREE from "three";

const WHITE = "#f2f5fa";
const ORANGE = "#e8702a";
const GREY = "#aeb8c7";
const MIN_SILHOUETTE = 0.02;

/** Cada dibujo apunta hacia arriba en un lienzo de 128×128. */
const DRAW = {
  sls(g) {
    core(g);
    g.fillStyle = WHITE;
    for (const x of [38, 80]) {
      g.fillRect(x, 44, 10, 66);
      tri(g, x, 44, x + 10, 44, x + 5, 32);
    }
  },
  core,
  eus(g) {
    g.fillStyle = WHITE;
    g.fillRect(52, 54, 24, 44);
    capsule(g, 52);
  },
  orion(g) {
    g.fillStyle = GREY;
    g.fillRect(28, 66, 72, 6); // paneles solares
    g.fillStyle = WHITE;
    g.fillRect(52, 60, 24, 26);
    capsule(g, 60);
  },
  hls(g) {
    g.fillStyle = WHITE;
    g.fillRect(52, 18, 24, 76);
    tri(g, 52, 18, 76, 18, 64, 4);
    g.fillStyle = ORANGE;
    g.fillRect(52, 44, 24, 5);
    g.strokeStyle = GREY;
    g.lineWidth = 4;
    g.beginPath();
    g.moveTo(54, 88);
    g.lineTo(38, 112);
    g.moveTo(74, 88);
    g.lineTo(90, 112);
    g.stroke();
  },
  dot(g) {
    g.fillStyle = WHITE;
    g.beginPath();
    g.arc(64, 64, 44, 0, 2 * Math.PI);
    g.fill();
  },
  gateway(g) {
    g.fillStyle = GREY;
    g.fillRect(16, 58, 96, 12);
    g.fillStyle = WHITE;
    g.fillRect(50, 36, 28, 56);
    g.fillRect(44, 44, 40, 10);
  },
};

function tri(g, ax, ay, bx, by, cx, cy) {
  g.beginPath();
  g.moveTo(ax, ay);
  g.lineTo(bx, by);
  g.lineTo(cx, cy);
  g.fill();
}

function core(g) {
  g.fillStyle = ORANGE;
  g.fillRect(52, 40, 24, 74);
  g.fillStyle = WHITE;
  g.fillRect(52, 26, 24, 16);
  tri(g, 52, 26, 76, 26, 64, 8);
}

function capsule(g, y) {
  g.fillStyle = GREY;
  tri(g, 50, y, 78, y, 64, y - 22);
}

function makeTexture(id) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  g.shadowColor = "rgba(160, 200, 255, 0.9)";
  g.shadowBlur = 10;
  DRAW[id](g);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function sprite(map, scale) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map, sizeAttenuation: false, depthTest: false }));
  s.scale.setScalar(scale);
  s.renderOrder = 10;
  return s;
}

export function createShip(scene) {
  const textures = Object.fromEntries(Object.keys(DRAW).map((k) => [k, makeTexture(k)]));
  const ship = sprite(textures.sls, 0.05);
  scene.add(ship);
  const gateway = sprite(textures.gateway, 0.045);
  scene.add(gateway);

  /** Lejos la silueta no se distingue: por debajo de este tamaño se dibuja un punto. */
  function setLook(s, id, scale) {
    s.scale.setScalar(scale);
    const map = textures[scale < MIN_SILHOUETTE ? "dot" : id];
    if (s.material.map !== map) {
      s.material.map = map;
      s.material.needsUpdate = true;
    }
  }
  return { ship, gateway, setLook };
}
