import bpy, sys, json
argv = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=argv[0])
sc = bpy.context.scene
arms = [o for o in sc.objects if o.type == "ARMATURE"]
out = {"objects": [(o.name, o.type) for o in sc.objects][:12], "frame_range": [sc.frame_start, sc.frame_end], "fps": sc.render.fps}
if arms:
    a = arms[0]; out["arm"] = a.name; out["arm_scale"] = list(a.scale); out["bones"] = [b.name for b in a.pose.bones][:8]
    pts = []
    for f in range(int(sc.frame_start), int(sc.frame_end) + 1, max(1, int((sc.frame_end - sc.frame_start) / 20))):
        sc.frame_set(f); hb = a.pose.bones[0]
        p = a.matrix_world @ hb.head; lo = min((a.matrix_world @ b.head).z for b in a.pose.bones)
        pts.append([f, round(p.x, 3), round(p.y, 3), round(p.z, 3), round(lo, 3)])
    out["root_track_blender"] = pts
print("PROBE", json.dumps(out), flush=True)
