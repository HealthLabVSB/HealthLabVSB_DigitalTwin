"""Add the 30 WishCap cameras and the blue 2 x 2 x 0.10 m mat to a finished .blend, as two collections that start hidden
(eye icon off; the mat is also off in renders). In the mocap .blend files they ride on the root empty
"byt_v_mocap_ramci", so they follow the same transform as the flat.
Usage: Blender -b IN.blend -P bl_extras.py -- OUT.blend"""
import bpy, json, math, sys
from mathutils import Matrix, Vector
argv = sys.argv[sys.argv.index("--") + 1:]
HERE = "/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad"
rig = json.load(open(HERE + "/web/rig.json"))
bl = lambda v: Vector((v[0], -v[2], v[1]))            # web model frame (x, y up, z = -b) -> Blender model frame (a, b, h)
root = bpy.data.objects.get("byt_v_mocap_ramci")
COLOR = {"pokojicek": (0.15, 0.39, 0.92, 1), "koupelna": (0.09, 0.64, 0.29, 1), "obyvak": (0.92, 0.35, 0.05, 1), "chodbicka": (0.86, 0.15, 0.15, 1)}

def collection(name):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(c)
    for o in list(c.objects): bpy.data.objects.remove(o, do_unlink=True)
    return c

def place(o, M, coll):
    coll.objects.link(o)
    if root: o.parent = root; o.matrix_parent_inverse = Matrix.Identity(4)
    o.matrix_basis = M

kc = collection("kamery_wishcap")
for c in rig["model_cams"]:
    cd = bpy.data.cameras.new(f"kamera_{c['i']:02d}")
    cd.sensor_fit = "HORIZONTAL"; cd.sensor_width = 4.968
    cd.lens = cd.sensor_width / 2 / math.tan(math.radians(c["fov"][0]) / 2); cd.display_size = 0.25
    cd.clip_start = 0.05; cd.clip_end = 30
    o = bpy.data.objects.new(f"kamera_{c['i']:02d}_{c['room']}", cd)
    r, d, f = bl(c["r"]), bl(c["d"]), bl(c["f"])            # OpenCV right / down / forward; Blender camera: X right, Y up, -Z view
    R = Matrix((r, -d, -f)).transposed()
    o.matrix_basis = Matrix.Translation(bl(c["p"])) @ R.to_4x4()
    place(o, o.matrix_basis.copy(), kc); o.color = COLOR.get(c["room"], (1, 1, 1, 1))
    o["mac"] = rig["calib"]["2026-02"][c["i"]]["mac"]; o["kalibrace"] = "calib/camera-2026-02.calib"

mc = collection("matrace_2x2m")
m = rig["mat"]; x0, x1 = m["x"]; y0, y1 = -m["z"][1], -m["z"][0]; z0, z1 = m["y"]
me = bpy.data.meshes.new("matrace_2x2m")
V = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
F = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
me.from_pydata(V, [], F); me.update()
mat = bpy.data.materials.get("matrace_modra") or bpy.data.materials.new("matrace_modra"); mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF"); bsdf.inputs["Base Color"].default_value = (0.03, 0.16, 0.70, 1); bsdf.inputs["Roughness"].default_value = 0.65
me.materials.append(mat)
o = bpy.data.objects.new("matrace_2x2m", me); place(o, Matrix.Identity(4), mc)
bev = o.modifiers.new("zaobleni", "BEVEL"); bev.width = 0.012; bev.segments = 3
mc.hide_render = True
for name in ("kamery_wishcap", "matrace_2x2m"):
    bpy.context.view_layer.layer_collection.children[name].hide_viewport = True
bpy.context.view_layer.update()
# check: cameras must sit on the calibration centres in whatever frame this file is in
G = lambda p: Vector((p[0], -p[2], p[1]))
dev = []
for c in rig["model_cams"]:
    w = bpy.data.objects[f"kamera_{c['i']:02d}_{c['room']}"].matrix_world.translation
    dev.append(w)
print("CAMS", len(kc.objects), "first", tuple(round(v, 3) for v in dev[0]), "root", root.name if root else None, flush=True)
bpy.ops.wm.save_as_mainfile(filepath=argv[0], copy=True); print("SAVED", argv[0], flush=True)
