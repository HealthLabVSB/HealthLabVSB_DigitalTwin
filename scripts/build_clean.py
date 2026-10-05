"""Clean architectural 3D model of the flat: plain painted walls with drawn windows / doors / tiles,
procedural kitchen, simple furniture placed from the splat, real photo only for the teal feature
wall and the framed pictures.  usage: build_clean.py SPLAT OUT.glb [--no-ceiling]"""
import numpy as np, sys
import cv2, trimesh
from PIL import Image
from splatio import read_ply, xyz_of
from ortho import render
from walls2 import FY, TH

NO_CEIL = "--no-ceiling" in sys.argv
SRC, OUT = [a for a in sys.argv[1:] if not a.startswith("--")]
H = 2.31; PX = 0.008
S = 1.1711                                      # metres per model unit: rig triangulation (camera-2026-02.calib, iterace 07)
SO = 1.2779                                     # the old scale some measurements below were written in
mo = lambda v: v / SO                           # an old-metre splat measurement -> model units
mtr = lambda v: v / S                           # a real size in metres -> model units (the GLB is scaled x S in Blender)
nA = np.array([np.cos(TH), 0, np.sin(TH)]); nB = np.array([-np.sin(TH), 0, np.cos(TH)])
UP = np.array([0, -1.0, 0]); DOWN = np.array([0, 1.0, 0])
_, D = read_ply(SRC)
hgt = FY - xyz_of(D)[:, 1]

WALL = np.array([236, 233, 226]); FRAME = np.array([58, 60, 64]); GLASS = np.array([196, 214, 228])
WHITE_F = np.array([242, 242, 240]); OAK = np.array([176, 132, 86]); DARK = np.array([30, 30, 32])

rooms = {
    "obyvak_kuchyn_chodba": [(-4.09, -4.69), (2.22, -4.69), (2.22, 0.51), (3.64, 0.51), (3.64, 1.85), (1.55, 1.85),
                             (1.55, 1.37), (-1.12, 1.37), (-1.12, 1.26), (-4.09, 1.26)],
    # bedroom: north wall at b 5.31 (splat wall peak + rig cam 3), east wall behind the freestanding wardrobe (Dan)
    "loznice": [(-4.09, 1.41), (-1.45, 1.41), (-1.45, 2.62), (-0.24, 2.62), (-0.24, 5.31), (-4.09, 5.31)],
    # bathroom reaches the hall wall (tiled floor from b 1.95 in the splat); the corner by the WC is an installation box-out
    "koupelna": [(0.79, 2.62), (1.60, 2.62), (1.60, 1.95), (2.79, 1.95), (2.79, 5.35), (0.79, 5.35)],
    "predsin": [(3.64, 0.79), (5.76, 0.79), (5.76, 3.74), (3.64, 3.74)],
}
exterior = {("obyvak_kuchyn_chodba", 0), ("obyvak_kuchyn_chodba", 9), ("loznice", 5), ("loznice", 4)}
openings = {
    ("obyvak_kuchyn_chodba", 8): [((-2.23, -1.52), 2.12 / 1.2779)], ("loznice", 0): [((-2.23, -1.52), 2.12 / 1.2779)],          # 0.91 x 2.12 m (splat)
    ("obyvak_kuchyn_chodba", 4): [((1.92, 2.66), 2.12 / 1.2779)], ("koupelna", 2): [((1.92, 2.66), 2.12 / 1.2779)],            # 0.95 x 2.12 m (splat)
    ("obyvak_kuchyn_chodba", 3): [((0.79, 1.85), H)], ("predsin", 3): [((0.79, 1.85), H)],          # open corridor, no frame (Dan)
}
tunnels = [(-2.23, -1.52, 1.26, 1.41, 2.12 / 1.2779), (1.92, 2.66, 1.85, 1.95, 2.12 / 1.2779)]


def P3(a, b, h): return np.array([a, h, -b], float)


def mat_img(arr):
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return trimesh.visual.material.PBRMaterial(baseColorTexture=img, doubleSided=True, metallicFactor=0.0, roughnessFactor=0.85)


def mat_col(rgb, rough=0.8, metal=0.0, alpha=1.0):
    c = np.asarray(rgb, float) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)          # glTF baseColorFactor is linear, ours are sRGB
    return trimesh.visual.material.PBRMaterial(baseColorFactor=np.r_[c, alpha],
                                               doubleSided=True, metallicFactor=metal, roughnessFactor=rough,
                                               alphaMode="BLEND" if alpha < 1 else None)


scene = trimesh.Scene()
_n = [0]
def add(mesh, name):
    _n[0] += 1; scene.add_geometry(mesh, node_name=f"{name}_{_n[0]}", geom_name=f"{name}_{_n[0]}")


def quad(c, uv, material):
    m = trimesh.Trimesh(np.array(c), np.array([[0, 1, 2], [0, 2, 3]]), process=False)
    m.visual = trimesh.visual.TextureVisuals(uv=np.array(uv), material=material); return m


