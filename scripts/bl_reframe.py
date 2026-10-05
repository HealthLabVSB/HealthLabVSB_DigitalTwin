"""Re-export a GLB from the model frame into a mocap frame.  Blender -b -P bl_reframe.py -- IN.glb OUT.glb (panel|captury)"""
import bpy, sys
from mathutils import Matrix
argv = sys.argv[sys.argv.index("--") + 1:]
exec(open("/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/rig_xf.py").read())
T = Matrix({"panel": blender_matrix, "captury": blender_matrix_captury, "captury_fbx": blender_matrix_captury_fbx}[argv[2]]())
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=argv[0])
for o in bpy.context.scene.objects:
    if o.parent is None: o.matrix_world = T @ o.matrix_world
bpy.ops.export_scene.gltf(filepath=argv[1], export_format="GLB", export_image_format="JPEG", export_jpeg_quality=92,
                          export_apply=True, export_yup=True, export_cameras=False, export_lights=False)
print("REFRAMED", argv[1], flush=True)
