#!/usr/bin/env python3
"""Phase 1 — Level 2 Environmental Foundation.

Source-of-Truth extension applied ON TOP of the frozen Phase 0 hallway.
This does not rebuild corridor layout, camera animation, door sequence, or
delete existing assets.  Re-running this script from the Phase 0 checkpoint
(or current hallway.blend) reproduces the Phase 1 layer.

Pipeline:
  phase1_pre_environment.blend  →  this script --setup  →  hallway.blend
  this script --render  →  phase1_environment_review.mp4 (image sequence + audio)

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase1_environment.py -- --setup
  blender -b hallway.blend --python scripts/build_hallway_phase1_environment.py -- --steam-fix
  blender -b hallway.blend --python scripts/build_hallway_phase1_environment.py -- --look-restore
  blender -b hallway.blend --python scripts/build_hallway_phase1_environment.py -- --stills
  blender -b hallway.blend --python scripts/build_hallway_phase1_environment.py -- --render
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_hallway_final_door_sequence as final_pass
import build_hallway_phase10_5 as p105
import build_hallway_phase10_6 as p106
import build_hallway_phase10_6b as p106b
import build_hallway_phase6 as p6
import build_hallway_reference_lookdev as ref

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
CHECKPOINT = ROOT / "renders" / "checkpoints" / "phase1_pre_environment.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase1_environment"
STILL_DIR = OUTPUT_DIR / "stills"
FRAME_DIR = OUTPUT_DIR / "frames"
ASSET_DIR = ROOT / "assets" / "hallway_phase1_environment"
ARTIFACT_DIR = Path("/opt/cursor/artifacts")
REPORT_PATH = OUTPUT_DIR / "phase1_environment_report.txt"
WALK_CAM = "CAM_P105_WALK"
WALK_TARGET = "CAM_P105_WALK.Target"
FPS = 24
RES_X, RES_Y = 768, 432
FRAME_START, FRAME_END = 1, 360

COL_ENV = "PHASE1_ENVIRONMENT"
COL_STEAM = "PHASE1_STEAM"
COL_AUDIO = "PHASE1_AUDIO"
COL_WET = "PHASE1_WETNESS"

# Steam sockets: local leak jets at real hardware. Aim points down/inward from the source
# so the volume grows along the leak instead of sitting as a mid-corridor oval.
STEAM_SOCKETS = (
    dict(
        name="STEAM_SOCKET_VALVE_B",
        kind="valve packing leak",
        source=(0.84, 14.62, 2.43),
        aim=(0.22, 14.50, 1.22),
        peak_density=12.5,
        keys=(36, 52, 78, 108),
        seed=0.17,
        sound="local_steam_hiss_a.wav",
        speaker="SPK_STEAM_VALVE_B",
    ),
    dict(
        name="STEAM_SOCKET_INGRESS_B",
        kind="wall penetration / damaged connection",
        source=(1.01, 15.09, 2.43),
        aim=(0.28, 15.16, 1.24),
        peak_density=11.8,
        keys=(150, 168, 198, 228),
        seed=0.61,
        sound="local_steam_hiss_b.wav",
        speaker="SPK_STEAM_INGRESS_B",
    ),
    dict(
        name="STEAM_SOCKET_ELBOW_C",
        kind="pressure release at elbow flange",
        source=(-0.84, 17.84, 2.46),
        aim=(-0.20, 17.70, 1.18),
        peak_density=13.4,
        keys=(240, 258, 300, 330),
        seed=1.04,
        sound="local_steam_hiss_c.wav",
        speaker="SPK_STEAM_ELBOW_C",
    ),
)

SPEAKERS = (
    dict(name="SPK_PIPE_RUMBLE", loc=(0.84, 14.62, 2.20), sound="local_pipe_rumble.wav", vol=0.55, dist=1.4, dmax=11.0),
    dict(name="SPK_VENT_HUM", loc=(-1.00, 12.05, 1.68), sound="local_vent_hum.wav", vol=0.42, dist=1.1, dmax=9.0),
    dict(name="SPK_ELECTRICAL", loc=(1.02, 10.70, 1.36), sound="local_electrical_hum.wav", vol=0.28, dist=1.0, dmax=8.0),
    dict(name="SPK_DRIP_A", loc=(-0.42, 17.90, 0.12), sound="local_water_drip.wav", vol=0.50, dist=0.9, dmax=7.5),
    dict(name="SPK_DRIP_B", loc=(0.55, 15.09, 0.10), sound="local_water_drip.wav", vol=0.32, dist=0.9, dmax=7.0),
    dict(name="SPK_METAL_TICK", loc=(-0.84, 17.84, 2.46), sound="local_metal_tick.wav", vol=0.34, dist=1.2, dmax=10.0),
)

WEATHER_MATS = (
    "MAT_Wall_PaintedConcrete",
    "MAT_Floor_IndustrialConcrete",
    "MAT_Ceiling_AgedConcrete",
    "MAT_Pipe_DarkPaintedSteel",
    "MAT_Pipe_Secondary",
    "MAT_Structure_PaintedSteel",
    "MAT_Metal_Galvanized",
    "MAT_Cabinet_PaintedMetal",
    "MAT_Valve_IndustrialAccent",
    "MAT_Vent_GalvanizedMetal",
    "MAT_Rubber_Dark",
)


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--render" in argv:
        return "render"
    if "--stills" in argv:
        return "stills"
    if "--steam-fix" in argv:
        return "steam-fix"
    if "--look-restore" in argv:
        return "look-restore"
    if "--setup" in argv or "--no-render" in argv:
        return "setup"
    return "setup"


def incoming(socket):
    return socket.links[0].from_socket if socket.links else None


def clear_collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is not None:
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for child in list(col.children):
            clear_collection(child.name)
            bpy.data.collections.remove(child)
    else:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def ensure_collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def clear_phase1_layer() -> None:
    for name in (COL_ENV, COL_STEAM, COL_AUDIO, COL_WET):
        col = bpy.data.collections.get(name)
        if col is None:
            continue
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    for name in ("LIGHT_P1_FILL", "LIGHT_P1_FILL_C"):
        fill = bpy.data.objects.get(name)
        if fill is not None:
            bpy.data.objects.remove(fill, do_unlink=True)
    for mat in list(bpy.data.materials):
        if mat.name.startswith("MAT_P1_"):
            bpy.data.materials.remove(mat)
    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith("P1_"):
            bpy.data.meshes.remove(mesh)
    for spk in list(bpy.data.speakers):
        if spk.name.startswith("SPK_") or spk.name.startswith("P1_"):
            bpy.data.speakers.remove(spk)
    for group in list(bpy.data.node_groups):
        if group.name.startswith("P1_"):
            bpy.data.node_groups.remove(group)
    scene = bpy.context.scene
    if scene.sequence_editor:
        for strip in list(scene.sequence_editor.strips_all):
            if strip.name.startswith("P1_"):
                scene.sequence_editor.strips.remove(strip)


def restore_lookdev_base() -> None:
    """Rebuild the validated LookDev surfaces, then Phase 1 injects on top."""
    ref.rebuild_reference_materials()
    p106b.rebuild_pipe(bpy.data.materials["MAT_Pipe_DarkPaintedSteel"], True)
    p106b.rebuild_pipe(bpy.data.materials["MAT_Pipe_Secondary"], False)
    if bpy.data.materials.get("MAT_Valve_IndustrialAccent"):
        p106b.rebuild_valve(bpy.data.materials["MAT_Valve_IndustrialAccent"])
    if bpy.data.materials.get("MAT_Metal_Galvanized"):
        p106b.rebuild_galv(bpy.data.materials["MAT_Metal_Galvanized"])
    if bpy.data.materials.get("MAT_Structure_PaintedSteel"):
        p106b.rebuild_structure(bpy.data.materials["MAT_Structure_PaintedSteel"])
    ref.create_blended_puddles()


def build_weathering_group() -> bpy.types.NodeTree:
    existing = bpy.data.node_groups.get("P1_NG_Environment")
    if existing is not None:
        bpy.data.node_groups.remove(existing)
    ng = bpy.data.node_groups.new("P1_NG_Environment", "ShaderNodeTree")
    p6.add_group_socket(ng, "Rust", "OUTPUT", "NodeSocketFloat")
    p6.add_group_socket(ng, "Streak", "OUTPUT", "NodeSocketFloat")
    p6.add_group_socket(ng, "Damp", "OUTPUT", "NodeSocketFloat")
    p6.add_group_socket(ng, "Skirt", "OUTPUT", "NodeSocketFloat")
    p6.add_group_socket(ng, "Condensation", "OUTPUT", "NodeSocketFloat")
    p6.add_group_socket(ng, "Mineral", "OUTPUT", "NodeSocketFloat")
    p6.add_group_socket(ng, "Oil", "OUTPUT", "NodeSocketFloat")
    p6.add_group_socket(ng, "Breakup", "OUTPUT", "NodeSocketFloat")
    nodes = ng.nodes
    links = ng.links
    geom = nodes.new("ShaderNodeNewGeometry")
    geom.location = (-1600, 80)
    sep = nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-1420, 80)
    links.new(geom.outputs["Position"], sep.inputs["Vector"])
    x_s, y_s, z_s = sep.outputs["X"], sep.outputs["Y"], sep.outputs["Z"]
    info = nodes.new("ShaderNodeObjectInfo")
    info.location = (-1600, -360)
    breakup = info.outputs["Random"]

    map_streak = nodes.new("ShaderNodeMapping")
    map_streak.location = (-1200, 280)
    map_streak.inputs["Scale"].default_value = (38.0, 7.5, 0.22)
    links.new(geom.outputs["Position"], map_streak.inputs["Vector"])
    streak_n = nodes.new("ShaderNodeTexNoise")
    streak_n.location = (-1000, 280)
    streak_n.noise_dimensions = "3D"
    streak_n.inputs["Scale"].default_value = 1.15
    streak_n.inputs["Detail"].default_value = 4.0
    streak_n.inputs["Roughness"].default_value = 0.58
    links.new(map_streak.outputs["Vector"], streak_n.inputs["Vector"])
    streak_f = p6.map_range(ng, streak_n.outputs["Factor"], 0.50, 0.84, 0.0, 1.0, (-780, 280))

    drip = None
    for i, (sx, sy, sz, rx, ry, strength) in enumerate(p6.DRIP_SOURCES):
        dx = p6.math_node(ng, "SUBTRACT", (-1200, -40 - i * 70), x_s, sx)
        dy = p6.math_node(ng, "SUBTRACT", (-1040, -40 - i * 70), y_s, sy)
        ax = p6.math_node(ng, "ABSOLUTE", (-880, -20 - i * 70), dx)
        ay = p6.math_node(ng, "ABSOLUTE", (-880, -60 - i * 70), dy)
        fx = p6.map_range(ng, ax, 0.0, rx * 1.15, 1.0, 0.0, (-720, -20 - i * 70))
        fy = p6.map_range(ng, ay, 0.0, ry * 1.10, 1.0, 0.0, (-720, -60 - i * 70))
        lat = p6.math_node(ng, "MULTIPLY", (-540, -40 - i * 70), fx, fy)
        below = p6.math_node(
            ng,
            "GREATER_THAN",
            (-540, -90 - i * 70),
            p6.math_node(ng, "SUBTRACT", (-720, -100 - i * 70), sz, z_s),
            0.02,
        )
        fall = p6.map_range(ng, z_s, 0.03, sz, 1.0, 0.28, (-540, 10 - i * 70))
        src = p6.math_node(ng, "MULTIPLY", (-360, -40 - i * 70), lat, below)
        src = p6.math_node(ng, "MULTIPLY", (-200, -40 - i * 70), src, fall)
        src = p6.math_node(ng, "MULTIPLY", (-40, -40 - i * 70), src, strength)
        src = p6.math_node(ng, "MULTIPLY", (120, -40 - i * 70), src, streak_f)
        drip = src if drip is None else p6.math_node(ng, "MAXIMUM", (280, -40 - i * 40), drip, src)

    skirt_h = p6.map_range(ng, z_s, 0.0, 0.38, 1.0, 0.0, (-1000, 80))
    gap_n = nodes.new("ShaderNodeTexNoise")
    gap_n.location = (-1000, 140)
    gap_n.inputs["Scale"].default_value = 0.48
    gap_n.inputs["Detail"].default_value = 1.4
    links.new(geom.outputs["Position"], gap_n.inputs["Vector"])
    gaps = p6.map_range(ng, gap_n.outputs["Factor"], 0.30, 0.70, 0.08, 1.0, (-780, 140))
    skirt = p6.math_node(ng, "MULTIPLY", (-560, 100), skirt_h, gaps)

    rust = None
    rust_weights = (0.55, 0.92, 0.78, 1.00, 0.84, 0.70, 0.48)
    for j, (jy, w) in enumerate(zip(p6.JOINT_Y, rust_weights)):
        dy = p6.math_node(
            ng,
            "ABSOLUTE",
            (-1000, -720 - j * 48),
            p6.math_node(ng, "SUBTRACT", (-1160, -720 - j * 48), y_s, jy),
        )
        near = p6.map_range(ng, dy, 0.0, 0.22, 1.0, 0.0, (-780, -720 - j * 48))
        near = p6.math_node(ng, "MULTIPLY", (-600, -720 - j * 48), near, w)
        rust = near if rust is None else p6.math_node(ng, "MAXIMUM", (-420, -720 - j * 30), rust, near)
    rust_n = nodes.new("ShaderNodeTexNoise")
    rust_n.location = (-780, -1080)
    rust_n.inputs["Scale"].default_value = 18.0
    rust_n.inputs["Detail"].default_value = 3.0
    links.new(geom.outputs["Position"], rust_n.inputs["Vector"])
    rust_break = p6.map_range(ng, rust_n.outputs["Factor"], 0.38, 0.78, 0.15, 1.0, (-560, -1080))
    rust = p6.math_node(ng, "MULTIPLY", (-280, -1000), rust, rust_break)
    rust = p6.math_node(ng, "MULTIPLY", (-100, -1000), rust, p6.mix_float(ng, breakup, 0.55, 1.0, (-280, -1080)))

    cond_h = p6.map_range(ng, z_s, 1.85, 2.62, 0.0, 1.0, (-1000, 420))
    cond = p6.math_node(ng, "MULTIPLY", (-720, 400), cond_h, rust)
    cond = p6.math_node(ng, "MULTIPLY", (-540, 400), cond, p6.mix_float(ng, breakup, 0.35, 1.0, (-720, 460)))

    mineral = p6.math_node(ng, "MULTIPLY", (320, 40), drip, p6.map_range(ng, z_s, 0.4, 2.4, 0.15, 1.0, (140, 80)))

    oil_dx = p6.math_node(ng, "SUBTRACT", (-1000, 560), x_s, 0.42)
    oil_dy = p6.math_node(ng, "SUBTRACT", (-1000, 510), y_s, 14.70)
    oil_ax = p6.math_node(ng, "ABSOLUTE", (-820, 560), oil_dx)
    oil_ay = p6.math_node(ng, "ABSOLUTE", (-820, 510), oil_dy)
    oil_fx = p6.map_range(ng, oil_ax, 0.0, 0.28, 1.0, 0.0, (-640, 560))
    oil_fy = p6.map_range(ng, oil_ay, 0.0, 0.55, 1.0, 0.0, (-640, 510))
    oil_z = p6.map_range(ng, z_s, -0.01, 0.08, 1.0, 0.0, (-640, 460))
    oil = p6.math_node(ng, "MULTIPLY", (-460, 530), oil_fx, oil_fy)
    oil = p6.math_node(ng, "MULTIPLY", (-300, 530), oil, oil_z)

    out = nodes.new("NodeGroupOutput")
    out.location = (560, 40)
    links.new(rust, out.inputs["Rust"])
    links.new(streak_f, out.inputs["Streak"])
    links.new(drip, out.inputs["Damp"])
    links.new(skirt, out.inputs["Skirt"])
    links.new(cond, out.inputs["Condensation"])
    links.new(mineral, out.inputs["Mineral"])
    links.new(oil, out.inputs["Oil"])
    links.new(breakup, out.inputs["Breakup"])
    return ng


def inject_weathering(group: bpy.types.NodeTree) -> None:
    rust_col = (0.145, 0.062, 0.030)
    oxide = (0.210, 0.110, 0.048)
    damp_col = (0.105, 0.118, 0.112)
    mineral_col = (0.28, 0.26, 0.22)
    oil_col = (0.025, 0.022, 0.018)
    grime = (0.078, 0.070, 0.058)
    recipes = {
        "MAT_Wall_PaintedConcrete": dict(
            color=(("Damp", 0.72, damp_col), ("Skirt", 0.48, grime), ("Streak", 0.16, grime)),
            rough_down=("Damp", 0.14),
            rough_up=("Skirt", 0.07),
            rust=0.0,
            wet=("Damp", 0.22),
        ),
        "MAT_Floor_IndustrialConcrete": dict(
            color=(("Damp", 0.38, damp_col), ("Oil", 0.70, oil_col), ("Skirt", 0.22, grime)),
            rough_down=("Damp", 0.18),
            rough_up=("Oil", 0.04),
            rust=0.0,
            wet=("Damp", 0.28),
        ),
        "MAT_Ceiling_AgedConcrete": dict(
            color=(("Streak", 0.18, grime), ("Mineral", 0.12, mineral_col)),
            rough_down=None,
            rough_up=("Streak", 0.05),
            rust=0.0,
            wet=None,
        ),
        "MAT_Pipe_DarkPaintedSteel": dict(
            color=(("Rust", 0.86, rust_col), ("Mineral", 0.28, mineral_col), ("Condensation", 0.22, damp_col)),
            rough_down=("Condensation", 0.18),
            rough_up=("Rust", 0.16),
            rust=0.72,
            wet=("Condensation", 0.24),
        ),
        "MAT_Pipe_Secondary": dict(
            color=(("Rust", 0.58, oxide), ("Mineral", 0.22, mineral_col), ("Condensation", 0.18, damp_col)),
            rough_down=("Condensation", 0.14),
            rough_up=("Rust", 0.12),
            rust=0.46,
            wet=("Condensation", 0.16),
        ),
        "MAT_Structure_PaintedSteel": dict(
            color=(("Rust", 0.22, oxide), ("Skirt", 0.12, grime)),
            rough_down=None,
            rough_up=("Rust", 0.08),
            rust=0.18,
            wet=None,
        ),
        "MAT_Metal_Galvanized": dict(
            color=(("Rust", 0.16, oxide), ("Mineral", 0.14, mineral_col)),
            rough_down=("Condensation", 0.08),
            rough_up=("Rust", 0.08),
            rust=0.12,
            wet=("Condensation", 0.10),
        ),
        "MAT_Cabinet_PaintedMetal": dict(
            color=(("Skirt", 0.20, grime), ("Damp", 0.10, damp_col)),
            rough_down=None,
            rough_up=("Skirt", 0.05),
            rust=0.04,
            wet=None,
        ),
        "MAT_Valve_IndustrialAccent": dict(
            color=(("Rust", 0.28, rust_col), ("Mineral", 0.18, mineral_col)),
            rough_down=("Condensation", 0.08),
            rough_up=("Rust", 0.10),
            rust=0.22,
            wet=None,
        ),
        "MAT_Vent_GalvanizedMetal": dict(
            color=(("Damp", 0.22, damp_col), ("Mineral", 0.12, mineral_col)),
            rough_down=None,
            rough_up=("Damp", 0.08),
            rust=0.06,
            wet=None,
        ),
        "MAT_Rubber_Dark": dict(
            color=(("Damp", 0.10, damp_col),),
            rough_down=None,
            rough_up=None,
            rust=0.0,
            wet=None,
        ),
    }
    for name, spec in recipes.items():
        mat = bpy.data.materials.get(name)
        if mat is None or not mat.use_nodes:
            continue
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        grp = nt.nodes.new("ShaderNodeGroup")
        grp.node_tree = group
        grp.name = "P1_Weather"
        grp.label = "P1 Environment"
        base_x, base_y = bsdf.location.x - 520, bsdf.location.y + 300
        grp.location = (base_x, base_y)
        color = incoming(bsdf.inputs["Base Color"])
        rough = incoming(bsdf.inputs["Roughness"])
        cursor_y = base_y
        for socket_name, weight, col in spec["color"]:
            fac = p6.math_node(nt, "MULTIPLY", (base_x + 180, cursor_y), grp.outputs[socket_name], weight)
            color = p6.mix_color(nt, fac, color, col, (base_x + 360, cursor_y))
            cursor_y -= 80
        if spec["rust"] > 0.0:
            ox = p6.math_node(nt, "MULTIPLY", (base_x + 180, cursor_y), grp.outputs["Rust"], spec["rust"])
            color = p6.mix_color(nt, ox, color, rust_col, (base_x + 360, cursor_y))
        p6.link(nt, color, bsdf.inputs["Base Color"])
        if spec["rough_up"]:
            sname, amt = spec["rough_up"]
            fac = grp.outputs[sname]
            rough = p6.mix_float(
                nt,
                fac,
                rough,
                p6.math_node(nt, "ADD", (bsdf.location.x - 180, bsdf.location.y - 80), rough, amt),
                (bsdf.location.x - 40, bsdf.location.y - 80),
            )
        if spec["rough_down"]:
            sname, amt = spec["rough_down"]
            fac = p6.math_node(nt, "MULTIPLY", (bsdf.location.x - 260, bsdf.location.y - 140), grp.outputs[sname], 1.0)
            rough = p6.mix_float(
                nt,
                fac,
                rough,
                p6.math_node(nt, "SUBTRACT", (bsdf.location.x - 180, bsdf.location.y - 160), rough, amt),
                (bsdf.location.x - 40, bsdf.location.y - 140),
            )
        p6.link(nt, rough, bsdf.inputs["Roughness"])
        if spec["wet"] and "Coat Weight" in bsdf.inputs:
            sname, amt = spec["wet"]
            coat_in = incoming(bsdf.inputs["Coat Weight"])
            wet = p6.math_node(nt, "MULTIPLY", (bsdf.location.x - 200, bsdf.location.y + 120), grp.outputs[sname], amt)
            if coat_in is not None:
                coat = p6.math_node(nt, "ADD", (bsdf.location.x - 40, bsdf.location.y + 120), coat_in, wet)
                p6.link(nt, coat, bsdf.inputs["Coat Weight"])
            else:
                p6.link(nt, wet, bsdf.inputs["Coat Weight"])


def make_principled(name, color, rough, coat=0.0, spec=0.5, ior=1.45):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        bpy.data.materials.remove(mat)
    return final_pass.make_principled(name, color, rough, coat=coat)


def add_disc(name, x, y, rx, ry, z, mat, col) -> bpy.types.Object:
    verts = []
    count = 16
    for i in range(count):
        a = (2.0 * math.pi * i) / count
        wobble = 1.0 + 0.10 * math.sin(i * 2.15 + y) + 0.04 * math.sin(i * 4.1 + x)
        verts.append((x + rx * wobble * math.cos(a), y + ry * wobble * math.sin(a), z))
    mesh = bpy.data.meshes.new(f"P1_{name}_MESH")
    mesh.from_pydata(verts, [], [tuple(range(count))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    mesh.materials.append(mat)
    if hasattr(obj, "visible_shadow"):
        obj.visible_shadow = False
    return obj


def build_wetness() -> dict:
    col = clear_collection(COL_WET)
    water = make_principled("MAT_P1_ShallowWater", (0.055, 0.066, 0.062), 0.10, coat=0.28)
    bsdf = next(n for n in water.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.70
    oil = make_principled("MAT_P1_OilFilm", (0.018, 0.016, 0.012), 0.22, coat=0.45)
    wet_floor = make_principled("MAT_P1_WetPatch", (0.045, 0.048, 0.046), 0.18, coat=0.16)
    extras = [
        add_disc("P1_WET_VENT_B", -0.52, 12.05, 0.18, 0.32, 0.004, wet_floor, col),
        add_disc("P1_WET_INGRESS_B", 0.58, 15.09, 0.16, 0.28, 0.004, water, col),
        add_disc("P1_OIL_VALVE_B", 0.36, 14.68, 0.22, 0.40, 0.0035, oil, col),
        add_disc("P1_WET_ELBOW_C", -0.48, 17.84, 0.14, 0.24, 0.004, water, col),
    ]
    # Condensation beads at leak hardware — few, shared material.
    bead_mat = make_principled("MAT_P1_Condensation", (0.55, 0.62, 0.64), 0.06, coat=0.35)
    bsdf = next(n for n in bead_mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.55
    bead_locs = (
        (0.84, 14.62, 2.28),
        (0.78, 14.70, 2.22),
        (0.90, 14.54, 2.18),
        (1.01, 15.09, 2.30),
        (0.96, 15.04, 2.20),
        (-0.84, 17.84, 2.32),
        (-0.78, 17.90, 2.24),
        (-0.90, 17.78, 2.16),
        (-0.36, 20.55, 2.20),
        (0.84, 14.47, 2.34),
    )
    beads = []
    for i, loc in enumerate(bead_locs):
        mesh = bpy.data.meshes.new(f"P1_BEAD_{i:02d}_MESH")
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.011 if i % 2 == 0 else 0.008)
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(f"P1_BEAD_{i:02d}", mesh)
        obj.location = loc
        col.objects.link(obj)
        mesh.materials.append(bead_mat)
        beads.append(obj.name)
    return {"wet_objects": [o.name for o in extras], "beads": beads}


def steam_material(name: str, peak: float, seed: float) -> bpy.types.Material:
    """EEVEE leak jet: elongated cube, broken noise, source-dense, zero filled emission."""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.name = "P1_SteamVolume"
    vol.location = (980, 40)
    vol.inputs["Color"].default_value = (0.92, 0.74, 0.48, 1.0)
    vol.inputs["Density"].default_value = 0.0
    if "Anisotropy" in vol.inputs:
        vol.inputs["Anisotropy"].default_value = 0.18
    if "Emission Color" in vol.inputs:
        vol.inputs["Emission Color"].default_value = (0.96, 0.70, 0.38, 1.0)
    if "Emission Strength" in vol.inputs:
        vol.inputs["Emission Strength"].default_value = 0.0

    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-1100, 40)
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.name = "P1_SteamAdvect"
    mapping.location = (-900, 80)
    # Stretch noise along the leak so features read as streaks, not a disc.
    mapping.inputs["Scale"].default_value = (2.05, 1.75, 0.38)
    mapping.inputs["Location"].default_value = (seed, seed * 0.37, 0.0)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])

    def noise(loc, scale, detail, roughness, w, distortion=0.55):
        node = nt.nodes.new("ShaderNodeTexNoise")
        node.location = loc
        node.noise_dimensions = "4D"
        node.inputs["Scale"].default_value = scale
        node.inputs["Detail"].default_value = detail
        if "Roughness" in node.inputs:
            node.inputs["Roughness"].default_value = roughness
        if "Distortion" in node.inputs:
            node.inputs["Distortion"].default_value = distortion
        if "W" in node.inputs:
            node.inputs["W"].default_value = w
        nt.links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node

    def map_range(loc, src, fmin, fmax, tmin, tmax):
        node = nt.nodes.new("ShaderNodeMapRange")
        node.location = loc
        node.clamp = True
        nt.links.new(src, node.inputs["Value"])
        node.inputs["From Min"].default_value = fmin
        node.inputs["From Max"].default_value = fmax
        node.inputs["To Min"].default_value = tmin
        node.inputs["To Max"].default_value = tmax
        return node

    n_large = noise((-680, 260), 1.55, 6.0, 0.68, seed)
    n_large.name = "P1_SteamNoiseLarge"
    n_fine = noise((-680, 20), 5.2, 3.0, 0.52, seed + 1.7, 0.8)
    n_fine.name = "P1_SteamNoiseFine"
    cells = nt.nodes.new("ShaderNodeTexVoronoi")
    cells.name = "P1_SteamCells"
    cells.location = (-680, -240)
    cells.voronoi_dimensions = "4D"
    cells.feature = "F1"
    if "Scale" in cells.inputs:
        cells.inputs["Scale"].default_value = 2.35
    if "Randomness" in cells.inputs:
        cells.inputs["Randomness"].default_value = 1.0
    if "W" in cells.inputs:
        cells.inputs["W"].default_value = seed + 3.4
    nt.links.new(mapping.outputs["Vector"], cells.inputs["Vector"])

    # Hard contrast so EEVEE froxels keep holes instead of averaging into a disc.
    clumps = map_range((-420, 260), n_large.outputs["Fac"], 0.42, 0.58, 0.0, 1.0)
    wisps = map_range((-420, 20), n_fine.outputs["Fac"], 0.34, 0.68, 0.12, 1.0)
    distance = cells.outputs["Distance"] if "Distance" in cells.outputs else cells.outputs[0]
    holes = map_range((-420, -240), distance, 0.22, 0.48, 1.0, 0.0)

    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-900, -420)
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
    # Dense at the valve (local -Z), feathered toward the tip. Not radial.
    along = map_range((-620, -360), sep.outputs["Z"], -0.48, 0.46, 1.0, 0.08)

    absx = nt.nodes.new("ShaderNodeMath")
    absx.operation = "ABSOLUTE"
    absx.location = (-620, -520)
    nt.links.new(sep.outputs["X"], absx.inputs[0])
    absy = nt.nodes.new("ShaderNodeMath")
    absy.operation = "ABSOLUTE"
    absy.location = (-620, -620)
    nt.links.new(sep.outputs["Y"], absy.inputs[0])
    # Square-ish cross-section (not LENGTH) so the jet never silhouettes as an oval.
    lateral = nt.nodes.new("ShaderNodeMath")
    lateral.operation = "MAXIMUM"
    lateral.location = (-440, -560)
    nt.links.new(absx.outputs[0], lateral.inputs[0])
    nt.links.new(absy.outputs[0], lateral.inputs[1])
    widen = map_range((-440, -720), sep.outputs["Z"], -0.48, 0.46, 0.62, 1.18)
    scaled = nt.nodes.new("ShaderNodeMath")
    scaled.operation = "DIVIDE"
    scaled.location = (-240, -560)
    nt.links.new(lateral.outputs[0], scaled.inputs[0])
    nt.links.new(widen.outputs["Result"], scaled.inputs[1])
    n_lat_m = nt.nodes.new("ShaderNodeMath")
    n_lat_m.operation = "MULTIPLY"
    n_lat_m.location = (-240, -720)
    nt.links.new(n_fine.outputs["Fac"], n_lat_m.inputs[0])
    n_lat_m.inputs[1].default_value = 0.28
    n_lat = nt.nodes.new("ShaderNodeMath")
    n_lat.operation = "SUBTRACT"
    n_lat.location = (-240, -840)
    nt.links.new(n_lat_m.outputs[0], n_lat.inputs[0])
    n_lat.inputs[1].default_value = 0.14
    ragged = nt.nodes.new("ShaderNodeMath")
    ragged.operation = "SUBTRACT"
    ragged.location = (-40, -560)
    nt.links.new(scaled.outputs[0], ragged.inputs[0])
    nt.links.new(n_lat.outputs[0], ragged.inputs[1])
    lat_mask = map_range((160, -560), ragged.outputs[0], 0.03, 0.40, 1.0, 0.0)

    amount = nt.nodes.new("ShaderNodeValue")
    amount.name = "P1_SteamAmount"
    amount.label = "Steam Amount"
    amount.location = (160, 340)
    amount.outputs[0].default_value = 0.0

    structure = nt.nodes.new("ShaderNodeMath")
    structure.operation = "MULTIPLY"
    structure.location = (160, 180)
    nt.links.new(clumps.outputs["Result"], structure.inputs[0])
    nt.links.new(wisps.outputs["Result"], structure.inputs[1])
    broken = nt.nodes.new("ShaderNodeMath")
    broken.operation = "MULTIPLY"
    broken.location = (340, 140)
    nt.links.new(structure.outputs[0], broken.inputs[0])
    nt.links.new(holes.outputs["Result"], broken.inputs[1])
    shaped = nt.nodes.new("ShaderNodeMath")
    shaped.operation = "MULTIPLY"
    shaped.location = (340, -40)
    nt.links.new(broken.outputs[0], shaped.inputs[0])
    nt.links.new(along.outputs["Result"], shaped.inputs[1])
    masked = nt.nodes.new("ShaderNodeMath")
    masked.operation = "MULTIPLY"
    masked.location = (540, -40)
    nt.links.new(shaped.outputs[0], masked.inputs[0])
    nt.links.new(lat_mask.outputs["Result"], masked.inputs[1])
    mul_peak = nt.nodes.new("ShaderNodeMath")
    mul_peak.operation = "MULTIPLY"
    mul_peak.location = (540, 140)
    nt.links.new(amount.outputs[0], mul_peak.inputs[0])
    mul_peak.inputs[1].default_value = peak
    dens = nt.nodes.new("ShaderNodeMath")
    dens.operation = "MULTIPLY"
    dens.location = (740, 40)
    nt.links.new(mul_peak.outputs[0], dens.inputs[0])
    nt.links.new(masked.outputs[0], dens.inputs[1])
    nt.links.new(dens.outputs[0], vol.inputs["Density"])
    # Tiny structured emission on wisps only — never a filled disc.
    emit = nt.nodes.new("ShaderNodeMath")
    emit.operation = "MULTIPLY"
    emit.location = (740, 220)
    nt.links.new(amount.outputs[0], emit.inputs[0])
    emit.inputs[1].default_value = 0.008
    emit2 = nt.nodes.new("ShaderNodeMath")
    emit2.operation = "MULTIPLY"
    emit2.location = (900, 220)
    nt.links.new(emit.outputs[0], emit2.inputs[0])
    nt.links.new(broken.outputs[0], emit2.inputs[1])
    if "Emission Strength" in vol.inputs:
        nt.links.new(emit2.outputs[0], vol.inputs["Emission Strength"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (1220, 40)
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    mat["p1_peak_density"] = peak
    return mat


def key_socket(socket, frame: int, value) -> None:
    socket.default_value = value
    socket.keyframe_insert(data_path="default_value", frame=frame)


def soften_action(id_data) -> None:
    ad = getattr(id_data, "animation_data", None)
    if ad is None or ad.action is None:
        return
    for layer in ad.action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "BEZIER"
                        kp.handle_left_type = "AUTO_CLAMPED"
                        kp.handle_right_type = "AUTO_CLAMPED"


def key_density(mat: bpy.types.Material, frame: int, value: float) -> None:
    amount = mat.node_tree.nodes["P1_SteamAmount"]
    peak = float(mat.get("p1_peak_density", 1.0)) or 1.0
    amount.outputs[0].default_value = 0.0 if peak <= 0 else (value / peak)
    amount.outputs[0].keyframe_insert(data_path="default_value", frame=frame)
    soften_action(mat.node_tree)


def add_steam_volume(name, mat, col) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"P1_{name}_MESH")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    mesh.materials.append(mat)
    obj.display_type = "WIRE"
    if hasattr(obj, "visible_shadow"):
        obj.visible_shadow = False
    return obj


def animate_steam_advection(mat: bpy.types.Material, start: int, end: int, seed: float) -> None:
    mapping = mat.node_tree.nodes["P1_SteamAdvect"]
    n_large = mat.node_tree.nodes["P1_SteamNoiseLarge"]
    n_fine = mat.node_tree.nodes["P1_SteamNoiseFine"]
    loc = mapping.inputs["Location"]
    key_socket(loc, start, (seed, seed * 0.37, 0.0))
    key_socket(loc, end, (seed + 0.55, seed * 0.37 + 0.95, 1.65))
    if "W" in n_large.inputs:
        key_socket(n_large.inputs["W"], start, seed)
        key_socket(n_large.inputs["W"], end, seed + 1.85)
        key_socket(n_fine.inputs["W"], start, seed + 1.7)
        key_socket(n_fine.inputs["W"], end, seed + 3.6)
    cells = mat.node_tree.nodes.get("P1_SteamCells")
    if cells is not None and "W" in cells.inputs:
        key_socket(cells.inputs["W"], start, seed + 3.4)
        key_socket(cells.inputs["W"], end, seed + 5.1)
    soften_action(mat.node_tree)


def build_steam() -> dict:
    col = clear_collection(COL_STEAM)
    created = []
    for spec in STEAM_SOCKETS:
        mat = steam_material(f"MAT_P1_{spec['name']}", spec["peak_density"], spec["seed"])
        obj = add_steam_volume(spec["name"], mat, col)
        source = Vector(spec["source"])
        aim = Vector(spec["aim"])
        leak = aim - source
        empty = bpy.data.objects.new(f"{spec['name']}_SOURCE", None)
        empty.location = source
        empty.rotation_euler = leak.normalized().to_track_quat("Z", "Y").to_euler()
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.08
        col.objects.link(empty)
        obj.parent = empty
        start, peak, hold, end = spec["keys"]
        scale_keys = (
            (1, (0.07, 0.06, 0.14)),
            (start, (0.12, 0.10, 0.28)),
            (peak, (0.38, 0.52, 1.42)),
            (hold, (0.50, 0.70, 1.78)),
            (end, (0.62, 0.88, 2.08)),
            (FRAME_END, (0.62, 0.88, 2.08)),
        )
        obj.animation_data_clear()
        for frame, scale in scale_keys:
            obj.scale = scale
            drift = (frame - start) / max(end - start, 1)
            obj.location = (
                0.03 * spec["seed"] + 0.05 * drift,
                -0.02 * spec["seed"] - 0.04 * drift,
                scale[2] * 0.48,
            )
            obj.keyframe_insert(data_path="scale", frame=frame)
            obj.keyframe_insert(data_path="location", frame=frame)
        soften_action(obj)
        key_density(mat, 1, 0.0)
        key_density(mat, start, 0.0)
        key_density(mat, peak, spec["peak_density"])
        key_density(mat, hold, spec["peak_density"] * 0.72)
        key_density(mat, end, 0.0)
        key_density(mat, FRAME_END, 0.0)
        animate_steam_advection(mat, start, end, spec["seed"])
        created.append(
            {
                "name": spec["name"],
                "kind": spec["kind"],
                "source": spec["source"],
                "aim": spec["aim"],
                "frames": spec["keys"],
                "peak_density": spec["peak_density"],
            }
        )
    return {"sockets": created}


def zero_world_volume() -> dict:
    """World volume reads as camera-attached fog. Heat is carried by local steam only."""
    scene = bpy.context.scene
    world = scene.world
    if world and world.node_tree:
        vol = world.node_tree.nodes.get("P10_Volume")
        if vol is not None and "Density" in vol.inputs:
            vol.inputs["Density"].default_value = 0.0
    return {"world_volume_density": 0.0}


def apply_steam_correction() -> dict:
    """Rebuild only the steam layer. Preserve weathering, wetness, lights, audio, camera."""
    cam_before = camera_keys()
    for mat in list(bpy.data.materials):
        if mat.name.startswith("MAT_P1_STEAM"):
            bpy.data.materials.remove(mat)
    steam = build_steam()
    world = zero_world_volume()
    configure_eevee_phase1(bpy.context.scene)
    bpy.context.scene["PHASE1_STEAM_FIX"] = 1
    cam_after = camera_keys()
    report = {
        "steam": steam,
        "world": world,
        "camera_unchanged": cam_before == cam_after,
        "camera": cam_after,
        "objects": len(bpy.data.objects),
        "lights": len([o for o in bpy.data.objects if o.type == "LIGHT"]),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "phase1_steam_fix.json").write_text(json.dumps(report, indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    return report


def tint_steam_to_practicals() -> dict:
    """Keep steam domains/keys. Warm scatter so wisps inherit tungsten, not grey-white."""
    tinted = []
    for mat in bpy.data.materials:
        if not mat.name.startswith("MAT_P1_STEAM"):
            continue
        nt = mat.node_tree
        if nt is None:
            continue
        vol = nt.nodes.get("P1_SteamVolume")
        if vol is None:
            continue
        vol.inputs["Color"].default_value = (0.92, 0.74, 0.48, 1.0)
        if "Emission Color" in vol.inputs:
            vol.inputs["Emission Color"].default_value = (0.96, 0.70, 0.38, 1.0)
        for node in nt.nodes:
            if node.type != "MATH" or node.operation != "MULTIPLY":
                continue
            if abs(node.inputs[1].default_value - 0.022) < 1e-4 or abs(node.inputs[1].default_value - 0.034) < 1e-4:
                node.inputs[1].default_value = 0.008
        tinted.append(mat.name)
    return {"tinted": tinted}


def apply_look_restore() -> dict:
    """Restore dark warm practical lighting. Do not rebuild steam, camera, door, or layout."""
    cam_before = camera_keys()
    heat = apply_heat_atmosphere()
    lighting = apply_lighting_variation()
    steam = tint_steam_to_practicals()
    world = zero_world_volume()
    configure_eevee_phase1(bpy.context.scene)
    bpy.context.scene["PHASE1_LOOK_RESTORE"] = 1
    cam_after = camera_keys()
    report = {
        "heat": heat,
        "lighting": lighting,
        "steam": steam,
        "world": world,
        "camera_unchanged": cam_before == cam_after,
        "camera": cam_after,
        "fill_present": bool(bpy.data.objects.get("LIGHT_P1_FILL") or bpy.data.objects.get("LIGHT_P1_FILL_C")),
        "active_lights": sorted(
            o.name for o in bpy.data.objects if o.type == "LIGHT" and o.data.energy > 0.01
        ),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "phase1_look_restore.json").write_text(json.dumps(report, indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    return report

def apply_heat_atmosphere() -> dict:
    scene = bpy.context.scene
    world = scene.world
    density = 0.0
    strength = 0.04
    color = (0.70, 0.46, 0.22, 1.0)
    if world and world.node_tree:
        bg = world.node_tree.nodes.get("Background")
        if bg is not None:
            bg.inputs[1].default_value = strength
            if "Color" in bg.inputs:
                bg.inputs["Color"].default_value = color
        vol = world.node_tree.nodes.get("P10_Volume")
        if vol is not None and "Density" in vol.inputs:
            vol.inputs["Density"].default_value = density
            if "Color" in vol.inputs:
                vol.inputs["Color"].default_value = (0.62, 0.48, 0.28, 1.0)
    return {"world_strength": strength, "volume_density": density, "world_color": color[:3]}


def action_fcurves(action):
    return list(final_pass.action_fcurves(action))


def apply_lighting_variation() -> dict:
    """Practical fixtures only. No corridor-wide fill. Warm dirty-yellow tungsten."""
    for name in ("LIGHT_P1_FILL", "LIGHT_P1_FILL_C"):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.lights.remove(data)
        light = bpy.data.lights.get(name)
        if light is not None:
            bpy.data.lights.remove(light)

    practical_colors = {
        "LIGHT_A_03_NORMAL": (1.00, 0.78, 0.42),
        "LIGHT_A_04_AGED_TINT": (1.00, 0.74, 0.38),
        "LIGHT_B_01_NORMAL": (1.00, 0.82, 0.46),
        "LIGHT_FINAL_DOOR_FLUORESCENT": (1.00, 0.80, 0.48),
    }
    warmed = []
    for name, color in practical_colors.items():
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "LIGHT":
            continue
        obj.data.color = color
        warmed.append(name)

    variations = {
        "LIGHT_A_03_NORMAL": (
            (1, 16.6),
            (28, 17.4),
            (64, 16.4),
            (110, 17.6),
            (168, 16.8),
            (230, 17.3),
            (300, 16.7),
            (360, 17.1),
        ),
        "LIGHT_B_01_NORMAL": (
            (1, 15.4),
            (40, 14.8),
            (96, 16.0),
            (150, 15.2),
            (210, 15.8),
            (280, 14.9),
            (360, 15.5),
        ),
    }
    for name, keys in variations.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.data.animation_data_clear()
        for frame, energy in keys:
            obj.data.energy = energy
            obj.data.keyframe_insert(data_path="energy", frame=frame)
        if obj.data.animation_data and obj.data.animation_data.action:
            for fc in action_fcurves(obj.data.animation_data.action):
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
                    kp.handle_left_type = "AUTO_CLAMPED"
                    kp.handle_right_type = "AUTO_CLAMPED"
    return {
        "fill": [],
        "warmed": warmed,
        "varied": list(variations),
        "door_light_untouched": True,
    }


def load_sound(filename: str):
    path = ASSET_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing Phase 1 audio: {path}")
    existing = bpy.data.sounds.get(path.name)
    if existing is not None:
        return existing
    sound = bpy.data.sounds.load(str(path))
    sound.name = path.name
    try:
        sound.pack()
    except Exception:
        pass
    return sound


def add_speaker(name, loc, sound, vol, dist, dmax, col) -> bpy.types.Object:
    data = bpy.data.speakers.new(name)
    data.sound = sound
    data.volume = vol
    data.attenuation = 1.4
    if hasattr(data, "distance_reference"):
        data.distance_reference = dist
    if hasattr(data, "distance_max"):
        data.distance_max = dmax
    if hasattr(data, "volume_min"):
        data.volume_min = 0.0
    if hasattr(data, "volume_max"):
        data.volume_max = vol
    obj = bpy.data.objects.new(name, data)
    obj.location = loc
    col.objects.link(obj)
    return obj


def build_audio() -> dict:
    col = clear_collection(COL_AUDIO)
    scene = bpy.context.scene
    if not scene.sequence_editor:
        scene.sequence_editor_create()
    seq = scene.sequence_editor
    for strip in list(seq.strips_all):
        if strip.name.startswith("P1_"):
            seq.strips.remove(strip)
    amb_path = ASSET_DIR / "amb_level2_loop.wav"
    rare_path = ASSET_DIR / "rare_distant_structure.wav"
    load_sound(amb_path.name)
    load_sound(rare_path.name)
    amb_strip = seq.strips.new_sound("P1_AMB_LEVEL2", str(amb_path), 1, FRAME_START)
    amb_strip.volume = 0.42
    rare_strip = seq.strips.new_sound("P1_RARE_STRUCTURE", str(rare_path), 2, FRAME_START)
    rare_strip.volume = 0.22
    placed = []
    for spec in SPEAKERS:
        sound = load_sound(spec["sound"])
        add_speaker(spec["name"], spec["loc"], sound, spec["vol"], spec["dist"], spec["dmax"], col)
        placed.append(spec["name"])
    for spec in STEAM_SOCKETS:
        sound = load_sound(spec["sound"])
        add_speaker(spec["speaker"], spec["source"], sound, 0.62, 0.8, 8.5, col)
        placed.append(spec["speaker"])
    scene.audio_volume = 1.0
    if hasattr(scene, "audio_distance_model"):
        scene.audio_distance_model = "INVERSE_CLAMPED"
    return {
        "ambience": amb_strip.name,
        "rare": rare_strip.name,
        "speakers": placed,
        "source": "procedural (no user Level 2 file in workspace)",
    }


def configure_eevee_phase1(scene: bpy.types.Scene) -> None:
    p106b.restore_eevee(scene)
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 12
    scene.eevee.volumetric_start = 0.12
    scene.eevee.volumetric_end = 28.0
    scene.eevee.volumetric_samples = 48
    scene.eevee.volumetric_tile_size = "2"
    if hasattr(scene.eevee, "use_volume_custom_range"):
        scene.eevee.use_volume_custom_range = True
    scene.eevee.use_raytracing = True
    scene.eevee.use_fast_gi = True
    scene.eevee.fast_gi_method = "AMBIENT_OCCLUSION_ONLY"
    scene.eevee.use_volumetric_shadows = False
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.use_motion_blur = False
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    scene.render.fps = FPS
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.render.filepath = str(FRAME_DIR / "frame_")
    scene.render.use_file_extension = True
    scene.render.use_overwrite = True
    scene.render.use_placeholder = False


def snapshot_counts() -> dict:
    scene = bpy.context.scene
    return {
        "objects": len(bpy.data.objects),
        "materials": len(bpy.data.materials),
        "lights": len([o for o in bpy.data.objects if o.type == "LIGHT"]),
        "speakers": len([o for o in bpy.data.objects if o.type == "SPEAKER"]),
        "steam_volumes": len([o for o in bpy.data.objects if o.name.startswith("STEAM_SOCKET_") and o.type == "MESH"]),
        "engine": scene.render.engine,
        "samples": scene.eevee.taa_render_samples,
        "volume_samples": scene.eevee.volumetric_samples,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "fps": scene.render.fps,
        "frames": [scene.frame_start, scene.frame_end],
        "camera": scene.camera.name if scene.camera else None,
    }


def camera_keys() -> dict:
    cam = bpy.data.objects.get(WALK_CAM)
    tgt = bpy.data.objects.get(WALK_TARGET)
    return {
        "camera": p105.inspect_keys(cam) if cam else [],
        "target": p105.inspect_keys(tgt) if tgt else [],
    }


def apply_phase1() -> dict:
    before = snapshot_counts()
    cam_before = camera_keys()
    clear_phase1_layer()
    restore_lookdev_base()
    group = build_weathering_group()
    inject_weathering(group)
    wet = build_wetness()
    steam = build_steam()
    heat = apply_heat_atmosphere()
    lighting = apply_lighting_variation()
    audio = build_audio()
    configure_eevee_phase1(bpy.context.scene)
    bpy.context.scene["PHASE1_ENVIRONMENT"] = 1
    after = snapshot_counts()
    cam_after = camera_keys()
    report = {
        "before": before,
        "after": after,
        "camera_before": cam_before,
        "camera_after": cam_after,
        "camera_unchanged": cam_before == cam_after,
        "wet": wet,
        "steam": steam,
        "heat": heat,
        "lighting": lighting,
        "audio": audio,
        "checkpoint": str(CHECKPOINT),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "phase1_setup.json").write_text(json.dumps(report, indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    return report


def render_stills(frames=(1, 72, 144, 180, 240, 264, 336, 348), prefix="phase1_lookrestore") -> list[Path]:
    scene = bpy.context.scene
    configure_eevee_phase1(scene)
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    scene.camera = bpy.data.objects[WALK_CAM]
    paths = []
    for frame in frames:
        scene.frame_set(frame)
        path = STILL_DIR / f"{prefix}_f{frame:04d}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        shutil.copy2(path, ARTIFACT_DIR / path.name)
        paths.append(path)
    return paths


def mixdown_audio(path: Path) -> Path:
    mix_script = SCRIPT_DIR / "mix_phase1_audio.py"
    subprocess.check_call(["python3", str(mix_script)])
    generated = OUTPUT_DIR / "phase1_mixdown.wav"
    if generated != path:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated, path)
    return path


def encode_mp4(frame_dir: Path, audio_path: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-start_number", "1",
        "-i", str(frame_dir / "frame_%04d.png"),
        "-i", str(audio_path),
        "-shortest",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(dest),
    ]
    subprocess.check_call(cmd)


def render_animation() -> dict:
    scene = bpy.context.scene
    configure_eevee_phase1(scene)
    if FRAME_DIR.exists():
        shutil.rmtree(FRAME_DIR)
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(FRAME_DIR / "frame_")
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.camera = bpy.data.objects[WALK_CAM]
    t0 = time.time()
    bpy.ops.render.render(animation=True)
    elapsed = time.time() - t0
    frames = sorted(FRAME_DIR.glob("frame_*.png"))
    audio_path = OUTPUT_DIR / "phase1_mixdown.wav"
    mixdown_audio(audio_path)
    mp4 = OUTPUT_DIR / "phase1_look_restore_review.mp4"
    encode_mp4(FRAME_DIR, audio_path, mp4)
    artifact = ARTIFACT_DIR / "phase1_look_restore_review.mp4"
    try:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mp4, artifact)
    except OSError as exc:
        artifact = None
        print(f"artifact copy skipped: {exc}")
    return {
        "frame_count": len(frames),
        "elapsed_sec": round(elapsed, 2),
        "sec_per_frame": round(elapsed / max(len(frames), 1), 3),
        "mp4": str(mp4),
        "artifact": str(artifact),
        "audio": str(audio_path),
    }


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mode = parse_mode()
    if mode == "setup":
        report = apply_phase1()
        print(json.dumps({"mode": mode, **{k: report[k] for k in ("before", "after", "camera_unchanged")}}, indent=2))
        return
    if mode == "steam-fix":
        report = apply_steam_correction()
        print(json.dumps({"mode": mode, "camera_unchanged": report["camera_unchanged"], "steam": report["steam"]}, indent=2))
        return
    if mode == "look-restore":
        report = apply_look_restore()
        print(json.dumps({"mode": mode, "camera_unchanged": report["camera_unchanged"], "fill_present": report["fill_present"], "heat": report["heat"]}, indent=2))
        return
    if mode == "stills":
        if bpy.context.scene.get("PHASE1_ENVIRONMENT") != 1:
            apply_phase1()
        paths = render_stills()
        print("stills", [str(p) for p in paths])
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
        return
    if mode == "render":
        if bpy.context.scene.get("PHASE1_ENVIRONMENT") != 1:
            apply_phase1()
        result = render_animation()
        (OUTPUT_DIR / "phase1_render.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
