#!/usr/bin/env python3
"""Part 2 static basement — independent working copy only.

Opens part2_basement.blend (a copy of PHASE_1_STABLE). Never writes hallway.blend.
Connects through the existing FINAL_DOOR by opening WALL.End in the copy.
Does not edit CAM_P105_WALK, door actions, lights, or the Part 1 timeline.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SRC_BLEND = ROOT / "part2_basement.blend"
PART1_BLEND = ROOT / "hallway.blend"
OUT_DIR = ROOT / "renders" / "part2_basement"
STILL_DIR = OUT_DIR / "stills"
ARTIFACT = Path("/opt/cursor/artifacts")
REPORT = OUT_DIR / "PART2_BASEMENT_REPORT.md"

# Interior of the storage room, past WALL.End (y=24.0–24.2).
Y0, LENGTH, WIDTH, HEIGHT = 24.22, 5.50, 4.50, 2.50
X0, X1 = -WIDTH / 2.0, WIDTH / 2.0
Y1 = Y0 + LENGTH
WALL_T = 0.18
CEIL_Z = HEIGHT

DOOR_X0, DOOR_X1 = -0.46, 0.46
DOOR_Z1 = 2.08

RNG = random.Random(2202)

COL_ARCH = "P2_ARCH"
COL_FURN = "P2_FURNITURE"
COL_FRAME = "P2_FRAME_CLOTH"
COL_PROPS = "P2_DESK_PROPS"
COL_CLUTTER = "P2_CLUTTER"
COL_CABLES = "P2_CABLES"
COL_LIGHTS = "P2_LIGHTS"
COL_CAMS = "P2_CAMERAS"
COL_CONN = "P2_CONNECTION"


def col(name: str) -> bpy.types.Collection:
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def link(obj: bpy.types.Object, collection: bpy.types.Collection) -> bpy.types.Object:
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def principled(name, color, rough=0.72, spec=0.35, metallic=0.0) -> bpy.types.Material:
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    out.location = (480, 0)
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    bsdf.inputs["Metallic"].default_value = metallic
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def sock(node, ident: str):
    for s in list(node.inputs) + list(node.outputs):
        if s.identifier == ident or s.name == ident:
            return s
    raise KeyError(ident)


def aged_concrete(name: str, seed: float) -> bpy.types.Material:
    mat = principled(name, (0.22, 0.21, 0.19), rough=0.92, spec=0.18)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 38.0 + seed * 4.0
    tex.inputs["Detail"].default_value = 11.0
    tex.inputs["Roughness"].default_value = 0.58
    tex2 = nt.nodes.new("ShaderNodeTexNoise")
    tex2.inputs["Scale"].default_value = 12.0 + seed
    tex2.inputs["Detail"].default_value = 6.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.28
    cr.color_ramp.elements[0].color = (0.09, 0.09, 0.085, 1)
    cr.color_ramp.elements[1].position = 0.72
    cr.color_ramp.elements[1].color = (0.34, 0.32, 0.28, 1)
    extra = cr.color_ramp.elements.new(0.48)
    extra.color = (0.20, 0.205, 0.19, 1)
    damp = nt.nodes.new("ShaderNodeValToRGB")
    damp.color_ramp.elements[0].position = 0.42
    damp.color_ramp.elements[0].color = (0.10, 0.12, 0.11, 1)
    damp.color_ramp.elements[1].color = (1, 1, 1, 1)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    sock(mix, "Factor_Float").default_value = 0.45
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.28
    bump.inputs["Distance"].default_value = 0.04
    coord = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coord.outputs["Generated"], tex.inputs["Vector"])
    nt.links.new(coord.outputs["Generated"], tex2.inputs["Vector"])
    nt.links.new(tex.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(tex2.outputs["Fac"], damp.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], sock(mix, "A_Color"))
    nt.links.new(damp.outputs["Color"], sock(mix, "B_Color"))
    nt.links.new(sock(mix, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def wood_mat(name, color, seed: float) -> bpy.types.Material:
    mat = principled(name, color, rough=0.78, spec=0.22)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapn = nt.nodes.new("ShaderNodeMapping")
    mapn.inputs["Scale"].default_value = (4.0 + seed, 0.35, 1.0)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0 + seed
    noise.inputs["Detail"].default_value = 8.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (color[0] * 0.45, color[1] * 0.42, color[2] * 0.38, 1)
    cr.color_ramp.elements[1].color = (min(color[0] * 1.15, 1), min(color[1] * 1.1, 1), min(color[2] * 1.05, 1), 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    nt.links.new(coord.outputs["Object"], mapn.inputs["Vector"])
    nt.links.new(mapn.outputs["Vector"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def box(name, loc, size, mat, collection, bevel=0.0) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    if bevel > 0:
        mod = obj.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
    return link(obj, collection)


def cylinder(name, loc, radius, depth, mat, collection, verts=12, rot=(0, 0, 0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    return link(obj, collection)


def jitter_rot(obj, ax=0.08, ay=0.08, az=0.35) -> None:
    obj.rotation_euler[0] += RNG.uniform(-ax, ax)
    obj.rotation_euler[1] += RNG.uniform(-ay, ay)
    obj.rotation_euler[2] += RNG.uniform(-az, az)


def apply_eval(obj: bpy.types.Object) -> None:
    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(deps)
    mesh = bpy.data.meshes.new_from_object(eval_obj)
    old = obj.data
    obj.modifiers.clear()
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def punch_wall_end() -> None:
    """Door-sized opening through WALL.End in the copy. Original blend untouched."""
    wall = bpy.data.objects.get("WALL.End")
    if wall is None:
        raise RuntimeError("WALL.End missing")
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 24.1, DOOR_Z1 * 0.5))
    cutter = bpy.context.object
    cutter.name = "P2_WALLEND_CUTTER"
    cutter.scale = ((DOOR_X1 - DOOR_X0) * 0.5 + 0.02, 0.22, DOOR_Z1 * 0.5 + 0.02)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    link(cutter, col(COL_CONN))
    cutter.hide_render = True
    cutter.hide_viewport = True
    mod = wall.modifiers.new("P2_DOOR_OPENING", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    apply_eval(wall)
    recess = bpy.data.objects.get("FINAL_DOOR_RECESS")
    if recess:
        recess.hide_render = True
        recess.hide_viewport = True
        recess.name = "FINAL_DOOR_RECESS_HIDDEN_P2"


def build_shell(mats: dict) -> None:
    c = col(COL_ARCH)
    # Floor / ceiling / walls. South wall only the shoulders beyond the corridor.
    box("P2_FLOOR", (0.0, (Y0 + Y1) * 0.5, -0.09), (WIDTH + 0.36, LENGTH + 0.36, 0.18), mats["floor"], c)
    box("P2_CEIL", (0.0, (Y0 + Y1) * 0.5, HEIGHT + 0.08), (WIDTH + 0.36, LENGTH + 0.36, 0.16), mats["ceil"], c)
    box("P2_WALL_WEST", (X0 - WALL_T * 0.5, (Y0 + Y1) * 0.5, HEIGHT * 0.5), (WALL_T, LENGTH + WALL_T, HEIGHT), mats["wall"], c)
    box("P2_WALL_EAST", (X1 + WALL_T * 0.5, (Y0 + Y1) * 0.5, HEIGHT * 0.5), (WALL_T, LENGTH + WALL_T, HEIGHT), mats["wall"], c)
    box("P2_WALL_NORTH", (0.0, Y1 + WALL_T * 0.5, HEIGHT * 0.5), (WIDTH + WALL_T * 2, WALL_T, HEIGHT), mats["wall"], c)
    # South shoulders beside the corridor end wall.
    west_w = abs(X0) - 1.30
    east_w = X1 - 1.30
    if west_w > 0.05:
        box("P2_WALL_SOUTH_W", (X0 + west_w * 0.5, Y0 - WALL_T * 0.5, HEIGHT * 0.5), (west_w, WALL_T, HEIGHT), mats["wall"], c, 0.004)
    if east_w > 0.05:
        box("P2_WALL_SOUTH_E", (X1 - east_w * 0.5, Y0 - WALL_T * 0.5, HEIGHT * 0.5), (east_w, WALL_T, HEIGHT), mats["wall"], c, 0.004)
    # Threshold strip so the door hole has a floor.
    box("P2_THRESHOLD", (0.0, 24.11, -0.02), (1.05, 0.28, 0.04), mats["floor"], c, 0.002)
    # Ceiling pipes
    pipe = mats["pipe"]
    for i, (x, z, rad, y0, y1) in enumerate((
        (-1.55, 2.32, 0.055, Y0 + 0.2, Y1 - 0.2),
        (1.70, 2.28, 0.042, Y0 + 0.4, Y1 - 0.15),
        (0.85, 2.38, 0.028, Y0 + 1.1, Y0 + 4.2),
    )):
        depth = y1 - y0
        cylinder(f"P2_PIPE_{i:02d}", (x, (y0 + y1) * 0.5, z), rad, depth, pipe, c, 10, rot=(math.pi * 0.5, 0, 0))
    # Old junction box
    box("P2_ELEC_BOX", (-2.08, 25.4, 1.55), (0.18, 0.28, 0.36), mats["metal"], c, 0.004)
    box("P2_ELEC_CONDUIT", (-2.08, 25.4, 2.05), (0.045, 0.045, 0.7), mats["cable"], c)


def build_furniture(mats: dict) -> dict:
    c = col(COL_FURN)
    desk_c = (0.08, 27.22, 0.0)
    desk_top = box("P2_DESK_TOP", (desk_c[0], desk_c[1], 0.73), (1.40, 0.70, 0.04), mats["desk"], c, 0.006)
    for i, (dx, dy) in enumerate(((-0.62, -0.28), (0.62, -0.28), (-0.62, 0.28), (0.62, 0.28))):
        box(f"P2_DESK_LEG_{i}", (desk_c[0] + dx, desk_c[1] + dy, 0.355), (0.055, 0.055, 0.71), mats["desk"], c, 0.003)
    box("P2_DESK_RAIL", (desk_c[0], desk_c[1] - 0.02, 0.16), (1.28, 0.04, 0.04), mats["desk"], c)
    chair_c = (0.04, 26.48, 0.0)
    seat = box("P2_CHAIR_SEAT", (chair_c[0], chair_c[1], 0.455), (0.42, 0.40, 0.04), mats["chair"], c, 0.005)
    for i, (dx, dy) in enumerate(((-0.16, -0.15), (0.16, -0.15), (-0.16, 0.15), (0.16, 0.15))):
        box(f"P2_CHAIR_LEG_{i}", (chair_c[0] + dx, chair_c[1] + dy, 0.225), (0.038, 0.038, 0.45), mats["chair"], c, 0.002)
    box("P2_CHAIR_BACK_L", (chair_c[0] - 0.16, chair_c[1] - 0.18, 0.92), (0.04, 0.035, 0.88), mats["chair"], c, 0.002)
    box("P2_CHAIR_BACK_R", (chair_c[0] + 0.16, chair_c[1] - 0.18, 0.92), (0.04, 0.035, 0.88), mats["chair"], c, 0.002)
    box("P2_CHAIR_SLAT_A", (chair_c[0], chair_c[1] - 0.18, 1.12), (0.34, 0.03, 0.05), mats["chair"], c, 0.002)
    box("P2_CHAIR_SLAT_B", (chair_c[0], chair_c[1] - 0.18, 0.88), (0.34, 0.03, 0.05), mats["chair"], c, 0.002)
    box("P2_CHAIR_SLAT_C", (chair_c[0], chair_c[1] - 0.18, 0.66), (0.34, 0.03, 0.05), mats["chair"], c, 0.002)
    return {"desk": desk_c, "chair": chair_c, "desk_top": desk_top, "seat": seat}


def make_photo_image() -> bpy.types.Image:
    path = OUT_DIR / "p2_photo_blurred.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = 256, 320
    # Blurred unidentifiable figure-like shapes. No identity.
    import numpy as np
    rng = np.random.default_rng(77)
    img = np.zeros((h, w, 3), dtype=np.float64)
    yy, xx = np.mgrid[0:h, 0:w]
    img[..., 0] = 0.16 + 0.05 * np.sin(xx * 0.05 + 0.4)
    img[..., 1] = 0.14 + 0.04 * np.sin(yy * 0.04)
    img[..., 2] = 0.11 + 0.03 * np.cos(xx * 0.03)
    blob = np.exp(-((xx - 128) ** 2 + (yy - 140) ** 2) / 3800)
    img += blob[..., None] * np.array([0.10, 0.08, 0.05])
    vig = 1.0 - 0.55 * (((xx - 128) / 128) ** 2 + ((yy - 160) / 160) ** 2)
    img *= vig[..., None]
    img += rng.normal(0, 0.05, img.shape)
    # Heavy blur
    k = 21
    ker = np.hanning(k)
    ker = ker / ker.sum()
    for c in range(3):
        for i in range(h):
            img[i, :, c] = np.convolve(img[i, :, c], ker, mode="same")
        for j in range(w):
            img[:, j, c] = np.convolve(img[:, j, c], ker, mode="same")
    img = np.clip(img, 0, 1)
    rgba = (np.dstack([img, np.ones((h, w))]) * 255).astype("uint8")
    image = bpy.data.images.new("P2_PHOTO_BLUR", w, h)
    image.pixels = (rgba.astype("float64") / 255.0).flatten().tolist()
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    return image


def build_frame_and_cloth(desk_c, mats: dict) -> None:
    c = col(COL_FRAME)
    # Frame at sit-side of desk, leaving hand space to the right.
    fx, fy, fz = desk_c[0] - 0.22, desk_c[1] - 0.08, 0.89
    root = bpy.data.objects.new("P2_FRAME_ROOT", None)
    root.location = (fx, fy, fz)
    link(root, c)
    outer = box("P2_FRAME_OUTER", (fx, fy, fz), (0.22, 0.028, 0.28), mats["frame"], c, 0.003)
    # Face the sitter (-Y). Glass/dust sit on the south face.
    photo = box("P2_FRAME_PHOTO", (fx, fy - 0.004, fz), (0.15, 0.003, 0.20), mats["photo"], c)
    glass = box("P2_FRAME_GLASS", (fx, fy - 0.010, fz), (0.16, 0.0035, 0.21), mats["glass"], c)
    dust = box("P2_FRAME_DUST", (fx, fy - 0.013, fz), (0.168, 0.0025, 0.218), mats["dust"], c)
    for obj in (outer, glass, photo, dust):
        world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world
    root.rotation_euler = (math.radians(-18.0), 0.0, math.radians(8.0))
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=12, y_subdivisions=10, size=1.0, location=(fx + 0.18, fy - 0.02, 0.754))
    cloth = bpy.context.object
    cloth.name = "P2_CLOTH"
    cloth.scale = (0.13, 0.10, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    mesh = cloth.data
    for v in mesh.vertices:
        v.co.z += 0.012 * math.sin(v.co.x * 28.0) * math.cos(v.co.y * 22.0) + RNG.uniform(-0.004, 0.006)
        v.co.x += RNG.uniform(-0.004, 0.004)
    cloth.rotation_euler = (0.0, 0.0, math.radians(22.0))
    cloth.data.materials.append(mats["cloth"])
    link(cloth, c)


def build_desk_props(desk_c, mats: dict) -> None:
    c = col(COL_PROPS)
    # Leave a clear ~30cm hand zone at desk front-center.
    papers = [
        ((desk_c[0] + 0.48, desk_c[1] + 0.18, 0.753), 0.22),
        ((desk_c[0] + 0.52, desk_c[1] + 0.12, 0.756), -0.40),
    ]
    for i, (loc, rot) in enumerate(papers):
        p = box(f"P2_PAPER_{i}", loc, (0.16, 0.11, 0.002), mats["paper"], c)
        p.rotation_euler[2] = rot
    box("P2_METAL_BRACKET", (desk_c[0] - 0.52, desk_c[1] + 0.22, 0.760), (0.12, 0.04, 0.018), mats["metal"], c, 0.002).rotation_euler[2] = 0.5
    cylinder("P2_BOLT_A", (desk_c[0] - 0.58, desk_c[1] + 0.12, 0.758), 0.012, 0.018, mats["metal"], c, 8)
    cylinder("P2_BOLT_B", (desk_c[0] - 0.54, desk_c[1] + 0.08, 0.758), 0.010, 0.014, mats["metal"], c, 8)
    box("P2_TOOL_PLIERS_BODY", (desk_c[0] + 0.55, desk_c[1] - 0.22, 0.762), (0.18, 0.035, 0.02), mats["metal"], c, 0.002).rotation_euler[2] = -0.7
    box("P2_TOOL_SCREWDRIVER", (desk_c[0] - 0.48, desk_c[1] - 0.24, 0.760), (0.16, 0.018, 0.016), mats["handle"], c, 0.001).rotation_euler[2] = 0.3
    box("P2_RUBBER_GASKET", (desk_c[0] + 0.42, desk_c[1] + 0.02, 0.754), (0.05, 0.05, 0.008), mats["cable"], c)


def snap_ground(obj: bpy.types.Object, z: float = 0.0) -> None:
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    minz = min(c.z for c in corners)
    obj.location.z += z - minz


def cardboard(name, loc_xy, size, mats, collection, z_bottom=0.0, loose=False) -> bpy.types.Object:
    loc = (loc_xy[0], loc_xy[1], z_bottom + size[2] * 0.5)
    obj = box(name, loc, size, mats["cardboard"], collection, 0.003)
    obj.rotation_euler[0] = 0.0
    obj.rotation_euler[1] = 0.0
    obj.rotation_euler[2] = RNG.uniform(-0.28, 0.28)
    snap_ground(obj, z_bottom)
    obj.location.x += RNG.uniform(-0.03, 0.03)
    obj.location.y += RNG.uniform(-0.03, 0.03)
    if loose:
        obj["p2_loose"] = True
    return obj


def build_clutter(mats: dict) -> None:
    c = col(COL_CLUTTER)
    # East clutter wall: stacked columns, floor-snapped, denser than a scatter.
    columns = [
        (1.38, 26.45, [(0.42, 0.36, 0.38), (0.38, 0.34, 0.32), (0.40, 0.30, 0.28)]),
        (1.72, 26.55, [(0.36, 0.32, 0.44), (0.34, 0.30, 0.26)]),
        (1.48, 26.95, [(0.40, 0.34, 0.36), (0.36, 0.32, 0.40), (0.30, 0.28, 0.22)]),
        (1.82, 27.05, [(0.38, 0.36, 0.42), (0.34, 0.30, 0.34)]),
        (1.40, 27.40, [(0.44, 0.38, 0.48), (0.36, 0.32, 0.30)]),
        (1.76, 27.50, [(0.34, 0.32, 0.36), (0.40, 0.34, 0.38), (0.28, 0.26, 0.24)]),
        (1.46, 27.95, [(0.40, 0.36, 0.34), (0.32, 0.30, 0.36)]),
        (1.80, 28.10, [(0.38, 0.34, 0.46), (0.30, 0.28, 0.22)]),
        (1.52, 28.45, [(0.36, 0.34, 0.40), (0.34, 0.30, 0.28)]),
        (1.86, 28.50, [(0.32, 0.30, 0.34)]),
    ]
    n = 0
    for x, y, sizes in columns:
        z = 0.0
        for j, (sx, sy, sz) in enumerate(sizes):
            cardboard(f"P2_BOX_WALL_{n:02d}", (x, y), (sx, sy, sz), mats, c, z_bottom=z, loose=(j == len(sizes) - 1))
            z += sz + 0.004
            n += 1
    # Metal shelf with legs on the floor.
    for i, (dx, dy) in enumerate(((-0.16, -0.46), (0.16, -0.46), (-0.16, 0.46), (0.16, 0.46))):
        box(f"P2_SHELF_LEG_{i}", (1.88 + dx, 27.15 + dy, 0.85), (0.04, 0.04, 1.70), mats["rust"], c, 0.002)
    for i, z in enumerate((0.12, 0.62, 1.12, 1.58)):
        box(f"P2_SHELF_BOARD_{i}", (1.78, 27.15, z), (0.42, 1.05, 0.03), mats["rust"], c, 0.002)
    box("P2_DEAD_DRIVE", (1.72, 27.00, 0.68), (0.18, 0.28, 0.08), mats["plastic"], c, 0.002)
    box("P2_DEAD_PSU", (1.74, 27.40, 0.20), (0.22, 0.30, 0.12), mats["metal"], c, 0.002)
    cylinder("P2_DEAD_FAN", (1.70, 26.90, 1.20), 0.07, 0.04, mats["plastic"], c, 12, rot=(math.pi * 0.5, 0, 0.4))
    west_stacks = [
        (-1.85, 25.15, [(0.40, 0.32, 0.36), (0.32, 0.28, 0.24)]),
        (-1.72, 25.60, [(0.30, 0.34, 0.30)]),
        (-1.90, 26.85, [(0.36, 0.30, 0.40), (0.28, 0.26, 0.22)]),
        (-1.62, 28.55, [(0.42, 0.34, 0.34)]),
        (-1.82, 29.05, [(0.38, 0.38, 0.42), (0.30, 0.28, 0.20)]),
        (-1.95, 27.35, [(0.30, 0.28, 0.28)]),
    ]
    k = 0
    for x, y, sizes in west_stacks:
        z = 0.0
        for sx, sy, sz in sizes:
            cardboard(f"P2_BOX_WEST_{k:02d}", (x, y), (sx, sy, sz), mats, c, z_bottom=z, loose=True)
            z += sz + 0.004
            k += 1
    crate = box("P2_CRATE_PLASTIC", (-1.75, 26.20, 0.16), (0.46, 0.32, 0.28), mats["plastic"], c, 0.004)
    crate.rotation_euler[2] = 0.28
    snap_ground(crate, 0.0)
    box("P2_BROKEN_SEAT", (-1.55, 28.85, 0.03), (0.36, 0.32, 0.05), mats["chair"], c, 0.003)
    snap_ground(bpy.data.objects["P2_BROKEN_SEAT"], 0.0)
    leg = box("P2_BROKEN_LEG", (-1.40, 28.70, 0.04), (0.04, 0.04, 0.36), mats["chair"], c)
    leg.rotation_euler[0] = 1.15
    snap_ground(leg, 0.0)
    nz = 0.0
    for i in range(4):
        sz = RNG.uniform(0.22, 0.36)
        cardboard(
            f"P2_BOX_NORTH_{i:02d}",
            (RNG.uniform(-0.8, 0.6), RNG.uniform(29.10, 29.42)),
            (RNG.uniform(0.30, 0.46), RNG.uniform(0.26, 0.38), sz),
            mats, c, z_bottom=0.0, loose=True,
        )


def bezier_cable(name, pts, radius, mat, collection) -> bpy.types.Object:
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 12
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    curve.fill_mode = "FULL"
    curve.twist_mode = "MINIMUM"
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(pts) - 1)
    for bp, p in zip(spline.bezier_points, pts):
        bp.co = Vector(p)
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
        bp.radius = 1.0
    obj = bpy.data.objects.new(name, curve)
    if mat:
        obj.data.materials.append(mat)
    return link(obj, collection)


def build_cables(mats: dict) -> list[str]:
    c = col(COL_CABLES)
    rig = []
    # Independent editable curves reserved for later climb/wrap.
    paths = [
        ("P2_CABLE_RIG_01", 0.026, [
            (-1.95, 25.35, 0.026), (-1.15, 25.75, 0.022), (-0.35, 26.20, 0.028),
            (0.18, 26.58, 0.024), (0.62, 26.95, 0.020), (1.10, 27.20, 0.026),
        ]),
        ("P2_CABLE_RIG_02", 0.022, [
            (1.50, 26.35, 0.024), (1.05, 26.58, 0.030), (0.48, 26.72, 0.022),
            (0.08, 26.92, 0.026), (-0.32, 27.28, 0.022), (-0.78, 27.78, 0.028),
        ]),
        ("P2_CABLE_RIG_03", 0.030, [
            (-2.02, 27.15, 0.18), (-1.65, 26.85, 0.06), (-1.05, 26.55, 0.028),
            (-0.38, 26.38, 0.024), (0.22, 26.32, 0.026), (0.72, 26.48, 0.022),
        ]),
        ("P2_CABLE_RIG_04", 0.018, [
            (0.52, 27.02, 0.022), (0.18, 26.68, 0.032), (-0.08, 26.42, 0.026),
            (-0.12, 26.18, 0.022), (0.12, 25.88, 0.028), (0.42, 25.48, 0.022),
        ]),
        ("P2_CABLE_RIG_05", 0.024, [
            (1.82, 27.95, 0.026), (1.28, 27.62, 0.032), (0.78, 27.32, 0.022),
            (0.32, 27.08, 0.026), (-0.18, 26.95, 0.022), (-0.68, 26.62, 0.028),
        ]),
        ("P2_CABLE_RIG_06", 0.020, [
            (-1.58, 28.65, 0.024), (-0.98, 28.22, 0.032), (-0.38, 27.85, 0.022),
            (0.12, 27.45, 0.026), (0.48, 27.10, 0.022), (0.88, 26.80, 0.028),
        ]),
    ]
    for name, rad, pts in paths:
        bezier_cable(name, pts, rad, mats["cable"], c)
        rig.append(name)
    fills = [
        [(1.88, 25.15, 0.022), (1.38, 25.55, 0.028), (0.88, 25.82, 0.022), (0.48, 25.42, 0.026), (0.18, 25.05, 0.022)],
        [(-1.88, 29.15, 0.024), (-1.28, 28.82, 0.030), (-0.68, 28.42, 0.022), (-0.18, 28.05, 0.028), (0.28, 27.72, 0.022)],
        [(1.95, 28.72, 0.022), (1.45, 28.95, 0.026), (0.88, 29.15, 0.022), (0.28, 29.32, 0.026)],
        [(-1.78, 24.58, 0.022), (-1.18, 24.88, 0.028), (-0.58, 25.15, 0.022), (0.02, 25.35, 0.026), (0.38, 24.78, 0.022)],
        [(0.88, 26.15, 0.022), (1.18, 25.75, 0.030), (1.48, 25.35, 0.022), (1.82, 24.98, 0.026)],
        [(-0.78, 27.15, 0.022), (-0.28, 27.45, 0.028), (0.22, 27.78, 0.022), (0.58, 28.12, 0.026)],
        [(1.58, 27.75, 0.16), (1.32, 27.42, 0.06), (1.08, 27.12, 0.026), (0.82, 26.82, 0.022)],
        [(-1.98, 26.35, 0.14), (-1.55, 26.05, 0.05), (-1.12, 25.75, 0.026), (-0.68, 25.45, 0.022)],
    ]
    for i, pts in enumerate(fills):
        rad = 0.014 + (i % 4) * 0.003
        bezier_cable(f"P2_CABLE_FILL_{i:02d}", pts, rad, mats["cable"], c)
    return rig


def build_lights() -> None:
    c = col(COL_LIGHTS)
    bpy.ops.object.light_add(type="POINT", location=(0.10, 27.18, 2.22))
    lamp = bpy.context.object
    lamp.name = "LIGHT_P2_DESK_PENDANT"
    lamp.data.color = (1.0, 0.78, 0.48)
    lamp.data.energy = 140.0
    lamp.data.shadow_soft_size = 0.12
    lamp.data.use_shadow = True
    link(lamp, c)
    # Physical fixture
    shade = cylinder("P2_LAMP_SHADE", (0.10, 27.18, 2.32), 0.11, 0.08, principled("MAT_P2_Shade", (0.12, 0.11, 0.09), 0.7), col(COL_ARCH), 16)
    cord = cylinder("P2_LAMP_CORD", (0.10, 27.18, 2.42), 0.008, 0.16, principled("MAT_P2_Cord", (0.04, 0.04, 0.04), 0.6), col(COL_ARCH), 8)
    bpy.ops.object.light_add(type="AREA", location=(0.0, 27.0, 2.42))
    bleed = bpy.context.object
    bleed.name = "LIGHT_P2_ROOM_CONTOUR"
    bleed.data.color = (0.85, 0.72, 0.52)
    bleed.data.energy = 8.5
    bleed.data.size = 1.8
    bleed.data.shape = "DISK"
    bleed.rotation_euler[0] = 0.0
    link(bleed, c)
    bpy.ops.object.light_add(type="POINT", location=(1.68, 27.45, 0.48))
    led = bpy.context.object
    led.name = "LIGHT_P2_PSU_LED"
    led.data.color = (0.35, 0.85, 0.40)
    led.data.energy = 0.45
    led.data.shadow_soft_size = 0.02
    led.data.use_shadow = False
    link(led, c)


def look_at(cam, target) -> None:
    direction = Vector(target) - Vector(cam.location)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def build_cameras(desk_c, chair_c) -> None:
    c = col(COL_CAMS)
    bpy.ops.object.camera_add(location=(chair_c[0] + 0.02, chair_c[1] + 0.08, 1.18))
    sit = bpy.context.object
    sit.name = "CAM_P2_SIT"
    sit.data.lens = 32.0
    sit.data.sensor_width = 36.0
    sit.data.clip_start = 0.05
    sit.data.clip_end = 40.0
    look_at(sit, (desk_c[0] - 0.08, desk_c[1] - 0.04, 0.82))
    link(sit, c)
    bpy.ops.object.camera_add(location=(-1.55, 24.85, 1.55))
    wide = bpy.context.object
    wide.name = "CAM_P2_WIDE"
    wide.data.lens = 22.0
    wide.data.sensor_width = 36.0
    wide.data.clip_start = 0.05
    wide.data.clip_end = 50.0
    look_at(wide, (0.3, 27.4, 0.9))
    link(wide, c)
    bpy.ops.object.camera_add(location=(desk_c[0] + 0.12, desk_c[1] - 0.58, 1.12))
    desk = bpy.context.object
    desk.name = "CAM_P2_DESK"
    desk.data.lens = 35.0
    desk.data.sensor_width = 36.0
    desk.data.clip_start = 0.04
    look_at(desk, (desk_c[0] - 0.10, desk_c[1] - 0.02, 0.84))
    link(desk, c)
    bpy.ops.object.camera_add(location=(0.35, 26.05, 0.55))
    floor = bpy.context.object
    floor.name = "CAM_P2_FLOOR"
    floor.data.lens = 22.0
    floor.data.sensor_width = 36.0
    look_at(floor, (1.25, 27.15, 0.45))
    link(floor, c)
    bpy.ops.object.camera_add(location=(0.0, 21.4, 1.55))
    conn = bpy.context.object
    conn.name = "CAM_P2_CONNECT"
    conn.data.lens = 28.0
    conn.data.sensor_width = 36.0
    look_at(conn, (0.0, 25.6, 1.15))
    link(conn, c)


def configure_preview(scene: bpy.types.Scene) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
    scene.eevee.use_raytracing = True
    scene.eevee.use_fast_gi = True
    scene.eevee.fast_gi_method = "AMBIENT_OCCLUSION_ONLY"
    scene.render.resolution_x = 768
    scene.render.resolution_y = 432
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.use_motion_blur = False
    scene.render.use_compositing = False
    scene.render.filepath = str(STILL_DIR / "preview_")


def mats_all() -> dict:
    photo_img = make_photo_image()
    photo = principled("MAT_P2_Photo", (0.25, 0.22, 0.18), 0.85)
    nt = photo.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = photo_img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    glass = principled("MAT_P2_Glass", (0.55, 0.58, 0.60), 0.12, spec=0.85)
    if "Transmission Weight" in next(n for n in glass.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs:
        next(n for n in glass.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Transmission Weight"].default_value = 0.72
        next(n for n in glass.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Alpha"].default_value = 0.35
        glass.blend_method = "BLEND"
        glass.use_screen_refraction = True
    dust = principled("MAT_P2_Dust", (0.28, 0.26, 0.22), 0.95, spec=0.05)
    dust.blend_method = "BLEND"
    next(n for n in dust.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Alpha"].default_value = 0.62
    cloth = principled("MAT_P2_Cloth", (0.18, 0.17, 0.15), 0.9)
    nt = cloth.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    nse = nt.nodes.new("ShaderNodeTexNoise")
    nse.inputs["Scale"].default_value = 14.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (0.05, 0.055, 0.05, 1)
    cr.color_ramp.elements[1].color = (0.16, 0.14, 0.11, 1)
    nt.links.new(nse.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], bsdf.inputs["Base Color"])
    return {
        "wall": aged_concrete("MAT_P2_Wall", 0.3),
        "floor": aged_concrete("MAT_P2_Floor", 1.1),
        "ceil": aged_concrete("MAT_P2_Ceil", 2.0),
        "desk": wood_mat("MAT_P2_Desk", (0.14, 0.09, 0.055), 0.4),
        "chair": wood_mat("MAT_P2_Chair", (0.11, 0.08, 0.05), 1.6),
        "frame": wood_mat("MAT_P2_Frame", (0.12, 0.08, 0.045), 2.2),
        "cardboard": principled("MAT_P2_Cardboard", (0.32, 0.24, 0.14), 0.88),
        "metal": principled("MAT_P2_Metal", (0.18, 0.18, 0.19), 0.45, metallic=0.55),
        "rust": principled("MAT_P2_Rust", (0.22, 0.10, 0.05), 0.7, metallic=0.25),
        "plastic": principled("MAT_P2_Plastic", (0.12, 0.18, 0.16), 0.55),
        "pipe": principled("MAT_P2_Pipe", (0.16, 0.17, 0.16), 0.5, metallic=0.4),
        "cable": principled("MAT_P2_Cable", (0.03, 0.03, 0.03), 0.62),
        "paper": principled("MAT_P2_Paper", (0.42, 0.38, 0.30), 0.85),
        "handle": principled("MAT_P2_Handle", (0.08, 0.09, 0.10), 0.4, metallic=0.3),
        "glass": glass,
        "photo": photo,
        "dust": dust,
        "cloth": cloth,
    }


def render_stills() -> list[Path]:
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    configure_preview(scene)
    walk = bpy.data.objects.get("CAM_P105_WALK")
    orig_cam = scene.camera
    orig_frame = scene.frame_current
    jobs = [
        ("CAM_P2_WIDE", 1, "01_wide.png"),
        ("CAM_P2_SIT", 1, "02_sit_fps.png"),
        ("CAM_P2_DESK", 1, "03_desk_close.png"),
        ("CAM_P2_FLOOR", 1, "04_cables_clutter.png"),
        ("CAM_P2_CONNECT", 348, "05_connection.png"),
    ]
    paths = []
    for cam_name, frame, fname in jobs:
        cam = bpy.data.objects[cam_name]
        scene.camera = cam
        scene.frame_set(frame)
        path = STILL_DIR / fname
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        dest = ARTIFACT / f"part2_{fname}"
        dest.write_bytes(path.read_bytes())
        paths.append(path)
        print("still", path)
    scene.camera = orig_cam if orig_cam else walk
    scene.frame_set(orig_frame)
    return paths


def write_report(rig_cables: list[str], stills: list[Path]) -> None:
    collections = sorted(n for n in (
        COL_ARCH, COL_FURN, COL_FRAME, COL_PROPS, COL_CLUTTER, COL_CABLES, COL_LIGHTS, COL_CAMS, COL_CONN
    ))
    props = [o.name for o in col(COL_PROPS).objects]
    frames = [o.name for o in col(COL_FRAME).objects]
    cables = [o.name for o in col(COL_CABLES).objects]
    text = f"""# Part 2 basement — static scene report

