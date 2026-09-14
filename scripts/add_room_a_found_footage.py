#!/usr/bin/env python3
"""Room A 30s found-footage camcorder take on the EXISTING backrooms.blend.

Does not rebuild walls, floor, ceiling, or lights. No formal Cycles render.

  blender -b backrooms.blend --python scripts/add_room_a_found_footage.py -- --check
  blender -b backrooms.blend --python scripts/add_room_a_found_footage.py -- --preview
"""

from __future__ import annotations

import math
import random
import subprocess
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "backrooms.blend"
PREVIEW_DIR = ROOT / "renders" / "room_a_preview"

FPS = 30
DURATION = 30.0
COLL = "CAM_FOUND_FOOTAGE"
FX_COLL = "FX_DRIED_BLOOD"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

# Room A interior (measured from backrooms.blend, do not change walls):
#   x -5.80 .. -1.60   y 1.00 .. 4.80
# East door: x -1.60 .. -1.40, y 3.00 .. 4.60
BLOOD_C = (-2.08, 1.30)


def parse_args() -> dict:
    mode = "check"
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--preview" in argv:
        mode = "preview"
    return {"mode": mode}


def frame_at(t: float) -> int:
    return max(1, min(900, int(round(1 + t * FPS))))


def lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def smoothstep(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def iter_fcurves(id_data):
    ad = getattr(id_data, "animation_data", None)
    if ad is None or ad.action is None:
        return
    act = ad.action
    fcurves = getattr(act, "fcurves", None)
    if fcurves:
        yield from fcurves
        return
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            bags = list(strip.channelbags) if hasattr(strip, "channelbags") else []
            if not bags and act.slots:
                bag = strip.channelbag(act.slots[0])
                if bag is not None:
                    bags = [bag]
            for bag in bags:
                yield from bag.fcurves


def insert_xyz(obj, path: str, frame: int, value, interp: str = "BEZIER") -> None:
    if path == "location":
        obj.location = Vector(value)
    elif path == "rotation_euler":
        obj.rotation_euler = value
    obj.keyframe_insert(data_path=path, frame=frame)
    for fc in iter_fcurves(obj):
        if fc.data_path != path:
            continue
        for kp in fc.keyframe_points:
            if int(round(kp.co[0])) == frame:
                kp.interpolation = interp
                kp.handle_left_type = "AUTO_CLAMPED"
                kp.handle_right_type = "AUTO_CLAMPED"


def add_noise_mods(obj, data_path: str, scale: float, strength: float, seed: float) -> None:
    n = 0
    for fc in iter_fcurves(obj):
        if fc.data_path != data_path:
            continue
        for mod in list(fc.modifiers):
            if mod.type == "NOISE":
                fc.modifiers.remove(mod)
        mod = fc.modifiers.new("NOISE")
        mod.scale = scale + 1.1 * n
        mod.strength = strength
        mod.phase = seed + n * 2.3
        mod.depth = 0
        n += 1


def sample_keys(keys, t, nvals=3):
    if t <= keys[0][0]:
        return keys[0][1:]
    for a, b in zip(keys, keys[1:]):
        if a[0] <= t <= b[0]:
            u = smoothstep((t - a[0]) / max(1e-6, b[0] - a[0]))
            return tuple(lerp(a[i], b[i], u) for i in range(1, nvals + 1))
    return keys[-1][1:]


def hide_previous_take() -> None:
    old = bpy.data.collections.get("CAM_FOUND_FOOTAGE_01")
    if old is not None:
        old.hide_viewport = True
        old.hide_render = True
        for obj in old.objects:
            obj.hide_viewport = True
            obj.hide_render = True


def clear_this_take() -> None:
    for name in (COLL, FX_COLL):
        if name in bpy.data.collections:
            col = bpy.data.collections[name]
            for obj in list(col.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(col)
    for name in (
        "POV_ROOT",
        "BODY_MOTION",
        "HEAD_MOTION",
        "HAND_MOTION",
        "CAM_MAIN",
        "CAM_OSD",
        "OSD_TIME",
        "OSD_REC",
        "OSD_REC_DOT",
        "OSD_BATT",
        "OSD_BATT_FILL",
        "OSD_MODE",
        "BLOOD.RoomA.Dried",
        "CAM_PATH_GUIDE",
    ):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)


def new_col(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def make_empty(name: str, col, size=0.16) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = size
    col.objects.link(obj)
    return obj


def parent_local(child, parent_obj) -> None:
    child.parent = parent_obj
    child.matrix_parent_inverse.identity()


def emissive(name, color, strength=1.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    mat.blend_method = "OPAQUE"
    return mat


def make_blood(col) -> bpy.types.Object:
    rng = random.Random(17)
    bm = bmesh.new()
    n = 36
    verts = []
    cx, cy = BLOOD_C
    for i in range(n):
        a = (2.0 * math.pi * i) / n
        r = (
            0.46
            + 0.16 * math.sin(i * 0.73 + 0.2)
            + 0.11 * math.sin(i * 1.91 + 1.4)
            + 0.07 * math.sin(i * 3.4)
            + rng.uniform(-0.05, 0.05)
        )
        x = cx + r * math.cos(a) * 1.18
        y = cy + r * math.sin(a) * 0.78
        x = min(-1.72, max(-2.72, x))
        y = min(1.92, max(1.12, y))
        verts.append(bm.verts.new((x, y, 0.0018)))
    face = bm.faces.new(verts)
    # Extra irregular lobes near the east wall.
    geom = bmesh.ops.extrude_face_region(bm, geom=[face])
    verts2 = [g for g in geom["geom"] if isinstance(g, bmesh.types.BMVert)]
    for v in verts2:
        v.co.z = 0.0004
    mesh = bpy.data.meshes.new("BLOOD.RoomA.Dried")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("BLOOD.RoomA.Dried", mesh)
    col.objects.link(obj)

    mat = bpy.data.materials.new("MAT.DriedBlood")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 18.0
    tex.inputs["Detail"].default_value = 8.0
    tex.inputs["Roughness"].default_value = 0.62
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.28
    ramp.color_ramp.elements[0].color = (0.012, 0.004, 0.003, 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (0.045, 0.012, 0.008, 1.0)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.94
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.04
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.04
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    obj.data.materials.append(mat)
    return obj


def make_rect(name, col, w, h, d=0.0004):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.scale = (w, h, d)
    col.objects.link(obj)
    return obj


def make_disc(name, col, radius=0.0016):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, cap_tris=True, segments=16, radius=radius)
    for v in bm.verts:
        v.co.z = 0.0
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    return obj


def make_text(name, col, body, size=0.0034):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size
    curve.align_x = "LEFT"
    curve.align_y = "CENTER"
    if Path(FONT).exists():
        curve.font = bpy.data.fonts.load(FONT)
    obj = bpy.data.objects.new(name, curve)
    col.objects.link(obj)
    return obj


def build_osd(col, cam) -> bpy.types.Object:
    osd = make_empty("CAM_OSD", col, 0.04)
    parent_local(osd, cam)
    # Screen-space: camera looks -Z, +X right, +Y up. Sit on the near plane.
    dist = 0.052
    osd.location = (0.0, 0.0, -dist)
    osd.rotation_euler = (0.0, 0.0, 0.0)
    w = dist * 36.0 / 28.0
    h = dist * 27.0 / 28.0
    white = emissive("MAT.OSD.White", (0.86, 0.90, 0.82), 3.5)
    red = emissive("MAT.OSD.Red", (0.85, 0.07, 0.04), 6.0)
    dark = emissive("MAT.OSD.Dark", (0.08, 0.09, 0.07), 0.8)
    amber = emissive("MAT.OSD.Amber", (0.75, 0.18, 0.04), 5.0)

    batt = make_rect("OSD_BATT", col, 0.0072, 0.0036)
    parent_local(batt, osd)
    batt.location = (-w * 0.42, h * 0.40, 0.0008)
    batt.data.materials.append(dark)
    fill = make_rect("OSD_BATT_FILL", col, 0.00055, 0.0024)
    parent_local(fill, osd)
    fill.location = (-w * 0.42 - 0.0026, h * 0.40, 0.0012)
    fill.data.materials.append(amber)
    nip = make_rect("OSD_BATT_NIP", col, 0.0007, 0.0015)
    parent_local(nip, osd)
    nip.location = (-w * 0.42 + 0.0041, h * 0.40, 0.0008)
    nip.data.materials.append(dark)

    rec_dot = make_disc("OSD_REC_DOT", col, 0.0015)
    parent_local(rec_dot, osd)
    rec_dot.location = (w * 0.38, h * 0.40, 0.0008)
    rec_dot.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    rec_dot.data.materials.append(red)
    rec = make_text("OSD_REC", col, "REC", 0.0030)
    parent_local(rec, osd)
    rec.location = (w * 0.38 + 0.0024, h * 0.40, 0.0008)
    rec.data.materials.append(red)

    time = make_text("OSD_TIME", col, "0:23:51", 0.0036)
    parent_local(time, osd)
    time.location = (-0.010, -h * 0.41, 0.0008)
    time.data.materials.append(white)

    mode = make_text("OSD_MODE", col, "SP  4:3", 0.0022)
    parent_local(mode, osd)
    mode.location = (w * 0.22, -h * 0.41, 0.0008)
    mode.data.materials.append(white)

    for obj in (osd, batt, fill, nip, rec_dot, rec, time, mode):
        obj.show_in_front = True
        obj.hide_render = False
        obj.display_type = "SOLID"
    return osd


def osd_frame_handler(scene):
    f = scene.frame_current
    t = max(0.0, (f - 1) / float(FPS))
    clock = 23 * 60 + 51 + t
    mm = int(clock // 60)
    ss = int(clock % 60)
    time = bpy.data.objects.get("OSD_TIME")
    if time is not None and time.type == "FONT":
        time.data.body = f"{mm // 60}:{mm % 60:02d}:{ss:02d}" if mm >= 60 else f"0:{mm:02d}:{ss:02d}"
    rec = bpy.data.objects.get("OSD_REC")
    dot = bpy.data.objects.get("OSD_REC_DOT")
    rec_on = (f % 30) < 16
    for obj in (rec, dot):
        if obj is not None:
            obj.hide_viewport = not rec_on
            obj.hide_render = not rec_on
    fill = bpy.data.objects.get("OSD_BATT_FILL")
    if fill is not None:
        batt_on = (f % 44) < 30
        fill.hide_viewport = not batt_on
        fill.hide_render = not batt_on


def register_osd_handler():
    for h in list(bpy.app.handlers.frame_change_pre):
        if getattr(h, "__name__", "") == "osd_frame_handler":
            bpy.app.handlers.frame_change_pre.remove(h)
    bpy.app.handlers.frame_change_pre.append(osd_frame_handler)


def build_rig(col):
    root = make_empty("POV_ROOT", col, 0.22)
    body = make_empty("BODY_MOTION", col, 0.12)
    head = make_empty("HEAD_MOTION", col, 0.10)
    hand = make_empty("HAND_MOTION", col, 0.08)
    data = bpy.data.cameras.new("CAM_MAIN")
    data.lens = 28.0
    data.sensor_width = 36.0
    data.sensor_height = 27.0
    data.sensor_fit = "HORIZONTAL"
    data.clip_start = 0.04
    data.clip_end = 40.0
    data.dof.use_dof = False
    cam = bpy.data.objects.new("CAM_MAIN", data)
    col.objects.link(cam)

    root.location = (-5.38, 2.48, 0.10)
    root.rotation_euler = (0.0, 0.0, math.radians(92.0))
    body.location = (0, 0, 0)
    head.location = (0, 0, 0)
    head.rotation_euler = (math.radians(90.0 + 8.0), math.radians(22.0), 0.0)
    hand.location = (0, 0, 0)
    cam.location = (0, 0, 0)
    cam.rotation_euler = (0, 0, 0)

    parent_local(body, root)
    parent_local(head, body)
    parent_local(hand, head)
    parent_local(cam, hand)
    bpy.context.scene.camera = cam
    return root, body, head, hand, cam


# t, x, y, z, yaw_deg  (yaw 0=north, +90=west, -90=east, ±180=south)
ROOT_KEYS = [
    (0.00, -5.38, 2.48, 0.100, 92.0),
    (2.00, -5.379, 2.481, 0.101, 92.4),
    (2.12, -5.370, 2.488, 0.108, 94.0),
    (2.22, -5.355, 2.505, 0.155, 86.0),
    (2.38, -5.325, 2.460, 0.240, 104.0),
    (2.70, -5.280, 2.510, 0.560, 74.0),
    (3.15, -5.235, 2.430, 0.980, 48.0),
    (3.65, -5.195, 2.360, 1.380, 14.0),
    (4.20, -5.155, 2.310, 1.550, -10.0),
    (5.00, -5.120, 2.270, 1.610, -24.0),
    (5.50, -5.020, 2.180, 1.615, -36.0),
    (6.25, -4.680, 1.980, 1.600, -52.0),
    (6.55, -4.560, 1.900, 1.590, -60.0),
    (6.72, -4.548, 1.892, 1.595, -62.0),
    (7.20, -4.490, 1.855, 1.568, -64.0),
    (7.55, -4.610, 1.930, 1.612, -58.0),
    (8.00, -4.600, 1.950, 1.608, -50.0),
    (9.20, -4.585, 1.980, 1.610, -18.0),
    (10.40, -4.570, 2.020, 1.612, 12.0),
    (11.40, -4.555, 2.050, 1.608, -8.0),
    (12.20, -4.500, 2.140, 1.612, -22.0),
    (13.10, -4.080, 2.520, 1.608, 6.0),
    (13.55, -4.050, 2.560, 1.605, 10.0),
    (14.50, -3.520, 3.180, 1.615, 22.0),
    (15.40, -3.150, 3.520, 1.608, -8.0),
    (16.20, -2.720, 3.220, 1.612, -48.0),
    (17.00, -2.320, 3.020, 1.608, -78.0),
    (17.80, -2.100, 2.930, 1.605, -88.0),
    (18.50, -2.015, 2.875, 1.600, -93.0),
    (19.80, -2.012, 2.872, 1.602, -90.0),
    (20.80, -2.000, 2.868, 1.600, -86.0),
    (21.40, -1.995, 2.860, 1.598, -92.0),
    (24.80, -1.992, 2.858, 1.600, -90.0),
    (26.20, -1.990, 2.862, 1.600, -82.0),
    (26.80, -1.980, 2.900, 1.605, -70.0),
    (27.25, -1.920, 3.32, 1.608, -48.0),
    (27.70, -1.520, 3.48, 1.610, -80.0),
    (28.20, -0.980, 3.38, 1.605, -120.0),
    (28.70, -0.640, 3.05, 1.598, -150.0),
    (29.15, -0.555, 2.80, 1.592, -170.0),
    (29.50, -0.528, 2.690, 1.590, -176.0),
    (30.00, -0.518, 2.665, 1.588, -172.0),
]

# additive head: pitch, yaw, roll (degrees)
LOOK_KEYS = [
    (0.00, 9.0, 2.0, 22.0),
    (2.00, 8.5, 2.4, 21.5),
    (2.20, 14.0, -4.0, 28.0),
    (2.40, 4.0, 8.0, 12.0),
    (2.80, -6.0, -10.0, -8.0),
    (3.30, 8.0, 6.0, 10.0),
    (3.90, 2.0, -4.0, -3.0),
    (4.50, 0.5, 3.0, 2.5),
    (5.00, -2.0, 4.0, 1.0),
    (5.80, -12.0, -18.0, 0.6),
    (6.50, -22.0, -32.0, 0.8),
    (6.75, -24.0, -40.0, 0.4),
    (7.20, -28.0, -42.0, 0.5),
    (7.55, -18.0, -22.0, 0.3),
    (8.00, -10.0, -8.0, 0.2),
    (8.55, -4.0, 6.0, 0.4),
    (9.10, 8.0, 14.0, 0.6),
    (9.35, 10.0, 18.0, 0.8),
    (9.55, 8.5, 16.0, 0.4),
    (10.10, 2.0, -2.0, 0.2),
    (10.70, 1.0, -22.0, -0.4),
    (11.00, 1.4, -26.0, -0.5),
    (11.20, 1.0, -23.0, -0.2),
    (11.80, 0.4, -8.0, 0.2),
    (12.40, 0.8, 4.0, 0.3),
    (13.20, 1.2, 10.0, 0.4),
    (14.20, 0.6, -4.0, 0.2),
    (15.30, 2.5, 8.0, 0.3),
    (16.40, 0.5, -6.0, 0.2),
    (17.20, 0.8, 4.0, 0.2),
    (18.20, 1.0, 8.0, 0.3),
    (18.70, 2.0, 18.0, 0.4),
    (19.05, 3.0, 96.0, 1.2),
    (19.22, 2.4, 112.0, 1.6),
    (19.40, 2.0, 104.0, 0.8),
    (19.80, 1.6, 100.0, 0.5),
    (20.40, 1.0, 42.0, 0.3),
    (21.00, 0.6, 8.0, 0.2),
    (21.50, 0.4, -6.0, 0.2),
    (22.10, 1.0, -18.0, 0.3),
    (22.70, 0.8, -28.0, 0.4),
    (23.20, 0.6, -24.0, 0.3),
    (23.80, 0.5, -8.0, 0.2),
    (24.40, 0.8, -22.0, 0.3),
    (25.10, 0.6, -30.0, 0.4),
    (25.70, 0.5, -26.0, 0.3),
    (26.40, 0.8, -12.0, 0.2),
    (27.20, 1.2, 6.0, 0.3),
    (28.10, 0.6, -4.0, 0.2),
    (28.80, 2.0, 8.0, 0.3),
    (29.20, 1.0, 14.0, 0.4),
    (29.45, 0.8, 18.0, 0.3),
    (29.62, 0.6, 10.0, 0.2),
    (29.80, 1.2, -16.0, 0.3),
    (30.00, 0.8, -22.0, 0.2),
]

# Head local translation for corner peek (local -X is left).
PEEK_KEYS = [
    (0.00, 0.0, 0.0, 0.0),
    (21.40, 0.0, 0.0, 0.0),
    (22.00, -0.02, 0.004, 0.0),
    (22.55, -0.11, 0.012, 0.008),
    (23.05, -0.13, 0.010, 0.006),
    (23.55, -0.08, 0.004, 0.002),
    (24.05, -0.05, 0.002, 0.0),
    (24.55, -0.10, 0.010, 0.006),
    (25.15, -0.145, 0.014, 0.010),
    (25.70, -0.12, 0.008, 0.004),
    (26.30, -0.04, 0.002, 0.0),
    (27.00, 0.0, 0.0, 0.0),
    (30.00, 0.0, 0.0, 0.0),
]

WALK_SPANS = [
    (12.20, 13.35),
    (13.80, 16.85),
    (17.20, 18.20),
    (26.90, 29.20),
]


def walk_weight(t: float) -> float:
    best = 0.0
    for a, b in WALK_SPANS:
        if a <= t <= b:
            edge = min(t - a, b - t, 0.28) / 0.28
            best = max(best, smoothstep(max(0.0, min(1.0, edge))))
    return best


def build_steps():
    rng = random.Random(41)
    steps = []
    t = 0.0
    while t < DURATION + 1.0:
        d = rng.uniform(0.55, 0.72)
        amp_z = rng.uniform(0.012, 0.025)
        amp_x = rng.uniform(0.008, 0.020)
        amp_y = rng.uniform(0.004, 0.010)
        steps.append((t, t + d, amp_z, amp_x, amp_y, 1 if len(steps) % 2 == 0 else -1))
        t += d
    return steps


STEPS = build_steps()


def body_offset(t: float):
    w = walk_weight(t)
    z = x = y = 0.0
    roll = pitch = yaw = 0.0
    if w > 1e-4:
        for a, b, az, ax, ay, side in STEPS:
            if a <= t <= b:
                u = (t - a) / max(1e-6, b - a)
                bump = math.sin(math.pi * u)
                z = w * az * bump
                x = w * ax * side * math.sin(math.pi * u)
                y = w * ay * math.sin(2.0 * math.pi * u) * 0.45
                roll = w * math.radians(0.35 * side * math.sin(math.pi * u))
                pitch = w * math.radians(-0.22 * bump)
                yaw = w * math.radians(0.18 * side * math.sin(math.pi * u * 0.5))
                break
    # Breathing always, stronger when idle.
    br = 3.55 + 0.55 * math.sin(t * 0.17)
    breath = (0.0024 + 0.0018 * (1.0 - w)) * math.sin(t * 2.0 * math.pi / br)
    breath += 0.0006 * math.sin(t * 1.13 + 0.4)
    z += breath
    x += (0.0008 + 0.0005 * (1.0 - w)) * math.sin(t * 0.62 + 0.9)
    return x, y, z, pitch, roll, yaw


def animate(root, body, head, hand):
    dt = 1.0 / FPS
    t = 0.0
    last = -1
    while t <= DURATION + 1e-6:
        f = frame_at(t)
        if f != last:
            x, y, z, yaw = sample_keys(ROOT_KEYS, t, 4)
            insert_xyz(root, "location", f, (x, y, z))
            insert_xyz(root, "rotation_euler", f, (0.0, 0.0, math.radians(yaw)))
            bx, by, bz, bp, br, bya = body_offset(t)
            insert_xyz(body, "location", f, (bx, by, bz))
            insert_xyz(body, "rotation_euler", f, (bp, br, bya))
            pitch, hyaw, hroll = sample_keys(LOOK_KEYS, t, 3)
            # Head stabilization: 40–70% counter to body, never 100%.
            hroll -= math.degrees(br) * 0.55
            hyaw -= math.degrees(bya) * 0.48
            insert_xyz(
                head,
                "rotation_euler",
                f,
                (math.radians(90.0 + pitch), math.radians(hroll), math.radians(hyaw)),
            )
            px, py, pz = sample_keys(PEEK_KEYS, t, 3)
            insert_xyz(head, "location", f, (px - 0.52 * bx, py - 0.35 * by, pz - 0.18 * bz))
            # Hand: millimetre drift + occasional grip correction.
            fear = 0.35
            if t >= 6.5:
                fear = 0.7
            if t >= 18.5:
                fear = 0.85
            if t >= 22.0:
                fear = 1.0
            hx = 0.0016 * math.sin(t * 5.1 + 0.2) + 0.0009 * math.sin(t * 1.9)
            hy = 0.0012 * math.sin(t * 4.3 + 1.1) + 0.0007 * math.sin(t * 2.4)
            hz = 0.0010 * math.sin(t * 3.6 + 0.7)
            if abs((t + 0.17) % 3.4 - 0.12) < 0.08:
                hx += 0.0018 * fear
            insert_xyz(hand, "location", f, (hx, hy, hz))
            hr = math.radians((0.06 + 0.08 * fear) * math.sin(t * 4.7))
            hp = math.radians((0.05 + 0.05 * fear) * math.sin(t * 3.9 + 0.8))
            hyy = math.radians((0.05 + 0.06 * fear) * math.sin(t * 5.6 + 1.4))
            insert_xyz(hand, "rotation_euler", f, (hp, hr, hyy))
            last = f
        t += dt
    add_noise_mods(hand, "location", 9.5, 0.00055, 2.2)
    add_noise_mods(hand, "rotation_euler", 13.0, 0.00045, 4.8)


def add_path_guide(col):
    curve = bpy.data.curves.new("CAM_PATH_GUIDE", "CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("POLY")
    spline.points.add(len(ROOT_KEYS) - 1)
    for i, (_t, x, y, z, _yaw) in enumerate(ROOT_KEYS):
        spline.points[i].co = (x, y, z, 1.0)
    obj = bpy.data.objects.new("CAM_PATH_GUIDE", curve)
    obj.hide_render = True
    col.objects.link(obj)


def setup_scene(scene):
    scene.frame_start = 1
    scene.frame_end = 900
    scene.frame_step = 1
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    scene.render.resolution_percentage = 100
    scene.render.use_motion_blur = False
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass


def look_vector(cam):
    return (cam.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()


def collision_report():
    dg = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    cam = bpy.data.objects["CAM_MAIN"]
    problems = []
    dirs = [
        Vector((1, 0, 0)),
        Vector((-1, 0, 0)),
        Vector((0, 1, 0)),
        Vector((0, -1, 0)),
        Vector((0.7, 0.7, 0)),
        Vector((-0.7, 0.7, 0)),
        Vector((0.7, -0.7, 0)),
        Vector((-0.7, -0.7, 0)),
    ]
    for f in range(1, 901, 2):
        scene.frame_set(f)
        dg.update()
        osd_frame_handler(scene)
        p = cam.matrix_world.translation.copy()
        t = (f - 1) / 30.0
        r = 0.12 if 21.5 <= t <= 26.4 else 0.20
        if t < 2.1:
            if p.z < 0.06 or p.z > 0.22:
                problems.append(f"f{f} floor height {p.z:.3f}")
        else:
            if p.z < 0.06 or (t > 5.0 and (p.z < 1.35 or p.z > 1.85)):
                if not (2.1 <= t <= 5.0):
                    problems.append(f"f{f} height {p.z:.3f}")
        for d in dirs:
            hit, loc, nor, idx, obj, mat = scene.ray_cast(dg, p, d)
            if not hit:
                continue
            if obj is not None and ("BLOOD" in obj.name or obj.name.startswith("OSD")):
                continue
            if (loc - p).length < r:
                problems.append(
                    f"f{f} clip {(loc-p).length:.3f} {obj.name if obj else '?'} {tuple(round(x,2) for x in loc)}"
                )
                break
    return problems


def print_sanity():
    scene = bpy.context.scene
    labels = (
        (0.0, "floor"),
        (2.3, "pickup bump"),
        (4.2, "lift"),
        (7.2, "blood"),
        (10.7, "look around"),
        (15.0, "wander"),
        (19.2, "look back"),
        (22.8, "peek 1"),
        (25.2, "peek 2"),
        (28.2, "exit"),
        (29.7, "scan / cut"),
    )
    for t, label in labels:
        scene.frame_set(frame_at(t))
        bpy.context.evaluated_depsgraph_get().update()
        osd_frame_handler(bpy.context.scene)
        cam = bpy.data.objects["CAM_MAIN"]
        p = cam.matrix_world.translation
        v = look_vector(cam)
        heading = math.degrees(math.atan2(-v.x, v.y))
        print(
            f"  t={t:5.2f} {label:12s} pos=({p.x:6.2f},{p.y:6.2f},{p.z:5.2f}) "
            f"look=({v.x:5.2f},{v.y:5.2f},{v.z:5.2f}) yaw={heading:6.1f}"
        )


def configure_preview(scene):
    frames = PREVIEW_DIR / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    scene.render.filepath = str(frames / "frame_")
    scene.render.use_compositing = False
    scene.frame_start = 1
    scene.frame_end = 900
    scene.frame_step = 1
    return frames


def encode_mp4(frame_dir: Path) -> Path:
    out = PREVIEW_DIR / "room_a_found_footage_preview.mp4"
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "30",
            "-i",
            str(frame_dir / "frame_%04d.jpg"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            str(out),
        ]
    )
    return out


def main():
    args = parse_args()
    scene = bpy.context.scene
    hide_previous_take()
    clear_this_take()
    fx = new_col(FX_COLL)
    make_blood(fx)
    col = new_col(COLL)
    root, body, head, hand, cam = build_rig(col)
    build_osd(col, cam)
    animate(root, body, head, hand)
    add_path_guide(col)
    setup_scene(scene)
    register_osd_handler()
    osd_frame_handler(scene)

    print("Sanity poses:")
    print_sanity()
    problems = collision_report()
    print("Collision hits", len(problems))
    for line in problems[:20]:
        print(" ", line)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH, "frames", scene.frame_start, scene.frame_end)

    if args["mode"] == "preview":
        frames = configure_preview(scene)
        print("Preview ->", frames)
        bpy.ops.render.render(animation=True)
        out = encode_mp4(frames)
        print("Wrote", out)


if __name__ == "__main__":
    main()
