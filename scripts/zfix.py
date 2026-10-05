"""Z-fighting cure, exec'd at the end of bl_detail.py (so renders AND bakes get it).
Faces of two different objects lying in one plane (same or opposite normal) and overlapping flicker in web viewers and
show black hidden faces. For every such pair the smaller object (never a floor / ceiling / wall face) is shrunk by 1 mm
per side along its own axes - invisible, but no two faces share a plane any more."""
import bpy, collections
import numpy as np
from mathutils import Vector, Matrix

ZF_SKIP = ("kytka", "zaclona", "teren", "strom", "panelak", "podstavec", "zaves", "rucnik", "pled", "pradlo")
TOL = 0.00025                                                                    # same plane within 0.25 mm
PLANAR = ("podlaha", "strop_", "zed_obyvak", "zed_loznice", "zed_koupelna", "zed_predsin")      # never moved


def zf_pairs(objs):
    F = []
    for o in objs:
        mw = o.matrix_world; nm = mw.to_3x3().inverted().transposed(); me = o.data
        V = np.array([mw @ v.co for v in me.vertices])
        for p in me.polygons:
            if p.area < 1e-6: continue
            n = (nm @ p.normal).normalized(); vs = V[list(p.vertices)]; c = vs.mean(0)
            F.append((o.name, np.array(n), float(np.dot(n, c)), vs, c))
    B = collections.defaultdict(list)
    for i, (_, n, d, _, _) in enumerate(F):
        k = (round(abs(n[0]), 2), round(abs(n[1]), 2), round(abs(n[2]), 2), round(abs(d) * 500))
        for dk in (-1, 0, 1): B[(k[0], k[1], k[2], k[3] + dk)].append(i)
    pairs, seen = set(), set()
    for lst in B.values():
        for x in range(len(lst)):
            a = F[lst[x]]
            for y in range(x + 1, len(lst)):
                b = F[lst[y]]
                if a[0] == b[0] or (lst[x], lst[y]) in seen: continue
                seen.add((lst[x], lst[y]))
                if abs(np.dot(a[1], b[1])) < 0.999 or abs(a[2] - np.dot(a[1], b[4])) > TOL: continue
                n = a[1]; u = np.cross(n, [0, 0, 1] if abs(n[2]) < 0.9 else [1, 0, 0]); u /= np.linalg.norm(u); v = np.cross(n, u)
                A2 = np.stack([a[3] @ u, a[3] @ v], 1); B2 = np.stack([b[3] @ u, b[3] @ v], 1)
                lo = np.maximum(A2.min(0), B2.min(0)); hi = np.minimum(A2.max(0), B2.max(0))
                if np.prod(np.maximum(hi - lo, 0)) >= 2e-5: pairs.add(tuple(sorted((a[0], b[0]))))
    return pairs


def world_dims(o):
    M = o.matrix_world.to_3x3(); bb = np.array([list(c) for c in o.bound_box])
    ld = bb.max(0) - bb.min(0); return ld, np.array([M.col[i].length for i in range(3)]) * ld, (bb.max(0) + bb.min(0)) / 2


def shrink(o, mm=0.001):
    if o.data.users > 1: o.data = o.data.copy()
    ld, wd, c = world_dims(o)
    f = [1.0 - 2 * min(mm, 0.2 * w) / w if w > 1e-6 and l > 1e-9 else 1.0 for l, w in zip(ld, wd)]
    o.data.transform(Matrix.Translation(Vector(c)) @ Matrix.Diagonal((*f, 1)) @ Matrix.Translation(-Vector(c)))


def zf_cure():
    objs = [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith(ZF_SKIP)]
    total = set()
    for step, mm in enumerate((0.001, 0.0005, 0.002, 0.00075, 0.0013)):        # cumulative shrinks all differ by >= 0.25 mm
        pairs = zf_pairs(objs)
        vol = {o.name: float(np.prod(np.maximum(world_dims(o)[1], 1e-4))) for o in objs}
        victims = set()
        for a, b in pairs:
            cand = [x for x in (a, b) if not x.startswith(PLANAR)]
            if cand: victims.add(min(cand, key=lambda x: (vol[x], x)))
        print(f"ZFIX pass {step}: {len(pairs)} pairs, shrink {len(victims)} by {mm * 1000:.2f} mm", flush=True)
        if not victims: break
        for nm in victims: shrink(bpy.data.objects[nm], mm)
        total |= victims
    return zf_pairs(objs), total


ZF_PAIRS, ZF_VICTIMS = zf_cure()