Part 1 `hallway.blend` was not saved. Working copy: `part2_basement.blend`.
Backup: `renders/checkpoints/part1_pre_part2_hallway.blend`.

## STOP Event

No object or collection named STOP Event was found in the live PHASE_1_STABLE inspect.
`CAM_P105_WALK` keys remain y=1.4 / 14.0 / 18.0. World strength 0.04. Objects 663 before Part 2 build.

## Room size (interior)

- Length (Y): {LENGTH:.2f} m  ({Y0:.2f} → {Y1:.2f})
- Width (X): {WIDTH:.2f} m  ({X0:.2f} → {X1:.2f})
- Height (Z): {HEIGHT:.2f} m
- Single exit through existing `FINAL_DOOR` / punched `WALL.End`

## Connection

Existing end door at y≈23.8 is the only original doorway. Part 2 opens a door-sized hole in `WALL.End` on the copy and hides `FINAL_DOOR_RECESS` so the basement is visible through that door. Corridor walls, floor, camera, door Action, and timeline are not rewritten.

`FINAL_DOOR_HINGEAction` is left intact; the connection still uses frame 348 (half-open) without inserting keys.

## Collections

{chr(10).join(f"- `{n}`" for n in collections)}

## Frame / cloth

{chr(10).join(f"- `{n}`" for n in frames)}

