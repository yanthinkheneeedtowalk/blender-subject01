#!/usr/bin/env python3
"""Backrooms blockout. Layout first: thin walls, a long hall, side rooms, 1 m doors.

  blender -b --python scripts/build_backrooms.py -- --fast
  blender -b --python scripts/build_backrooms.py -- --no-render
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "backrooms.blend"
RENDER_DIR = ROOT / "renders"
LAYOUT_PNG = ROOT / "reference" / "backrooms_layout.png"

PIXEL = 0.20
WALL_H = 3.6
CORRIDOR_W = 3.2
ROOM_SPAN = 4.8
DOOR_W = 1.0


def parse_args() -> dict:
    args = {"samples": 24, "resolution": (1280, 720), "render": True, "fast": False}
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
    for img in list(bpy.data.images):
        if img.name not in {"Render Result", "Viewer Node"}:
            bpy.data.images.remove(img)
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


def px(meters: float) -> int:
    return max(1, round(meters / PIXEL))


def build_layout() -> tuple[list[list[float]], float, float]:
    """Floor=1, wall=0. Thin walls, long hall on X, rooms north/south with 1 m doors."""
    length, width = 32.0, 18.0
    tw, th = px(length), px(width)
    img = [[1.0] * tw for _ in range(th)]

    def fill(x0: int, y0: int, x1: int, y1: int, value: float) -> None:
        for y in range(max(0, y0), min(th, y1)):
            row = img[y]
            for x in range(max(0, x0), min(tw, x1)):
                row[x] = value

    # Outer shell, one pixel thick.
    fill(0, 0, tw, 1, 0.0)
    fill(0, th - 1, tw, th, 0.0)
    fill(0, 0, 1, th, 0.0)
    fill(tw - 1, 0, tw, th, 0.0)

    hall_y0 = px((width - CORRIDOR_W) * 0.5)
    hall_y1 = hall_y0 + px(CORRIDOR_W)
    door = px(DOOR_W)
    wall = 1
    span = px(ROOM_SPAN)

    # Long corridor walls (thin), then punch 1 m doors into each bay.
    fill(1, hall_y0 - wall, tw - 1, hall_y0, 0.0)
    fill(1, hall_y1, tw - 1, hall_y1 + wall, 0.0)

    x = span
    bay = 0
    while x < tw - 2:
        fill(x, 1, x + wall, hall_y0 - wall, 0.0)
        fill(x, hall_y1 + wall, x + wall, th - 1, 0.0)
        if bay % 2 == 0:
            mid_n = (1 + hall_y0 - wall) // 2
            mid_s = (hall_y1 + wall + th - 1) // 2
            fill(x, mid_n - door // 2, x + wall, mid_n + door // 2, 1.0)
            fill(x, mid_s - door // 2, x + wall, mid_s + door // 2, 1.0)
        x += span
        bay += 1

    n_bays = max(1, (tw - 2) // span)
    for bay in range(n_bays):
        x0 = 1 + bay * span
        x1 = min(tw - 1, x0 + span)
        if bay % 3 == 2:
            gap = max(door, (x1 - x0) - px(1.6))
            gx = x0 + (x1 - x0 - gap) // 2
            fill(gx, hall_y0 - wall, gx + gap, hall_y0, 1.0)
            fill(gx, hall_y1, gx + gap, hall_y1 + wall, 1.0)
        else:
            dx = x0 + max(0, (x1 - x0 - door) // 2)
            fill(dx, hall_y0 - wall, dx + door, hall_y0, 1.0)
            fill(dx, hall_y1, dx + door, hall_y1 + wall, 1.0)

    fill(1, hall_y0, tw - 1, hall_y1, 1.0)
    return img, length, width


def layout_to_image(pixels: list[list[float]]) -> bpy.types.Image:
    th, tw = len(pixels), len(pixels[0])
    img = bpy.data.images.new("BackroomsLayout", tw, th, alpha=False, float_buffer=True)
    flat: list[float] = []
    for y in range(th):
        for x in range(tw):
            v = pixels[y][x]
            flat.extend((v, v, v, 1.0))
    img.pixels = flat
    img.pack()
    LAYOUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    scale = 8
    preview = bpy.data.images.new("BackroomsLayoutPreview", tw * scale, th * scale, alpha=False)
    big: list[float] = []
    for y in range(th):
        out_row: list[float] = []
        for x in range(tw):
            rgb = (0.86, 0.74, 0.38) if pixels[y][x] > 0.5 else (0.10, 0.09, 0.07)
            out_row.extend((rgb[0], rgb[1], rgb[2], 1.0) * scale)
        for _ in range(scale):
            big.extend(out_row)
    preview.pixels = big
    preview.filepath_raw = str(LAYOUT_PNG)
    preview.file_format = "PNG"
    preview.save()
    bpy.data.images.remove(preview)
    return img


def mat_simple(name: str, color: tuple[float, float, float, float], rough: float, emit: float = 0.0) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if emit > 0:
        node = nt.nodes.new("ShaderNodeEmission")
        node.inputs["Color"].default_value = color
        node.inputs["Strength"].default_value = emit
        nt.links.new(node.outputs["Emission"], out.inputs["Surface"])
    else:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = rough
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _link(ng, a, b):
    ng.links.new(a, b)


def build_geometry_nodes(layout: bpy.types.Image, mats: dict, size_x: float, size_y: float, vx: int, vy: int) -> bpy.types.NodeTree:
    ng = bpy.data.node_groups.new("BackroomsBlockout", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nodes, links = ng.nodes, ng.links
    n_out = nodes.new("NodeGroupOutput")
    n_out.location = (1400, 0)

    grid = nodes.new("GeometryNodeMeshGrid")
    grid.location = (-900, 0)
    grid.inputs["Size X"].default_value = size_x
    grid.inputs["Size Y"].default_value = size_y
    grid.inputs["Vertices X"].default_value = vx
    grid.inputs["Vertices Y"].default_value = vy
    tex = nodes.new("GeometryNodeImageTexture")
    tex.location = (-680, -80)
    tex.interpolation = "Closest"
    tex.extension = "EXTEND"
    tex.inputs["Image"].default_value = layout
    sep = nodes.new("FunctionNodeSeparateColor")
    sep.location = (-460, -80)
    is_path = nodes.new("FunctionNodeCompare")
    is_path.location = (-260, -80)
    is_path.operation = "GREATER_THAN"
    is_path.inputs["B"].default_value = 0.5
    not_path = nodes.new("FunctionNodeBooleanMath")
    not_path.location = (-80, -160)
    not_path.operation = "NOT"
    on_face = nodes.new("GeometryNodeFieldOnDomain")
    on_face.location = (-80, -80)
    on_face.data_type = "BOOLEAN"
    on_face.domain = "FACE"
    _link(ng, grid.outputs["UV Map"], tex.inputs["Vector"])
    _link(ng, tex.outputs["Color"], sep.inputs["Color"] if "Color" in sep.inputs else sep.inputs[0])
    _link(ng, sep.outputs["Red"], is_path.inputs["A"])
    _link(ng, is_path.outputs["Result"], on_face.inputs["Value"])
    _link(ng, on_face.outputs["Value"], not_path.inputs[0])

    def branch(delete_sel, material, loc_y: float, extrude: bool):
        delete = nodes.new("GeometryNodeDeleteGeometry")
        delete.location = (80, loc_y)
        delete.domain = "FACE"
        _link(ng, grid.outputs["Mesh"], delete.inputs["Geometry"])
        _link(ng, delete_sel, delete.inputs["Selection"])
        geo = delete.outputs["Geometry"]
        if extrude:
            ext = nodes.new("GeometryNodeExtrudeMesh")
            ext.location = (280, loc_y)
            ext.mode = "FACES"
            ext.inputs["Individual"].default_value = False
            ext.inputs["Offset Scale"].default_value = WALL_H
            comb = nodes.new("ShaderNodeCombineXYZ")
            comb.location = (80, loc_y - 160)
            comb.inputs["Z"].default_value = 1.0
            _link(ng, geo, ext.inputs["Mesh"])
            _link(ng, comb.outputs["Vector"], ext.inputs["Offset"])
            geo = ext.outputs["Mesh"]
        shade = nodes.new("GeometryNodeSetShadeSmooth")
        shade.location = (500, loc_y)
        shade.inputs["Shade Smooth"].default_value = False
        _link(ng, geo, shade.inputs["Mesh"])
        setm = nodes.new("GeometryNodeSetMaterial")
        setm.location = (700, loc_y)
        imat = nodes.new("GeometryNodeInputMaterial")
        imat.location = (500, loc_y + 120)
        imat.material = material
        _link(ng, shade.outputs["Mesh"], setm.inputs["Geometry"])
        _link(ng, imat.outputs["Material"], setm.inputs["Material"])
        return setm.outputs["Geometry"]

    floor = branch(not_path.outputs["Boolean"], mats["carpet"], 260, False)
    walls = branch(on_face.outputs["Value"], mats["wallpaper"], 0, True)

    join = nodes.new("GeometryNodeJoinGeometry")
    join.location = (1100, 200)
    _link(ng, floor, join.inputs["Geometry"])
    _link(ng, walls, join.inputs["Geometry"])
    _link(ng, join.outputs["Geometry"], n_out.inputs["Geometry"])
    return ng


def add_ceiling(size_x: float, size_y: float, mats: dict) -> bpy.types.Object:
    import bmesh

    sx, sy = size_x * 0.5, size_y * 0.5
    mesh = bpy.data.meshes.new("CeilingMesh")
    mesh.from_pydata(
        [(-sx, -sy, WALL_H), (sx, -sy, WALL_H), (sx, sy, WALL_H), (-sx, sy, WALL_H)],
        [],
        [(0, 3, 2, 1)],
    )
    mesh.update()
    obj = bpy.data.objects.new("Ceiling", mesh)
    obj.data.materials.append(mats["ceiling"])
    bpy.context.scene.collection.objects.link(obj)

    light_mesh = bpy.data.meshes.new("LightsMesh")
    lbm = bmesh.new()
    rng = random.Random(4)
    for x in [i * 4.0 for i in range(-3, 4)]:
        for y in (-6.4, 0.0, 6.4):
            if abs(y) > 0.1 and rng.random() < 0.2:
                continue
            cube = bmesh.ops.create_cube(lbm, size=1.0)
            bmesh.ops.scale(lbm, vec=Vector((1.2, 0.55, 0.06)), verts=cube["verts"])
            bmesh.ops.translate(lbm, vec=Vector((x, y, WALL_H - 0.04)), verts=cube["verts"])
    lbm.to_mesh(light_mesh)
    lbm.free()
    lights = bpy.data.objects.new("Fluorescents", light_mesh)
    lights.data.materials.append(mats["light"])
    bpy.context.scene.collection.objects.link(lights)
    return obj
    hall_y = 0.0
    # Walk view: standing in the hall, looking down its length.
    cam = bpy.data.cameras.new("CameraWalk")
    cam.lens = 28
    cam.clip_end = 80
    obj = bpy.data.objects.new("CameraWalk", cam)
    obj.location = (-size_x * 0.42, hall_y, 1.6)
    target = Vector((size_x * 0.35, hall_y, 1.45))
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.scene.camera = obj

    plan = bpy.data.cameras.new("CameraPlan")
    plan.type = "ORTHO"
    plan.ortho_scale = max(size_x, size_y) * 1.08
    plan.clip_end = 80
    pobj = bpy.data.objects.new("CameraPlan", plan)
    pobj.location = (0.0, 0.0, 28.0)
    pobj.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.scene.collection.objects.link(pobj)


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


def setup_render(args: dict, filepath: Path) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args["samples"]
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "use_adaptive_sampling"):
        scene.cycles.use_adaptive_sampling = True
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 6
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
    scene.view_settings.exposure = 0.1


def render_camera(name: str, path: Path) -> None:
    scene = bpy.context.scene
    scene.camera = bpy.data.objects[name]
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print("Rendered", path)


def main() -> None:
    args = parse_args()
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    clear_scene()
    pixels, size_x, size_y = build_layout()
    layout = layout_to_image(pixels)
    mats = {
        "wallpaper": mat_simple("Wallpaper", srgb(0.66, 0.59, 0.42), 0.74),
        "carpet": mat_simple("Carpet", srgb(0.46, 0.40, 0.24), 0.9),
        "ceiling": mat_simple("Ceiling", srgb(0.78, 0.76, 0.70), 0.86),
        "light": mat_simple("Fluorescent", srgb(0.96, 1.0, 0.82), 0.4, emit=18.0),
    }
    tw, th = len(pixels[0]), len(pixels)
    ng = build_geometry_nodes(layout, mats, size_x, size_y, tw + 1, th + 1)
    mesh = bpy.data.meshes.new("BackroomsMesh")
    obj = bpy.data.objects.new("Backrooms", mesh)
    bpy.context.scene.collection.objects.link(obj)
    mod = obj.modifiers.new("BackroomsGN", "NODES")
    mod.node_group = ng
    add_world()
    add_ceiling(size_x, size_y, mats)
    add_cameras(size_x, size_y)
    setup_render(args, RENDER_DIR / "backrooms.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH, "size", size_x, "x", size_y, "grid", tw, "x", th)
    if args["render"]:
        render_camera("CameraWalk", RENDER_DIR / "backrooms.png")
        for name in ("Ceiling", "Fluorescents"):
            bpy.data.objects[name].hide_render = True
        render_camera("CameraPlan", RENDER_DIR / "backrooms_plan.png")
        for name in ("Ceiling", "Fluorescents"):
            bpy.data.objects[name].hide_render = False
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
