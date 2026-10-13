// WishCap tags FBX (tags.fbx from WishCaptury's scripts/track_tags.py) in the flat: the radar on its stand, measuring
// devices, fixtures and moving objects. Such a file is already in the web model frame (x = a, y = height, z = -b) in
// millimetres, and says so with an empty node named "wishcap_tags"; its nodes are nulls with no skeleton.
//
// The radar is the node "radar" (or the parent of a "*_tag0" child): its frame is the radar's own - origin at the
// antenna, +z where it looks, +y up. The stand model (models/radar_stojan.glb, from WishCaptury's
// scripts/radar_stand.py) is placed so its head sits exactly there, its pole stands vertically under the head's socket
// ("patice") and its tripod on the floor, the back leg turned away from where the radar looks. The model's one pole
// slides with the head, so any height works: set low, the pole simply passes through the tripod and the floor.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

export const MARKER = "wishcap_tags";
export const isTagsFbx = g => !!g.getObjectByName(MARKER);

const ARROW = 0x16a34a, ITEM = 0x7c3aed, TAGFACE = new THREE.MeshBasicMaterial({ color: 0xf5f5f5, side: THREE.DoubleSide });

function label(text, color, h = 0.11) {
  const c = document.createElement("canvas"), x = c.getContext("2d"); x.font = "bold 40px -apple-system, sans-serif";
  const w = Math.max(128, Math.ceil(x.measureText(text).width) + 40); c.width = w; c.height = 64;
  x.fillStyle = "#" + color.toString(16).padStart(6, "0"); x.beginPath(); x.roundRect(4, 4, w - 8, 56, 18); x.fill();
  x.fillStyle = "#fff"; x.font = "bold 40px -apple-system, sans-serif"; x.textAlign = "center"; x.textBaseline = "middle"; x.fillText(text, w / 2, 34);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false, transparent: true }));
  s.scale.set(h * w / 64, h, 1); s.renderOrder = 10; return s;
}

function findRadar(g) {
  let r = g.getObjectByName("radar");
  if (!r) g.traverse(o => { if (!r && /_tag0$/.test(o.name) && o.parent && o.parent !== g) r = o.parent; });
  return r ?? null;
}

// world pose of a node without the file's mm -> m scale
function pose(o) {
  o.updateWorldMatrix(true, false);
  const p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3();
  o.matrixWorld.decompose(p, q, s);
  return { p, q, m: new THREE.Matrix4().compose(p, q, new THREE.Vector3(1, 1, 1)) };
}

let standCache = null;
async function loadStand(ver) {
  standCache ??= new GLTFLoader().loadAsync("models/radar_stojan.glb?v=" + ver);
  return (await standCache).scene.clone(true);
}

// put the stand's head on the radar frame `R` (Matrix4, metres), the rest under it on the floor
export function placeStand(stand, R) {
  const stojan = stand.getObjectByName("stojan"), hlava = stand.getObjectByName("hlava");
  const tyc = stand.getObjectByName("tyc"), patice = stand.getObjectByName("patice");
  // the model as built: the pole is drawn in the stand's frame for the head where the file put it
  hlava.updateMatrix(); const head0 = hlava.userData.head0 ??= hlava.matrix.clone();
  const sock0 = patice.position.clone().applyMatrix4(head0);
  const sockW = patice.position.clone().applyMatrix4(R);
  const fwd = new THREE.Vector3().setFromMatrixColumn(R, 2); fwd.y = 0;
  const yaw = fwd.lengthSq() > 1e-9 ? Math.atan2(fwd.x, fwd.z) : 0;
  const S = new THREE.Matrix4().makeRotationY(yaw).setPosition(sockW.x, 0, sockW.z);
  S.decompose(stojan.position, stojan.quaternion, stojan.scale);
  const head = S.clone().invert().multiply(R); head.decompose(hlava.position, hlava.quaternion, hlava.scale);
  const sock = patice.position.clone().applyMatrix4(head);
  const pole = head.clone().invert().multiply(new THREE.Matrix4().makeTranslation(0, sock.y - sock0.y, 0));
  pole.decompose(tyc.position, tyc.quaternion, tyc.scale);
  stand.updateMatrixWorld(true);
  return { height: R.elements[13], socket: sockW };
}

