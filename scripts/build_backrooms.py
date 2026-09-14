#!/usr/bin/env python3
"""Backrooms Level 0 — small abandoned office, real-world metres.

  blender -b --python scripts/build_backrooms.py -- --fast
  blender -b --python scripts/build_backrooms.py -- --no-render

Non-destructive source of truth is this script: walls are solid 0.20 m
boxes (never single-sided planes). Openings are separate jamb / lintel
pieces so width and height stay editable. Scale is applied (1,1,1).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "backrooms.blend"
RENDER_DIR = ROOT / "renders"
WALLPAPER_PNG = ROOT / "reference" / "backrooms_wallpaper.png"
LAYOUT_PNG = ROOT / "reference" / "backrooms_layout.png"

# Building envelope and structure (metres).
SIZE_X = 12.0
SIZE_Y = 10.0
WALL_T = 0.20
FLOOR_T = 0.20
CEIL_T = 0.15
ROOM_H = 2.70  # interior clear height
ORIGIN = Vector((-SIZE_X * 0.5, -SIZE_Y * 0.5, 0.0))  # SW corner in world XY


def W(x: float, y: float, z: float = 0.0) -> Vector:
    return ORIGIN + Vector((x, y, z))


def parse_args() -> dict:
    args = {"samples": 32, "resolution": (1280, 720), "render": True, "fast": False}
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    i = 0
    while i < len(argv):
        if argv[i] == "--fast":
            args["fast"] = True
            args["samples"] = 16
        elif argv[i] == "--no-render":
            args["render"] = False
        elif argv[i] == "--samples" and i + 1 < len(argv):
            args["samples"] = int(argv[i + 1])
            i += 1
        i += 1
    return args


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


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def srgb(r: float, g: float, b: float, a: float = 1.0) -> tuple[float, float, float, float]:
    def f(x: float) -> float:
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    return (f(r), f(g), f(b), a)


def apply_scale(obj: bpy.types.Object) -> None:
    sx, sy, sz = obj.scale
    obj.data.transform(Matrix.Diagonal((sx, sy, sz, 1.0)))
    obj.scale = (1.0, 1.0, 1.0)
    obj.data.update()


def fix_normals(obj: bpy.types.Object) -> None:
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def add_box(
    name: str,
    x0: float,
    y0: float,
    z0: float,
    x1: float,
    y1: float,
    z1: float,
    col: bpy.types.Collection,
    mat: bpy.types.Material | None = None,
) -> bpy.types.Object:
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if z1 < z0:
        z0, z1 = z1, z0
    sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
    center = W((x0 + x1) * 0.5, (y0 + y1) * 0.5, (z0 + z1) * 0.5)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    obj.location = center
    obj.scale = (sx, sy, sz)
    apply_scale(obj)
    fix_normals(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    return obj


def wall_opening_x(
    name: str,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    open_x0: float,
    open_x1: float,
    open_z1: float,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    z0: float = 0.0,
    z1: float = ROOM_H,
) -> None:
    """Wall spanning X, thickness in Y, with a centred-height opening."""
    add_box(f"{name}.JambL", x0, y0, z0, open_x0, y1, z1, col, mat)
    add_box(f"{name}.JambR", open_x1, y0, z0, x1, y1, z1, col, mat)
    add_box(f"{name}.Lintel", open_x0, y0, open_z1, open_x1, y1, z1, col, mat)


def wall_opening_y(
    name: str,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    open_y0: float,
    open_y1: float,
    open_z1: float,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    z0: float = 0.0,
    z1: float = ROOM_H,
) -> None:
    """Wall spanning Y, thickness in X, with an opening."""
    add_box(f"{name}.JambS", x0, y0, z0, x1, open_y0, z1, col, mat)
    add_box(f"{name}.JambN", x0, open_y1, z0, x1, y1, z1, col, mat)
    add_box(f"{name}.Lintel", x0, open_y0, open_z1, x1, open_y1, z1, col, mat)


def make_wallpaper_image() -> bpy.types.Image:
    """Tileable yellow damask-ish print, ~0.45 m repeat on the wall."""
    n = 1024
    img = bpy.data.images.new("WallpaperTile", n, n, alpha=False)
    pixels = [0.0] * (n * n * 4)
    tiles = 4
    for y in range(n):
        for x in range(n):
            u = (x / n) * tiles
            v = (y / n) * tiles
            fu, fv = u - math.floor(u), v - math.floor(v)
            # Tileable trig damask.
            d1 = abs(math.sin(fu * math.pi * 2) * math.sin(fv * math.pi * 2))
            d2 = abs(math.sin((fu + fv) * math.pi * 2) * math.sin((fu - fv) * math.pi * 2))
            cx, cy = fu - 0.5, fv - 0.5
            diamond = abs(cx) + abs(cy)
            motif = 0.55 * d1 + 0.25 * d2 + 0.20 * (1.0 if diamond < 0.18 else 0.0)
            motif = max(0.0, min(1.0, motif))
            # Paper yellow / printed ochre.
            r = 0.78 - 0.16 * motif
            g = 0.68 - 0.18 * motif
            b = 0.40 - 0.10 * motif
            i = (y * n + x) * 4
            pixels[i : i + 4] = [r, g, b, 1.0]
    img.pixels = pixels
    img.pack()
    WALLPAPER_PNG.parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(WALLPAPER_PNG)
    img.file_format = "PNG"
    img.save()
    return img


def new_mat(name: str) -> tuple[bpy.types.Material, bpy.types.NodeTree]:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return mat, nt


def mat_wallpaper(tile: bpy.types.Image, space: bpy.types.Object) -> bpy.types.Material:
    mat, nt = new_mat("Wallpaper")
    nodes, links = nt.nodes, nt.links
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (720, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (440, 0)
    bsdf.inputs["Roughness"].default_value = 0.72
    tex = nodes.new("ShaderNodeTexImage")
    tex.location = (-40, 80)
    tex.image = tile
    tex.interpolation = "Smart"
    tex.projection = "BOX"
    tex.projection_blend = 0.12
    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (-520, 80)
    coord.object = space
    mapn = nodes.new("ShaderNodeMapping")
    mapn.location = (-300, 80)
    mapn.inputs["Scale"].default_value = (1.0 / 0.45, 1.0 / 0.45, 1.0 / 0.45)
    dirt = nodes.new("ShaderNodeTexNoise")
    dirt.location = (-40, -220)
    dirt.inputs["Scale"].default_value = 3.4
    dirt.inputs["Detail"].default_value = 8.0
    dirt.inputs["Roughness"].default_value = 0.55
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (160, -220)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.55, 0.48, 0.28, 1.0)
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    mix = nodes.new("ShaderNodeMix")
    mix.location = (240, 40)
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.22
    bump = nodes.new("ShaderNodeBump")
    bump.location = (240, -80)
    bump.inputs["Strength"].default_value = 0.08
    links.new(coord.outputs["Object"], mapn.inputs["Vector"])
    links.new(mapn.outputs["Vector"], tex.inputs["Vector"])
    links.new(coord.outputs["Object"], dirt.inputs["Vector"])
    links.new(dirt.outputs["Fac"], ramp.inputs["Fac"])
    links.new(tex.outputs["Color"], mix.inputs["A"])
    links.new(ramp.outputs["Color"], mix.inputs["B"])
    links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def mat_carpet() -> bpy.types.Material:
    mat, nt = new_mat("Carpet")
    nodes, links = nt.nodes, nt.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (360, 0)
    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (-560, 0)
    n1 = nodes.new("ShaderNodeTexNoise")
    n1.location = (-340, 120)
    n1.inputs["Scale"].default_value = 28.0
    n1.inputs["Detail"].default_value = 11.0
    n1.inputs["Roughness"].default_value = 0.75
    n2 = nodes.new("ShaderNodeTexNoise")
    n2.location = (-340, -80)
    n2.inputs["Scale"].default_value = 4.5
    n2.inputs["Detail"].default_value = 6.0
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-80, 80)
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = srgb(0.22, 0.16, 0.08)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = srgb(0.50, 0.40, 0.22)
    wet = nodes.new("ShaderNodeValToRGB")
    wet.location = (-80, -160)
    wet.color_ramp.elements[0].position = 0.62
    wet.color_ramp.elements[0].color = (0.95, 0.95, 0.95, 1.0)
    wet.color_ramp.elements[1].position = 0.86
    wet.color_ramp.elements[1].color = (0.28, 0.28, 0.28, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.location = (140, -40)
    bump.inputs["Strength"].default_value = 0.35
    links.new(coord.outputs["Object"], n1.inputs["Vector"])
    links.new(coord.outputs["Object"], n2.inputs["Vector"])
    links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    links.new(n2.outputs["Fac"], wet.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(n1.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(wet.outputs["Color"], bsdf.inputs["Roughness"])
    if "Coat Weight" in bsdf.inputs:
        links.new(n2.outputs["Fac"], bsdf.inputs["Coat Weight"])
        bsdf.inputs["Coat Roughness"].default_value = 0.22
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.18
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def mat_ceiling() -> bpy.types.Material:
    mat, nt = new_mat("CeilingTiles")
    nodes, links = nt.nodes, nt.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (420, 0)
    bsdf.inputs["Roughness"].default_value = 0.88
    coord = nodes.new("ShaderNodeTexCoord")
    brick = nodes.new("ShaderNodeTexBrick")
    brick.location = (-80, 40)
    brick.inputs["Scale"].default_value = 1.0 / 0.60
    brick.inputs["Mortar Size"].default_value = 0.018
    brick.inputs["Color1"].default_value = srgb(0.78, 0.75, 0.68)
    brick.inputs["Color2"].default_value = srgb(0.72, 0.70, 0.62)
    brick.inputs["Mortar"].default_value = srgb(0.42, 0.40, 0.36)
    stain = nodes.new("ShaderNodeTexNoise")
    stain.inputs["Scale"].default_value = 2.8
    stain.inputs["Detail"].default_value = 8.0
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.18
    mix.inputs["B"].default_value = srgb(0.62, 0.58, 0.48)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    links.new(coord.outputs["Object"], brick.inputs["Vector"])
    links.new(coord.outputs["Object"], stain.inputs["Vector"])
    links.new(brick.outputs["Color"], mix.inputs["A"])
    links.new(stain.outputs["Fac"], mix.inputs["Factor"])
    links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    links.new(brick.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def mat_housing() -> bpy.types.Material:
    mat, nt = new_mat("LightHousing")
    nodes = nt.nodes
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = srgb(0.82, 0.82, 0.78)
    bsdf.inputs["Roughness"].default_value = 0.42
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.35
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def mat_emitter() -> bpy.types.Material:
    mat, nt = new_mat("FluorescentTube")
    nodes = nt.nodes
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    # Cool white. Yellow walls bounce it into a sickly yellow-green.
    emit.inputs["Color"].default_value = srgb(0.86, 0.94, 1.0)
    emit.inputs["Strength"].default_value = 28.0
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def add_world() -> None:
    world = bpy.data.worlds.new("Void")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bg.inputs["Strength"].default_value = 0.0
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def build_structure(mats: dict, cols: dict) -> None:
    wcol, fcol, ccol = cols["Walls"], cols["Floor"], cols["Ceiling"]
    wall, core = mats["wallpaper"], mats["core"]
    z1 = ROOM_H

    add_box("Floor", 0.0, 0.0, -FLOOR_T, SIZE_X, SIZE_Y, 0.0, fcol, mats["carpet"])
    add_box("Ceiling", 0.0, 0.0, z1, SIZE_X, SIZE_Y, z1 + CEIL_T, ccol, mats["ceiling"])

    # Outer shell. Entrance in the south wall: 1.2 m x 2.2 m at x=10.60-11.80.
    add_box("WALL.Outer.West", 0.0, 0.0, 0.0, WALL_T, SIZE_Y, z1, wcol, wall)
    add_box("WALL.Outer.East", SIZE_X - WALL_T, 0.0, 0.0, SIZE_X, SIZE_Y, z1, wcol, wall)
    add_box("WALL.Outer.North", WALL_T, SIZE_Y - WALL_T, 0.0, SIZE_X - WALL_T, SIZE_Y, z1, wcol, wall)
    add_box("WALL.Outer.South.W", WALL_T, 0.0, 0.0, 10.60, WALL_T, z1, wcol, wall)
    add_box("WALL.Outer.South.E", 11.80, 0.0, 0.0, SIZE_X - WALL_T, WALL_T, z1, wcol, wall)
    add_box("WALL.Outer.South.Lintel", 10.60, 0.0, 2.20, 11.80, WALL_T, z1, wcol, wall)

    # Room B (3.0 x 2.8) SW. Opening north 1.5 x 2.3 into Hall B.
    add_box("WALL.RoomB.East", 3.20, WALL_T, 0.0, 3.40, 3.00, z1, wcol, wall)
    wall_opening_x("WALL.RoomB.North", WALL_T, 3.40, 3.00, 3.20, 1.30, 2.80, 2.30, wcol, wall)

    # Hall B: north then east, 1.5 m then 1.4 m.
    add_box("WALL.HallB.West", 1.10, 3.20, 0.0, 1.30, 5.80, z1, wcol, wall)
    add_box("WALL.HallB.EastNS", 2.80, 3.20, 0.0, 3.00, 4.40, z1, wcol, wall)
    add_box("WALL.HallB.SouthEW.W", 2.80, 4.40, 0.0, 3.50, 4.60, z1, wcol, wall)
    add_box("WALL.HallB.SouthEW.E", 4.80, 4.40, 0.0, 5.40, 4.60, z1, wcol, wall)
    add_box("WALL.HallB.Jog", 4.00, 4.40, 0.0, 4.20, 4.95, z1, wcol, wall)

    # Dead-end alcove south of Hall B, 1.3 m wide.
    add_box("WALL.DeadSW.West", 3.40, 1.40, 0.0, 3.60, 4.40, z1, wcol, wall)
    add_box("WALL.DeadSW.East", 4.80, 1.40, 0.0, 5.00, 4.40, z1, wcol, wall)
    add_box("WALL.DeadSW.South", 3.60, 1.40, 0.0, 4.80, 1.60, z1, wcol, wall)

    # Main (5.0 x 4.0) against the south side.
    add_box("WALL.Main.West", 5.20, WALL_T, 0.0, 5.40, 4.20, z1, wcol, wall)
    wall_opening_x("WALL.Main.North", 5.40, 10.40, 4.20, 4.40, 7.00, 8.60, 2.35, wcol, wall)
    wall_opening_y("WALL.Main.East", 10.40, 10.60, WALL_T, 4.40, 1.80, 3.60, 2.30, wcol, wall)

    # Central L-stub + 0.40 m column — stops a straight look across Main.
    add_box("WALL.Main.StubV", 7.60, 1.90, 0.0, 7.80, 4.20, z1, wcol, wall)
    add_box("WALL.Main.StubH", 7.80, 1.90, 0.0, 9.10, 2.10, z1, wcol, wall)
    add_box("COL.Main.L", 7.50, 1.80, 0.0, 7.90, 2.20, z1, wcol, wall)

    # Entrance hall 1.2 m, dead-end north of the Main opening.
    add_box("WALL.Ent.End", 10.60, 4.40, 0.0, SIZE_X - WALL_T, 4.60, z1, wcol, wall)

    # Hall B continues east north of Main (1.4 m).
    add_box("WALL.HallB.NorthE", 6.40, 5.80, 0.0, 10.40, 6.00, z1, wcol, wall)

    # T into Corr A (1.8 m) with a lintelled opening, not a full-height cut.
    wall_opening_x("WALL.CorrA.South", 4.60, 6.40, 5.80, 6.00, 4.80, 6.20, 2.40, wcol, wall)

    # Room A (4.2 x 3.8) NW. Opening east 1.6 x 2.4 into Corr A.
    add_box("WALL.RoomA.South", WALL_T, 5.80, 0.0, 4.40, 6.00, z1, wcol, wall)
    wall_opening_y("WALL.RoomA.East", 4.40, 4.60, 6.00, SIZE_Y - WALL_T, 8.00, 9.60, 2.40, wcol, wall)

    # Corr A jog — blocks Room A from the T.
    add_box("WALL.CorrA.Jog", 5.90, 6.80, 0.0, 6.40, 7.00, z1, wcol, wall)
    add_box("WALL.CorrA.EastS", 6.40, 6.00, 0.0, 6.60, 6.80, z1, wcol, wall)

    # Dead-end north-east branch 1.4 m, then around the core.
    wall_opening_y("WALL.DeadNE.West", 6.40, 6.60, 6.80, 9.80, 6.80, 8.40, 2.30, wcol, wall)
    add_box("WALL.DeadNE.East", 7.80, 6.60, 0.0, 8.00, 8.40, z1, wcol, wall)
    add_box("WALL.DeadNE.South", 6.60, 6.60, 0.0, 7.80, 6.80, z1, wcol, wall)

    # Solid service core — you walk around it, never through it.
    add_box("WALL.Core", 8.20, 6.20, 0.0, 10.40, 8.40, z1, wcol, core)

    # Hall N (1.4 m) along the north, Hall E (1.2 m) dead-end south.
    add_box("WALL.HallN.South", 8.00, 8.40, 0.0, 10.60, 8.60, z1, wcol, wall)
    add_box("WALL.HallE.West", 10.40, 6.00, 0.0, 10.60, 8.40, z1, wcol, wall)
    add_box("WALL.HallE.South", 10.60, 5.80, 0.0, SIZE_X - WALL_T, 6.00, z1, wcol, wall)

    # Close leftover pockets so they are not accidental rooms.
    add_box("WALL.Pocket.SW", 3.60, WALL_T, 0.0, 5.20, 1.40, z1, wcol, wall)


def add_ceiling_grid(col: bpy.types.Collection, mat: bpy.types.Material) -> None:
    """Drop-ceiling T-bars on a 0.60 m grid, underside of the slab."""
    z0, z1 = ROOM_H - 0.025, ROOM_H
    bar = 0.025
    step = 0.60
    x = 0.0
    i = 0
    while x <= SIZE_X + 0.001:
        add_box(f"CEIL.TBarX.{i:02d}", x, 0.0, z0, min(SIZE_X, x + bar), SIZE_Y, z1, col, mat)
        x += step
        i += 1
    y = 0.0
    j = 0
    while y <= SIZE_Y + 0.001:
        add_box(f"CEIL.TBarY.{j:02d}", 0.0, y, z0, SIZE_X, min(SIZE_Y, y + bar), z1, col, mat)
        y += step
        j += 1


def add_light(
    name: str,
    x: float,
    y: float,
    along: str,
    col: bpy.types.Collection,
    housing: bpy.types.Material,
    emit: bpy.types.Material,
) -> None:
    z_h0, z_h1 = ROOM_H - 0.08, ROOM_H
    z_e0, z_e1 = ROOM_H - 0.085, ROOM_H - 0.055
    if along == "X":
        add_box(f"{name}.Housing", x - 0.60, y - 0.10, z_h0, x + 0.60, y + 0.10, z_h1, col, housing)
        add_box(f"{name}.Lamp", x - 0.56, y - 0.07, z_e0, x + 0.56, y + 0.07, z_e1, col, emit)
    else:
        add_box(f"{name}.Housing", x - 0.10, y - 0.60, z_h0, x + 0.10, y + 0.60, z_h1, col, housing)
        add_box(f"{name}.Lamp", x - 0.07, y - 0.56, z_e0, x + 0.07, y + 0.56, z_e1, col, emit)


def place_lights(col: bpy.types.Collection, housing: bpy.types.Material, emit: bpy.types.Material) -> None:
    # ~2.0–2.5 m spacing, 1.2 m fixtures, only over walkable rooms / halls.
    specs = [
        ("LIGHT.Main.01", 6.60, 2.20, "X"),
        ("LIGHT.Main.02", 8.70, 2.20, "X"),
        ("LIGHT.Main.03", 9.40, 3.40, "Y"),
        ("LIGHT.RoomB.01", 1.70, 1.60, "X"),
        ("LIGHT.HallB.01", 2.05, 4.50, "Y"),
        ("LIGHT.HallB.02", 5.20, 5.10, "X"),
        ("LIGHT.HallB.03", 7.40, 5.10, "X"),
        ("LIGHT.RoomA.01", 1.50, 7.90, "X"),
        ("LIGHT.RoomA.02", 3.20, 7.90, "X"),
        ("LIGHT.CorrA.01", 5.50, 8.40, "Y"),
        ("LIGHT.DeadNE.01", 7.10, 8.20, "Y"),
        ("LIGHT.HallN.01", 9.40, 9.10, "X"),
        ("LIGHT.HallE.01", 11.20, 7.20, "Y"),
        ("LIGHT.Ent.01", 11.20, 2.30, "Y"),
        ("LIGHT.DeadSW.01", 4.15, 2.80, "Y"),
    ]
    for name, x, y, along in specs:
        add_light(name, x, y, along, col, housing, emit)


def add_cameras() -> None:
    def cam(name: str, loc, target, lens: float, ortho: bool = False) -> bpy.types.Object:
        data = bpy.data.cameras.new(name)
        data.lens = lens
        data.clip_end = 40
        if ortho:
            data.type = "ORTHO"
            data.ortho_scale = 13.2
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        obj.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.collection.objects.link(obj)
        return obj

    # Standing in Main, looking at the L-stub, north opening and lights.
    c1 = cam(
        "CameraMain",
        W(9.55, 1.05, 1.55),
        W(7.40, 3.40, 1.45),
        24,
    )
    bpy.context.scene.camera = c1
    # Just inside the entrance, first corner: hall dead-end + opening into Main.
    cam("CameraEntrance", W(11.20, 0.85, 1.55), W(11.20, 3.60, 1.45), 28)
    # Second corner: Corr A jog, Room A opening to the north-west.
    cam("CameraCorner", W(5.20, 6.35, 1.55), W(5.50, 8.80, 1.40), 28)
    plan = cam("CameraPlan", W(6.0, 5.0, 12.0), W(6.0, 5.0, 0.0), 35, ortho=True)
    plan.rotation_euler = (0.0, 0.0, 0.0)


def setup_render(args: dict, filepath: Path) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args["samples"]
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "use_adaptive_sampling"):
        scene.cycles.use_adaptive_sampling = True
    scene.cycles.max_bounces = 10
    scene.cycles.diffuse_bounces = 8
    scene.cycles.glossy_bounces = 4
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    scene.render.resolution_x, scene.render.resolution_y = args["resolution"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(filepath)
    scene.render.use_compositing = False
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.15
    scene.view_settings.look = "None"


def render_camera(name: str, path: Path) -> None:
    scene = bpy.context.scene
    scene.camera = bpy.data.objects[name]
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print("Rendered", path, flush=True)


def hide_for_plan(hide: bool) -> None:
    prefixes = ("Ceiling", "CEIL.", "LIGHT.")
    for obj in bpy.data.objects:
        if obj.name == "Ceiling" or obj.name.startswith(prefixes):
            obj.hide_render = hide


def save_layout_png() -> None:
    """Top-down occupancy sketch from wall object sizes."""
    px_per_m = 40
    tw, th = int(SIZE_X * px_per_m), int(SIZE_Y * px_per_m)
    pix = [0.86, 0.74, 0.38, 1.0] * (tw * th)

    def paint(x0: float, y0: float, x1: float, y1: float, rgb: tuple[float, float, float]) -> None:
        ix0 = max(0, int(min(x0, x1) * px_per_m))
        ix1 = min(tw, int(max(x0, x1) * px_per_m) + 1)
        iy0 = max(0, int(min(y0, y1) * px_per_m))
        iy1 = min(th, int(max(y0, y1) * px_per_m) + 1)
        r, g, b = rgb
        for y in range(iy0, iy1):
            row = y * tw * 4
            for x in range(ix0, ix1):
                i = row + x * 4
                pix[i : i + 4] = [r, g, b, 1.0]

    for obj in bpy.data.objects:
        if not obj.name.startswith(("WALL.", "COL.")):
            continue
        cx = obj.location.x - ORIGIN.x
        cy = obj.location.y - ORIGIN.y
        sx, sy = obj.dimensions.x, obj.dimensions.y
        paint(cx - sx * 0.5, cy - sy * 0.5, cx + sx * 0.5, cy + sy * 0.5, (0.12, 0.10, 0.08))

    img = bpy.data.images.new("LayoutPreview", tw, th, alpha=False)
    img.pixels = pix
    LAYOUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(LAYOUT_PNG)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def validate_scene() -> None:
    dg = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    # Wall thickness sample: Main west face.
    origin = W(5.00, 2.20, 1.20)
    hit, loc, nrm, *_rest = scene.ray_cast(dg, origin, Vector((1, 0, 0)))
    thick = None
    if hit:
        hit2, loc2, *_r = scene.ray_cast(dg, loc + Vector((0.001, 0, 0)), Vector((1, 0, 0)))
        if hit2:
            thick = (loc2 - loc).length
        else:
            # Exit ray from inside the wall.
            hit2, loc2, *_r = scene.ray_cast(dg, loc + nrm * -0.001 + Vector((0.05, 0, 0)), Vector((1, 0, 0)))
            if hit2:
                thick = (loc2 - loc).length
    print("validate wall hit", hit, loc, "thickness_est", thick)

    def vis(a, b) -> bool:
        d = b - a
        hit, loc, *_r = scene.ray_cast(dg, a, d.normalized())
        if not hit:
            return True
        return (loc - a).length > d.length - 0.05

    entrance = W(11.20, 1.20, 1.55)
    room_a = W(2.20, 8.00, 1.55)
    room_b = W(1.70, 1.50, 1.55)
    print("see-through entrance->A", vis(entrance, room_a))
    print("see-through entrance->B", vis(entrance, room_b))
    print("see-through A->B", vis(room_a, room_b))


def main() -> None:
    args = parse_args()
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    clear_scene()
    cols = {
        "Walls": collection("Walls"),
        "Floor": collection("Floor"),
        "Ceiling": collection("Ceiling"),
        "Lights": collection("Lights"),
    }
    tile = make_wallpaper_image()
    space = bpy.data.objects.new("WallpaperSpace", None)
    space.location = W(0.0, 0.0, 0.0)
    bpy.context.scene.collection.objects.link(space)
    mats = {
        "wallpaper": mat_wallpaper(tile, space),
        "carpet": mat_carpet(),
        "ceiling": mat_ceiling(),
        "housing": mat_housing(),
        "emit": mat_emitter(),
        "core": mat_wallpaper(tile, space),
    }
    build_structure(mats, cols)
    add_ceiling_grid(cols["Ceiling"], mats["ceiling"])
    place_lights(cols["Lights"], mats["housing"], mats["emit"])
    add_world()
    add_cameras()
    save_layout_png()
    setup_render(args, RENDER_DIR / "backrooms.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    validate_scene()
    if args["render"]:
        render_camera("CameraMain", RENDER_DIR / "backrooms.png")
        render_camera("CameraEntrance", RENDER_DIR / "backrooms_entrance.png")
        render_camera("CameraCorner", RENDER_DIR / "backrooms_corner.png")
        hide_for_plan(True)
        fill = bpy.data.lights.new("PlanFill", "SUN")
        fill.energy = 2.4
        fill_obj = bpy.data.objects.new("PlanFill", fill)
        fill_obj.rotation_euler = (0.0, 0.0, 0.0)
        bpy.context.scene.collection.objects.link(fill_obj)
        render_camera("CameraPlan", RENDER_DIR / "backrooms_plan.png")
        bpy.data.objects.remove(fill_obj, do_unlink=True)
        hide_for_plan(False)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
