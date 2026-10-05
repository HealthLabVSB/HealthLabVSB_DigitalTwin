"""Hybrid splat: the real capture, fixed to the clean model.

- architecture (walls, floors, ceilings, reveals, frames, window panes) comes from the model only: flat gaussians
  sampled on the baked GLB, coloured by the baked lighting, so planes are perfectly flat and hole-free;
- real gaussians survive only inside the rooms, off the architectural planes, close to a model object (furniture,
  kitchen, doors, plants ...), not huge and not transparent -> fog, floaters and the outside are gone;
- the bathroom capture is too broken, so there the model replaces it;
- model objects fill whatever the capture never saw (gaussians only where no real one is near).
usage: hybrid_splat.py SPLAT.ply BAKED.glb OUT.ply [--no-ceiling]"""
import json, sys, os
import numpy as np, trimesh
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from splatio import read_ply, write_ply, xyz_of, components
from walls2 import FY, TH

args = [a for a in sys.argv[1:] if not a.startswith("--")]
SRC, GLB, OUT = args
NO_CEIL = "--no-ceiling" in sys.argv
C0 = 0.28209479177387814
H = 2.31
SPACING = {"zapec_podlahy": 0.015, "zapec_zdi": 0.021, "zapec_stropy": 0.028, "zapec_telo": 0.04, "sklo": 0.03, "*": 0.016}
if "--hires" in sys.argv:                       # iterace 07: ~2x finer sampling (metres between gaussians)
    SPACING = {"zapec_podlahy": 0.010, "zapec_zdi": 0.011, "zapec_stropy": 0.016, "zapec_telo": 0.04, "sklo": 0.02, "*": 0.008}
RIG = "--rig" in sys.argv
nA = np.array([np.cos(TH), 0, np.sin(TH)]); nB = np.array([-np.sin(TH), 0, np.cos(TH)])
rng = np.random.default_rng(3)
rooms = json.load(open("lights.json"))["rooms"]
BATH = (0.79, 2.79, 1.95, 5.35)                # bathroom incl. its entry (iterace 04)


def g2s(G):                                    # glTF (a, h, -b) -> splat xyz
    a, h, b = G[:, 0], G[:, 1], -G[:, 2]
    return a[:, None] * nA + b[:, None] * nB + np.stack([np.zeros_like(a), FY - h, np.zeros_like(a)], 1)


def g2s_dir(N):
    a, h, b = N[:, 0], N[:, 1], -N[:, 2]
    return a[:, None] * nA + b[:, None] * nB + np.stack([np.zeros_like(a), -h, np.zeros_like(a)], 1)


def in_poly(a, b, poly):
    c = np.zeros(len(a), bool); n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        cross = (y0 > b) != (y1 > b)
        xint = x0 + (b - y0) * (x1 - x0) / np.where(y1 != y0, y1 - y0, 1e-12)
        c ^= cross & (a < xint)
    return c


def texture_of(m):
    mat = m.visual.material
    img = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
    fac = np.array(getattr(mat, "baseColorFactor", None) if getattr(mat, "baseColorFactor", None) is not None else [255, 255, 255, 255], float)
    fac = fac / 255.0 if fac.max() > 1.0 else fac
    return (np.asarray(img.convert("RGB"), float) / 255.0 if img is not None else None), fac


def lattice_samples(m, sp):
    """Regular lattice (spacing sp) on every large triangle, Poisson-count random points on small ones."""
    T = m.triangles; A = m.area_faces; P, F = [], []
    for fi in np.where(A > 3 * sp * sp)[0]:
        v0, v1, v2 = T[fi]; e1, e2 = v1 - v0, v2 - v0
        u = e1 / np.linalg.norm(e1); nrm = np.cross(e1, e2); nrm /= np.linalg.norm(nrm); w = np.cross(nrm, u)
        x1, x2, y2 = np.linalg.norm(e1), e2 @ u, e2 @ w
        xs = np.arange(min(0, x2) + sp / 2, max(x1, x2), sp); ys = np.arange(sp / 2, y2, sp)
        if len(xs) == 0 or len(ys) == 0: continue
        X, Y = np.meshgrid(xs, ys); X, Y = X.ravel(), Y.ravel()
        # barycentric inside test in 2D: triangle (0,0), (x1,0), (x2,y2)
        l2 = Y / y2; l1 = (X - l2 * x2) / x1; ok = (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1)
        P.append(v0 + np.outer(X[ok], u) + np.outer(Y[ok], w)); F.append(np.full(ok.sum(), fi))
    small = np.where(A <= 3 * sp * sp)[0]
    cnt = rng.poisson(A[small] / (sp * sp))
    if cnt.sum():
        fs = np.repeat(small, cnt); r1, r2 = rng.random(len(fs)), rng.random(len(fs)); sw = r1 + r2 > 1
        r1[sw], r2[sw] = 1 - r1[sw], 1 - r2[sw]
        P.append(T[fs, 0] + r1[:, None] * (T[fs, 1] - T[fs, 0]) + r2[:, None] * (T[fs, 2] - T[fs, 0])); F.append(fs)
    return (np.concatenate(P), np.concatenate(F)) if P else (np.zeros((0, 3)), np.zeros(0, int))


