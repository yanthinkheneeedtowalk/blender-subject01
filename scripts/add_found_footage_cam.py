#!/usr/bin/env python3
"""Add a found-footage camera rig to the EXISTING backrooms.blend.

Does not rebuild walls, floor, ceiling, or lights.

  blender -b backrooms.blend --python scripts/add_found_footage_cam.py -- --check
  blender -b backrooms.blend --python scripts/add_found_footage_cam.py -- --preview
  blender -b backrooms.blend --python scripts/add_found_footage_cam.py -- --stills
  blender -b backrooms.blend --python scripts/add_found_footage_cam.py -- --master
"""

from __future__ import annotations

import math
import random
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "backrooms.blend"
PREVIEW_DIR = ROOT / "renders" / "found_footage_preview"
MASTER_DIR = ROOT / "renders" / "found_footage_master"
STILLS_DIR = ROOT / "renders" / "found_footage_stills"
VHS_DIR = ROOT / "renders" / "found_footage_vhs"

FPS = 30
DURATION = 26.0
CAM_Z = 1.63
COLLISION_R = 0.20
COLL = "CAM_FOUND_FOOTAGE_01"


def parse_args() -> dict:
    mode = "check"
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--preview" in argv:
        mode = "preview"
    if "--stills" in argv:
        mode = "stills"
    if "--master" in argv:
        mode = "master"
    if "--vhs" in argv:
        mode = "vhs"
    return {"mode": mode}


def frame_at(t: float) -> int:
    return max(1, int(round(1 + t * FPS)))


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


def insert_xyz(obj: bpy.types.Object, path: str, frame: int, value, interp: str = "BEZIER") -> None:
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


def set_overshoot_handles(obj: bpy.types.Object, path: str, frame: int) -> None:
    for fc in iter_fcurves(obj):
        if fc.data_path != path:
            continue
        for kp in fc.keyframe_points:
            if int(round(kp.co[0])) == frame:
                kp.handle_left_type = "FREE"
                kp.handle_right_type = "FREE"
                kp.easing = "EASE_IN_OUT"


def add_noise_mods(obj, data_path: str, scale: float, strength: float, seed: float) -> None:
    n = 0
    for fc in iter_fcurves(obj):
        if fc.data_path != data_path:
            continue
        # Replace existing noise so re-runs stay editable and non-destructive.
        for mod in list(fc.modifiers):
            if mod.type == "NOISE":
                fc.modifiers.remove(mod)
        mod = fc.modifiers.new("NOISE")
        mod.scale = scale + 0.85 * n
        mod.strength = strength
        mod.phase = seed + n * 1.7
        mod.depth = 1
        mod.use_restricted_range = False
        n += 1


def clear_old_rig() -> None:
    if COLL in bpy.data.collections:
        col = bpy.data.collections[COLL]
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    for name in ("CAM_ROOT", "CAM_BODY", "CAM_LOOK", "CAM_FoundFootage", "Camera", "CAM_PATH_GUIDE"):
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.type in {"EMPTY", "CAMERA", "CURVE"}:
            # Keep the existing plan / walk cameras.
            if name == "Camera" and obj.type == "CAMERA":
                # Only remove if it belongs to a previous found-footage pass.
                if obj.parent and obj.parent.name == "CAM_LOOK":
                    bpy.data.objects.remove(obj, do_unlink=True)
            elif name != "Camera":
                bpy.data.objects.remove(obj, do_unlink=True)
    for act_name in (
        "CAM_ROOTAction",
        "CAM_BODYAction",
        "CAM_LOOKAction",
        "CameraAction",
        "CAM_FoundFootageAction",
    ):
        act = bpy.data.actions.get(act_name)
        if act is not None:
            bpy.data.actions.remove(act)


def collection() -> bpy.types.Collection:
    col = bpy.data.collections.new(COLL)
    bpy.context.scene.collection.children.link(col)
    return col


def make_empty(name: str, col: bpy.types.Collection, size: float = 0.18) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = size
    col.objects.link(obj)
    return obj


