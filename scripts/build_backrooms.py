#!/usr/bin/env python3
"""Procedural Backrooms level in Geometry Nodes, following Blender Guru
https://www.youtube.com/watch?v=kBsVJSETydU

- Texture-driven maze paths
- Adaptive wall volumes from the layout
- Outer shell (forced border walls)
- Box-projected wallpaper / carpet / ceiling (not candy-yellow)
- Random wall cutouts + light-panel randomness
- Named attribute driving emission in the shader
- Cycles + compositor: grade, glare, grain

Usage:
  blender -b --python scripts/build_backrooms.py
  blender -b --python scripts/build_backrooms.py -- --fast
  blender -b --python scripts/build_backrooms.py -- --no-render
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "backrooms.blend"
RENDER_DIR = ROOT / "renders"
MAZE_PNG = ROOT / "reference" / "backrooms_layout.png"


def parse_args() -> dict:
    args = {
        "samples": 48,
        "resolution": (1280, 720),
        "render": True,
        "fast": False,
        "cutouts": True,
        "seed": 11,
        "debug_cut": False,
    }
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    i = 0
    while i < len(argv):
        if argv[i] == "--fast":
            args["fast"] = True
            args["samples"] = 28
            args["resolution"] = (1280, 720)
        elif argv[i] == "--no-render":
            args["render"] = False
        elif argv[i] == "--no-cutouts":
            args["cutouts"] = False
        elif argv[i] == "--debug-cut":
            args["debug_cut"] = True
        elif argv[i] == "--samples" and i + 1 < len(argv):
            args["samples"] = int(argv[i + 1])
            i += 1
        elif argv[i] == "--seed" and i + 1 < len(argv):
            args["seed"] = int(argv[i + 1])
            i += 1
        i += 1
    return args


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.node_groups,
        bpy.data.images,
        bpy.data.curves,
    ):
        for item in list(datablocks):
            if getattr(item, "name", "") == "Render Result":
                continue
            try:
                datablocks.remove(item)
            except Exception:
                pass


def srgb(r: float, g: float, b: float) -> tuple[float, float, float, float]:
    def f(x: float) -> float:
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    return (f(r), f(g), f(b), 1.0)


# --- Maze layout (texture-driven paths) ---------------------------------

def generate_maze(width: int, height: int, seed: int) -> tuple[list[list[bool]], list[list[bool]], list[list[bool]]]:
    """Recursive backtracker, then knock extra walls for long corridors.

    H[r][c] is the wall between (c, r-1) and (c, r). V[r][c] between (c-1, r) and (c, r).
    True means the wall is present.
    """
    rng = random.Random(seed)
    visited = [[False] * width for _ in range(height)]
    horiz = [[True] * width for _ in range(height + 1)]
    vert = [[True] * (width + 1) for _ in range(height)]

    stack = [(width // 2, 0)]
    visited[0][width // 2] = True
    while stack:
        x, y = stack[-1]
        options = []
        if x > 0 and not visited[y][x - 1]:
            options.append((-1, 0))
        if x < width - 1 and not visited[y][x + 1]:
            options.append((1, 0))
        if y > 0 and not visited[y - 1][x]:
            options.append((0, -1))
        if y < height - 1 and not visited[y + 1][x]:
            options.append((0, 1))
        if not options:
            stack.pop()
            continue
        dx, dy = rng.choice(options)
        nx, ny = x + dx, y + dy
        visited[ny][nx] = True
        if dx == 1:
            vert[y][x + 1] = False
        elif dx == -1:
            vert[y][x] = False
        elif dy == 1:
            horiz[y + 1][x] = False
        else:
            horiz[y][x] = False
        stack.append((nx, ny))

    # Long north-south corridor through the middle (Guru "Creating Long Corridors").
    cx = width // 2
    for y in range(height - 1):
        horiz[y + 1][cx] = False
        if cx > 0 and rng.random() < 0.35:
            vert[y][cx] = False
        if cx < width and rng.random() < 0.35:
            vert[y][cx + 1] = False

    # Extra random knock-downs so it is rooms, not a perfect maze.
    for _ in range(int(width * height * 0.18)):
        if rng.random() < 0.5:
            y = rng.randrange(1, height)
            x = rng.randrange(width)
            horiz[y][x] = False
        else:
            y = rng.randrange(height)
            x = rng.randrange(1, width)
            vert[y][x] = False

    # Keep the outer shell closed.
    for x in range(width):
        horiz[0][x] = True
        horiz[height][x] = True
    for y in range(height):
        vert[y][0] = True
        vert[y][width] = True
    return horiz, vert, visited


def rasterize_maze(
    width: int,
    height: int,
    horiz: list[list[bool]],
    vert: list[list[bool]],
    cell_px: int,
    wall_px: int,
) -> list[list[float]]:
    tw = width * cell_px + (width + 1) * wall_px
    th = height * cell_px + (height + 1) * wall_px
    img = [[0.0] * tw for _ in range(th)]

    def fill(x0: int, y0: int, x1: int, y1: int, value: float) -> None:
        for y in range(max(0, y0), min(th, y1)):
            row = img[y]
            for x in range(max(0, x0), min(tw, x1)):
                row[x] = value

    for cy in range(height):
        for cx in range(width):
            x0 = wall_px + cx * (cell_px + wall_px)
            y0 = wall_px + cy * (cell_px + wall_px)
            fill(x0, y0, x0 + cell_px, y0 + cell_px, 1.0)
            if not vert[cy][cx + 1]:
                fill(x0 + cell_px, y0, x0 + cell_px + wall_px, y0 + cell_px, 1.0)
            if not horiz[cy + 1][cx]:
                fill(x0, y0 + cell_px, x0 + cell_px, y0 + cell_px + wall_px, 1.0)
    return img


def maze_to_image(pixels: list[list[float]], name: str) -> bpy.types.Image:
    th = len(pixels)
    tw = len(pixels[0])
    img = bpy.data.images.new(name, tw, th, alpha=False, float_buffer=True)
    flat: list[float] = []
    for y in range(th):
        row = pixels[y]
        for x in range(tw):
            v = row[x]
            flat.extend((v, v, v, 1.0))
    img.pixels = flat
    img.pack()
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    MAZE_PNG.parent.mkdir(parents=True, exist_ok=True)
    img.filepath_raw = str(MAZE_PNG)
    img.file_format = "PNG"
    img.save()
    return img


def longest_corridor(width: int, height: int, horiz: list[list[bool]]) -> tuple[int, int, int]:
    """Return (cell_x, start_y, length) for the longest north-south opening."""
    best = (width // 2, 0, 1)
    for x in range(width):
        run = 1
        start = 0
        for y in range(height - 1):
            if not horiz[y + 1][x]:
                if run == 1:
                    start = y
                run += 1
                if run > best[2]:
                    best = (x, start, run)
            else:
                run = 1
    return best


# --- Materials (box projection, not candy yellow) -----------------------

def _noise(nt, scale: float, detail: float = 6.0):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = 0.55
    return n


def _set(bsdf, name: str, value) -> None:
    if name in bsdf.inputs:
        bsdf.inputs[name].default_value = value


def mat_wallpaper() -> bpy.types.Material:
    """Dirty beige paper, grime at the skirting line. Not candy yellow."""
    mat = bpy.data.materials.new("Wallpaper")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    _set(bsdf, "Roughness", 0.72)
    _set(bsdf, "Specular IOR Level", 0.22)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.7, 0.7, 0.7)
    paper = _noise(nt, 48.0, 10.0)
    stains = _noise(nt, 1.35, 5.0)
    mold = _noise(nt, 0.55, 3.0)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    dirt_z = nt.nodes.new("ShaderNodeValToRGB")
    dirt_z.color_ramp.elements[0].position = 0.0
    dirt_z.color_ramp.elements[0].color = (0.42, 0.36, 0.24, 1.0)
    dirt_z.color_ramp.elements[1].position = 0.22
    dirt_z.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    base_mix = nt.nodes.new("ShaderNodeMixRGB")
    base_mix.blend_type = "MULTIPLY"
    base_mix.inputs["Fac"].default_value = 0.28
    base_mix.inputs["Color1"].default_value = srgb(0.67, 0.60, 0.43)
    stain_mix = nt.nodes.new("ShaderNodeMixRGB")
    stain_mix.blend_type = "MULTIPLY"
    stain_mix.inputs["Fac"].default_value = 0.22
    zdiv = nt.nodes.new("ShaderNodeMath")
    zdiv.operation = "DIVIDE"
    zdiv.inputs[1].default_value = 3.6
    rough = nt.nodes.new("ShaderNodeMath")
    rough.operation = "MULTIPLY_ADD"
    rough.inputs[1].default_value = 0.18
    rough.inputs[2].default_value = 0.62
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.004
    links = nt.links
    links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    links.new(coord.outputs["Object"], sep.inputs["Vector"])
    links.new(mapping.outputs["Vector"], paper.inputs["Vector"])
    links.new(mapping.outputs["Vector"], stains.inputs["Vector"])
    links.new(mapping.outputs["Vector"], mold.inputs["Vector"])
    links.new(sep.outputs["Z"], zdiv.inputs[0])
    links.new(zdiv.outputs["Value"], dirt_z.inputs["Fac"])
    links.new(stains.outputs["Fac"], base_mix.inputs["Color2"])
    links.new(base_mix.outputs["Color"], stain_mix.inputs["Color1"])
    links.new(dirt_z.outputs["Color"], stain_mix.inputs["Color2"])
    links.new(stain_mix.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(paper.outputs["Fac"], rough.inputs[0])
    links.new(rough.outputs["Value"], bsdf.inputs["Roughness"])
    links.new(paper.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def mat_carpet() -> bpy.types.Material:
    mat = bpy.data.materials.new("Carpet")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    _set(bsdf, "Sheen Weight", 0.55)
    _set(bsdf, "Sheen Roughness", 0.4)
    _set(bsdf, "Specular IOR Level", 0.18)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (2.4, 2.4, 2.4)
    noise = _noise(nt, 22.0, 8.0)
    voro = nt.nodes.new("ShaderNodeTexVoronoi")
    voro.inputs["Scale"].default_value = 64.0
    wet = _noise(nt, 1.1, 2.0)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = srgb(0.34, 0.28, 0.14)
    ramp.color_ramp.elements[1].color = srgb(0.52, 0.44, 0.24)
    rough = nt.nodes.new("ShaderNodeMapRange")
    rough.inputs["From Min"].default_value = 0.0
    rough.inputs["From Max"].default_value = 1.0
    rough.inputs["To Min"].default_value = 0.42
    rough.inputs["To Max"].default_value = 0.92
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.55
    bump.inputs["Distance"].default_value = 0.006
    links = nt.links
    links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], voro.inputs["Vector"])
    links.new(mapping.outputs["Vector"], wet.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(wet.outputs["Fac"], rough.inputs["Value"])
    links.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    links.new(voro.outputs["Distance"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def mat_ceiling() -> bpy.types.Material:
    mat = bpy.data.materials.new("CeilingTiles")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.88
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.55, 0.55, 0.55)
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.squash = 1.0
    brick.inputs["Scale"].default_value = 2.2
    brick.inputs["Mortar Size"].default_value = 0.028
    brick.inputs["Brick Width"].default_value = 1.0
    brick.inputs["Row Height"].default_value = 1.0
    brick.inputs["Color1"].default_value = srgb(0.78, 0.75, 0.66)
    brick.inputs["Color2"].default_value = srgb(0.72, 0.70, 0.62)
    brick.inputs["Mortar"].default_value = srgb(0.48, 0.46, 0.40)
    noise = _noise(nt, 4.5, 6.0)
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.2
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    links = nt.links
    links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(brick.outputs["Color"], mix.inputs["Color1"])
    links.new(noise.outputs["Fac"], mix.inputs["Color2"])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def mat_light() -> bpy.types.Material:
    """Fluorescent diffuser. Strength comes from the GN 'emit' attribute."""
    mat = bpy.data.materials.new("Fluorescent")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = srgb(0.96, 1.0, 0.78)
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "emit"
    math = nt.nodes.new("ShaderNodeMath")
    math.operation = "MAXIMUM"
    math.inputs[1].default_value = 8.0
    links = nt.links
    links.new(attr.outputs["Fac"], math.inputs[0])
    links.new(math.outputs["Value"], emit.inputs["Strength"])
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def mat_housing() -> bpy.types.Material:
    mat = bpy.data.materials.new("LightHousing")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    _set(bsdf, "Base Color", srgb(0.12, 0.12, 0.11))
    _set(bsdf, "Metallic", 0.65)
    _set(bsdf, "Roughness", 0.38)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


# --- Geometry Nodes graph ----------------------------------------------

def _frame(ng: bpy.types.NodeTree, label: str, color: tuple[float, float, float]) -> bpy.types.Node:
    frame = ng.nodes.new("NodeFrame")
    frame.label = label
    frame.use_custom_color = True
    frame.color = color
    return frame


def _parent(nodes: list, frame: bpy.types.Node) -> None:
    for n in nodes:
        n.parent = frame


def build_geometry_nodes(
    maze_image: bpy.types.Image,
    mats: dict,
    size_x: float,
    size_y: float,
    verts_x: int,
    verts_y: int,
    wall_height: float,
    use_cutouts: bool,
    seed: int,
    hero_cut: Vector,
    hero_obj: bpy.types.Object | None = None,
) -> bpy.types.NodeTree:
    ng = bpy.data.node_groups.new("BackroomsGenerator", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    height_sock = ng.interface.new_socket(name="Wall Height", in_out="INPUT", socket_type="NodeSocketFloat")
    try:
        height_sock.default_value = wall_height
        height_sock.min_value = 2.0
        height_sock.max_value = 6.0
    except Exception:
        pass
    cut_sock = ng.interface.new_socket(name="Cutout Density", in_out="INPUT", socket_type="NodeSocketFloat")
    try:
        cut_sock.default_value = 0.02 if use_cutouts else 0.0
        cut_sock.min_value = 0.0
        cut_sock.max_value = 0.2
    except Exception:
        pass
    light_sock = ng.interface.new_socket(name="Light Density", in_out="INPUT", socket_type="NodeSocketFloat")
    try:
        light_sock.default_value = 0.16
        light_sock.min_value = 0.02
        light_sock.max_value = 1.0
    except Exception:
        pass
    seed_sock = ng.interface.new_socket(name="Seed", in_out="INPUT", socket_type="NodeSocketInt")
    try:
        seed_sock.default_value = seed
    except Exception:
        pass

    nodes = ng.nodes
    links = ng.links
    n_in = nodes.new("NodeGroupInput")
    n_in.location = (-1600, 0)
    n_out = nodes.new("NodeGroupOutput")
    n_out.location = (2400, 0)

    def link(a, b):
        links.new(a, b)

    # Paths from texture
    grid = nodes.new("GeometryNodeMeshGrid")
    grid.location = (-1300, 200)
    grid.inputs["Size X"].default_value = size_x
    grid.inputs["Size Y"].default_value = size_y
    grid.inputs["Vertices X"].default_value = verts_x
    grid.inputs["Vertices Y"].default_value = verts_y
    img = nodes.new("GeometryNodeImageTexture")
    img.location = (-1080, 40)
    img.interpolation = "Closest"
    img.extension = "EXTEND"
    img.inputs["Image"].default_value = maze_image
    sep = nodes.new("FunctionNodeSeparateColor")
    sep.location = (-860, 40)
    is_path = nodes.new("FunctionNodeCompare")
    is_path.location = (-680, 40)
    is_path.operation = "GREATER_THAN"
    is_path.inputs["B"].default_value = 0.5
    not_path = nodes.new("FunctionNodeBooleanMath")
    not_path.location = (-500, -40)
    not_path.operation = "NOT"
    link(grid.outputs["UV Map"], img.inputs["Vector"])
    link(img.outputs["Color"], sep.inputs["Color"] if "Color" in sep.inputs else sep.inputs[0])
    link(sep.outputs["Red"], is_path.inputs["A"])
    link(is_path.outputs["Result"], not_path.inputs[0])
    _parent([grid, img, sep, is_path, not_path], _frame(ng, "Paths from texture", (0.18, 0.16, 0.12)))

    # Floor
    del_floor = nodes.new("GeometryNodeDeleteGeometry")
    del_floor.location = (-280, 280)
    del_floor.domain = "FACE"
    del_floor.mode = "ALL"
    set_carpet = nodes.new("GeometryNodeSetMaterial")
    set_carpet.location = (-40, 280)
    mat_carpet = nodes.new("GeometryNodeInputMaterial")
    mat_carpet.location = (-280, 420)
    mat_carpet.material = mats["carpet"]
    link(grid.outputs["Mesh"], del_floor.inputs["Geometry"])
    link(not_path.outputs["Boolean"], del_floor.inputs["Selection"])
    link(del_floor.outputs["Geometry"], set_carpet.inputs["Geometry"])
    link(mat_carpet.outputs["Material"], set_carpet.inputs["Material"])
    _parent([del_floor, set_carpet, mat_carpet], _frame(ng, "Floor", (0.16, 0.14, 0.10)))

    # Walls = inverse of paths, extruded to wall height
    del_walls = nodes.new("GeometryNodeDeleteGeometry")
    del_walls.location = (-280, 40)
    del_walls.domain = "FACE"
    extrude = nodes.new("GeometryNodeExtrudeMesh")
    extrude.location = (-40, 40)
    extrude.mode = "FACES"
    extrude.inputs["Individual"].default_value = True
    combine = nodes.new("ShaderNodeCombineXYZ")
    combine.location = (-280, -140)
    combine.inputs["X"].default_value = 0.0
    combine.inputs["Y"].default_value = 0.0
    combine.inputs["Z"].default_value = 1.0
    set_wall = nodes.new("GeometryNodeSetMaterial")
    set_wall.location = (200, 40)
    mat_wall = nodes.new("GeometryNodeInputMaterial")
    mat_wall.location = (-40, 180)
    mat_wall.material = mats["wallpaper"]
    shade_wall = nodes.new("GeometryNodeSetShadeSmooth")
    shade_wall.location = (420, 40)
    shade_wall.inputs["Shade Smooth"].default_value = False
    link(grid.outputs["Mesh"], del_walls.inputs["Geometry"])
    link(is_path.outputs["Result"], del_walls.inputs["Selection"])
    link(del_walls.outputs["Geometry"], extrude.inputs["Mesh"])
    link(combine.outputs["Vector"], extrude.inputs["Offset"])
    link(n_in.outputs["Wall Height"], extrude.inputs["Offset Scale"])
    link(extrude.outputs["Mesh"], set_wall.inputs["Geometry"])
    link(mat_wall.outputs["Material"], set_wall.inputs["Material"])
    link(set_wall.outputs["Geometry"], shade_wall.inputs["Mesh"])
    merge = nodes.new("GeometryNodeMergeByDistance")
    merge.location = (620, 40)
    merge.inputs["Distance"].default_value = 0.002
    link(shade_wall.outputs["Geometry"], merge.inputs["Geometry"])
    _parent(
        [del_walls, extrude, combine, set_wall, mat_wall, shade_wall, merge],
        _frame(ng, "Adaptive walls + outer shell", (0.20, 0.17, 0.12)),
    )

    walls_geo = merge.outputs["Geometry"]

    # Door-like cutouts: world-aligned boxes from the floor up (~90% wall height).
    # Do not rotate onto the face normal — that left floating shelves on the right wall.
    dist_cut = nodes.new("GeometryNodeDistributePointsOnFaces")
    dist_cut.location = (840, -80)
    dist_cut.distribute_method = "RANDOM"
    nrm = nodes.new("GeometryNodeInputNormal")
    nrm.location = (420, -220)
    sep_n = nodes.new("ShaderNodeSeparateXYZ")
    sep_n.location = (600, -220)
    abs_z = nodes.new("ShaderNodeMath")
    abs_z.location = (780, -220)
    abs_z.operation = "ABSOLUTE"
    vert_sel = nodes.new("FunctionNodeCompare")
    vert_sel.location = (960, -220)
    vert_sel.operation = "LESS_THAN"
    vert_sel.inputs["B"].default_value = 0.25
    door = nodes.new("GeometryNodeMeshCube")
    door.location = (840, -400)
    door.inputs["Size"].default_value = (1.18, 1.18, 3.22)
    inst_cut = nodes.new("GeometryNodeInstanceOnPoints")
    inst_cut.location = (1100, -80)
    drop = nodes.new("GeometryNodeTranslateInstances")
    drop.location = (1280, -80)
    drop.inputs["Translation"].default_value = (0.0, 0.0, -0.22)
    if "Local Space" in drop.inputs:
        drop.inputs["Local Space"].default_value = False
    real_cut = nodes.new("GeometryNodeRealizeInstances")
    real_cut.location = (1460, -80)
    boolean = nodes.new("GeometryNodeMeshBoolean")
    boolean.location = (1640, 40)
    boolean.operation = "DIFFERENCE"
    boolean.solver = "EXACT"
    if "Hole Tolerant" in boolean.inputs:
        boolean.inputs["Hole Tolerant"].default_value = True
    link(walls_geo, dist_cut.inputs["Mesh"])
    link(n_in.outputs["Cutout Density"], dist_cut.inputs["Density"])
    link(n_in.outputs["Seed"], dist_cut.inputs["Seed"])
    link(nrm.outputs["Normal"], sep_n.inputs["Vector"])
    link(sep_n.outputs["Z"], abs_z.inputs[0])
    link(abs_z.outputs["Value"], vert_sel.inputs["A"])
    link(vert_sel.outputs["Result"], dist_cut.inputs["Selection"])
    link(dist_cut.outputs["Points"], inst_cut.inputs["Points"])
    link(door.outputs["Mesh"], inst_cut.inputs["Instance"])
    link(inst_cut.outputs["Instances"], drop.inputs["Instances"])
    link(drop.outputs["Instances"], real_cut.inputs["Geometry"])
    hero_door = nodes.new("GeometryNodeMeshCube")
    hero_door.location = (1460, -280)
    hero_door.inputs["Size"].default_value = (1.42, 0.72, 3.22)
    hero_xf = nodes.new("GeometryNodeTransform")
    hero_xf.location = (1640, -280)
    hero_vec = nodes.new("FunctionNodeInputVector")
    hero_vec.location = (1460, -400)
    hero_vec.vector = (hero_cut.x, hero_cut.y, hero_cut.z)
    link(hero_vec.outputs["Vector"], hero_xf.inputs["Translation"])
    link(hero_door.outputs["Mesh"], hero_xf.inputs["Geometry"])
    join_cut = nodes.new("GeometryNodeJoinGeometry")
    join_cut.location = (1680, -80)
    link(real_cut.outputs["Geometry"], join_cut.inputs["Geometry"])
    link(hero_xf.outputs["Geometry"], join_cut.inputs["Geometry"])
    if hero_obj is not None:
        info = nodes.new("GeometryNodeObjectInfo")
        info.location = (1460, -520)
        info.transform_space = "ORIGINAL"
        info.inputs["Object"].default_value = hero_obj
        link(info.outputs["Geometry"], join_cut.inputs["Geometry"])
    link(walls_geo, boolean.inputs["Mesh 1"])
    link(join_cut.outputs["Geometry"], boolean.inputs["Mesh 2"])
    _parent(
        [dist_cut, nrm, sep_n, abs_z, vert_sel, door, inst_cut, drop, real_cut, boolean],
        _frame(ng, "Floor-hugging door cutouts", (0.14, 0.12, 0.16)),
    )
    walls_out = boolean.outputs["Mesh"] if use_cutouts else walls_geo

    # Ceiling over the whole layout
    xform = nodes.new("GeometryNodeTransform")
    xform.location = (-280, 560)
    comb_up = nodes.new("ShaderNodeCombineXYZ")
    comb_up.location = (-500, 520)
    comb_up.inputs["X"].default_value = 0.0
    comb_up.inputs["Y"].default_value = 0.0
    flip = nodes.new("GeometryNodeFlipFaces")
    flip.location = (-40, 560)
    set_ceil = nodes.new("GeometryNodeSetMaterial")
    set_ceil.location = (200, 560)
    mat_ceil = nodes.new("GeometryNodeInputMaterial")
    mat_ceil.location = (-40, 700)
    mat_ceil.material = mats["ceiling"]
    link(grid.outputs["Mesh"], xform.inputs["Geometry"])
    link(n_in.outputs["Wall Height"], comb_up.inputs["Z"])
    link(comb_up.outputs["Vector"], xform.inputs["Translation"])
    link(xform.outputs["Geometry"], flip.inputs["Mesh"])
    link(flip.outputs["Mesh"], set_ceil.inputs["Geometry"])
    link(mat_ceil.outputs["Material"], set_ceil.inputs["Material"])

    # Lights only over paths, with random on/off + emit attribute
    del_light_area = nodes.new("GeometryNodeDeleteGeometry")
    del_light_area.location = (420, 700)
    del_light_area.domain = "FACE"
    dist_lights = nodes.new("GeometryNodeDistributePointsOnFaces")
    dist_lights.location = (640, 700)
    dist_lights.distribute_method = "RANDOM"
    panel = nodes.new("GeometryNodeMeshCube")
    panel.location = (640, 520)
    panel.inputs["Size"].default_value = (1.18, 0.58, 0.03)
    house = nodes.new("GeometryNodeMeshCube")
    house.location = (640, 380)
    house.inputs["Size"].default_value = (1.28, 0.68, 0.08)
    set_house_mat = nodes.new("GeometryNodeSetMaterial")
    set_house_mat.location = (860, 380)
    mat_house = nodes.new("GeometryNodeInputMaterial")
    mat_house.location = (640, 260)
    mat_house.material = mats["housing"]
    link(house.outputs["Mesh"], set_house_mat.inputs["Geometry"])
    link(mat_house.outputs["Material"], set_house_mat.inputs["Material"])
    rnd_on = nodes.new("FunctionNodeRandomValue")
    rnd_on.location = (640, 880)
    rnd_on.data_type = "BOOLEAN"
    for key in ("Probability", "Max"):
        if key in rnd_on.inputs:
            try:
                rnd_on.inputs[key].default_value = 0.62 if key == "Probability" else 1
            except TypeError:
                pass
            break
    rnd_emit = nodes.new("FunctionNodeRandomValue")
    rnd_emit.location = (860, 900)
    rnd_emit.data_type = "FLOAT"
    rnd_emit.inputs["Min"].default_value = 12.0
    rnd_emit.inputs["Max"].default_value = 42.0
    inst_lights = nodes.new("GeometryNodeInstanceOnPoints")
    inst_lights.location = (900, 700)
    inst_house = nodes.new("GeometryNodeInstanceOnPoints")
    inst_house.location = (900, 520)
    drop_diff = nodes.new("GeometryNodeTranslateInstances")
    drop_diff.location = (1120, 700)
    drop_diff.inputs["Translation"].default_value = (0.0, 0.0, -0.04)
    if "Local Space" in drop_diff.inputs:
        drop_diff.inputs["Local Space"].default_value = False
    store_emit = nodes.new("GeometryNodeStoreNamedAttribute")
    store_emit.location = (1320, 700)
    store_emit.data_type = "FLOAT"
    store_emit.domain = "INSTANCE"
    store_emit.inputs["Name"].default_value = "emit"
    real_lights = nodes.new("GeometryNodeRealizeInstances")
    real_lights.location = (1520, 700)
    real_house = nodes.new("GeometryNodeRealizeInstances")
    real_house.location = (1120, 520)
    set_light = nodes.new("GeometryNodeSetMaterial")
    set_light.location = (1720, 700)
    mat_light = nodes.new("GeometryNodeInputMaterial")
    mat_light.location = (1520, 840)
    mat_light.material = mats["light"]
    join_lights = nodes.new("GeometryNodeJoinGeometry")
    join_lights.location = (1900, 620)
    link(set_ceil.outputs["Geometry"], del_light_area.inputs["Geometry"])
    link(not_path.outputs["Boolean"], del_light_area.inputs["Selection"])
    link(del_light_area.outputs["Geometry"], dist_lights.inputs["Mesh"])
    link(n_in.outputs["Light Density"], dist_lights.inputs["Density"])
    link(n_in.outputs["Seed"], dist_lights.inputs["Seed"])
    seed2 = nodes.new("ShaderNodeMath")
    seed2.location = (420, 900)
    seed2.operation = "ADD"
    seed2.inputs[1].default_value = 17.0
    link(n_in.outputs["Seed"], seed2.inputs[0])
    link(seed2.outputs["Value"], rnd_on.inputs["Seed"])
    link(seed2.outputs["Value"], rnd_emit.inputs["Seed"])
    link(dist_lights.outputs["Points"], inst_lights.inputs["Points"])
    link(rnd_on.outputs["Value"], inst_lights.inputs["Selection"])
    link(panel.outputs["Mesh"], inst_lights.inputs["Instance"])
    link(inst_lights.outputs["Instances"], drop_diff.inputs["Instances"])
    link(drop_diff.outputs["Instances"], store_emit.inputs["Geometry"])
    link(rnd_emit.outputs["Value"], store_emit.inputs["Value"])
    link(store_emit.outputs["Geometry"], real_lights.inputs["Geometry"])
    link(real_lights.outputs["Geometry"], set_light.inputs["Geometry"])
    link(mat_light.outputs["Material"], set_light.inputs["Material"])
    link(dist_lights.outputs["Points"], inst_house.inputs["Points"])
    link(rnd_on.outputs["Value"], inst_house.inputs["Selection"])
    link(set_house_mat.outputs["Geometry"], inst_house.inputs["Instance"])
    link(inst_house.outputs["Instances"], real_house.inputs["Geometry"])
    link(set_light.outputs["Geometry"], join_lights.inputs["Geometry"])
    link(real_house.outputs["Geometry"], join_lights.inputs["Geometry"])
    _parent(
        [xform, comb_up, flip, set_ceil, mat_ceil, del_light_area, dist_lights, panel, house, set_house_mat, mat_house, rnd_on, rnd_emit, inst_lights, inst_house, drop_diff, store_emit, real_lights, real_house, set_light, mat_light, join_lights, seed2],
        _frame(ng, "Ceiling + random lights", (0.12, 0.16, 0.18)),
    )

    join = nodes.new("GeometryNodeJoinGeometry")
    join.location = (1860, 200)
    link(set_carpet.outputs["Geometry"], join.inputs["Geometry"])
    link(walls_out, join.inputs["Geometry"])
    link(set_ceil.outputs["Geometry"], join.inputs["Geometry"])
    link(join_lights.outputs["Geometry"], join.inputs["Geometry"])
    link(join.outputs["Geometry"], n_out.inputs["Geometry"])
    return ng


def add_cutter_cube(name: str, location: Vector, dimensions: tuple[float, float, float]) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= dimensions[0]
        v.co.y *= dimensions[1]
        v.co.z *= dimensions[2]
    bm.to_mesh(mesh)
    bm.free()
    obj.location = location
    obj.hide_render = True
    obj.display_type = "WIRE"
    return obj


def add_backrooms_object(ng: bpy.types.NodeTree) -> bpy.types.Object:
    mesh = bpy.data.meshes.new("BackroomsMesh")
    obj = bpy.data.objects.new("Backrooms", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mod = obj.modifiers.new("BackroomsGN", "NODES")
    mod.node_group = ng
    return obj


def add_world(haze: float = 0.01) -> None:
    world = bpy.data.worlds.new("Void")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.01, 0.012, 0.008, 1.0)
    bg.inputs["Strength"].default_value = 0.04
    scatter = nt.nodes.new("ShaderNodeVolumeScatter")
    scatter.inputs["Color"].default_value = srgb(0.85, 0.92, 0.70)
    scatter.inputs["Density"].default_value = haze
    if "Anisotropy" in scatter.inputs:
        scatter.inputs["Anisotropy"].default_value = 0.35
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    nt.links.new(scatter.outputs["Volume"], out.inputs["Volume"])


def add_camera(size_x: float, size_y: float, width: int, height: int, cell: float, wall: float, corridor: tuple[int, int, int], wall_height: float) -> bpy.types.Object:
    cx, start_y, length = corridor
    origin_x = -size_x / 2 + wall + (cx + 0.5) * (cell + wall)
    y0 = -size_y / 2 + wall + (start_y + 1.2) * (cell + wall)
    y1 = -size_y / 2 + wall + (start_y + max(length - 0.4, 1.2)) * (cell + wall)
    cam = bpy.data.cameras.new("Camera")
    cam.lens = 28
    cam.sensor_width = 36
    cam.clip_end = 200
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = 5.6
    obj = bpy.data.objects.new("Camera", cam)
    obj.location = (origin_x, y0, 1.58)
    target = Vector((origin_x, y1, 1.35))
    direction = target - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    focus = bpy.data.objects.new("Focus", None)
    focus.location = target
    bpy.context.scene.collection.objects.link(focus)
    cam.dof.focus_object = focus
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.scene.camera = obj
    return obj


def setup_compositor() -> None:
    ng = bpy.data.node_groups.new("BackroomsComp", "CompositorNodeTree")
    ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    grade = None
    for ntype in ("CompositorNodeHueSat", "CompositorNodeHueSaturation"):
        try:
            grade = ng.nodes.new(ntype)
            break
        except RuntimeError:
            continue
    if grade is not None:
        try:
            grade.inputs["Saturation"].default_value = 0.88
            grade.inputs["Hue"].default_value = 0.505
            grade.inputs["Value"].default_value = 0.98
        except KeyError:
            pass
    contrast = ng.nodes.new("CompositorNodeBrightContrast")
    try:
        contrast.inputs["Bright"].default_value = -0.02
        contrast.inputs["Contrast"].default_value = 0.08
    except KeyError:
        pass
    bloom = ng.nodes.new("CompositorNodeGlare")
    for glare_name in ("Bloom", "Fog Glow", "Ghosts"):
        try:
            bloom.inputs["Type"].default_value = glare_name
            break
        except TypeError:
            continue
    try:
        bloom.inputs["Threshold"].default_value = 0.55
        bloom.inputs["Strength"].default_value = 0.85
        bloom.inputs["Size"].default_value = 0.55
    except KeyError:
        pass
    mix_grain = ng.nodes.new("ShaderNodeMixRGB")
    mix_grain.blend_type = "OVERLAY"
    mix_grain.inputs["Fac"].default_value = 0.055
    grain = bpy.data.images.new("FilmGrain", 1280, 720, alpha=False)
    pixels = [0.0] * (1280 * 720 * 4)
    rng = random.Random(3)
    for i in range(0, len(pixels), 4):
        v = 0.5 + (rng.random() - 0.5) * 0.38
        pixels[i] = pixels[i + 1] = pixels[i + 2] = v
        pixels[i + 3] = 1.0
    grain.pixels = pixels
    img_node = ng.nodes.new("CompositorNodeImage")
    img_node.image = grain
    out = ng.nodes.new("NodeGroupOutput")
    links = ng.links
    src = rl.outputs["Image"]
    if grade is not None:
        links.new(src, grade.inputs["Image"] if "Image" in grade.inputs else grade.inputs[0])
        src = grade.outputs["Image"] if "Image" in grade.outputs else grade.outputs[0]
    links.new(src, contrast.inputs["Image"] if "Image" in contrast.inputs else contrast.inputs[0])
    src = contrast.outputs["Image"] if "Image" in contrast.outputs else contrast.outputs[0]
    links.new(src, bloom.inputs["Image"])
    links.new(bloom.outputs["Image"], mix_grain.inputs["Color1"])
    links.new(img_node.outputs["Image"], mix_grain.inputs["Color2"])
    links.new(mix_grain.outputs["Color"], out.inputs[0])
    scene = bpy.context.scene
    scene.compositing_node_group = ng
    scene.render.use_compositing = True


def setup_render(args: dict) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args["samples"]
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "use_adaptive_sampling"):
        scene.cycles.use_adaptive_sampling = True
    scene.cycles.max_bounces = 16
    scene.cycles.diffuse_bounces = 10
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 4
    scene.cycles.transparent_max_bounces = 4
    scene.cycles.volume_bounces = 4
    if hasattr(scene.cycles, "volume_step_rate"):
        scene.cycles.volume_step_rate = 1.2
    if hasattr(scene.cycles, "use_light_tree"):
        scene.cycles.use_light_tree = True
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    scene.render.resolution_x, scene.render.resolution_y = args["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    name = "backrooms_fast.png" if args["fast"] else "backrooms.png"
    scene.render.filepath = str(RENDER_DIR / name)
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    scene.view_settings.exposure = -0.05
    scene.view_settings.look = "None"
    setup_compositor()


def main() -> None:
    args = parse_args()
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    clear_scene()

    rooms_x, rooms_y = 9, 13
    cell_m, wall_m = 3.05, 0.22
    cell_px, wall_px = 12, 1
    wall_height = 3.6
    horiz, vert, _visited = generate_maze(rooms_x, rooms_y, args["seed"])
    pixels = rasterize_maze(rooms_x, rooms_y, horiz, vert, cell_px, wall_px)
    maze_image = maze_to_image(pixels, "MazeLayout")
    verts_x = len(pixels[0])
    verts_y = len(pixels)
    size_x = rooms_x * cell_m + (rooms_x + 1) * wall_m
    size_y = rooms_y * cell_m + (rooms_y + 1) * wall_m

    mats = {
        "wallpaper": mat_wallpaper(),
        "carpet": mat_carpet(),
        "ceiling": mat_ceiling(),
        "light": mat_light(),
        "housing": mat_housing(),
    }
    corridor = longest_corridor(rooms_x, rooms_y, horiz)
    cx, start_y, _length = corridor
    origin_x = -size_x / 2 + wall_m + (cx + 0.5) * (cell_m + wall_m)
    y0 = -size_y / 2 + wall_m + (start_y + 1.2) * (cell_m + wall_m)
    cutter = add_cutter_cube(
        "RightWallDoorCutter",
        Vector((2.18, -11.15, 1.61)),
        (1.48, 0.95, 3.22),
    )
    hero_cut = Vector(cutter.location)
    ng = build_geometry_nodes(
        maze_image,
        mats,
        size_x,
        size_y,
        verts_x,
        verts_y,
        wall_height,
        args["cutouts"],
        args["seed"],
        hero_cut,
        cutter,
    )
    add_backrooms_object(ng)
    add_world(0.0 if args["debug_cut"] else 0.01)
    add_camera(size_x, size_y, rooms_x, rooms_y, cell_m, wall_m, corridor, wall_height)
    setup_render(args)

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("hero_cut", tuple(round(c, 3) for c in hero_cut), "cam_guess", round(origin_x, 3), round(y0, 3))
    # Visible marker for aligning the right-wall doorway, removed after lookdev.
    if args.get("debug_cut"):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=hero_cut)
        marker = bpy.context.object
        marker.name = "HeroCutMarker"
        marker.scale = (0.38, 0.64, 1.61)
        mat = bpy.data.materials.new("MarkerRed")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (1, 0.05, 0.05, 1)
        em.inputs["Strength"].default_value = 20
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        marker.data.materials.append(mat)
    print("Maze", verts_x, "x", verts_y, "size", round(size_x, 2), "x", round(size_y, 2), "corridor", corridor)
    if args["render"]:
        bpy.ops.render.render(write_still=True)
        print("Rendered", bpy.context.scene.render.filepath)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
