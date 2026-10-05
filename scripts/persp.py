"""Perspective splat renderer (EWA, front-to-back alpha, DC colour only) for checking splats from the render cameras.
Cameras are given in the model frame (a, b, h) like bl_render.py's views."""
import numpy as np
from walls2 import gauss_params, FY, TH

C0 = 0.28209479177387814
nA = np.array([np.cos(TH), 0, np.sin(TH)]); nB = np.array([-np.sin(TH), 0, np.cos(TH)])


def m2s(p):                                     # model (a, b, h) -> splat xyz
    a, b, h = p
    return a * nA + b * nB + np.array([0, FY - h, 0])


def render_persp(D, pos, tgt, lens_mm=16, W=640, H=360, near=0.08, bg=(1.0, 0.0, 1.0)):
    c, t = m2s(pos), m2s(tgt)
    f = t - c; f /= np.linalg.norm(f)
    up_w = np.array([0, -1.0, 0])                                   # splat +y is down
    r = np.cross(f, up_w); r /= np.linalg.norm(r); u = np.cross(r, f)
    R = np.stack([r, -u, f])                                        # camera x right, y down (image rows), z forward
    fx = W * lens_mm / 36.0; fy = fx; cx, cy = W / 2, H / 2
    x, cov, a = gauss_params(D)
    rgb = np.clip(0.5 + C0 * np.stack([D[f"f_dc_{i}"] for i in range(3)], 1).astype(np.float64), 0, 1)
    Xc = (x - c) @ R.T
    z = Xc[:, 2]
    m = z > near
    px_ = fx * Xc[:, 0] / np.where(m, z, 1) + cx; py_ = fy * Xc[:, 1] / np.where(m, z, 1) + cy
    m &= (px_ > -200) & (px_ < W + 200) & (py_ > -200) & (py_ < H + 200)
    idx = np.where(m)[0][np.argsort(z[m])]
    Xi, zi = Xc[idx], z[idx]
    J = np.zeros((len(idx), 2, 3))
    J[:, 0, 0] = fx / zi; J[:, 0, 2] = -fx * Xi[:, 0] / zi ** 2
    J[:, 1, 1] = fy / zi; J[:, 1, 2] = -fy * Xi[:, 1] / zi ** 2
    Cc = np.einsum("ij,njk,lk->nil", R, cov[idx], R)
    C2 = np.einsum("nij,njk,nlk->nil", J, Cc, J) + np.eye(2) * 0.3            # low-pass like 3DGS
    inv = np.linalg.inv(C2)
    rad = 3 * np.sqrt(np.stack([C2[:, 0, 0], C2[:, 1, 1]], 1))
    P = np.stack([px_[idx], py_[idx]], 1)
    i0 = np.maximum(np.floor(P - rad).astype(int), 0); i1 = np.minimum(np.ceil(P + rad).astype(int), [W - 1, H - 1])
    img = np.zeros((H, W, 3)); T = np.ones((H, W))
    for g in range(len(idx)):
        if (i1[g] < i0[g]).any() or (i1[g] - i0[g] > 400).any(): continue
        xs = np.arange(i0[g, 0], i1[g, 0] + 1) + .5; ys = np.arange(i0[g, 1], i1[g, 1] + 1) + .5
        du, dv = np.meshgrid(xs - P[g, 0], ys - P[g, 1])
        q = inv[g, 0, 0] * du * du + 2 * inv[g, 0, 1] * du * dv + inv[g, 1, 1] * dv * dv
        al = np.minimum(a[idx[g]] * np.exp(-.5 * q), 0.99)
        sl = (slice(i0[g, 1], i1[g, 1] + 1), slice(i0[g, 0], i1[g, 0] + 1))
        w = T[sl] * al
        img[sl] += w[..., None] * rgb[idx[g]]
        T[sl] *= 1 - al
    return img + T[..., None] * np.asarray(bg)
