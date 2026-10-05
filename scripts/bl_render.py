"""Photoreal pass in Blender: physical materials, bevels, plants, curtains, daylight + Cycles renders.
usage: Blender -b -P bl_render.py -- MODEL.glb OUTDIR [quick] [views=a,b,...]"""
import bpy, math, sys, random
from mathutils import Vector, Matrix
import bmesh

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = argv[0], argv[1]
QUICK = "quick" in argv
BAKE_MODE = "bake" in argv
FINAL = "final" in argv
VIEWS = next((a.split("=")[1].split(",") for a in argv if a.startswith("views=")), None)
random.seed(3)
S_M = 1.1711                                   # metres per model unit (same as bl_detail.S)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
objs = [o for o in bpy.data.objects if o.type == "MESH"]


def principled(o):
    if not o.data.materials: return None, None
    m = o.data.materials[0]
    if m is None or not m.use_nodes: return m, None
    return m, next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def set_(p, **kw):
    for k, v in kw.items():
        if k in p.inputs: p.inputs[k].default_value = v


def bevel(o, w, seg=3):
    md = o.modifiers.new("bevel", "BEVEL"); md.width = w; md.segments = seg; md.limit_method = "ANGLE"


def bump_from(m, p, strength, scale=None, image=None):
    nt = m.node_tree; b = nt.nodes.new("ShaderNodeBump"); b.inputs["Strength"].default_value = strength
    if image is not None:
        nt.links.new(image.outputs["Color"], b.inputs["Height"])
    else:
        nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = scale; nz.inputs["Detail"].default_value = 8
        nt.links.new(nz.outputs["Fac"], b.inputs["Height"])
    nt.links.new(b.outputs["Normal"], p.inputs["Normal"])


