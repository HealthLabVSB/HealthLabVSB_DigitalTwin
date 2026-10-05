"""Register the model (splat units) into the WishCap rig frame using real camera frames + calibration."""
import sys, json, glob, os, numpy as np, cv2
sys.path.insert(0, "/Users/dan/WishCaptury")
from wishcap.calib.captury import load_rig
RIG = load_rig("/Users/dan/WishCaptury/calib/camera-2026-02.calib", units="m")
S = 1.2779
rooms = json.load(open("lights.json"))["rooms"]
F0 = json.load(open("rig_fit.json"))

def segments():
    """3D line segments of the model in (a, b, h_m): plan in units, height in metres."""
    segs = []
    H = 2.31 * S
    for name in ("obyvak_kuchyn_chodba", "loznice", "predsin", "koupelna"):
        P = rooms[name]
        for i in range(len(P)):
            p0, p1 = P[i], P[(i + 1) % len(P)]
            segs.append(((*p0, 0.0), (*p1, 0.0), "floor")); segs.append(((*p0, H), (*p1, H), "ceil"))
            segs.append(((*p0, 0.0), (*p0, H), "corner"))
    for bh, bl in [(0.65, -0.61), (-2.79, -3.85)]:                          # living-room windows on a = -4.09
        for h in (0.70 * S, 2.25 * S): segs.append(((-4.09, bl, h), (-4.09, bh, h), "win"))
        for b in (bl, bh): segs.append(((-4.09, b, 0.70 * S), (-4.09, b, 2.25 * S), "win"))
    segs.append(((1.68, -4.69, 0.70 * S), (1.68, 0.45, 0.70 * S), "counter"))   # worktop front edge
    segs.append(((1.68, -4.69, 0.0), (1.68, 0.45, 0.0), "counter"))
    for a in (-2.23, -1.52): segs.append(((a, 1.26, 0.0), (a, 1.26, 2.12), "door"))
    segs.append(((-2.23, 1.26, 2.12), (-1.52, 1.26, 2.12), "door"))
    return segs

def to_rig(abh, p):
    """(a, b) units + h metres -> rig xyz metres. p = (s, th, tx, ty, dy)"""
    s, th, tx, ty, dy = p
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]]); Mi = np.array([[0, -1], [-1, 0]]); M = R @ Mi
    Q = np.asarray(abh)[..., :2]; h = np.asarray(abh)[..., 2]
    X = ((Q - [tx, ty]) * s) @ M
    return np.stack([X[..., 0], h + dy, X[..., 1]], -1)

def sample(segs, step=0.05):
    pts, kinds = [], []
    for p0, p1, k in segs:
        p0, p1 = np.array(p0, float), np.array(p1, float)
        L = np.linalg.norm((p1 - p0) * [S, S, 1]); n = max(2, int(L / step))
        for t in np.linspace(0, 1, n): pts.append(p0 + (p1 - p0) * t); kinds.append(k)
    return np.array(pts), kinds

FRAMES = {int(os.path.basename(f)[3:5]): f for f in sorted(glob.glob("/Users/dan/WishCaptury/compare/frames/cam*_f100.jpg"))}
def overlay(p, out):
    segs = segments(); P3, kinds = sample(segs, 0.02)
    tiles = []
    for ci, f in FRAMES.items():
        img = cv2.imread(f); cam = RIG[ci]
        W = to_rig(P3, p); cpos = W @ cam.R.T + cam.t
        uv = cam.project(W)
        ok = (cpos[:, 2] > 0.1) & (uv[:, 0] >= 0) & (uv[:, 0] < img.shape[1]) & (uv[:, 1] >= 0) & (uv[:, 1] < img.shape[0])
        col = {"floor": (0, 255, 255), "ceil": (255, 0, 255), "corner": (0, 255, 0), "win": (255, 128, 0), "counter": (0, 0, 255), "door": (0, 128, 255)}
        for (u, v), k, o in zip(uv, kinds, ok):
            if o: cv2.circle(img, (int(u), int(v)), 2, col[k], -1)
        cv2.putText(img, f"cam{ci}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        tiles.append(cv2.resize(img, (720, 540)))
    grid = np.vstack([np.hstack(tiles[i:i + 3]) for i in (0, 3)])
    cv2.imwrite(out, grid)

if __name__ == "__main__":
    p0 = [F0["s"], F0["th"], F0["tx"], F0["ty"], 0.0]
    overlay(p0, "reg_before.jpg"); print("cams", list(FRAMES))