def parent_local(child: bpy.types.Object, parent_obj: bpy.types.Object) -> None:
    child.parent = parent_obj
    child.matrix_parent_inverse.identity()


# ---------------------------------------------------------------------------
# Route in world metres. Yaw 0 = north (+Y), +90 = west (−X), −90 = east (+X).
#
# Measured from backrooms.blend (do not regenerate the map):
#   Entrance interior  x 4.60–5.80, y −4.80–−0.60, door south open
#   Main east opening  x 4.40–4.60, y −3.20–−1.40
#   Main interior      x −0.60–4.40, y −4.80–−0.80
#   L-stub             x 1.60–1.90, y −3.20–−0.80  (keep x >= 2.02 while y <= −0.80)
#   Main north opening x 1.00–2.60, y −0.80–−0.60
#   Hall B             y −0.40–0.80, x ~−4.7–4.4
#   Core mass          x 2.20–4.40, y 1.20–3.40 (behind WALL.HallB.NorthE y=0.80)
# ---------------------------------------------------------------------------

ROOT_KEYS = [
    # t, x, y, yaw_deg
    (0.00, 5.26, -4.420, 7.0),
    (1.00, 5.263, -4.416, 6.0),
    (2.00, 5.258, -4.412, 8.0),
    (2.80, 5.22, -3.82, 14.0),
    (3.60, 5.14, -3.12, 34.0),
    (4.40, 4.68, -2.50, 64.0),
    (5.20, 4.02, -2.36, 80.0),
    (6.20, 3.28, -2.24, 86.0),
    (7.00, 2.88, -2.20, 88.0),
    (8.20, 2.62, -2.18, 92.0),
    (9.00, 2.56, -2.16, 90.0),
    (9.50, 2.562, -2.158, 88.0),  # pause ~0.5s, 0.76m east of StubV
    (10.20, 2.42, -1.88, 58.0),
    (11.10, 2.22, -1.28, 24.0),
    (12.05, 2.08, -0.90, 8.0),  # still south of north wall, east of stub
    (12.55, 1.92, -0.48, 18.0),  # through opening; start yawing into Hall B
    (13.40, 1.62, -0.02, 48.0),
    (14.20, 1.48, 0.14, 72.0),  # look west down Hall B, not into the north wall
    (15.20, 1.44, 0.18, 82.0),
    (16.40, 1.42, 0.20, 86.0),
    (16.80, 1.421, 0.201, 87.0),
    (17.20, 1.419, 0.199, 88.0),  # full stop ~0.8s, glance west / Room B
    (18.00, 1.420, 0.200, 86.0),
    (18.50, 1.421, 0.200, 84.0),
    (19.20, 1.422, 0.200, 70.0),  # body lags the head snap
    (20.40, 1.424, 0.200, 10.0),
    (22.00, 1.52, 0.20, -36.0),
    (23.00, 1.98, 0.21, -28.0),
    (24.20, 2.46, 0.22, -52.0),
    (25.40, 2.80, 0.23, -62.0),  # ENE down Hall B; Core stays behind the north wall
    (25.70, 2.84, 0.231, -60.0),
    (26.00, 2.86, 0.232, -58.0),
]