def sample_mesh(m, density):
    """Area-weighted random points with colour (baked texture), normal and alpha."""
    sp = 1.0 / np.sqrt(density)
    pts, fi = lattice_samples(m, sp)
    n = len(pts)
    nrm = m.face_normals[fi]
    img, fac = texture_of(m)
    if img is not None and getattr(m.visual, "uv", None) is not None:
        bary = trimesh.triangles.points_to_barycentric(m.triangles[fi], pts)
        uv = (m.visual.uv[m.faces[fi]] * bary[:, :, None]).sum(1)
        Hh, Ww = img.shape[:2]
        px = np.clip((uv[:, 0] % 1.0) * (Ww - 1), 0, Ww - 1).astype(int); py = np.clip((1 - uv[:, 1] % 1.0) * (Hh - 1), 0, Hh - 1).astype(int)
        col = img[py, px] * fac[:3]
    else:
        col = np.tile(fac[:3], (n, 1))
    return pts, nrm, col, np.full(n, fac[3] if len(fac) > 3 else 1.0)


# ---------------------------------------------------------------- model samples
scene = trimesh.load(GLB)
arch, furn, every = [], [], []                  # every = all model samples, lit or not (for the distance test)
for node in scene.graph.nodes_geometry:
    T, gname = scene.graph[node]
    m = scene.geometry[gname].copy(); m.apply_transform(T)
    if not isinstance(m, trimesh.Trimesh) or m.area < 1e-6: continue
    nm = str(node)                                  # node = Blender object name (zapec_<group>_<i>, sklo_okno_...)
    if NO_CEIL and nm.startswith("zapec_stropy"): continue
    kind = "arch" if nm.startswith(("zapec_zdi", "zapec_telo", "zapec_podlahy", "zapec_stropy")) or "sklo" in nm else "furn"
    sp = next((v for k, v in SPACING.items() if nm.startswith(k)), SPACING["*"])
    p, n, c, al = sample_mesh(m, 1.0 / sp ** 2)
    every.append(p)
    lit = c.max(1) > 0.035                       # near-black = faces the bake never saw (insides, undersides); they leak at edges
    p, n, c, al = p[lit], n[lit], c[lit], al[lit]
    (arch if kind == "arch" else furn).append((p, n, c, al, np.full(len(p), sp)))
    print(f"{nm:28s} {kind} area {m.area:7.2f} m2 -> {len(p)} samples", flush=True)
cat = lambda L, k: np.concatenate([x[k] for x in L])
A_p, A_n, A_c, A_a, A_s = (cat(arch, k) for k in range(5))
F_p, F_n, F_c, F_a, F_s = (cat(furn, k) for k in range(5))
S_M = 1.1711                                   # the baked GLB is in metres; the splat is in model units
A_xyz, F_xyz = g2s(A_p / S_M), g2s(F_p / S_M)

# ---------------------------------------------------------------- real gaussians: only solid things the model lacks
lines, D = read_ply(SRC)
X = xyz_of(D)
a, b, h = X @ nA, X @ nB, FY - X[:, 1]
inside = np.zeros(len(D), bool)
for poly in rooms.values():
    inside |= in_poly(a, b, poly)
inside &= (h > 0.03) & (h < (H - 0.25 if NO_CEIL else H - 0.06))
in_bath = (a > BATH[0] - 0.05) & (a < BATH[1] + 0.05) & (b > BATH[2] - 0.05) & (b < BATH[3] + 0.05)
scl = np.exp(np.stack([D[f"scale_{k}"] for k in range(3)], 1)).max(1)
opa = 1 / (1 + np.exp(-D["opacity"]))
# zones fully covered by model furniture: real duplicates there only add clutter (dining set: chairs were re-arranged)
in_dining = (a > -0.75) & (a < 1.15) & (b > -4.15) & (b < -2.45) & (h < 1.0)
cand = inside & ~in_bath & ~in_dining & (scl < 0.10) & (opa > 0.35)
tm = cKDTree(g2s(np.concatenate(every) / S_M))
dm, _ = tm.query(X[cand], k=1, distance_upper_bound=0.5)
idx = np.where(cand)[0][dm > 0.15]                              # model surfaces win; keep only what is clearly not in the model (19 cm)
comp, sizes = components(X[idx], 0.05, 5)                       # solid clusters only (fog and specks are sparse)
big = np.array([c >= 0 and sizes.get(c, 0) >= 800 for c in comp])
for c_ in set(comp[big].tolist()):                               # ghosts are faint: whole cluster must be opaque
    sel = comp == c_
    if np.median(opa[idx[sel]]) < 0.6: big[sel] = False
