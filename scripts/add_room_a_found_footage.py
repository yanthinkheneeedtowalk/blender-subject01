#!/usr/bin/env python3
"""Room A 30s found-footage camcorder take on the EXISTING backrooms.blend.

Camera rig / animation / OSD only. Does not rebuild walls, blood, or lights.
No formal Cycles render.

  blender -b backrooms.blend --python scripts/add_room_a_found_footage.py -- --check
  blender -b backrooms.blend --python scripts/add_room_a_found_footage.py -- --stills
  blender -b backrooms.blend --python scripts/add_room_a_found_footage.py -- --preview
"""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "backrooms.blend"
PREVIEW_DIR = ROOT / "renders" / "room_a_preview"
OSD_SEQ_DIR = ROOT / "assets" / "osd"
OSD_MOV = ROOT / "assets" / "osd_timer.mov"

FPS = 30
DURATION = 30.0
COLL = "CAM_FOUND_FOOTAGE"
OSD_W, OSD_H = 640, 480
BLOOD_C = (-1.90, 1.24)

# Standing eye height after grip. Opening lives on the floor.
STAND_Z = 1.60


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
                kp.handle_left_type = "FREE" if interp == "BEZIER" else "VECTOR"
                kp.handle_right_type = "FREE" if interp == "BEZIER" else "VECTOR"


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


def sample_keys(keys, t, nvals=3):
    """Linear between authored keys. Shaping lives in the key values, not a global ease."""
    if t <= keys[0][0]:
        return keys[0][1:]
    for a, b in zip(keys, keys[1:]):
        if a[0] <= t <= b[0]:
            u = (t - a[0]) / max(1e-6, b[0] - a[0])
            return tuple(lerp(a[i], b[i], u) for i in range(1, nvals + 1))
    return keys[-1][1:]


def shape_sparse_fcurves(obj) -> None:
    """Handmade Bezier: holds stay vector-flat; motion uses asymmetric handles."""
    for fc in iter_fcurves(obj):
        pts = list(fc.keyframe_points)
        n = len(pts)
        for i, kp in enumerate(pts):
            hold = False
            if i + 1 < n and abs(pts[i + 1].co[1] - kp.co[1]) < 1e-5 and (pts[i + 1].co[0] - kp.co[0]) > 8:
                hold = True
            if i > 0 and abs(pts[i - 1].co[1] - kp.co[1]) < 1e-5 and (kp.co[0] - pts[i - 1].co[0]) > 8:
                hold = True
            if hold:
                kp.interpolation = "BEZIER"
                kp.handle_left_type = "VECTOR"
                kp.handle_right_type = "VECTOR"
                continue
            kp.interpolation = "BEZIER"
            kp.handle_left_type = "FREE"
            kp.handle_right_type = "FREE"
            t = kp.co[0]
            v = kp.co[1]
            dt_in = (t - pts[i - 1].co[0]) if i else 10.0
            dt_out = (pts[i + 1].co[0] - t) if i + 1 < n else 10.0
            a = 0.16 + (i % 5) * 0.07
            b = 0.46 - (i % 5) * 0.06
            kp.handle_left = (t - dt_in * a, v)
            kp.handle_right = (t + dt_out * b, v)


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
    """Remove only this take's camera rig / OSD. Never touch blood or walls."""
    if COLL in bpy.data.collections:
        col = bpy.data.collections[COLL]
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    keep = {"BLOOD.RoomA.Dried"}
    for obj in list(bpy.data.objects):
        if obj.name in keep:
            continue
        if (
            obj.name.startswith("OSD_")
            or obj.name in {
                "POV_ROOT",
                "BODY_MOTION",
                "HEAD_MOTION",
                "HAND_MOTION",
                "CAM_MAIN",
                "CAM_OSD",
                "CAM_PATH_GUIDE",
                "CAM_BODY",
                "CAM_LOOK",
                "CAM_ROOT",
            }
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


def ensure_blood() -> bpy.types.Object | None:
    obj = bpy.data.objects.get("BLOOD.RoomA.Dried")
    if obj is None:
        print("WARNING: BLOOD.RoomA.Dried missing — not recreating.")
        return None
    print("Keeping existing blood at", tuple(round(x, 4) for x in obj.location))
    return obj


# ---------------------------------------------------------------------------
# Screen-space OSD. Never parented to the camera.
# Timer is an image sequence / movie driven by scene.frame_current.
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
    "8": "01110100011000101111000011000101110",
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


def osd_cache_key(frame: int):
    t = max(0.0, (frame - 1) / float(FPS))
    return (int(t), (frame % 30) < 16, (frame % 44) < 30)


def build_osd_pixels(frame: int) -> list[float]:
    w, h = OSD_W, OSD_H
    buf = [0.0] * (w * h * 4)
    t = max(0.0, (frame - 1) / float(FPS))
    lcd = (0.90, 0.94, 0.78)
    red = (0.92, 0.12, 0.07)
    amber = (0.82, 0.28, 0.06)
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


def ensure_osd_scratch() -> bpy.types.Image:
    img = bpy.data.images.get("OSD_SCRATCH")
    if img is None or tuple(img.size) != (OSD_W, OSD_H):
        if img is not None:
            bpy.data.images.remove(img)
        img = bpy.data.images.new("OSD_SCRATCH", OSD_W, OSD_H, alpha=True)
    return img


def paint_osd_image(frame: int) -> bpy.types.Image:
    img = ensure_osd_scratch()
    img.pixels = build_osd_pixels(frame)
    return img


def write_osd_sequence() -> Path:
    """Write 900 screen-space OSD frames + a movie the timeline can drive natively."""
    if OSD_MOV.exists() and (OSD_SEQ_DIR / "osd_0900.png").exists():
        print("OSD assets exist, skipping rebuild")
        return OSD_MOV
    OSD_SEQ_DIR.mkdir(parents=True, exist_ok=True)
    img = ensure_osd_scratch()
    cache: dict = {}
    for f in range(1, 901):
        key = osd_cache_key(f)
        src = OSD_SEQ_DIR / f"src_{key[0]:02d}_{int(key[1])}_{int(key[2])}.png"
        if key not in cache:
            img.pixels = build_osd_pixels(f)
            img.filepath_raw = str(src)
            img.file_format = "PNG"
            img.save()
            cache[key] = src
        dst = OSD_SEQ_DIR / f"osd_{f:04d}.png"
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        try:
            dst.symlink_to(cache[key].name)
        except OSError:
            shutil.copyfile(cache[key], dst)
    OSD_MOV.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            "30",
            "-i",
            str(OSD_SEQ_DIR / "osd_%04d.png"),
            "-c:v",
            "png",
            "-pix_fmt",
            "rgba",
            str(OSD_MOV),
        ]
    )
    print("OSD sequence", OSD_SEQ_DIR, "movie", OSD_MOV, "unique", len(cache))
    return OSD_MOV