## Desk props (independent meshes)

{chr(10).join(f"- `{n}`" for n in props)}

## Cables reserved for later deformation

{chr(10).join(f"- `{n}`" for n in rig_cables)}

All cables are independent Bezier curves with bevel. Fill cables: {', '.join(cables)}.

## External assets

None. Materials and the blurred photo are original procedural / generated content.

## Known issues

- `WALL.End` boolean is copy-only; original Part 1 mesh is in the backups.
- Glass uses EEVEE blended transmission; scratches are shader roughness, not a normal map atlas.
- No character, no cloth sim, no rigid body, no cable motion.

## Stills

{chr(10).join(f"- `{p}`" for p in stills)}
"""
    REPORT.write_text(text)
    (ARTIFACT / "PART2_BASEMENT_REPORT.md").write_text(text)


def main() -> None:
    if Path(bpy.data.filepath).resolve() == PART1_BLEND.resolve():
        raise SystemExit("refusing to build inside hallway.blend")
    scene = bpy.context.scene
    # Do not change Part 1 frame range / walk camera.
    punch_wall_end()
    mats = mats_all()
    build_shell(mats)
    furn = build_furniture(mats)
    build_frame_and_cloth(furn["desk"], mats)
    build_desk_props(furn["desk"], mats)
    build_clutter(mats)
    rig = build_cables(mats)
    build_lights()
    build_cameras(furn["desk"], furn["chair"])
    stills = render_stills()
    write_report(rig, stills)
    bpy.context.scene.camera = bpy.data.objects.get("CAM_P2_WIDE")
    bpy.ops.wm.save_as_mainfile(filepath=str(SRC_BLEND))
    print("saved", SRC_BLEND)


if __name__ == "__main__":
    main()
