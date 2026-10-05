"""rig.json for the viewer: the 30 WishCap cameras (shown snapped in front of the model walls, see TODO.md) of both calibrations (rig metres, OpenCV extrinsics) and the 4x4 matrices taking
each rig frame into the web model frame (x = a_m, y = h_m, z = -b_m). Used by model.html (camera toggle) and fbx.html."""
import json, re, math, numpy as np
import sys
import rig_xf as X
OUT = sys.argv[1] if len(sys.argv) > 1 else "rig.json"
S, RS, M = X.S_MODEL, X.RS, X.M
k = S / RS
W26 = np.array([[k * M[0][0], 0, k * M[0][1], S * X.RTX],          # 2026-02 rig (x, y, z) m -> web model
                [0, k, 0, -k * X.RDY],
                [-k * M[1][0], 0, -k * M[1][1], -S * X.RTY],
                [0, 0, 0, 1]])
Z = np.load("calib_shot003_to_202602.npz"); A = np.eye(4); A[:3, :3] = Z["R"]; A[:3, 3] = Z["t"]
W03 = W26 @ A                                                      # shot_003 rig -> 2026-02 -> web model
def parse(path):
    out = []
    for blk in re.split(r"\ncamera\t", open(path).read())[1:]:
        i, mac = blk.split("\n")[0].split("\t")[:2]
        o = [float(v) / 1000 for v in re.search(r"origin\t+\s*(\S+)\s+(\S+)\s+(\S+)", blk).groups()]
        ex = re.search(r"#\s+extrinsics\n" + r"#\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+\n" * 3, blk).groups()
        R = np.array([float(v) for v in ex]).reshape(3, 3)
        sw, sh = [float(v) for v in re.search(r"sensorSize\t+\s*(\S+)\s+(\S+)", blk).groups()]
        f = float(re.search(r"focalLength\t+\s*(\S+)", blk).group(1))
        out.append(dict(i=int(i), mac=mac.strip(), o=[round(v, 5) for v in o], R=np.round(R, 6).tolist(),
                        fov=[round(2 * math.degrees(math.atan(sw / 2 / f)), 2), round(2 * math.degrees(math.atan(sh / 2 / f)), 2)]))
    return out
C26 = parse("/Users/dan/WishCaptury/calib/camera-2026-02.calib")
C03 = parse("/Users/dan/Downloads/Dataset_klekz/config/camera.calib")
ROOM_EN = {"pokojicek": "bedroom", "koupelna": "bathroom", "obyvak": "living_room", "chodbicka": "hallway"}
rooms = {str(c): ROOM_EN[r] for r, v in json.load(open("/Users/dan/WishCaptury/configs/apartment.json"))["rooms"].items() for c in v["cameras"]}
# the cameras in the web model frame (from the 2026-02 calibration): centre + forward / right / down unit vectors
model = []
for c in C26:
    R = np.array(c["R"]); p = W26 @ np.r_[c["o"], 1]
    model.append(dict(i=c["i"], room=rooms[str(c["i"])], p=np.round(p[:3], 4).tolist(),
                      f=np.round(W26[:3, :3] @ R[2] / k, 5).tolist(), r=np.round(W26[:3, :3] @ R[0] / k, 5).tolist(),
                      d=np.round(W26[:3, :3] @ R[1] / k, 5).tolist(), fov=c["fov"]))
# Interim fix, see TODO.md "More precise alignment of the cameras with the flat": a few model walls sit 15-30 cm inside
# the real ones, so some calibrated cameras end up behind a wall. For display, each camera is pushed into the room it
# looks at until it hangs INSET in front of every nearby wall. The calibrated centre stays in p_calib (and in "calib",
# which the FBX registration uses).
INSET, NEAR = 0.08, 0.45
POLYS = {n: np.array(p, float) * S for n, p in json.load(open("lights.json"))["rooms"].items()}     # (a, b) metres
def inside(pt, P):
    c = False
    for i in range(len(P)):
        (x1, y1), (x2, y2) = P[i], P[i - 1]
        if (y1 > pt[1]) != (y2 > pt[1]) and pt[0] < (x2 - x1) * (pt[1] - y1) / (y2 - y1) + x1: c = not c
    return c
def snap(q, f):
    room = next((P for P in POLYS.values() if inside(q + 0.6 * f, P)), None)          # the room the camera looks into
    if room is None: return q
    for _ in range(3):
        for i in range(len(room)):
            A_, B_ = room[i - 1], room[i]; L_ = np.linalg.norm(B_ - A_); u = (B_ - A_) / L_
            n = np.array([-u[1], u[0]])
            if not inside((A_ + B_) / 2 + 0.01 * n, room): n = -n                     # inward normal
            t, s_ = (q - A_) @ u, (q - A_) @ n
            if -0.3 < t < L_ + 0.3 and -NEAR < s_ < INSET: q = q + (INSET - s_) * n
    return q
for m in model:
    p = np.array(m["p"]); ab = np.array([p[0], -p[2]]); f = np.array([m["f"][0], -m["f"][2]]); f /= np.linalg.norm(f)
    q = snap(ab.copy(), f)
    m["p_calib"] = m["p"]; m["p"] = [round(q[0], 4), m["p"][1], round(-q[1], 4)]
    m["moved_cm"] = round(float(np.linalg.norm(q - ab)) * 100, 1)
# Cameras 15 and 23 hang from the ceiling on either side of the pillar. A photo of the pillar (Dan, 2026-10-05) and the
# rig frames put the real pillar ~16 cm further east than the model has it; until the pillar moves (TODO.md), the two
# cameras move 16 cm west so that they sit next to the model pillar as in the photo (15: ~0.29 m west of it, 23: ~0.07 m east).
PILLAR_FIX = {15: -0.16, 23: -0.16}
for m in model:
    if m["i"] in PILLAR_FIX:
        m["p"][0] = round(m["p"][0] + PILLAR_FIX[m["i"]], 4)
        m["moved_cm"] = round(float(np.hypot(m["p"][0] - m["p_calib"][0], m["p"][2] - m["p_calib"][2])) * 100, 1)
print("moved cameras:", {m["i"]: m["moved_cm"] for m in model if m["moved_cm"] > 0.05})
mat_a, mat_b = (0.42 - 1.0 / S, 0.42 + 1.0 / S), (-0.04 - 2.0 / S, -0.04)  # units; pillar a -0.05..0.30, b 0..0.50
L = json.load(open("lights.json"))["rooms"]                          # room polygons (units) -> web x, z metres
POLY_EN = {"obyvak_kuchyn_chodba": "living_kitchen_hall", "loznice": "bedroom", "koupelna": "bathroom", "predsin": "entrance_hall"}
rooms_poly = {POLY_EN[n]: [[round(a * S, 4), round(-b * S, 4)] for a, b in p] for n, p in L.items()}
json.dump(dict(rooms=rooms, rooms_poly=rooms_poly, calib={"2026-02": C26, "shot_003": C03},
               to_model={"2026-02": W26.round(7).tolist(), "shot_003": W03.round(7).tolist()},
               model_cams=model,
               mat=dict(x=[round(mat_a[0] * S, 4), round(mat_a[1] * S, 4)], z=[round(-mat_b[1] * S, 4), round(-mat_b[0] * S, 4)],
                        y=[0.002, 0.102])), open(OUT, "w"))
print("cams", len(C26), len(C03), "mat", json.load(open(OUT))["mat"])
