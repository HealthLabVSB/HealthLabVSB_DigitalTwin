"""Wall extraction + see-through hole maps for the levelled model.
Walls: Manhattan lines through plan cells that are filled over >= 0.6 m of height.
Coverage: alpha-composited 2D gaussians projected along the wall normal (what a viewer renders)."""
import numpy as np, pickle
from scipy import ndimage
from splatio import read_ply, xyz_of

SP = "/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/"
FY, TH = 1.326, np.radians(10.75)          # real floor (file +Y points DOWN, COLMAP convention)
CEIL_H = 2.309                              # ceiling height above the floor
CELL = 0.05


def quat_to_mat(q):
    q = q / np.linalg.norm(q, axis=1, keepdims=True)
    w, x, y, z = q.T
    return np.stack([np.stack([1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], -1),
                     np.stack([2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], -1),
                     np.stack([2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)], -1)], 1)


def gauss_params(d):
    x = xyz_of(d)
    R = quat_to_mat(np.stack([d[f"rot_{i}"] for i in range(4)], 1).astype(np.float64))
    S = np.exp(np.stack([d[f"scale_{i}"] for i in range(3)], 1).astype(np.float64))
    cov = np.einsum("nij,nj,nkj->nik", R, S ** 2, R)
    a = 1 / (1 + np.exp(-d["opacity"].astype(np.float64)))
    return x, cov, a


def coverage(x, cov, a, n3, t3, s0, s1, off, hmax, slab=0.15):
    """Rendered alpha on an (s, h) grid looking along -n3 at the wall slab."""
    up = np.array([0, -1.0, 0])             # height grows towards -Y
    dn = x @ n3 - off; s = x @ t3; h = FY - x[:, 1]
    m = (np.abs(dn) < slab) & (s > s0 - .4) & (s < s1 + .4) & (h > -.2) & (h < hmax + .3)
    J = np.stack([t3, up])                                   # 2x3
    C2 = np.einsum("ij,njk,lk->nil", J, cov[m], J) + np.eye(2) * 1e-6
    P = np.stack([s[m], h[m]], 1); A = a[m]
    ns, nh = int(np.ceil((s1 - s0) / CELL)), int(np.ceil(hmax / CELL))
    logT = np.zeros((nh, ns))
    inv = np.linalg.inv(C2)
    r = 3 * np.sqrt(np.stack([C2[:, 0, 0], C2[:, 1, 1]], 1))
    i0 = np.floor((P - r - [s0, 0]) / CELL).astype(int); i1 = np.floor((P + r - [s0, 0]) / CELL).astype(int)
    i0 = np.maximum(i0, 0); i1 = np.minimum(i1, [ns - 1, nh - 1])
    ok = (i1 >= i0).all(1)
    for g in np.where(ok)[0]:
        cs = s0 + (np.arange(i0[g, 0], i1[g, 0] + 1) + .5) * CELL
        ch = (np.arange(i0[g, 1], i1[g, 1] + 1) + .5) * CELL
        ds, dh = np.meshgrid(cs - P[g, 0], ch - P[g, 1])
        q = inv[g, 0, 0] * ds * ds + 2 * inv[g, 0, 1] * ds * dh + inv[g, 1, 1] * dh * dh
        al = np.minimum(A[g] * np.exp(-.5 * q), 0.99)
        logT[i0[g, 1]:i1[g, 1] + 1, i0[g, 0]:i1[g, 0] + 1] += np.log1p(-al)
    return 1 - np.exp(logT)


