"""Turn the panel-frame .blend into the Captury-frame one: only the root empty's matrix changes."""
import bpy, sys
from mathutils import Matrix
argv = sys.argv[sys.argv.index("--") + 1:]
exec(open("/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/rig_xf.py").read())
root = bpy.data.objects["byt_v_mocap_ramci"]
root.matrix_world = Matrix(blender_matrix_captury_fbx())
root["popis"] = "Byt tam, kam Blender importuje FBX z Captury (kalibrace shot_003 / Dataset_klekz)."
bpy.ops.wm.save_as_mainfile(filepath=argv[0], copy=True); print("SAVED", argv[0], flush=True)