def box(a0, a1, b0, b1, h0, h1, rgb, name="box", rough=0.8, alpha=1.0, drop=None):
    m = trimesh.creation.box(bounds=[[min(a0, a1), h0, -max(b0, b1)], [max(a0, a1), h1, -min(b0, b1)]])
    if drop is not None:                                         # leave out the face pointing along drop (never visible)
        m.update_faces(m.face_normals @ np.asarray(drop, float) < 0.99); m.remove_unreferenced_vertices()
    m.visual = trimesh.visual.TextureVisuals(uv=np.zeros((len(m.vertices), 2)), material=mat_col(rgb, rough, alpha=alpha))
    add(m, name)


def cyl(a, b, r, h0, h1, rgb, name="cyl", sections=32):
    m = trimesh.creation.cylinder(radius=r, height=h1 - h0, sections=sections)
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    m.apply_translation([a, (h0 + h1) / 2, -b])
    m.visual = trimesh.visual.TextureVisuals(uv=np.zeros((len(m.vertices), 2)), material=mat_col(rgb))
    add(m, name)


def sphere(a, b, h, r, rgb, name="ball"):
    m = trimesh.creation.icosphere(subdivisions=2, radius=r); m.apply_scale([1, 1.25, 1]); m.apply_translation([a, h, -b])
    m.visual = trimesh.visual.TextureVisuals(uv=np.zeros((len(m.vertices), 2)), material=mat_col(rgb, 0.9)); add(m, name)


def ear_clip(poly):
    pts = [tuple(p) for p in poly]; idx = list(range(len(pts))); tris = []
    cr = lambda o, a, b: (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    ins = lambda p, a, b, c: cr(a, b, p) >= 0 and cr(b, c, p) >= 0 and cr(c, a, p) >= 0
    while len(idx) > 3:
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if cr(pts[i0], pts[i1], pts[i2]) <= 1e-9: continue
            if any(ins(pts[j], pts[i0], pts[i1], pts[i2]) for j in idx if j not in (i0, i1, i2)): continue
            tris.append((i0, i1, i2)); idx.pop(k); break
    tris.append(tuple(idx)); return tris


# ---------------------------------------------------------------- splat helpers (detection + photo decals)
def wall_render(p0, p1, n_out, din=0.10, dout=0.35):
    t = np.array(p1, float) - np.array(p0, float); L = np.linalg.norm(t); t /= L
    t3 = nA * t[0] + nB * t[1]; n3 = nA * n_out[0] + nB * n_out[1]
    s0 = np.array(p0) @ t; off = np.array(p0) @ n_out
    img, al = render(D, t3, UP, n3, s0, s0 + L, -FY, -FY + H, off - din, off + dout, px=PX, alpha=True)
    return np.clip(img, 0, 1), al                      # row 0 = top (h = H), column 0 = p0


def photo_decals(p0, p1, n_out, hmin=1.0, hmax=2.05):
    """Saturated framed things (pictures) on a wall -> list of (s0, s1, h0, h1, image)."""
    img, al = wall_render(p0, p1, n_out, din=0.08, dout=0.08)
    hsv = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2HSV)
    m = (hsv[..., 1] > 70) & (al > 0.7)
    r0, r1 = int((H - hmax) / PX), int((H - hmin) / PX); m[:r0] = 0; m[r1:] = 0
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    out = []
    for i in range(1, n):
        x, y, w, h_, area = st[i]
        if w * PX < 0.15 or h_ * PX < 0.15 or area * PX * PX < 0.03: continue
        crop = (img[y:y + h_, x:x + w] * 255 * 1.3)
        out.append((x * PX, (x + w) * PX, H - (y + h_) * PX, H - y * PX, crop))
    return out


# ---------------------------------------------------------------- procedural wall textures
def canvas(L, Hh=H, col=WALL):
    return np.ones((int(Hh / PX), int(L / PX), 3)) * col


def rect(img, s0, s1, h0, h1, col):
    Hp = img.shape[0]; r0, r1 = int((H - h1) / PX), int((H - h0) / PX); c0, c1 = int(s0 / PX), int(s1 / PX)
    img[max(r0, 0):max(r1, 0), max(c0, 0):max(c1, 0)] = col


def draw_window(img, s0, s1, h0=0.80, h1=2.10):
    f = 0.06
    rect(img, s0, s1, h0, h1, FRAME)
    mid = (s0 + s1) / 2
    for a, b in [(s0 + f, mid - f / 2), (mid + f / 2, s1 - f)]:
        rect(img, a, b, h0 + f, h1 - f, GLASS)
        r0, r1 = int((H - (h1 - f)) / PX), int((H - (h0 + f)) / PX); c0, c1 = int(a / PX), int(b / PX)
        g = np.linspace(1.06, 0.92, max(r1 - r0, 1))[:, None, None]        # soft sky gradient
        img[r0:r1, c0:c1] = np.clip(img[r0:r1, c0:c1] * g, 0, 255)
    rect(img, s0 - 0.03, s1 + 0.03, h0 - 0.04, h0, WHITE_F)                 # sill


def tiles(img, h0, h1, col, grout, tw=0.60, th=0.30):
    Hp, Wp = img.shape[:2]
    r0, r1 = int((H - h1) / PX), int((H - h0) / PX)
    yy, xx = np.mgrid[r0:r1, 0:Wp]
    hh = H - yy * PX; ss = xx * PX
    g = ((ss % tw) < 0.004) | (((hh - h0) % th) < 0.004)
    block = np.ones((r1 - r0, Wp, 3)) * col
    block[g] = grout
    img[r0:r1] = block


