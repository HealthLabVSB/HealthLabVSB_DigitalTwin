import json, re, numpy as np
from scipy.optimize import minimize
txt = open("/Users/dan/WishCaptury/calib/camera-2026-02.calib").read()
C = {}
for b in re.split(r"\ncamera\t", txt)[1:]:
    i = int(b.split("\t")[0]); o = [float(v) for v in re.search(r"origin\t+\s*(\S+)\s+(\S+)\s+(\S+)", b).groups()]
    C[i] = np.array(o) / 1000
rig_rooms = json.load(open("/Users/dan/WishCaptury/configs/apartment.json"))["rooms"]
room_of = {c: r for r, v in rig_rooms.items() for c in v["cameras"]}
M = json.load(open("lights.json"))["rooms"]
poly = {"pokojicek": [M["loznice"]], "koupelna": [M["koupelna"]],
        "obyvak": [M["obyvak_kuchyn_chodba"]], "chodbicka": [M["obyvak_kuchyn_chodba"], M["predsin"]]}
def seg_dist(p, a, b):
    ab = b - a; t = np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0, 1); return np.linalg.norm(p - (a + t * ab))
def inside(p, P):
    c = False; n = len(P)
    for i in range(n):
        (x0, y0), (x1, y1) = P[i], P[(i + 1) % n]
        if (y0 > p[1]) != (y1 > p[1]) and p[0] < x0 + (p[1] - y0) * (x1 - x0) / (y1 - y0): c = not c
    return c
def wall_dist(p, P):
    P = np.array(P, float); return min(seg_dist(p, P[i], P[(i + 1) % len(P)]) for i in range(len(P)))
ids = sorted(C); X = np.array([[C[i][0], C[i][2]] for i in ids])
def xf(params):
    s, th, tx, ty = params
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]]); Mi = np.array([[0, -1], [-1, 0]])   # mirror (a,b) ~ (-z,-x)
    return (X @ (R @ Mi).T) / s + [tx, ty]
def cost(params, report=False):
    Q = xf(params); tot = 0; rows = []
    for k, i in enumerate(ids):
        r = room_of[i]; Ps = poly[r]
        ins = any(inside(Q[k], P) for P in Ps)
        wd = min(wall_dist(Q[k], P) for P in Ps)
        out = 0.0 if ins else wd
        near = wd * params[0] if r in ("pokojicek", "koupelna") else 0.0      # metres from the nearest wall
        tot += 400 * out ** 2 + max(0.0, near - 0.45) ** 2
        rows.append((i, r, ins, round(wd * params[0], 2)))
    if report: return tot, rows
    return tot
best = None
for s0 in np.linspace(1.0, 1.4, 9):
    for th0 in np.radians(np.arange(-12, 13, 4)):
        # translation guess: centre bedroom cams on the bedroom centroid
        R = np.array([[np.cos(th0), -np.sin(th0)], [np.sin(th0), np.cos(th0)]]); Mi = np.array([[0, -1], [-1, 0]])
        Qb = (X[[ids.index(i) for i in rig_rooms["pokojicek"]["cameras"]]] @ (R @ Mi).T) / s0
        t0 = np.mean(M["loznice"], 0) - Qb.mean(0)
        r = minimize(cost, [s0, th0, *t0], method="Nelder-Mead", options=dict(maxiter=4000, xatol=1e-5, fatol=1e-7))
        if best is None or r.fun < best.fun: best = r
s, th, tx, ty = best.x
tot, rows = cost(best.x, True)
print(f"BEST cost {tot:.4f}  scale {s:.4f} m/unit  rot {np.degrees(th):.2f} deg  t ({tx:.3f},{ty:.3f})")
for row in rows: print(row)
json.dump(dict(s=s, th=th, tx=tx, ty=ty), open("rig_fit.json", "w"))
# feasible scale interval: rescan s with the rest re-optimised
for sv in (1.10, 1.15, 1.20, 1.25, 1.30, 1.35):
    r = minimize(lambda p: cost([sv, *p]), best.x[1:], method="Nelder-Mead", options=dict(maxiter=3000))
    print("s", sv, "cost", round(r.fun, 4))