def load_osd_movie() -> bpy.types.Image:
    existing = bpy.data.images.get("OSD_TIMER")
    if existing is not None:
        bpy.data.images.remove(existing)
    img = bpy.data.images.load(str(OSD_MOV), check_existing=False)
    img.name = "OSD_TIMER"
    img.source = "MOVIE"
    img.filepath = str(OSD_MOV)
    iu = getattr(img, "image_user", None)
    if iu is not None:
        iu.frame_duration = 900
        iu.frame_start = 1
        iu.frame_offset = 0
        iu.use_auto_refresh = True
        iu.use_cyclic = False
    try:
        img.reload()
    except Exception:
        pass
    return img


def setup_osd_compositor(scene, osd_img) -> None:
    ng = bpy.data.node_groups.get("OSD_SCREENSPACE")
    if ng is None:
        ng = bpy.data.node_groups.new("OSD_SCREENSPACE", "CompositorNodeTree")
    ng.nodes.clear()
    ng.interface.clear()
    ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    rl.location = (0, 80)
    img_n = ng.nodes.new("CompositorNodeImage")
    img_n.image = osd_img
    img_n.location = (0, -140)
    for attr, val in (("frame_duration", 900), ("frame_start", 1), ("frame_offset", 0)):
        if hasattr(img_n, attr):
            setattr(img_n, attr, val)
    iu = getattr(img_n, "image_user", None)
    if iu is not None:
        iu.frame_duration = 900
        iu.frame_start = 1
        iu.frame_offset = 0
        iu.use_auto_refresh = True
    over = ng.nodes.new("CompositorNodeAlphaOver")
    over.location = (260, 40)
    out = ng.nodes.new("NodeGroupOutput")
    out.location = (480, 40)
    ng.links.new(rl.outputs["Image"], over.inputs[1])
    ng.links.new(img_n.outputs["Image"], over.inputs[2])
    ng.links.new(over.outputs["Image"], out.inputs[0])
    scene.compositing_node_group = ng
    scene.render.use_compositing = True


def attach_camera_osd(cam, osd_img) -> None:
    """Screen-space camcorder HUD in Camera View. Does not inherit CAM roll."""
    cam.data.show_background_images = True
    while cam.data.background_images:
        cam.data.background_images.remove(cam.data.background_images[0])
    bg = cam.data.background_images.new()
    bg.image = osd_img
    bg.alpha = 1.0
    bg.display_depth = "FRONT"
    if hasattr(bg, "frame_method"):
        try:
            bg.frame_method = "STRETCH"
        except TypeError:
            pass
    iu = getattr(bg, "image_user", None)
    if iu is not None:
        iu.frame_duration = 900
        iu.frame_start = 1
        iu.frame_offset = 0
        iu.use_auto_refresh = True
        iu.use_cyclic = False


