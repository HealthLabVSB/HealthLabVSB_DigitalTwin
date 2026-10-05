import bpy, sys, json
from mathutils import Matrix
argv = sys.argv[sys.argv.index("--") + 1:]
exec(open("/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/rig_xf.py").read())
Ti = Matrix(blender_matrix_captury_fbx()).inverted(); S = S_MODEL
out = {}
for f in argv:
    bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=f)
    sc = bpy.context.scene; arm = next(o for o in sc.objects if o.type == "ARMATURE"); pts = []
    for fr in range(int(sc.frame_start) + 12, int(sc.frame_end) + 1, 3):
        sc.frame_set(fr)
        for b in arm.pose.bones:
            p = Ti @ (arm.matrix_world @ b.head); pts.append((p.x / S, p.y / S, p.z))
    out[f.split("/")[-2]] = pts
json.dump(out, open("/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/klekz_pts.json", "w"))
print("EXTENT done", len(out), flush=True)
