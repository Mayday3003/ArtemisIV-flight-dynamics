// Escena 3D: renderizador, cámara, Tierra, Luna, estrellas y luces.
// Escala: 1 unidad de escena = 1 000 km. El eje +Z de ECI apunta "arriba" (camera.up).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

export const KM_PER_UNIT = 1000;

/** Textura procedural de la Tierra: océano, casquetes y retícula de 30° (sin descargas). */
function earthTexture() {
  const c = document.createElement("canvas");
  c.width = 1024;
  c.height = 512;
  const g = c.getContext("2d");
  const grad = g.createLinearGradient(0, 0, 0, c.height);
  grad.addColorStop(0, "#e8eef5");
  grad.addColorStop(0.08, "#1d5fa8");
  grad.addColorStop(0.5, "#0f3f7a");
  grad.addColorStop(0.92, "#1d5fa8");
  grad.addColorStop(1, "#e8eef5");
  g.fillStyle = grad;
  g.fillRect(0, 0, c.width, c.height);
  g.strokeStyle = "rgba(255,255,255,0.25)";
  g.lineWidth = 1;
  for (let lon = 0; lon < 360; lon += 30) {
    const x = (lon / 360) * c.width;
    g.beginPath();
    g.moveTo(x, 0);
    g.lineTo(x, c.height);
    g.stroke();
  }
  for (let lat = -60; lat <= 60; lat += 30) {
    const y = ((90 - lat) / 180) * c.height;
    g.beginPath();
    g.moveTo(0, y);
    g.lineTo(c.width, y);
    g.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function moonTexture() {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 256;
  const g = c.getContext("2d");
  g.fillStyle = "#9a9a9a";
  g.fillRect(0, 0, c.width, c.height);
  // Cráteres pseudoaleatorios con semilla fija (la Luna se ve igual en cada carga)
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 260; i++) {
    const r = 2 + rnd() * 12;
    g.fillStyle = `rgba(${60 + rnd() * 60},${60 + rnd() * 60},${60 + rnd() * 60},0.45)`;
    g.beginPath();
    g.arc(rnd() * c.width, rnd() * c.height, r, 0, 2 * Math.PI);
    g.fill();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** Esfera con los polos sobre el eje Z (SphereGeometry los pone sobre Y). */
function zUpSphere(radius, segments) {
  const geo = new THREE.SphereGeometry(radius, segments, segments / 2);
  geo.rotateX(Math.PI / 2);
  return geo;
}

function starField(count, radius) {
  const pos = new Float32Array(count * 3);
  let seed = 42;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < count; i++) {
    const z = 2 * rnd() - 1;
    const a = 2 * Math.PI * rnd();
    const s = Math.sqrt(1 - z * z);
    pos.set([radius * s * Math.cos(a), radius * s * Math.sin(a), radius * z], 3 * i);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({ color: 0xffffff, size: 1.5, sizeAttenuation: false });
  return new THREE.Points(geo, mat);
}

export function createScene(container, bodies) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(container.clientWidth, container.clientHeight);
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x02040a);

  const camera = new THREE.PerspectiveCamera(50, container.clientWidth / container.clientHeight, 1e-5, 1e6);
  camera.up.set(0, 0, 1);
  camera.position.set(2, -2, 1);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 1e-3;
  controls.maxDistance = 5e3;

  scene.add(new THREE.AmbientLight(0xffffff, 0.25));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  scene.add(sun, sun.target);

  const earth = new THREE.Mesh(
    zUpSphere(bodies.earth.radius_km / KM_PER_UNIT, 96),
    new THREE.MeshStandardMaterial({ map: earthTexture(), roughness: 0.9 })
  );
  earth.matrixAutoUpdate = false;
  scene.add(earth);

  const moon = new THREE.Mesh(
    zUpSphere(bodies.moon.radius_km / KM_PER_UNIT, 64),
    new THREE.MeshStandardMaterial({ map: moonTexture(), roughness: 1 })
  );
  scene.add(moon);

  const stars = starField(3000, 4e3);
  scene.add(stars);

  const axes = new THREE.AxesHelper(bodies.earth.radius_km * 2 / KM_PER_UNIT);
  axes.visible = false;
  scene.add(axes);

  function resize() {
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  }
  window.addEventListener("resize", resize);

  return { THREE, renderer, scene, camera, controls, sun, earth, moon, stars, axes };
}

/** Matrix4 de Three.js a partir de una 3×3 por filas y una traslación. */
export function setMatrix(m4, M, tx, ty, tz) {
  m4.set(M[0], M[1], M[2], tx, M[3], M[4], M[5], ty, M[6], M[7], M[8], tz, 0, 0, 0, 1);
}

export function rotZ(angle) {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return [c, -s, 0, s, c, 0, 0, 0, 1];
}

export function mul3(A, B) {
  const out = new Array(9);
  for (let i = 0; i < 3; i++)
    for (let j = 0; j < 3; j++)
      out[3 * i + j] = A[3 * i] * B[j] + A[3 * i + 1] * B[3 + j] + A[3 * i + 2] * B[6 + j];
  return out;
}