def unregister_osd_handler() -> None:
    for h in list(bpy.app.handlers.frame_change_pre):
        name = getattr(h, "__name__", "")
        if name in {"osd_frame_handler", "osd_update", "paint_osd_image"}:
            bpy.app.handlers.frame_change_pre.remove(h)
    for h in list(bpy.app.handlers.frame_change_post):
        name = getattr(h, "__name__", "")
        if name in {"osd_frame_handler", "osd_update", "paint_osd_image"}:
            bpy.app.handlers.frame_change_post.remove(h)


def overlay_osd_on_jpeg(jpg: Path, frame: int) -> None:
    """Workbench playblast does not composite; overlay the baked screen-space PNG."""
    src = OSD_SEQ_DIR / f"osd_{frame:04d}.png"
    if not src.exists():
        png = jpg.with_suffix(".osd.png")
        img = paint_osd_image(frame)
        img.filepath_raw = str(png)
        img.file_format = "PNG"
        img.save()
        src = png
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
            str(src),
            "-filter_complex",
            "overlay=0:0",
            "-q:v",
            "3",
            str(tmp),
        ]
    )
    tmp.replace(jpg)


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

    # Floor, looking toward the SE dried-blood corner — not the west wall.
    root.location = (-3.16, 2.14, 0.078)
    root.rotation_euler = (0.0, 0.0, math.radians(-114.0))
    body.location = (0, 0, 0)
    head.location = (0, 0, 0)
    head.rotation_mode = "XYZ"
    head.rotation_euler = (math.radians(85.0), 0.0, math.radians(2.0))
    hand.location = (0, 0, 0)
    cam.location = (0, 0, 0)
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = (0.0, 0.0, math.radians(27.0))

    parent_local(body, root)
    parent_local(head, body)
    parent_local(hand, head)
    parent_local(cam, hand)
    bpy.context.scene.camera = cam
    return root, body, head, hand, cam


