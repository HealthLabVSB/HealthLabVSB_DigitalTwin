"""INRIA .ply -> antimatter15 .splat (32 B/gaussian: xyz f32, scale f32, rgba u8, quat u8), sorted big+opaque first."""
import sys, numpy as np
from splatio import read_ply
C0 = 0.28209479177387814
_, D = read_ply(sys.argv[1])
SCALE = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0          # e.g. 1.2779: model units -> metres
xyz = (np.stack([D["x"], D["y"], D["z"]], 1) * SCALE).astype(np.float32)
sc = (np.exp(np.stack([D[f"scale_{k}"] for k in range(3)], 1)) * SCALE).astype(np.float32)
op = 1 / (1 + np.exp(-D["opacity"].astype(np.float64)))
rgb = 0.5 + C0 * np.stack([D[f"f_dc_{k}"] for k in range(3)], 1)
rgba = (np.clip(np.concatenate([rgb, op[:, None]], 1), 0, 1) * 255).round().astype(np.uint8)
q = np.stack([D[f"rot_{k}"] for k in range(4)], 1).astype(np.float64); q /= np.linalg.norm(q, axis=1, keepdims=True) + 1e-12
qu = np.clip(q * 128 + 128, 0, 255).astype(np.uint8)
order = np.argsort(-(sc.prod(1) * op))
buf = np.zeros(len(D), dtype=[("p", "<f4", 3), ("s", "<f4", 3), ("c", "u1", 4), ("r", "u1", 4)])
buf["p"], buf["s"], buf["c"], buf["r"] = xyz[order], sc[order], rgba[order], qu[order]
buf.tofile(sys.argv[2]); print(sys.argv[2], len(D), "gaussians", round(buf.nbytes / 1e6, 1), "MB")
