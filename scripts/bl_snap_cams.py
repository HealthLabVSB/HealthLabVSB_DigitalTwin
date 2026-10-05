"""Move the rig cameras in a .blend to the positions shown in the viewer (snapped in front of the model walls, see
TODO.md). The calibrated centre is kept as the custom property "calibrated_position" (model frame, Blender axes).
Usage: Blender -b IN.blend -P bl_snap_cams.py -- RIG.json OUT.blend"""
import bpy, json, re, sys
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
cams = {c["i"]: c for c in json.load(open(argv[0]))["model_cams"]}
bl = lambda p: Vector((p[0], -p[2], p[1]))                    # web model frame -> Blender model frame
n = 0
for o in bpy.data.objects:
    m = re.match(r"^(cam|kamera)_(\d\d)_", o.name)
    if o.type != "CAMERA" or not m: continue
    c = cams[int(m.group(2))]
    o.matrix_basis.translation = bl(c["p"])                   # model frame (under flat_in_mocap_frame in the mocap files)
    o["calibrated_position"] = list(bl(c["p_calib"])); o["moved_cm"] = c["moved_cm"]; n += 1
print("SNAPPED", n, flush=True)
bpy.ops.wm.save_as_mainfile(filepath=argv[1], copy=True); print("SAVED", argv[1], flush=True)