# t, x, y, z, yaw_deg  (0=north, +90=west, -90=east)
# Opening faces the blood stain, off-center. Pickup is staged. Frame 900 stays
# at the Room A threshold — does not walk out into Corr A.
ROOT_KEYS = [
    (0.00, -3.160, 2.140, 0.078, -114.0),
    (1.85, -3.159, 2.141, 0.079, -113.5),
    # 2–3s contact: bump, 2–5cm slide, no lift
    (2.08, -3.158, 2.142, 0.080, -113.2),
    (2.16, -3.142, 2.158, 0.088, -110.0),
    (2.28, -3.118, 2.122, 0.084, -116.5),
    (2.42, -3.124, 2.118, 0.081, -114.0),
    (2.62, -3.126, 2.120, 0.080, -113.8),
    (2.88, -3.125, 2.119, 0.079, -114.0),
    (3.00, -3.124, 2.118, 0.080, -114.2),
    # 3–5s pickup: back/side, irregular rise, stall around 1.1m, then eye height
    (3.12, -3.162, 2.148, 0.095, -119.0),
    (3.22, -3.175, 2.155, 0.168, -106.0),
    (3.34, -3.148, 2.132, 0.310, -124.0),
    (3.46, -3.128, 2.118, 0.455, -100.0),
    (3.58, -3.142, 2.108, 0.620, -113.0),
    (3.66, -3.136, 2.102, 0.590, -118.0),
    (3.78, -3.122, 2.095, 0.820, -108.0),
    (3.90, -3.112, 2.090, 1.050, -116.0),
    (4.02, -3.108, 2.088, 1.140, -111.0),
    (4.16, -3.098, 2.082, 1.320, -117.0),
    (4.32, -3.086, 2.076, 1.520, -112.0),
    (4.48, -3.074, 2.072, 1.595, -109.5),
    (4.68, -3.066, 2.070, 1.625, -111.5),
    (4.88, -3.060, 2.072, 1.612, -113.0),
    (5.05, -3.058, 2.074, 1.602, -114.0),
    # 5–8s re-look blood: lean in, hold, small recoil
    (5.40, -3.050, 2.066, 1.590, -116.5),
    (5.80, -3.040, 2.056, 1.568, -118.5),
    (6.35, -3.036, 2.052, 1.562, -117.8),
    (6.90, -3.038, 2.054, 1.566, -117.0),
    (7.30, -3.048, 2.064, 1.582, -115.0),
    (7.75, -3.054, 2.070, 1.595, -112.5),
    (8.15, -3.056, 2.074, 1.602, -108.0),
    # 8–12s look-around: ROOT lags HEAD
    (8.55, -3.058, 2.082, 1.606, -88.0),
    (9.05, -3.064, 2.098, 1.608, -42.0),
    (9.50, -3.070, 2.112, 1.610, -16.0),
    (10.00, -3.074, 2.122, 1.610, -6.0),
    (10.45, -3.072, 2.128, 1.608, 10.0),
    (10.85, -3.070, 2.132, 1.608, 6.0),
    (11.25, -3.066, 2.136, 1.610, -8.0),
    (11.70, -3.060, 2.140, 1.610, -40.0),
    (12.15, -3.054, 2.144, 1.610, -60.0),
    (12.40, -3.050, 2.148, 1.610, -66.0),
    # 12.4–17 walk Room A, not a straight line to the door
    (12.58, -3.10, 2.20, 1.612, -50.0),
    (13.10, -3.36, 2.46, 1.610, -18.0),
    (13.48, -3.58, 2.60, 1.608, 14.0),
    (13.72, -3.62, 2.62, 1.606, 18.0),
    (13.95, -3.63, 2.625, 1.605, 16.0),
    (14.40, -3.63, 2.628, 1.606, 8.0),
    (14.62, -3.58, 2.70, 1.608, -10.0),
    (15.15, -3.40, 3.20, 1.610, -32.0),
    (15.60, -3.12, 3.30, 1.610, -58.0),
    (16.10, -2.74, 3.28, 1.608, -80.0),
    (16.55, -2.42, 3.26, 1.606, -86.0),
    (17.00, -2.18, 3.22, 1.604, -90.0),
    # 17–21 approach the opening, stop, behind-check, then sidestep behind the wall
    (17.45, -2.06, 3.18, 1.602, -92.0),
    (17.95, -2.00, 3.16, 1.600, -90.0),
    (18.35, -1.998, 3.15, 1.598, -88.0),
    (18.85, -1.996, 3.145, 1.598, -84.0),
    (19.20, -1.995, 3.14, 1.597, -76.0),
    (19.55, -1.994, 3.14, 1.597, -82.0),
    (20.00, -1.993, 3.12, 1.598, -88.0),
    (20.55, -1.992, 3.02, 1.598, -90.0),
    (21.15, -1.90, 2.94, 1.598, -90.0),
    (21.65, -1.86, 2.87, 1.598, -91.0),
    # 21.6–28 stand south of the jamb; HEAD peeks north
    (22.40, -1.86, 2.87, 1.598, -90.0),
    (23.40, -1.86, 2.87, 1.598, -91.0),
    (24.50, -1.86, 2.87, 1.598, -90.0),
    (26.10, -1.86, 2.87, 1.598, -88.0),
    (27.40, -1.86, 2.87, 1.598, -86.0),
    (28.10, -1.80, 2.94, 1.600, -84.0),
    # HEAD already out; BODY then ROOT arc to the threshold and STOP
    (28.45, -1.92, 2.98, 1.602, -82.0),
    (28.80, -1.78, 3.08, 1.604, -90.0),
    (29.15, -1.66, 3.14, 1.604, -100.0),
    (29.50, -1.60, 3.17, 1.602, -106.0),
    (29.80, -1.58, 3.18, 1.600, -103.0),
    (30.00, -1.57, 3.19, 1.600, -101.0),
]

