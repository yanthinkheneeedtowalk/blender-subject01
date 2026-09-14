#!/usr/bin/env python3
"""Phase 1 — Backrooms Level 2 utility corridor blockout.

ONE continuous 24 m straight corridor. No rooms, branches, doors, props,
detailed pipes, final materials, or final lighting.

Subtle three-zone scale:
  A normal → B compression → C deep / isolated

  blender -b hallway.blend --python scripts/build_hallway_phase1.py -- --stills
  blender -b hallway.blend --python scripts/build_hallway_phase1.py -- --no-render
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
STILL_DIR = ROOT / "renders" / "hallway_phase1"

LENGTH = 24.0
WALL_T = 0.20
FLOOR_T = 0.20
CEIL_T = 0.20
EYE_Z = 1.68

# Interior targets (metres). Transitions are NOT exactly on 8 / 16.
ZONE_A = dict(y0=0.00, y1=7.70, width=2.20, height=3.00)
ZONE_B = dict(y0=8.90, y1=15.50, width=2.05, height=2.74)
ZONE_C = dict(y0=16.70, y1=24.00, width=2.20, height=2.93)
# Structural transitions occupy the gaps between zone interiors.
TRANS_AB = dict(y0=7.70, y1=8.90)
TRANS_BC = dict(y0=15.50, y1=16.70)


def parse_args() -> dict:
    mode = "stills"
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--no-render" in argv:
        mode = "check"
    elif "--playblast" in argv:
        mode = "playblast"
    return {"mode": mode}


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for blocks in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.collections,
        bpy.data.node_groups,
        bpy.data.images,
        bpy.data.curves,
    ):
        for item in list(blocks):
            if getattr(item, "name", "") in {"Render Result", "Viewer Node"}:
                continue
            try:
                blocks.remove(item)
            except Exception:
                pass


def new_col(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def mat_rgb(name: str, rgb: tuple[float, float, float], rough: float = 0.78) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*rgb, 1.0)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = rough
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


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
    obj.data.materials.append(mat)
    return obj


def half(width: float) -> float:
    return width * 0.5


def build_corridor(col, mats):
    concrete, struct, floor, ceil = mats
    ha, hb, hc = half(ZONE_A["width"]), half(ZONE_B["width"]), half(ZONE_C["width"])
    xa, xb, xc = ha, hb, hc  # 1.10, 1.025, 1.10
    outer = xa + WALL_T  # 1.30

    # Continuous floor and outer shell — one volume, not three rooms.
    add_box("FLOOR", -outer, 0.0, -FLOOR_T, outer, LENGTH, 0.0, col, floor)
    add_box("WALL.West.Shell", -outer, 0.0, 0.0, -xa, LENGTH, ZONE_A["height"] + 0.05, col, concrete)
    add_box("WALL.East.Shell", xa, 0.0, 0.0, outer, LENGTH, ZONE_A["height"] + 0.05, col, concrete)
    add_box("CEIL.Shell", -outer, 0.0, ZONE_A["height"], outer, LENGTH, ZONE_A["height"] + CEIL_T, col, ceil)
    add_box("WALL.Start", -outer, -WALL_T, 0.0, outer, 0.0, ZONE_A["height"] + 0.05, col, concrete)
    add_box("WALL.End", -outer, LENGTH, 0.0, outer, LENGTH + WALL_T, ZONE_A["height"] + 0.05, col, concrete)

    # Zone B wall offsets — 7.5 cm per side. Insets tuck against the piers
    # so there is no 10 cm full-width pocket at either transition.
    pier_d = 0.11
    pier_ab_y0, pier_ab_y1 = TRANS_AB["y0"] + 0.15, TRANS_AB["y1"] - 0.10
    pier_bc_y0, pier_bc_y1 = TRANS_BC["y0"] + 0.10, TRANS_BC["y1"] - 0.15
    add_box(
        "WALL.West.InsetB",
        -xa, pier_ab_y1 - 0.04, 0.0,
        -xb, pier_bc_y0 + 0.04, ZONE_B["height"],
        col, concrete,
    )
    add_box(
        "WALL.East.InsetB",
        xb, pier_ab_y1 - 0.04, 0.0,
        xa, pier_bc_y0 + 0.04, ZONE_B["height"],
        col, concrete,
    )

    # Piers at A→B: slightly proud of the inset so the jog reads as a column line.
    add_box("PIER.AB.West", -xa, pier_ab_y0, 0.0, -xa + pier_d, pier_ab_y1, ZONE_A["height"], col, struct)
    add_box("PIER.AB.East", xa - pier_d, pier_ab_y0, 0.0, xa, pier_ab_y1, ZONE_A["height"], col, struct)
    # Transverse beam then soffit — ceiling drops under a beam, not a knife-edge.
    add_box("BEAM.AB", -xa, TRANS_AB["y0"] + 0.25, ZONE_B["height"] - 0.04, xa, TRANS_AB["y1"] - 0.15, ZONE_A["height"], col, struct)
    add_box(
        "CEIL.SoffitB",
        -xb, ZONE_B["y0"] - 0.15, ZONE_B["height"],
        xb, ZONE_B["y1"] + 0.20, ZONE_A["height"],
        col, ceil,
    )

    # Piers + beam at B→C: walls step back out, soffit ends, ceiling rises to 2.93.
    add_box("PIER.BC.West", -xa, pier_bc_y0, 0.0, -xa + pier_d, pier_bc_y1, ZONE_A["height"], col, struct)
    add_box("PIER.BC.East", xa - pier_d, pier_bc_y0, 0.0, xa, pier_bc_y1, ZONE_A["height"], col, struct)
    add_box("BEAM.BC", -xa, TRANS_BC["y0"] + 0.20, ZONE_C["height"] - 0.06, xa, TRANS_BC["y1"] - 0.20, ZONE_A["height"], col, struct)
    add_box(
        "CEIL.SoffitC",
        -xc, ZONE_C["y0"] - 0.20, ZONE_C["height"],
        xc, LENGTH, ZONE_A["height"],
        col, ceil,
    )
    # Shared beam language so A / C are not a featureless tube vs a second room.
    # Zone A ribs stay shallow under the 3.00 m soffit; Zone C sits under 2.93 m.
    add_box("BEAM.A.01", -xa, 2.55, 2.88, xa, 2.78, ZONE_A["height"], col, struct)
    add_box("BEAM.A.02", -xa, 5.35, 2.88, xa, 5.58, ZONE_A["height"], col, struct)
    add_box("BEAM.C.01", -xc, 19.15, ZONE_C["height"] - 0.10, xc, 19.38, ZONE_A["height"], col, struct)
    # Far-end header: same language as other beams, not a new room.
    add_box("BEAM.End", -xc, LENGTH - 0.55, ZONE_C["height"] - 0.05, xc, LENGTH - 0.22, ZONE_A["height"], col, struct)


def add_even_lights(col):
    """Identical fixtures along the run. Lighting must not sell the zones."""
    for i, y in enumerate((2.0, 6.0, 10.0, 14.0, 18.0, 22.0)):
        data = bpy.data.lights.new(f"LIGHT.Utility.{i+1:02d}", "AREA")
        data.energy = 180.0
        data.size = 0.55
        data.color = (1.0, 0.97, 0.92)
        obj = bpy.data.objects.new(f"LIGHT.Utility.{i+1:02d}", data)
        obj.location = (0.0, y, 2.62)
        obj.rotation_euler = (math.radians(180.0), 0.0, 0.0)
        col.objects.link(obj)


def add_inspect_camera(col) -> bpy.types.Object:
    data = bpy.data.cameras.new("CAM_INSPECT")
    data.lens = 32.0
    data.sensor_width = 36.0
    data.sensor_fit = "HORIZONTAL"
    data.clip_start = 0.08
    data.clip_end = 40.0
    cam = bpy.data.objects.new("CAM_INSPECT", data)
    cam.location = (0.0, 1.40, EYE_Z)
    cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    col.objects.link(cam)
    bpy.context.scene.camera = cam
    # Scrub path along the corridor at eye height, looking down +Y.
    for y, frame in ((1.40, 1), (4.50, 50), (8.20, 90), (12.00, 140), (16.20, 185), (20.50, 230), (22.80, 250)):
        cam.location = (0.0, y, EYE_Z)
        cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        cam.keyframe_insert("location", frame=frame)
        cam.keyframe_insert("rotation_euler", frame=frame)
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 250
    bpy.context.scene.render.fps = 24
    cam.location = (0.0, 1.40, EYE_Z)
    return cam


def look_plus_y():
    return Vector((0.0, 1.0, 0.0))


def measure_station(scene, cam, y: float) -> dict:
    dg = bpy.context.evaluated_depsgraph_get()
    origin = Vector((0.0, y, EYE_Z))
    cam.location = origin
    cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    scene.frame_set(1)
    dg.update()
    hits = {}
    rays = {
        "left": Vector((-1, 0, 0)),
        "right": Vector((1, 0, 0)),
        "up": Vector((0, 0, 1)),
        "down": Vector((0, 0, -1)),
        "fwd": Vector((0, 1, 0)),
    }
    for key, direction in rays.items():
        hit, loc, *_rest = scene.ray_cast(dg, origin, direction)
        hits[key] = (loc - origin).length if hit else None
    width = None
    height = None
    if hits["left"] is not None and hits["right"] is not None:
        width = hits["left"] + hits["right"]
    if hits["up"] is not None and hits["down"] is not None:
        height = hits["up"] + hits["down"]
    return {
        "y": y,
        "width": width,
        "ceiling": hits["up"],
        "floor": hits["down"],
        "height": height,
        "fwd": hits["fwd"],
    }


def print_scale(scene, cam):
    stations = (
        ("A mid", 4.00),
        ("A→B beam", 8.20),
        ("B mid", 12.20),
        ("B→C beam", 16.20),
        ("C mid", 20.00),
        ("C deep", 22.50),
    )
    print("=== SPATIAL SCALE (raycast from x=0, z=1.68) ===")
    rows = []
    lines = [
        "SPATIAL SCALE TABLE — raycast from x=0, z=1.68 m",
        "Zone interiors (authored):",
        f"  Zone A  y={ZONE_A['y0']:.2f}–{ZONE_A['y1']:.2f}  length={ZONE_A['y1']-ZONE_A['y0']:.2f}  width={ZONE_A['width']:.2f}  ceiling={ZONE_A['height']:.2f}",
        f"  Trans AB y={TRANS_AB['y0']:.2f}–{TRANS_AB['y1']:.2f}  length={TRANS_AB['y1']-TRANS_AB['y0']:.2f}  (piers + beam + soffit start)",
        f"  Zone B  y={ZONE_B['y0']:.2f}–{ZONE_B['y1']:.2f}  length={ZONE_B['y1']-ZONE_B['y0']:.2f}  width={ZONE_B['width']:.2f}  ceiling={ZONE_B['height']:.2f}",
        f"  Trans BC y={TRANS_BC['y0']:.2f}–{TRANS_BC['y1']:.2f}  length={TRANS_BC['y1']-TRANS_BC['y0']:.2f}  (piers + beam + soffit rise)",
        f"  Zone C  y={ZONE_C['y0']:.2f}–{ZONE_C['y1']:.2f}  length={ZONE_C['y1']-ZONE_C['y0']:.2f}  width={ZONE_C['width']:.2f}  ceiling={ZONE_C['height']:.2f}",
        "",
        "Measured stations:",
    ]
    for label, y in stations:
        m = measure_station(scene, cam, y)
        rows.append((label, m))
        w = f"{m['width']:.3f}" if m["width"] else "—"
        h = f"{m['height']:.3f}" if m["height"] else "—"
        c = f"{m['ceiling']:.3f}" if m["ceiling"] else "—"
        line = f"  {label:12s} y={y:5.2f}  width={w}  height={h}  eye-to-ceil={c}"
        print(line)
        lines.append(line)
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    (STILL_DIR / "spatial_scale.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", STILL_DIR / "spatial_scale.txt")
    return rows


STILLS = (
    (1.60, "01_zone_a_entry", 0.0),
    (4.20, "02_zone_a_mid", 0.0),
    (7.40, "03_trans_ab_approach", 2.0),
    (8.35, "04_trans_ab_beam", 4.0),
    (10.40, "05_zone_b_start", 2.0),
    (12.20, "06_zone_b_mid", 3.0),
    (15.20, "07_trans_bc_approach", 3.0),
    (16.30, "08_trans_bc_beam", 2.0),
    (19.20, "09_zone_c_mid", 0.0),
    (22.40, "10_zone_c_vanishing", 1.0),
)


def render_stills(scene, cam):
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 90
    scene.render.use_compositing = False
    paths = []
    for y, name, pitch in STILLS:
        cam.location = (0.0, y, EYE_Z)
        cam.rotation_euler = (math.radians(90.0 - pitch), 0.0, 0.0)
        path = STILL_DIR / f"{name}.jpg"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print("still", path)
        paths.append(path)
    # Reset inspect cam to the start, looking down the hall.
    cam.location = (0.0, 1.40, EYE_Z)
    cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    return paths


def render_walk(scene, cam):
    """~10 s first-person walk at 24 fps along the 24 m corridor."""
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    out = STILL_DIR / "phase1_walk.mp4"
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 250
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.filepath = str(out)
    scene.render.use_compositing = False
    cam.location = (0.0, 1.40, EYE_Z)
    cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    bpy.ops.render.render(animation=True)
    print("walk", out)
    return out


def configure_scene(scene):
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    world = bpy.data.worlds.new("WORLD.Hallway")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.12, 0.12, 0.13, 1.0)
        bg.inputs[1].default_value = 0.35


def main():
    args = parse_args()
    clear_scene()
    scene = bpy.context.scene
    configure_scene(scene)
    col = new_col("HALLWAY_PHASE1")
    mats = (
        mat_rgb("MAT.Wall", (0.42, 0.41, 0.39), 0.82),
        mat_rgb("MAT.Struct", (0.34, 0.33, 0.31), 0.74),
        mat_rgb("MAT.Floor", (0.28, 0.27, 0.25), 0.86),
        mat_rgb("MAT.Ceil", (0.48, 0.47, 0.45), 0.80),
    )
    build_corridor(col, mats)
    add_even_lights(col)
    cam = add_inspect_camera(col)
    print_scale(scene, cam)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    if args["mode"] in {"stills", "playblast"}:
        render_stills(scene, cam)
        if args["mode"] == "playblast":
            render_walk(scene, cam)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