# Additive head: pitch (deg, − = down), yaw (deg, + = left/west), roll
LOOK_KEYS = [
    (0.00, -4.0, 3.0, 0.4),
    (0.65, -5.4, 4.2, 0.6),
    (1.45, -1.1, 1.8, 0.2),
    (2.00, 0.6, 1.2, -0.2),
    (3.10, 1.0, 8.0, 0.3),  # eyes into Main before the body finishes turning
    (4.05, 0.5, 16.0, 0.6),
    (5.10, 0.3, 7.0, 0.2),
    (6.80, 0.2, 4.0, -0.3),
    (8.20, 0.5, 18.0, 0.4),  # start looking left at the L-stub
    (8.85, 0.8, 42.0, 0.9),  # peek the L-corner / behind the jog; eyes first
    (9.40, 0.3, 24.0, 0.4),
    (9.85, 0.4, -52.0, -0.3),  # eyes toward Hall B ~0.35s before body
    (10.55, 0.3, -22.0, 0.1),
    (12.00, 0.4, -4.0, -0.2),
    (13.20, 0.3, 8.0, 0.2),
    (14.60, 0.4, 10.0, 0.3),
    (16.10, 0.8, 8.0, 0.4),  # glance Room B / west, do not enter
    (17.30, 1.0, 12.0, 0.6),
    (18.20, 0.5, 10.0, 0.3),
    (18.50, 0.4, 8.0, 0.2),  # snap start (looking west down Hall B)
    (18.95, 0.2, -32.0, -1.0),  # Core / Hall N, ~48° + 2° overshoot
    (19.35, 0.3, -12.0, -0.2),  # correction back along the hall
    (20.60, 0.4, -10.0, 0.2),
    (22.00, 0.5, -10.0, 0.1),
    (23.40, 1.2, -6.0, 0.4),  # lean / peek forward along Hall B east
    (25.20, 0.7, -4.0, 0.2),
    (25.55, 0.4, -8.0, 0.1),
    (26.00, 0.3, -7.0, 0.2),
]

WALK_SPANS = [
    (2.00, 9.00),
    (10.00, 16.40),
    (22.00, 25.40),
]


def walk_weight(t: float) -> float:
    best = 0.0
    for a, b in WALK_SPANS:
        if a <= t <= b:
            edge = min(t - a, b - t, 0.35) / 0.35
            best = max(best, smoothstep(max(0.0, min(1.0, edge))))
    return best


def exposure_at(t: float) -> float:
    # Consumer auto-exposure: brief overshoot entering Main lights, slow pullback.
    keys = [
        (0.0, 0.10),
        (2.2, 0.11),
        (2.55, 0.38),  # ~0.2s overexpose entering fluorescents
        (3.20, 0.16),
        (7.0, 0.15),
        (9.5, 0.13),
        (12.8, 0.21),
        (14.2, 0.18),
        (16.2, 0.10),
        (18.6, 0.09),
        (19.1, 0.26),
        (19.8, 0.14),
        (22.6, 0.24),
        (26.0, 0.28),
    ]
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            return lerp(v0, v1, smoothstep((t - t0) / max(1e-6, t1 - t0)))
    return keys[-1][1]


def build_rig(col: bpy.types.Collection) -> tuple:
    root = make_empty("CAM_ROOT", col, 0.22)
    body = make_empty("CAM_BODY", col, 0.12)
    look = make_empty("CAM_LOOK", col, 0.10)
    data = bpy.data.cameras.new("CAM_FoundFootage")
    data.lens = 26.0
    data.sensor_width = 36.0
    data.sensor_height = 27.0
    data.sensor_fit = "HORIZONTAL"
    data.clip_start = 0.05
    data.clip_end = 40.0
    data.dof.use_dof = True
    data.dof.aperture_fstop = 8.0
    data.dof.focus_distance = 3.4
    cam = bpy.data.objects.new("Camera", data)
    col.objects.link(cam)

    root.location = (ROOT_KEYS[0][1], ROOT_KEYS[0][2], CAM_Z)
    root.rotation_euler = (0.0, 0.0, math.radians(ROOT_KEYS[0][3]))
    body.location = (0.0, 0.0, 0.0)
    look.location = (0.0, 0.0, 0.0)
    # X = +90 looks along parent +Y (north) when root yaw is 0.
    look.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    cam.location = (0.0, 0.0, 0.0)
    cam.rotation_euler = (0.0, 0.0, 0.0)

    parent_local(body, root)
    parent_local(look, body)
    parent_local(cam, look)

    bpy.context.scene.camera = cam
    return root, body, look, cam


def animate_root(root: bpy.types.Object) -> None:
    root.rotation_mode = "XYZ"
    for t, x, y, yaw in ROOT_KEYS:
        f = frame_at(t)
        insert_xyz(root, "location", f, (x, y, CAM_Z))
        insert_xyz(root, "rotation_euler", f, (0.0, 0.0, math.radians(yaw)))