# pitch (+=up), yaw (+=left relative to body). Head leads root turns.
LOOK_KEYS = [
    (0.00, -5.0, 2.0),
    (1.90, -4.6, 1.6),
    (2.12, -1.5, -5.0),
    (2.22, 4.0, 6.0),
    (2.36, -7.0, -4.0),
    (2.52, -4.2, 1.2),
    (2.85, -5.0, 2.0),
    (3.00, -4.5, 1.4),
    (3.14, 3.0, -9.0),
    (3.26, -9.0, 12.0),
    (3.40, 7.0, -7.0),
    (3.55, -12.0, 5.0),
    (3.70, 2.5, -6.0),
    (3.85, -7.0, 4.0),
    (4.00, 0.8, -2.5),
    (4.18, -4.0, 3.5),
    (4.36, -3.0, -1.0),
    (4.68, -5.0, 1.2),
    (4.88, -10.0, 0.6),
    (5.05, -14.0, -2.0),
    # re-look stain, imperfect framing, pause, lean, recoil
    (5.28, -12.0, -6.0),
    (5.55, -22.0, -12.0),
    (5.82, -28.0, -20.0),
    (6.10, -31.0, -22.0),
    (6.28, -32.0, -21.0),
    (6.48, -29.0, -18.0),
    (6.95, -30.0, -17.0),
    (7.25, -28.0, -10.0),
    (7.55, -20.0, -4.0),
    (7.90, -12.0, 2.0),
    (8.18, -7.0, 6.0),
    (8.38, -6.0, 12.0),
    (8.55, -6.5, 18.0),
    (8.78, -6.0, 26.0),
    (9.00, -6.5, 34.0),
    (9.22, -7.0, 40.0),
    (9.40, -6.5, 43.0),
    (9.58, -6.0, 38.0),
    (9.85, -6.2, 36.0),
    (10.08, -6.0, 44.0),
    (10.28, -6.5, 50.0),
    (10.48, -7.0, 54.0),
    (10.62, -6.5, 57.0),
    (10.80, -6.5, 52.0),
    (11.08, -7.0, 40.0),
    (11.28, -6.5, 28.0),
    (11.50, -6.5, 14.0),
    (11.72, -6.0, 2.0),
    (11.92, -6.5, -10.0),
    (12.10, -7.0, -16.0),
    (12.26, -6.5, -18.0),
    (12.42, -6.5, -12.0),
    (12.70, -6.5, -4.0),
    (13.05, -7.0, 12.0),
    (13.35, -6.5, 22.0),
    (13.58, -6.0, 26.0),
    (13.85, -7.0, 24.0),
    (14.20, -6.5, 16.0),
    (14.55, -6.5, 6.0),
    (14.95, -7.0, -8.0),
    (15.40, -6.5, -4.0),
    (15.85, -6.5, 4.0),
    (16.30, -6.0, 8.0),
    (16.80, -6.5, 6.0),
    (17.30, -6.0, 4.0),
    (17.80, -5.5, 3.0),
    (18.20, -5.5, 2.0),
    (18.40, -5.5, 4.0),
    # behind check over the right shoulder, toward the room they walked
    (18.55, -5.0, -10.0),
    (18.68, -5.5, -38.0),
    (18.82, -12.0, -72.0),
    (18.96, -14.0, -94.0),
    (19.10, -16.0, -108.0),
    (19.24, -15.0, -102.0),
    (19.50, -14.0, -98.0),
    (19.85, -6.0, -82.0),
    (20.20, -6.0, -48.0),
    (20.55, -6.0, -16.0),
    (20.90, -5.5, -4.0),
    (21.25, -5.5, 2.0),
    (21.60, -5.5, 6.0),
    (21.95, -5.0, 8.0),
    (22.25, -5.5, 11.0),
    (22.55, -6.0, 13.0),
    (22.85, -5.5, 12.0),
    (23.20, -6.0, 7.0),
    (23.55, -6.0, 4.0),
    (23.95, -6.0, 3.0),
    (24.40, -6.5, 3.0),
    (24.90, -6.0, 8.0),
    (25.35, -5.5, 12.0),
    (25.85, -6.0, 16.0),
    (26.30, -5.5, 18.0),
    (26.70, -6.0, 14.0),
    (27.10, -6.5, 10.0),
    (27.45, -6.0, 12.0),
    (27.85, -6.5, 8.0),
    (28.20, -6.0, 4.0),
    (28.55, -6.0, 2.0),
    (28.90, -6.5, -2.0),
    (29.20, -6.0, 6.0),
    (29.45, -5.5, 10.0),
    (29.68, -6.0, 5.0),
    (29.85, -6.0, 2.0),
    (30.00, -6.5, 4.0),
]

# Image roll on CAM local Z. Large only while the camcorder is on the floor / being lifted.
ROLL_KEYS = [
    (0.00, 27.0),
    (1.90, 26.2),
    (2.12, 31.0),
    (2.22, 34.5),
    (2.36, 21.0),
    (2.52, 29.0),
    (2.85, 26.5),
    (3.00, 26.8),
    (3.14, 16.0),
    (3.28, 38.0),
    (3.44, 6.0),
    (3.60, -16.0),
    (3.72, 22.0),
    (3.84, -14.0),
    (3.96, 16.0),
    (4.10, -9.0),
    (4.24, 7.0),
    (4.40, -3.5),
    (4.58, 1.8),
    (4.76, -0.7),
    (4.92, 0.4),
    (5.12, 0.2),
    (6.20, 0.7),
    (7.30, -0.5),
    (8.20, 0.3),
    (10.50, 0.9),
    (13.50, -0.7),
    (14.20, 0.3),
    (18.40, 0.2),
    (19.12, 1.5),
    (19.50, 0.3),
    (22.60, 0.6),
    (23.55, -0.4),
    (26.30, 0.5),
    (29.20, -0.3),
    (30.00, 0.2),
]

