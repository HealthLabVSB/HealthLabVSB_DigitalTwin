"""For each wall: where does the raw splat put the floor edge and the wall, compared with the model wall and the cameras?"""
import json, numpy as np
from splatio import read_ply, xyz_of
from walls2 import FY, TH
S = 1.1711
_, D = read_ply("/Users/dan/Downloads/splat/byt_cely_clean2_hloc.ply"); X = xyz_of(D).astype(np.float64)
op = 1 / (1 + np.exp(-D["opacity"].astype(np.float64)))
nA = np.array([np.cos(TH), 0, np.sin(TH)]); nB = np.array([-np.sin(TH), 0, np.cos(TH)])
A, B, H = X @ nA * S, X @ nB * S, (FY - X[:, 1]) * S
cams = {c["i"]: (c["p_calib"][0], -c["p_calib"][2]) for c in json.load(open("../viewer/rig.json"))["model_cams"]}
# name, normal axis, outward sign, along-range, model wall coordinate, cameras on it
W = [("living S", "b", -1, (-1.0, 1.5), -5.49, [20]), ("living S (shelf)", "b", -1, (-4.0, -2.0), -5.49, [21, 22]),
     ("living W", "a", -1, (-4.5, -0.5), -4.79, [11, 12]), ("living E", "a", +1, (-5.0, -0.5), 2.58, [18, 19]),
     ("bedroom N", "b", +1, (-3.6, -0.6), 6.22, [3]), ("bedroom W", "a", -1, (2.2, 5.8), -4.79, [0, 4]),
     ("bathroom E", "a", +1, (3.3, 6.0), 3.27, [6, 10]), ("bathroom W", "a", -1, (3.3, 6.0), 0.93, [8, 9]),
     ("bathroom N", "b", +1, (1.2, 3.0), 6.27, [6, 7]), ("hall S", "b", -1, (4.5, 6.5), 0.93, [28, 29]),
     ("hall E", "a", +1, (1.2, 4.2), 6.73, [27]), ("hall N", "b", +1, (4.5, 6.5), 4.38, [26])]
print(f"{'wall':18s} model   floor-edge  wall(1.1-2.65)  cams (coordinate)")
for name, ax, sg, (r0, r1), mw, cs in W:
    n, t = (B, A) if ax == "b" else (A, B)
    out = (n - mw) * sg                                   # metres outward from the model wall
    sel = (t > r0) & (t < r1) & (out > -0.6) & (out < 0.6) & (op > 0.2)
    bins = np.arange(-0.6, 0.6001, 0.02); c = (bins[:-1] + bins[1:]) / 2
    fl, _ = np.histogram(out[sel & (np.abs(H) < 0.03)], bins=bins, weights=op[sel & (np.abs(H) < 0.03)])
    wl, _ = np.histogram(out[sel & (H > 1.1) & (H < 2.65)], bins=bins, weights=op[sel & (H > 1.1) & (H < 2.65)])
    edge = c[np.nonzero(fl > 0.15 * fl.max())[0].max()] if fl.max() > 0 else np.nan     # outermost bin with real floor
    wpk = c[np.argmax(wl)] if wl.max() > 0 else np.nan
    cpos = ", ".join(f"{k}:{((cams[k][1] if ax == 'b' else cams[k][0]) - mw) * sg:+.2f}" for k in cs)
    print(f"{name:18s} {mw:6.2f}   {edge:+6.2f}       {wpk:+6.2f}          {cpos}   (offsets outward from the model wall, m)")
