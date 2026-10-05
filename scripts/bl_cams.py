"""Render the model from arbitrary cameras (json list of [name, pos, target, lens]) for side-by-side checks with the splat.
Blender -b -P bl_render.py -P bl_cams.py -- MODEL.glb OUTDIR bake cams=FILE.json"""
import bpy, sys, json
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[1]; cams = json.load(open(next(a.split("=", 1)[1] for a in argv if a.startswith("cams="))))
sc = bpy.context.scene; sc.cycles.samples = 40; sc.render.resolution_x, sc.render.resolution_y = 800, 450; sc.use_nodes = False
cam = bpy.data.objects["kamera"]; sc.camera = cam
for o in bpy.data.objects:
    if o.name.startswith("podstavec"): o.hide_render = True
for name, pos, tgt, lens in cams:
    S_ = 1.1711; pos = Vector((pos[0] * S_, pos[1] * S_, pos[2])); tgt = Vector((tgt[0] * S_, tgt[1] * S_, tgt[2]))   # plan in units, height in m
    cam.location = pos; cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens
    sc.render.filepath = f"{OUT}/cam_{name}.png"; bpy.ops.render.render(write_still=True); print("CAM", name, flush=True)