# Facing east (ROOT yaw ≈ -90): local +X is world south. Negative X peeks north into the door.
PEEK_KEYS = [
    (0.00, 0.0, 0.0, 0.0),
    (21.35, 0.0, 0.0, 0.0),
    (21.70, -0.04, 0.0, 0.0),
    (22.05, -0.08, 0.002, 0.0),
    (22.35, -0.115, 0.004, 0.002),
    (22.70, -0.125, 0.004, 0.002),
    (23.00, -0.120, 0.003, 0.002),
    (23.30, -0.078, 0.002, 0.0),
    (23.60, -0.065, 0.001, 0.0),
    (24.30, -0.062, 0.001, 0.0),
    (24.90, -0.080, 0.002, 0.0),
    (25.35, -0.12, 0.003, 0.002),
    (25.80, -0.170, 0.005, 0.003),
    (26.25, -0.195, 0.006, 0.004),
    (26.80, -0.168, 0.005, 0.003),
    (27.30, -0.150, 0.004, 0.002),
    (27.90, -0.120, 0.003, 0.002),
    (28.35, -0.070, 0.002, 0.0),
    (28.75, -0.025, 0.0, 0.0),
    (29.15, 0.0, 0.0, 0.0),
    (30.00, 0.0, 0.0, 0.0),
]

WALK_SPANS = [
    (12.52, 13.78),
    (14.55, 17.25),
    (28.50, 29.35),
]

# Irregular step durations 0.55–0.72s. Not a fixed period.
STEP_DURS = (0.61, 0.67, 0.58, 0.64, 0.70, 0.60, 0.66, 0.59, 0.71, 0.63, 0.57, 0.68)
STEP_AZ = (0.012, 0.018, 0.011, 0.020, 0.015, 0.022, 0.010, 0.017, 0.014, 0.019, 0.013, 0.016)
STEP_AX = (0.009, 0.015, 0.011, 0.017, 0.010, 0.018, 0.008, 0.014, 0.012, 0.016, 0.009, 0.013)
STEP_AY = (0.005, 0.009, 0.004, 0.010, 0.006, 0.008, 0.005, 0.007, 0.004, 0.009, 0.006, 0.008)


def walk_weight(t: float) -> float:
    best = 0.0
    for a, b in WALK_SPANS:
        if a <= t <= b:
            edge = min(t - a, b - t, 0.28) / 0.28
            best = max(best, max(0.0, min(1.0, edge)) ** 1.35)
    return best


def build_steps():
    steps = []
    t = 0.0
    i = 0
    while t < DURATION + 2.0:
        d = STEP_DURS[i % len(STEP_DURS)]
        steps.append(
            (
                t,
                t + d,
                STEP_AZ[i % len(STEP_AZ)],
                STEP_AX[i % len(STEP_AX)],
                STEP_AY[i % len(STEP_AY)],
                1 if i % 2 == 0 else -1,
            )
        )
        t += d
        i += 1
    return steps


STEPS = build_steps()

# Irregular breath cycles 3–5s, not a perfect sine.
BREATH = []
_bt = 0.0
for _p, _a in (
    (3.35, 0.0020),
    (4.55, 0.0016),
    (3.80, 0.0022),
    (4.90, 0.0015),
    (3.20, 0.0019),
    (4.25, 0.0017),
    (3.65, 0.0021),
    (4.70, 0.0014),
):
    BREATH.append((_bt, _bt + _p, _p, _a))
    _bt += _p


def breath_z(t: float) -> float:
    for a, b, p, amp in BREATH:
        if a <= t <= b:
            u = (t - a) / p
            if u < 0.36:
                k = (u / 0.36) ** 1.15
            else:
                k = 1.0 - ((u - 0.36) / 0.64) ** 0.85
            return amp * k
    return 0.0


def _step_vert(u: float) -> float:
    """Foot contact → settle → weight transfer → mid-step rise → next contact."""
    if u < 0.12:
        return lerp(0.0, -0.28, u / 0.12)
    if u < 0.28:
        return lerp(-0.28, 0.06, (u - 0.12) / 0.16)
    if u < 0.52:
        return lerp(0.06, 1.0, (u - 0.28) / 0.24)
    if u < 0.78:
        return lerp(1.0, 0.16, (u - 0.52) / 0.26)
    return lerp(0.16, 0.0, (u - 0.78) / 0.22)


def _step_lat(u: float, side: float) -> float:
    if u < 0.16:
        k = 1.0
    elif u < 0.46:
        k = lerp(1.0, 0.08, (u - 0.16) / 0.30)
    else:
        k = lerp(0.08, -1.0, (u - 0.46) / 0.54)
    return side * k


def _step_fwd(u: float) -> float:
    if u < 0.14:
        return lerp(-0.40, 0.04, u / 0.14)
    if u < 0.48:
        return lerp(0.04, 1.0, (u - 0.14) / 0.34)
    return lerp(1.0, -0.22, (u - 0.48) / 0.52)


