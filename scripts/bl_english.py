"""Health.Lab Model 1.0.8: English names for the parts of the .blend a user touches (root empty, the camera / mat
collections, the render camera). Usage: Blender -b IN.blend -P bl_english.py -- OUT.blend (model|wishcap|captury)"""
import bpy, sys
argv = sys.argv[sys.argv.index("--") + 1:]
ROOM = {"pokojicek": "bedroom", "koupelna": "bathroom", "obyvak": "living_room", "chodbicka": "hallway"}
DESC = {"wishcap": "The flat in the frame of WishCap panel takes (calibration camera-2026-02.calib). Import an FBX/glTF take with default settings and it lines up.",
        "captury": "The flat where Blender puts an FBX exported by Captury (calibration shot_003, e.g. Dataset_klekz). Import with default settings and it lines up."}
root = bpy.data.objects.get("byt_v_mocap_ramci")
if root:
    root.name = "flat_in_mocap_frame"; root.pop("popis", None); root["description"] = DESC[argv[1]]
for old, new in (("kamery_wishcap", "wishcap_cameras"), ("matrace_2x2m", "mat_2x2m")):
    if old in bpy.data.collections: bpy.data.collections[old].name = new
for o in bpy.data.objects:
    if o.type == "CAMERA" and o.name.startswith("kamera_") and o.name != "kamera":
        _, i, room = o.name.split("_", 2); o.name = f"cam_{i}_{ROOM.get(room, room)}"; o.data.name = f"cam_{i}"
        if "kalibrace" in o: o["calibration"] = o.pop("kalibrace")
    elif o.name == "kamera": o.name = "render_camera"
    elif o.name == "matrace_2x2m":
        o.name = "mat_2x2m"; o.data.name = "mat_2x2m"
        if "zaobleni" in o.modifiers: o.modifiers["zaobleni"].name = "bevel"
if "matrace_modra" in bpy.data.materials: bpy.data.materials["matrace_modra"].name = "mat_blue"
print("NAMES", [c.name for c in bpy.data.collections], root.name if root else None, flush=True)
bpy.ops.wm.save_as_mainfile(filepath=argv[0], copy=True); print("SAVED", argv[0], flush=True)
