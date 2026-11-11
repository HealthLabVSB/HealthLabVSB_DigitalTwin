# TODO

## The north bed in the bedroom against the north wall

*Czech: severní postel v pokojíčku ke zdi.*

**Status:** the model is done (2026-10-13); the renders, the splats and the floor plan still show 1.0.8.

The north bed stood 0.37 m off the north wall. Bedroom cameras 0–3 show it against the wall (Dan noticed it in the
WishCap panel). It moved 0.334 m north, its duvet now 5 mm short of the wall, and its nightstand with the router on it
moved with it, so the gap between them is unchanged. Changed: `scripts/bl_detail.py`, `scripts/build_clean.py`,
`scripts/plan_m.py`, the six `.blend` files, and the twelve baked GLBs (re-baked from the `.blend` files with the
original atlas layout: size 4096, density 160, 256 spp; `_captury` reframed with `blender_matrix_captury_fbx`).

- [ ] Re-render the bedroom views (`render_bedroom*`, `render_dollhouse`) and the README images made from them.
- [ ] Re-sample the hybrid splats (`hybrid_splat.py`, then `to_splat.py`); they are sampled from the model.
- [ ] Redraw `renders/floor_plan_metres.png` (`plan_m.py` needs `klekz_pts.json` and `c3d_frames.npy`).

## More precise alignment of the cameras with the flat

*Czech: přesnější zarovnání kamer s bytem.*

**Status:** interim fix in 1.0.8 Beta, recorded 2026-10-05.

### What the interim fix does

- The 30 rig cameras are **shown** snapped 8 cm in front of the model walls. This applies to:
  - the viewer (`viewer/rig.json` → `model_cams[].p`);
  - the Blender collection `wishcap_cameras`.
- Cameras 15 and 23 are moved 16 cm west, so they sit next to the model pillar as in the photo of the pillar.
- The **calibrated** positions are kept:
  - in the viewer: `model_cams[].p_calib` and `calib`;
  - in Blender: the custom property `calibrated_position`.
- The FBX registration in the viewer uses the calibration, so mocap recordings are **not** affected.

### What was found

A few **model walls** are misplaced. The rig calibration itself is fine: cameras on interior walls sit 0–15 cm in front of them, and recordings stand on the floor to ±2 cm (over the whole living room only since the registration was levelled in November 2026; see the README's registration checks).

| Where | Finding | Evidence |
|---|---|---|
| Living room, south wall | ~27 cm further south than in the model. The shelf, desk and pictures along it move with it. | The pictures on the wall and the floor end at b ≈ −5.76 m in the raw splat. The rig cameras triangulate the shelf front at −5.47 m, and the shelf is ~35 cm deep. The model has the wall at −5.49 m. Cameras 20–22 then hang 7–11 cm in front of the real wall. |
| Bathroom, east wall | ~15–20 cm further east; the bathroom is ~2.5 m wide instead of 2.34 m. | Cameras 5, 6 and 10 are behind it. Dan: "the shower is wider in reality". The bathroom capture was broken, so its walls were partly estimated. |
| Entrance hall, south wall | Possibly ~30 cm further south. Check on site (door niche?). | Cameras 28 and 29 are behind it, and both calibrations agree on them. |
| Pillar | ~16 cm further east. | Dan's photo of the pillar with cameras 15 and 23: camera 15 is ~0.29 m west of the pillar, camera 23 ~0.07 m east of it. The photo fits within ±10 px with the shift and 50–74 px without it. Rig frame of camera 19 agrees. |
| Bedroom, cameras 3 and 4 | Behind the north / west wall by 7–19 cm. | The two calibrations (2026-02, shot_003) disagree on these two cameras by 16–17 cm (elsewhere by 2–8 cm), so this is calibration uncertainty. The bedroom is linked to the rest of the rig only through the door. The splat puts the north wall where the model has it. |

**Why it was missed before:** the cleaned splat `byt_cely_clean2_hloc_dan4.ply` contains artificial wall-fill gaussians placed on the model walls, so checking walls against it confirmed the model. Check against the raw splat `byt_cely_clean2_hloc.ply` or the rig frames instead (`scripts/check_wall_profiles.py`, `scripts/check_project_walls.py`).

### To do

- [ ] **Measure on site:**
  - living room length from the south wall to the bedroom wall (model ~6.97 m, expected ~7.24 m);
  - bathroom width (model 2.34 m, expected ~2.5 m);
  - the south end of the entrance hall;
  - the pillar's distance from the west wall and the wardrobe.
- [ ] **Edit the model:**
  - the room polygons and the pillar box in `scripts/build_clean.py`;
  - the furniture along the changed walls (shelf, desk, pictures, bathroom fittings) in `scripts/bl_detail.py`.
- [ ] **Re-run the pipeline:** model → renders → bake → hybrid splat → viewer, and release it as 1.0.9.
- [ ] **Remove the interim snapping** (`snap`, `PILLAR_FIX` in `scripts/cams_json.py`, and `scripts/bl_snap_cams.py`). Then check that every camera, at its calibrated position, hangs 5–15 cm in front of its wall.
- [ ] **Optionally re-check** the calibration of bedroom cameras 3 and 4.