def body_offset(t: float):
    w = walk_weight(t)
    x = y = z = 0.0
    roll = pitch = yaw = 0.0
    if w > 1e-4:
        for a, b, az, ax, ay, side in STEPS:
            if a <= t <= b:
                u = (t - a) / max(1e-6, b - a)
                z = w * az * _step_vert(u)
                x = w * ax * _step_lat(u, side)
                y = w * ay * _step_fwd(u)
                roll = w * math.radians(0.32 * _step_lat(u, side))
                pitch = w * math.radians(-0.20 * _step_vert(u))
                yaw = w * math.radians(0.10 * side * (0.35 if u < 0.5 else -0.25))
                break
    idle = 1.0 - w
    z += breath_z(t) * (0.55 + 0.85 * idle)
    # Slow posture drift, not a walk cycle.
    x += idle * 0.00055 * math.sin(t * 0.47 + 0.9)
    y += idle * 0.00035 * math.sin(t * 0.31 + 1.7)
    z += idle * 0.00025 * math.sin(t * 0.19 + 0.4)
    # Contact bump on the body, 2.1–2.6s only.
    if 2.10 <= t <= 2.58:
        u = (t - 2.10) / 0.48
        env = (1.0 - u) ** 1.7
        if t < 2.22:
            z += 0.0045 * env
            x += 0.0030 * env
        elif t < 2.34:
            z -= 0.0035 * env
            x -= 0.0020 * env
        else:
            z += 0.0015 * env
    return x, y, z, pitch, roll, yaw


GRIP_TIMES = (4.82, 8.18, 15.58, 23.88)


def hand_offset(t: float):
    hx = 0.0010 * math.sin(t * 4.7 + 0.3) + 0.0005 * math.sin(t * 1.6 + 2.1)
    hy = 0.0008 * math.sin(t * 3.8 + 1.1) + 0.0004 * math.sin(t * 2.3 + 0.4)
    hz = 0.0006 * math.sin(t * 3.2 + 0.7) + 0.00035 * math.sin(t * 1.1 + 1.8)
    rx = math.radians(0.05 * math.sin(t * 3.6 + 0.5))
    ry = math.radians(0.04 * math.sin(t * 4.5 + 1.4))
    rz = math.radians(0.05 * math.sin(t * 5.2 + 0.9))
    for g in GRIP_TIMES:
        d = abs(t - g)
        if d < 0.10:
            k = 1.0 - d / 0.10
            hx += 0.0014 * k
            rz += math.radians(0.28 * k)
            ry += math.radians(-0.18 * k)
    return hx, hy, hz, rx, ry, rz


def animate(root, body, head, hand, cam):
    for t, x, y, z, yaw in ROOT_KEYS:
        f = frame_at(t)
        insert_xyz(root, "location", f, (x, y, z))
        insert_xyz(root, "rotation_euler", f, (0.0, 0.0, math.radians(yaw)))
    for t, roll in ROLL_KEYS:
        f = frame_at(t)
        insert_xyz(cam, "rotation_euler", f, (0.0, 0.0, math.radians(roll)))
    shape_sparse_fcurves(root)
    shape_sparse_fcurves(cam)

    dt = 1.0 / FPS
    t = 0.0
    last = -1
    walking = False
    while t <= DURATION + 1e-6:
        f = frame_at(t)
        if f != last:
            w = walk_weight(t)
            walking = w > 0.02
            # Dense keys while walking (foot contacts). Sparse-ish while standing.
            key_body = walking or (f % 3 == 1) or t < 5.2
            if key_body:
                bx, by, bz, bp, br, bya = body_offset(t)
                insert_xyz(body, "location", f, (bx, by, bz))
                insert_xyz(body, "rotation_euler", f, (bp, br, bya))
                pitch, hyaw = sample_keys(LOOK_KEYS, t, 2)
                # Head counters 50–70% of body so the lens is not chest-locked.
                pitch -= math.degrees(bp) * 0.62
                hyaw -= math.degrees(bya) * 0.58
                insert_xyz(
                    head,
                    "rotation_euler",
                    f,
                    (math.radians(90.0 + pitch), 0.0, math.radians(hyaw)),
                )
                px, py, pz = sample_keys(PEEK_KEYS, t, 3)
                insert_xyz(
                    head,
                    "location",
                    f,
                    (px - 0.62 * bx, py - 0.30 * by, pz - 0.22 * bz),
                )
            if walking or (f % 4 == 1) or t < 5.2:
                hx, hy, hz, hrx, hry, hrz = hand_offset(t)
                insert_xyz(hand, "location", f, (hx, hy, hz))
                insert_xyz(hand, "rotation_euler", f, (hrx, hry, hrz))
            last = f
        t += dt
    add_noise_mods(hand, "location", 13.0, 0.00028, 1.6)
    add_noise_mods(hand, "rotation_euler", 18.0, 0.00022, 3.1)


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