keep = np.zeros(len(D), bool); keep[idx[big]] = True
R_keep = D[keep]
print(f"real gaussians: {len(D)} -> extras kept {keep.sum()} (candidates {cand.sum()}, off-model {len(idx)})")
fill = np.ones(len(F_xyz), bool)
if NO_CEIL:
    fill &= F_p[:, 1] < H * S_M - 0.03
print(f"model: architecture {len(A_xyz)}, objects {fill.sum()}")


def gaussians(xyz, nrm, col, alpha, sig_in):
    n = len(xyz); G = np.zeros(n, dtype=D.dtype)
    G["x"], G["y"], G["z"] = xyz.T
    nn = g2s_dir(nrm); nn /= np.linalg.norm(nn, axis=1, keepdims=True) + 1e-12
    helper = np.where(np.abs(nn[:, 1:2]) < 0.9, [[0, 1, 0]], [[1, 0, 0]])
    t1 = np.cross(helper, nn); t1 /= np.linalg.norm(t1, axis=1, keepdims=True); t2 = np.cross(nn, t1)
    q = Rotation.from_matrix(np.stack([t1, t2, nn], 2)).as_quat()            # x y z w
    G["rot_0"], G["rot_1"], G["rot_2"], G["rot_3"] = q[:, 3], q[:, 0], q[:, 1], q[:, 2]
    G["scale_0"] = G["scale_1"] = np.log(sig_in); G["scale_2"] = np.log(0.0015)
    al = np.clip(alpha * 0.98, 0.02, 0.98); G["opacity"] = np.log(al / (1 - al))
    fdc = (np.clip(col, 0, 1) - 0.5) / C0
    G["f_dc_0"], G["f_dc_1"], G["f_dc_2"] = fdc.T
    return G


GA = gaussians(A_xyz, A_n, A_c, A_a, A_s * 0.68 / S_M)
GF = gaussians(F_xyz[fill], F_n[fill], F_c[fill], F_a[fill], F_s[fill] * 0.8 / S_M)
out = np.concatenate([R_keep, GA, GF])
if RIG:                                              # the WishCap rig frame of the mocap takes (metres, Y up)
    import rig_xf as RX
    def rig_of(xs):                                  # splat-frame units -> rig metres
        a_, b_, h_ = xs @ nA, xs @ nB, FY - xs[:, 1]
        return np.stack(RX.model_m_to_rig(a_ * RX.S_MODEL, b_ * RX.S_MODEL, h_ * RX.S_MODEL), 1)
    xs = np.stack([out["x"], out["y"], out["z"]], 1).astype(np.float64)
    J = np.stack([rig_of(np.eye(3)[k][None])[0] - rig_of(np.zeros((1, 3)))[0] for k in range(3)], 1)   # columns = images of e_k
    R3 = J / RX.RS
    pos = rig_of(xs)
    q = np.stack([out["rot_1"], out["rot_2"], out["rot_3"], out["rot_0"]], 1).astype(np.float64)       # x y z w
    Rg = Rotation.from_quat(q / np.linalg.norm(q, axis=1, keepdims=True)).as_matrix()
    Rn = np.einsum("ij,njk->nik", R3, Rg)
    if np.linalg.det(R3) < 0: Rn[:, :, 2] *= -1                                                       # keep it a rotation
    qn = Rotation.from_matrix(Rn).as_quat()
    out["x"], out["y"], out["z"] = pos.T
    out["rot_0"], out["rot_1"], out["rot_2"], out["rot_3"] = qn[:, 3], qn[:, 0], qn[:, 1], qn[:, 2]
    for k_ in ("scale_0", "scale_1", "scale_2"): out[k_] += np.log(RX.RS)
    print("rig frame: det R3 %.3f, floor y %.3f" % (np.linalg.det(R3), np.percentile(out["y"], 1)))
else:
    for k_ in ("x", "y", "z"): out[k_] *= S_M                              # the hybrid is written 1:1 in metres
    for k_ in ("scale_0", "scale_1", "scale_2"): out[k_] += np.log(S_M)
# view-independent colour only: write degree-0 SH (68 bytes/gaussian instead of 248); every 3DGS viewer reads it
keep_f = ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2", "opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
small = np.zeros(len(out), dtype=[(f, "<f4") for f in keep_f])
for f in keep_f: small[f] = out[f]
hdr = ["ply", "format binary_little_endian 1.0", f"element vertex {len(small)}"] + [f"property float {f}" for f in keep_f] + ["end_header"]
with open(OUT, "wb") as fh:
    fh.write(("\n".join(hdr) + "\n").encode("ascii")); small.tofile(fh)
np.save(OUT.replace(".ply", "_counts.npy"), np.array([len(R_keep), len(GA), len(GF)]))
print(f"WROTE {OUT}: real {len(R_keep)} + architecture {len(GA)} + object fill {len(GF)} = {len(out)}  ({os.path.getsize(OUT) / 1e6:.0f} MB, SH0)")