tex_cache = {}
def wall_texture(room, e, p0, p1, n_out, L):
    key = (room, e)
    img = canvas(L)
    if room == "koupelna":
        tiles(img, 0.0, 0.75, np.array([78, 78, 82]), np.array([60, 60, 62]))
        tiles(img, 0.75, 2.05, np.array([196, 196, 192]), np.array([168, 168, 164]))
    if key == ("obyvak_kuchyn_chodba", 6):                                    # built-in wardrobe, 3 sliding doors
        rect(img, 0.08, L - 0.08, 0.02, 2.15, np.array([244, 244, 242]))
        for k in range(1, 3):
            rect(img, 0.08 + k * (L - 0.16) / 3 - 0.006, 0.08 + k * (L - 0.16) / 3 + 0.006, 0.02, 2.15, np.array([175, 178, 182]))
        rect(img, 0.08, L - 0.08, 2.12, 2.16, np.array([175, 178, 182]))
    if key == ("obyvak_kuchyn_chodba", 1):                                    # kitchen back wall: backsplash
        rect(img, 0.0, 3.69, 0.70, 1.22, np.array([226, 224, 218]))
    if key == ("predsin", 1):                                                 # front door: narrow glass leaf + wooden leaf
        # measured on the splat elevation: frame b 0.80-2.00 (s = b - 0.79), side leaf with the frosted strip at the corner
        rect(img, 0.01, 1.21, 0.0, mo(2.16), FRAME)
        rect(img, 0.31, 1.15, 0.0, mo(2.10), OAK)                                  # main leaf b 1.10-1.94
        rect(img, 0.07, 0.27, 0.0, mo(2.10), OAK * 0.95)                           # side leaf b 0.86-1.06
        rect(img, 0.14, 0.20, mo(0.35), mo(1.95), np.array([215, 222, 226]))           # frosted strip
        rect(img, 0.36, 0.48, mtr(1.01), mtr(1.04), np.array([180, 182, 186]))           # handle
    if key == ("predsin", 2):                                                 # teal feature wall: real photo
        im, al = wall_render(p0, p1, n_out, din=0.20, dout=0.10)
        photo = np.clip(im * 255 * 1.3, 0, 255); keep = al > 0.6
        img[keep] = photo[keep]
    return img


# ---------------------------------------------------------------- floors / ceilings
allpts = np.array([p for r in rooms.values() for p in r])
A0, B0 = allpts.min(0) - 0.3; A1, B1 = allpts.max(0) + 0.3
Wf, Hf = int((A1 - A0) / PX), int((B1 - B0) / PX)
rng = np.random.default_rng(7)
PW, PL = int(mtr(0.192) / PX), int(mtr(1.285) / PX)                # real 19.2 x 128.5 cm planks
lam = np.zeros((Wf, Hf, 3))                                   # planks along a (image transposed below)
grain = cv2.GaussianBlur(rng.normal(0, 1, (Wf, Hf)), (0, 0), sigmaX=1.2, sigmaY=40); grain /= grain.std()
base = np.array([178, 130, 80])                              # honey oak as in the tour
for c0 in range(0, Hf, PW):
    off = int(rng.integers(0, PL))
    for r0 in range(-off, Wf, PL):
        lam[max(r0, 0):min(r0 + PL, Wf), c0:c0 + PW] = base * (1 + rng.normal(0, 0.045)) * (1 + rng.normal(0, 0.008, 3))
        lam[max(r0, 0):max(r0, 0) + 1, c0:c0 + PW] *= 0.72
    lam[:, c0:c0 + 1] *= 0.75