def setup_scene(scene, cam, osd_img):
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
    setup_osd_compositor(scene, osd_img)
    attach_camera_osd(cam, osd_img)
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
        if 21.3 <= t <= 28.4 or t >= 28.4:
            r = 0.12
        else:
            r = 0.20
        if t < 3.02:
            if p.z < 0.045 or p.z > 0.16:
                problems.append(f"f{f} floor height {p.z:.3f}")
        elif t > 5.05:
            if p.z < 1.40 or p.z > 1.80:
                problems.append(f"f{f} height {p.z:.3f}")
        if t >= 5.05:
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
                    f"f{f} clip {(loc-p).length:.3f} {obj.name if obj else '?'} {tuple(round(x, 2) for x in loc)}"
                )
                break
    return problems


def blood_screen_note(cam) -> str:
    blood = bpy.data.objects.get("BLOOD.RoomA.Dried")
    if blood is None:
        return "no-blood"
    p = cam.matrix_world.translation
    to_b = Vector((BLOOD_C[0], BLOOD_C[1], 0.01)) - p
    look = look_vector(cam)
    if to_b.length < 1e-6:
        return "on-blood"
    ang = math.degrees(look.angle(to_b.normalized()))
    return f"blood_ang={ang:.1f} dist={to_b.length:.2f}"


def print_sanity():
    scene = bpy.context.scene
    labels = (
        (0.0, "floor"),
        (2.25, "contact"),
        (3.0, "prelift"),
        (4.0, "pickup"),
        (5.0, "settled"),
        (6.4, "blood look"),
        (9.4, "look fwd"),
        (10.5, "look left"),
        (12.2, "look exit"),
        (13.9, "walk pause"),
        (16.5, "wander"),
        (18.4, "at door"),
        (19.15, "look back"),
        (22.7, "peek 1"),
        (23.7, "retract"),
        (26.4, "peek 2"),
        (29.6, "threshold"),
        (30.0, "cut"),
    )
    for t, label in labels:
        scene.frame_set(frame_at(t))
        bpy.context.evaluated_depsgraph_get().update()
        cam = bpy.data.objects["CAM_MAIN"]
        p = cam.matrix_world.translation
        v = look_vector(cam)
        heading = math.degrees(math.atan2(-v.x, v.y))
        roll = cam_roll_deg(cam)
        extra = blood_screen_note(cam) if t in (0.0, 6.4) else ""
        print(
            f"  t={t:5.2f} {label:12s} pos=({p.x:6.2f},{p.y:6.2f},{p.z:5.2f}) "
            f"look=({v.x:5.2f},{v.y:5.2f},{v.z:5.2f}) yaw={heading:7.1f} roll={roll:6.1f} {extra}"
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


STILL_FRAMES = (
    (1, "floor"),
    (68, "contact"),
    (90, "prelift"),
    (112, "pickup"),
    (150, "settled"),
    (192, "blood_look"),
    (282, "look_fwd"),
    (318, "look_left"),
    (418, "walk_pause"),
    (552, "at_door"),
    (575, "look_back"),
    (682, "peek1"),
    (712, "retract"),
    (793, "peek2"),
    (888, "threshold"),
    (900, "cut"),
)


def render_stills(scene) -> Path:
    out_dir = PREVIEW_DIR / "check"
    out_dir.mkdir(parents=True, exist_ok=True)
    configure_preview(scene)
    for f, label in STILL_FRAMES:
        scene.frame_set(f)
        path = out_dir / f"{label}_{f:04d}.jpg"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        overlay_osd_on_jpeg(path, f)
        print("still", path)
    return out_dir


def overlay_preview_frames(frame_dir: Path) -> None:
    osd_dir = PREVIEW_DIR / "osd"
    osd_dir.mkdir(parents=True, exist_ok=True)
    for f in range(1, 901):
        src = OSD_SEQ_DIR / f"osd_{f:04d}.png"
        dst = osd_dir / f"osd_{f:04d}.png"
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.symlink_to(src)
    print("osd links", 900)


def main():
    args = parse_args()
    scene = bpy.context.scene
    hide_previous_take()
    clear_this_take()
    ensure_blood()
    col = new_col(COLL)
    root, body, head, hand, cam = build_rig(col)
    animate(root, body, head, hand, cam)
    add_path_guide(col)
    unregister_osd_handler()
    write_osd_sequence()
    osd_img = load_osd_movie()
    setup_scene(scene, cam, osd_img)

    print("Sanity poses:")
    print_sanity()
    problems = collision_report()
    print("Collision/horizon hits", len(problems))
    for line in problems[:24]:
        print(" ", line)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH, "frames", scene.frame_start, scene.frame_end)
    print(
        "OSD timer: movie",
        OSD_MOV,
        "driven by scene frame (no frame_change_pre).",
    )

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
