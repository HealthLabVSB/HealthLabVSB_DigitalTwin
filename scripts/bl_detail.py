"""Detail pass for the photoreal scene, exec'd by bl_render.py after the base materials are set.
Blender axes here: X = a, Y = b, Z = h (metres, wall-aligned frame of build_clean.py).
The bathroom is rebuilt after the 2021 tour photo (scene 32605745); the rest gets doors, LED panels, softer
furniture, kitchen and desk props.  Every new object is a real mesh at the end, so bl_bake.py can bake it."""
import bpy, bmesh, math, random, json, os
from mathutils import Vector, Matrix

rnd = random.Random(11)
HERE = "/private/tmp/claude-501/-Users-dan-WishCaptury/a6354438-d500-490d-9fcf-d1a74f5f98d2/scratchpad"
D_ = bpy.data
COL = bpy.context.collection


# ------------------------------------------------------------------ helpers
def srgb(*c):
    return tuple(((v / 255 + 0.055) / 1.055) ** 2.4 if v / 255 > 0.04045 else v / 255 / 12.92 for v in c)


def pmat(name, base, rough=0.5, metal=0.0, coat=0.0, sheen=0.0, transm=0.0, emit=None, emit_str=0.0, alpha=1.0):
    m = D_.materials.new(name); m.use_nodes = True; p = m.node_tree.nodes["Principled BSDF"]
    set_(p, **{"Base Color": (*base, 1), "Roughness": rough, "Metallic": metal, "Coat Weight": coat,
               "Sheen Weight": sheen, "Transmission Weight": transm, "Alpha": alpha})
    if emit is not None: set_(p, **{"Emission Color": (*emit, 1), "Emission Strength": emit_str})
    return m


# ---- metric conversion (iterace 06). The splat/model unit is S metres (rig-camera fit, door 0.90x2.10, worktop 0.91).
# Everything is authored in model units as before; at the end every object gets one of these placements:
#   SC  (default) scale x S about the origin: architecture and anything measured on the splat
#   SXY scale x S in plan only: footprint measured on the splat, heights given in real metres
#   FX(a, b, zref) real-size object: kept as is, moved so its anchor (a, b, zref in units) lands where it belongs
#   MET authored directly in metres
S = 1.1711                                    # metres per unit (rig triangulation, iterace 07)
SO = 1.2779                                   # old scale: constants written as 'old metres' below
KO = S / SO
STUL2 = "stul2" in argv                       # dining set in position 2 (by the south window)
D2 = (-3.0 - 0.42 / SO, -3.62 + 4.40 / SO)       # its shift in units
H_U = 2.31
MODE = {}
_CTX = [("SC",)]
def begin(*mode): _CTX.append(mode)
def end(): _CTX.pop()
def link(ob):
    COL.objects.link(ob); MODE[ob.name] = _CTX[-1]; return ob


def placement(mode):
    if mode[0] == "SC": return Matrix.Diagonal((S, S, S, 1))
    if mode[0] == "SXY": return Matrix.Diagonal((S, S, 1, 1))
    if mode[0] == "MET": return Matrix.Identity(4)
    if mode[0] == "MXY": return Matrix.Diagonal((KO, KO, 1, 1))              # old-metre plan, real heights
    _, a, b, z = mode
    return Matrix.Translation(((S - 1) * a, (S - 1) * b, (S - 1) * z))


def from_bm(name, bm, mat, smooth=False):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = D_.meshes.new(name); bm.to_mesh(me); bm.free()
    if smooth:
        for p in me.polygons: p.use_smooth = True
    ob = D_.objects.new(name, me); me.materials.append(mat); return link(ob)


def cube(name, x0, x1, y0, y1, z0, z1, mat, bev=0.0, seg=3, sub=0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) @
                          Matrix.Diagonal((abs(x1 - x0), abs(y1 - y0), abs(z1 - z0), 1)))
    ob = from_bm(name, bm, mat, smooth=bool(sub))
    if bev: bevel(ob, bev, seg)
    if sub:
        md = ob.modifiers.new("sub", "SUBSURF"); md.levels = md.render_levels = sub
    return ob


