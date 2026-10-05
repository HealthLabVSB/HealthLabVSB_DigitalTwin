"""Floor plan in metres (iterace 08): rooms, key furniture, both dining-table positions, the 30 WishCap cameras
(calib/camera-2026-02.calib, mapped with the rig registration) and the Captury C3D subject (compare/unknown.c3d)."""
import json, re, numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle
import rig_xf as X
S = X.S_MODEL
M = np.array(X.M)
def rig_to_model_m(p):                                   # rig (2026-02) metres -> model metres (a, b)
    Q = (np.atleast_2d(p)[:, [0, 2]] @ M.T) / X.RS + [X.RTX, X.RTY]
    return Q * S
txt = open("/Users/dan/WishCaptury/calib/camera-2026-02.calib").read()
C = {int(b.split("\t")[0]): np.array([float(v) for v in re.search(r"origin\t+\s*(\S+)\s+(\S+)\s+(\S+)", b).groups()]) / 1000
     for b in re.split(r"\ncamera\t", txt)[1:]}
room_of = {c: r for r, v in json.load(open("/Users/dan/WishCaptury/configs/apartment.json"))["rooms"].items() for c in v["cameras"]}
rooms = json.load(open("lights.json"))["rooms"]
names = {"obyvak_kuchyn_chodba": "obývák + kuchyň + chodba", "loznice": "ložnice (pokojíček)", "koupelna": "koupelna", "predsin": "předsíň"}
col = {"pokojicek": "#2563eb", "koupelna": "#16a34a", "obyvak": "#ea580c", "chodbicka": "#dc2626"}
fig, ax = plt.subplots(figsize=(15, 15))
for n, poly in rooms.items():
    P = np.array(poly) * S; ax.add_patch(Polygon(P, closed=True, fc="#f5f5f4", ec="#292524", lw=2.5))
    c = P.mean(0); w, h = np.ptp(P[:, 0]), np.ptp(P[:, 1])
    if n == "obyvak_kuchyn_chodba": c = c + [-2.3, 0.3]               # keep the label clear of the pillar and the mat
    ax.text(c[0], c[1] + 0.22, names[n], ha="center", fontsize=12, weight="bold")
    ax.text(c[0], c[1] - 0.12, f"{w:.2f} × {h:.2f} m", ha="center", fontsize=11)
def rect(a0, a1, b0, b1, lab="", fc="#dbeafe", ec="#1e3a8a"):
    ax.add_patch(Rectangle((a0 * S, b0 * S), (a1 - a0) * S, (b1 - b0) * S, fc=fc, ec=ec, lw=1))
    if lab: ax.text((a0 + a1) / 2 * S, (b0 + b1) / 2 * S, lab, ha="center", va="center", fontsize=8)
for yc in (1.965, 4.605): rect(-4.09, -4.09 + 2.04 / S, yc - 0.46 / S, yc + 0.46 / S, "postel 2,04 × 0,92")
rect(-0.775, -0.775 + 0.60 / S, 2.67, 4.38, "skříň\n2,0 × 0,6", fc="#fef3c7", ec="#92400e")
TC1 = (0.42 / 1.2779, -4.40 / 1.2779); TC2 = (-3.0, -3.62)
for (a, b), lab, cc in ((TC1, "stůl – pozice 1", "#16a34a"), (TC2, "stůl – pozice 2", "#9333ea")):
    ax.add_patch(Circle((a * S, b * S), 0.48, fc="none", ec=cc, lw=2.5, ls="-" if "1" in lab else "--"))
    ax.text(a * S, b * S - 0.72, lab, ha="center", fontsize=10, color=cc, weight="bold")
R_ = json.load(open("web/rig.json"))["mat"]                # blue 2 x 2 m mat by the pillar (iterace 08)
ax.add_patch(Rectangle((R_["x"][0], -R_["z"][1]), R_["x"][1] - R_["x"][0], R_["z"][1] - R_["z"][0], fc="#1f5fd6", ec="#0b2f7a", lw=1.5, alpha=0.55))
ax.text((R_["x"][0] + R_["x"][1]) / 2, -(R_["z"][0] + R_["z"][1]) / 2 - 0.55, "matrace 2 × 2 m", ha="center", fontsize=10, color="#0b2f7a", weight="bold")
rect(-0.05, 0.30, 0.00, 0.50, "sloup", fc="#a8a29e", ec="#292524")
try:                                                     # where the Captury takes of Dataset_klekz happened (hips, every 3rd frame)
    K = np.concatenate([np.array(v) for v in json.load(open("klekz_pts.json")).values()])
    ax.plot(K[::25, 0] * S, K[::25, 1] * S, ".", ms=1.5, color="#0f766e", alpha=0.35, label="záznamy Captury Dataset_klekz (klouby)")
except Exception as e: print("no klekz", e)
for (x0, x1, y, lab) in [(-2.23, -1.52, 1.335, "dveře 0,83 × 1,94 m"), (1.92, 2.66, 1.90, "dveře 0,87 × 1,94 m")]:
    ax.plot([x0 * S, x1 * S], [y * S, y * S], color="#b45309", lw=6, solid_capstyle="butt")
    ax.text((x0 + x1) / 2 * S, y * S - 0.28, lab, ha="center", fontsize=9, color="#b45309")
for i, p in C.items():
    q = rig_to_model_m(p)[0]; ax.plot(*q, "o", ms=9, color=col[room_of[i]], mec="k"); ax.text(q[0] + 0.08, q[1] + 0.08, str(i), fontsize=8)
for r, c in col.items(): ax.plot([], [], "o", color=c, mec="k", label=f"kamera WishCaptury – {r}")
try:                                                     # Captury C3D subject (shot_003 frame -> 2026-02 -> model)
    Z = np.load("calib_shot003_to_202602.npz"); F = np.load("c3d_frames.npy").reshape(-1, 3)
    F = F[np.isfinite(F).all(1) & (np.abs(F).sum(1) > 0)]
    q = rig_to_model_m(F @ Z["R"].T + Z["t"]); ax.plot(q[::7, 0], q[::7, 1], ".", ms=2, color="#be185d", alpha=0.5, label="záznam Captury (unknown.c3d)")
except Exception as e: print("no c3d", e)
ax.legend(loc="lower right", fontsize=10)
ax.set_aspect("equal"); ax.set_xlabel("m"); ax.set_ylabel("m"); ax.grid(alpha=0.25)
ax.set_title("Byt v reálných metrech – iterace 08 (1 jednotka splatu = 1,171 m, triangulace z kamer WishCaptury)\n"
             "strop 2,70 m · model je zapečený do rámce mocapu", fontsize=13)
plt.tight_layout(); plt.savefig("rozmery_pudorys.png", dpi=70)
print("ok")
