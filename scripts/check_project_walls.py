"""Project the model's walls (floor and ceiling junctions) into the real rig frames with the 2026-02 calibration."""
import json, re, sys, numpy as np
from PIL import Image, ImageDraw
import rig_xf as X
S = 1.1711; CEIL = 2.70
txt = open("/Users/dan/WishCaptury/calib/camera-2026-02.calib").read(); blocks = re.split(r"\ncamera\t", txt)[1:]
def cam(i):
    b = blocks[i]
    o = np.array([float(v) for v in re.search(r"origin\t+\s*(\S+)\s+(\S+)\s+(\S+)", b).groups()]) / 1000
    ex = np.array([float(v) for v in re.search(r"#\s+extrinsics\n" + r"#\s+(\S+)\s+(\S+)\s+(\S+)\s+\S+\n" * 3, b).groups()]).reshape(3, 3)
    K = np.array([float(v) for v in re.search(r"#\s+intrinsics\n" + r"#\s+(\S+)\s+(\S+)\s+(\S+)\n" * 3, b).groups()]).reshape(3, 3)
    dist = [float(v) for v in re.search(r"distortion\t+\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", b).groups()]
    return o, ex, K, dist
def project(i, P_model, W):
    o, R, K, (k1, k2, p1, p2, k3) = cam(i)
    rig = np.array([X.model_m_to_rig(a, b, h) for a, b, h in P_model])
    pc = (rig - o) @ R.T; ok = pc[:, 2] > 0.05
    x, y = pc[:, 0] / pc[:, 2], pc[:, 1] / pc[:, 2]; r2 = x * x + y * y; rad = 1 + k1 * r2 + k2 * r2 ** 2 + k3 * r2 ** 3
    xd = x * rad + 2 * p1 * x * y + p2 * (r2 + 2 * x * x); yd = y * rad + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
    ok &= r2 < 2.2
    return np.stack([(K[0, 0] * xd + K[0, 2]) * W, (K[1, 1] * yd + K[1, 2]) * W], 1), ok
rooms = {n: np.array(p) * S for n, p in json.load(open("lights.json"))["rooms"].items()}
def seg(A, B, h, n=60): return [(A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t, h) for t in np.linspace(0, 1, n)]
def draw(i, alt_south=None, out=None, extra=()):
    im = Image.open(f"/Users/dan/WishCaptury/compare/frames/cam{i}_f100.jpg").convert("RGB"); W = im.width; d = ImageDraw.Draw(im)
    def poly(pts, col, w=3):
        uv, ok = project(i, pts, W)
        for k in range(len(uv) - 1):
            if ok[k] and ok[k + 1]: d.line([tuple(uv[k]), tuple(uv[k + 1])], fill=col, width=w)
    for P in rooms.values():
        for k in range(len(P)):
            for h, col in ((0.0, (255, 40, 40)), (CEIL, (255, 120, 120))): poly(seg(P[k - 1], P[k], h), col)
    if alt_south is not None:
        for h in (0.0, CEIL): poly(seg((-4.79, alt_south), (2.6, alt_south), h), (0, 220, 255))
    for (a, b, h, lab) in extra:
        uv, ok = project(i, [(a, b, h)], W)
        if ok[0]: x, y = uv[0]; d.ellipse([x - 14, y - 14, x + 14, y + 14], outline=(40, 120, 255), width=4); d.text((x + 16, y - 8), lab, fill=(40, 120, 255))
    im.save(out or f"proj_cam{i}.jpg", quality=88)
cams = {c["i"]: c for c in json.load(open("../viewer/rig.json"))["model_cams"]}
ext = [(cams[k]["p_calib"][0], -cams[k]["p_calib"][2], cams[k]["p_calib"][1], f"cam{k}") for k in (15, 20, 21, 22, 23)]
for i in (13, 15, 17, 19): draw(i, alt_south=-5.70, extra=ext)
print("ok")