def animate_look(look: bpy.types.Object) -> None:
    look.rotation_mode = "XYZ"
    rng = random.Random(7)
    t = 0.0
    dt = 1.0 / FPS
    last_f = -1
    # Narrative look sampled onto every frame with walk micro-corrections mixed in.
    look_sorted = list(LOOK_KEYS)

    def sample_look(tt: float):
        if tt <= look_sorted[0][0]:
            return look_sorted[0][1], look_sorted[0][2], look_sorted[0][3]
        for (t0, p0, y0, r0), (t1, p1, y1, r1) in zip(look_sorted, look_sorted[1:]):
            if t0 <= tt <= t1:
                u = smoothstep((tt - t0) / max(1e-6, t1 - t0))
                return lerp(p0, p1, u), lerp(y0, y1, u), lerp(r0, r1, u)
        return look_sorted[-1][1], look_sorted[-1][2], look_sorted[-1][3]

    while t <= DURATION + 1e-6:
        f = frame_at(t)
        if f != last_f:
            pitch, yaw, roll = sample_look(t)
            w = walk_weight(t)
            # Head micro-corrections while walking; breathing-scale drift while idle.
            pitch += w * 0.42 * math.sin(t * 10.7 + 0.3)
            yaw += w * 0.45 * math.sin(t * 7.3 + 1.1)
            roll += w * 0.38 * math.sin(t * 9.1 + 0.6)
            pitch += (1.0 - 0.55 * w) * 0.12 * math.sin(t * 1.7)
            yaw += (1.0 - 0.55 * w) * 0.10 * math.sin(t * 1.35 + 0.4)
            insert_xyz(
                look,
                "rotation_euler",
                f,
                (
                    math.radians(90.0 + pitch),
                    math.radians(roll),
                    math.radians(yaw),
                ),
            )
            # Breathing / idle drift on the head, always on.
            bz = 0.0032 * math.sin(t * 1.55) + 0.0011 * math.sin(t * 0.47)
            bx = 0.0014 * math.sin(t * 0.83 + 0.6)
            by = 0.0011 * math.sin(t * 0.61 + 1.2)
            insert_xyz(look, "location", f, (bx, by, bz))
            last_f = f
        t += dt
    set_overshoot_handles(look, "rotation_euler", frame_at(18.95))
    set_overshoot_handles(look, "rotation_euler", frame_at(19.35))
    add_noise_mods(look, "rotation_euler", 13.0, 0.00055, 3.2)
    add_noise_mods(look, "location", 9.5, 0.00045, 4.1)
    _ = rng  # keep seed available if we later jitter key times


def animate_body(body: bpy.types.Object) -> None:
    rng = random.Random(11)
    t = 0.0
    phase = 0.0
    dt = 1.0 / FPS
    last_f = -1
    while t <= DURATION + 1e-6:
        f = frame_at(t)
        if f != last_f:
            w = walk_weight(t)
            step_var = 0.92 + 0.08 * math.sin(t * 2.13) + rng.uniform(-0.03, 0.03) * w
            freq = lerp(1.62, 1.88, 0.5 + 0.5 * math.sin(t * 0.47))
            phase += dt * 2.0 * math.pi * freq * step_var
            amp_z = lerp(0.015, 0.025, 0.5 + 0.5 * math.sin(t * 1.17 + 0.4))
            amp_x = lerp(0.008, 0.018, 0.5 + 0.5 * math.sin(t * 0.91))
            z = w * amp_z * math.sin(phase) * (1.0 + 0.12 * math.sin(phase * 0.5 + 0.7))
            x = w * amp_x * math.sin(phase + math.pi * 0.5) * (1.0 + 0.18 * math.sin(t * 0.73))
            x += w * 0.004 * math.sin(t * 0.35)
            insert_xyz(body, "location", f, (x, 0.0, z), interp="BEZIER")
            # Body sway stops with the walk. Pitch/roll/yaw micro only while moving.
            bp = w * math.radians(0.42 * math.sin(phase + 0.2))
            br = w * math.radians(0.38 * math.sin(phase + math.pi * 0.5))
            by = w * math.radians(0.40 * math.sin(phase * 0.5 + 0.9))
            insert_xyz(body, "rotation_euler", f, (bp, br, by), interp="BEZIER")
            last_f = f
        t += dt
    add_noise_mods(body, "location", 8.0, 0.00035, 1.4)


