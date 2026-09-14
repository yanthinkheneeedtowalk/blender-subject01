#!/usr/bin/env python3
"""Room A 30s found-footage camcorder take on the EXISTING backrooms.blend.

Does not rebuild walls, floor, ceiling, or lights. No formal Cycles render.

  blender -b backrooms.blend --python scripts/add_room_a_found_footage.py -- --check
  blender -b backrooms.blend --python scripts/add_room_a_found_footage.py -- --stills
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
OSD_W, OSD_H = 640, 480
BLOOD_C = (-1.90, 1.24)


def parse_args() -> dict:
    mode = "check"
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--preview" in argv:
        mode = "preview"
    elif "--stills" in argv:
        mode = "stills"
    return {"mode": mode}


def frame_at(t: float) -> int:
    return max(1, min(900, int(round(1 + t * FPS))))


def lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def ease_look(u: float, pin: float = 2.15, pout: float = 1.55) -> float:
    """Fast middle, slower settle. Not a symmetric smoothstep."""
    u = max(0.0, min(1.0, u))
    if u < 0.45:
        t = u / 0.45
        return 0.62 * (t ** pin)
    t = (u - 0.45) / 0.55
    return 0.62 + 0.38 * (1.0 - (1.0 - t) ** pout)


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
                kp.handle_left_type = "FREE" if interp == "BEZIER" else "AUTO_CLAMPED"
                kp.handle_right_type = "FREE" if interp == "BEZIER" else "AUTO_CLAMPED"


def add_noise_mods(obj, data_path: str, scale: float, strength: float, seed: float) -> None:
    n = 0
    for fc in iter_fcurves(obj):
        if fc.data_path != data_path:
            continue
        for mod in list(fc.modifiers):
            if mod.type == "NOISE":
                fc.modifiers.remove(mod)
        mod = fc.modifiers.new("NOISE")
        mod.scale = scale + 1.4 * n
        mod.strength = strength
        mod.phase = seed + n * 2.7
        mod.depth = 0
        n += 1


def sample_keys(keys, t, nvals=3, ease=False):
    if t <= keys[0][0]:
        return keys[0][1:]
    for a, b in zip(keys, keys[1:]):
        if a[0] <= t <= b[0]:
            raw = (t - a[0]) / max(1e-6, b[0] - a[0])
            u = ease_look(raw) if ease else raw * raw * (3.0 - 2.0 * raw)
            return tuple(lerp(a[i], b[i], u) for i in range(1, nvals + 1))
    return keys[-1][1:]


def hide_previous_take() -> None:
    old = bpy.data.collections.get("CAM_FOUND_FOOTAGE_01")
    if old is None:
        return
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
    for obj in list(bpy.data.objects):
        if (
            obj.name.startswith("BLOOD.RoomA")
            or obj.name.startswith("OSD_")
            or obj.name in {"POV_ROOT", "BODY_MOTION", "HEAD_MOTION", "HAND_MOTION", "CAM_MAIN", "CAM_OSD", "CAM_PATH_GUIDE"}
        ):
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


def _blood_ring(bm, ox, oy, rx, ry, seed, n=32, z=0.0):
    rng = random.Random(seed)
    verts = []
    for i in range(n):
        a = (2.0 * math.pi * i) / n
        k = (
            0.70
            + 0.18 * math.sin(i * 0.71 + seed)
            + 0.12 * math.sin(i * 1.87 + 0.6)
            + 0.08 * math.sin(i * 3.3 + seed * 0.4)
            + rng.uniform(-0.07, 0.07)
        )
        sx = 0.40 if math.cos(a) > 0.0 else 1.22
        sy = 1.05 if math.sin(a) > 0.0 else 0.48
        verts.append(bm.verts.new((ox + k * rx * sx * math.cos(a), oy + k * ry * sy * math.sin(a), z)))
    return bm.faces.new(verts)


def make_blood(col) -> bpy.types.Object:
    bm = bmesh.new()
    faces = [
        _blood_ring(bm, 0.0, 0.0, 0.55, 0.42, 17, 40),
        _blood_ring(bm, -0.38, 0.20, 0.18, 0.12, 23, 22),
        _blood_ring(bm, 0.20, 0.26, 0.13, 0.09, 41, 18),
        _blood_ring(bm, -0.14, -0.12, 0.10, 0.07, 8, 16),
        _blood_ring(bm, -0.55, 0.08, 0.08, 0.06, 55, 14),
    ]
    geom = bmesh.ops.extrude_face_region(bm, geom=faces)
    for g in geom["geom"]:
        if isinstance(g, bmesh.types.BMVert):
            g.co.z = 0.010
    mesh = bpy.data.meshes.new("BLOOD.RoomA.Dried")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("BLOOD.RoomA.Dried", mesh)
    obj.location = (BLOOD_C[0], BLOOD_C[1], 0.006)
    col.objects.link(obj)
    obj.color = (0.05, 0.012, 0.008, 1.0)

    mat = bpy.data.materials.get("MAT.DriedBlood") or bpy.data.materials.new("MAT.DriedBlood")
    mat.use_nodes = True
    mat.diffuse_color = (0.045, 0.012, 0.008, 1.0)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 22.0
    tex.inputs["Detail"].default_value = 10.0
    tex.inputs["Roughness"].default_value = 0.68
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (0.015, 0.004, 0.003, 1.0)
    ramp.color_ramp.elements[1].position = 0.82
    ramp.color_ramp.elements[1].color = (0.07, 0.016, 0.010, 1.0)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    splat = bpy.data.images.get("BLOOD.TEX") or bpy.data.images.new("BLOOD.TEX", 256, 256)
    pix = []
    rng = random.Random(9)
    for y in range(256):
        for x in range(256):
            nx, ny = (x - 128) / 128.0, (y - 128) / 128.0
            r = math.sqrt(nx * nx * 0.72 + ny * ny)
            n = rng.random()
            edge = max(0.0, min(1.0, 1.15 - r * 1.05 - 0.18 * n))
            d = 0.018 + 0.04 * (1.0 - edge) + 0.01 * n
            pix.extend((d, d * 0.28, d * 0.18, 1.0))
    splat.pixels = pix
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = splat
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.96
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.02
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    obj.data.materials.append(mat)
    return obj


# ---------------------------------------------------------------------------
# Screen-space OSD (compositor overlay). Never parented to the camera.
# ---------------------------------------------------------------------------

_GLYPHS = {
    "0": "01110100011001110101100111000101110",
    "1": "00100011000010000100001000010001110",
    "2": "01110100010000100010001000100011111",
    "3": "01110100010000100110000011000101110",
    "4": "00010001100101010010111110001000010",
    "5": "11111100001111000001000011000101110",
    "6": "01110100001111010001100011000101110",
    "7": "11111000010001000100010000100001000",
    "8": "01110100010111010001100011000101110",
    "9": "01110100011000101111000011000101110",
    ":": "00000001000000000000001000000000000",
    "R": "11110100011111010001100011000110001",
    "E": "11111100001111010000100001000011111",
    "C": "01110100011000010000100001000101110",
    "S": "01111100000111000001000011000111110",
    "P": "11110100011000111110100001000010000",
    " ": "00000000000000000000000000000000000",
}


def _clock_text(t: float) -> str:
    clock = 23 * 60 + 51 + t
    mm = int(clock // 60)
    ss = int(clock % 60)
    return f"{mm // 60}:{mm % 60:02d}:{ss:02d}" if mm >= 60 else f"0:{mm:02d}:{ss:02d}"


def _stamp(buf, w, h, x0, y0, text, rgb, scale):
    r, g, b = rgb
    step = 6 * scale
    for gi, ch in enumerate(text):
        bits = _GLYPHS.get(ch, _GLYPHS[" "])
        for row in range(7):
            for col in range(5):
                if bits[row * 5 + col] != "1":
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        x = x0 + gi * step + col * scale + dx
                        y = y0 + (6 - row) * scale + dy
                        if 0 <= x < w and 0 <= y < h:
                            i = (y * w + x) * 4
                            buf[i : i + 4] = [r, g, b, 1.0]


def _rect(buf, w, h, x0, y0, x1, y1, rgb, a=1.0):
    r, g, b = rgb
    for y in range(max(0, y0), min(h, y1)):
        for x in range(max(0, x0), min(w, x1)):
            i = (y * w + x) * 4
            buf[i : i + 4] = [r, g, b, a]


def build_osd_pixels(frame: int) -> list[float]:
    w, h = OSD_W, OSD_H
    buf = [0.0] * (w * h * 4)
    t = max(0.0, (frame - 1) / float(FPS))
    lcd = (0.90, 0.94, 0.78)
    red = (0.92, 0.12, 0.07)
    amber = (0.82, 0.28, 0.06)
    # Battery outline top-left (y from bottom in Blender images).
    bx, by = 22, h - 42
    _rect(buf, w, h, bx, by + 16, bx + 46, by + 18, lcd)
    _rect(buf, w, h, bx, by, bx + 46, by + 2, lcd)
    _rect(buf, w, h, bx, by, bx + 2, by + 18, lcd)
    _rect(buf, w, h, bx + 44, by, bx + 46, by + 18, lcd)
    _rect(buf, w, h, bx + 46, by + 5, bx + 50, by + 13, lcd)
    if (frame % 44) < 30:
        _rect(buf, w, h, bx + 3, by + 4, bx + 7, by + 14, amber)
    if (frame % 30) < 16:
        _rect(buf, w, h, w - 118, h - 36, w - 106, h - 24, red)
        _stamp(buf, w, h, w - 100, h - 42, "REC", red, 3)
    _stamp(buf, w, h, 22, 18, _clock_text(t), lcd, 3)
    _stamp(buf, w, h, w - 148, 18, "SP  4:3", lcd, 2)
    return buf


def ensure_osd_image() -> bpy.types.Image:
    img = bpy.data.images.get("OSD_OVERLAY")
    if img is None or tuple(img.size) != (OSD_W, OSD_H):
        if img is not None:
            bpy.data.images.remove(img)
        img = bpy.data.images.new("OSD_OVERLAY", OSD_W, OSD_H, alpha=True)
    return img


def paint_osd_image(frame: int) -> bpy.types.Image:
    img = ensure_osd_image()
    img.pixels = build_osd_pixels(frame)
    return img


def setup_osd_compositor(scene) -> None:
    ng = bpy.data.node_groups.get("OSD_SCREENSPACE")
    if ng is None:
        ng = bpy.data.node_groups.new("OSD_SCREENSPACE", "CompositorNodeTree")
    ng.nodes.clear()
    ng.interface.clear()
    ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    rl.location = (0, 80)
    img_n = ng.nodes.new("CompositorNodeImage")
    img_n.image = ensure_osd_image()
    img_n.location = (0, -140)
    over = ng.nodes.new("CompositorNodeAlphaOver")
    over.location = (260, 40)
    out = ng.nodes.new("NodeGroupOutput")
    out.location = (480, 40)
    ng.links.new(rl.outputs["Image"], over.inputs[1])
    ng.links.new(img_n.outputs["Image"], over.inputs[2])
    ng.links.new(over.outputs["Image"], out.inputs[0])
    scene.compositing_node_group = ng
    scene.render.use_compositing = True


def osd_frame_handler(scene):
    paint_osd_image(scene.frame_current)


def register_osd_handler():
    for h in list(bpy.app.handlers.frame_change_pre):
        if getattr(h, "__name__", "") == "osd_frame_handler":
            bpy.app.handlers.frame_change_pre.remove(h)
    bpy.app.handlers.frame_change_pre.append(osd_frame_handler)


def overlay_osd_on_jpeg(jpg: Path, frame: int) -> None:
    """Guarantee screen-space OSD even if Workbench skips the compositor."""
    png = jpg.with_suffix(".osd.png")
    img = paint_osd_image(frame)
    img.filepath_raw = str(png)
    img.file_format = "PNG"
    img.save()
    tmp = jpg.with_suffix(".comp.jpg")
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(jpg),
            "-i",
            str(png),
            "-filter_complex",
            "overlay=0:0",
            "-q:v",
            "3",
            str(tmp),
        ]
    )
    tmp.replace(jpg)
    png.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Rig — roll lives on CAM_MAIN local Z (look axis), never on HEAD Y.
# ---------------------------------------------------------------------------

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
    osd = make_empty("CAM_OSD", col, 0.04)
    osd.parent = None

    root.location = (-5.38, 2.48, 0.10)
    root.rotation_euler = (0.0, 0.0, math.radians(92.0))
    body.location = (0, 0, 0)
    head.location = (0, 0, 0)
    head.rotation_mode = "XYZ"
    head.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    hand.location = (0, 0, 0)
    cam.location = (0, 0, 0)
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = (0.0, 0.0, math.radians(20.0))

    parent_local(body, root)
    parent_local(head, body)
    parent_local(hand, head)
    parent_local(cam, hand)
    bpy.context.scene.camera = cam
    return root, body, head, hand, cam


# t, x, y, z, yaw_deg  (0=north, +90=west, -90=east)
# Pickup keeps facing the west wall. Horizon recover is CAM roll, not ROOT yaw.
ROOT_KEYS = [
    (0.00, -5.38, 2.48, 0.100, 92.0),
    (1.80, -5.379, 2.481, 0.101, 92.3),
    (1.88, -5.368, 2.492, 0.112, 93.8),
    (1.96, -5.350, 2.470, 0.128, 89.5),
    (2.10, -5.328, 2.448, 0.255, 91.0),
    (2.28, -5.305, 2.475, 0.520, 87.5),
    (2.48, -5.288, 2.452, 0.880, 90.5),
    (2.70, -5.270, 2.430, 1.250, 88.0),
    (2.95, -5.252, 2.412, 1.480, 90.0),
    (3.20, -5.240, 2.400, 1.575, 89.0),
    (3.50, -5.228, 2.388, 1.605, 87.0),
    (3.80, -5.215, 2.372, 1.612, 84.0),
    (4.15, -5.175, 2.310, 1.614, 62.0),
    (4.55, -5.110, 2.220, 1.612, 28.0),
    (5.00, -5.020, 2.120, 1.610, -8.0),
    (5.35, -4.960, 2.050, 1.608, -22.0),
    (5.80, -4.900, 1.980, 1.606, -48.0),
    (6.50, -4.780, 1.920, 1.602, -72.0),
    (6.90, -4.720, 1.880, 1.575, -80.0),
    (7.50, -4.690, 1.860, 1.568, -84.0),
    (8.20, -4.680, 1.855, 1.572, -82.0),
    (8.80, -4.710, 1.878, 1.598, -76.0),
    (9.50, -4.730, 1.905, 1.610, -62.0),
    (10.10, -4.728, 1.930, 1.612, -18.0),
    (10.80, -4.720, 1.960, 1.610, 8.0),
    (11.40, -4.718, 1.972, 1.611, 22.0),
    (12.00, -4.715, 1.980, 1.610, 6.0),
    (12.70, -4.680, 2.040, 1.612, -38.0),
    (13.50, -4.560, 2.140, 1.612, -58.0),
    (14.10, -4.280, 2.420, 1.608, -22.0),
    (14.80, -3.920, 2.780, 1.612, 4.0),
    (15.30, -3.780, 2.980, 1.610, 10.0),
    (15.70, -3.760, 3.040, 1.608, 8.0),
    (16.40, -3.280, 3.220, 1.610, -36.0),
    (17.20, -2.720, 3.120, 1.608, -78.0),
    (18.00, -2.220, 2.960, 1.605, -90.0),
    (18.70, -2.080, 2.900, 1.602, -93.0),
    (19.40, -2.020, 2.882, 1.600, -90.0),
    (20.60, -2.012, 2.878, 1.600, -88.0),
    (21.50, -2.000, 2.872, 1.598, -90.0),
    (22.20, -1.992, 2.885, 1.598, -86.0),
    (24.40, -1.988, 2.890, 1.600, -88.0),
    (26.40, -1.985, 2.898, 1.600, -84.0),
    (27.00, -1.978, 2.930, 1.602, -72.0),
    (27.28, -1.930, 3.20, 1.606, -52.0),
    (27.55, -1.760, 3.40, 1.608, -68.0),
    (27.85, -1.480, 3.48, 1.610, -98.0),
    (28.20, -1.080, 3.38, 1.606, -128.0),
    (28.55, -0.700, 3.08, 1.598, -152.0),
    (28.85, -0.560, 2.86, 1.592, -168.0),
    (29.15, -0.538, 2.78, 1.590, -172.0),
    (29.50, -0.530, 2.76, 1.588, -166.0),
    (30.00, -0.522, 2.75, 1.588, -160.0),
]

# pitch (+=up), yaw (+=left relative to body)
LOOK_KEYS = [
    (0.00, -11.0, 1.5),
    (1.80, -10.5, 1.8),
    (1.90, -4.0, -3.0),
    (2.05, 8.0, 6.0),
    (2.22, -6.0, -5.0),
    (2.45, 4.0, 4.0),
    (2.70, 1.0, -2.0),
    (3.05, 0.6, 1.5),
    (3.40, 0.3, 0.6),
    (3.80, 0.2, 1.0),
    (4.05, 0.4, 3.0),
    (4.22, 0.6, 8.0),
    (4.40, 0.3, 16.0),
    (4.55, -1.0, 22.0),
    (4.68, -2.5, 24.0),
    (4.78, -2.0, 21.0),
    (5.15, -6.0, 8.0),
    (5.35, -8.5, 2.0),
    (5.50, -9.0, 0.5),
    (5.85, -12.0, -8.0),
    (6.10, -14.0, -14.0),
    (6.28, -15.5, -16.0),
    (6.40, -14.5, -15.0),
    (6.70, -18.0, -12.0),
    (7.05, -22.0, -10.0),
    (7.35, -24.0, -9.0),
    (7.55, -23.0, -8.5),
    (8.10, -22.5, -8.0),
    (8.55, -20.0, -6.0),
    (8.90, -16.0, -4.0),
    (9.30, -8.0, -2.0),
    (9.55, -2.0, 2.0),
    (9.80, 3.0, 6.0),
    (10.05, 8.0, 10.0),
    (10.22, 11.0, 12.0),
    (10.38, 9.5, 10.5),
    (10.70, 2.0, 4.0),
    (10.95, 1.0, 10.0),
    (11.15, 1.4, 16.0),
    (11.32, 1.6, 20.0),
    (11.45, 1.2, 18.0),
    (11.70, 0.8, 10.0),
    (12.00, 0.6, 4.0),
    (12.25, 0.5, 4.0),
    (12.55, 0.8, -12.0),
    (12.85, 1.0, -24.0),
    (13.05, 1.2, -28.0),
    (13.20, 0.9, -25.0),
    (13.55, 0.6, -12.0),
    (14.20, 1.0, 10.0),
    (14.80, 2.2, 14.0),
    (15.20, 9.0, 8.0),
    (15.45, 10.5, 7.0),
    (15.70, 2.0, 4.0),
    (16.30, 0.8, -16.0),
    (17.00, 0.5, 6.0),
    (17.60, 0.6, 10.0),
    (18.20, 0.8, 6.0),
    (18.70, 1.2, 12.0),
    (19.00, 2.0, 48.0),
    (19.12, 2.4, 78.0),
    (19.22, 2.6, 98.0),
    (19.32, 2.2, 104.0),
    (19.45, 1.8, 96.0),
    (19.70, 1.4, 90.0),
    (20.10, 1.0, 42.0),
    (20.50, 0.6, 14.0),
    (21.10, 0.4, 6.0),
    (21.60, 0.5, 8.0),
    (22.00, 0.8, 18.0),
    (22.25, 1.0, 28.0),
    (22.50, 0.6, 34.0),
    (22.70, 0.4, 38.0),
    (22.88, 0.3, 36.0),
    (23.20, 0.4, 22.0),
    (23.55, 0.5, 10.0),
    (23.90, 0.4, 8.0),
    (24.30, 0.7, 18.0),
    (24.60, 0.5, 24.0),
    (24.90, 0.4, 28.0),
    (25.15, 0.3, 26.0),
    (25.35, 0.4, 24.0),
    (25.80, 0.5, 16.0),
    (26.30, 0.6, 12.0),
    (26.80, 0.8, 16.0),
    (27.20, 1.0, 8.0),
    (27.70, 0.6, -4.0),
    (28.20, 0.5, 6.0),
    (28.70, 1.6, 10.0),
    (28.95, 1.2, 18.0),
    (29.12, 0.8, 16.0),
    (29.30, 0.5, 4.0),
    (29.48, 0.7, -10.0),
    (29.68, 1.0, -16.0),
    (29.82, 0.7, -8.0),
    (30.00, 0.6, -12.0),
]

# Image roll on CAM local Z. Recovers to ~0 after pickup.
ROLL_KEYS = [
    (0.00, 20.0),
    (1.80, 19.4),
    (1.90, 26.0),
    (2.02, 34.0),
    (2.16, 14.0),
    (2.32, 6.0),
    (2.50, -3.2),
    (2.70, 1.8),
    (2.92, -1.1),
    (3.15, 0.7),
    (3.45, -0.3),
    (3.80, 0.2),
    (6.90, 0.4),
    (7.40, -0.6),
    (8.20, 0.3),
    (9.50, 0.2),
    (14.80, -0.8),
    (15.70, 0.5),
    (19.22, 1.4),
    (19.50, 0.4),
    (22.70, 0.6),
    (25.15, -0.5),
    (27.55, 0.8),
    (29.15, -0.4),
    (30.00, 0.3),
]

PEEK_KEYS = [
    (0.00, 0.0, 0.0, 0.0),
    (21.50, 0.0, 0.0, 0.0),
    (22.10, -0.04, 0.008, 0.0),
    (22.55, -0.09, 0.016, 0.006),
    (22.90, -0.10, 0.018, 0.006),
    (23.30, -0.06, 0.008, 0.002),
    (23.70, -0.05, 0.006, 0.0),
    (24.20, -0.05, 0.006, 0.0),
    (24.70, -0.10, 0.018, 0.008),
    (25.20, -0.13, 0.022, 0.010),
    (25.70, -0.11, 0.016, 0.006),
    (26.30, -0.04, 0.006, 0.0),
    (27.00, 0.0, 0.0, 0.0),
    (30.00, 0.0, 0.0, 0.0),
]

WALK_SPANS = [
    (13.50, 15.25),
    (15.85, 18.50),
    (27.05, 28.85),
]


def walk_weight(t: float) -> float:
    best = 0.0
    for a, b in WALK_SPANS:
        if a <= t <= b:
            edge = min(t - a, b - t, 0.32) / 0.32
            best = max(best, max(0.0, min(1.0, edge)) ** 1.4)
    return best


def build_steps():
    rng = random.Random(17)
    steps = []
    t = 0.0
    while t < DURATION + 1.0:
        d = rng.choice((0.58, 0.61, 0.67, 0.55, 0.70, 0.64, 0.59, 0.72))
        amp_z = rng.uniform(0.010, 0.021)
        amp_x = rng.uniform(0.008, 0.017)
        amp_y = rng.uniform(0.004, 0.009)
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
                bump = math.sin(math.pi * (u ** 0.82))
                z = w * az * bump
                x = w * ax * side * math.sin(math.pi * u)
                y = w * ay * math.sin(2.0 * math.pi * (u ** 1.12)) * 0.4
                roll = w * math.radians(0.28 * side * math.sin(math.pi * u))
                pitch = w * math.radians(-0.18 * bump)
                yaw = w * math.radians(0.14 * side * math.sin(math.pi * u * 0.55))
                break
    br = 3.4 + 0.7 * math.sin(t * 0.13 + 0.4)
    idle = 1.0 - w
    z += (0.0018 + 0.0016 * idle) * math.sin(t * 2.0 * math.pi / br)
    z += 0.0004 * math.sin(t * 1.07 + 0.8)
    x += (0.0005 + 0.0004 * idle) * math.sin(t * 0.51 + 1.2)
    return x, y, z, pitch, roll, yaw


def animate(root, body, head, hand, cam):
    for t, x, y, z, yaw in ROOT_KEYS:
        f = frame_at(t)
        insert_xyz(root, "location", f, (x, y, z))
        insert_xyz(root, "rotation_euler", f, (0.0, 0.0, math.radians(yaw)))
    for t, roll in ROLL_KEYS:
        f = frame_at(t)
        insert_xyz(cam, "rotation_euler", f, (0.0, 0.0, math.radians(roll)))
    dt = 1.0 / FPS
    t = 0.0
    last = -1
    while t <= DURATION + 1e-6:
        f = frame_at(t)
        if f != last:
            bx, by, bz, bp, br, bya = body_offset(t)
            insert_xyz(body, "location", f, (bx, by, bz))
            insert_xyz(body, "rotation_euler", f, (bp, br, bya))
            pitch, hyaw = sample_keys(LOOK_KEYS, t, 2, ease=True)
            pitch -= math.degrees(bp) * 0.60
            hyaw -= math.degrees(bya) * 0.55
            insert_xyz(
                head,
                "rotation_euler",
                f,
                (math.radians(90.0 + pitch), 0.0, math.radians(hyaw)),
            )
            px, py, pz = sample_keys(PEEK_KEYS, t, 3)
            insert_xyz(head, "location", f, (px - 0.58 * bx, py - 0.32 * by, pz - 0.22 * bz))
            hx = 0.0011 * math.sin(t * 4.6 + 0.3) + 0.0006 * math.sin(t * 1.7)
            hy = 0.0009 * math.sin(t * 3.9 + 1.0) + 0.0005 * math.sin(t * 2.2)
            hz = 0.0007 * math.sin(t * 3.1 + 0.6)
            if abs((t + 0.21) % 4.1 - 0.09) < 0.05:
                hx += 0.0012
            insert_xyz(hand, "location", f, (hx, hy, hz))
            insert_xyz(
                hand,
                "rotation_euler",
                f,
                (
                    math.radians(0.06 * math.sin(t * 3.7 + 0.5)),
                    math.radians(0.05 * math.sin(t * 4.4)),
                    math.radians(0.05 * math.sin(t * 5.1 + 1.1)),
                ),
            )
            last = f
        t += dt
    add_noise_mods(hand, "location", 11.0, 0.00035, 1.6)
    add_noise_mods(hand, "rotation_euler", 16.0, 0.00028, 3.1)


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
    scene.render.resolution_x = OSD_W
    scene.render.resolution_y = OSD_H
    scene.render.resolution_percentage = 100
    scene.render.use_motion_blur = False
    scene.render.use_sequencer = False
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    setup_osd_compositor(scene)
    scene.render.use_compositing = False


def look_vector(cam):
    return (cam.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()


def cam_roll_deg(cam) -> float:
    mw = cam.matrix_world.to_3x3()
    right = (mw @ Vector((1.0, 0.0, 0.0))).normalized()
    up = (mw @ Vector((0.0, 1.0, 0.0))).normalized()
    world_up = Vector((0.0, 0.0, 1.0))
    return math.degrees(math.atan2(right.dot(world_up), up.dot(world_up)))


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
        p = cam.matrix_world.translation.copy()
        t = (f - 1) / 30.0
        r = 0.12 if 21.5 <= t <= 26.6 else 0.20
        if t < 1.85:
            if p.z < 0.06 or p.z > 0.22:
                problems.append(f"f{f} floor height {p.z:.3f}")
        elif t > 3.8:
            if p.z < 1.40 or p.z > 1.80:
                problems.append(f"f{f} height {p.z:.3f}")
        if t >= 3.8:
            roll = cam_roll_deg(cam)
            if abs(roll) > 8.0:
                problems.append(f"f{f} horizon roll {roll:.1f}")
        for d in dirs:
            hit, loc, nor, idx, obj, mat = scene.ray_cast(dg, p, d)
            if not hit:
                continue
            if obj is not None and ("BLOOD" in obj.name or obj.name.startswith("OSD") or obj.name.startswith("CAM_")):
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
        (2.5, "pickup"),
        (3.8, "settled"),
        (5.5, "blood edge"),
        (7.4, "blood look"),
        (11.3, "look left"),
        (13.1, "look exit"),
        (15.5, "hesitate"),
        (19.3, "look back"),
        (22.8, "peek 1"),
        (25.2, "peek 2"),
        (28.2, "exit"),
        (29.7, "scan / cut"),
    )
    for t, label in labels:
        scene.frame_set(frame_at(t))
        bpy.context.evaluated_depsgraph_get().update()
        cam = bpy.data.objects["CAM_MAIN"]
        p = cam.matrix_world.translation
        v = look_vector(cam)
        heading = math.degrees(math.atan2(-v.x, v.y))
        roll = cam_roll_deg(cam)
        print(
            f"  t={t:5.2f} {label:12s} pos=({p.x:6.2f},{p.y:6.2f},{p.z:5.2f}) "
            f"look=({v.x:5.2f},{v.y:5.2f},{v.z:5.2f}) yaw={heading:7.1f} roll={roll:6.1f}"
        )


def configure_preview(scene):
    frames = PREVIEW_DIR / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x = OSD_W
    scene.render.resolution_y = OSD_H
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


STILL_FRAMES = (
    (1, "floor"),
    (76, "pickup"),
    (90, "osd90"),
    (115, "settled"),
    (166, "blood_edge"),
    (180, "blood_notice"),
    (223, "blood_look"),
    (300, "osd300"),
    (340, "look_left"),
    (466, "wander"),
    (580, "look_back"),
    (600, "osd600"),
    (685, "peek1"),
    (757, "peek2"),
    (847, "exit"),
    (900, "cut"),
)


def render_stills(scene) -> Path:
    out_dir = PREVIEW_DIR / "check"
    out_dir.mkdir(parents=True, exist_ok=True)
    configure_preview(scene)
    for f, label in STILL_FRAMES:
        scene.frame_set(f)
        osd_frame_handler(scene)
        path = out_dir / f"{label}_{f:04d}.jpg"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        overlay_osd_on_jpeg(path, f)
        print("still", path)
    return out_dir


def overlay_preview_frames(frame_dir: Path) -> None:
    osd_dir = PREVIEW_DIR / "osd"
    osd_dir.mkdir(parents=True, exist_ok=True)
    cache = {}
    img = ensure_osd_image()
    for f in range(1, 901):
        t = max(0.0, (f - 1) / float(FPS))
        key = (int(t), (f % 30) < 16, (f % 44) < 30)
        src = osd_dir / f"src_{key[0]:02d}_{int(key[1])}_{int(key[2])}.png"
        if key not in cache:
            paint_osd_image(f)
            img.filepath_raw = str(src)
            img.file_format = "PNG"
            img.save()
            cache[key] = src
        dst = osd_dir / f"osd_{f:04d}.png"
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.symlink_to(cache[key].name)
    print("osd pngs", len(cache))


def main():
    args = parse_args()
    scene = bpy.context.scene
    hide_previous_take()
    clear_this_take()
    fx = new_col(FX_COLL)
    make_blood(fx)
    col = new_col(COLL)
    root, body, head, hand, cam = build_rig(col)
    animate(root, body, head, hand, cam)
    add_path_guide(col)
    setup_scene(scene)
    register_osd_handler()
    paint_osd_image(1)

    print("Sanity poses:")
    print_sanity()
    problems = collision_report()
    print("Collision/horizon hits", len(problems))
    for line in problems[:24]:
        print(" ", line)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH, "frames", scene.frame_start, scene.frame_end)

    if args["mode"] == "preview":
        frames = configure_preview(scene)
        print("Preview ->", frames)
        bpy.ops.render.render(animation=True)
        overlay_preview_frames(frames)
        osd_dir = PREVIEW_DIR / "osd"
        out = PREVIEW_DIR / "room_a_found_footage_preview.mp4"
        subprocess.check_call(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                "30",
                "-i",
                str(frames / "frame_%04d.jpg"),
                "-framerate",
                "30",
                "-i",
                str(osd_dir / "osd_%04d.png"),
                "-filter_complex",
                "overlay=0:0",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "18",
                str(out),
            ]
        )
        print("Wrote", out)
    elif args["mode"] == "stills":
        print("Stills ->", render_stills(scene))


if __name__ == "__main__":
    main()
