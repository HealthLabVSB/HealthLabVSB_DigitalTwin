import numpy as np


def read_ply(path):
    with open(path, "rb") as f:
        raw = b""
        while b"end_header\n" not in raw:
            raw += f.read(4096)
    hdr_end = raw.index(b"end_header\n") + len(b"end_header\n")
    lines = raw[:hdr_end].decode("ascii", "replace").splitlines()
    props = [ln.split()[1:3] for ln in lines if ln.startswith("property")]
    assert all(t == "float" for t, _ in props), "non-float props present"
    n = [int(ln.split()[-1]) for ln in lines if ln.startswith("element vertex")][0]
    dtype = np.dtype([(nm, "<f4") for _, nm in props])
    data = np.fromfile(path, dtype=dtype, count=n, offset=hdr_end)
    assert len(data) == n
    return lines, data


def write_ply(path, lines, data):
    hdr = "\n".join(f"element vertex {len(data)}" if ln.startswith("element vertex") else ln
                    for ln in lines) + "\n"
    with open(path, "wb") as f:
        f.write(hdr.encode("ascii"))
        data.tofile(f)


def xyz_of(data):
    return np.stack([data["x"], data["y"], data["z"]], 1).astype(np.float64)


def components(xyz, vox, kmin):
    """Density-connected components: voxels with >= kmin points, 26-connected.
    Returns per-point component id (-1 = point in a sparse voxel) and {id: point count}."""
    origin = xyz.min(0)
    vi = np.floor((xyz - origin) / vox).astype(np.int64)
    dims = vi.max(0) + 2
    key = (vi[:, 0] * dims[1] + vi[:, 1]) * dims[2] + vi[:, 2]
    uniq, inv, counts = np.unique(key, return_inverse=True, return_counts=True)
    sidx = np.where(counts >= kmin)[0]
    usolid = uniq[sidx]
    M = len(usolid)
    vc = np.stack([usolid // (dims[2] * dims[1]), (usolid // dims[2]) % dims[1], usolid % dims[2]], 1)
    parent = np.arange(M)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    offs = [(1,0,0),(0,1,0),(0,0,1),(1,1,0),(1,-1,0),(1,0,1),(1,0,-1),(0,1,1),(0,1,-1),
            (1,1,1),(1,1,-1),(1,-1,1),(1,-1,-1)]
    # vectorised neighbour lookup via searchsorted on the sorted solid keys
    for dx, dy, dz in offs:
        nk = ((vc[:, 0] + dx) * dims[1] + (vc[:, 1] + dy)) * dims[2] + (vc[:, 2] + dz)
        pos = np.clip(np.searchsorted(usolid, nk), 0, M - 1)
        hit = np.where(usolid[pos] == nk)[0]
        for i, j in zip(hit, pos[hit]):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj
    roots = np.array([find(i) for i in range(M)])
    vox_comp = np.full(len(uniq), -1, np.int64)
    vox_comp[sidx] = roots
    pt_comp = vox_comp[inv]
    ids, cnts = np.unique(pt_comp[pt_comp >= 0], return_counts=True)
    return pt_comp, dict(zip(ids.tolist(), cnts.tolist()))
