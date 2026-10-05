import json, sys, numpy as np, cv2
import reg_rig as R_
Su = 1.2779                                                     # old metres-per-unit used inside segments()
def segs_units():
    out = []
    for p0, p1, k in R_.segments():
        if k == "ceil": continue
        out.append(((p0[0], p0[1], p0[2] / Su), (p1[0], p1[1], p1[2] / Su), k))
    return out
def to_rig(abh, p):
    s, th, tx, ty, dy = p
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]]); M = R @ np.array([[0, -1], [-1, 0]])
    Q = np.asarray(abh)[..., :2]; X = ((Q - [tx, ty]) * s) @ M
    return np.stack([X[..., 0], np.asarray(abh)[..., 2] * s + dy, X[..., 1]], -1)
def overlay(p, out, crop=None):
    pts, kinds = [], []
    for p0, p1, k in segs_units():
        p0, p1 = np.array(p0), np.array(p1)
        for t in np.linspace(0, 1, 160): pts.append(p0 + (p1 - p0) * t); kinds.append(k)
    pts = np.array(pts); W = to_rig(pts, p)
    col = {"floor": (0, 255, 255), "corner": (0, 255, 0), "win": (255, 128, 0), "counter": (0, 0, 255), "door": (0, 128, 255)}
    tiles = []
    for ci, f in R_.FRAMES.items():
        img = cv2.imread(f); cam = R_.RIG[ci]; c = W @ cam.R.T + cam.t
        rn = np.hypot(c[:, 0] / np.maximum(c[:, 2], 1e-3), c[:, 1] / np.maximum(c[:, 2], 1e-3)); uv = cam.project(W)
        for (u, v), k, z, r in zip(uv, kinds, c[:, 2], rn):
            if z > 0.2 and r < 1.3 and 0 <= u < img.shape[1] and 0 <= v < img.shape[0]: cv2.circle(img, (int(u), int(v)), 2, col[k], -1)
        cv2.putText(img, f"cam{ci}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
        tiles.append(img if crop else cv2.resize(img, (720, 540)))
    if crop: cv2.imwrite(out, tiles[crop]); return
    cv2.imwrite(out, np.vstack([np.hstack(tiles[i:i + 3]) for i in (0, 3)]))
if __name__ == "__main__":
    F = json.load(open("rig_icp.json")); p = [F["s"], F["th"], F["tx"], F["ty"], F["dy"]]
    overlay(p, "reg_icp.jpg")
    for k in (4, 5): overlay(p, f"reg_icp_cam{k}.jpg", crop=k)