lam *= (1 + 0.07 * grain)[..., None]
floor = lam.transpose(1, 0, 2)[::-1].copy()                  # rows = b (top = b max), cols = a
bath = np.zeros((Hf, Wf), np.uint8)
cv2.fillPoly(bath, [np.array([[(a - A0) / PX, (B1 - b) / PX] for a, b in rooms["koupelna"]], np.int32)], 1)
yy, xx = np.mgrid[0:Hf, 0:Wf]
gr = ((xx * PX) % 0.60 < 0.004) | ((yy * PX) % 0.30 < 0.004)
tile = np.ones((Hf, Wf, 3)) * [200, 200, 196]; tile[gr] = [172, 172, 168]
floor[bath > 0] = tile[bath > 0]
ceil = np.ones((Hf, Wf, 3)) * [238, 238, 235]
ceil[(((xx * PX) % mtr(0.60) < 0.006) | ((yy * PX) % mtr(0.60) < 0.006)) & (bath == 0)] = [222, 222, 219]   # real 60 cm tiles   # bathroom: plain plasterboard
# ceiling light panels: bright spots of the splat ceiling
cimg, cal = render(D, nA, -nB, UP, A0, A1, -B1, -B0, -FY + H - 0.06, -FY + H + 0.06, px=PX, alpha=True)
light = cv2.dilate((((cimg @ [0.299, 0.587, 0.114]) > 0.9) & (cal > 0.5)).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
# real fixtures are modelled in Blender: export the light blobs (centre, size) instead of painting them on the ceiling
import json
nL, labL, stL, cenL = cv2.connectedComponentsWithStats(light[:Hf, :Wf].astype(np.uint8))
# the ceiling render runs b upwards from B0 (row 0 = B0), unlike the textures (row 0 = B1): the old painted spots were mirrored
fixtures = [dict(a=float(A0 + cenL[i][0] * PX), b=float(B0 + cenL[i][1] * PX), w=float(stL[i][2] * PX), h=float(stL[i][3] * PX))
            for i in range(1, nL) if stL[i][4] * PX * PX > 0.01]
json.dump(dict(fixtures=fixtures, A0=float(A0), B1=float(B1), rooms=rooms), open("lights.json", "w"), indent=1)
print("light fixtures:", [(round(f["a"], 2), round(f["b"], 2), round(f["w"], 2), round(f["h"], 2)) for f in fixtures])
fmat, cmat = mat_img(floor), mat_img(ceil)
for name, poly in rooms.items():
    tris = np.array(ear_clip(poly))
    V = np.array([P3(a, b, 0.0) for a, b in poly]); UV = np.array([((a - A0) / (A1 - A0), (b - B0) / (B1 - B0)) for a, b in poly])
    m = trimesh.Trimesh(V, tris, process=False); m.visual = trimesh.visual.TextureVisuals(uv=UV, material=fmat); add(m, f"podlaha_{name}")
    if not NO_CEIL:
        Vc = V.copy(); Vc[:, 1] = H
        m = trimesh.Trimesh(Vc, tris[:, ::-1], process=False); m.visual = trimesh.visual.TextureVisuals(uv=UV, material=cmat)
        add(m, f"strop_{name}")

# ---------------------------------------------------------------- walls
SILL, WTOP = 0.70, 2.25
# outer frame edges (b) measured on the splat elevations of the a = -4.09 facade
WINDOWS_B = {("obyvak_kuchyn_chodba", 9): [(0.65, -0.61), (-2.79, -3.85)], ("loznice", 5): [(4.05, 2.93)]}
win_list = []; win_ops = {}
for key, spans in WINDOWS_B.items():
    poly = rooms[key[0]]; p0 = np.array(poly[key[1]], float); p1 = np.array(poly[(key[1] + 1) % len(poly)], float)
    dd = (p1 - p0) / np.linalg.norm(p1 - p0)
    win_ops[key] = sorted(tuple(sorted((np.array([p0[0], b]) - p0) @ dd for b in sp)) for sp in spans)
    win_list += [(key[0], key[1], s0, s1) for s0, s1 in win_ops[key]]
is_tunnel = lambda lo, hi: any(abs(lo - t[0]) < 1e-6 and abs(hi - t[1]) < 1e-6 for t in tunnels)


def box_sn(p0, d, n_out, s0, s1, n0, n1, h0, h1, rgb, name, alpha=1.0, rough=0.8):
    """Box given in edge coordinates: s along the wall, n outward from the inner face."""
    c = [p0 + d * s + n_out * n for s in (s0, s1) for n in (n0, n1)]
    aa = [q[0] for q in c]; bb = [q[1] for q in c]
    box(min(aa), max(aa), min(bb), max(bb), h0, h1, rgb, name, rough=rough, alpha=alpha)
for name, poly in rooms.items():
    for e in range(len(poly)):
        p0 = np.array(poly[e], float); p1 = np.array(poly[(e + 1) % len(poly)], float)
        d = p1 - p0; L = np.linalg.norm(d); d /= L; n_out = np.array([d[1], -d[0]])
        thick = 0.25 if (name, e) in exterior else 0.08          # < the 10 cm hall|bathroom gap: bodies never reach the other face
        tex = mat_img(wall_texture(name, e, p0, p1, n_out, L))
        ops = []
        for (lo, hi), top in openings.get((name, e), []):
            ax = 0 if abs(d[0]) > 0.5 else 1
            al = (np.array([lo, hi]) - p0[ax]) * d[ax]; ops.append((al.min(), al.max(), top))
        wins = win_ops.get((name, e), [])
        cuts = sorted([0.0, L] + [v for o in ops for v in o[:2]] + [v for w in wins for v in w])
        for k in range(len(cuts) - 1):
            s0, s1 = cuts[k], cuts[k + 1]
            if s1 - s0 < 1e-3: continue
            op = next((o for o in ops if o[0] <= s0 + 1e-6 and o[1] >= s1 - 1e-6), None)
            wn = next((w for w in wins if w[0] <= s0 + 1e-6 and w[1] >= s1 - 1e-6), None)
            spans = [(op[2], H)] if op else ([(0.0, SILL), (WTOP, H)] if wn else [(0.0, H)])
            if op and (name, e) in (("obyvak_kuchyn_chodba", 3), ("predsin", 3)): spans = []   # shared plane: one thin lintel below
            q0, q1 = p0 + d * s0, p0 + d * s1
            for h0, h1 in spans:
                add(quad([P3(*q0, h0), P3(*q0, h1), P3(*q1, h1), P3(*q1, h0)],          # wound so the normal faces the room
                         [(s0 / L, h0 / H), (s0 / L, h1 / H), (s1 / L, h1 / H), (s1 / L, h0 / H)], tex), f"zed_{name}_{e}")
                if h0 == 0.0 and name != "koupelna" and (name, e) != ("obyvak_kuchyn_chodba", 6):   # skirting board
                    excl = [(0.0, 1.23)] if (name, e) == ("predsin", 1) else []          # not across the front door
                    pieces = [(s0, s1)]
                    for x0, x1 in excl:
                        pieces = [q for a_, b_ in pieces for q in ((a_, min(b_, x0)), (max(a_, x1), b_)) if q[1] - q[0] > 1e-3]
                    for a_, b_ in pieces:
                        c0, c1 = p0 + d * a_ - n_out * 0.012, p0 + d * b_ + n_out * 0.001
                        box(min(c0[0], c1[0]), max(c0[0], c1[0]), min(c0[1], c1[1]), max(c0[1], c1[1]), 0.0, 0.065, (150, 112, 74), "lista")
                if op and is_tunnel(*sorted([q0[0], q1[0]])): continue                # the tunnel lintel closes it
                # wall body strictly behind the textured face: from 2 mm outside the face to the full thickness.
                # At room corners it also stops 2 mm short, so it never lies in the plane of the next wall's face
                # (coplanar faces render as black streaks in Cycles and flicker in web viewers).
                e0 = 0.002 if k == 0 else 0.0; e1 = 0.002 if k == len(cuts) - 2 else 0.0
                inner0, outer1 = p0 + d * (s0 + e0) + n_out * 0.002, p0 + d * (s1 - e1) + n_out * thick
                a_lo, a_hi = sorted([inner0[0], outer1[0]]); b_lo, b_hi = sorted([inner0[1], outer1[1]])
                box(a_lo, max(a_hi, a_lo + 1e-3), b_lo, max(b_hi, b_lo + 1e-3), h0, h1, WALL, "zed_telo",
                    drop=(-n_out[0], 0.0, n_out[1]))                            # its inner face hides behind the texture
        for s0, s1 in wins:                                                     # real windows: frame, glass, sill
            f, n0, n1 = 0.06, 0.08, 0.15
            mid = (s0 + s1) / 2
            # frame pieces butt against each other and reach 1 cm into the reveal, so no two faces share a plane
            for a_, b_ in [(s0 - 0.01, s0 + f), (s1 - f, s1 + 0.01), (mid - 0.03, mid + 0.03)]:
                box_sn(p0, d, n_out, a_, b_, n0, n1, SILL + f, WTOP - f, FRAME, "ram_okna", rough=0.5)
            box_sn(p0, d, n_out, s0 - 0.01, s1 + 0.01, n0, n1, WTOP - f, WTOP + 0.01, FRAME, "ram_okna", rough=0.5)
            box_sn(p0, d, n_out, s0 - 0.01, s1 + 0.01, n0, n1, SILL - 0.01, SILL + f, FRAME, "ram_okna", rough=0.5)
            box_sn(p0, d, n_out, s0 + f - 0.01, s1 - f + 0.01, 0.11, 0.12, SILL + f - 0.01, WTOP - f + 0.01, GLASS, "sklo_okno",
                   alpha=0.25, rough=0.05)
            box_sn(p0, d, n_out, s0 - 0.03, s1 + 0.03, -0.05, n0 + 0.005, SILL - 0.03, SILL + 0.01, WHITE_F, "parapet")


def door_frame(axis, lo, hi, top, n0, n1):
    """Dark steel door frame wrapping the jamb depth n0..n1 (the axis across the wall); axis = the one the opening runs along."""
    def bx(s0, s1, h0, h1):
        if axis == "a": box(s0, s1, n0, n1, h0, h1, FRAME, "zarubne")
        else: box(n0, n1, s0, s1, h0, h1, FRAME, "zarubne")
    bx(lo - 0.03, lo + 0.03, 0, top - 0.03); bx(hi - 0.03, hi + 0.03, 0, top - 0.03)    # jambs stop under the head
    bx(lo - 0.03, hi + 0.03, top - 0.03, top + 0.03)


for a0, a1, b0, b1, top in tunnels:
    # reveal walls + lintel, inset 3 mm from both wall faces so they never share a plane with the textured walls
    box(a0 - 0.05, a0, b0 + 0.003, b1 - 0.003, 0, H, WALL, "osteni"); box(a1, a1 + 0.05, b0 + 0.003, b1 - 0.003, 0, H, WALL, "osteni")
    box(a0, a1, b0 + 0.003, b1 - 0.003, top, H, WALL, "nadprazi")
    if b1 - b0 <= 0.30: door_frame("a", a0, a1, top, b0 - 0.01, b1 + 0.01)                     # one frame through a thin wall
    else: door_frame("a", a0, a1, top, b0 - 0.01, b0 + 0.11); door_frame("a", a0, a1, top, b1 - 0.11, b1 + 0.01)
    poly = [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]                                             # threshold floor
    m = trimesh.Trimesh(np.array([P3(a, b, 0.0) for a, b in poly]), np.array([[0, 1, 2], [0, 2, 3]]), process=False)
    m.visual = trimesh.visual.TextureVisuals(uv=np.array([((a - A0) / (A1 - A0), (b - B0) / (B1 - B0)) for a, b in poly]), material=fmat)
    add(m, "podlaha_prah")

def art_print(kind, W=340, Hh=480):
    """Poster-like prints: a mid-century sun-and-hills abstract and a botanical line study on warm paper."""
    yy, xx = np.mgrid[0:Hh, 0:W].astype(float); yy /= Hh; xx /= W; rng_ = np.random.default_rng(kind + 4)
    img = np.ones((Hh, W, 3)) * [242, 236, 224]
    if kind == 0:
        sun = (xx - 0.62) ** 2 + ((yy - 0.42) * Hh / W) ** 2 < 0.045; img[sun] = [214, 140, 80]
        for k, (c, h0, amp) in enumerate([([168, 182, 160], 0.58, 0.06), ([120, 146, 132], 0.68, 0.05), ([72, 98, 96], 0.80, 0.04)]):
            img[yy > h0 + amp * np.sin(xx * (5 + k) + k)] = c
        img[(yy > 0.86)] = [52, 66, 72]
    else:
        stem = np.abs(xx - (0.5 + 0.08 * np.sin(yy * 5))) < 0.006
        img[stem & (yy > 0.15) & (yy < 0.88)] = [70, 88, 70]
        for k in range(9):
            y0 = 0.2 + k * 0.075; side = 1 if k % 2 else -1
            cx = 0.5 + 0.08 * np.sin(y0 * 5) + side * 0.12; cy = y0 + 0.02
            leaf = ((xx - cx) / 0.13) ** 2 + ((yy - cy) / 0.035) ** 2 < 1
            img[leaf] = [96 + 10 * k % 30, 128, 98]
        img[(yy > 0.9) & (np.abs(xx - 0.5) < 0.18) & (yy < 0.905)] = [90, 90, 90]
    if kind == 2:                                                           # bold abstract (bedroom painting)
        img[:] = [236, 228, 214]
        for k in range(14):
            cx, cy, rr = rng_.uniform(0.1, 0.9), rng_.uniform(0.1, 0.9), rng_.uniform(0.06, 0.22)
            col = [[214, 72, 120], [240, 170, 40], [40, 120, 170], [90, 170, 90], [230, 110, 60], [120, 60, 150]][k % 6]
            img[((xx - cx) * W / Hh) ** 2 + (yy - cy) ** 2 < rr * rr] = col
    img *= 1 + rng_.normal(0, 0.015, (Hh, W, 1))                           # paper grain
    m = 18; img[:m] = img[-m:] = img[:, :m] = img[:, -m:] = [248, 246, 240]   # passe-partout
    return np.clip(img, 0, 255)


# two framed prints above the desk (living room north wall, b = 1.26), drawn instead of the blurry splat crops
for a0 in (-3.62, -3.12):
    box(a0, a0 + 0.42, 1.235, 1.26, 1.22, 1.80, (245, 245, 243), "obraz")                   # white frame
    pic = art_print(0 if a0 < -3.4 else 1)
    add(quad([P3(a0 + 0.04, 1.234, 1.27), P3(a0 + 0.38, 1.234, 1.27), P3(a0 + 0.38, 1.234, 1.75), P3(a0 + 0.04, 1.234, 1.75)],
             [(0, 0), (1, 0), (1, 1), (0, 1)], mat_img(pic)), "obraz")
# painting above the bed at the bedroom north wall (current splat, colours approximate)
box(-3.47, -2.63, 5.285, 5.31, 1.22, 1.78, (40, 40, 42), "obraz")
add(quad([P3(-3.44, 5.284, 1.25), P3(-2.66, 5.284, 1.25), P3(-2.66, 5.284, 1.75), P3(-3.44, 5.284, 1.75)],
         [(0, 0), (1, 0), (1, 1), (0, 1)], mat_img(art_print(2, W=560, Hh=360))), "obraz")
print("windows:", [(r, e, round(s0, 2), round(s1, 2)) for r, e, s0, s1 in win_list])

# ---------------------------------------------------------------- kitchen (procedural)
def cabinet_run(a_front, a_back, b0, b1, h0, h1, mod=0.60, drawers=False, oven=None, name="kuchyn"):
    box(a_front, a_back, b0, b1, h0, h1, WHITE_F, name)
    n = max(1, round((b1 - b0) / mod)); w = (b1 - b0) / n
    for k in range(1, n):                                                       # door seams
        bb = b0 + k * w; box(a_front - 0.004, a_front, bb - 0.003, bb + 0.003, h0 + 0.02, h1 - 0.02, (170, 172, 176), name)
    for k in range(n):                                                          # handles
        bc = b0 + (k + 0.5) * w; hh = h1 - 0.08 if h0 < 0.5 else h0 + 0.06
        box(a_front - 0.02, a_front, bc - 0.08, bc + 0.08, hh - 0.01, hh + 0.01, (150, 152, 156), name)
    if drawers: box(a_front - 0.004, a_front, b0, b1, h1 - 0.20, h1 - 0.194, (170, 172, 176), name)
    if oven: box(a_front - 0.006, a_front, oven[0], oven[1], 0.12, 0.60, DARK, "trouba")
cabinet_run(1.68, 2.22, -4.69, -1.00, 0.0, 0.66, drawers=True, oven=(-2.30, -1.72))
box(1.66, 2.22, -4.69, -1.00, 0.66, 0.70, OAK, "kuchyn_deska")
box(1.76, 1.95, -3.2, -2.75, 0.70, 0.71, (190, 192, 196), "drez")                 # sink
cabinet_run(1.86, 2.22, -4.69, -1.00, 1.22, 2.20)
cabinet_run(1.68, 2.22, -1.00, 0.45, 0.0, 2.20, mod=0.725)
box(1.70, 2.12, -4.05, -3.60, 0.70, 0.72, (40, 40, 42), "varna_deska")          # hob
box(-0.05, 0.30, 0.00, 0.50, 0.0, H + 0.002, WALL, "sloup")                    # top just above the ceiling: lit when it is cut away

# ---------------------------------------------------------------- furniture (positions measured in the splat)
SOFA, CUSH, BLUE, PLANT, POT = (236, 236, 232), (220, 170, 60), (96, 120, 156), (70, 118, 62), (210, 210, 206)
# L sofa facing the TV (backrest along the east and north edges)
box(-2.95, -1.55, -1.50, -0.66, 0.0, 0.42, SOFA, "sedacka"); box(-2.52, -1.55, -2.74, -1.50, 0.0, 0.42, SOFA, "sedacka")
box(-1.78, -1.55, -2.74, -0.66, 0.42, 0.80, SOFA, "sedacka"); box(-2.95, -1.78, -0.88, -0.66, 0.42, 0.80, SOFA, "sedacka")
box(-1.95, -1.80, -2.25, -1.80, 0.42, 0.70, CUSH, "polstar"); box(-1.95, -1.80, -1.65, -1.20, 0.42, 0.70, CUSH, "polstar")
box(-2.90, -2.05, -1.45, -0.90, 0.42, 0.46, (45, 45, 48), "deka")
cyl(mo(-3.85), mo(-2.45), mo(0.40), 0.435 - mtr(0.03), 0.435, WHITE_F, "konf_stolek"); cyl(mo(-3.85), mo(-2.45), mtr(0.06), 0.0, 0.435 - mtr(0.025), WHITE_F, "konf_stolek")   # top 0.435 u (splat)
cyl(mo(0.42), mo(-4.40), mo(0.525), 0.595 - mtr(0.03), 0.595, WHITE_F, "jidelni_stul"); cyl(mo(0.42), mo(-4.40), mtr(0.06), 0.0, 0.595 - mtr(0.025), WHITE_F, "jidelni_stul")   # top 0.595 u (splat)
for ang in np.radians([0, 90, 180, 270]):
    ca, cb = 0.20 + 0.72 * np.cos(ang), -3.40 + 0.72 * np.sin(ang)
    box(ca - 0.21, ca + 0.21, cb - 0.21, cb + 0.21, 0.44, 0.47, WHITE_F, "zidle")
    for da, db in [(-0.18, -0.18), (-0.18, 0.18), (0.18, -0.18), (0.18, 0.18)]:
        box(ca + da - 0.015, ca + da + 0.015, cb + db - 0.015, cb + db + 0.015, 0.0, 0.44, WHITE_F, "zidle")
    ba, bb = ca + 0.20 * np.cos(ang), cb + 0.20 * np.sin(ang)
    box(ba - 0.03 - 0.17 * abs(np.sin(ang)), ba + 0.03 + 0.17 * abs(np.sin(ang)),
        bb - 0.03 - 0.17 * abs(np.cos(ang)), bb + 0.03 + 0.17 * abs(np.cos(ang)), 0.47, 0.90, WHITE_F, "zidle")
# TV bench and a 40" TV (0.88 x 0.48 m panel, measured on the splat) on a pedestal foot
box(-4.05, -3.65, -2.14, -1.16, 0.0, 0.33, WHITE_F, "tv_stolek")
box(-3.99, -3.95, -2.14, -1.26, 0.46, 0.96, DARK, "televize")
box(-3.97, -3.80, -1.82, -1.58, 0.33, 0.345, DARK, "televize_noha"); box(-3.975, -3.955, -1.74, -1.66, 0.345, 0.47, DARK, "televize_noha")
for b0 in (-1.15, -2.55):                                                       # glass shelving either side of the TV
    for hh in (0.0, 0.42, 0.84, 1.26, 1.68):
        box(-4.05, -3.70, b0, b0 + 0.40, hh, hh + 0.02, (205, 214, 220), "regal", alpha=0.7)
    for da, db in [(-4.04, b0), (-4.04, b0 + 0.39), (-3.71, b0), (-3.71, b0 + 0.39)]:
        box(da, da + 0.01, db, db + 0.01, 0.0, 1.70, (150, 152, 156), "regal")
DT_L, DT_W = 0.625, 0.585                       # desk tops measured on the splat (units): living desk, work desk
box(-4.00, -2.50, 0.80, 1.25, DT_L - mtr(0.03), DT_L, WHITE_F, "psaci_stul")
for da in (-3.97, -2.55): box(da, da + 0.03, 0.83, 1.22, 0.0, DT_L - mtr(0.03), WHITE_F, "psaci_stul")
box(-3.55, -3.05, 1.18, 1.22, DT_L + mtr(0.11), DT_L + mtr(0.43), DARK, "monitor")
box(-3.45, -3.05, 0.35, 0.75, 0.0, 0.48, (40, 52, 90), "kancelarska_zidle"); box(-3.45, -3.05, 0.33, 0.37, 0.48, 0.95, (40, 52, 90), "kancelarska_zidle")
box(-4.05, -1.65, -4.69, -4.35, 0.0, 0.90, WHITE_F, "regal_prihradky")
for bb in np.arange(-3.75, -1.65, 0.40): box(bb, bb + 0.02, -4.69, -4.35, 0.0, 0.90, (220, 220, 218), "regal_prihradky")
box(-4.05, -1.65, -4.69, -4.35, 0.44, 0.46, (220, 220, 218), "regal_prihradky")
box(mo(-0.75), mo(1.45), -4.69, mo(-5.39), DT_W - mtr(0.03), DT_W, WHITE_F, "pracovni_stul")
for da in (mo(-0.72), mo(1.40)): box(da, da + mtr(0.03), -4.66, mo(-5.42), 0.0, DT_W - mtr(0.03), WHITE_F, "pracovni_stul")
for ca in (-0.05, 0.75): box(ca, ca + mtr(0.55), -4.66, -4.62, DT_W + mtr(0.13), DT_W + mtr(0.46), DARK, "monitor")
cyl(-3.70, -2.72, mtr(0.16), 0.0, mtr(0.32), POT, "kvetinac"); sphere(-3.70, -2.72, mtr(1.0), mtr(0.35), PLANT, "kytka")   # ficus by the TV wall
cyl(-3.85, -0.05, mtr(0.10), 0.0, mtr(0.22), POT, "kvetinac"); sphere(-3.85, -0.05, mtr(0.50), mtr(0.21), PLANT, "kytka")   # small plant at the window (splat)
# bedroom
for b0 in (1.50, 4.10):
    box(-4.05, -2.05, b0, b0 + 0.90, 0.0, 0.30, WHITE_F, "postel"); box(-4.00, -2.10, b0 + 0.03, b0 + 0.87, 0.30, 0.48, (238, 238, 236), "matrace")
    box(-3.55, -2.08, b0 + 0.02, b0 + 0.88, 0.48, 0.52, BLUE, "prikryvka"); box(-3.98, -3.62, b0 + 0.12, b0 + 0.78, 0.48, 0.60, (250, 250, 248), "polstar")
    box(-4.07, -3.99, b0, b0 + 0.90, 0.30, 0.85, WHITE_F, "celo_postele")
for b0 in (2.52, 3.70): box(-3.96, -3.60, b0, b0 + 0.38, 0.0, 0.50, WHITE_F, "nocni_stolek")   # current splat: desk between them
# built-in wardrobe at the back of the niche (splat: doors in the plane a -0.75, b 2.74-4.34, 2.60 m high), three doors;
# the 0.9 m deep niche in front of it is free floor (Dan: from the corner by the door, three doors)
SAT_A0, SAT_B0, SAT_B1, SAT_H = -0.775, 2.67, 4.38, 2.03
box(SAT_A0, SAT_A0 + mtr(0.60), SAT_B0, SAT_B1, 0.0, SAT_H, WHITE_F, "satnik")                 # freestanding, against the east wall
for bs in (SAT_B0 + (SAT_B1 - SAT_B0) / 3, SAT_B0 + 2 * (SAT_B1 - SAT_B0) / 3): box(SAT_A0 - 0.006, SAT_A0 + 0.002, bs - 0.004, bs + 0.004, 0.02, SAT_H - 0.02, (175, 178, 182), "satnik")
# bathroom
box(0.79, 0.95, 2.80, 3.25, 0.0, 1.05, (236, 236, 232), "wc_instalace"); box(0.95, 1.38, 2.85, 3.20, 0.25, 0.45, (250, 250, 250), "wc")
box(0.80, 0.81, 2.94, 3.11, 0.88, 1.02, (250, 250, 250), "splachovani")
box(1.80, 2.40, 4.85, 5.35, 0.78, 0.86, (250, 250, 250), "umyvadlo"); box(1.85, 2.35, 5.33, 5.34, 1.10, 1.85, (200, 214, 222), "zrcadlo")
cyl(1.00, 3.82, 0.17, 0.0, 0.60, (245, 245, 245), "kos_na_pradlo")
box(1.94, 1.96, 4.15, 5.35, 0.0, mtr(2.00), (205, 220, 228), "sprchova_stena", alpha=0.35)               # wider shower; real 2.0 m pane
# vestibule
# shoe cabinet with two plants and the hat/coat rack above it, on the wall opposite the front door (Dan)
box(3.645, 4.00, 2.40, 3.15, 0.0, 1.00, WHITE_F, "botnik")                       # b from the splat (handles at 0.95 / 1.25)
for b in (2.60, 2.95): cyl(3.82, b, mtr(0.07), 1.00, 1.00 + mtr(0.14), POT, "kvetinac"); sphere(3.82, b, 1.00 + mtr(0.30), mtr(0.13), PLANT, "kytka")
box(5.52, 5.755, 2.15, 3.45, 1.72, 1.74, WHITE_F, "vesak")                           # coat rack on the door wall (splat)
for b in np.arange(2.25, 3.40, 0.16): box(5.70, 5.755, b - 0.006, b + 0.006, 1.60, 1.72, (200, 202, 205), "vesak_hacek")

scene.export(OUT)
print("WROTE", OUT, "| nodes:", len(scene.graph.nodes_geometry))
