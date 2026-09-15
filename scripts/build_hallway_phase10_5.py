#!/usr/bin/env python3
"""Phase 10.5 — endless corridor continuation + 9s first-person walk preview.

TWO GOALS ONLY:
  1. Continue the existing corridor far enough that no endpoint is perceived.
  2. Produce a 9-second first-person forward walking video of the completed
     Hero section (Zones A/B/C), looking into that continuation.

This is a MOTION / CAMERA / ENDLESSNESS PREVIEW.
It is NOT a material rebuild, look-dev pass, or final cinematic render.

Do not redesign shaders, replace materials, grade color, or add procedural
texture.  Hero 0–24 m stays frozen.  Extension objects are additive, named
P105_*, and live in CORRIDOR_EXTENSION* collections.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase10_5.py -- --no-render
  blender -b hallway.blend --python scripts/build_hallway_phase10_5.py -- --stills
  blender -b hallway.blend --python scripts/build_hallway_phase10_5.py -- --video
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_hallway_phase3 as p3
import build_hallway_phase5 as p5
import build_hallway_phase8 as p8
import build_hallway_phase9 as p9

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase10_5"
ARTIFACT_DIR = Path("/opt/cursor/artifacts")

HERO_END = 24.0
EXT_LEN = 72.0
EXT_END = HERO_END + EXT_LEN  # 96 m
MODULE = 7.30  # Zone C length, used to continue fixture rhythm
EYE_Z = p5.EYE_Z
ZONE_A = p5.ZONE_A
ZONE_B = p5.ZONE_B
ZONE_C = p5.ZONE_C
PHASE2_COUNTS = p5.PHASE2_COUNTS
PHASE4_COLLECTIONS = p5.PHASE4_COLLECTIONS
LIBRARY = p5.LIBRARY
P8_PREFIXES = p8.P8_PREFIXES
P9_PREFIXES = p9.P9_PREFIXES
EXPECTED_P8 = 209
EXPECTED_P9 = 11
EXPECTED_MARKS = 5

FPS = 24
DURATION_S = 9.0
FRAME_END = int(FPS * DURATION_S)  # 216
WALK_Y0 = 1.40
WALK_Y1 = 14.00  # 12.6 m in 9 s ≈ 1.4 m/s
LOOK_AHEAD = 12.0
PITCH_DEG = 1.2
LENS_MM = 32.0
CLIP_END = 130.0
VOLUMETRIC_END = 120.0
PLAYBLAST_SAMPLES = 10
STILL_SAMPLES = 16
HERO_SAMPLES = 48

# Zone C fixture offsets relative to zone start (16.70).
C_LIGHT_OFFSETS = (
    ("LIGHT_C_01_WEAK", 0.52),
    ("LIGHT_C_02_OFF", 1.84),
    ("LIGHT_C_03_NORMAL", 3.20),
    ("LIGHT_C_04_WEAK", 5.02),
)
C_BEAM_OFFSETS = (1.15, 3.85, 6.25)
C_SUPPORT_LEFT = ("SUPPORT_Wall_Left_C_17_95", "SUPPORT_Wall_Left_C_21_20")
C_SUPPORT_RIGHT = (
    "SUPPORT_Wall_Right_C_19_45",
    "SUPPORT_Wall_Right_C_21_20",
    "SUPPORT_Wall_Right_C_23_10",
)

P105_PREFIX = "P105_"
CAM_WALK = "CAM_P105_WALK"
CAM_TARGET = "CAM_P105_WALK.Target"
COL_EXT = "CORRIDOR_EXTENSION"
COL_LIGHTS = "CORRIDOR_EXTENSION_LIGHTS"
COL_CAM = "CORRIDOR_EXTENSION_CAMERAS"

HERO_LIGHT_NAMES = (
    "LIGHT_A_01_NORMAL",
    "LIGHT_A_02_NORMAL",
    "LIGHT_A_03_NORMAL",
    "LIGHT_A_04_AGED_TINT",
    "LIGHT_A_WALL_01_NORMAL",
    "LIGHT_B_01_NORMAL",
    "LIGHT_B_02_WEAK",
    "LIGHT_B_03_OFF",
    "LIGHT_B_04_WEAK",
    "LIGHT_B_WALL_01_WEAK",
    "LIGHT_C_01_WEAK",
    "LIGHT_C_02_OFF",
    "LIGHT_C_03_NORMAL",
    "LIGHT_C_04_WEAK",
    "LIGHT_C_WALL_01_OFF",
)


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--no-render" in argv:
        return "check"
    if "--stills" in argv:
        return "stills"
    if "--video" in argv:
        return "video"
    return "check"


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def is_extension(name: str) -> bool:
    return name.startswith(P105_PREFIX) or name.startswith("CAM_P105")


def is_core(name: str) -> bool:
    if is_extension(name):
        return False
    if name.startswith(P8_PREFIXES) or name.startswith(P9_PREFIXES):
        return False
    if name.startswith(("FIX_", "LIGHT_A_", "LIGHT_B_", "LIGHT_C_", "P7_", "CAM_P10_")):
        return False
    return True


def material_fingerprint() -> dict[str, tuple]:
    rows = {}
    for mat in bpy.data.materials:
        if mat.node_tree is None:
            continue
        nodes = tuple(sorted(n.bl_idname for n in mat.node_tree.nodes))
        rows[mat.name] = (len(mat.node_tree.nodes), nodes)
    return rows


def light_energy_map() -> dict[str, tuple]:
    rows = {}
    for name in HERO_LIGHT_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "LIGHT":
            continue
        data = obj.data
        rows[name] = (
            round(data.energy, 5),
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
        )
    return rows


def inspect_keys(camera: bpy.types.Object) -> list[tuple[int, float]]:
    ad = camera.animation_data
    if ad is None or ad.action is None:
        return []
    action = ad.action
    bags = []
    for layer in action.layers:
        for strip in layer.strips:
            bags.extend(list(strip.channelbags))
    keys = []
    for bag in bags:
        for fc in bag.fcurves:
            if fc.data_path == "location" and fc.array_index == 1:
                keys = [(int(kp.co.x), round(kp.co.y, 3)) for kp in fc.keyframe_points]
    return keys


def set_linear(obj: bpy.types.Object) -> None:
    ad = obj.animation_data
    if ad is None or ad.action is None:
        return
    for layer in ad.action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"


def add_box(name, x0, y0, z0, x1, y1, z1, col, mat) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    sx, sy, sz = abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=(sx, sy, sz))
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = ((x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5)
    col.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    obj["phase"] = 10.5
    return obj


def duplicate_offset(
    src: bpy.types.Object,
    name: str,
    dy: float,
    col: bpy.types.Collection,
    copy_data: bool = False,
) -> bpy.types.Object:
    obj = src.copy()
    if copy_data and src.data is not None:
        obj.data = src.data.copy()
        obj.data.name = f"{name}_DATA"
    obj.name = name
    obj.location = src.location.copy()
    obj.location.y += dy
    for existing in list(obj.users_collection):
        existing.objects.unlink(obj)
    col.objects.link(obj)
    obj["phase"] = 10.5
    obj["source"] = src.name
    return obj


def related_fixture_objects(light_name: str) -> list[bpy.types.Object]:
    found = []
    for obj in bpy.data.objects:
        if is_extension(obj.name):
            continue
        if obj.name == light_name or light_name in obj.name:
            found.append(obj)
    return found


def clear_phase105() -> None:
    for obj in list(bpy.data.objects):
        if is_extension(obj.name):
            bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        if col.name.startswith("CORRIDOR_EXTENSION"):
            bpy.data.collections.remove(col)
    end = bpy.data.objects.get("WALL.End")
    if end is not None:
        end.hide_render = False
        if hasattr(end, "visible_camera"):
            end.visible_camera = True
    for block in (bpy.data.meshes, bpy.data.curves, bpy.data.lights, bpy.data.cameras):
        for item in list(block):
            if item.name.startswith("P105_") and item.users == 0:
                block.remove(item)


def hide_hero_endcap() -> None:
    """Keep WALL.End in the file (editable) but out of the render."""
    end = bpy.data.objects.get("WALL.End")
    if end is None:
        raise RuntimeError("WALL.End missing")
    end.hide_render = True
    if hasattr(end, "visible_camera"):
        end.visible_camera = False


def build_shell(col: bpy.types.Collection) -> None:
    wall = bpy.data.materials["MAT_Wall_PaintedConcrete"]
    floor = bpy.data.materials["MAT_Floor_IndustrialConcrete"]
    ceil = bpy.data.materials["MAT_Ceiling_AgedConcrete"]
    xa = ZONE_A["width"] * 0.5
    xc = ZONE_C["width"] * 0.5
    outer = xa + 0.20
    y0, y1 = HERO_END, EXT_END
    add_box(f"{P105_PREFIX}FLOOR", -outer, y0, -0.20, outer, y1, 0.0, col, floor)
    add_box(
        f"{P105_PREFIX}WALL.West.Shell",
        -outer, y0, 0.0, -xa, y1, ZONE_A["height"] + 0.05, col, wall,
    )
    add_box(
        f"{P105_PREFIX}WALL.East.Shell",
        xa, y0, 0.0, outer, y1, ZONE_A["height"] + 0.05, col, wall,
    )
    add_box(
        f"{P105_PREFIX}CEIL.Shell",
        -outer, y0, ZONE_A["height"], outer, y1, ZONE_A["height"] + 0.20, col, ceil,
    )
    add_box(
        f"{P105_PREFIX}CEIL.SoffitC",
        -xc, y0, ZONE_C["height"], xc, y1, ZONE_A["height"], col, ceil,
    )
    # Far cap, well beyond fog/perspective from the hero walk.
    add_box(
        f"{P105_PREFIX}WALL.Far",
        -outer, y1, 0.0, outer, y1 + 0.20, ZONE_A["height"] + 0.05, col, wall,
    )


def build_repeating_structure(col: bpy.types.Collection) -> int:
    beam_src = bpy.data.objects.get("BEAM_Ceiling_C_01")
    count = 0
    module_count = int(round(EXT_LEN / MODULE))
    for index in range(module_count):
        y0 = HERO_END + index * MODULE
        if beam_src is not None:
            for bi, offset in enumerate(C_BEAM_OFFSETS):
                y = y0 + offset
                if y >= EXT_END - 0.4:
                    continue
                dy = y - beam_src.location.y
                duplicate_offset(
                    beam_src,
                    f"{P105_PREFIX}BEAM_C_{index:02d}_{bi:02d}",
                    dy,
                    col,
                    copy_data=False,
                )
                count += 1
        for src_name in C_SUPPORT_LEFT + C_SUPPORT_RIGHT:
            src = bpy.data.objects.get(src_name)
            if src is None:
                continue
            # Supports were authored relative to Zone C start 16.70.
            local = src.location.y - ZONE_C["y0"]
            y = y0 + local
            if y >= EXT_END - 0.3:
                continue
            duplicate_offset(
                src,
                f"{P105_PREFIX}{src_name}_M{index:02d}",
                y - src.location.y,
                col,
                copy_data=False,
            )
            count += 1
    return count


def build_pipes(col: bpy.types.Collection) -> None:
    primary = bpy.data.materials["MAT_Pipe_DarkPaintedSteel"]
    secondary = bpy.data.materials["MAT_Pipe_Secondary"]
    p3.add_straight_pipe(
        f"{P105_PREFIX}PIPE_Primary_C_Continue",
        (-0.36, 23.45, 2.46),
        (-0.36, EXT_END - 0.55, 2.46),
        0.26,
        col,
        primary,
        "EXT",
    )
    p3.add_straight_pipe(
        f"{P105_PREFIX}PIPE_Secondary_Right_C_Continue",
        (0.84, 23.20, 2.54),
        (0.84, EXT_END - 0.80, 2.54),
        0.09,
        col,
        secondary,
        "EXT",
    )
    p3.add_straight_pipe(
        f"{P105_PREFIX}PIPE_Secondary_Left_C_Continue",
        (-0.84, 24.10, 2.20),
        (-0.84, EXT_END - 0.80, 2.20),
        0.06,
        col,
        secondary,
        "EXT",
    )
    for obj in col.objects:
        if obj.name.startswith(P105_PREFIX) and obj.type == "CURVE":
            obj["phase"] = 10.5


def build_fixtures(col: bpy.types.Collection) -> int:
    count = 0
    module_count = int(round(EXT_LEN / MODULE))
    for index in range(module_count):
        y0 = HERO_END + index * MODULE
        for src_name, offset in C_LIGHT_OFFSETS:
            src = bpy.data.objects.get(src_name)
            if src is None:
                continue
            y = y0 + offset
            if y >= EXT_END - 0.6:
                continue
            dy = y - src.location.y
            tag = f"M{index:02d}"
            for related in related_fixture_objects(src_name):
                copy_data = related.type == "LIGHT"
                duplicate_offset(
                    related,
                    f"{P105_PREFIX}{related.name}_{tag}",
                    dy,
                    col,
                    copy_data=copy_data,
                )
                count += 1
    return count


def build_walk_camera(col: bpy.types.Collection) -> tuple[bpy.types.Object, bpy.types.Object]:
    existing = bpy.data.objects.get(CAM_WALK)
    if existing is not None:
        bpy.data.objects.remove(existing, do_unlink=True)
    existing_t = bpy.data.objects.get(CAM_TARGET)
    if existing_t is not None:
        bpy.data.objects.remove(existing_t, do_unlink=True)

    data = bpy.data.cameras.new(CAM_WALK)
    data.lens = LENS_MM
    data.sensor_width = 36.0
    data.sensor_fit = "HORIZONTAL"
    data.clip_start = 0.08
    data.clip_end = CLIP_END
    cam = bpy.data.objects.new(CAM_WALK, data)
    col.objects.link(cam)
    cam["phase"] = 10.5

    target = bpy.data.objects.new(CAM_TARGET, None)
    target.empty_display_type = "PLAIN_AXES"
    target.empty_display_size = 0.15
    target.hide_render = True
    col.objects.link(target)
    target["phase"] = 10.5

    con = cam.constraints.new("TRACK_TO")
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    if cam.animation_data:
        cam.animation_data_clear()
    if target.animation_data:
        target.animation_data_clear()

    def place(y: float) -> None:
        cam.location = (0.0, y, EYE_Z)
        ty = y + LOOK_AHEAD
        tz = EYE_Z - math.tan(math.radians(PITCH_DEG)) * LOOK_AHEAD
        target.location = (0.0, ty, tz)

    place(WALK_Y0)
    cam.keyframe_insert("location", frame=1)
    target.keyframe_insert("location", frame=1)
    place(WALK_Y1)
    cam.keyframe_insert("location", frame=FRAME_END)
    target.keyframe_insert("location", frame=FRAME_END)
    set_linear(cam)
    set_linear(target)

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.frame_set(1)
    place(WALK_Y0)
    scene.camera = cam
    return cam, target


def extend_atmosphere(scene: bpy.types.Scene) -> None:
    """Longer volume range so the continuation recedes; density unchanged."""
    scene.eevee.volumetric_end = VOLUMETRIC_END
    inspect = bpy.data.objects.get("CAM_INSPECT")
    if inspect is not None and inspect.type == "CAMERA":
        # Leave inspect clip as authored; only the preview camera sees 96 m.
        pass


def configure_preview_eevee(scene: bpy.types.Scene, samples: int) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    scene.eevee.taa_render_samples = samples
    scene.eevee.use_raytracing = False
    scene.eevee.volumetric_end = VOLUMETRIC_END


def restore_hero_eevee(scene: bpy.types.Scene) -> None:
    scene.eevee.taa_render_samples = HERO_SAMPLES
    scene.eevee.use_raytracing = False
    scene.eevee.volumetric_end = VOLUMETRIC_END
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720


def ray_ignore_end(scene, origin, direction) -> float | None:
    end = bpy.data.objects.get("WALL.End")
    hidden = end.hide_get() if end is not None else False
    if end is not None:
        end.hide_set(True)
    bpy.context.view_layer.update()
    hit = p5.ray(scene, origin, direction)
    if end is not None:
        end.hide_set(hidden)
    bpy.context.view_layer.update()
    return hit


def validate(scene, before, lights_before, mats_before, inspect_before) -> dict:
    after = p5.snapshot()
    original = {k: v for k, v in before.items() if is_core(k)}
    after_core = {k: v for k, v in after.items() if is_core(k)}
    moved = [name for name, row in original.items() if after_core.get(name) != row]
    removed = sorted(set(original) - set(after_core))
    added_core = sorted(name for name in (set(after_core) - set(original)) if not is_extension(name))
    lights_after = light_energy_map()
    light_changed = [name for name, row in lights_before.items() if lights_after.get(name) != row]
    mats_after = material_fingerprint()
    mat_changed = [name for name, row in mats_before.items() if mats_after.get(name) != row]
    inspect = bpy.data.objects["CAM_INSPECT"]
    inspect_after = inspect_keys(inspect)
    camera_errors = []
    scene.frame_set(1)
    for frame in range(1, 251, 8):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        position = inspect.matrix_world.translation.copy()
        if abs(position.x) > 0.01 or abs(position.z - EYE_Z) > 0.01:
            camera_errors.append((frame, tuple(round(v, 3) for v in position)))
    hide_list = [
        obj
        for obj in bpy.data.objects
        if obj.name.startswith(P8_PREFIXES)
        or obj.name.startswith(P9_PREFIXES)
        or obj.name.startswith("MARK_")
        or obj.name.startswith("FIX_")
        or obj.name.startswith("CAM_P10_")
        or (obj.users_collection and any(c.name.startswith("POLISH_") for c in obj.users_collection))
        or (obj.users_collection and any(c.name in PHASE4_COLLECTIONS for c in obj.users_collection))
        or (obj.users_collection and any(c.name == "STORY_SIGNAGE" for c in obj.users_collection))
    ]
    hidden = {obj.name: obj.hide_get() for obj in hide_list}
    for obj in hide_list:
        obj.hide_set(True)
    bpy.context.view_layer.update()
    stations = []
    for label, y, width, height in (
        ("A clear", 3.25, ZONE_A["width"], ZONE_A["height"]),
        ("B clear", 11.75, ZONE_B["width"], ZONE_B["height"]),
        ("C clear", 21.55, ZONE_C["width"], ZONE_C["height"]),
    ):
        origin = Vector((0.0, y, EYE_Z))
        left = p5.ray(scene, origin, Vector((-1.0, 0.0, 0.0)))
        right = p5.ray(scene, origin, Vector((1.0, 0.0, 0.0)))
        up = p5.ray(scene, origin, Vector((0.0, 0.0, 1.0)))
        stations.append(
            dict(
                label=label,
                y=y,
                width=(left + right) if left is not None and right is not None else 0.0,
                ceiling=(up + EYE_Z) if up is not None else 0.0,
                target_width=width,
                target_ceiling=height,
            )
        )
    for obj in hide_list:
        obj.hide_set(hidden.get(obj.name, False))
    bpy.context.view_layer.update()

    walk = bpy.data.objects[CAM_WALK]
    scene.frame_set(1)
    bpy.context.view_layer.update()
    start = tuple(round(v, 3) for v in walk.matrix_world.translation)
    scene.frame_set(FRAME_END)
    bpy.context.view_layer.update()
    end = tuple(round(v, 3) for v in walk.matrix_world.translation)
    scene.frame_set(1)

    forward_hits = []
    for y in (WALK_Y0, 8.0, WALK_Y1, 18.0):
        origin = Vector((0.0, y, EYE_Z))
        dist = ray_ignore_end(scene, origin, Vector((0.0, 1.0, 0.0)))
        forward_hits.append((y, dist))

    vol = None
    if scene.world and scene.world.node_tree:
        node = scene.world.node_tree.nodes.get("P10_Volume")
        if node:
            vol = node.inputs["Density"].default_value
    bg = scene.world.node_tree.nodes.get("Background") if scene.world and scene.world.node_tree else None
    ext_count = len([o for o in bpy.data.objects if is_extension(o.name)])
    return dict(
        moved=moved,
        removed=removed,
        added_core=added_core,
        light_changed=light_changed,
        mat_changed=mat_changed,
        camera_errors=camera_errors,
        inspect_keys_before=inspect_before,
        inspect_keys_after=inspect_after,
        stations=stations,
        walk_start=start,
        walk_end=end,
        forward_hits=forward_hits,
        wall_end_hidden=bool(bpy.data.objects["WALL.End"].hide_render),
        volumetric_end=scene.eevee.volumetric_end,
        volume_density=vol if vol is not None else -1.0,
        world_strength=bg.inputs[1].default_value if bg else -1.0,
        phase2_counts={
            name: len(bpy.data.collections[name].objects) if bpy.data.collections.get(name) else -1
            for name in PHASE2_COUNTS
        },
        phase3_present=all(
            bpy.data.collections.get(n)
            for n in ("UTILITY_PRIMARY_PIPES", "UTILITY_SECONDARY_PIPES", "UTILITY_SUPPORTS")
        ),
        phase4_present=all(bpy.data.collections.get(n) for n in PHASE4_COLLECTIONS),
        library_ok=all(bpy.data.materials.get(name) for name in LIBRARY),
        aging_ok=bpy.data.node_groups.get("P6_NG_AgingMasks") is not None,
        markings=len([o for o in bpy.data.objects if o.name.startswith("MARK_")]),
        p8_count=len([o for o in bpy.data.objects if o.name.startswith("P8_")]),
        p9_count=len([o for o in bpy.data.objects if o.name.startswith("P9_")]),
        ext_count=ext_count,
        hero_cams=all(bpy.data.objects.get(n) for n in ("CAM_HERO_A", "CAM_HERO_B", "CAM_HERO_C")),
        inspect_exists=bpy.data.objects.get("CAM_INSPECT") is not None,
        walk_exists=bpy.data.objects.get(CAM_WALK) is not None,
        frame_end=scene.frame_end,
        fps=scene.render.fps,
        off_still_off=all(
            bpy.data.objects[n].data.energy == 0.0
            for n in ("LIGHT_B_03_OFF", "LIGHT_C_02_OFF", "LIGHT_C_WALL_01_OFF")
            if bpy.data.objects.get(n)
        ),
    )


def write_report(validation: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    phase1_pass = (
        all(
            abs(row["width"] - row["target_width"]) < 0.001
            and abs(row["ceiling"] - row["target_ceiling"]) < 0.001
            for row in validation["stations"]
        )
        and not validation["moved"]
        and not validation["removed"]
    )
    phase2_pass = validation["phase2_counts"] == PHASE2_COUNTS and not validation["moved"]
    phase3_pass = validation["phase3_present"] and not validation["moved"]
    phase4_pass = validation["phase4_present"] and not validation["moved"]
    phase5_pass = validation["library_ok"] and not validation["moved"] and not validation["mat_changed"]
    phase6_pass = validation["aging_ok"] and validation["markings"] == EXPECTED_MARKS and not validation["moved"]
    phase7_pass = not validation["light_changed"] and validation["off_still_off"]
    phase8_pass = validation["p8_count"] == EXPECTED_P8 and validation["hero_cams"] and not validation["moved"]
    phase9_pass = validation["p9_count"] == EXPECTED_P9 and validation["markings"] == EXPECTED_MARKS
    inspect_ok = validation["inspect_keys_before"] == validation["inspect_keys_after"]
    min_forward = min((d if d is not None else 0.0) for _, d in validation["forward_hits"])
    endless_ok = validation["wall_end_hidden"] and min_forward > 50.0
    walk_ok = (
        validation["walk_exists"]
        and abs(validation["walk_start"][1] - WALK_Y0) < 0.02
        and abs(validation["walk_end"][1] - WALK_Y1) < 0.02
        and abs(validation["walk_start"][2] - EYE_Z) < 0.02
        and abs(validation["walk_end"][2] - EYE_Z) < 0.02
        and validation["frame_end"] == FRAME_END
        and validation["fps"] == FPS
    )
    density_ok = abs(validation["volume_density"] - 0.0036) < 1e-6
    phase105_pass = (
        phase1_pass
        and phase2_pass
        and phase3_pass
        and phase4_pass
        and phase5_pass
        and phase6_pass
        and phase7_pass
        and phase8_pass
        and phase9_pass
        and inspect_ok
        and not validation["camera_errors"]
        and not validation["added_core"]
        and endless_ok
        and walk_ok
        and density_ok
    )
    lines = [
        "PHASE 10.5 無盡走廊延續 + 9 秒第一人稱行走預覽",
        "這是 MOTION / CAMERA / ENDLESSNESS PREVIEW，不是最終電影級畫面。",
        "未重建材質、未改 shader、未做飽和／調色、未加程序紋理。",
        "Hero 0–24 m 凍結。延續段為可編輯的 P105_* 附加物件。",
        "",
        "GOAL 1  CORRIDOR CONTINUATION",
        f"  Hero 端牆 WALL.End 仍在檔案中（y=24.1），hide_render={validation['wall_end_hidden']}。",
        f"  附加殼體 / 管 / 燈從 y=24 延到 y={EXT_END:.0f}（+{EXT_LEN:.0f} m）。",
        "  使用既有 MAT_* 指定，無新 shader。燈具為 C 段 linked duplicate。",
        "  未 bake / flatten / merge。",
        f"  延續物件數：{validation['ext_count']}",
        "  前方 +Y 射線（暫時隱藏 WALL.End 以免 viewport ray 打到它）：",
    ]
    for y, dist in validation["forward_hits"]:
        lines.append(f"    y={y:5.2f}  hit={dist:.2f} m" if dist is not None else f"    y={y:5.2f}  hit=NONE")
    lines += [
        "",
        "GOAL 2  9s FIRST-PERSON WALK",
        f"  Camera {CAM_WALK}  lens {LENS_MM} mm, clip_end {CLIP_END:.0f} m。",
        f"  {FRAME_END} frames @ {FPS} fps = {DURATION_S:.0f} s。",
        f"  y {WALK_Y0:.2f} → {WALK_Y1:.2f} m（約 1.4 m/s），眼高 {EYE_Z:.2f} m，x=0。",
        f"  起點 {validation['walk_start']}  終點 {validation['walk_end']}",
        "  Track-To 看向走廊軸線。CAM_INSPECT 250 幀路徑未改。",
        "",
        "ATMOSPHERE",
        f"  Volume density {validation['volume_density']:.4f}（未改）。",
        f"  volumetric_end {validation['volumetric_end']:.1f} m（僅加長範圍以覆蓋延續段）。",
        f"  World strength {validation['world_strength']:.3f}。",
        "",
        "KNOWN LOOK WEAKNESSES (NOT ADDRESSED IN 10.5)",
        "  Materials remain preview-quality: relatively flat, grey, limited surface response.",
        "  Color richness, hero material rebuild, and look-dev are deferred.",
        "  Lighting/material interaction and final grading are deferred.",
        "  Playblast uses low EEVEE samples; do not treat it as the final render.",
        "",
        "PHASE 1 空間凍結量測點",
        "  標籤       y       實測寬度       實測天花高度       目標寬度       目標天花高度",
    ]
    for row in validation["stations"]:
        lines.append(
            f"  {row['label']:10s} {row['y']:5.2f}    {row['width']:.3f} m       "
            f"{row['ceiling']:.3f} m          {row['target_width']:.3f} m       "
            f"{row['target_ceiling']:.3f} m"
        )
    lines += [
        "",
        "凍結／驗證細節",
        f"  核心物件變換改動：{len(validation['moved'])}",
        f"  核心物件刪除：{len(validation['removed'])}；非延續新增：{len(validation['added_core'])}",
        f"  Hero 燈光能量／位置改動：{len(validation['light_changed'])}",
        f"  材質節點指紋改動：{len(validation['mat_changed'])}",
        f"  CAM_INSPECT 路徑錯誤：{len(validation['camera_errors'])}",
        f"  CAM_INSPECT keys unchanged: {inspect_ok}",
        "",
        "PHASE 1 空間凍結狀態： " + ("PASS" if phase1_pass else "FAIL"),
        "PHASE 2 結構凍結狀態： " + ("PASS" if phase2_pass else "FAIL"),
        "PHASE 3 管線凍結狀態： " + ("PASS" if phase3_pass else "FAIL"),
        "PHASE 4 設備凍結狀態： " + ("PASS" if phase4_pass else "FAIL"),
        "PHASE 5 材質凍結狀態： " + ("PASS" if phase5_pass else "FAIL"),
        "PHASE 6 老化凍結狀態： " + ("PASS" if phase6_pass else "FAIL"),
        "PHASE 7 照明佈局凍結狀態： " + ("PASS" if phase7_pass else "FAIL"),
        "PHASE 8 英雄打磨凍結狀態： " + ("PASS" if phase8_pass else "FAIL"),
        "PHASE 9 標誌凍結狀態： " + ("PASS" if phase9_pass else "FAIL"),
        "PHASE 10.5 無盡預覽驗證： " + ("PASS" if phase105_pass else "FAIL"),
        "  未開始 Hero Material Rebuild / Look Development。",
        "  未開始 Phase 11。",
    ]
    if validation["moved"]:
        lines.append("  被改動物件：" + ", ".join(validation["moved"][:20]))
    if validation["light_changed"]:
        lines.append("  燈光改動：" + ", ".join(validation["light_changed"][:12]))
    if validation["mat_changed"]:
        lines.append("  材質改動：" + ", ".join(validation["mat_changed"][:12]))
    if validation["added_core"]:
        lines.append("  非預期新增：" + ", ".join(validation["added_core"][:20]))
    report = OUTPUT_DIR / "phase10_5_endless_preview_validation.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", report)
    print("PHASE 10.5 VALIDATION", "PASS" if phase105_pass else "FAIL")
    print("forward", validation["forward_hits"])
    print("walk", validation["walk_start"], "->", validation["walk_end"])
    return report


def render_preview_stills(scene: bpy.types.Scene) -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    configure_preview_eevee(scene, STILL_SAMPLES)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 90
    scene.camera = bpy.data.objects[CAM_WALK]
    stills = (
        (1, "FRAME_001_entrance"),
        (108, "FRAME_108_mid_walk"),
        (FRAME_END, "FRAME_216_end_walk"),
    )
    paths = []
    for frame, label in stills:
        scene.frame_set(frame)
        path = OUTPUT_DIR / f"{label}.jpg"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print("still", label, "frame", frame)
        paths.append(path)
    return paths


def render_walk_video(scene: bpy.types.Scene) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = OUTPUT_DIR / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    configure_preview_eevee(scene, PLAYBLAST_SAMPLES)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    scene.camera = bpy.data.objects[CAM_WALK]
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.filepath = str(frames / "phase10_5_walk_")
    bpy.ops.render.render(animation=True)
    output = OUTPUT_DIR / "phase10_5_endless_walk.mp4"
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(frames / "phase10_5_walk_%04d.jpg"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            str(output),
        ]
    )
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact = ARTIFACT_DIR / "phase10_5_endless_walk.mp4"
    subprocess.check_call(["cp", "-f", str(output), str(artifact)])
    print("playblast", output)
    print("artifact", artifact)
    return output


def main() -> None:
    mode = parse_mode()
    scene = bpy.context.scene
    before = p5.snapshot()
    lights_before = light_energy_map()
    mats_before = material_fingerprint()
    inspect_before = inspect_keys(bpy.data.objects["CAM_INSPECT"])
    clear_phase105()
    col = collection(COL_EXT)
    lights = collection(COL_LIGHTS)
    cams = collection(COL_CAM)
    hide_hero_endcap()
    build_shell(col)
    build_repeating_structure(col)
    build_pipes(col)
    build_fixtures(lights)
    build_walk_camera(cams)
    extend_atmosphere(scene)
    validation = validate(scene, before, lights_before, mats_before, inspect_before)
    write_report(validation)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    if mode in {"stills", "video"}:
        render_preview_stills(scene)
        if mode == "video":
            render_walk_video(scene)
        restore_hero_eevee(scene)
        scene.camera = bpy.data.objects[CAM_WALK]
        scene.frame_set(1)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 10.5 complete; no material rebuild; Phase 11 not started.")


if __name__ == "__main__":
    main()
