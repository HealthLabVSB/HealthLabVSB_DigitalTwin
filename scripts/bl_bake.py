"""Bake the Cycles lighting of the photoreal scene into texture atlases and export an unlit GLB that looks the
same in any web viewer.  Runs after bl_render.py has built the scene:
    Blender -b -P bl_render.py -P bl_bake.py -- MODEL.glb OUTDIR bake [size=4096] [spp=512] [dens=220] [dry]
Per atlas: diffuse lighting (denoised) x albedo + glossy (denoised), then the same AgX view transform as the renders."""
import bpy, bmesh, math, os, sys, time
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[1]
opt = dict(a.split("=", 1) for a in argv if "=" in a)
MAXSIZE, SPP, DENS = int(opt.get("size", 4096)), int(opt.get("spp", 512)), float(opt.get("dens", 220))
DRY = "dry" in argv
sc = bpy.context.scene; vl = bpy.context.view_layer
t_start = time.time()
log = lambda *a: print("BAKE", f"{time.time() - t_start:7.1f}s", *a, flush=True)

# atlas groups: (name, name prefixes, texel density factor); the first match wins, everything else is furniture
GROUPS = [("telo", ("zed_telo",), 0.6), ("zdi", ("zed_", "osteni", "nadprazi", "sloup", "parapet", "ram_okna", "zarubne", "obraz"), 1.0),
          ("podlahy", ("podlaha_",), 1.0), ("stropy", ("strop_", "led_", "bodovka", "vyustka"), 0.7), ("listy", ("kytka_listy",), 1.6),
          ("zaclony", ("zaclona",), 0.8)]
group_of = lambda n: next((g for g, pre, _ in GROUPS if n.startswith(pre)), "nabytek")
factor = dict((g, f) for g, _, f in GROUPS); factor["nabytek"] = 1.3

is_glass = lambda o: any(m is not None and m.name.startswith("sklo") for m in o.data.materials)
OUTSIDE = ("teren", "strom", "panelak", "podstavec")                     # light the bake, never exported
for o in list(sc.objects):
    if o.name.startswith("podstavec"): bpy.data.objects.remove(o, do_unlink=True)
bake_objs = [o for o in sc.objects if o.type == "MESH" and not o.name.startswith(OUTSIDE) and not is_glass(o)]
glass_objs = [o for o in sc.objects if o.type == "MESH" and is_glass(o)]

# ---- 0. bake-only material tweaks: curtains as opaque white cloth (transmission does not bake into a texture),
#         screens / oven / hob with a faint sheen only (a mirror-like coat bakes the whole room onto them)
for o in bake_objs:
    for m in o.data.materials:
        p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m and m.use_nodes else None
        if p is None: continue
        if m.name.startswith("zaclona"):
            p.inputs["Transmission Weight"].default_value = 0.0; p.inputs["Base Color"].default_value = (0.95, 0.94, 0.92, 1)
        if o.name.startswith(("televize", "monitor", "trouba", "varna_deska")):
            p.inputs["Coat Weight"].default_value = 0.0; p.inputs["Roughness"].default_value = 0.3
            p.inputs["Specular IOR Level"].default_value = 0.15

# ---- 1. real geometry: apply the bevels, drop faces nobody can see (bottoms resting on the floor)
bpy.ops.object.select_all(action="DESELECT")
for o in bake_objs: o.select_set(True)
vl.objects.active = bake_objs[0]
bpy.ops.object.make_single_user(object=True, obdata=True)
for o in bake_objs:                                   # leaves: one bake side is enough, rims would only eat atlas space
    if o.name.startswith("kytka_listy"):
        for md in [m for m in o.modifiers if m.type == "SOLIDIFY"]: o.modifiers.remove(md)
bpy.ops.object.convert(target="MESH")
area = {}
for o in bake_objs:
    bm = bmesh.new(); bm.from_mesh(o.data); mw = o.matrix_world; nm = mw.to_3x3().inverted().transposed()
    if not o.name.startswith("podlaha"):
        kill = [f for f in bm.faces if (nm @ f.normal).normalized().z < -0.99 and max((mw @ v.co).z for v in f.verts) < 0.003]
        bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(o.data); bm.free()
    sx = mw.to_scale(); area[o.name] = sum(p.area for p in o.data.polygons) * abs(sx[0] * sx[1] * sx[2]) ** (2 / 3)

