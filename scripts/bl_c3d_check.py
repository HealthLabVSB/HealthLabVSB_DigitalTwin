"""Proof render: the Captury-frame model with the C3D subject (compare/unknown.c3d) imported as markers.
Blender -b -P bl_c3d_check.py -- MODEL_captury.glb markers.npy OUT.png"""
import bpy, sys, math
import numpy as np
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=argv[0])
P = np.load(argv[1])                                      # (frames, markers, 3) metres, shot_003 frame, Y up
mat = bpy.data.materials.new("marker"); mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1.0, 0.1, 0.05, 1)
mat.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1.0, 0.1, 0.05, 1)
mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 3.0
for f in (250,):
    for p in P[f]:
        if not np.isfinite(p).all() or np.abs(p).sum() == 0: continue
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.03, location=(p[0], -p[2], p[1]))
        bpy.context.object.data.materials.append(mat)
c = np.nanmean(P[250], 0); C = Vector((c[0], -c[2], 0.9))
sc = bpy.context.scene; sc.render.engine = "BLENDER_EEVEE_NEXT"; sc.render.resolution_x, sc.render.resolution_y = 1600, 900
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun); sun.data.energy = 3
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
dg = bpy.context.evaluated_depsgraph_get()
best = None
for k in range(24):                                     # a side view whose line of sight to the subject is free
    a = 2 * math.pi * k / 24; d = Vector((math.cos(a), math.sin(a), 0.25)).normalized()
    hit, loc, *_ = sc.ray_cast(dg, C, d, distance=3.0)
    free = 3.0 if not hit else (loc - C).length
    if best is None or free > best[0]: best = (free, d)
dist = min(best[0] - 0.15, 2.6)
views = {"a_zhora": (C + Vector((0, 0, 3.4)), 16), "b_zboku": (C + best[1] * dist + Vector((0, 0, 0.2)), 18)}
for name, (pos, lens) in views.items():
    cam.location = pos; tgt = C if name != "b_zboku" else Vector((C.x, C.y, 0.7))
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = lens
    sc.render.filepath = argv[2].replace(".png", f"_{name}.png"); bpy.ops.render.render(write_still=True)
print("C3D CHECK DONE free side distance", round(best[0], 2), flush=True)
