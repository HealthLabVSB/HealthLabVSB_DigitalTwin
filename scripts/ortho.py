"""Orthographic splat renderer (front-to-back alpha compositing, DC colour only).
See-through shows as the background colour (magenta by default)."""
import numpy as np
from walls2 import gauss_params

C0 = 0.28209479177387814


def render(D, u, v, d, u0, u1, v0, v1, dmin, dmax, px=0.02, sel=None, bg=(1.0, 0.0, 1.0), alpha=False):
    """View along +d; image axes u (right) and v (up), all world unit vectors.
    Gaussians with depth (x.d) in [dmin, dmax] are drawn. Returns HxWx3 image on white."""
    x, cov, a = gauss_params(D)
    rgb = np.clip(0.5 + C0 * np.stack([D[f"f_dc_{i}"] for i in range(3)], 1).astype(np.float64), 0, 1)
    pu, pv, pd = x @ u, x @ v, x @ d
    m = (pd > dmin) & (pd < dmax) & (pu > u0 - .3) & (pu < u1 + .3) & (pv > v0 - .3) & (pv < v1 + .3)
    if sel is not None: m &= sel
    idx = np.where(m)[0][np.argsort(pd[m])]                   # nearest first
    J = np.stack([u, v])
    C2 = np.einsum("ij,njk,lk->nil", J, cov[idx], J) + np.eye(2) * 1e-6
    inv = np.linalg.inv(C2)
    W, H = int((u1 - u0) / px), int((v1 - v0) / px)
    img = np.zeros((H, W, 3)); T = np.ones((H, W))
    r = 3 * np.sqrt(np.stack([C2[:, 0, 0], C2[:, 1, 1]], 1))
    P = np.stack([pu[idx], pv[idx]], 1)
    i0 = np.maximum(np.floor((P - r - [u0, v0]) / px).astype(int), 0)
    i1 = np.minimum(np.floor((P + r - [u0, v0]) / px).astype(int), [W - 1, H - 1])
    for g in range(len(idx)):
        if (i1[g] < i0[g]).any(): continue
        cu = u0 + (np.arange(i0[g, 0], i1[g, 0] + 1) + .5) * px
        cv = v0 + (np.arange(i0[g, 1], i1[g, 1] + 1) + .5) * px
        du, dv = np.meshgrid(cu - P[g, 0], cv - P[g, 1])
        q = inv[g, 0, 0] * du * du + 2 * inv[g, 0, 1] * du * dv + inv[g, 1, 1] * dv * dv
        al = np.minimum(a[idx[g]] * np.exp(-.5 * q), 0.99)
        sl = (slice(i0[g, 1], i1[g, 1] + 1), slice(i0[g, 0], i1[g, 0] + 1))
        w = T[sl] * al
        img[sl] += w[..., None] * rgb[idx[g]]
        T[sl] *= 1 - al
    if alpha:                                                 # un-premultiplied colour + opacity
        cov_ = 1 - T
        return (img / np.maximum(cov_, 1e-6)[..., None])[::-1], cov_[::-1]
    img += T[..., None] * np.asarray(bg)                      # magenta background = see-through
    return img[::-1]                                          # v up
