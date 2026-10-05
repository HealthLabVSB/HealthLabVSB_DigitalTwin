"""transforms/frames.json: every matrix needed to move data between the model frame and the mocap rig frames.
Run from the scripts folder (needs rig_xf.py, rig_icp.json, calib_shot003_to_202602.npz). Usage: python make_frames.py OUT.json"""
import json, sys, numpy as np
import rig_xf as X
S, RS, M = X.S_MODEL, X.RS, X.M
k = S / RS
W26 = np.array([[k * M[0][0], 0, k * M[0][1], S * X.RTX], [0, k, 0, -k * X.RDY],
                [-k * M[1][0], 0, -k * M[1][1], -S * X.RTY], [0, 0, 0, 1]])           # 2026-02 rig (m, Y up) -> model (glTF axes)
Z = np.load("calib_shot003_to_202602.npz"); A = np.eye(4); A[:3, :3] = Z["R"]; A[:3, 3] = Z["t"]
W03 = W26 @ A                                                                          # shot_003 rig -> model (glTF axes)
B = {"wishcap": np.array(X.blender_matrix()), "captury_gltf": np.array(X.blender_matrix_captury()),
     "captury_fbx": np.array(X.blender_matrix_captury_fbx())}
from walls2 import FY, TH                                                              # the splat frame: +Y down, turned TH
c, s_ = np.cos(TH), np.sin(TH)
SPL = np.array([[c, 0, s_, 0], [0, -1, 0, S * FY], [s_, 0, -c, 0], [0, 0, 0, 1]])        # splat metres -> model (glTF axes)
SPU = SPL @ np.diag([S, S, S, 1])                                                          # splat units  -> model (glTF axes)
r = lambda m: np.round(m, 8).tolist()
out = {
 "about": "Health.Lab Model 1.0.8 Beta. 4x4 matrices, row-major, act on column vectors [x, y, z, 1]. Metres everywhere.",
 "model_frame": {"gltf_axes": "x = a (east-west along the facade), y = height above the floor, z = -b; this is what the GLB/viewer uses",
                 "blender_axes": "x = a, y = b, z = height (a glTF import turns (x, y, z) into (x, -z, y))",
                 "scale": "1 unit of the original splat = 1.1711 m"},
 "rig_to_model": {
   "wishcap_2026_02": {"matrix": r(W26), "inverse": r(np.linalg.inv(W26)),
                       "about": "WishCap panel takes (calibration camera-2026-02.calib), rig metres, Y up -> model (glTF axes)"},
   "captury_shot003": {"matrix": r(W03), "inverse": r(np.linalg.inv(W03)),
                       "about": "Captury exports (C3D, FBX; calibration shot_003), rig metres, Y up -> model (glTF axes)"}},
 "splat_to_model": {
   "metres": {"matrix": r(SPL), "inverse": r(np.linalg.inv(SPL)),
              "about": "hybrid_splat.ply / hybrid_splat_no_ceiling(_table2).ply and viewer/*.splat: the frame of the original reconstruction in metres, +Y down, turned 10.75 deg about the vertical"},
   "units": {"matrix": r(SPU), "inverse": r(np.linalg.inv(SPU)),
             "about": "gaussian_splat_original.ply: the original reconstruction in splat units (1 unit = 1.1711 m)"}},
 "blender": {n: {"model_to_frame": r(m), "frame_to_model": r(np.linalg.inv(m))} for n, m in B.items()},
 "blender_about": {"wishcap": "where Blender puts a WishCap FBX or a Y-up glTF in the 2026-02 rig frame",
                   "captury_gltf": "where Blender puts Y-up glTF/C3D-style data in the Captury (shot_003) frame",
                   "captury_fbx": "where Blender puts an FBX exported by Captury (it lands turned 180 deg about the vertical vs glTF)"},
}
json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "frames.json", "w"), indent=1)
print("frames ok")
