#!/usr/bin/env python3
"""Phase 2 — Level 2 Spatial Expansion.

Additive extension on the frozen Phase 1 hallway.  Does not rebuild corridor
layout, CAM_P105_WALK, door sequence, steam sockets, weathering, or lighting
philosophy.  Re-running --setup from phase2_pre_spatial_expansion.blend
reproduces only PHASE2_* collections.

Pipeline:
  phase2_pre_spatial_expansion.blend  →  this script --setup  →  hallway.blend
  this script --stills   →  Preview Gate frames
  this script --render   →  phase2_spatial_expansion_review.mp4

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase2_spatial.py -- --setup
  blender -b hallway.blend --python scripts/build_hallway_phase2_spatial.py -- --stills
  blender -b hallway.blend --python scripts/build_hallway_phase2_spatial.py -- --render
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

import build_hallway_phase1_environment as p1
import build_hallway_phase3 as p3
import build_hallway_phase10_5 as p105

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
CHECKPOINT = ROOT / "renders" / "checkpoints" / "phase2_pre_spatial_expansion.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase2_spatial"
STILL_DIR = OUTPUT_DIR / "stills"
FRAME_DIR = OUTPUT_DIR / "frames"
ASSET_DIR = ROOT / "assets" / "hallway_phase2_spatial"
ARTIFACT_DIR = Path("/opt/cursor/artifacts")
WALK_CAM = "CAM_P105_WALK"
WALK_TARGET = "CAM_P105_WALK.Target"
REVIEW_CAM = "CAM_P2_REVIEW"
REVIEW_TARGET = "CAM_P2_REVIEW.Target"
FPS = 24
RES_X, RES_Y = 768, 432
FRAME_START, FRAME_END = 1, 720

COL_GEO = "PHASE2_SPATIAL"
COL_PIPE = "PHASE2_PIPES"
COL_PROP = "PHASE2_PROPS"
COL_LIGHT = "PHASE2_LIGHTS"
COL_STEAM = "PHASE2_STEAM"
COL_AUDIO = "PHASE2_AUDIO"
COL_CAM = "PHASE2_CAMERAS"
COL_WET = "PHASE2_WET"
PREFIX = "P2_"

# Hub west of Zone A opening. Interior faces.
HUB_X0, HUB_X1 = -5.45, -1.10
HUB_Y0, HUB_Y1 = 4.85, 7.55
HUB_H = 2.82

HOT_X0, HOT_X1 = -5.45, -3.35
HOT_Y0, HOT_Y1 = 7.55, 13.35
HOT_DROP = 0.32

VENT_X0, VENT_X1 = -5.45, -3.35
VENT_Y0, VENT_Y1 = 0.45, 4.85

DEAD_X0, DEAD_X1 = -8.55, -5.45
DEAD_Y0, DEAD_Y1 = 0.45, 1.85

MAINT_X0, MAINT_X1 = -8.55, -5.45
MAINT_Y0, MAINT_Y1 = 5.05, 7.95

EAST_X0, EAST_X1 = 1.10, 3.55
EAST_Y0, EAST_Y1 = 1.90, 2.95

OPEN_Y0, OPEN_Y1 = 5.68, 6.72
OPEN_Z1 = 2.32
EAST_OPEN_Y0, EAST_OPEN_Y1 = 1.95, 2.90

# First-person review path. Does not touch CAM_P105_WALK.
# Stays inside walkable interiors: corridor → hub → hot → vent → dead → hub → maint → corridor.
ROUTE = (
    (1, (0.00, 1.85, 1.68), (0.04, 8.60, 1.42)),
    (40, (0.00, 4.55, 1.68), (-0.95, 6.18, 1.48)),
    (72, (0.02, 6.20, 1.68), (-3.10, 6.18, 1.46)),
    (120, (-2.20, 6.12, 1.68), (-4.55, 6.22, 1.28)),
    (160, (-3.25, 6.12, 1.68), (-4.28, 7.70, 1.38)),
    (210, (-4.35, 8.15, 1.42), (-4.32, 11.20, 1.18)),
    (280, (-4.36, 9.40, 1.36), (-4.28, 12.55, 1.32)),
    (340, (-4.36, 8.05, 1.46), (-4.22, 5.20, 1.25)),
    (400, (-4.08, 3.40, 1.68), (-4.75, 1.10, 1.32)),
    (455, (-4.40, 1.18, 1.68), (-7.35, 1.14, 1.38)),
    (510, (-6.95, 1.16, 1.68), (-8.30, 1.14, 1.42)),
    (555, (-4.38, 2.35, 1.68), (-4.25, 5.55, 1.38)),
    (600, (-4.35, 6.12, 1.68), (-7.05, 6.42, 1.22)),
    (645, (-7.00, 6.42, 1.68), (-8.05, 7.30, 1.08)),
    (685, (-3.05, 6.16, 1.68), (0.85, 6.22, 1.48)),
    (720, (0.00, 7.15, 1.68), (0.02, 16.40, 1.32)),
)

P2_STEAM = (
    dict(
        name="STEAM_P2_PIPE_HUB",
        source=(-2.55, 7.28, 2.38),
        aim=(-2.72, 7.05, 1.18),
        peak_density=9.4,
        keys=(110, 135, 175, 230),
        seed=0.41,
    ),
    dict(
        name="STEAM_P2_HOT_A",
        source=(-3.52, 10.85, 2.22),
        aim=(-3.78, 11.05, 1.08),
        peak_density=14.8,
        keys=(230, 260, 310, 390),
        seed=0.88,
        scale=(1.15, 1.20, 1.35),
    ),
    dict(
        name="STEAM_P2_HOT_B",
        source=(-5.22, 12.40, 2.18),
        aim=(-4.95, 12.55, 1.02),
        peak_density=13.6,
        keys=(250, 285, 340, 420),
        seed=1.27,
        scale=(1.10, 1.15, 1.30),
    ),
)

P2_LIGHTS = (
    dict(name="LIGHT_P2_HUB", loc=(-3.40, 6.20, 2.48), energy=15.2, color=(1.00, 0.78, 0.40), size=1.10, rot=(0.0, 0.0, 0.0)),
    dict(name="LIGHT_P2_HUB_AIM", loc=(-3.55, 6.35, 2.05), energy=9.8, color=(1.00, 0.74, 0.36), size=0.62, rot=(-1.22, 0.0, 0.0)),
    dict(name="LIGHT_P2_HOT", loc=(-4.40, 10.70, 2.22), energy=16.8, color=(1.00, 0.70, 0.32), size=1.00, rot=(0.0, 0.0, 0.0)),
    dict(name="LIGHT_P2_HOT_AIM", loc=(-4.38, 11.05, 1.82), energy=12.4, color=(1.00, 0.66, 0.28), size=0.72, rot=(-1.28, 0.0, 0.0)),
    dict(name="LIGHT_P2_HOT_FAR", loc=(-4.40, 12.20, 2.18), energy=14.2, color=(1.00, 0.68, 0.30), size=0.85, rot=(0.0, 0.0, 0.0)),
    dict(name="LIGHT_P2_VENT", loc=(-4.40, 2.35, 2.42), energy=13.6, color=(0.84, 0.90, 0.98), size=1.00, rot=(0.0, 0.0, 0.0)),
    dict(name="LIGHT_P2_VENT_AIM", loc=(-4.55, 2.50, 1.88), energy=8.8, color=(0.80, 0.86, 0.96), size=0.58, rot=(0.0, 1.22, 0.0)),
    dict(name="LIGHT_P2_MAINT", loc=(-7.00, 6.48, 2.28), energy=12.6, color=(1.00, 0.80, 0.46), size=0.82, rot=(0.0, 0.0, 0.0)),
    dict(name="LIGHT_P2_SHAFT", loc=(-5.00, 7.26, 4.15), energy=7.2, color=(1.00, 0.76, 0.38), size=0.42, rot=(3.1416, 0.0, 0.0)),
    dict(name="LIGHT_P2_DEAD", loc=(-7.05, 1.16, 2.12), energy=8.4, color=(0.82, 0.88, 0.96), size=0.62, rot=(0.0, 0.0, 0.0)),
)


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--render" in argv:
        return "render"
    if "--stills" in argv:
        return "stills"
    return "setup"


def mat(name: str) -> bpy.types.Material:
    found = bpy.data.materials.get(name)
    if found is None:
        raise RuntimeError(f"Protected material missing: {name}")
    return found


def clear_phase2() -> None:
    for name in (COL_GEO, COL_PIPE, COL_PROP, COL_LIGHT, COL_STEAM, COL_AUDIO, COL_CAM, COL_WET):
        col = bpy.data.collections.get(name)
        if col is None:
            continue
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    for block in list(bpy.data.lights):
        if block.name.startswith("LIGHT_P2_"):
            bpy.data.lights.remove(block)
    for block in list(bpy.data.materials):
        if block.name.startswith("MAT_P2_STEAM") or block.name.startswith("MAT_P2_"):
            bpy.data.materials.remove(block)
    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith(PREFIX) or mesh.name.startswith("P2_"):
            bpy.data.meshes.remove(mesh)
    for spk in list(bpy.data.speakers):
        if spk.name.startswith("SPK_P2_"):
            bpy.data.speakers.remove(spk)
    scene = bpy.context.scene
    if scene.sequence_editor:
        for strip in list(scene.sequence_editor.strips_all):
            if strip.name.startswith("P2_"):
                scene.sequence_editor.strips.remove(strip)


def ensure_col(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def add_box(name, x0, y0, z0, x1, y1, z1, col, material) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{PREFIX}{name}_MESH")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = ((x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5)
    col.objects.link(obj)
    mesh.materials.append(material)
    return obj


def add_cyl(name, loc, radius, depth, rot, col, material, segments=10) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{PREFIX}{name}_MESH")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius, radius2=radius, depth=depth)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.rotation_euler = rot
    col.objects.link(obj)
    mesh.materials.append(material)
    return obj


def cut_opening(wall_name: str, x0, y0, z0, x1, y1, z1) -> None:
    wall = bpy.data.objects.get(wall_name)
    if wall is None:
        raise RuntimeError(f"Missing wall {wall_name}")
    flag = f"P2_OPENING_{wall_name}"
    if wall.get(flag) == 1:
        return
    tmp_col = ensure_col(COL_GEO)
    cutter = add_box(f"{wall_name}_CUT", x0, y0, z0, x1, y1, z1, tmp_col, mat("MAT_Wall_PaintedConcrete"))
    cutter.hide_render = True
    cutter.hide_set(True)
    bpy.context.view_layer.update()
    for solver in ("EXACT", "FLOAT", "MANIFOLD"):
        # Remove leftover failed modifiers.
        for leftover in list(wall.modifiers):
            if leftover.name.startswith("P2_OPENING"):
                wall.modifiers.remove(leftover)
        mod = wall.modifiers.new("P2_OPENING", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = solver
        if hasattr(mod, "use_self"):
            mod.use_self = False
        if hasattr(mod, "use_hole_tolerant"):
            mod.use_hole_tolerant = True
        mod.object = cutter
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = wall.evaluated_get(depsgraph)
        new_mesh = bpy.data.meshes.new_from_object(eval_obj)
        if len(new_mesh.vertices) > len(wall.data.vertices):
            old = wall.data
            mats = list(old.materials)
            wall.data = new_mesh
            wall.data.materials.clear()
            for m in mats:
                wall.data.materials.append(m)
            if old.users == 0:
                bpy.data.meshes.remove(old)
            if "P2_OPENING" in wall.modifiers:
                wall.modifiers.remove(wall.modifiers["P2_OPENING"])
            break
        bpy.data.meshes.remove(new_mesh)
        wall.modifiers.remove(mod)
    else:
        bpy.data.objects.remove(cutter, do_unlink=True)
        raise RuntimeError(f"Boolean opening failed on {wall_name}")
    bpy.data.objects.remove(cutter, do_unlink=True)
    wall[flag] = 1


def room_shell(prefix, x0, y0, z0, x1, y1, z1, h, col, skip_east=False, skip_west=False, skip_south=False, skip_north=False):
    wall = mat("MAT_Wall_PaintedConcrete")
    floor = mat("MAT_Floor_IndustrialConcrete")
    ceil = mat("MAT_Ceiling_AgedConcrete")
    t = 0.20
    add_box(f"{prefix}_FLOOR", x0, y0, z0 - t, x1, y1, z0, col, floor)
    add_box(f"{prefix}_CEIL", x0, y0, h, x1, y1, h + t, col, ceil)
    if not skip_west:
        add_box(f"{prefix}_WALL_W", x0 - t, y0, z0, x0, y1, h, col, wall)
    if not skip_east:
        add_box(f"{prefix}_WALL_E", x1, y0, z0, x1 + t, y1, h, col, wall)
    if not skip_south:
        add_box(f"{prefix}_WALL_S", x0, y0 - t, z0, x1, y0, h, col, wall)
    if not skip_north:
        add_box(f"{prefix}_WALL_N", x0, y1, z0, x1, y1 + t, h, col, wall)


def finish_opening(name, x_face, y0, y1, z1, col, toward_neg_x=True):
    wall = mat("MAT_Wall_PaintedConcrete")
    steel = mat("MAT_Structure_PaintedSteel")
    jam = 0.08
    depth = 0.22 if toward_neg_x else -0.22
    x0, x1 = (x_face + depth, x_face) if toward_neg_x else (x_face, x_face + depth)
    add_box(f"{name}_JAMB_S", min(x0, x1), y0 - jam, 0.0, max(x0, x1), y0, z1 + 0.06, col, steel)
    add_box(f"{name}_JAMB_N", min(x0, x1), y1, 0.0, max(x0, x1), y1 + jam, z1 + 0.06, col, steel)
    add_box(f"{name}_LINTEL", min(x0, x1), y0 - jam, z1, max(x0, x1), y1 + jam, z1 + 0.10, col, steel)
    add_box(f"{name}_SILL", min(x0, x1), y0, 0.0, max(x0, x1), y1, 0.04, col, wall)


def add_pipe(name, a, b, dia, col, material):
    return p3.add_straight_pipe(name, a, b, dia, col, material, "P2", "PIPE_Straight")


def add_bracket(name, loc, col, along="Y"):
    steel = mat("MAT_Structure_PaintedSteel")
    if along == "Y":
        add_box(name, loc[0] - 0.04, loc[1] - 0.05, loc[2] - 0.03, loc[0] + 0.04, loc[1] + 0.05, loc[2] + 0.03, col, steel)
    else:
        add_box(name, loc[0] - 0.05, loc[1] - 0.04, loc[2] - 0.03, loc[0] + 0.05, loc[1] + 0.04, loc[2] + 0.03, col, steel)


def build_geometry() -> dict:
    geo = ensure_col(COL_GEO)
    pipe_col = ensure_col(COL_PIPE)
    prop = ensure_col(COL_PROP)
    wet = ensure_col(COL_WET)
    wall = mat("MAT_Wall_PaintedConcrete")
    pipe_a = mat("MAT_Pipe_DarkPaintedSteel")
    pipe_b = mat("MAT_Pipe_Secondary")
    steel = mat("MAT_Structure_PaintedSteel")
    galv = mat("MAT_Metal_Galvanized")
    valve = mat("MAT_Valve_IndustrialAccent")
    cab = mat("MAT_Cabinet_PaintedMetal")
    vent_m = mat("MAT_Vent_GalvanizedMetal")
    rubber = mat("MAT_Rubber_Dark")

    counts = {"boxes": 0, "pipes": 0, "props": 0}

    # Cut openings in protected shells (geometry only; materials stay).
    cut_opening("WALL.West.Shell", -1.42, OPEN_Y0, 0.0, -0.98, OPEN_Y1, OPEN_Z1)
    cut_opening("WALL.East.Shell", 0.98, EAST_OPEN_Y0, 0.0, 1.42, EAST_OPEN_Y1, 2.20)
    finish_opening("P2_WEST_OPEN", -1.10, OPEN_Y0, OPEN_Y1, OPEN_Z1, geo, True)
    finish_opening("P2_EAST_OPEN", 1.10, EAST_OPEN_Y0, EAST_OPEN_Y1, 2.20, geo, False)

    room_shell("P2_HUB", HUB_X0, HUB_Y0, 0.0, HUB_X1, HUB_Y1, 0.0, HUB_H, geo, skip_east=True, skip_north=True, skip_south=True, skip_west=True)
    # North/south walls leave the west third open into Hot / Vent corridors.
    add_box("P2_HUB_WALL_N", -3.35, HUB_Y1, 0.0, HUB_X1, HUB_Y1 + 0.20, HUB_H, geo, wall)
    add_box("P2_HUB_WALL_S", -3.35, HUB_Y0 - 0.20, 0.0, HUB_X1, HUB_Y0, HUB_H, geo, wall)
    add_box("P2_HUB_WALL_W_N", HUB_X0 - 0.20, 6.72, 0.0, HUB_X0, HUB_Y1, HUB_H, geo, wall)
    add_box("P2_HUB_WALL_W_S", HUB_X0 - 0.20, HUB_Y0, 0.0, HUB_X0, 5.68, HUB_H, geo, wall)

    room_shell("P2_HOT", HOT_X0, HOT_Y0, -HOT_DROP, HOT_X1, HOT_Y1, -HOT_DROP, 2.55, geo, skip_south=True)
    # Steps down into hot sector.
    for i, z in enumerate((0.00, -0.11, -0.22)):
        y0 = 7.55 + i * 0.18
        add_box(f"P2_HOT_STEP_{i}", HOT_X0, y0, -HOT_DROP, HOT_X1, y0 + 0.18, z, geo, mat("MAT_Floor_IndustrialConcrete"))

    room_shell("P2_VENT", VENT_X0, VENT_Y0, 0.0, VENT_X1, VENT_Y1, 0.0, 2.70, geo, skip_north=True, skip_west=True)
    add_box("P2_VENT_WALL_W", VENT_X0 - 0.20, 1.85, 0.0, VENT_X0, VENT_Y1, 2.70, geo, wall)
    room_shell("P2_DEAD", DEAD_X0, DEAD_Y0, 0.0, DEAD_X1, DEAD_Y1, 0.0, 2.55, geo, skip_east=True)
    room_shell("P2_MAINT", MAINT_X0, MAINT_Y0, 0.0, MAINT_X1, MAINT_Y1, 0.0, 2.62, geo, skip_east=True)
    finish_opening("P2_MAINT_OPEN", -5.45, 5.70, 6.70, 2.18, geo, True)
    room_shell("P2_EAST", EAST_X0, EAST_Y0, 0.0, EAST_X1, EAST_Y1, 0.0, 2.40, geo, skip_west=True)

    # Locked east dead-end door (sealed, not Clockwork).
    add_box("P2_EAST_DOOR", 3.42, 2.02, 0.04, 3.50, 2.82, 2.12, geo, cab)
    add_box("P2_EAST_DOOR_BAR", 3.40, 2.28, 0.92, 3.52, 2.56, 1.08, geo, steel)

    # Sealed gate at ventilation dead end.
    add_box("P2_DEAD_GATE", -8.52, 0.58, 0.04, -8.38, 1.72, 2.15, geo, galv)
    add_box("P2_DEAD_GATE_BAR_A", -8.54, 0.70, 0.70, -8.36, 1.60, 0.82, geo, steel)
    add_box("P2_DEAD_GATE_BAR_B", -8.54, 0.70, 1.35, -8.36, 1.60, 1.47, geo, steel)

    # Raised service platform + short stairs in hub (walk around, not through).
    add_box("P2_PLATFORM", -2.85, 6.58, 0.00, -1.55, 7.48, 0.42, geo, steel)
    add_box("P2_PLATFORM_STEP_0", -1.55, 6.58, 0.00, -1.32, 7.05, 0.14, geo, steel)
    add_box("P2_PLATFORM_STEP_1", -1.55, 6.58, 0.00, -1.32, 6.82, 0.28, geo, steel)

    # Vertical shaft (look, do not fly the camera through).
    add_box("P2_SHAFT_WALL_W", -5.45, 7.00, 2.82, -5.28, 7.55, 5.35, geo, wall)
    add_box("P2_SHAFT_WALL_E", -4.72, 7.00, 2.82, -4.55, 7.55, 5.35, geo, wall)
    add_box("P2_SHAFT_WALL_S", -5.45, 7.00, 2.82, -4.55, 7.12, 5.35, geo, wall)
    add_box("P2_SHAFT_WALL_N", -5.45, 7.43, 2.82, -4.55, 7.55, 5.35, geo, wall)
    add_box("P2_SHAFT_CEIL", -5.45, 7.00, 5.35, -4.55, 7.55, 5.50, geo, mat("MAT_Ceiling_AgedConcrete"))
    add_box("P2_SHAFT_GRATE", -5.38, 7.12, 2.80, -4.62, 7.43, 2.84, geo, galv)

    # Ladder in shaft.
    add_cyl("P2_LADDER_L", (-5.20, 7.16, 1.70), 0.018, 3.2, (0, 0, 0), prop, steel, 8)
    add_cyl("P2_LADDER_R", (-4.88, 7.16, 1.70), 0.018, 3.2, (0, 0, 0), prop, steel, 8)
    for i in range(9):
        z = 0.28 + i * 0.34
        add_cyl(f"P2_LADDER_RUNG_{i:02d}", (-5.04, 7.16, z), 0.012, 0.34, (0, math.pi * 0.5, 0), prop, steel, 6)

    # Pipe-dense hub: supported runs, elbows, a riser that forces a sidestep.
    add_pipe("P2_PIPE_HUB_PRI", (-1.25, 7.18, 2.42), (-5.20, 7.18, 2.42), 0.18, pipe_col, pipe_a)
    add_pipe("P2_PIPE_HUB_SEC", (-1.25, 5.12, 2.28), (-5.20, 5.12, 2.28), 0.11, pipe_col, pipe_b)
    add_pipe("P2_PIPE_HUB_CROSS", (-3.05, 5.05, 2.08), (-3.05, 7.40, 2.08), 0.14, pipe_col, pipe_a)
    add_pipe("P2_PIPE_RISER", (-3.05, 6.52, 0.08), (-3.05, 6.52, 2.08), 0.16, pipe_col, pipe_a)
    p3.add_elbow(
        "P2_PIPE_HUB_ELBOW",
        (-5.20, 7.18, 2.42),
        (-1.0, 0.0, 0.0),
        (0.0, 0.0, -1.0),
        0.18,
        0.18,
        pipe_col,
        pipe_a,
        "P2",
    )
    add_pipe("P2_PIPE_HUB_DROP", (-5.38, 7.18, 2.24), (-5.38, 7.18, 0.55), 0.16, pipe_col, pipe_a)
    add_cyl("P2_PIPE_RISER_VALVE", (-3.05, 6.52, 1.22), 0.11, 0.16, (math.pi * 0.5, 0, 0), pipe_col, valve, 10)
    add_cyl("P2_PIPE_HUB_JUNCTION", (-3.05, 7.18, 2.42), 0.14, 0.12, (0, math.pi * 0.5, 0), pipe_col, steel, 10)
    for x in (-1.70, -2.55, -3.40, -4.25, -5.05):
        add_bracket(f"P2_BRK_PRI_{x:.2f}", (x, 7.18, 2.58), pipe_col, "X")
        add_bracket(f"P2_BRK_SEC_{x:.2f}", (x, 5.12, 2.44), pipe_col, "X")
    add_pipe("P2_PIPE_WALL_N", (-5.28, 6.90, 1.92), (-1.35, 6.90, 1.92), 0.09, pipe_col, pipe_b)
    add_pipe("P2_PIPE_WALL_S", (-5.28, 5.05, 1.88), (-1.35, 5.05, 1.88), 0.08, pipe_col, pipe_b)

    # Hot sector pipes + condensation.
    add_pipe("P2_PIPE_HOT_A", (-3.52, 7.70, 2.18), (-3.52, 13.15, 2.18), 0.17, pipe_col, pipe_a)
    add_pipe("P2_PIPE_HOT_B", (-5.22, 7.70, 2.05), (-5.22, 13.15, 2.05), 0.13, pipe_col, pipe_a)
    add_pipe("P2_PIPE_HOT_C", (-3.70, 11.40, 1.55), (-5.10, 11.40, 1.55), 0.10, pipe_col, pipe_b)
    add_pipe("P2_PIPE_HOT_D", (-3.48, 8.20, 1.72), (-3.48, 12.90, 1.72), 0.08, pipe_col, pipe_b)
    add_cyl("P2_HOT_VALVE", (-3.52, 10.85, 2.18), 0.12, 0.18, (0, math.pi * 0.5, 0), pipe_col, valve, 10)
    add_cyl("P2_HOT_FLANGE", (-5.22, 12.40, 2.05), 0.16, 0.05, (0, 0, 0), pipe_col, steel, 10)
    add_box("P2_WET_HOT_A", -5.10, 10.40, -HOT_DROP + 0.002, -3.70, 11.20, -HOT_DROP + 0.008, wet, rubber)
    add_box("P2_WET_HOT_B", -4.95, 12.00, -HOT_DROP + 0.002, -3.85, 12.55, -HOT_DROP + 0.008, wet, rubber)
    p3.add_elbow(
        "P2_PIPE_HOT_ELBOW",
        (-3.52, 11.40, 2.18),
        (0.0, 1.0, 0.0),
        (-1.0, 0.0, 0.0),
        0.16,
        0.12,
        pipe_col,
        pipe_a,
        "P2",
    )

    # Ventilation ducts / grilles.
    add_box("P2_DUCT_MAIN", -4.55, 0.70, 2.05, -4.20, 4.70, 2.48, geo, vent_m)
    add_box("P2_DUCT_DROP", -5.42, 2.00, 1.55, -5.12, 2.35, 2.08, geo, vent_m)
    add_box("P2_VENT_GRILLE", -3.38, 1.85, 1.35, -3.34, 2.45, 1.95, geo, vent_m)
    for i, z in enumerate((1.42, 1.58, 1.74)):
        add_box(f"P2_VENT_SLAT_{i}", -3.36, 1.90, z, -3.32, 2.40, z + 0.03, geo, galv)
    add_box("P2_FAN_HOUSING", -5.42, 2.55, 1.70, -5.28, 3.15, 2.30, geo, vent_m)
    add_cyl("P2_FAN_HUB", (-5.30, 2.85, 2.00), 0.06, 0.08, (0, math.pi * 0.5, 0), prop, steel, 8)
    add_box("P2_FAN_BLADE_A", -5.36, 2.72, 1.96, -5.24, 2.98, 2.04, prop, galv)
    add_box("P2_FAN_BLADE_B", -5.33, 2.82, 1.82, -5.27, 2.88, 2.18, prop, galv)
    add_box("P2_MAINT_PANEL_VENT", -5.42, 3.40, 0.85, -5.36, 4.05, 1.55, geo, cab)
    add_box("P2_WARN_PLATE", -3.38, 3.55, 1.55, -3.34, 3.92, 1.82, prop, valve)

    # Maintenance room: sparse abandoned work.
    add_box("P2_BENCH", -8.35, 7.15, 0.00, -6.55, 7.72, 0.82, prop, cab)
    add_box("P2_BENCH_LEG_A", -8.28, 7.20, 0.00, -8.16, 7.32, 0.82, prop, steel)
    add_box("P2_BENCH_LEG_B", -6.70, 7.55, 0.00, -6.58, 7.67, 0.82, prop, steel)
    add_box("P2_SHELF", -8.48, 5.20, 0.90, -8.28, 6.55, 1.85, prop, cab)
    add_box("P2_PANEL_A", -6.05, 5.12, 0.70, -5.55, 5.18, 1.70, prop, cab)
    add_box("P2_PANEL_A_DOOR", -6.02, 5.18, 0.78, -5.72, 5.22, 1.55, prop, steel)
    add_box("P2_CART", -6.55, 6.05, 0.00, -5.85, 6.55, 0.62, prop, galv)
    add_box("P2_CART_WHEEL_A", -6.48, 6.10, 0.05, -6.40, 6.18, 0.16, prop, rubber)
    add_box("P2_CART_WHEEL_B", -5.95, 6.42, 0.05, -5.87, 6.50, 0.16, prop, rubber)
    add_cyl("P2_WRENCH", (-7.40, 7.40, 0.86), 0.018, 0.28, (0, math.pi * 0.5, 0.4), prop, steel, 6)
    add_cyl("P2_BROKEN_WHEEL", (-7.90, 7.48, 0.90), 0.07, 0.03, (math.pi * 0.5, 0.2, 0), prop, valve, 8)
    add_box("P2_MARK_STRIPE", -8.50, 6.10, 1.55, -8.48, 6.55, 1.70, prop, valve)
    add_pipe("P2_PIPE_MAINT_IN", (-8.40, 6.90, 2.20), (-5.50, 6.90, 2.20), 0.10, pipe_col, pipe_b)
    add_cyl("P2_MAINT_VALVE", (-6.80, 6.90, 2.20), 0.09, 0.12, (0, math.pi * 0.5, 0), pipe_col, valve, 8)

    # Hub wet patch under leak.
    add_box("P2_WET_HUB", -3.55, 6.70, 0.002, -2.70, 7.20, 0.008, wet, rubber)

    # Visible practical housings (not extra fill — they mark the new fixtures).
    add_box("P2_FIX_HUB", -3.70, 5.95, 2.62, -3.10, 6.45, 2.72, geo, steel)
    add_box("P2_FIX_HOT", -4.70, 10.45, 2.38, -4.10, 10.95, 2.48, geo, steel)
    add_box("P2_FIX_HOT_FAR", -4.70, 11.95, 2.34, -4.10, 12.45, 2.44, geo, steel)
    add_box("P2_FIX_VENT", -4.70, 2.10, 2.58, -4.10, 2.60, 2.68, geo, galv)
    add_box("P2_FIX_MAINT", -7.25, 6.28, 2.42, -6.75, 6.68, 2.52, geo, steel)

    counts["pipes"] = len(pipe_col.objects)
    counts["props"] = len(prop.objects)
    counts["boxes"] = len(geo.objects)
    return counts


def build_lights() -> list[str]:
    col = ensure_col(COL_LIGHT)
    names = []
    for spec in P2_LIGHTS:
        data = bpy.data.lights.new(spec["name"], "AREA")
        data.energy = spec["energy"]
        data.color = spec["color"]
        data.shape = "RECTANGLE"
        data.size = spec["size"]
        data.size_y = spec["size"] * 0.55
        obj = bpy.data.objects.new(spec["name"], data)
        obj.location = spec["loc"]
        obj.rotation_euler = spec.get("rot", (0.0, 0.0, 0.0))
        col.objects.link(obj)
        names.append(spec["name"])
    return names


def add_steam_socket(spec, col) -> dict:
    mat_vol = p1.steam_material(f"MAT_P2_{spec['name']}", spec["peak_density"], spec["seed"])
    obj = p1.add_steam_volume(spec["name"], mat_vol, col)
    source = Vector(spec["source"])
    aim = Vector(spec["aim"])
    empty = bpy.data.objects.new(f"{spec['name']}_SOURCE", None)
    empty.location = source
    empty.rotation_euler = (aim - source).normalized().to_track_quat("Z", "Y").to_euler()
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.08
    col.objects.link(empty)
    obj.parent = empty
    start, peak, hold, end = spec["keys"]
    mul = spec.get("scale", (1.0, 1.0, 1.0))
    scale_keys = (
        (1, (0.07 * mul[0], 0.06 * mul[1], 0.14 * mul[2])),
        (start, (0.12 * mul[0], 0.10 * mul[1], 0.28 * mul[2])),
        (peak, (0.36 * mul[0], 0.48 * mul[1], 1.32 * mul[2])),
        (hold, (0.48 * mul[0], 0.64 * mul[1], 1.62 * mul[2])),
        (end, (0.58 * mul[0], 0.80 * mul[1], 1.90 * mul[2])),
        (FRAME_END, (0.58 * mul[0], 0.80 * mul[1], 1.90 * mul[2])),
    )
    obj.animation_data_clear()
    for frame, scale in scale_keys:
        obj.scale = scale
        drift = (frame - start) / max(end - start, 1)
        obj.location = (0.03 * spec["seed"], -0.02 * spec["seed"] - 0.03 * drift, scale[2] * 0.48)
        obj.keyframe_insert(data_path="scale", frame=frame)
        obj.keyframe_insert(data_path="location", frame=frame)
    p1.soften_action(obj)
    p1.key_density(mat_vol, 1, 0.0)
    p1.key_density(mat_vol, start, 0.0)
    p1.key_density(mat_vol, peak, spec["peak_density"])
    p1.key_density(mat_vol, hold, spec["peak_density"] * 0.70)
    p1.key_density(mat_vol, end, 0.0)
    p1.key_density(mat_vol, FRAME_END, 0.0)
    p1.animate_steam_advection(mat_vol, start, end, spec["seed"])
    return {"name": spec["name"], "source": spec["source"], "frames": spec["keys"]}


def build_steam() -> dict:
    col = ensure_col(COL_STEAM)
    return {"sockets": [add_steam_socket(spec, col) for spec in P2_STEAM]}


def build_review_camera() -> dict:
    col = ensure_col(COL_CAM)
    cam_data = bpy.data.cameras.new(REVIEW_CAM)
    cam_data.lens = 32.0
    cam_data.clip_start = 0.08
    cam_data.clip_end = 130.0
    cam = bpy.data.objects.new(REVIEW_CAM, cam_data)
    tgt = bpy.data.objects.new(REVIEW_TARGET, None)
    tgt.empty_display_type = "PLAIN_AXES"
    tgt.empty_display_size = 0.12
    col.objects.link(cam)
    col.objects.link(tgt)
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    for frame, loc, look in ROUTE:
        cam.location = loc
        tgt.location = look
        cam.keyframe_insert("location", frame=frame)
        tgt.keyframe_insert("location", frame=frame)
    p1.soften_action(cam)
    p1.soften_action(tgt)
    return {"camera": REVIEW_CAM, "frames": FRAME_END, "keys": len(ROUTE)}


P2_SPEAKERS = (
    dict(name="SPK_P2_PIPE_DENSE", loc=(-3.05, 6.20, 1.55), sound="p2_pipe_dense_rumble.wav", vol=0.62, dist=1.3, dmax=7.5),
    dict(name="SPK_P2_HOT_STEAM", loc=(-4.40, 10.90, 1.40), sound="p2_hot_steam.wav", vol=0.58, dist=1.1, dmax=8.0),
    dict(name="SPK_P2_HOT_TICK", loc=(-3.52, 10.85, 2.18), sound="p2_thermal_tick.wav", vol=0.40, dist=1.0, dmax=7.0),
    dict(name="SPK_P2_VENT_FAN", loc=(-5.30, 2.85, 2.00), sound="p2_vent_fan.wav", vol=0.55, dist=1.2, dmax=8.5),
    dict(name="SPK_P2_MAINT_HUM", loc=(-6.80, 6.40, 1.20), sound="p2_maint_hum.wav", vol=0.32, dist=0.9, dmax=6.0),
    dict(name="SPK_P2_SHAFT", loc=(-5.00, 7.22, 3.40), sound="p2_shaft_reverb.wav", vol=0.48, dist=1.4, dmax=7.5),
)


def build_audio() -> dict:
    col = ensure_col(COL_AUDIO)
    placed = []
    for spec in P2_SPEAKERS:
        path = ASSET_DIR / spec["sound"]
        if not path.exists():
            continue
        existing = bpy.data.sounds.get(path.name)
        if existing is None:
            sound = bpy.data.sounds.load(str(path))
            sound.name = path.name
            try:
                sound.pack()
            except Exception:
                pass
        else:
            sound = existing
        p1.add_speaker(spec["name"], spec["loc"], sound, spec["vol"], spec["dist"], spec["dmax"], col)
        placed.append(spec["name"])
    return {"speakers": placed}


def freeze_check(before: dict) -> dict:
    after = {
        "walk": p105.inspect_keys(bpy.data.objects[WALK_CAM]),
        "target": p105.inspect_keys(bpy.data.objects[WALK_TARGET]),
        "world": p1.apply_heat_atmosphere.__name__,
    }
    world = bpy.context.scene.world
    bg = world.node_tree.nodes.get("Background") if world and world.node_tree else None
    vol = world.node_tree.nodes.get("P10_Volume") if world and world.node_tree else None
    strength = bg.inputs[1].default_value if bg else -1
    density = vol.inputs["Density"].default_value if vol and "Density" in vol.inputs else -1
    fill = bool(bpy.data.objects.get("LIGHT_P1_FILL") or bpy.data.objects.get("LIGHT_P1_FILL_C"))
    steam = [o.name for o in bpy.data.objects if o.name.startswith("STEAM_SOCKET_") and o.type == "MESH"]
    return {
        "walk_unchanged": before["walk"] == p105.inspect_keys(bpy.data.objects[WALK_CAM]),
        "target_unchanged": before["target"] == p105.inspect_keys(bpy.data.objects[WALK_TARGET]),
        "world_strength": round(strength, 3),
        "world_volume": round(density, 4),
        "fill_present": fill,
        "phase1_steam": steam,
        "walk_keys": before["walk"],
    }


def snapshot() -> dict:
    return {
        "objects": len(bpy.data.objects),
        "materials": len(bpy.data.materials),
        "lights": len([o for o in bpy.data.objects if o.type == "LIGHT"]),
        "meshes": len(bpy.data.meshes),
    }


def apply_phase2() -> dict:
    before_cam = {
        "walk": p105.inspect_keys(bpy.data.objects[WALK_CAM]),
        "target": p105.inspect_keys(bpy.data.objects[WALK_TARGET]),
    }
    before = snapshot()
    clear_phase2()
    geo = build_geometry()
    lights = build_lights()
    steam = build_steam()
    cam = build_review_camera()
    audio = build_audio()
    freeze = freeze_check(before_cam)
    # Restore Phase 1 look in case any import mutated world (heat_atmosphere is not called here).
    p1.zero_world_volume()
    bpy.context.scene["PHASE2_SPATIAL"] = 1
    after = snapshot()
    report = {
        "checkpoint": str(CHECKPOINT),
        "before": before,
        "after": after,
        "geometry": geo,
        "lights": lights,
        "steam": steam,
        "camera": cam,
        "audio": audio,
        "freeze": freeze,
        "phase1_protected": freeze["walk_unchanged"] and freeze["target_unchanged"] and not freeze["fill_present"] and freeze["world_volume"] == 0.0,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "phase2_setup.json").write_text(json.dumps(report, indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    return report


def configure_review(scene: bpy.types.Scene) -> None:
    p1.configure_eevee_phase1(scene)
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    cam = bpy.data.objects.get(REVIEW_CAM)
    if cam is None:
        raise RuntimeError("CAM_P2_REVIEW missing")
    scene.camera = cam
    scene.render.filepath = str(FRAME_DIR / "frame_")


def gate_frames() -> list[int]:
    # 0 / 25 / 50 / 75 / 100 plus dedicated hot and vent.
    return [1, 180, 280, 360, 400, 630, 720]


def render_stills() -> list[Path]:
    scene = bpy.context.scene
    configure_review(scene)
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    labels = {
        1: "begin",
        180: "pipe_dense_25",
        280: "hot_steam",
        360: "mid_50",
        400: "ventilation",
        630: "maintenance_75",
        720: "ending",
    }
    paths = []
    for frame in gate_frames():
        scene.frame_set(frame)
        label = labels.get(frame, f"f{frame:04d}")
        path = STILL_DIR / f"phase2_gate_{label}_f{frame:04d}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        try:
            shutil.copy2(path, ARTIFACT_DIR / path.name)
        except OSError:
            pass
        paths.append(path)
    return paths


def mixdown_audio(dest: Path) -> Path:
    mix = SCRIPT_DIR / "mix_phase2_audio.py"
    subprocess.check_call(["python3", str(mix)])
    generated = OUTPUT_DIR / "phase2_mixdown.wav"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if generated != dest:
        shutil.copy2(generated, dest)
    return dest


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
    configure_review(scene)
    if FRAME_DIR.exists():
        shutil.rmtree(FRAME_DIR)
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    bpy.ops.render.render(animation=True)
    elapsed = time.time() - t0
    frames = sorted(FRAME_DIR.glob("frame_*.png"))
    audio_path = OUTPUT_DIR / "phase2_mixdown.wav"
    mixdown_audio(audio_path)
    mp4 = OUTPUT_DIR / "phase2_spatial_expansion_review.mp4"
    encode_mp4(FRAME_DIR, audio_path, mp4)
    artifact = ARTIFACT_DIR / "phase2_spatial_expansion_review.mp4"
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
        "artifact": str(artifact) if artifact else None,
        "audio": str(audio_path),
    }


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mode = parse_mode()
    if mode == "setup":
        report = apply_phase2()
        print(json.dumps({"mode": mode, "phase1_protected": report["phase1_protected"], "freeze": report["freeze"], "geometry": report["geometry"]}, indent=2))
        return
    if bpy.context.scene.get("PHASE2_SPATIAL") != 1:
        apply_phase2()
    if mode == "stills":
        paths = render_stills()
        print("stills", [str(p) for p in paths])
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
        return
    if mode == "render":
        result = render_animation()
        (OUTPUT_DIR / "phase2_render.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
