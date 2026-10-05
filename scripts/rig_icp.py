import json, numpy as np
from scipy.spatial import cKDTree
from scipy.optimize import minimize
from splatio import read_ply, xyz_of
from walls2 import FY, TH
nA = np.array([np.cos(TH), 0, np.sin(TH)]); nB = np.array([-np.sin(TH), 0, np.cos(TH)])
_, D = read_ply("/Users/dan/Downloads/splat/byt_cely_clean2_hloc_dan4.ply")
X = xyz_of(D); opa = 1 / (1 + np.exp(-D["opacity"])); sc = np.exp(np.stack([D[f"scale_{k}"] for k in range(3)], 1)).max(1)
m = (opa > 0.5) & (sc < 0.05)
SPL = np.stack([X[m] @ nA, X[m] @ nB, FY - X[m][:, 1]], 1)         # (a, b, h) all in units
tree = cKDTree(SPL)
P = np.load("rig_points.npy")
print("rig points", len(P), "height hist", np.histogram(P[:, 1], bins=[-0.1, 0.05, 0.15, 0.3, 0.6, 1.0, 1.5, 2.2, 3.2])[0])
def inv(p, Pr):
    s, th, tx, ty, dy = p
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]]); M = R @ np.array([[0, -1], [-1, 0]])
    Q = (Pr[:, [0, 2]] @ M.T) / s + [tx, ty]
    return np.c_[Q, (Pr[:, 1] - dy) / s]
def cost(p, trunc=0.12):
    d, _ = tree.query(inv(p, P)); d = d * p[0]
    return np.mean(np.minimum(d, trunc) ** 2)
F0 = json.load(open("rig_fit.json")); F1 = json.load(open("rig_reg.json"))
cands = {"camera_fit": [F0["s"], F0["th"], F0["tx"], F0["ty"], 0.0], "edge_fit": [F1["s"], F1["th"], F1["tx"], F1["ty"], F1["dy"]]}
for k, p in cands.items():
    d, _ = tree.query(inv(p, P)); d *= p[0]
    print(f"{k:11s} cost {cost(p):.5f}  median dist {np.median(d) * 100:.1f} cm  <5cm {np.mean(d < 0.05) * 100:.0f}%")
best = None
for name, p0 in cands.items():
    for k in range(8):
        x0 = np.array(p0) + (np.random.default_rng(k).normal(0, 1, 5) * [0.01, 0.01, 0.05, 0.05, 0.03] if k else 0)
        for tr in (0.4, 0.2, 0.1, 0.06):
            x0 = minimize(cost, x0, args=(tr,), method="Nelder-Mead", options=dict(maxiter=3000, xatol=1e-6, fatol=1e-8)).x
        c = cost(x0, 0.06)
        if best is None or c < best[0]: best = (c, x0, name)
c, p, nm = best
d, _ = tree.query(inv(p, P)); d *= p[0]
print(f"BEST from {nm}: s {p[0]:.4f} th {np.degrees(p[1]):.3f} deg t ({p[2]:.4f},{p[3]:.4f}) dy {p[4]:.4f} | median {np.median(d)*100:.1f} cm, <3cm {np.mean(d<0.03)*100:.0f}%, <5cm {np.mean(d<0.05)*100:.0f}%")
json.dump(dict(s=p[0], th=p[1], tx=p[2], ty=p[3], dy=p[4], median_cm=float(np.median(d) * 100)), open("rig_icp.json", "w"))
# stability: refit on random halves
for k in range(3):
    idx = np.random.default_rng(100 + k).random(len(P)) < 0.5; P_ = P; P = P_[idx]
    x = p.copy()
    for tr in (0.1, 0.06): x = minimize(cost, x, args=(tr,), method="Nelder-Mead", options=dict(maxiter=3000, xatol=1e-6, fatol=1e-8)).x
    P = P_
    print(f"half {k}: s {x[0]:.4f} th {np.degrees(x[1]):.3f} t ({x[2]:.4f},{x[3]:.4f}) dy {x[4]:.4f}")