# ---- 2. split into atlas chunks so every chunk fits one MAXSIZE^2 texture at its density
chunks = []
for g in [x[0] for x in GROUPS] + ["nabytek"]:
    objs = sorted([o for o in bake_objs if group_of(o.name) == g], key=lambda o: o.name)
    if not objs: continue
    d = DENS * factor[g]; cap = MAXSIZE ** 2 * 0.60 / d ** 2              # m^2 one atlas can hold (60 % packing)
    cur, acc = [], 0.0
    for o in objs:
        if cur and acc + area[o.name] > cap: chunks.append((g, cur, acc, d)); cur, acc = [], 0.0
        cur.append(o); acc += area[o.name]
    if cur: chunks.append((g, cur, acc, d))
for g, objs, acc, d in chunks:
    need = math.sqrt(acc * d * d / 0.60)
    log(f"chunk {g}: {len(objs)} objects, {acc:.1f} m2 -> {need:.0f} px")
if DRY: sys.exit(0)


def uv_nodes_explicit(mat):
    """Image textures read the original UVMap explicitly, so the new 'bake' layer can be the active (target) one."""
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.type == "TEX_IMAGE" and not n.inputs["Vector"].is_linked:
            uv = nt.nodes.new("ShaderNodeUVMap"); uv.uv_map = "UVMap"; nt.links.new(uv.outputs["UV"], n.inputs["Vector"])


def target_node(mat, img):
    nt = mat.node_tree
    n = nt.nodes.get("bake_target") or nt.nodes.new("ShaderNodeTexImage")
    n.name = "bake_target"; n.image = img
    for x in nt.nodes: x.select = False
    n.select = True; nt.nodes.active = n


def denoise(img):
    """OIDN through the compositor (no Render Layers node, so nothing but the image is processed)."""
    sc.use_nodes = True; nt = sc.node_tree; nt.nodes.clear()
    src = nt.nodes.new("CompositorNodeImage"); src.image = img
    dn = nt.nodes.new("CompositorNodeDenoise"); dn.use_hdr = True; dn.prefilter = "ACCURATE"
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(src.outputs["Image"], dn.inputs["Image"]); nt.links.new(dn.outputs[0], comp.inputs[0])
    eng = sc.render.engine; sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x, sc.render.resolution_y = img.size; sc.render.resolution_percentage = 100
    st = sc.render.image_settings; st.file_format = "OPEN_EXR"; st.color_mode = "RGBA"; st.color_depth = "32"
    tmp = os.path.join(OUT, "_denoise_tmp.exr"); sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)            # Render Result pixels are not readable; go through an EXR
    sc.render.engine = eng; sc.use_nodes = False
    v = bpy.data.images.load(tmp); px = pixels(v); bpy.data.images.remove(v); os.remove(tmp)
    return px


def pixels(img):
    px = np.empty(len(img.pixels), np.float32); img.pixels.foreach_get(px)
    return px.reshape(img.size[1], img.size[0], img.channels)[..., :3]


