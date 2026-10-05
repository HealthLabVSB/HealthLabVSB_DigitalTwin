"""Triangulate 3D points in the WishCap rig frame from the calibrated living-room frames (SIFT + epipolar check)."""
import numpy as np, cv2, itertools, json
import reg_rig as R_
sift = cv2.SIFT_create(nfeatures=12000, contrastThreshold=0.02)
FEAT = {}
for ci, f in R_.FRAMES.items():
    g = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2GRAY)
    kp, des = sift.detectAndCompute(g, None)
    FEAT[ci] = (np.array([k.pt for k in kp]), des)
    print("cam", ci, len(kp), flush=True)
def skew(v): return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
pts3, tracks = [], []
bf = cv2.BFMatcher(cv2.NORM_L2)
for c1, c2 in itertools.combinations(sorted(FEAT), 2):
    A, B = R_.RIG[c1], R_.RIG[c2]
    p1, d1 = FEAT[c1]; p2, d2 = FEAT[c2]
    m = bf.knnMatch(d1, d2, k=2)
    good = [a for a, b in m if a.distance < 0.8 * b.distance]
    if len(good) < 8: continue
    u1 = A.undistort(p1[[g.queryIdx for g in good]]); u2 = B.undistort(p2[[g.trainIdx for g in good]])
    Rrel = B.R @ A.R.T; trel = B.t - Rrel @ A.t
    E = skew(trel) @ Rrel; Fm = np.linalg.inv(B.K).T @ E @ np.linalg.inv(A.K)
    h1 = np.c_[u1, np.ones(len(u1))]; h2 = np.c_[u2, np.ones(len(u2))]
    l2 = h1 @ Fm.T; dist = np.abs(np.sum(h2 * l2, 1)) / np.hypot(l2[:, 0], l2[:, 1])
    ok = dist < 2.0
    if ok.sum() < 5: continue
    X = cv2.triangulatePoints(A.P, B.P, u1[ok].T, u2[ok].T); X = (X[:3] / X[3]).T
    # in front of both cameras, inside the room box, reprojection small
    ca = X @ A.R.T + A.t; cb = X @ B.R.T + B.t
    r1 = np.linalg.norm(A.project(X) - p1[[g.queryIdx for g in good]][ok], axis=1)
    r2 = np.linalg.norm(B.project(X) - p2[[g.trainIdx for g in good]][ok], axis=1)
    v = (ca[:, 2] > 0.3) & (cb[:, 2] > 0.3) & (X[:, 1] > -0.1) & (X[:, 1] < 3.2) & (r1 < 3) & (r2 < 3)
    print(f"pair {c1}-{c2}: {len(good)} matches, {ok.sum()} epipolar, {v.sum()} triangulated", flush=True)
    pts3.append(X[v])
P = np.concatenate(pts3)
np.save("rig_points.npy", P); print("total", len(P), "height range", np.percentile(P[:, 1], [2, 50, 98]).round(2))
