// Shared by model.html and fbx.html: the WishCap cameras, the blue mat and room lookup, all in the web model frame
// (x = a metres, y = height, z = -b metres; the floor is y = 0). Data come from rig.json (made by cams_json.py).
import * as THREE from "three";

export const ROOM_COLOR = { bedroom: 0x2563eb, bathroom: 0x16a34a, living_room: 0xea580c, hallway: 0xdc2626 };
export const ROOM_NAME = { living_kitchen_hall: "living room + kitchen + hall", bedroom: "bedroom", bathroom: "bathroom", entrance_hall: "entrance hall" };

export async function loadRig(ver) { return (await fetch("rig.json?v=" + ver)).json(); }

function label(text, color, h = 0.16) {
  const c = document.createElement("canvas"), x = c.getContext("2d"); c.width = 128; c.height = 64;
  x.fillStyle = "#" + color.toString(16).padStart(6, "0"); x.beginPath(); x.roundRect(4, 4, 120, 56, 18); x.fill();
  x.fillStyle = "#fff"; x.font = "bold 40px -apple-system, sans-serif"; x.textAlign = "center"; x.textBaseline = "middle"; x.fillText(text, 64, 34);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false, transparent: true }));
  s.scale.set(h * 2, h, 1); s.renderOrder = 10; return s;
}

// the 30 rig cameras (calibration 2026-02): body, a 0.35 m view frustum and the index
export function makeCameras(rig) {
  const g = new THREE.Group(); g.name = "cameras";
  for (const c of rig.model_cams) {
    const col = ROOM_COLOR[c.room] ?? 0x444444, p = new THREE.Vector3(...c.p);
    const f = new THREE.Vector3(...c.f), r = new THREE.Vector3(...c.r), d = new THREE.Vector3(...c.d);
    const L = 0.35, th = Math.tan(c.fov[0] * Math.PI / 360) * L, tv = Math.tan(c.fov[1] * Math.PI / 360) * L;
    const k = [[1, 1], [1, -1], [-1, -1], [-1, 1]].map(([i, j]) => p.clone().addScaledVector(f, L).addScaledVector(r, i * th).addScaledVector(d, j * tv));
    const pts = []; for (let i = 0; i < 4; i++) pts.push(p, k[i], k[i], k[(i + 1) % 4]);
    g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: col })));
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.06, 0.1), new THREE.MeshBasicMaterial({ color: col }));
    body.position.copy(p); body.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(r, d.clone().negate(), f.clone().negate())); g.add(body);
    const s = label(String(c.i), col); s.position.copy(p).add(new THREE.Vector3(0, 0.12, 0)); g.add(s);
  }
  return g;
}

// blue gym mat 2 x 2 x 0.10 m on the floor in the free area south of the pillar (where the klekz takes were recorded)
export function makeMat(rig) {
  const m = rig.mat, w = m.x[1] - m.x[0], h = m.y[1] - m.y[0], l = m.z[1] - m.z[0];
  const geo = new THREE.BoxGeometry(w, h, l, 1, 1, 1);
  const box = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ color: 0x1f5fd6 }));
  box.position.set((m.x[0] + m.x[1]) / 2, (m.y[0] + m.y[1]) / 2, (m.z[0] + m.z[1]) / 2);
  box.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: 0x0b2f7a })));
  const g = new THREE.Group(); g.name = "mat"; g.add(box);
  return g;
}

// the model is unlit (baked light); these lights only shade the mat and the mocap figure
export function addLights(scene) {
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8070, 2.2));
  const d = new THREE.DirectionalLight(0xffffff, 1.6); d.position.set(2, 5, 3); scene.add(d);
}

// which room a point (web x, z) is in
export function roomAt(rig, x, z) {
  for (const [n, poly] of Object.entries(rig.rooms_poly)) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, zi] = poly[i], [xj, zj] = poly[j];
      if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) inside = !inside;
    }
    if (inside) return n;
  }
  return null;
}

// a checkbox pill for the .bar
export function toggle(bar, text, on, cb) {
  const l = document.createElement("label"); l.className = "chk";
  const i = document.createElement("input"); i.type = "checkbox"; i.checked = on; i.onchange = () => cb(i.checked);
  l.append(i, " " + text); bar.appendChild(l); cb(on); return i;
}
