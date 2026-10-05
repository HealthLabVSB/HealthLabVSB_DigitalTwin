# Splats

The PLY files are over GitHub's 100 MB limit and are not in git; get them from the release assets or from the maintainers.

| File | Content | Frame |
|---|---|---|
| `hybrid_splat.ply`, `hybrid_splat_no_ceiling.ply`, `hybrid_splat_table2.ply`, `hybrid_splat_no_ceiling_table2.ply` | Hybrid splat, ~5.2 M gaussians, SH0 | splat frame, metres (`transforms/frames.json` → `splat_to_model.metres`) |
| `hybrid_splat_wishcap.ply`, `hybrid_splat_table2_wishcap.ply` | Hybrid splat | WishCap rig 2026-02, metres, Y up |
| `hybrid_splat_captury.ply`, `hybrid_splat_table2_captury.ply` | Hybrid splat | Captury rig shot_003, metres, Y up |
| `gaussian_splat_original.ply` | Original 3D Gaussian Splatting reconstruction (cleaned) | splat frame, splat units (`splat_to_model.units`) |

Web versions of the hybrid and original splats are in `viewer/*.splat` (antimatter15 format, splat frame, metres).