// the layer: everything a tags FBX shows, and its own clock for the moving objects
export async function makeTagsLayer(g, ver) {
  const root = new THREE.Group(); root.scale.setScalar(0.001); root.add(g);   // the file is in mm
  const clip = g.animations.reduce((a, b) => (b.duration > (a?.duration ?? -1) ? b : a), null);
  // played once and held at the end, not looped: a take's clock may run past this file's last key
  const mixer = new THREE.AnimationMixer(g);
  if (clip) { const a = mixer.clipAction(clip); a.setLoop(THREE.LoopOnce); a.clampWhenFinished = true; a.play(); }
  mixer.setTime(0); root.updateMatrixWorld(true);
  const group = new THREE.Group(); group.add(root);
  const radarNode = findRadar(g), info = { radar: null, items: [] };
  let stand = null, arrow = null, radarLabel = null;
  if (radarNode) {
    const { p, m } = pose(radarNode);
    stand = await loadStand(ver); placeStand(stand, m); group.add(stand);
    const dir = new THREE.Vector3().setFromMatrixColumn(m, 2).normalize();
    arrow = new THREE.ArrowHelper(dir, p, 2.0, ARROW, 0.16, 0.08); group.add(arrow);
    radarLabel = label("radar", ARROW); radarLabel.position.copy(p).add(new THREE.Vector3(0, 0.34, 0)); group.add(radarLabel);
    info.radar = { p, dir, tilt: THREE.MathUtils.radToDeg(Math.asin(THREE.MathUtils.clamp(dir.y, -1, 1))) };
  }
  // every other top-level null: axes and its name; an object's tags as small squares where they sit on it
  const marks = [];
  for (const o of g.children) {
    if (o === radarNode || o.name === MARKER || o.isLight || o.isCamera) continue;
    const ax = new THREE.AxesHelper(100); o.add(ax);                    // 0.1 m in the file's mm
    const lb = label(o.name, ITEM, 0.09); group.add(lb); marks.push([o, lb]);
    for (const k of o.children) if (k !== ax && !k.isLight) {
      const sq = new THREE.Mesh(new THREE.PlaneGeometry(80, 80), TAGFACE); sq.position.z = 0.5; k.add(sq);
    }
    info.items.push(o.name);
  }
  const dts = []; const tr = clip?.tracks[0]?.times ?? [];
  for (let i = 1; i < tr.length; i++) dts.push(tr[i] - tr[i - 1]); dts.sort((a, b) => a - b);
  const layer = {
    group, info, dur: clip?.duration ?? 0, fps: dts.length ? Math.round(1 / dts[dts.length >> 1]) : 20, t0: 0,
    setTime(s) {
      mixer.setTime(s); root.updateMatrixWorld(true);
      for (const [o, lb] of marks) { o.getWorldPosition(lb.position); lb.position.y += 0.16; }
    },
    setVisible(v) { group.visible = v; },
    dispose() { mixer.stopAllAction(); group.traverse(o => { o.geometry?.dispose?.(); }); },
  };
  layer.setTime(0);
  return layer;
}

// a line for the side panel
export function describe(layer, name) {
  const r = layer.info.radar, parts = [`<b>Tags: ${name}</b>`];
  if (r) {
    let az = THREE.MathUtils.radToDeg(Math.atan2(r.dir.x, -r.dir.z)); if (Math.abs(az) < 0.5) az = 0;
    parts.push(`radar at a ${r.p.x.toFixed(2)} m, b ${(-r.p.z).toFixed(2)} m, height ${r.p.y.toFixed(2)} m;`
      + ` looks ${az.toFixed(0)}° from +b, ${r.tilt >= 0 ? "up" : "down"} ${Math.abs(r.tilt).toFixed(0)}°`);
  } else parts.push(`<span class="warn">no radar (tag 0) in the file</span>`);
  if (layer.info.items.length) parts.push(`also: ${layer.info.items.join(", ")}`);
  return parts.join("<br>");
}
