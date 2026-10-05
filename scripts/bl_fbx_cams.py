import bpy, sys, json
argv = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=argv[0])
cams = {o.name: list(o.matrix_world.translation) for o in bpy.context.scene.objects if o.type == "CAMERA"}
print("CAMS", json.dumps(cams), flush=True)
