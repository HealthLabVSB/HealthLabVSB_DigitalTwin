"""Floor plan in metres: rooms, key furniture, both dining-table positions, the 30 WishCap cameras (as shown in the
viewer: snapped in front of the model walls, see TODO.md), the mat, and the Captury recordings.
Usage: python plan_m.py RIG.json OUT.png [en|cs]   (run where lights.json, c3d_frames.npy, klekz_pts.json are)"""
import json, sys, numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle
RIG, OUT = sys.argv[1], sys.argv[2]; CS = len(sys.argv) > 3 and sys.argv[3] == "cs"
T = (lambda cs, en: cs) if CS else (lambda cs, en: en)
S = 1.1711
rig = json.load(open(RIG)); W03 = np.array(rig["to_model"]["shot_003"])
rooms = json.load(open("lights.json"))["rooms"]
names = {"obyvak_kuchyn_chodba": T("obývák + kuchyň + chodba", "living room + kitchen + hall"), "loznice": T("ložnice (pokojíček)", "bedroom"),
         "koupelna": T("koupelna", "bathroom"), "predsin": T("předsíň", "entrance hall")}
col = {"bedroom": "#2563eb", "bathroom": "#16a34a", "living_room": "#ea580c", "hallway": "#dc2626",
       "pokojicek": "#2563eb", "koupelna": "#16a34a", "obyvak": "#ea580c", "chodbicka": "#dc2626"}
room_lab = {"bedroom": T("ložnice", "bedroom"), "bathroom": T("koupelna", "bathroom"), "living_room": T("obývák", "living room"), "hallway": T("chodbička", "hallway")}
fig, ax = plt.subplots(figsize=(15, 15))
for n, poly in rooms.items():
    P = np.array(poly) * S; ax.add_patch(Polygon(P, closed=True, fc="#f5f5f4", ec="#292524", lw=2.5))
    c = P.mean(0); w, h = np.ptp(P[:, 0]), np.ptp(P[:, 1])
    if n == "obyvak_kuchyn_chodba": c = c + [-2.3, 0.3]
    ax.text(c[0], c[1] + 0.22, names[n], ha="center", fontsize=12, weight="bold")
    ax.text(c[0], c[1] - 0.12, f"{w:.2f} × {h:.2f} m".replace(".", "," if CS else "."), ha="center", fontsize=11)
def rect(a0, a1, b0, b1, lab="", fc="#dbeafe", ec="#1e3a8a"):
    ax.add_patch(Rectangle((a0 * S, b0 * S), (a1 - a0) * S, (b1 - b0) * S, fc=fc, ec=ec, lw=1))
    if lab: ax.text((a0 + a1) / 2 * S, (b0 + b1) / 2 * S, lab, ha="center", va="center", fontsize=8)
for yc in (1.965, 4.8902): rect(-4.09, -4.09 + 2.04 / S, yc - 0.46 / S, yc + 0.46 / S, T("postel 2,04 × 0,92", "bed 2.04 × 0.92"))
rect(-0.775, -0.775 + 0.60 / S, 2.67, 4.38, T("skříň\n2,0 × 0,6", "wardrobe\n2.0 × 0.6"), fc="#fef3c7", ec="#92400e")
TC1 = (0.42 / 1.2779, -4.40 / 1.2779); TC2 = (-3.0, -3.62)
for (a, b), lab, cc in ((TC1, T("stůl – pozice 1", "table – position 1"), "#16a34a"), (TC2, T("stůl – pozice 2", "table – position 2"), "#9333ea")):
    ax.add_patch(Circle((a * S, b * S), 0.48, fc="none", ec=cc, lw=2.5, ls="-" if "1" in lab else "--"))
    ax.text(a * S, b * S - 0.72, lab, ha="center", fontsize=10, color=cc, weight="bold")
for (x0, x1, y, lab) in [(-2.23, -1.52, 1.335, T("dveře 0,83 × 1,94 m", "door 0.83 × 1.94 m")), (1.92, 2.66, 1.90, T("dveře 0,87 × 1,94 m", "door 0.87 × 1.94 m"))]:
    ax.plot([x0 * S, x1 * S], [y * S, y * S], color="#b45309", lw=6, solid_capstyle="butt")
    ax.text((x0 + x1) / 2 * S, y * S - 0.28, lab, ha="center", fontsize=9, color="#b45309")
m = rig["mat"]
ax.add_patch(Rectangle((m["x"][0], -m["z"][1]), m["x"][1] - m["x"][0], m["z"][1] - m["z"][0], fc="#1f5fd6", ec="#0b2f7a", lw=1.5, alpha=0.55))
ax.text((m["x"][0] + m["x"][1]) / 2, -(m["z"][0] + m["z"][1]) / 2 - 0.55, T("matrace 2 × 2 m", "mat 2 × 2 m"), ha="center", fontsize=10, color="#0b2f7a", weight="bold")
rect(-0.05, 0.30, 0.00, 0.50, T("sloup", "pillar"), fc="#a8a29e", ec="#292524")
try:
    K = np.concatenate([np.array(v) for v in json.load(open("klekz_pts.json")).values()])
    ax.plot(K[::25, 0] * S, K[::25, 1] * S, ".", ms=1.5, color="#0f766e", alpha=0.35, label=T("záznamy Captury Dataset_klekz (klouby)", "Captury recordings Dataset_klekz (joints)"))
except Exception as e: print("no klekz", e)
for c in rig["model_cams"]:
    x, y = c["p"][0], -c["p"][2]; ax.plot(x, y, "o", ms=9, color=col[c["room"]], mec="k"); ax.text(x + 0.08, y + 0.08, str(c["i"]), fontsize=8)
for r in ("bedroom", "bathroom", "living_room", "hallway"): ax.plot([], [], "o", color=col[r], mec="k", label=T("kamera WishCaptury – ", "WishCaptury camera – ") + room_lab[r])
try:
    Z = np.load("calib_shot003_to_202602.npz"); F = np.load("c3d_frames.npy").reshape(-1, 3); F = F[np.isfinite(F).all(1) & (np.abs(F).sum(1) > 0)]
    Q = (np.c_[F, np.ones(len(F))] @ W03.T)[:, :3]
    ax.plot(Q[::7, 0], -Q[::7, 2], ".", ms=2, color="#be185d", alpha=0.5, label=T("záznam Captury (unknown.c3d)", "Captury recording (unknown.c3d)"))
except Exception as e: print("no c3d", e)
ax.legend(loc="lower right", fontsize=10); ax.set_aspect("equal"); ax.set_xlabel("a [m]"); ax.set_ylabel("b [m]"); ax.grid(alpha=0.25)
ax.set_title(T("Byt v reálných metrech (1 jednotka splatu = 1,171 m, triangulace z kamer WishCaptury)\nstrop 2,70 m · kamery přichycené ke stěnám modelu (viz TODO)",
               "The flat in real metres (1 splat unit = 1.171 m, triangulated from the WishCaptury cameras)\nceiling 2.70 m · cameras snapped to the model walls (see TODO.md)"), fontsize=13)
plt.tight_layout(); plt.savefig(OUT, dpi=70); print("ok", OUT)