def glass_mat(name, tint=(0.95, 0.97, 0.98)):
    """Glass that lets sun shadows through (transparent for shadow rays)."""
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); mix = nt.nodes.new("ShaderNodeMixShader")
    g = nt.nodes.new("ShaderNodeBsdfGlass"); g.inputs["IOR"].default_value = 1.45; g.inputs["Roughness"].default_value = 0.0
    g.inputs["Color"].default_value = (*tint, 1)
    t = nt.nodes.new("ShaderNodeBsdfTransparent"); lp = nt.nodes.new("ShaderNodeLightPath")
    nt.links.new(lp.outputs["Is Shadow Ray"], mix.inputs["Fac"]); nt.links.new(g.outputs[0], mix.inputs[1])
    nt.links.new(t.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


GLASS = glass_mat("sklo")
WHITE_PIECES = ("konf_stolek", "jidelni_stul", "zidle", "psaci_stul", "regal_prihradky", "botnik", "nocni_stolek",
                "satnik", "tv_stolek", "pracovni_stul", "postel", "celo_postele", "vesak", "obraz", "kos_na_pradlo")
FABRIC = ("sedacka", "deka", "kancelarska_zidle", "matrace", "prikryvka", "polstar")
plants = []
for o in objs:
    n = o.name; m, p = principled(o)
    if p is None: continue
    col = tuple(p.inputs["Base Color"].default_value)[:3]
    tex = next((x for x in m.node_tree.nodes if x.type == "TEX_IMAGE"), None)
    if n.startswith("zed_telo") or n.startswith(("osteni", "nadprazi", "sloup", "parapet")):
        set_(p, Roughness=0.9); bevel(o, 0.004, 1)
    elif n.startswith("zed_koupelna"):
        set_(p, Roughness=0.12); set_(p, **{"Coat Weight": 0.3})
    elif n.startswith("zed_"):
        set_(p, Roughness=0.92); bump_from(m, p, 0.02, scale=600)
        if tex is not None and not getattr(m, "_paint_done", False):           # faint tonal drift of real paint
            nt_ = m.node_tree; nz_ = nt_.nodes.new("ShaderNodeTexNoise"); nz_.inputs["Scale"].default_value = 1.6; nz_.inputs["Detail"].default_value = 3
            mr_ = nt_.nodes.new("ShaderNodeMapRange"); mr_.inputs["To Min"].default_value = 0.975; mr_.inputs["To Max"].default_value = 1.02
            gc_ = nt_.nodes.new("ShaderNodeTexCoord"); nt_.links.new(gc_.outputs["Object"], nz_.inputs["Vector"])
            nt_.links.new(nz_.outputs["Fac"], mr_.inputs["Value"])
            mx_ = nt_.nodes.new("ShaderNodeMixRGB"); mx_.blend_type = "MULTIPLY"; mx_.inputs["Fac"].default_value = 1.0
            nt_.links.new(tex.outputs["Color"], mx_.inputs[1]); nt_.links.new(mr_.outputs[0], mx_.inputs[2]); nt_.links.new(mx_.outputs[0], p.inputs["Base Color"])
    elif n.startswith("podlaha_koupelna"):
        set_(p, Roughness=0.18)
    elif n.startswith("podlaha_"):
        set_(p, Roughness=0.45); set_(p, **{"Coat Weight": 0.25, "Coat Roughness": 0.15})
        if tex: bump_from(m, p, 0.06, image=tex)
    elif n.startswith("strop_"):
        set_(p, Roughness=0.95)
    elif n.startswith(("sklo_okno", "sprchova_stena")) or (n.split("_")[0] == "regal" and not n.startswith("regal_prihradky") and col[2] > 0.75):
        o.data.materials[0] = GLASS
    elif n.startswith(("ram_okna", "zarubne")):
        set_(p, Metallic=0.6, Roughness=0.35)
    elif n.startswith(("trouba", "varna_deska", "televize", "monitor")):
        set_(p, Roughness=0.06, **{"Coat Weight": 1.0})
    elif n.startswith("drez") or (n.split("_")[0] == "regal" and not n.startswith("regal_prihradky")):
        set_(p, Metallic=1.0, Roughness=0.25)
    elif n.startswith("kuchyn_deska"):
        set_(p, Roughness=0.35); bevel(o, 0.004, 2)
        nt = m.node_tree; w = nt.nodes.new("ShaderNodeTexWave"); w.inputs["Scale"].default_value = 2.0
        w.inputs["Distortion"].default_value = 6; w.inputs["Detail"].default_value = 6; w.bands_direction = "Y"
        ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.color_ramp.elements[0].color = (0.42, 0.26, 0.13, 1)
        ramp.color_ramp.elements[1].color = (0.62, 0.42, 0.22, 1)
        nt.links.new(w.outputs["Fac"], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    elif n.startswith("kuchyn"):
        if sum(col) / 3 < 0.75: set_(p, Metallic=1.0, Roughness=0.25)          # handles / seams
        else: set_(p, Roughness=0.2, **{"Coat Weight": 0.5}); bevel(o, 0.003, 2)
    elif n.startswith(("wc", "umyvadlo", "splachovani")):
        set_(p, Roughness=0.06, **{"Coat Weight": 1.0}); bevel(o, 0.02, 4)
    elif n.startswith("zrcadlo"):
        set_(p, Metallic=1.0, Roughness=0.02, **{"Base Color": (0.9, 0.9, 0.9, 1)})
    elif n.startswith("kvetinac"):
        set_(p, Roughness=0.35)
    elif n.startswith("kytka"):
        plants.append(o)
    elif n.startswith(FABRIC):
        set_(p, Roughness=1.0, **{"Sheen Weight": 0.7, "Sheen Roughness": 0.4})
        bevel(o, 0.035 if n.startswith(("sedacka", "matrace", "polstar")) else 0.015, 4)
        bump_from(m, p, 0.15, scale=900)
    elif n.startswith(WHITE_PIECES):
        set_(p, Roughness=0.3); bevel(o, 0.006, 2)

exec(open("/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad/bl_detail.py").read())

# ---- plants: replace the placeholder balls with real foliage (tall ficus by the TV wall, bushes elsewhere)
def leaf_material(name, col):
    m = bpy.data.materials.new(name); m.use_nodes = True; pp = m.node_tree.nodes["Principled BSDF"]
    set_(pp, **{"Base Color": (*col, 1), "Roughness": 0.4, "Subsurface Weight": 0.15, "Subsurface Radius": (0.1, 0.3, 0.05),
                "Coat Weight": 0.3}); return m
LEAVES = [leaf_material("list_tmavy", (0.035, 0.12, 0.025)), leaf_material("list_svetly", (0.07, 0.20, 0.04))]
TRUNK = bpy.data.materials.new("kmen"); TRUNK.use_nodes = True; set_(TRUNK.node_tree.nodes["Principled BSDF"], **{"Base Color": (0.12, 0.08, 0.05, 1), "Roughness": 0.8})
SOIL = bpy.data.materials.new("hlina"); SOIL.use_nodes = True; set_(SOIL.node_tree.nodes["Principled BSDF"], **{"Base Color": (0.04, 0.03, 0.02, 1), "Roughness": 1.0})


def add_leaf(verts, faces, mats, base, d, length, width, droop):
    d = d.normalized(); side = d.cross(Vector((0, 0, 1)))
    side = side.normalized() if side.length > 1e-3 else Vector((1, 0, 0)); up = side.cross(d).normalized()
    secs = []
    for k in range(7):
        t = k / 6; pos = base + d * length * t - up * droop * length * t * t
        w = width * math.sin(math.pi * min(t, 0.97)) ** 0.75 if k < 6 else 0.0
        secs.append((pos - side * w + up * 0.0, pos + up * 0.12 * w, pos + side * w))
    i0_ = len(verts)
    for l, c, r in secs: verts += [tuple(l), tuple(c), tuple(r)]
    mi = random.randrange(2)
    for k in range(6):
        a = i0_ + 3 * k; b = a + 3
        faces += [(a, a + 1, b + 1, b), (a + 1, a + 2, b + 2, b + 1)]; mats += [mi, mi]


for o in plants:
    c = o.matrix_world @ (sum((Vector(b) for b in o.bound_box), Vector()) / 8)
    r = max(o.dimensions) / 2
    bpy.data.objects.remove(o, do_unlink=True)
    pots = [q for q in bpy.data.objects if q.name.startswith("kvetinac") and (Vector(q.matrix_world.translation.xy) if False else True)]
    def _pc(q): return q.matrix_world @ (sum((Vector(b) for b in q.bound_box), Vector()) / 8)
    near = min(pots, key=lambda q: (Vector((_pc(q).x, _pc(q).y)) - Vector((c.x, c.y))).length)
    pot_top = max((near.matrix_world @ Vector(b)).z for b in near.bound_box)
    verts, faces, mats = [], [], []
    if r > 0.25 and c.y < -2.5:                                          # ficus, ~1.65 m (splat, by the TV wall)
        top = Vector((c.x + 0.03, c.y - 0.02, 1.55)); trunk = [Vector((c.x, c.y, pot_top)), Vector((c.x - 0.02, c.y + 0.03, 0.9)), top]
        cen, rad = Vector((c.x, c.y, 1.12)), Vector((0.36, 0.36, 0.52)); n, L0, W0, dr = 520, 0.085, 0.032, 0.35
    else:                                                                 # bushy plant
        trunk = [Vector((c.x, c.y, pot_top)), Vector((c.x, c.y, pot_top + r * 0.6))]
        cen, rad = Vector((c.x, c.y, pot_top + r * 1.1)), Vector((r, r, r * 1.1)); n, L0, W0, dr = int(120 * r / 0.3) + 30, r * 0.55, r * 0.17, 0.45
    for k in range(n):
        u = Vector((random.gauss(0, 1), random.gauss(0, 1), random.gauss(0, 1))).normalized()
        if r > 0.25 and c.y < -2.5:
            base = cen + Vector((u.x * rad.x, u.y * rad.y, u.z * rad.z)) * random.uniform(0.55, 1.0) ** 0.5
            d = (u + Vector((random.uniform(-.6, .6), random.uniform(-.6, .6), 0.2))); length = L0 * random.uniform(0.8, 1.2)
        else:
            base = Vector((c.x, c.y, pot_top + random.uniform(0.02, r * 0.5))); u.z = abs(u.z) * 0.9 + 0.25
            d = u; length = L0 * random.uniform(0.7, 1.3)
        add_leaf(verts, faces, mats, base, d, length, W0 * random.uniform(0.8, 1.2), dr * random.uniform(0.6, 1.3))
    me = bpy.data.meshes.new("kytka_listy"); me.from_pydata(verts, [], faces); me.update()
    for m in LEAVES: me.materials.append(m)
    for poly, mi in zip(me.polygons, mats): poly.material_index = mi; poly.use_smooth = True
    ob = bpy.data.objects.new("kytka_listy", me); bpy.context.collection.objects.link(ob)
    ob.modifiers.new("solid", "SOLIDIFY").thickness = 0.0015
    cu = bpy.data.curves.new("kytka_kmen", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.012 if r > 0.25 else 0.005; cu.use_fill_caps = True
    sp = cu.splines.new("POLY"); sp.points.add(len(trunk) - 1)
    for i, q in enumerate(trunk): sp.points[i].co = (*q, 1)
    tob = bpy.data.objects.new("kytka_kmen", cu); bpy.context.collection.objects.link(tob); cu.materials.append(TRUNK)
    soil = bpy.data.meshes.new("hlina"); prad = 0.15 if r > 0.25 else (0.095 if c.z < 0.9 else 0.065)
    soil.from_pydata([(c.x + prad * math.cos(2 * math.pi * k / 24), c.y + prad * math.sin(2 * math.pi * k / 24), pot_top - 0.025) for k in range(24)], [], [tuple(range(24))])
    sob = bpy.data.objects.new("kytka_hlina", soil); bpy.context.collection.objects.link(sob); soil.materials.append(SOIL)
vl_ = bpy.context.view_layer
for o_ in vl_.objects: o_.select_set(False)
trunks = [o_ for o_ in bpy.data.objects if o_.name.startswith("kytka_kmen")]
for o_ in trunks: o_.select_set(True)
if trunks: vl_.objects.active = trunks[0]; bpy.ops.object.convert(target="MESH")

# ---- curtains (sheer, with folds) either side of each window, 12 cm in front of the wall
cur_mat = bpy.data.materials.new("zaclona"); cur_mat.use_nodes = True
cp = cur_mat.node_tree.nodes["Principled BSDF"]
set_(cp, **{"Base Color": (0.93, 0.92, 0.9, 1), "Roughness": 1.0, "Transmission Weight": 0.55, "Sheen Weight": 0.5})
# curtain panels (b from, b to) beside the windows on the a = -4.09 wall, kept clear of shelves and bed heads
panels_b = [(b0 * S_M, b1 * S_M) for b0, b1 in [(0.85, 0.52), (-0.48, -0.72), (-2.58, -2.92), (-3.72, -4.05), (4.09, 3.97), (3.01, 2.80)]]   # metres
for b0, b1 in panels_b:
    if True:
        verts, faces = [], []
        nb, nz = 48, 2
        for i in range(nb + 1):
            bb = b0 + (b1 - b0) * i / nb
            dx = 0.025 * math.sin(i / nb * math.pi * 7)
            for zz in (0.03, 2.28 * S_M): verts.append((-4.09 * S_M + 0.09 + dx, bb, zz))
        for i in range(nb): faces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
        me = bpy.data.meshes.new("zaclona"); me.from_pydata(verts, [], faces); me.update()
        ob = bpy.data.objects.new("zaclona", me); bpy.context.collection.objects.link(ob); me.materials.append(cur_mat)

# ---- world, sun, fill lights
world = bpy.data.worlds.new("svet"); bpy.context.scene.world = world; world.use_nodes = True
nt = world.node_tree; nt.nodes.clear()
sky = nt.nodes.new("ShaderNodeTexSky"); sky.sky_type = "NISHITA"; sky.sun_elevation = math.radians(22)
sky.sun_rotation = math.radians(250); sky.sun_disc = False; sky.altitude = 300
bg = nt.nodes.new("ShaderNodeBackground"); bg.inputs["Strength"].default_value = 0.35
wo = nt.nodes.new("ShaderNodeOutputWorld"); nt.links.new(sky.outputs[0], bg.inputs[0]); nt.links.new(bg.outputs[0], wo.inputs[0])
sun = bpy.data.lights.new("slunce", "SUN"); sun.energy = 3.5; sun.angle = math.radians(1.5); sun.color = (1.0, 0.95, 0.88)
so = bpy.data.objects.new("slunce", sun); bpy.context.collection.objects.link(so)
so.rotation_euler = Vector((1.0, 0.35, -0.42)).normalized().to_track_quat("-Z", "Y").to_euler()
ground = bpy.data.meshes.new("teren")                                            # something outside the windows
ground.from_pydata([(-60, -60, -6), (60, -60, -6), (60, 60, -6), (-60, 60, -6)], [], [(0, 1, 2, 3)])
g_ob = bpy.data.objects.new("teren", ground); bpy.context.collection.objects.link(g_ob)
gm = bpy.data.materials.new("teren"); gm.use_nodes = True
set_(gm.node_tree.nodes["Principled BSDF"], **{"Base Color": (0.18, 0.24, 0.12, 1), "Roughness": 1}); ground.materials.append(gm)
gnt = gm.node_tree; gn = gnt.nodes.new("ShaderNodeTexNoise"); gn.inputs["Scale"].default_value = 0.4; gn.inputs["Detail"].default_value = 8
gr = gnt.nodes.new("ShaderNodeValToRGB"); gr.color_ramp.elements[0].color = (0.10, 0.15, 0.05, 1); gr.color_ramp.elements[1].color = (0.30, 0.34, 0.16, 1)
gnt.links.new(gn.outputs["Fac"], gr.inputs["Fac"]); gnt.links.new(gr.outputs["Color"], gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
base_me = bpy.data.meshes.new("podstavec"); base_me.from_pydata([(-60, -60, -0.004), (60, -60, -0.004), (60, 60, -0.004), (-60, 60, -0.004)], [], [(0, 1, 2, 3)])
base_ob = bpy.data.objects.new("podstavec", base_me); bpy.context.collection.objects.link(base_ob)          # light base, top view only
bm_ = bpy.data.materials.new("podstavec"); bm_.use_nodes = True; set_(bm_.node_tree.nodes["Principled BSDF"], **{"Base Color": (0.62, 0.62, 0.62, 1), "Roughness": 0.8})
base_me.materials.append(bm_)
BARK = bpy.data.materials.new("kura"); BARK.use_nodes = True; set_(BARK.node_tree.nodes["Principled BSDF"], **{"Base Color": (0.09, 0.07, 0.05, 1)})
CANOPY = bpy.data.materials.new("koruna"); CANOPY.use_nodes = True; cp_ = CANOPY.node_tree.nodes["Principled BSDF"]
set_(cp_, **{"Base Color": (0.11, 0.17, 0.06, 1), "Roughness": 0.85, "Subsurface Weight": 0.1})
ctn = CANOPY.node_tree; cn1 = ctn.nodes.new("ShaderNodeTexNoise"); cn1.inputs["Scale"].default_value = 3.5; cn1.inputs["Detail"].default_value = 10
cvo = ctn.nodes.new("ShaderNodeTexVoronoi"); cvo.inputs["Scale"].default_value = 9.0                  # leafy clumps
cr_ = ctn.nodes.new("ShaderNodeValToRGB"); cr_.color_ramp.elements[0].color = (0.035, 0.07, 0.02, 1); cr_.color_ramp.elements[1].color = (0.20, 0.28, 0.08, 1)
cmx = ctn.nodes.new("ShaderNodeMath"); cmx.operation = "MULTIPLY"
ctn.links.new(cn1.outputs["Fac"], cmx.inputs[0]); ctn.links.new(cvo.outputs["Distance"], cmx.inputs[1])
cmr = ctn.nodes.new("ShaderNodeMapRange"); cmr.inputs["From Max"].default_value = 0.45; ctn.links.new(cmx.outputs[0], cmr.inputs["Value"])
ctn.links.new(cmr.outputs[0], cr_.inputs["Fac"]); ctn.links.new(cr_.outputs["Color"], cp_.inputs["Base Color"])
cbp = ctn.nodes.new("ShaderNodeBump"); cbp.inputs["Strength"].default_value = 0.8; ctn.links.new(cvo.outputs["Distance"], cbp.inputs["Height"])
ctn.links.new(cbp.outputs["Normal"], cp_.inputs["Normal"])
tex_c = bpy.data.textures.new("koruna_tex", "CLOUDS"); tex_c.noise_scale = 0.5; tex_c.noise_depth = 4
rng_ = random.Random(5)
for k in range(16):                                                         # young trees in the park below the windows
    x, y = rng_.uniform(-48, -16), rng_.uniform(-35, 35); h = rng_.uniform(4.0, 7.0); rr = rng_.uniform(1.4, 2.6)
    bm = bmesh.new()
    for j in range(4):                                                        # a crown made of a few clumps
        ox, oy, oz = (0, 0, 0) if j == 0 else (rng_.uniform(-.6, .6) * rr, rng_.uniform(-.6, .6) * rr, rng_.uniform(-.3, .5) * rr)
        rj = rr * (1.0 if j == 0 else rng_.uniform(0.5, 0.75))
        bmesh.ops.create_icosphere(bm, subdivisions=4, radius=rj,
                                   matrix=Matrix.Translation((x + ox, y + oy, -6 + h + oz)) @ Matrix.Diagonal((1, 1, 1.2, 1)))
    me = bpy.data.meshes.new("strom"); bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new("strom", me); bpy.context.collection.objects.link(ob)
    me.materials.append(CANOPY); dmod = ob.modifiers.new("d", "DISPLACE"); dmod.texture = tex_c; dmod.strength = 0.9
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.25, radius2=0.15, depth=h)
    bmesh.ops.translate(bm, vec=(x, y, -6 + h / 2), verts=bm.verts); me = bpy.data.meshes.new("kmen_s"); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new("strom_kmen", me); bpy.context.collection.objects.link(ob); me.materials.append(BARK)
FAC = bpy.data.materials.new("fasada"); FAC.use_nodes = True; fnt = FAC.node_tree
fb = fnt.nodes.new("ShaderNodeTexBrick"); fb.offset = 0.0
for k_, v_ in {"Scale": 1.0, "Mortar Size": 0.45, "Brick Width": 1.6, "Row Height": 2.9, "Mortar Smooth": 0.0}.items(): fb.inputs[k_].default_value = v_
fb.inputs["Color1"].default_value = (0.10, 0.12, 0.15, 1); fb.inputs["Color2"].default_value = (0.16, 0.18, 0.22, 1); fb.inputs["Mortar"].default_value = (0.62, 0.60, 0.55, 1)
ftc = fnt.nodes.new("ShaderNodeTexCoord"); fsep = fnt.nodes.new("ShaderNodeSeparateXYZ"); fcomb = fnt.nodes.new("ShaderNodeCombineXYZ")
fnt.links.new(ftc.outputs["Object"], fsep.inputs[0]); fnt.links.new(fsep.outputs[1], fcomb.inputs[0]); fnt.links.new(fsep.outputs[2], fcomb.inputs[1])
fnt.links.new(fcomb.outputs[0], fb.inputs["Vector"]); fnt.links.new(fb.outputs["Color"], fnt.nodes["Principled BSDF"].inputs["Base Color"])
for (x0, y0, w, d, h) in [(-170, -110, 14, 60, 34), (-190, 30, 14, 48, 27), (-150, 120, 12, 40, 22), (-230, -20, 16, 60, 45)]:   # distant blocks of flats
    me = bpy.data.meshes.new("panelak"); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    bmesh.ops.transform(bm, matrix=Matrix.Translation((x0, y0 + d / 2, -6 + h / 2)) @ Matrix.Diagonal((w, d, h, 1)), verts=bm.verts)
    bm.to_mesh(me); bm.free(); ob = bpy.data.objects.new("panelak", me); bpy.context.collection.objects.link(ob); me.materials.append(FAC)
for (x, y, kind) in LIGHT_FIX:                                                  # ceiling fixtures from bl_detail
    L = bpy.data.lights.new("panel", "AREA"); L.color = (1.0, 0.93, 0.85)
    if kind == "panel": L.shape = "SQUARE"; L.size = 0.58; L.energy = (30 if (0.79 < x < 2.79 and 1.95 < y < 5.35) else 45) * S_M ** 2
    else: L.shape = "DISK"; L.size = 0.12; L.energy = 30 * S_M ** 2
    ob = bpy.data.objects.new("panel", L); ob.location = (x * S_M, y * S_M, 2.31 * S_M - 0.022); bpy.context.collection.objects.link(ob)
    ob.visible_camera = False; ob.visible_glossy = False                          # the emissive fixture mesh is what you see

# ---- render settings
sc = bpy.context.scene; sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences; prefs.compute_device_type = "METAL"; prefs.get_devices()
for d in prefs.devices: d.use = d.type == "METAL"
sc.cycles.device = "GPU"; sc.cycles.samples = 48 if QUICK else (288 if FINAL else 112); sc.cycles.use_denoising = True
sc.cycles.max_bounces = 10; sc.cycles.caustics_reflective = False; sc.cycles.caustics_refractive = False
sc.cycles.blur_glossy = 1.0
sc.render.resolution_x, sc.render.resolution_y = (960, 540) if QUICK else ((2560, 1440) if FINAL else (1600, 900))
sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Medium High Contrast"; sc.view_settings.exposure = 0.45
if not BAKE_MODE:
    sc.use_nodes = True; cn = sc.node_tree; cn.nodes.clear()
    rl = cn.nodes.new("CompositorNodeRLayers"); gl = cn.nodes.new("CompositorNodeGlare")
    gl.glare_type = "FOG_GLOW"; gl.quality = "HIGH"; gl.threshold = 3.0; gl.mix = -0.85; gl.size = 7    # only real light sources bloom
    ld = cn.nodes.new("CompositorNodeLensdist"); ld.inputs["Dispersion"].default_value = 0.008; ld.use_fit = True
    em = cn.nodes.new("CompositorNodeEllipseMask"); em.mask_width = 1.25; em.mask_height = 1.25
    bl = cn.nodes.new("CompositorNodeBlur"); bl.filter_type = "GAUSS"; bl.use_relative = True; bl.factor_x = 0.25; bl.factor_y = 0.25
    vg = cn.nodes.new("CompositorNodeMixRGB"); vg.blend_type = "MULTIPLY"; vg.inputs["Fac"].default_value = 0.22
    inv = cn.nodes.new("CompositorNodeMixRGB"); inv.blend_type = "MIX"; inv.inputs[1].default_value = (0.35, 0.35, 0.35, 1); inv.inputs[2].default_value = (1, 1, 1, 1)
    out = cn.nodes.new("CompositorNodeComposite")
    cn.links.new(rl.outputs["Image"], gl.inputs["Image"]); cn.links.new(gl.outputs["Image"], ld.inputs["Image"])
    cn.links.new(em.outputs["Mask"], bl.inputs["Image"]); cn.links.new(bl.outputs["Image"], inv.inputs["Fac"])
    cn.links.new(ld.outputs["Image"], vg.inputs[1]); cn.links.new(inv.outputs["Image"], vg.inputs[2]); cn.links.new(vg.outputs["Image"], out.inputs["Image"])
cam_data = bpy.data.cameras.new("kamera"); cam = bpy.data.objects.new("kamera", cam_data)
bpy.context.collection.objects.link(cam); sc.camera = cam
views = {
    "obyvak_okna": ((1.2, -2.3, 1.45), (-4.0, -1.7, 1.15), 17),
    "obyvak_roh": ((-3.75, -4.35, 1.6), (1.0, 0.3, 0.9), 15),
    "kuchyn": ((-2.6, -0.2, 1.5), (2.1, -2.6, 1.0), 19),
    "loznice": ((-1.65, 1.70, 1.55), (-4.0, 4.2, 0.85), 15),
    "loznice_skrin": ((-3.6, 2.0, 1.6), (-0.8, 3.6, 1.15), 16),
    "koupelna": ((2.32, 2.80, 1.6), (0.9, 4.7, 0.9), 14),
    "predsin": ((3.8, 1.1, 1.55), (5.7, 2.7, 1.1), 17),
    "domecek": ((7.5, -9.5, 11.5), (0.2, 0.2, 0.0), 30),
    "dvere_loznice": ((-0.9, -0.6, 1.5), (-1.85, 1.4, 1.25), 18),
    "dvere_koupelna": ((2.80, 0.68, 1.60), (2.15, 3.20, 1.00), 16),
    "koupelna_sprcha": ((1.05, 2.85, 1.62), (2.45, 5.0, 0.95), 14),
    "koupelna_dvere": ((1.35, 5.05, 1.62), (2.45, 2.85, 0.95), 14),
}
BAKE = "bake" in argv                                                          # bl_bake.py takes over the scene
for name, (pos, tgt, lens) in views.items():
    if BAKE or (VIEWS and name not in VIEWS): continue
    for o in bpy.data.objects:
        if o.name.startswith(("strop_", "led_", "bodovka", "teren", "strom", "panelak", "vyustka")): o.hide_render = name == "domecek"
        if o.name.startswith("podstavec"): o.hide_render = name != "domecek"
    pos = Vector((pos[0] * S_M, pos[1] * S_M, pos[2])); tgt = Vector((tgt[0] * S_M, tgt[1] * S_M, tgt[2]))   # plan in units, eye height in metres
    cam.location = pos; cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = lens; cam_data.clip_start = 0.05
    sc.render.filepath = f"{OUT}/render_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", name, flush=True)
if not QUICK and not VIEWS and not BAKE:
    bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/byt_fotorealisticky.blend")