def animate_hand_jitter(cam: bpy.types.Object) -> None:
    rng = random.Random(23)
    t = 0.0
    dt = 2.0 / FPS
    while t <= DURATION + 1e-6:
        f = frame_at(t)
        px = rng.uniform(-0.0018, 0.0018)
        py = rng.uniform(-0.0015, 0.0015)
        pz = rng.uniform(-0.0012, 0.0012)
        insert_xyz(cam, "location", f, (px, py, pz))
        rx = math.radians(rng.uniform(-0.08, 0.08))
        ry = math.radians(rng.uniform(-0.10, 0.10))
        rz = math.radians(rng.uniform(-0.07, 0.07))
        insert_xyz(cam, "rotation_euler", f, (rx, ry, rz))
        t += dt
    add_noise_mods(cam, "location", 7.5, 0.0016, 2.0)
    add_noise_mods(cam, "rotation_euler", 11.0, 0.0011, 5.0)


def animate_exposure(scene: bpy.types.Scene) -> None:
    t = 0.0
    while t <= DURATION + 1e-6:
        scene.view_settings.exposure = exposure_at(t)
        scene.view_settings.keyframe_insert(data_path="exposure", frame=frame_at(t))
        t += 0.20
    for fc in iter_fcurves(scene):
        if "exposure" not in fc.data_path:
            continue
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.handle_left_type = "AUTO_CLAMPED"
            kp.handle_right_type = "AUTO_CLAMPED"


