import bpy, sys
from mathutils import Matrix
argv = sys.argv[sys.argv.index("--") + 1:]
OUTD = argv[1]
bpy.ops.wm.save_as_mainfile(filepath=OUTD + "/byt_fotorealisticky.blend", copy=True); print("SAVED model frame", flush=True)
exec(open("/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/rig_xf.py").read())
T = Matrix(blender_matrix())
root = bpy.data.objects.new("byt_v_mocap_ramci", None); bpy.context.collection.objects.link(root)
for o in list(bpy.data.objects):                     # everything rides on one empty, so the shift is one visible transform
    if o is root or o.parent is not None: continue
    mw = o.matrix_world.copy(); o.parent = root; o.matrix_world = mw
root.matrix_world = T
root["popis"] = "Byt v ramci mocapu WishCap (calib/camera-2026-02.calib). Import FBX/C3D zaznamu s vychozim nastavenim se trefi."
bpy.ops.wm.save_as_mainfile(filepath=OUTD + "/byt_fotorealisticky_mocap.blend", copy=True); print("SAVED rig frame", flush=True)
