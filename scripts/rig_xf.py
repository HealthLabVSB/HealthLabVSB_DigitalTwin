"""Model -> WishCap rig frame (calib/camera-2026-02.calib, the calibration of the recent takes).

Fitted in iterace 07 by triangulating 547 points from the calibrated living-room frames (compare/frames, SIFT +
epipolar check) and aligning them to the splat: median residual 3.2 cm. The rig frame is metres here, Y up, the same
axes as the C3D / FBX takes (those are in millimetres). Blender imports a Y-up glTF and a Y-up FBX the same way,
(x, y, z) -> (x, -z, y), so a GLB written in this frame lands exactly on the imported mocap.

Model frame: a, b in splat units (or metres = units * S), h up.
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else \
    "/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad"
_F = json.load(open(os.path.join(HERE, "rig_icp.json")))
RS, RTH, RTX, RTY, RDY = _F["s"], _F["th"], _F["tx"], _F["ty"], _F["dy"]
S_MODEL = 1.1711                      # metres per unit used by the model (== RS to 4 digits)
_c, _s = math.cos(RTH), math.sin(RTH)
# M = R(th) @ [[0,-1],[-1,0]]  : (a, b) row vector @ M -> (x, z)
M = ((_s, -_c), (-_c, -_s))
F = RS / S_MODEL


def model_m_to_rig(a_m, b_m, h_m):
    """Model metric coordinates -> rig (x, y, z) metres (Y up)."""
    qa, qb = a_m / S_MODEL - RTX, b_m / S_MODEL - RTY
    x = (qa * M[0][0] + qb * M[1][0]) * RS
    z = (qa * M[0][1] + qb * M[1][1]) * RS
    return x, h_m * F + RDY, z


def blender_matrix():
    """4x4 (row-major lists) taking Blender model coords (a_m, b_m, h_m) to Blender coords of the rig frame,
    i.e. (x_rig, -z_rig, y_rig) - where Blender puts an imported Y-up glTF / FBX of the rig frame."""
    c0 = (RTX * M[0][0] + RTY * M[1][0]) * RS
    c1 = (RTX * M[0][1] + RTY * M[1][1]) * RS
    return [[F * M[0][0], F * M[1][0], 0.0, -c0],
            [-F * M[0][1], -F * M[1][1], 0.0, c1],
            [0.0, 0.0, F, RDY],
            [0.0, 0.0, 0.0, 1.0]]


def blender_matrix_captury():
    """Same, but into the frame of Captury's own exports (shot_003 calibration, e.g. compare/unknown.c3d).
    p_202602 = R p_shot003 + t was fitted on the 30 camera centres (median 5 cm)."""
    import numpy as np
    Z = np.load(os.path.join(HERE, "calib_shot003_to_202602.npz"))
    R, t = Z["R"], Z["t"]
    G = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])               # rig (x, y, z) -> Blender (x, -z, y)
    C = np.eye(4); C[:3, :3] = G @ R.T @ G.T; C[:3, 3] = -G @ R.T @ t
    return (C @ np.array(blender_matrix())).tolist()


def blender_matrix_captury_fbx():
    """Captury's own FBX lands in Blender at (-x, z, y) of its rig frame (verified to 0.0 mm on the 12 cameras stored in
    Dataset_klekz/*/unknown.fbx), i.e. turned 180 deg about the vertical against a glTF import. This matrix puts the model
    where such an FBX lands."""
    import numpy as np
    Rz = np.diag([-1.0, -1.0, 1.0, 1.0])
    return (Rz @ np.array(blender_matrix_captury())).tolist()
