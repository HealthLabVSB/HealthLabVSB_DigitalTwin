"""rig.json for the viewer: the 30 WishCap cameras of both calibrations (rig metres, OpenCV extrinsics) and the 4x4 matrices taking
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
