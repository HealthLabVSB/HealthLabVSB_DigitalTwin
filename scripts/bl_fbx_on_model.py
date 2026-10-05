"""Import a mocap FBX next to a model GLB (both as Blender imports them) and report where the skeleton is in the model.
Blender -b -P bl_fbx_on_model.py -- MODEL.glb TAKE.fbx MATRIX_NAME [render.png]"""
import bpy, sys, json
from mathutils import Matrix, Vector
argv = sys.argv[sys.argv.index("--") + 1:]
exec(open("/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/rig_xf.py").read())
T = Matrix({"panel": blender_matrix, "captury_fbx": blender_matrix_captury_fbx}[argv[2]]()); Ti = T.inverted()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=argv[0])
bpy.ops.import_scene.fbx(filepath=argv[1])
sc = bpy.context.scene; arm = next(o for o in sc.objects if o.type == "ARMATURE")
rooms = json.load(open("/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/lights.json"))["rooms"]
def room_of(a, b):
    for n, P in rooms.items():
        c = False
        for i in range(len(P)):
            (x0, y0), (x1, y1) = P[i], P[(i + 1) % len(P)]
            if (y0 > b) != (y1 > b) and a < x0 + (b - y0) * (x1 - x0) / (y1 - y0): c = not c
        if c: return n
    return "mimo byt"
S = S_MODEL; rows = []
for f in range(int(sc.frame_start) + 12, int(sc.frame_end) + 1, max(1, int((sc.frame_end - sc.frame_start) / 12))):
    sc.frame_set(f)
    pts = [Ti @ (arm.matrix_world @ b.head) for b in arm.pose.bones]            # back to model metres (a, b, h)
    hip = pts[0]; low = min(p.z for p in pts)
    rows.append((f, round(hip.x / S, 2), round(hip.y / S, 2), round(low, 3), room_of(hip.x / S, hip.y / S)))
for r in rows: print("TAKE", r, flush=True)
if len(argv) > 3:
    sc.frame_set(int((sc.frame_start + sc.frame_end) / 2))
    hip = arm.matrix_world @ arm.pose.bones[0].head
    sc.render.engine = "BLENDER_EEVEE_NEXT"; sc.render.resolution_x, sc.render.resolution_y = 1400, 900
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
    cam.location = hip + Vector((0, 0, 4.2)); cam.rotation_euler = (0, 0, 0); cam.data.lens = 14
    sc.render.filepath = argv[3]; bpy.ops.render.render(write_still=True)