sc.render.bake.margin = 8; sc.render.bake.margin_type = "EXTEND"; sc.render.bake.use_clear = True
sc.render.bake.target = "IMAGE_TEXTURES"; sc.cycles.use_denoising = False
os.makedirs(OUT, exist_ok=True)
baked = []
for ci, (g, objs, acc, d) in enumerate(chunks):
    size = int(min(MAXSIZE, max(512, 256 * math.ceil(math.sqrt(acc * d * d / 0.60) / 256))))   # WebGL2 is fine with NPOT
    name = f"{g}_{ci}"
    # own material copies per chunk (a material shared across atlases would get two bake targets)
    copies = {}
    for o in objs:
        for slot in o.material_slots:
            if slot.material is None: continue
            if slot.material not in copies:
                copies[slot.material] = slot.material.copy(); uv_nodes_explicit(copies[slot.material])
            slot.material = copies[slot.material]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    vl.objects.active = objs[0]
    if len(objs) > 1: bpy.ops.object.join()
    ob = vl.objects.active; ob.name = f"zapec_{name}"
    me = ob.data
    if "UVMap" not in me.uv_layers: me.uv_layers.new(name="UVMap")
    me.uv_layers["UVMap"].active_render = True
    bl = me.uv_layers.new(name="bake"); me.uv_layers.active = bl
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), margin_method="FRACTION", island_margin=(1.5 if g == "listy" else 6) / size,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    log(f"{name}: {len(me.polygons)} faces, atlas {size}px")

    imgs = {k: bpy.data.images.new(f"{k}_{name}", size, size, alpha=False, float_buffer=True) for k in ("light", "alb", "glo", "emit")}
    for k, typ, passes, spp in [("light", "DIFFUSE", {"DIRECT", "INDIRECT"}, SPP), ("alb", "DIFFUSE", {"COLOR"}, 16),
                                ("glo", "GLOSSY", {"DIRECT", "INDIRECT", "COLOR"}, max(32, SPP // 4)), ("emit", "EMIT", set(), 4)]:
        for m in copies.values(): target_node(m, imgs[k])
        sc.cycles.samples = spp
        bpy.ops.object.bake(type=typ, pass_filter=passes, margin=2 if g == "listy" else 8, use_clear=True)
        log(f"{name}: baked {k} ({spp} spp)")
    light, glo, alb, emi = denoise(imgs["light"]), denoise(imgs["glo"]), pixels(imgs["alb"]), pixels(imgs["emit"])
    assert light.shape == alb.shape == glo.shape == emi.shape, (light.shape, alb.shape, glo.shape)
    lin = light * alb + np.maximum(glo, 0) + np.maximum(emi, 0)                 # lamps, LED strip, exit sign glow
    fin = bpy.data.images.new(f"fin_{name}", size, size, alpha=False, float_buffer=True)
    fin.pixels.foreach_set(np.concatenate([lin, np.ones_like(lin[..., :1])], -1).astype(np.float32).ravel())
    path = os.path.join(OUT, f"zapec_{name}.png")
    sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGB"; sc.render.image_settings.color_depth = "8"
    fin.save_render(path, scene=sc)                       # applies AgX + look + exposure, same as the renders
    for im in list(imgs.values()) + [fin]: bpy.data.images.remove(im)
    # unlit export material: the baked image straight into the output (the glTF exporter writes KHR_materials_unlit)
    mat = bpy.data.materials.new(f"zapec_{name}"); mat.use_nodes = True; nt = mat.node_tree; nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = bpy.data.images.load(path); tex.image.colorspace_settings.name = "sRGB"
    uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "bake"; nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    outn = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(tex.outputs["Color"], outn.inputs["Surface"])
    baked.append((ob, mat))
    log(f"{name}: wrote {path}")

# ---- 3. swap to the baked materials, simple transparent glass, drop helpers, export with and without ceiling
for ob, mat in baked:
    ob.data.materials.clear(); ob.data.materials.append(mat)
    for p in ob.data.polygons: p.material_index = 0
    ob.data.uv_layers.remove(ob.data.uv_layers["UVMap"])
gm = bpy.data.materials.new("sklo_export"); gm.use_nodes = True
pb = gm.node_tree.nodes["Principled BSDF"]
pb.inputs["Base Color"].default_value = (0.86, 0.93, 0.97, 1); pb.inputs["Alpha"].default_value = 0.18; pb.inputs["Roughness"].default_value = 0.05
# window panes: unlit bright daylight, mostly opaque, like an exposed-for-the-room photo (the viewer has no sky)
wm = bpy.data.materials.new("sklo_okno_export"); wm.use_nodes = True; nt = wm.node_tree; nt.nodes.clear()
rgb = nt.nodes.new("ShaderNodeRGB"); rgb.outputs[0].default_value = (0.80, 0.88, 0.97, 1)
tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mix = nt.nodes.new("ShaderNodeMixShader"); mix.inputs["Fac"].default_value = 0.88
outn = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(rgb.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], outn.inputs["Surface"])
for o in glass_objs:
    o.data.materials.clear(); o.data.materials.append(wm if o.name.startswith("sklo_okno") else gm)
for o in list(sc.objects):
    if o.type != "MESH" or o.name.startswith(OUTSIDE): bpy.data.objects.remove(o, do_unlink=True)
kw = dict(export_format="GLB", export_image_format="JPEG", export_jpeg_quality=92, export_apply=True, export_yup=True,
          use_selection=False, export_cameras=False, export_lights=False)
exec(open("/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/rig_xf.py").read())
from mathutils import Matrix
T_RIG = Matrix(blender_matrix())
def to_frame(Mx):
    for o in sc.objects: o.matrix_world = Mx @ o.matrix_world
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "byt_zapeceny.glb"), **kw)
log("exported byt_zapeceny.glb (model frame, metres)")
to_frame(T_RIG)                                       # the rig frame of the mocap takes (camera-2026-02.calib)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "byt_zapeceny_mocap.glb"), **kw)
log("exported byt_zapeceny_mocap.glb (rig frame)")
for o in list(sc.objects):
    if o.name.startswith("zapec_stropy"): bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "byt_zapeceny_bez_stropu_mocap.glb"), **kw)
log("exported byt_zapeceny_bez_stropu_mocap.glb (rig frame)")
to_frame(T_RIG.inverted())
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "byt_zapeceny_bez_stropu.glb"), **kw)
log("exported byt_zapeceny_bez_stropu.glb (model frame)")