if __name__ == "__main__":
    _, D = read_ply("/Users/dan/Downloads/splat/byt_cely_clean2_hloc.ply")
    x, cov, a = gauss_params(D)
    h = FY - x[:, 1]
    # plan evidence: cells filled over >= 6 of the 10-cm height bins between 0.1 and 2.1 m
    sel = (a > 0.3) & (h > 0.1) & (h < 2.1)
    p = x[sel][:, [0, 2]]; hb = ((h[sel] - 0.1) / 0.1).astype(int)
    po = p.min(0) - .5
    ij = np.floor((p - po) / CELL).astype(int)
    key = ij[:, 0] * 100000 + ij[:, 1]
    u = np.unique(np.stack([key, hb], 1), axis=0)
    ck, span = np.unique(u[:, 0], return_counts=True)
    E = np.stack([ck // 100000, ck % 100000], 1)[span >= 6]
    Ec = (E + .5) * CELL + po
    print(f"wall-evidence cells: {len(E)}")
    walls = []
    for k in range(2):
        th = TH + k * np.pi / 2
        n = np.array([np.cos(th), np.sin(th)]); t = np.array([-n[1], n[0]])
        d = Ec @ n
        hh, e = np.histogram(d, bins=np.arange(d.min() - .1, d.max() + .1, 0.025))
        sm = ndimage.uniform_filter1d(hh.astype(float), 3)
        taken = np.zeros(len(sm), bool)
        for i in np.argsort(-sm):
            if sm[i] * 3 < 24 or taken[max(0, i - 5):i + 6].any(): continue
            taken[i] = True
            off = (e[i] + e[i + 1]) / 2
            band = np.abs(d - off) < 0.075
            s = np.sort(Ec[band] @ t)
            runs = np.split(s, np.where(np.diff(s) > 1.5)[0] + 1)
            for r in runs:
                if r[-1] - r[0] < 1.0 or len(r) < 20: continue
                walls.append(dict(k=k, n=n, t=t, off=off, s0=r[0] - .05, s1=r[-1] + .05))
    print(f"wall segments: {len(walls)}")
    out = []
    for w in walls:
        n3 = np.array([w["n"][0], 0, w["n"][1]]); t3 = np.array([w["t"][0], 0, w["t"][1]])
        ss = np.arange(w["s0"], w["s1"], CELL) + CELL / 2
        pts = w["off"] * w["n"][None] + ss[:, None] * w["t"][None]
        top = np.full(len(ss), CEIL_H - 0.04)                     # wall runs floor -> ceiling
        hmax = float(top.max())
        cv = coverage(x, cov, a, n3, t3, w["s0"], w["s1"], w["off"], hmax)
        cv = cv[:, :len(ss)]
        hgrid = (np.arange(cv.shape[0]) + .5) * CELL
        valid = hgrid[:, None] < top[None, :len(ss)]
        hole = (cv < 0.5) & valid
        lab, nl = ndimage.label(hole)
        holes = []
        for j in range(1, nl + 1):
            m = lab == j
            hi, si = np.where(m)
            bot, tp = hi.min() * CELL, (hi.max() + 1) * CELL
            wid = (si.max() - si.min() + 1) * CELL
            rect = m.sum() / ((hi.max() - hi.min() + 1) * (si.max() - si.min() + 1))
            if bot <= 0.10 and tp >= 1.75: kind = "opening"          # door / passage: keep
            elif bot >= 0.4 and rect >= 0.7 and wid >= 0.4 and (tp - bot) >= 0.4: kind = "window?"
            else: kind = "fill"
            holes.append(dict(mask=m, kind=kind, area=m.sum() * CELL ** 2, bot=bot, top=tp, wid=wid))
        w.update(cov=cv, valid=valid, holes=holes, n3=n3, t3=t3, top=top)
        out.append(w)
        fa = sum(hh["area"] for hh in holes if hh["kind"] == "fill")
        oa = sum(hh["area"] for hh in holes if hh["kind"] != "fill")
        print(f"  wall {len(out)-1:2d} dir {'AB'[w['k']]} off {w['off']:+6.2f} len {w['s1']-w['s0']:4.1f} m: "
              f"covered {((cv>=.5)&valid).sum()/valid.sum()*100:3.0f}%  to fill {fa:5.2f} m2  "
              f"openings/windows {oa:4.2f} m2 ({sum(hh['kind']!='fill' for hh in holes)})")
    pickle.dump(out, open(SP + "walls2.pkl", "wb"))
    tot = sum(hh["area"] for w in out for hh in w["holes"] if hh["kind"] == "fill")
    print(f"TOTAL to fill: {tot:.2f} m2 across {sum(hh['kind']=='fill' for w in out for hh in w['holes'])} holes")