def cyl(name, x, y, z0, z1, r, mat, seg=32, axis="Z", ry=None):
    """Cylinder from z0 to z1 along axis (start/end are coordinates along that axis; x, y the other two)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r, depth=abs(z1 - z0))
    if ry: bmesh.ops.scale(bm, vec=(1, ry / r, 1), verts=bm.verts)
    rot = {"Z": Matrix.Identity(4), "X": Matrix.Rotation(math.pi / 2, 4, "Y"), "Y": Matrix.Rotation(math.pi / 2, 4, "X")}[axis]
    c = (z0 + z1) / 2
    pos = {"Z": (x, y, c), "X": (c, x, y), "Y": (x, c, y)}[axis]
    bmesh.ops.transform(bm, matrix=Matrix.Translation(pos) @ rot, verts=bm.verts)
    return from_bm(name, bm, mat, smooth=True)


def prism(name, outline, z0, z1, mat, bev=0.0, seg=3):
    """Closed prism from a CCW (x, y) outline."""
    bm = bmesh.new()
    lo = [bm.verts.new((x, y, z0)) for x, y in outline]; hi = [bm.verts.new((x, y, z1)) for x, y in outline]
    bm.faces.new(lo[::-1]); bm.faces.new(hi)
    n = len(outline)
    for i in range(n):
        bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]))
    ob = from_bm(name, bm, mat)
    if bev: bevel(ob, bev, seg)
    return ob


def arc_pts(cx, cy, rx, ry, a0, a1, n):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * k / n)), cy + ry * math.sin(math.radians(a0 + (a1 - a0) * k / n)))
            for k in range(n + 1)]


def fillet(pts, r, n=6):
    P = [Vector(p) for p in pts]; out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        d1, d2 = (b - a).normalized(), (c - b).normalized()
        ang = d1.angle(d2, 0.0)
        if ang < 1e-3: out.append(b); continue
        t = min(r * math.tan(ang / 2), (b - a).length * 0.49, (c - b).length * 0.49)
        p1, p2 = b - d1 * t, b + d2 * t
        out += [(1 - s) ** 2 * p1 + 2 * (1 - s) * s * b + s * s * p2 for s in (k / n for k in range(n + 1))]
    out.append(P[-1]); return out


def ray_outline(poly, c, th):
    """Where a ray from c at angle th leaves the convex outline poly."""
    d = Vector((math.cos(th), math.sin(th))); best = None
    for i in range(len(poly)):
        p, q = Vector(poly[i]), Vector(poly[(i + 1) % len(poly)]); e = q - p
        den = d.x * e.y - d.y * e.x
        if abs(den) < 1e-12: continue
        w = p - Vector(c); t = (w.x * e.y - w.y * e.x) / den; u = (w.x * d.y - w.y * d.x) / den
        if t > 0 and -1e-9 <= u <= 1 + 1e-9 and (best is None or t < best): best = t
    return Vector(c) + d * best


def bowl_body(name, outline, c, rx, ry, z0, z1, depth, mat, n=64, nring=10):
    """Solid with a flat top whose elliptical opening (centre c, radii rx, ry) drops into a half-ellipsoid bowl."""
    bm = bmesh.new(); th = [2 * math.pi * k / n for k in range(n)]
    outer = [ray_outline(outline, c, t) for t in th]
    lo = [bm.verts.new((p.x, p.y, z0)) for p in outer]; hi = [bm.verts.new((p.x, p.y, z1)) for p in outer]
    rings = [[bm.verts.new((c[0] + rx * math.cos(a) * math.cos(t), c[1] + ry * math.cos(a) * math.sin(t), z1 - depth * math.sin(a))) for t in th]
             for a in (math.pi / 2 * k / nring for k in range(nring))]
    bottom = bm.verts.new((c[0], c[1], z1 - depth))
    bm.faces.new(lo[::-1])
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i])); bm.faces.new((hi[i], hi[j], rings[0][j], rings[0][i]))
        for k in range(nring - 1): bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
        bm.faces.new((rings[-1][i], rings[-1][j], bottom))
    ob = from_bm(name, bm, mat, smooth=False)
    for p in ob.data.polygons: p.use_smooth = p.center.z < z1 - 1e-4 and abs(p.normal.z) < 0.999 and p.center.z > z0 + 1e-4
    return ob


def ring_solid(name, c, orx, ory, irx, iry, z0, z1, mat, n=64, shift=(0.0, 0.0)):
    bm = bmesh.new(); th = [2 * math.pi * k / n for k in range(n)]
    O = [(c[0] + orx * math.cos(t), c[1] + ory * math.sin(t)) for t in th]
    I = [(c[0] + shift[0] + irx * math.cos(t), c[1] + shift[1] + iry * math.sin(t)) for t in th]
    ol, oh = [bm.verts.new((x, y, z0)) for x, y in O], [bm.verts.new((x, y, z1)) for x, y in O]
    il, ih = [bm.verts.new((x, y, z0)) for x, y in I], [bm.verts.new((x, y, z1)) for x, y in I]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((ol[i], ol[j], oh[j], oh[i])); bm.faces.new((ih[i], ih[j], il[j], il[i]))
        bm.faces.new((oh[i], oh[j], ih[j], ih[i])); bm.faces.new((il[i], il[j], ol[j], ol[i]))
    return from_bm(name, bm, mat, smooth=True)


CURVES = []
def tube(name, pts, r, mat, rr=0.05, closed=False):
    pts = fillet(pts, rr) if rr else [Vector(p) for p in pts]
    cu = D_.curves.new(name, "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = r; cu.bevel_resolution = 3
    cu.use_fill_caps = True; sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts): sp.points[i].co = (*p, 1)
    sp.use_cyclic_u = closed
    ob = D_.objects.new(name, cu); cu.materials.append(mat); link(ob); CURVES.append(ob); return ob


def grid(name, origin, u, v, nu, nv, disp, mat, thick=0.0, sub=1, normal_hint=None):
    """Cloth-like sheet: origin + s*u + t*v, displaced by disp(s, t) -> Vector."""
    o, u, v = Vector(origin), Vector(u), Vector(v)
    bm = bmesh.new(); V = [[bm.verts.new(o + u * (i / nu) + v * (j / nv) + disp(i / nu, j / nv)) for j in range(nv + 1)] for i in range(nu + 1)]
    for i in range(nu):
        for j in range(nv): bm.faces.new((V[i][j], V[i + 1][j], V[i + 1][j + 1], V[i][j + 1]))
    if normal_hint is not None:
        bm.normal_update()
        if sum((f.normal.dot(Vector(normal_hint)) for f in bm.faces)) < 0:
            for f in bm.faces: f.normal_flip()
    me = D_.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    ob = link(D_.objects.new(name, me)); me.materials.append(mat)
    if thick:
        md = ob.modifiers.new("solid", "SOLIDIFY"); md.thickness = thick; md.offset = 0
    if sub:
        md = ob.modifiers.new("sub", "SUBSURF"); md.levels = md.render_levels = sub
    return ob


def apply_all(ob):
    vl = bpy.context.view_layer
    for o in vl.objects: o.select_set(False)
    ob.select_set(True); vl.objects.active = ob
    for md in list(ob.modifiers): bpy.ops.object.modifier_apply(modifier=md.name)


def boolean_cut(ob, cutter):
    md = ob.modifiers.new("cut", "BOOLEAN"); md.object = cutter; md.operation = "DIFFERENCE"; md.solver = "EXACT"
    vl = bpy.context.view_layer
    for o in vl.objects: o.select_set(False)
    ob.select_set(True); vl.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="cut")
    D_.objects.remove(cutter, do_unlink=True)


def remove(prefixes):
    for o in list(D_.objects):
        if o.type == "MESH" and o.name.startswith(prefixes): D_.objects.remove(o, do_unlink=True)


def wood_mat(name, light, dark, scale=3.0, rough=0.45):
    """Oak veneer: long fibres along Z (doors) from a stretched noise, fine pores, slow tone drift."""
    m = pmat(name, light, rough); nt = m.node_tree; p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (14.0, 14.0, 0.5)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    fib = nt.nodes.new("ShaderNodeTexNoise"); fib.inputs["Scale"].default_value = 6.0; fib.inputs["Detail"].default_value = 12
    fib.inputs["Distortion"].default_value = 0.6; nt.links.new(mp.outputs["Vector"], fib.inputs["Vector"])
    mp2 = nt.nodes.new("ShaderNodeMapping"); mp2.inputs["Scale"].default_value = (140.0, 140.0, 6.0)
    nt.links.new(tc.outputs["Object"], mp2.inputs["Vector"])
    pore = nt.nodes.new("ShaderNodeTexNoise"); pore.inputs["Scale"].default_value = 1.0; pore.inputs["Detail"].default_value = 2
    nt.links.new(mp2.outputs["Vector"], pore.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB"); el = ramp.color_ramp.elements
    el[0].position = 0.30; el[0].color = (*dark, 1); el[1].position = 0.72; el[1].color = (*light, 1)
    nt.links.new(fib.outputs["Fac"], ramp.inputs["Fac"])
    pr = nt.nodes.new("ShaderNodeMapRange"); pr.inputs["To Min"].default_value = 0.86; pr.inputs["To Max"].default_value = 1.0
    nt.links.new(pore.outputs["Fac"], pr.inputs["Value"])
    mul = nt.nodes.new("ShaderNodeMixRGB"); mul.blend_type = "MULTIPLY"; mul.inputs["Fac"].default_value = 1.0
    nt.links.new(ramp.outputs["Color"], mul.inputs[1]); nt.links.new(pr.outputs[0], mul.inputs[2])
    nt.links.new(mul.outputs[0], p.inputs["Base Color"])
    b = nt.nodes.new("ShaderNodeBump"); b.inputs["Strength"].default_value = 0.08
    nt.links.new(pore.outputs["Fac"], b.inputs["Height"]); nt.links.new(b.outputs["Normal"], p.inputs["Normal"])
    set_(p, **{"Coat Weight": 0.25, "Coat Roughness": 0.25})
    return m


def fabric_bump(m, scale=900, strength=0.12):
    bump_from(m, m.node_tree.nodes["Principled BSDF"], strength, scale=scale)
    return m


# ------------------------------------------------------------------ shared materials
CHROME = pmat("chrom", (0.92, 0.92, 0.94), 0.07, metal=1.0)
STEEL = pmat("nerez", (0.85, 0.85, 0.86), 0.25, metal=1.0)
CERAMIC = pmat("keramika", (0.93, 0.93, 0.92), 0.06, coat=1.0)
PLASTIC_W = pmat("plast_bily", (0.88, 0.88, 0.87), 0.35)
PAINT_W = pmat("lak_bily", (0.86, 0.86, 0.85), 0.18, coat=0.4)
DARKPL = pmat("plast_cerny", (0.02, 0.02, 0.022), 0.4)
OAK = wood_mat("dub", srgb(198, 148, 94), srgb(176, 126, 78))
MIRROR = pmat("zrcadlo_m", (0.96, 0.96, 0.96), 0.01, metal=1.0)
LED = pmat("led_panel", (1, 1, 1), 0.5, emit=(1.0, 0.96, 0.9), emit_str=4.0)
LED_W = pmat("led_svitidlo", (1, 1, 1), 0.5, emit=(1.0, 0.95, 0.88), emit_str=2.5)
TOWEL_L = fabric_bump(pmat("rucnik_svetly", srgb(128, 128, 134), 1.0, sheen=0.8), 1400, 0.35)
TOWEL_D = fabric_bump(pmat("rucnik_tmavy", srgb(58, 58, 66), 1.0, sheen=0.8), 1400, 0.35)
CURTAIN_B = pmat("zaves_sprcha", (0.9, 0.9, 0.88), 0.6, sheen=0.3)

# ================================================================== BATHROOM (a 0.79-2.79, b 2.62-5.35)
remove(("wc_instalace", "wc_", "splachovani", "umyvadlo", "zrcadlo", "kos_na_pradlo"))
for o in list(D_.objects):
    if o.name.startswith("wc") and o.type == "MESH": D_.objects.remove(o, do_unlink=True)


def tile_mat():
    """Wall tiles 60 x 25 cm, stack bond: anthracite to 0.75 m, grey to 1.25, light beige to 1.75, paint above."""
    m = D_.materials.new("obklad_koupelna"); m.use_nodes = True; nt = m.node_tree; p = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry"); sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(geo.outputs["Position"], sep.inputs[0])
    add = nt.nodes.new("ShaderNodeMath"); add.operation = "ADD"; nt.links.new(sep.outputs[0], add.inputs[0]); nt.links.new(sep.outputs[1], add.inputs[1])
    uvw = nt.nodes.new("ShaderNodeCombineXYZ"); nt.links.new(add.outputs[0], uvw.inputs[0]); nt.links.new(sep.outputs[2], uvw.inputs[1])
    br = nt.nodes.new("ShaderNodeTexBrick"); br.offset = 0.0; br.squash = 1.0
    for k, v in {"Scale": 1.0, "Mortar Size": 0.0025, "Mortar Smooth": 0.1, "Bias": 0.0, "Brick Width": 0.60, "Row Height": 0.25}.items():
        br.inputs[k].default_value = v
    br.inputs["Color1"].default_value = (1, 1, 1, 1); br.inputs["Color2"].default_value = (0.93, 0.93, 0.93, 1)
    br.inputs["Mortar"].default_value = (1, 1, 1, 1)                     # joints come from the Fac mask only
    nt.links.new(uvw.outputs[0], br.inputs["Vector"])
    # colour bands by height
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 0; mr.inputs["From Max"].default_value = 2.31 * S   # metres after placement
    nt.links.new(sep.outputs[2], mr.inputs["Value"])
    ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.color_ramp.interpolation = "CONSTANT"; els = ramp.color_ramp.elements
    els[0].position = 0.0; els[0].color = (*srgb(52, 50, 50), 1)
    els[1].position = 0.75 / 2.31; els[1].color = (*srgb(118, 115, 112), 1)
    e = els.new(1.25 / 2.31); e.color = (*srgb(170, 164, 154), 1)
    e = els.new(1.75 / 2.31); e.color = (*srgb(236, 233, 226), 1)
    nt.links.new(mr.outputs[0], ramp.inputs["Fac"])
    # stone-like mottling inside each tile
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 18; nz.inputs["Detail"].default_value = 10
    nt.links.new(geo.outputs["Position"], nz.inputs["Vector"])
    mot = nt.nodes.new("ShaderNodeMapRange"); mot.inputs["To Min"].default_value = 0.93; mot.inputs["To Max"].default_value = 1.06
    nt.links.new(nz.outputs["Fac"], mot.inputs["Value"])
    tint = nt.nodes.new("ShaderNodeMixRGB"); tint.blend_type = "MULTIPLY"; tint.inputs["Fac"].default_value = 1
    nt.links.new(ramp.outputs["Color"], tint.inputs[1]); nt.links.new(br.outputs["Color"], tint.inputs[2])
    tint2 = nt.nodes.new("ShaderNodeMixRGB"); tint2.blend_type = "MULTIPLY"; tint2.inputs["Fac"].default_value = 1
    nt.links.new(tint.outputs[0], tint2.inputs[1]); nt.links.new(mot.outputs[0], tint2.inputs[2])
    # above 1.75 m: plain paint, no joints
    paint = nt.nodes.new("ShaderNodeMath"); paint.operation = "GREATER_THAN"; paint.inputs[1].default_value = 1.75 * S
    nt.links.new(sep.outputs[2], paint.inputs[0])
    joint = nt.nodes.new("ShaderNodeMath"); joint.operation = "MULTIPLY"
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    nt.links.new(paint.outputs[0], inv.inputs[1]); nt.links.new(br.outputs["Fac"], joint.inputs[0]); nt.links.new(inv.outputs[0], joint.inputs[1])
    grout = nt.nodes.new("ShaderNodeMixRGB"); grout.inputs["Color2"].default_value = (*srgb(120, 118, 115), 1)
    nt.links.new(joint.outputs[0], grout.inputs["Fac"]); nt.links.new(tint2.outputs[0], grout.inputs["Color1"])
    nt.links.new(grout.outputs[0], p.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange"); rough.inputs["To Min"].default_value = 0.28; rough.inputs["To Max"].default_value = 0.9
    pj = nt.nodes.new("ShaderNodeMath"); pj.operation = "MAXIMUM"; nt.links.new(paint.outputs[0], pj.inputs[0]); nt.links.new(joint.outputs[0], pj.inputs[1])
    nt.links.new(pj.outputs[0], rough.inputs["Value"]); nt.links.new(rough.outputs[0], p.inputs["Roughness"])
    b = nt.nodes.new("ShaderNodeBump"); b.inputs["Strength"].default_value = 0.35; b.invert = True
    nt.links.new(joint.outputs[0], b.inputs["Height"]); nt.links.new(b.outputs["Normal"], p.inputs["Normal"])
    return m


def floor_tile_mat():
    m = D_.materials.new("dlazba_koupelna"); m.use_nodes = True; nt = m.node_tree; p = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    br = nt.nodes.new("ShaderNodeTexBrick"); br.offset = 0.0
    for k, v in {"Scale": 1.0, "Mortar Size": 0.003, "Brick Width": 0.60, "Row Height": 0.60, "Bias": 0.0}.items():
        br.inputs[k].default_value = v
    br.inputs["Color1"].default_value = (*srgb(206, 203, 197), 1); br.inputs["Color2"].default_value = (*srgb(198, 195, 189), 1)
    br.inputs["Mortar"].default_value = (*srgb(160, 157, 152), 1)
    nt.links.new(geo.outputs["Position"], br.inputs["Vector"]); nt.links.new(br.outputs["Color"], p.inputs["Base Color"])
    set_(p, Roughness=0.32)
    b = nt.nodes.new("ShaderNodeBump"); b.inputs["Strength"].default_value = 0.3; b.invert = True
    nt.links.new(br.outputs["Fac"], b.inputs["Height"]); nt.links.new(b.outputs["Normal"], p.inputs["Normal"])
    return m


TILES, FLOOR_T = tile_mat(), floor_tile_mat()
for o in D_.objects:
    if o.type == "MESH" and o.name.startswith("zed_koupelna"): o.data.materials[0] = TILES
    if o.type == "MESH" and o.name.startswith("podlaha_koupelna"): o.data.materials[0] = FLOOR_T

# chrome edge trim on the installation box-out's outer corner (photo)
cube("roh_lista", 1.600, 1.612, 2.608, 2.632, 0.0, 1.75, CHROME)
cube("roh_lista", 1.588, 1.612, 2.620, 2.632, 0.0, 1.75, CHROME)
# --- wall-hung WC on the left wall, centred b = 3.0
YC = 3.0
begin("FX", 0.79, YC, 0.0)
outline = [(0.79, YC - 0.17)] + [(x, y) for x, y in arc_pts(1.12, YC, 0.33, 0.185, -90, 90, 24)] + [(0.79, YC + 0.17)]
wc = bowl_body("wc_misa", outline, (1.17, YC), 0.19, 0.125, 0.20, 0.43, 0.15, CERAMIC)
bevel(wc, 0.012, 3)
ring_solid("wc_sedatko", (1.17, YC), 0.255, 0.18, 0.18, 0.12, 0.43, 0.452, PLASTIC_W)
cyl("wc_voda", 1.17, YC, 0.338, 0.3385, 0.13, pmat("voda", (0.7, 0.75, 0.78), 0.02, coat=1.0), seg=48, ry=0.085)
lid = prism("wc_veko", [(x, y) for x, y in arc_pts(0.0, 0.0, 0.25, 0.18, 0, 360, 48)][:-1], 0.0, 0.02, PLASTIC_W, bev=0.008)
lid.rotation_euler = (0, math.radians(-98), 0); lid.location = (0.835, YC, 0.455 + 0.25)   # opened up against the wall
cube("wc_tlacitko_deska", 0.79, 0.80, YC - 0.125, YC + 0.125, 0.98, 1.14, PLASTIC_W, bev=0.004)
cyl("wc_tlacitko", YC, 1.06, 0.80, 0.806, 0.055, PAINT_W, axis="X")
cyl("wc_tlacitko2", YC, 1.06, 0.806, 0.808, 0.032, PLASTIC_W, axis="X")
# fold-down grab bar on the door side, offset grab bar on the other side, paper holder
cube("madlo_drzak", 0.79, 0.81, YC - 0.40, YC - 0.30, 0.62, 0.86, CHROME, bev=0.004)
tube("madlo_sklopne", [(0.80, YC - 0.35, 0.80), (1.56, YC - 0.35, 0.80), (1.56, YC - 0.35, 0.66), (0.80, YC - 0.35, 0.66)], 0.016, CHROME, rr=0.07)
tube("madlo_svisle", [(0.79, YC + 0.38, 1.44), (0.87, YC + 0.38, 1.44), (0.87, YC + 0.38, 0.74), (0.79, YC + 0.38, 0.74)], 0.016, CHROME, rr=0.04)
for z in (1.44, 0.74): cyl("madlo_rozeta", YC + 0.38, z, 0.79, 0.80, 0.035, CHROME, axis="X")
PAPER = pmat("papir_m", (0.92, 0.92, 0.9), 0.9)
tube("drzak_papiru", [(0.79, YC + 0.48, 0.76), (0.86, YC + 0.48, 0.76), (0.86, YC + 0.59, 0.76)], 0.008, CHROME, rr=0.02)   # on the wall (current)
cyl("papir", 0.86, 0.71, YC + 0.48, YC + 0.59, 0.055, PAPER, axis="Y")
cyl("wc_stetka", 0.93, YC + 0.30, 0.0, 0.34, 0.045, PLASTIC_W); cyl("wc_stetka_rukojet", 0.93, YC + 0.30, 0.34, 0.44, 0.01, PLASTIC_W)
cyl("cistic", 1.02, YC + 0.36, 0.0, 0.26, 0.035, pmat("lahev_zelena", srgb(90, 160, 60), 0.3, coat=0.5))
end()
# switches + sockets (left wall, by the far corner)
begin("FX", 0.79, 4.03, 0.0)
for z, w in [(1.45, 0.08), (1.24, 0.15), (0.95, 0.08)]:
    cube("vypinac", 0.79, 0.80, 4.03 - w / 2, 4.03 + w / 2, z - 0.04, z + 0.04, PLASTIC_W, bev=0.003)
# laundry hamper (white mesh look, open top with clothes) and bin
end()
# white three-tier trolley next to the WC (current splat; the 2021 hamper is gone)
begin("FX", 0.79, 3.69, 0.0)
TX0, TX1, TY0, TY1 = 0.84, 1.24, 3.48, 3.90
for x in (TX0 + 0.015, TX1 - 0.015):
    for y in (TY0 + 0.015, TY1 - 0.015):
        cyl("vozik", x, y, 0.07, 0.86, 0.011, PAINT_W, seg=16); cyl("vozik_kolecko", x, y, 0.0, 0.065, 0.028, DARKPL, seg=16)
for z in (0.22, 0.52, 0.82):
    cube("vozik_police", TX0, TX1, TY0, TY1, z - 0.012, z, PAINT_W, bev=0.003)
    for (x0, x1, y0, y1) in ((TX0, TX1, TY0, TY0 + 0.012), (TX0, TX1, TY1 - 0.012, TY1), (TX0, TX0 + 0.012, TY0, TY1), (TX1 - 0.012, TX1, TY0, TY1)):
        cube("vozik_okraj", x0, x1, y0, y1, z, z + 0.035, PAINT_W)
cube("vozik_krabice", TX0 + 0.05, TX0 + 0.30, TY0 + 0.06, TY0 + 0.24, 0.82, 0.92, pmat("krabice", srgb(235, 235, 240), 0.6), bev=0.004)
cube("vozik_stitek", TX0 + 0.05, TX0 + 0.30, TY0 + 0.059, TY0 + 0.061, 0.85, 0.89, pmat("stitek_modry", srgb(40, 80, 170), 0.5))
cyl("vozik_kosik", (TX0 + TX1) / 2, (TY0 + TY1) / 2, 0.52, 0.66, 0.15, fabric_bump(pmat("proutí", srgb(170, 130, 80), 0.9), 300, 0.6), seg=32)
cube("vozik_rucniky", TX0 + 0.04, TX1 - 0.04, TY0 + 0.05, TY1 - 0.05, 0.22, 0.32, TOWEL_L, bev=0.03, seg=3, sub=1)
end()
begin("FX", 0.79, 4.29, 0.0)
cube("kos", 0.82, 1.04, 4.16, 4.42, 0.0, 0.42, PLASTIC_W, bev=0.01)
cube("kos_sacek", 0.815, 1.045, 4.155, 4.425, 0.40, 0.43, DARKPL, bev=0.005)

end()
def mesh_mat():
    m = D_.materials.new("sit_kos"); m.use_nodes = True; nt = m.node_tree; p = nt.nodes["Principled BSDF"]
    geo = nt.nodes.new("ShaderNodeNewGeometry"); sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(geo.outputs["Position"], sep.inputs[0])
    add = nt.nodes.new("ShaderNodeMath"); add.operation = "ADD"; nt.links.new(sep.outputs[0], add.inputs[0]); nt.links.new(sep.outputs[1], add.inputs[1])
    uvw = nt.nodes.new("ShaderNodeCombineXYZ"); nt.links.new(add.outputs[0], uvw.inputs[0]); nt.links.new(sep.outputs[2], uvw.inputs[1])
    br = nt.nodes.new("ShaderNodeTexBrick"); br.offset = 0.5
    for k, v in {"Scale": 1.0, "Mortar Size": 0.0035, "Brick Width": 0.016, "Row Height": 0.016}.items(): br.inputs[k].default_value = v
    br.inputs["Color1"].default_value = (0.25, 0.25, 0.26, 1); br.inputs["Color2"].default_value = (0.25, 0.25, 0.26, 1)
    br.inputs["Mortar"].default_value = (0.86, 0.86, 0.85, 1)
    nt.links.new(uvw.outputs[0], br.inputs["Vector"]); nt.links.new(br.outputs["Color"], p.inputs["Base Color"])
    set_(p, Roughness=0.6); return m
# --- barrier-free washbasin on the LEFT wall by the far corner (splat top view: b 4.55-5.15), mirror above it
begin("FX", 0.79, 4.85, 0.0)
SY0, SY1, SX = 4.55, 5.15, 0.79
SC = (SY0 + SY1) / 2
basin_out = [(SX, SY0), (SX, SY1)] + [(x, y) for x, y in arc_pts(1.00, SC, 0.33, 0.30, 90, -90, 24)]
basin = bowl_body("umyvadlo_telo", basin_out, (1.07, SC), 0.15, 0.22, 0.70, 0.83, 0.11, CERAMIC)
bevel(basin, 0.010, 3)
cyl("umyvadlo_vytok", 1.07, SC, 0.719, 0.722, 0.02, CHROME)
cyl("baterie", 0.86, SC, 0.83, 0.93, 0.024, CHROME)
tube("baterie_vytok", [(0.86, SC, 0.91), (0.97, SC, 0.905), (0.99, SC, 0.885)], 0.011, CHROME, rr=0.02)
tube("baterie_paka", [(0.86, SC, 0.935), (0.85, SC + 0.16, 0.94)], 0.008, CHROME, rr=0)
tube("madlo_umyvadlo", [(0.79, SY1 + 0.06, 0.79), (1.22, SY1 + 0.06, 0.79), (1.22, SY1 + 0.15, 0.79), (0.79, SY1 + 0.15, 0.79)], 0.015, CHROME, rr=0.05)
end()
begin("FX", 1.86, 5.35, 0.0)
tube("madlo_bile", [(1.86, 5.35, 0.42), (1.86, 5.29, 0.42), (1.86, 5.29, 0.80), (1.86, 5.35, 0.80)], 0.016, PAINT_W, rr=0.03)
end()
begin("FX", 0.79, 4.85, 0.0)
mir = cube("zrcadlo_sklopne", -0.004, 0.004, -0.25, 0.25, 0.0, 0.62, MIRROR)
mir.location = (0.80, SC, 1.00); mir.rotation_euler = (0, math.radians(8), 0)                # top leans into the room
for sy in (-1, 1):                                                       # tilt hinges: arms from the wall to the mirror's sides
    cyl("zrcadlo_drzak", SC + sy * 0.258, 1.31, 0.79, 0.85, 0.008, CHROME, axis="X")
    cyl("zrcadlo_cep", 0.845, 1.31, SC + sy * 0.248, SC + sy * 0.262, 0.012, CHROME, axis="Y")
    cube("zrcadlo_rozeta", 0.79, 0.796, SC + sy * 0.258 - 0.02, SC + sy * 0.258 + 0.02, 1.29, 1.33, CHROME, bev=0.003)
cyl("davkovac", 0.87, SY0 + 0.07, 0.83, 0.98, 0.032, PLASTIC_W)
cyl("davkovac_pumpa", 0.87, SY0 + 0.07, 0.98, 1.02, 0.008, CHROME)
cyl("kelimek_drzak", 0.82, SY0 - 0.12, 0.94, 0.95, 0.04, CHROME)
cyl("kelimek", 0.82, SY0 - 0.12, 0.95, 1.05, 0.032, GLASS)
cube("svitidlo_zed", 0.79, 0.81, SY0 - 0.30, SY0 - 0.02, 1.92, 2.20, LED_W, bev=0.004)

end()
# --- walk-in shower: glass at a 2.20 (kept), curved curtain rail, thermostat, slide rail, fold-down seat
begin("FX", 1.95, 5.35, 0.0)
cube("sprcha_profil", 1.935, 1.965, 5.33, 5.35, 0.0, 2.0, STEEL)
end()
begin("SXY",)
rail = [(1.95, 4.15, 2.0)] + [(1.95 + 0.84 * s, 4.15 - 0.12 * math.sin(math.pi * s), 2.0) for s in (k / 14 for k in range(1, 14))] + [(2.79, 4.15, 2.0)]
tube("zaves_tyc", rail, 0.011, CHROME, rr=0)
vs, fs = [], []
NZ = 8
for i in range(61):                                          # curtain bunched at the right wall, irregular folds
    s_ = i / 60; amp = 0.022 + 0.012 * math.sin(s_ * 7.3) ** 2
    for j in range(NZ + 1):
        z = 0.10 + 1.88 * j / NZ; flare = 1.0 + 0.35 * (1 - j / NZ) ** 2
        y = 4.155 + amp * flare * math.sin(s_ * math.pi * 17 + 0.4 * math.sin(z * 3)); x = 2.60 + 0.18 * s_ - 0.02 * (1 - j / NZ) ** 2
        vs.append((x, y, z))
for i in range(60):
    for j in range(NZ): fs.append(((NZ + 1) * i + j, (NZ + 1) * (i + 1) + j, (NZ + 1) * (i + 1) + j + 1, (NZ + 1) * i + j + 1))
me = D_.meshes.new("zaves_sprcha"); me.from_pydata(vs, [], fs); me.update()
zv = link(D_.objects.new("zaves_sprcha", me)); me.materials.append(CURTAIN_B); zv.modifiers.new("solid", "SOLIDIFY").thickness = 0.002
end()
begin("FX", 2.37, 5.35, 0.0)
cyl("termostat", 5.30, 1.00, 2.21, 2.53, 0.026, CHROME, axis="X")
for x in (2.21, 2.53): cyl("termostat_hlava", 5.29, 1.00, x - 0.025, x + 0.025, 0.032, CHROME, axis="X")
tube("sprcha_tyc", [(2.45, 5.35, 1.05), (2.45, 5.30, 1.05), (2.45, 5.30, 1.95), (2.45, 5.35, 1.95)], 0.011, CHROME, rr=0.02)
head = cyl("sprcha_hlavice", 2.45, 5.24, 1.70, 1.73, 0.05, CHROME); head.rotation_euler = (math.radians(55), 0, 0)
head.location = (0, 0, 0); head.data.transform(Matrix.Translation((-2.45, -5.24, -1.715))); head.location = (2.45, 5.24, 1.76)
tube("sprcha_hadice", [(2.35, 5.28, 0.98), (2.33, 5.24, 0.62), (2.43, 5.22, 0.58), (2.46, 5.26, 1.62)], 0.008, CHROME, rr=0.12)
end()
begin("FX", 2.79, 4.65, 0.0)
tube("sedatko_ram", [(2.78, 4.45, 0.42), (2.72, 4.45, 0.42), (2.72, 4.45, 0.88), (2.72, 4.85, 0.88), (2.72, 4.85, 0.42), (2.78, 4.85, 0.42)], 0.012, CHROME, rr=0.03)
for k in range(6): cube("sedatko_lamela", 2.725, 2.745, 4.47 + k * 0.064, 4.51 + k * 0.064, 0.46, 0.86, PLASTIC_W, bev=0.004)
end()
begin("SXY",)
cube("sprcha_odtok", 2.05, 2.69, 5.24, 5.29, 0.0, 0.002, STEEL)

end()
# --- right wall: curved ladder towel radiator by the door, towel hooks, towel bar
begin("FX", 2.79, 2.30, 0.0)
RAD = pmat("radiator_lak", (0.88, 0.88, 0.87), 0.2, coat=0.6)
for y in (2.03, 2.57): tube("radiator", [(2.745, y, 0.16), (2.745, y, 1.96)], 0.016, RAD, rr=0)
zs = [0.22 + k * 0.055 for k in range(9)] + [0.80 + k * 0.055 for k in range(9)] + [1.38 + k * 0.055 for k in range(11)]
for z in zs: tube("radiator", [(2.745, 2.03, z), (2.712, 2.30, z), (2.745, 2.57, z)], 0.011, RAD, rr=0.30)
for y in (2.05, 2.55):
    for z in (0.30, 1.80): cube("radiator", 2.75, 2.79, y - 0.01, y + 0.01, z - 0.01, z + 0.01, RAD)
end()
begin("FX", 2.79, 3.915, 0.0)
WR = D_.textures.new("vrasky", "CLOUDS"); WR.noise_scale = 0.06; WR.noise_depth = 2
for y, mat_ in ((3.80, TOWEL_L), (4.03, TOWEL_D)):
    cyl("hacek", y, 1.47, 2.75, 2.79, 0.014, CHROME, axis="X")
    def towel_shape(s_, t, y=y):
        w = 0.20 + 0.12 * min(1.0, t / 0.25)                               # pinched where it hangs on the hook
        fold = (0.010 * math.sin(2 * math.pi * 2.5 * s_ + 0.7) + 0.006 * math.sin(2 * math.pi * 6 * s_)) * min(1.0, t / 0.15)
        return Vector((-0.016 - fold - 0.008 * t, y + (s_ - 0.5) * w, 1.475 - 0.62 * t - 0.012 * math.cos(math.pi * (s_ - 0.5)) * (t < 0.05)))
    bm = bmesh.new(); NU, NV = 24, 36
    V = [[bm.verts.new(towel_shape(i / NU, j / NV)) for j in range(NV + 1)] for i in range(NU + 1)]
    for i in range(NU):
        for j in range(NV): bm.faces.new((V[i][j], V[i][j + 1], V[i + 1][j + 1], V[i + 1][j]))
    me = D_.meshes.new("rucnik"); bm.to_mesh(me); bm.free()
    for p_ in me.polygons: p_.use_smooth = True
    ob_ = link(D_.objects.new("rucnik", me)); ob_.location = (2.79, 0, 0); me.materials.append(mat_)
    dm = ob_.modifiers.new("vrasky", "DISPLACE"); dm.texture = WR; dm.strength = 0.008; dm.direction = "X"
    sd = ob_.modifiers.new("solid", "SOLIDIFY"); sd.thickness = 0.012; sd.offset = 0
end()
begin("FX", 2.79, 3.76, 0.0)
tube("tyc_rucnik", [(2.79, 3.40, 0.80), (2.73, 3.40, 0.80), (2.73, 4.12, 0.80), (2.79, 4.12, 0.80)], 0.012, CHROME, rr=0.03)
prof = [(2.745, 0.47)] + [(2.73 + 0.018 * math.cos(math.radians(a)), 0.80 + 0.018 * math.sin(math.radians(a))) for a in range(0, 181, 20)] + [(2.708, 0.50)]
bm = bmesh.new(); rows = []
for y in (3.50, 4.02):
    rows.append([bm.verts.new((x, y, z)) for x, z in prof])
for i in range(len(prof) - 1): bm.faces.new((rows[0][i], rows[0][i + 1], rows[1][i + 1], rows[1][i]))
me = D_.meshes.new("rucnik_prehozeny"); bm.to_mesh(me); bm.free()
for p in me.polygons: p.use_smooth = True
tw = link(D_.objects.new("rucnik_prehozeny", me)); me.materials.append(TOWEL_L)
sm = tw.modifiers.new("sub", "SUBSURF"); sm.levels = sm.render_levels = 2; sm.boundary_smooth = "PRESERVE_CORNERS"
dm = tw.modifiers.new("vrasky", "DISPLACE"); dm.texture = WR; dm.strength = 0.006
tw.modifiers.new("solid", "SOLIDIFY").thickness = 0.012
end()
begin("FX", 2.25, 3.85, 0.0)
cube("predlozka", 1.95, 2.55, 3.62, 4.08, 0.0, 0.014, fabric_bump(pmat("predlozka_m", srgb(118, 118, 124), 1.0, sheen=1.0), 500, 0.6), bev=0.006)

end()
# --- bathroom door: oak leaf opened into the room against the radiator side, lever + pull bar
# opening a 1.92-2.66 (0.95 m), 2.12 m high; leaf hinged at the radiator side, opened into the room along that wall
DH = 2.12 / SO - 0.015                                   # leaf just under the 1.659 u opening
dl = cube("dvere_koupelna", 2.665, 2.707, 1.97, 2.70, 0.005, DH, OAK, bev=0.003)
for x in (2.655, 2.717):
    tube("klika", [(x, 2.62, 1.02 / S), (x, 2.51, 1.02 / S)], 0.009, STEEL, rr=0)
    cyl("rozeta", 2.62, 1.02 / S, min(x, 2.707), max(x, 2.665), 0.022, STEEL, axis="X")
tube("madlo_dvere", [(2.665, 2.10, 0.86 / S), (2.615, 2.10, 0.86 / S), (2.615, 2.55, 0.86 / S), (2.665, 2.55, 0.86 / S)], 0.013, STEEL, rr=0.03)
for z in (0.25 / S, 1.75 / S): cube("zaves_dveri", 2.705, 2.72, 1.95, 1.99, z, z + 0.11, STEEL)

# ================================================================== whole flat
# --- ceiling lights where the splat sees them (lights.json from build_clean.py): 60 cm LED panels sit in the
#     ceiling grid (the bathroom has a plain ceiling, so its panels stay where measured), small blobs are downlights
LJ = json.load(open(os.path.join(HERE, "lights.json")))
def inside(x, y, tol=0.05):
    for poly in LJ["rooms"].values():
        n = len(poly); c = False
        for i in range(n):
            (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0): c = not c
        if c: return True
    return False
G_U = 0.6 / S                                          # one real 60 cm ceiling tile in model units
def snap(x, y):
    return (LJ["A0"] + (math.floor((x - LJ["A0"]) / G_U) + 0.5) * G_U, LJ["B1"] - (math.floor((LJ["B1"] - y) / G_U) + 0.5) * G_U)
LIGHT_FIX = []
for f in LJ["fixtures"]:
    x, y, big = f["a"], f["b"], max(f["w"], f["h"]) >= 0.40
    if not inside(x, y): continue
    if any(math.hypot(x - q[0], y - q[1]) < 0.3 for q in LIGHT_FIX): continue          # one fixture, two blobs
    in_bath = 0.79 < x < 2.79 and 2.62 < y < 5.35
    if big and not in_bath:
        x, y = snap(x, y)
    LIGHT_FIX.append((x, y, "panel" if big else "spot"))
for x, y, kind in LIGHT_FIX:
    begin("FX", x, y, H_U)
    if kind == "panel":
        cube("led_ram", x - 0.298, x + 0.298, y - 0.298, y + 0.298, 2.296, 2.305, STEEL)
        cube("led_panel", x - 0.28, x + 0.28, y - 0.28, y + 0.28, 2.294, 2.2955, LED)
    else:
        cyl("bodovka_ram", x, y, 2.296, 2.306, 0.085, PLASTIC_W, seg=40)
        cyl("led_bodovka", x, y, 2.294, 2.2955, 0.062, LED, seg=40)
    end()
print("LIGHTS", [(round(x, 2), round(y, 2), k) for x, y, k in LIGHT_FIX], flush=True)

# --- bedroom door leaf (opened into the bedroom against the a = -1.45 wall) and the front door in 3D
cube("dvere_loznice", -1.515, -1.473, 1.43, 2.12, 0.005, 2.12 / SO - 0.015, OAK, bev=0.003)          # 0.91 x 2.12 m opening (splat)
for x in (-1.525, -1.463):
    tube("klika", [(x, 2.05, 1.02 / S), (x, 1.94, 1.02 / S)], 0.009, STEEL, rr=0)
x0, x1 = 5.715, 5.757                                                     # front door, b from the splat elevation
FR = pmat("zarubne_vchod", srgb(58, 60, 64), 0.4, metal=0.5)
cube("vchodove_dvere", x0, x1, 1.10, 1.94, 0.005, 2.10 / SO, OAK, bev=0.003)
cube("vchodove_dvere", x0, x1, 0.86, 1.06, 0.005, 2.10 / SO, OAK, bev=0.003)
cube("vchodove_sklo", x0 - 0.002, x0 + 0.004, 0.93, 0.99, 0.35 / SO, 1.95 / SO, pmat("matne_sklo", (0.85, 0.88, 0.9), 0.35), bev=0)
for (y0, y1) in ((0.80, 0.86), (1.06, 1.10), (1.94, 2.00)):
    cube("vchodove_zarubne", 5.70, 5.762, y0, y1, 0.0, 2.10 / SO, FR)
cube("vchodove_zarubne", 5.70, 5.762, 0.80, 2.00, 2.10 / SO, 2.16 / SO, FR)
tube("klika", [(x0 - 0.012, 1.17, 1.02 / S), (x0 - 0.012, 1.29, 1.02 / S)], 0.01, STEEL, rr=0)
cube("stitek", x0 - 0.008, x0, 1.15, 1.19, 0.90 / S, 1.12 / S, STEEL, bev=0.003)
cube("papir_dvere", x0 - 0.003, x0 - 0.001, 1.36, 1.58, 1.50 / S, 1.80 / S, pmat("papir_m2", (0.9, 0.9, 0.88), 0.8))
cube("unikovy_vychod", 5.73, 5.76, 1.29, 1.53, 2.40 / SO, 2.55 / SO, pmat("exit", srgb(30, 150, 80), 0.4, emit=srgb(60, 200, 110), emit_str=1.5), bev=0.004)
# coat rack on the door wall (splat: b 2.15-3.45, ~1.7 m): wire hat shelf with hooks
remove(("vesak",))
WIRE = pmat("drat_bily", (0.86, 0.86, 0.85), 0.3)
for k in range(6): tube("vesak_drat", [(5.755 - 0.04 * (k + 0.5), 2.15, 1.735), (5.755 - 0.04 * (k + 0.5), 3.45, 1.735)], 0.004, WIRE, rr=0)
for y in (2.17, 2.80, 3.43): tube("vesak_drat", [(5.76, y, 1.62), (5.755, y, 1.735), (5.52, y, 1.735)], 0.007, WIRE, rr=0.03)
for y in [2.25 + 0.16 * k for k in range(8)]: tube("vesak_hacek_d", [(5.53, y, 1.735), (5.53, y, 1.64), (5.56, y, 1.62)], 0.005, WIRE, rr=0.02)
# teal feature wall: paint + the 35 hexagon panels fitted on the splat (one glows orange)
TEAL = pmat("tyrkys", srgb(16, 78, 104), 0.85)
for o in D_.objects:
    if o.type == "MESH" and o.name.startswith("zed_predsin_2"): o.data.materials[0] = TEAL
HX = json.load(open(os.path.join(HERE, "hexes.json"))) if os.path.exists(os.path.join(HERE, "hexes.json")) else None
HEXW = pmat("hex_bily", (0.85, 0.85, 0.84), 0.55)
HEXO = pmat("hex_oranz", srgb(240, 160, 70), 0.5, emit=srgb(255, 150, 60), emit_str=3.0)
if HX:
    r_ = HX["R"] * 0.94
    for (a, z), orng in zip(HX["hexes"], HX["orange"]):
        pts = [(a + r_ * math.cos(math.radians(60 * k)), z + r_ * math.sin(math.radians(60 * k))) for k in range(6)]
        bm = bmesh.new(); f_ = [bm.verts.new((x, 3.739, zz)) for x, zz in pts]; b_ = [bm.verts.new((x, 3.727, zz)) for x, zz in pts]
        bm.faces.new(f_); bm.faces.new(b_[::-1])
        for k in range(6): bm.faces.new((f_[k], b_[k], b_[(k + 1) % 6], f_[(k + 1) % 6]))
        hob = from_bm("hex_panel", bm, HEXO if orng else HEXW); bevel(hob, 0.003, 2)
# shoe cabinet fronts: three tilt-out flaps with knobs
for z in (0.333, 0.666): cube("botnik_spara", 4.000, 4.004, 2.41, 3.14, z - 0.002, z + 0.002, pmat("spara", srgb(150, 150, 150), 0.6))
for z in (0.25, 0.58, 0.91): cyl("botnik_uchytka", 2.775, z, 4.00, 4.025, 0.012, STEEL, axis="X")

# --- kitchen: tap, LED strip under the wall units, a few things on the counter
begin("FX", 2.10, -2.98, 0.70)
cyl("baterie_kuchyn", 2.10, -2.98, 0.70, 0.74, 0.03, CHROME)
tube("baterie_kuchyn_vytok", [(2.10, -2.98, 0.74), (2.10, -2.98, 1.02), (1.94, -2.98, 1.02), (1.92, -2.98, 0.96)], 0.012, CHROME, rr=0.08)
end()
cube("kuchyn_ledpasek", 1.87, 1.90, -4.65, -1.04, 1.205, 1.215, LED_W)
begin("FX", 2.02, -1.55, 0.70); cyl("konvice", 2.02, -1.55, 0.71, 0.93, 0.085, STEEL, seg=40); end()
begin("FX", 2.115, -2.275, 0.70); cube("prkenko", 2.10, 2.13, -2.45, -2.10, 0.71, 1.02, OAK, bev=0.006); end()
begin("FX", 1.95, -1.25, 0.70)
cyl("misa_ovoce", 1.95, -1.25, 0.71, 0.79, 0.13, CERAMIC, seg=40)
for k in range(5):
    a, b = 1.95 + rnd.uniform(-0.06, 0.06), -1.25 + rnd.uniform(-0.06, 0.06)
    bpy_ob = cyl("ovoce", a, b, 0.76 + rnd.uniform(0, 0.03), 0.84 + rnd.uniform(0, 0.03), 0.04,
                 pmat("ovoce_m", rnd.choice([srgb(200, 60, 40), srgb(230, 170, 40), srgb(120, 160, 50)]), 0.4), seg=16)
    sm = bpy_ob.modifiers.new("sub", "SUBSURF"); sm.levels = sm.render_levels = 2
end()

# --- the white cubby shelf is open at the front (tour): frame, back, shelves, dividers
remove(("regal_prihradky",))
SHW = pmat("regal_bily", (0.86, 0.86, 0.85), 0.3)
cube("regal_prihradky", -4.05, -1.65, -4.69, -4.675, 0.0, 0.90, SHW)
for z0, z1 in ((0.0, 0.03), (0.435, 0.465), (0.87, 0.90)): cube("regal_prihradky", -4.05, -1.65, -4.675, -4.35, z0, z1, SHW, bev=0.002)
for k in range(7):
    x = -4.05 + k * 0.40
    cube("regal_prihradky", x, x + 0.02 if k < 6 else x, -4.675, -4.35, 0.0, 0.90, SHW, bev=0.002) if k < 6 else None
cube("regal_prihradky", -1.67, -1.65, -4.675, -4.35, 0.0, 0.90, SHW, bev=0.002)
# --- books, boxes and decor in the cubby shelf and on the glass shelves
BOOKCOLS = [srgb(*c) for c in [(160, 50, 45), (40, 70, 120), (220, 210, 190), (60, 90, 70), (200, 150, 60), (30, 30, 35), (150, 150, 155), (180, 90, 60)]]
for col_i in range(6):
    a0 = -4.03 + col_i * 0.40; a1 = a0 + 0.36
    for z0 in (0.03, 0.465):
        kind = rnd.random()
        if kind < 0.5:                                         # a row of books
            a = a0 + 0.01
            while a < a1 - 0.03:
                w = rnd.uniform(0.018, 0.04); h = rnd.uniform(0.20, 0.32) if z0 > 0.1 else rnd.uniform(0.22, 0.36)
                h = min(h, 0.40); d = rnd.uniform(0.15, 0.22)
                h = min(h, 0.395); cube("kniha", a, a + w, -4.67, -4.67 + d, z0, z0 + h, pmat("kniha_m", rnd.choice(BOOKCOLS), 0.6), bev=0.002)
                a += w + 0.002
        elif kind < 0.8:                                       # fabric storage box
            cube("box", a0 + 0.02, a1 - 0.02, -4.665, -4.37, z0, z0 + 0.34,
                 fabric_bump(pmat("box_m", rnd.choice([srgb(170, 165, 155), srgb(110, 112, 118)]), 1.0, sheen=0.5), 700, 0.2), bev=0.01)
begin("FX", -3.0, -4.52, 0.90); cyl("vaza", -3.0, -4.52, 0.90, 1.14, 0.06, CERAMIC, seg=40); end()
for b0 in (-1.15, -2.55):
    cyl("dekorace", -3.88, b0 + 0.20, 0.44, 0.58, 0.05, pmat("deko", srgb(70, 90, 110), 0.15, coat=1.0), seg=40)
    for k in range(5):
        cube("kniha", -4.03, -3.84, b0 + 0.03 + k * 0.035, b0 + 0.06 + k * 0.035, 0.86, 0.86 + rnd.uniform(0.18, 0.26),
             pmat("kniha_m", rnd.choice(BOOKCOLS), 0.6), bev=0.002)

# --- desks: keyboards, mouse, lamp
ZL, ZW = 0.625 * S, 0.585 * S                                             # desk tops (splat), metres
for (xa, xb, y0, zt) in [(-3.55, -3.10, 0.92, ZL), (-0.05, 0.40, -4.45, ZW), (0.70, 1.15, -4.45, ZW)]:
    begin("FX", (xa + xb) / 2, y0, 0.0); cube("klavesnice", xa, xb, y0, y0 + 0.14, zt, zt + 0.02, DARKPL, bev=0.003); end()
begin("FX", -2.95, 1.0, 0.0); cube("mys", -2.98, -2.92, 0.95, 1.05, ZL, ZL + 0.03, DARKPL, bev=0.012, seg=4); end()
begin("FX", -2.75, 1.10, 0.0)
cyl("lampa_noha", -2.75, 1.12, ZL, ZL + 0.40, 0.008, STEEL); cyl("lampa_paticka", -2.75, 1.12, ZL, ZL + 0.015, 0.07, STEEL)
cyl("lampa_stinitko", -2.75, 1.05, ZL + 0.33, ZL + 0.45, 0.07, PLASTIC_W)
end()


# ================================================================== round 2: living room, dining, hall (tour scenes 735/738/739)
LINEN = pmat("len_bily", srgb(232, 229, 222), 1.0, sheen=0.6)
nt_ = LINEN.node_tree; p_ = nt_.nodes["Principled BSDF"]
n1 = nt_.nodes.new("ShaderNodeTexNoise"); n1.inputs["Scale"].default_value = 900; n1.inputs["Detail"].default_value = 4
n2 = nt_.nodes.new("ShaderNodeTexNoise"); n2.inputs["Scale"].default_value = 9; n2.inputs["Detail"].default_value = 6
mx = nt_.nodes.new("ShaderNodeMath"); mx.operation = "MULTIPLY_ADD"; mx.inputs[1].default_value = 0.35
nt_.links.new(n2.outputs["Fac"], mx.inputs[0]); nt_.links.new(n1.outputs["Fac"], mx.inputs[2])
bp = nt_.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.25
nt_.links.new(mx.outputs[0], bp.inputs["Height"]); nt_.links.new(bp.outputs["Normal"], p_.inputs["Normal"])
MUSTARD = fabric_bump(pmat("horcicova", srgb(205, 150, 48), 1.0, sheen=0.7), 600, 0.3)
GREYF = fabric_bump(pmat("seda_latka", srgb(120, 120, 124), 1.0, sheen=0.7), 600, 0.3)
KNIT = fabric_bump(pmat("pled", srgb(196, 140, 45), 1.0, sheen=0.8), 220, 0.6)

remove(("sedacka", "polstar", "deka", "zidle", "kancelarska_zidle"))
# --- L sofa in a white linen slipcover (footprint measured in the splat): base, backs, arm, soft cushions
def soft(name, x0, x1, y0, y1, z0, z1, mat, r=0.035, sub=2):
    return cube(name, x0, x1, y0, y1, z0, z1, mat, bev=r, seg=2, sub=sub)
# sofa measured on the splat in metres (iterace 06): long part 2.4 x 0.9 m (back to the east, facing the TV), short part
# 0.75 m to the west along the north; seat 0.45, back 0.85, arm 0.62 m
begin("MXY")
XE, XBI, XW, XCH = -2.15, -2.38, -3.05, -3.80
YS, YN, YCH, YBI = -3.45, -1.05, -1.65, -1.27
soft("sedacka_zaklad", XW, XE, YS, YN, 0.07, 0.27, LINEN, 0.02)
soft("sedacka_zaklad", XCH, XW + 0.002, YCH, YN, 0.07, 0.27, LINEN, 0.02)
for x, y in [(XW + 0.05, YS + 0.05), (XE - 0.05, YS + 0.05), (XE - 0.05, YN - 0.05), (XCH + 0.05, YN - 0.05), (XCH + 0.05, YCH + 0.05), (XW + 0.05, YCH + 0.05)]:
    cyl("sedacka_noha", x, y, 0.0, 0.07, 0.022, OAK, seg=16)
soft("sedacka_operadlo", XBI, XE, YS + 0.20, YN, 0.27, 0.85, LINEN, 0.05)
soft("sedacka_operadlo", XCH, XBI, YBI, YN, 0.27, 0.85, LINEN, 0.05)
soft("sedacka_podrucka", XW, XE, YS, YS + 0.20, 0.27, 0.62, LINEN, 0.05)
seat_y = [YS + 0.205 + k * (YBI - 0.005 - YS - 0.205) / 3 for k in range(4)]
for k in range(3):
    soft("sedacka_sedak", XW + 0.01, XBI - 0.005, seat_y[k] + 0.003, seat_y[k + 1] - 0.003, 0.27, 0.45, LINEN, 0.06, 2)
soft("sedacka_sedak", XCH + 0.01, XW - 0.003, YCH + 0.01, YBI - 0.005, 0.27, 0.45, LINEN, 0.06, 2)
for k in range(3):
    c_ = soft("sedacka_opera", XBI - 0.19, XBI - 0.005, seat_y[k] + 0.01, seat_y[k + 1] - 0.01, 0.44, 0.86, LINEN, 0.07, 2)
    c_.data.transform(Matrix.Translation((XBI - 0.1, 0, 0.44)) @ Matrix.Rotation(math.radians(-9), 4, "Y") @ Matrix.Translation((-(XBI - 0.1), 0, -0.44)))
for x0, x1 in [(XCH + 0.01, XW - 0.02), (XW - 0.01, XBI - 0.02)]:
    c_ = soft("sedacka_opera", x0, x1, YBI - 0.19, YBI - 0.005, 0.44, 0.86, LINEN, 0.07, 2)
    c_.data.transform(Matrix.Translation((0, YBI - 0.1, 0.44)) @ Matrix.Rotation(math.radians(9), 4, "X") @ Matrix.Translation((0, -(YBI - 0.1), -0.44)))
for (x, y, ang, mat_) in [(XBI - 0.30, -2.50, 0, MUSTARD), (XBI - 0.30, -1.95, 0, MUSTARD), (XCH + 0.35, YBI - 0.30, 90, GREYF)]:
    c_ = soft("polstar_dek", -0.22, 0.22, -0.06, 0.06, -0.22, 0.22, mat_, 0.09, 2)
    c_.data.transform(Matrix.Translation((x, y, 0.67)) @ Matrix.Rotation(math.radians(ang), 4, "Z") @ Matrix.Rotation(math.radians(90), 4, "Z")
                      @ Matrix.Rotation(math.radians(18), 4, "X"))
# knitted throw over the short part, falling down its west end
def throw(s_, t_):
    L_ = s_ * 1.0; y = YCH + 0.06 + (YBI - YCH - 0.12) * t_ + 0.01 * math.sin(t_ * 17 + s_ * 5)
    top = XW + 0.25 - XCH                                                        # lying length on the seat
    if L_ < top: return Vector((XW + 0.25 - L_, y, 0.452 + 0.012 * math.sin(L_ * 23 + t_ * 9) * (L_ / top)))
    d_ = L_ - top; th = min(d_ / 0.06, 1) * math.pi / 2
    x = XCH - 0.02 * math.sin(th) - 0.008 * math.sin(t_ * 21); z = 0.452 - (0.03 * (1 - math.cos(th)) + max(0, d_ - 0.06))
    return Vector((x, y, z))
bm = bmesh.new(); NU, NV = 40, 16
Vt = [[bm.verts.new(throw(i / NU, j / NV)) for j in range(NV + 1)] for i in range(NU + 1)]
for i in range(NU):
    for j in range(NV): bm.faces.new((Vt[i][j], Vt[i + 1][j], Vt[i + 1][j + 1], Vt[i][j + 1]))
bm.normal_update()
if sum(f.normal.z for f in bm.faces) < 0:
    for f in bm.faces: f.normal_flip()
me = D_.meshes.new("pled"); bm.to_mesh(me); bm.free()
for p_ in me.polygons: p_.use_smooth = True
ob_ = link(D_.objects.new("pled", me)); me.materials.append(KNIT)
ob_.modifiers.new("solid", "SOLIDIFY").thickness = 0.012; sm = ob_.modifiers.new("sub", "SUBSURF"); sm.levels = sm.render_levels = 1
# coffee table (Ø 0.80 m, top 0.45 m, centre (-3.85, -2.45) m): a tray, a book, a candle
CT = 0.435 * S                                          # coffee table top (splat), metres
cyl("podnos", -3.85, -2.45, CT, CT + 0.015, 0.17, OAK, seg=48)
cube("kniha", -3.97, -3.77, -2.34, -2.20, CT + 0.015, CT + 0.04, pmat("kniha_m", srgb(40, 70, 120), 0.6), bev=0.002)
cyl("svicka", -3.80, -2.50, CT + 0.015, CT + 0.09, 0.035, pmat("vosk", srgb(240, 236, 226), 0.5, transm=0.2), seg=32)
end()

# --- dining chairs: white wooden spindle-back chairs facing the table
TC = (0.42, -4.40)                                                       # round table centre in OLD metres (splat)
TT = 0.595 * S                                                           # table top (splat), metres
if STUL2:
    for o in list(D_.objects):
        if o.type == 'MESH' and o.name.startswith('jidelni_stul'): o.location.x += D2[0]; o.location.y += D2[1]
CHAIRS = [((TC[0] + 0.80 * math.cos(math.radians(a_))) / SO + (D2[0] if STUL2 else 0), (TC[1] + 0.80 * math.sin(math.radians(a_))) / SO + (D2[1] if STUL2 else 0), a_ + 180)
          for a_ in ((0, 90, 180) if not STUL2 else (0, 90, 180))] + [(1.10 / SO, -5.25 / SO, -90)]
for k, (ca, cb, rot) in enumerate(CHAIRS):                               # 4th chair at the work desk
    begin("FX", ca, cb, 0.0)
    M = Matrix.Translation((ca, cb, 0)) @ Matrix.Rotation(math.radians(rot), 4, "Z")   # local +x points to the table / desk
    parts = [cube("zidle", -0.20, 0.20, -0.20, 0.20, 0.43, 0.465, PAINT_W, bev=0.008)]
    for lx, ly in [(0.17, 0.17), (0.17, -0.17), (-0.17, 0.17), (-0.17, -0.17)]:
        parts.append(cyl("zidle", lx, ly, 0.0, 0.44, 0.017, PAINT_W, seg=16))
    for ly in (0.17, -0.17): parts.append(cyl("zidle", -0.175, ly, 0.45, 0.905, 0.016, PAINT_W, seg=16))   # caps buried in seat / rail
    parts.append(cube("zidle", -0.20, -0.15, -0.20, 0.20, 0.84, 0.92, PAINT_W, bev=0.01))
    for j in range(5): parts.append(cyl("zidle", -0.175, -0.12 + j * 0.06, 0.455, 0.85, 0.008, PAINT_W, seg=12))
    for lx in (0.17, -0.17): parts.append(cyl("zidle", lx, 0.18, -0.17, 0.17, 0.008, PAINT_W, seg=12, axis="Y"))   # stretchers
    for p_ in parts: p_.data.transform(M)
    end()
if STUL2: TC = (TC[0] + D2[0] * SO, TC[1] + D2[1] * SO)
begin("MXY")
cyl("vaza_stul", TC[0], TC[1], TT, TT + 0.18, 0.045, GLASS, seg=32)
for j in range(5):
    tube("kvetina", [(TC[0], TC[1], TT + 0.05), (TC[0] + rnd.uniform(-0.08, 0.08), TC[1] + rnd.uniform(-0.08, 0.08), TT + 0.33 + rnd.uniform(0, 0.1))], 0.003,
         pmat("stonek", srgb(70, 110, 50), 0.6), rr=0)
for j in range(5):
    x_, y_ = TC[0] + rnd.uniform(-0.09, 0.09), TC[1] + rnd.uniform(-0.09, 0.09)
    bl_ = cube("kvet", x_ - 0.025, x_ + 0.025, y_ - 0.025, y_ + 0.025, TT + 0.33, TT + 0.38, pmat("kvet_m", srgb(235, 225, 210), 0.7), bev=0.02, seg=3, sub=1)
end()

# --- office chair at the desk (faces +b): five-star base, gas lift, seat, mesh back, arms
begin("FX", -3.25, 0.57, 0.0)
OFF = Matrix.Translation((-3.25, 0.57, 0))
parts = []
for k in range(5):
    a_ = math.radians(90 + 72 * k)
    parts.append(tube("kancelarska_zidle", [(0, 0, 0.09), (0.30 * math.cos(a_), 0.30 * math.sin(a_), 0.07)], 0.018, DARKPL, rr=0))
    parts.append(cyl("kancelarska_zidle", 0.30 * math.cos(a_), 0.30 * math.sin(a_), 0.0, 0.05, 0.025, DARKPL, seg=16))
parts.append(cyl("kancelarska_zidle", 0, 0, 0.08, 0.42, 0.028, STEEL, seg=20))
parts.append(cube("kancelarska_zidle", -0.24, 0.24, -0.24, 0.22, 0.42, 0.50, GREYF, bev=0.03, seg=3, sub=1))
bk = cube("kancelarska_zidle", -0.22, 0.22, -0.30, -0.26, 0.58, 1.08, DARKPL, bev=0.03, seg=3)
bk.data.transform(Matrix.Translation((0, -0.28, 0.58)) @ Matrix.Rotation(math.radians(-10), 4, "X") @ Matrix.Translation((0, 0.28, -0.58)))
parts.append(bk)
parts.append(tube("kancelarska_zidle", [(0, -0.20, 0.48), (0, -0.30, 0.56), (0, -0.30, 0.70)], 0.02, DARKPL, rr=0.05))
for sx in (-0.25, 0.25):
    parts.append(tube("kancelarska_zidle", [(sx, -0.05, 0.48), (sx, -0.05, 0.66), (sx, 0.12, 0.66)], 0.014, DARKPL, rr=0.04))
    parts.append(cube("kancelarska_zidle", sx - 0.03, sx + 0.03, -0.10, 0.16, 0.655, 0.68, DARKPL, bev=0.01))
for p_ in parts:
    if p_.type == "MESH": p_.data.transform(OFF)
    else: p_.data.transform(OFF)
end()

# --- hall wardrobe: three white sliding doors in alu frames (texture stays behind them)
L6 = 2.67
w6 = (L6 - 0.16) / 3
for k in range(3):
    s0, s1 = 0.08 + k * w6 - 0.012, 0.08 + (k + 1) * w6 + 0.012
    y0, y1 = (1.333, 1.351) if k == 1 else (1.352, 1.368)
    cube("skrin_dvere", 1.55 - s1, 1.55 - s0, y0, y1, 0.025, 2.14, PAINT_W, bev=0.002)
    for ss in (s0, s1 - 0.022):
        cube("skrin_profil", 1.55 - ss - 0.022, 1.55 - ss, y0 - 0.003, y1, 0.025, 2.14, STEEL, bev=0.002)
cube("skrin_kolejnice", 1.55 - L6 + 0.06, 1.49, 1.33, 1.369, 2.14, 2.20, STEEL)
cube("skrin_kolejnice", 1.55 - L6 + 0.06, 1.49, 1.33, 1.369, 0.0, 0.025, STEEL)


# ================================================================== round 3: bedroom (tour scene 736)
remove(("postel", "matrace", "prikryvka", "celo_postele"))
def check_mat(name, c1, c2, scale):
    """Gingham: stripes along x and along y (z on the sides) summed -> dark, mid and light squares."""
    m = D_.materials.new(name); m.use_nodes = True; nt = m.node_tree; p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["Object"], sep.inputs[0])
    st = []
    for comp in (0, 1, 2):
        mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = scale
        nt.links.new(sep.outputs[comp], mul.inputs[0])
        md = nt.nodes.new("ShaderNodeMath"); md.operation = "FLOORED_MODULO"; md.inputs[1].default_value = 2.0
        nt.links.new(mul.outputs[0], md.inputs[0])
        fl = nt.nodes.new("ShaderNodeMath"); fl.operation = "FLOOR"; nt.links.new(md.outputs[0], fl.inputs[0]); st.append(fl)
    geo = nt.nodes.new("ShaderNodeNewGeometry"); sn = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(geo.outputs["Normal"], sn.inputs[0])
    terms = []
    for comp in (0, 1, 2):                       # a stripe set counts only where it lies in the face plane
        ab = nt.nodes.new("ShaderNodeMath"); ab.operation = "ABSOLUTE"; nt.links.new(sn.outputs[comp], ab.inputs[0])
        om = nt.nodes.new("ShaderNodeMath"); om.operation = "SUBTRACT"; om.inputs[0].default_value = 1.0; nt.links.new(ab.outputs[0], om.inputs[1])
        mu = nt.nodes.new("ShaderNodeMath"); mu.operation = "MULTIPLY"; nt.links.new(st[comp].outputs[0], mu.inputs[0]); nt.links.new(om.outputs[0], mu.inputs[1])
        terms.append(mu)
    a1 = nt.nodes.new("ShaderNodeMath"); a1.operation = "ADD"; nt.links.new(terms[0].outputs[0], a1.inputs[0]); nt.links.new(terms[1].outputs[0], a1.inputs[1])
    a3 = nt.nodes.new("ShaderNodeMath"); a3.operation = "ADD"; nt.links.new(a1.outputs[0], a3.inputs[0]); nt.links.new(terms[2].outputs[0], a3.inputs[1])
    a2 = nt.nodes.new("ShaderNodeMath"); a2.operation = "MULTIPLY"; a2.inputs[1].default_value = 0.5; nt.links.new(a3.outputs[0], a2.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0; ramp.color_ramp.elements[0].color = (*c2, 1)
    ramp.color_ramp.elements[1].position = 0.4; ramp.color_ramp.elements[1].color = (*[(x + y) / 2 for x, y in zip(c1, c2)], 1)
    e = ramp.color_ramp.elements.new(0.9); e.color = (*c1, 1)
    nt.links.new(a2.outputs[0], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    set_(p, **{"Roughness": 1.0, "Sheen Weight": 0.6}); return fabric_bump(m, 1100, 0.15)
def zebra_mat(name, scale=7.0):
    """Black-and-white zebra print (current bedding and rug in the splat)."""
    m = D_.materials.new(name); m.use_nodes = True; nt = m.node_tree; p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord"); w = nt.nodes.new("ShaderNodeTexWave"); w.wave_type = "BANDS"; w.bands_direction = "DIAGONAL"
    w.inputs["Scale"].default_value = scale * 1.5; w.inputs["Distortion"].default_value = 6; w.inputs["Detail"].default_value = 2
    w.inputs["Detail Scale"].default_value = 1.6
    nt.links.new(tc.outputs["Object"], w.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB"); el = ramp.color_ramp.elements
    el[0].position = 0.42; el[0].color = (0.02, 0.02, 0.02, 1); el[1].position = 0.50; el[1].color = (0.80, 0.80, 0.79, 1)
    nt.links.new(w.outputs["Fac"], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    set_(p, **{"Roughness": 1.0, "Sheen Weight": 0.5}); return fabric_bump(m, 1100, 0.12)
DUVET = zebra_mat("povleceni_zebra")
PILLOWC = zebra_mat("povleceni_polstar_zebra", 9.0)
SHEET = fabric_bump(pmat("prosteradlo", srgb(236, 236, 234), 1.0, sheen=0.5), 1100, 0.1)
RUG = pmat("koberec", srgb(232, 230, 224), 1.0, sheen=1.0)
bump_from(RUG, RUG.node_tree.nodes["Principled BSDF"], 1.0, scale=450)
WR2 = D_.textures.new("vrasky2", "CLOUDS"); WR2.noise_scale = 0.12; WR2.noise_depth = 2
def wrinkle(ob, k=0.010, tex=WR2):
    sm = ob.modifiers.get("sub")
    if sm: sm.levels = sm.render_levels = 3
    dm = ob.modifiers.new("vrasky", "DISPLACE"); dm.texture = tex; dm.strength = k
def leaf_print(name):
    m = D_.materials.new(name); m.use_nodes = True; nt = m.node_tree; p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord"); w = nt.nodes.new("ShaderNodeTexWave"); w.wave_type = "RINGS"; w.wave_profile = "SAW"
    w.inputs["Scale"].default_value = 9.0; w.inputs["Distortion"].default_value = 5; w.inputs["Detail"].default_value = 2
    nt.links.new(tc.outputs["Object"], w.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB"); el = ramp.color_ramp.elements
    el[0].position = 0.86; el[0].color = (*srgb(78, 78, 82), 1); el[1].position = 0.93; el[1].color = (*srgb(225, 225, 222), 1)
    nt.links.new(w.outputs["Fac"], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    set_(p, **{"Roughness": 1.0, "Sheen Weight": 0.5}); return fabric_bump(m, 1100, 0.12)
LEAFP = leaf_print("povleceni_listy")
# beds measured on the splat in metres (iterace 06): 2.0 m long incl. headboard, 1.0 m wide, headboard on the west wall;
# the bed by the door ends 0.39 m before the door jamb (it used to run 0.6 m into the doorway)
begin("MET")
XW_ = -4.09 * S + 0.003                                              # west wall, metres
SOKL = pmat("sokl", srgb(90, 90, 92), 0.6)
for yc_, inner in ((1.965, 1), (4.605, -1)):                         # bed centres (splat, units)
    y0, y1 = yc_ * S - 0.46, yc_ * S + 0.46
    x0, x1 = XW_, XW_ + 2.04                                            # 2.04 m: ends 10 cm before the door frame
    cube("celo_postele", x0, x0 + 0.07, y0 - 0.01, y1 + 0.01, 0.05, 0.86, PAINT_W, bev=0.01)
    cube("postel_ram", x0 + 0.072, x1, y0, y1, 0.10, 0.32, PAINT_W, bev=0.008)
    cube("postel_sokl", x0 + 0.11, x1 - 0.04, y0 + 0.04, y1 - 0.04, 0.0, 0.10, SOKL, bev=0.004)
    yi = y1 if inner > 0 else y0                                                     # drawers on the side facing the room
    for xa, xb in ((x0 + 0.20, x0 + 1.04), (x0 + 1.09, x1 - 0.10)):
        cube("postel_suplik", xa, xb, yi if inner > 0 else yi - 0.005, yi + 0.005 if inner > 0 else yi, 0.13, 0.30, PAINT_W, bev=0.002)
    soft("matrace", x0 + 0.08, x1 - 0.02, y0 + 0.02, y1 - 0.02, 0.32, 0.50, SHEET, 0.03, 2)
    wrinkle(soft("perina", x0 + 0.62, x1 + 0.02, y0 - 0.025, y1 + 0.025, 0.385, 0.565, LEAFP, 0.06, 2), 0.012)
    wrinkle(soft("perina_lem", x0 + 0.55, x0 + 0.73, y0 - 0.025, y1 + 0.025, 0.50, 0.59, LEAFP, 0.045, 2), 0.008)
    pl = soft("polstar_postel", x0 + 0.10, x0 + 0.48, y0 + 0.12, y1 - 0.12, 0.50, 0.65, LEAFP, 0.07, 2); wrinkle(pl, 0.006)
    pl.data.transform(Matrix.Translation((x0 + 0.29, (y0 + y1) / 2, 0.5)) @ Matrix.Rotation(math.radians(-14), 4, "Y")
                      @ Matrix.Translation((-(x0 + 0.29), -(y0 + y1) / 2, -0.5)))
end()
LAMP_SH = pmat("stinitko", srgb(238, 234, 226), 0.9, transm=0.25)
# desk with metal legs under the window, between the nightstands (footprint from the splat, real 0.745 m top)
begin("SXY")
cube("stul_okno", -4.03, -3.55, 2.96, 3.66, 0.72, 0.745, PAINT_W, bev=0.004)
for yy_ in (3.00, 3.62):
    cube("stul_okno_noha", -3.82, -3.78, yy_ - 0.02, yy_ + 0.02, 0.0, 0.72, STEEL)
    cube("stul_okno_noha", -4.00, -3.58, yy_ - 0.02, yy_ + 0.02, 0.0, 0.03, STEEL)
end()
begin("FX", -3.78, 3.89, 0.50); cube("router", -3.90, -3.66, 3.80, 3.98, 0.50, 0.56, pmat("modra_krabicka", srgb(60, 110, 190), 0.4), bev=0.005); end()
# desk + monitor + white chair at the north wall, by the wardrobe
begin("SXY")
cube("stul_sever", -2.03, -1.10, 4.74, 5.29, 0.72, 0.745, PAINT_W, bev=0.004)                  # splat: against the north wall
for xx_ in (-2.01, -1.12):
    cube("stul_sever_noha", xx_ - 0.015, xx_ + 0.015, 4.76, 5.27, 0.0, 0.72, PAINT_W)
end()
begin("FX", -1.55, 5.20, 0.0)
cube("monitor", -1.78, -1.32, 5.20, 5.23, 0.82, 1.10, DARKPL); cube("monitor_noha", -1.57, -1.53, 5.22, 5.26, 0.745, 0.85, DARKPL)
cube("monitor_podstava", -1.66, -1.44, 5.14, 5.27, 0.745, 0.757, DARKPL, bev=0.004)
cube("klavesnice", -1.72, -1.38, 4.86, 4.99, 0.745, 0.765, DARKPL, bev=0.003)
end()
CH = pmat("zidle_bila_plast", (0.86, 0.86, 0.85), 0.25)
begin("FX", -1.55, 4.55, 0.0)
cube("zidle_bila", -1.76, -1.34, 4.35, 4.75, 0.44, 0.47, CH, bev=0.02, seg=3)
cube("zidle_bila", -1.76, -1.34, 4.33, 4.38, 0.47, 0.88, CH, bev=0.02, seg=3)                 # back away from the desk
for xx_, yy_ in ((-1.74, 4.37), (-1.36, 4.37), (-1.74, 4.73), (-1.36, 4.73)): cyl("zidle_bila", xx_, yy_, 0.0, 0.445, 0.012, STEEL, seg=12)
end()
for yc in (2.71, 3.89):
    cube("nocni_spara", -3.600, -3.596, yc - 0.18, yc + 0.18, 0.328, 0.332, pmat("spara2", srgb(160, 160, 160), 0.6))
    cyl("nocni_knopka", yc, 0.41, -3.596, -3.58, 0.012, STEEL, axis="X")
for yc in (2.71,):                                                       # lamp only on the bed-side stand (current)
    begin("FX", -3.82, yc, 0.50)
    cyl("lampicka", -3.82, yc, 0.50, 0.52, 0.06, PAINT_W); cyl("lampicka", -3.82, yc, 0.52, 0.76, 0.008, STEEL)
    sh = cyl("lampicka_stinitko", -3.82, yc, 0.70, 0.86, 0.10, LAMP_SH, seg=40)
    bm = bmesh.new(); bm.from_mesh(sh.data); bmesh.ops.delete(bm, geom=[f for f in bm.faces if abs(f.normal.z) > 0.9], context="FACES")
    for v in bm.verts:
        if v.co.z > 0.8: v.co.x = -3.82 + (v.co.x + 3.82) * 0.7; v.co.y = yc + (v.co.y - yc) * 0.7
    bm.to_mesh(sh.data); bm.free(); sh.modifiers.new("solid", "SOLIDIFY").thickness = 0.003
    end()
for yb in (3.20, 3.28, 3.85):                                                    # bar handles (doors 1+2 a pair, 3 single)
    begin("FX", -0.775, yb, 0.0)
    cube("satnik_madlo", -0.807, -0.793, yb - 0.006, yb + 0.006, 0.92, 1.24, STEEL, bev=0.003)
    for zz in (0.95, 1.21): cube("satnik_madlo", -0.794, -0.776, yb - 0.004, yb + 0.004, zz - 0.004, zz + 0.004, STEEL)
    end()
for o in D_.objects:                                                                  # glossy wardrobe like the tour
    if o.type == "MESH" and o.name.startswith("satnik") and o.dimensions.x > 0.1:
        o.data.materials[0] = pmat("satnik_lesk", (0.88, 0.88, 0.87), 0.12, coat=0.8)


# --- switches and sockets where a flat has them: by every door, above the worktop, by the beds and the desk
def switch(x, y, z, face, w=0.085, h=0.085, double=False):
    """face: outward normal of the wall it sits on, as (dx, dy)."""
    dx, dy = face; t = 0.011
    if dx: cube("vypinac", x, x + dx * t, y - w / 2, y + w / 2, z - h / 2, z + h / 2, PLASTIC_W, bev=0.003)
    else: cube("vypinac", x - w / 2, x + w / 2, y, y + dy * t, z - h / 2, z + h / 2, PLASTIC_W, bev=0.003)
for args in [((-1.36, 1.26, 1.10), (0, -1)), ((-1.36, 1.41, 1.10), (0, 1)), ((2.74, 1.85, 1.10), (0, -1)), ((2.735, 1.95, 1.10), (0, 1)),
             ((3.64, 2.05, 1.10), (1, 0)), ((5.76, 2.10, 1.10), (-1, 0)), ((1.92, -2.05, 1.02), (-1, 0)), ((1.92, -3.70, 1.02), (-1, 0)),
             ((-2.40, 1.26, 0.30), (0, -1)), ((-4.09, -1.70, 0.30), (1, 0)), ((-4.09, 2.55, 0.62), (1, 0)), ((-4.09, 4.04, 0.62), (1, 0))]:
    (x, y, z), f = args
    begin("FX", x, y, 0.0); switch(x, y, z, f); end()


# ================================================================== round 6: kitchen sink recess, hob, oven, monitor stands, diffusers
remove(("drez",))
cut_box = lambda: cube("rez", 1.755, 2.125, -3.19, -2.76, 0.40, 0.80, PLASTIC_W)
for o in list(D_.objects):
    if o.type != "MESH" or not o.name.startswith("kuchyn"): continue
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector([min(v[i] for v in bb) for i in range(3)]); hi = Vector([max(v[i] for v in bb) for i in range(3)])
    if lo.x < 1.9 < hi.x and lo.y < -2.97 < hi.y and hi.z > 0.60 and (hi.x - lo.x) > 0.3:
        boolean_cut(o, cut_box())
sink = bowl_body("drez_nerez", [(1.735, -3.21), (2.145, -3.21), (2.145, -2.74), (1.735, -2.74)], (1.94, -2.975), 0.18, 0.205, 0.53, 0.703, 0.165, STEEL)
bevel(sink, 0.004, 2)
cyl("drez_vytok", 1.94, -2.975, 0.5385, 0.541, 0.035, CHROME)
for cx, cy, rr_ in [(1.81, -3.94, 0.095), (1.81, -3.71, 0.075), (2.01, -3.94, 0.075), (2.01, -3.71, 0.095)]:
    ring_solid("varna_zona", (cx, cy), rr_, rr_, rr_ - 0.004, rr_ - 0.004, 0.7202, 0.7206, pmat("zona", (0.35, 0.35, 0.36), 0.3))
tube("trouba_madlo", [(1.68, -2.25, 0.555), (1.645, -2.25, 0.555), (1.645, -1.77, 0.555), (1.68, -1.77, 0.555)], 0.009, STEEL, rr=0.02)
cube("trouba_panel", 1.674, 1.68, -2.30, -1.72, 0.565, 0.62, pmat("panel_trouby", (0.03, 0.03, 0.035), 0.2, coat=1.0))
# white filler panels close the kitchen units up to the ceiling (tour)
cube("kuchyn_lista", 1.858, 1.872, -4.69, -1.00, 2.20, 2.304, PAINT_W)
cube("kuchyn_lista", 1.678, 1.692, -1.00, 0.45, 2.20, 2.304, PAINT_W)
cube("kuchyn_lista", 1.692, 1.872, -1.006, -0.994, 2.20, 2.304, PAINT_W)
# white caps over the door openings at wall-top level (hide frame edges and lintel slits in the cut-away view)
WALLW = pmat("zed_cap", srgb(236, 233, 226), 0.9)
for (x0, x1, y0, y1) in [(-2.30, -1.45, 1.24, 1.43), (1.85, 2.73, 1.83, 1.97), (1.66, 2.22, -4.69, 0.45)]:   # + kitchen top
    cube("zed_cap", x0, x1, y0, y1, 2.3105, 2.3125, WALLW)            # wholly above the ceiling plane
# monitors stand on their desks
for (xa, xb, y0, y1, zt) in [(-3.42, -3.18, 1.06, 1.24, 0.625 * S)]:
    begin("FX", -3.30, 1.20, 0.0)
    cube("monitor_noha", -3.32, -3.28, 1.19, 1.23, zt, 0.86, DARKPL); cube("monitor_podstava", xa, xb, y0, y1, zt, zt + 0.012, DARKPL, bev=0.004)
    end()
for ca in (-0.05, 0.75):
    begin("FX", ca + 0.275, -4.60, 0.0)
    cube("monitor_noha", ca + 0.255, ca + 0.295, -4.62, -4.58, 0.585 * S, 0.585 * S + 0.14, DARKPL)
    cube("monitor_podstava", ca + 0.16, ca + 0.39, -4.66, -4.49, 0.585 * S, 0.585 * S + 0.012, DARKPL, bev=0.004)
    end()
# swirl diffusers in the coffered ceiling (seen on the splat ceiling and in every tour room), snapped to the 60 cm grid
def swirl(x, y):
    cube("vyustka_deska", x - 0.296, x + 0.296, y - 0.296, y + 0.296, 2.300, 2.3085, PLASTIC_W)
    bm = bmesh.new(); BL = pmat("vyustka_cerna", (0.02, 0.02, 0.02), 0.5) if "vyustka_cerna" not in D_.materials else D_.materials["vyustka_cerna"]
    for k in range(14):
        th0 = 2 * math.pi * k / 14
        rs = [0.06 + 0.18 * i / 6 for i in range(7)]
        A = [(x + r * math.cos(th0 + 0.9 * (r - 0.06) / 0.18), y + r * math.sin(th0 + 0.9 * (r - 0.06) / 0.18)) for r in rs]
        B = [(x + r * math.cos(th0 + 0.13 + 0.9 * (r - 0.06) / 0.18), y + r * math.sin(th0 + 0.13 + 0.9 * (r - 0.06) / 0.18)) for r in rs]
        va = [bm.verts.new((px, py, 2.2994)) for px, py in A]; vb = [bm.verts.new((px, py, 2.2994)) for px, py in B]
        for i in range(6): bm.faces.new((va[i], vb[i], vb[i + 1], va[i + 1]))
    bm.normal_update()
    for f in bm.faces:
        if f.normal.z > 0: f.normal_flip()
    me = D_.meshes.new("vyustka"); bm.to_mesh(me); bm.free(); ob = link(D_.objects.new("vyustka", me)); me.materials.append(BL)
    cyl("vyustka_stred", x, y, 2.2982, 2.2989, 0.055, BL, seg=32)   # below the vanes, off the plate
for x, y in [(-2.89, -1.25), (-1.09, -3.05), (-1.69, 2.95)]:
    x, y = snap(x, y); begin("FX", x, y, H_U); swirl(x, y); end()

# ------------------------------------------------------------------ curves -> meshes (bake needs meshes)
vl = bpy.context.view_layer
for o in vl.objects: o.select_set(False)
for o in CURVES: o.select_set(True)
if CURVES:
    vl.objects.active = CURVES[0]; bpy.ops.object.convert(target="MESH")
for o in D_.objects:
    if o.type == "MESH" and o.name.startswith(("led_panel", "led_bodovka")):
        o.visible_shadow = False                                  # the area light just below must not be blocked
print("DETAIL done", flush=True)

# ------------------------------------------------------------------ metric placement of every object (see placement())
for o in list(D_.objects):
    if o.type in ("MESH", "CURVE"):
        o.matrix_world = placement(MODE.get(o.name, ("SC",))) @ o.matrix_world
print("METRIC placed", len([1 for o in D_.objects if o.type == "MESH"]), "objects;", sum(1 for m in MODE.values() if m[0] != "SC"), "not plain-scaled", flush=True)

# ------------------------------------------------------------------ z-fighting cure (shared planes -> 1 mm shrink)
exec(open(os.path.join(HERE, "zfix.py")).read())