def add_path_guide(col: bpy.types.Collection) -> None:
    curve = bpy.data.curves.new("CAM_PATH_GUIDE", "CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("POLY")
    spline.points.add(len(ROOT_KEYS) - 1)
    for i, (_t, x, y, _yaw) in enumerate(ROOT_KEYS):
        spline.points[i].co = (x, y, CAM_Z, 1.0)
    obj = bpy.data.objects.new("CAM_PATH_GUIDE", curve)
    obj.hide_render = True
    col.objects.link(obj)


def setup_scene(scene: bpy.types.Scene) -> None:
    scene.frame_start = 1
    scene.frame_end = frame_at(DURATION)
    scene.frame_step = 1
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    scene.render.resolution_percentage = 100
    scene.render.use_motion_blur = True
    try:
        scene.render.motion_blur_position = "CENTER"
    except TypeError:
        pass
    scene.render.motion_blur_shutter = 0.42
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    scene.view_settings.look = "None"


def _set_in(node, name, value) -> None:
    if name in node.inputs:
        node.inputs[name].default_value = value


def setup_vhs_compositor(scene: bpy.types.Scene) -> None:
    ng = bpy.data.node_groups.get("VHS_FOUND_FOOTAGE")
    if ng is None:
        ng = bpy.data.node_groups.new("VHS_FOUND_FOOTAGE", "CompositorNodeTree")
    ng.nodes.clear()
    ng.interface.clear()
    ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")

    rl = ng.nodes.new("CompositorNodeRLayers")
    rl.location = (0, 80)

    lens = ng.nodes.new("CompositorNodeLensdist")
    lens.location = (200, 80)
    try:
        _set_in(lens, "Type", "Horizontal")
    except TypeError:
        _set_in(lens, "Type", "Radial")
    try:
        _set_in(lens, "Fit", True)
    except Exception:
        pass

    scale_dn = ng.nodes.new("CompositorNodeScale")
    scale_dn.location = (400, 80)
    _set_in(scale_dn, "Type", "Relative")
    _set_in(scale_dn, "X", 0.56)
    _set_in(scale_dn, "Y", 0.56)

    sep = ng.nodes.new("CompositorNodeSeparateColor")
    sep.mode = "YCC"
    sep.ycc_mode = "ITUBT601"
    sep.location = (600, 140)

    blur_c = ng.nodes.new("CompositorNodeBlur")
    blur_c.location = (800, 40)
    _set_in(blur_c, "Type", "Fast Gaussian")
    if "Size" in blur_c.inputs:
        blur_c.inputs["Size"].default_value = (2.4, 0.7)

    comb = ng.nodes.new("CompositorNodeCombineColor")
    if hasattr(comb, "mode"):
        comb.mode = "YCC"
    if hasattr(comb, "ycc_mode"):
        comb.ycc_mode = "ITUBT601"
    comb.location = (1000, 140)

    scale_up = ng.nodes.new("CompositorNodeScale")
    scale_up.location = (1200, 80)
    _set_in(scale_up, "Type", "Relative")
    _set_in(scale_up, "X", 1.78)
    _set_in(scale_up, "Y", 1.78)

    glare = ng.nodes.new("CompositorNodeGlare")
    glare.location = (1400, 160)
    _set_in(glare, "Type", "Fog Glow")
    _set_in(glare, "Quality", "Medium")
    _set_in(glare, "Threshold", 0.92)
    _set_in(glare, "Size", 0.45)
    _set_in(glare, "Strength", 0.55)

    bc = ng.nodes.new("CompositorNodeBrightContrast")
    bc.location = (1600, 80)
    _set_in(bc, "Brightness", -0.035)
    _set_in(bc, "Contrast", 0.08)

    rgb = ng.nodes.new("CompositorNodeRGB")
    rgb.location = (1600, -80)
    rgb.outputs[0].default_value = (0.06, 0.055, 0.05, 1.0)

    mix_crush = ng.nodes.new("ShaderNodeMixRGB")
    mix_crush.blend_type = "DARKEN"
    mix_crush.location = (1800, 40)
    _set_in(mix_crush, "Factor", 0.11)

    hue = ng.nodes.new("CompositorNodeHueSat")
    hue.location = (2000, 40)
    _set_in(hue, "Saturation", 0.86)
    _set_in(hue, "Value", 1.02)

    coords = ng.nodes.new("CompositorNodeImageCoordinates")
    coords.location = (1800, -240)

    noise = ng.nodes.new("ShaderNodeTexNoise")
    noise.location = (2000, -240)
    noise.noise_dimensions = "4D"
    _set_in(noise, "Scale", 160.0)
    _set_in(noise, "Detail", 1.0)
    _set_in(noise, "Roughness", 0.35)

    mix_n = ng.nodes.new("ShaderNodeMixRGB")
    mix_n.blend_type = "OVERLAY"
    mix_n.location = (2200, 0)
    _set_in(mix_n, "Factor", 0.022)

    trans = ng.nodes.new("CompositorNodeTranslate")
    trans.location = (2400, 0)
    _set_in(trans, "X", 0.0)
    _set_in(trans, "Y", 0.0)

    out = ng.nodes.new("NodeGroupOutput")
    out.location = (2600, 0)

    links = ng.links
    links.new(rl.outputs["Image"], lens.inputs["Image"])
    links.new(lens.outputs["Image"], scale_dn.inputs["Image"])
    links.new(scale_dn.outputs["Image"], sep.inputs["Image"])
    links.new(sep.outputs["Red"], comb.inputs["Red"])
    # Horizontal chroma bleed: blur Cb/Cr only.
    cb_name = "Green" if "Green" in sep.outputs else "Green"
    cr_name = "Blue" if "Blue" in sep.outputs else "Blue"
    links.new(sep.outputs[cb_name], blur_c.inputs["Image"])
    links.new(blur_c.outputs["Image"], comb.inputs["Green"])
    # Slight extra horizontal smear on Cr via the same blur size.
    links.new(sep.outputs[cr_name], comb.inputs["Blue"])
    if "Alpha" in sep.outputs and "Alpha" in comb.inputs:
        links.new(sep.outputs["Alpha"], comb.inputs["Alpha"])
    links.new(comb.outputs["Image"], scale_up.inputs["Image"])
    links.new(scale_up.outputs["Image"], glare.inputs["Image"])
    links.new(glare.outputs["Image"], bc.inputs["Image"])
    links.new(bc.outputs["Image"], mix_crush.inputs["Color1"])
    links.new(rgb.outputs[0], mix_crush.inputs["Color2"])
    links.new(mix_crush.outputs["Color"], hue.inputs["Image"])
    links.new(hue.outputs["Image"], mix_n.inputs["Color1"])
    links.new(rl.outputs["Image"], coords.inputs["Image"])
    if "Normalized" in coords.outputs:
        links.new(coords.outputs["Normalized"], noise.inputs["Vector"])
    links.new(noise.outputs["Color"], mix_n.inputs["Color2"])
    links.new(mix_n.outputs["Color"], trans.inputs["Image"])
    links.new(trans.outputs["Image"], out.inputs["Image"])

    # Animated 4D noise W + tracking wobble.
    _set_in(noise, "W", 0.0)
    noise.inputs["W"].keyframe_insert("default_value", frame=1)
    _set_in(noise, "W", 6.5)
    noise.inputs["W"].keyframe_insert("default_value", frame=frame_at(DURATION))
    trans.inputs["X"].default_value = 0.0
    trans.inputs["X"].keyframe_insert("default_value", frame=1)
    trans.inputs["X"].default_value = 0.4
    trans.inputs["X"].keyframe_insert("default_value", frame=frame_at(DURATION))
    for fc in iter_fcurves(ng):
        if "Translate" in fc.data_path and "inputs[1]" in fc.data_path:
            for mod in list(fc.modifiers):
                if mod.type == "NOISE":
                    fc.modifiers.remove(mod)
            mod = fc.modifiers.new("NOISE")
            mod.scale = 18.0
            mod.strength = 0.85
            mod.depth = 1
        if "TexNoise" in fc.data_path or "Noise" in fc.data_path:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

    scene.compositing_node_group = ng
    scene.render.use_compositing = True


def collision_report() -> list[str]:
    dg = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    cam = bpy.data.objects["Camera"]
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
    for f in range(scene.frame_start, scene.frame_end + 1, 2):
        scene.frame_set(f)
        dg.update()
        p = cam.matrix_world.translation.copy()
        if p.z < 1.45 or p.z > 1.85:
            problems.append(f"f{f} height {p.z:.3f}")
        for d in dirs:
            hit, loc, *_r = scene.ray_cast(dg, p, d)
            if hit and (loc - p).length < COLLISION_R:
                problems.append(
                    f"f{f} clip {(loc - p).length:.3f} at {tuple(round(x, 2) for x in loc)}"
                )
                break
    return problems


def look_vector() -> Vector:
    cam = bpy.data.objects["Camera"]
    return (cam.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()


def print_sanity() -> None:
    scene = bpy.context.scene
    labels = (
        (0.0, "start"),
        (5.0, "enter Main"),
        (9.2, "stub"),
        (9.85, "eyes lead"),
        (10.40, "body turn"),
        (13.5, "Hall B"),
        (17.2, "stop glance"),
        (18.50, "pre snap"),
        (18.95, "snap"),
        (19.35, "correct"),
        (25.5, "cut"),
    )
    for t, label in labels:
        scene.frame_set(frame_at(t))
        bpy.context.evaluated_depsgraph_get().update()
        cam = bpy.data.objects["Camera"]
        p = cam.matrix_world.translation
        v = look_vector()
        heading = math.degrees(math.atan2(-v.x, v.y))
        hit, loc, *_r = scene.ray_cast(bpy.context.evaluated_depsgraph_get(), p, v)
        dist = (loc - p).length if hit else 99.0
        print(
            f"  t={t:5.2f} {label:12s} pos=({p.x:6.2f},{p.y:6.2f},{p.z:5.2f}) "
            f"look=({v.x:5.2f},{v.y:5.2f},{v.z:5.2f}) yaw={heading:6.1f} hit={dist:4.2f}m"
        )


def encode_mp4(frame_dir: Path, pattern: str, out_path: Path, fps: float = FPS, glob: bool = False) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-framerate", str(fps)]
    if glob:
        cmd += ["-pattern_type", "glob", "-i", str(frame_dir / pattern)]
    else:
        cmd += ["-i", str(frame_dir / pattern)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out_path)]
    subprocess.check_call(cmd)
    return out_path


def configure_preview(scene: bpy.types.Scene) -> Path:
    frames = PREVIEW_DIR / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    scene.render.use_motion_blur = False
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    scene.render.filepath = str(frames / "frame_")
    scene.render.use_compositing = False
    scene.frame_step = 1
    return frames


def configure_stills(scene: bpy.types.Scene) -> None:
    STILLS_DIR.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 960
    scene.render.use_motion_blur = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_compositing = False
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    scene.frame_step = 1
    scene.render.threads = 4


def configure_master(scene: bpy.types.Scene) -> Path:
    frames = MASTER_DIR / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 12
    scene.cycles.use_denoising = False
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 960
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.42
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(frames / "frame_")
    scene.render.use_compositing = False
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    return frames


def configure_vhs_video(scene: bpy.types.Scene) -> Path:
    frames = VHS_DIR / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.42
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    scene.render.filepath = str(frames / "frame_")
    scene.render.use_compositing = True
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    scene.frame_step = 2
    return frames


def main() -> None:
    args = parse_args()
    scene = bpy.context.scene
    clear_old_rig()
    col = collection()
    root, body, look, cam = build_rig(col)
    animate_root(root)
    animate_look(look)
    animate_body(body)
    animate_hand_jitter(cam)
    animate_exposure(scene)
    add_path_guide(col)
    setup_scene(scene)
    try:
        setup_vhs_compositor(scene)
        print("VHS compositor attached")
    except Exception as exc:
        print("VHS compositor failed:", type(exc).__name__, exc)

    print("Sanity poses:")
    print_sanity()
    problems = collision_report()
    print("Collision hits", len(problems))
    for line in problems[:16]:
        print(" ", line)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH, "frames", scene.frame_start, scene.frame_end)

    if args["mode"] == "check":
        return
    if args["mode"] == "preview":
        frames = configure_preview(scene)
        print("Preview render ->", frames)
        bpy.ops.render.render(animation=True)
        out = encode_mp4(frames, "frame_%04d.jpg", PREVIEW_DIR / "found_footage_preview.mp4")
        print("Wrote", out)
        return
    if args["mode"] == "stills":
        configure_stills(scene)
        scene.render.use_compositing = False  # CGI master stills, VHS is a separate pass
        for t in (0.5, 5.0, 9.85, 13.5, 18.5, 25.4):
            scene.frame_set(frame_at(t))
            scene.render.filepath = str(STILLS_DIR / f"ff_{t:.1f}s.png")
            bpy.ops.render.render(write_still=True)
            print("still", scene.render.filepath)
        return
    if args["mode"] == "master":
        frames = configure_master(scene)
        print("Master render ->", frames)
        bpy.ops.render.render(animation=True)
        out = encode_mp4(frames, "frame_%04d.png", MASTER_DIR / "found_footage_master.mp4")
        print("Wrote", out)
        return
    if args["mode"] == "vhs":
        frames = configure_vhs_video(scene)
        print("VHS render ->", frames)
        bpy.ops.render.render(animation=True)
        out = encode_mp4(
            frames,
            "frame_*.jpg",
            VHS_DIR / "found_footage_vhs.mp4",
            fps=15,
            glob=True,
        )
        print("Wrote", out)


if __name__ == "__main__":
    main()
