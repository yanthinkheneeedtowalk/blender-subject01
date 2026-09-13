#!/usr/bin/env python3
"""Build a suburban two-story house in Blender, matching reference/house_photo.jpg."""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "house.blend"
RENDER_PATH = ROOT / "renders" / "house_front.png"


def srgb(r: float, g: float, b: float, a: float = 1.0) -> tuple[float, float, float, float]:
    def f(x: float) -> float:
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    return (f(r), f(g), f(b), a)


# Palette sampled from the reference photo (sRGB 0-1).
SIDING = srgb(0.79, 0.73, 0.58)
SIDING_GROOVE = srgb(0.62, 0.56, 0.44)
ROOF = srgb(0.16, 0.17, 0.18)
ROOF_DARK = srgb(0.09, 0.09, 0.10)
SHAKE = srgb(0.52, 0.50, 0.47)
SHAKE_DARK = srgb(0.38, 0.37, 0.35)
SHUTTER = srgb(0.38, 0.10, 0.13)
TRIM = srgb(0.96, 0.95, 0.92)
GLASS = srgb(0.07, 0.09, 0.11)
BRICK = srgb(0.48, 0.23, 0.18)
BRICK_MORTAR = srgb(0.62, 0.50, 0.42)
CONCRETE = srgb(0.74, 0.70, 0.62)
GRASS_A = srgb(0.28, 0.42, 0.10)
GRASS_B = srgb(0.48, 0.52, 0.16)
MULCH = srgb(0.16, 0.09, 0.05)
LEAF_A = srgb(0.14, 0.28, 0.10)
LEAF_B = srgb(0.22, 0.38, 0.12)
LEAF_LIME = srgb(0.55, 0.62, 0.16)
LEAF_BURGUNDY = srgb(0.32, 0.10, 0.12)
SOIL = srgb(0.12, 0.08, 0.05)


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    out = {
        "samples": 96,
        "resolution": (1920, 1280),
        "render": True,
        "engine": "CYCLES",
    }
    i = 0
    while i < len(argv):
        if argv[i] == "--preview":
            out["samples"] = 24
            out["resolution"] = (960, 640)
        elif argv[i] == "--no-render":
            out["render"] = False
        elif argv[i] == "--samples" and i + 1 < len(argv):
            out["samples"] = int(argv[i + 1])
            i += 1
        elif argv[i] == "--engine" and i + 1 < len(argv):
            out["engine"] = argv[i + 1]
            i += 1
        i += 1
    return out


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for datablock in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.curves,
        bpy.data.collections,
        bpy.data.cameras,
        bpy.data.images,
    ):
        for item in list(datablock):
            if item.name == "Render Result":
                continue
            try:
                datablock.remove(item)
            except Exception:
                pass


def new_collection(name: str) -> bpy.types.Collection:
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def link_obj(obj: bpy.types.Object, coll: bpy.types.Collection) -> bpy.types.Object:
    coll.objects.link(obj)
    return obj


def mesh_from_bm(name: str, bm: bmesh.types.BMesh, coll: bpy.types.Collection) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    return link_obj(obj, coll)


def add_box(
    name: str,
    center: tuple[float, float, float],
    dims: tuple[float, float, float],
    coll: bpy.types.Collection,
    mat: bpy.types.Material | None = None,
    rotation: tuple[float, float, float] | None = None,
) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=dims)
    obj = mesh_from_bm(name, bm, coll)
    obj.location = center
    if rotation:
        obj.rotation_euler = rotation
    if mat:
        obj.data.materials.append(mat)
    return obj


def assign_mats(obj: bpy.types.Object, mats: list[bpy.types.Material]) -> None:
    obj.data.materials.clear()
    for mat in mats:
        obj.data.materials.append(mat)


def new_mat(name: str) -> tuple[bpy.types.Material, bpy.types.Node, bpy.types.NodeTree]:
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    if nt is None:
        mat.use_nodes = True
        nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat, bsdf, nt


def mix_rgb(nt: bpy.types.NodeTree, fac=0.5):
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.inputs["Fac"].default_value = fac
    return mix


def set_bsdf(bsdf: bpy.types.Node, **kwargs) -> None:
    mapping = {
        "color": "Base Color",
        "roughness": "Roughness",
        "metallic": "Metallic",
        "specular": "Specular IOR Level",
        "alpha": "Alpha",
        "transmission": "Transmission Weight",
        "ior": "IOR",
        "emission": "Emission Color",
        "emission_strength": "Emission Strength",
        "coat": "Coat Weight",
        "sheen": "Sheen Weight",
    }
    for key, value in kwargs.items():
        socket = mapping[key]
        bsdf.inputs[socket].default_value = value


def mat_siding() -> bpy.types.Material:
    mat, bsdf, nt = new_mat("Siding")
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0, 1.0, 7.5)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.wave_profile = "SAW"
    wave.inputs["Scale"].default_value = 1.0
    wave.inputs["Distortion"].default_value = 0.15
    wave.inputs["Detail"].default_value = 2.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.42
    ramp.color_ramp.elements[0].color = SIDING_GROOVE
    ramp.color_ramp.elements[1].position = 0.58
    ramp.color_ramp.elements[1].color = SIDING
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.012
    nt.links.new(geom.outputs["Position"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_bsdf(bsdf, roughness=0.62, specular=0.35)
    return mat


def mat_shake() -> bpy.types.Material:
    mat, bsdf, nt = new_mat("Shake")
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (6.5, 6.5, 6.5)
    mapping.inputs["Rotation"].default_value = (math.radians(90), 0.0, 0.0)
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.inputs["Color1"].default_value = SHAKE
    brick.inputs["Color2"].default_value = SHAKE_DARK
    brick.inputs["Mortar"].default_value = srgb(0.32, 0.31, 0.29)
    brick.inputs["Scale"].default_value = 2.0
    brick.inputs["Mortar Size"].default_value = 0.012
    brick.inputs["Brick Width"].default_value = 0.5
    brick.inputs["Row Height"].default_value = 0.22
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.4
    nt.links.new(geom.outputs["Position"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(brick.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_bsdf(bsdf, roughness=0.7)
    return mat


def mat_roof() -> bpy.types.Material:
    mat, bsdf, nt = new_mat("RoofShingles")
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (9.0, 9.0, 9.0)
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.inputs["Color1"].default_value = ROOF
    brick.inputs["Color2"].default_value = ROOF_DARK
    brick.inputs["Mortar"].default_value = srgb(0.12, 0.12, 0.13)
    brick.inputs["Scale"].default_value = 3.2
    brick.inputs["Mortar Size"].default_value = 0.018
    brick.inputs["Brick Width"].default_value = 0.5
    brick.inputs["Row Height"].default_value = 0.18
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    mix = mix_rgb(nt, 0.18)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    nt.links.new(geom.outputs["Position"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    nt.links.new(geom.outputs["Position"], noise.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(noise.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(brick.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_bsdf(bsdf, roughness=0.78)
    return mat


def mat_plain(name: str, color, roughness=0.45, metallic=0.0, specular=0.5) -> bpy.types.Material:
    mat, bsdf, _ = new_mat(name)
    set_bsdf(bsdf, color=color, roughness=roughness, metallic=metallic, specular=specular)
    return mat


def mat_glass() -> bpy.types.Material:
    mat, bsdf, _ = new_mat("WindowGlass")
    set_bsdf(
        bsdf,
        color=GLASS,
        roughness=0.05,
        transmission=0.28,
        ior=1.45,
        specular=0.9,
        alpha=1.0,
    )
    if hasattr(mat, "blend_method"):
        try:
            mat.blend_method = "BLEND"
        except TypeError:
            pass
    return mat


def mat_brick() -> bpy.types.Material:
    mat, bsdf, nt = new_mat("Brick")
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (8.0, 8.0, 8.0)
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.inputs["Color1"].default_value = BRICK
    brick.inputs["Color2"].default_value = srgb(0.38, 0.17, 0.14)
    brick.inputs["Mortar"].default_value = BRICK_MORTAR
    brick.inputs["Scale"].default_value = 2.4
    brick.inputs["Mortar Size"].default_value = 0.02
    brick.inputs["Row Height"].default_value = 0.25
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.4
    nt.links.new(geom.outputs["Position"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(brick.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_bsdf(bsdf, roughness=0.72)
    return mat


def mat_grass() -> bpy.types.Material:
    mat, bsdf, nt = new_mat("Grass")
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 12.0
    noise.inputs["Detail"].default_value = 8.0
    noise2 = nt.nodes.new("ShaderNodeTexNoise")
    noise2.inputs["Scale"].default_value = 55.0
    mix = mix_rgb(nt, 0.5)
    mix.inputs["Color1"].default_value = GRASS_A
    mix.inputs["Color2"].default_value = GRASS_B
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(geom.outputs["Position"], noise.inputs["Vector"])
    nt.links.new(geom.outputs["Position"], noise2.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], mix.inputs["Fac"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_bsdf(bsdf, roughness=0.85, sheen=0.2)
    return mat


def mat_mulch() -> bpy.types.Material:
    mat, bsdf, nt = new_mat("Mulch")
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "F1"
    vor.inputs["Scale"].default_value = 28.0
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    mix = mix_rgb(nt, 0.5)
    mix.inputs["Color1"].default_value = MULCH
    mix.inputs["Color2"].default_value = srgb(0.28, 0.16, 0.08)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.55
    nt.links.new(geom.outputs["Position"], vor.inputs["Vector"])
    nt.links.new(geom.outputs["Position"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], mix.inputs["Fac"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_bsdf(bsdf, roughness=0.9)
    return mat


def mat_leaf(name: str, color) -> bpy.types.Material:
    mat, bsdf, nt = new_mat(name)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 9.0
    mix = mix_rgb(nt, 0.5)
    mix.inputs["Color1"].default_value = color
    darker = (color[0] * 0.55, color[1] * 0.55, color[2] * 0.55, 1.0)
    mix.inputs["Color2"].default_value = darker
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    nt.links.new(geom.outputs["Position"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], mix.inputs["Fac"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    set_bsdf(bsdf, roughness=0.7, sheen=0.35)
    return mat


def flip_inward_faces(bm: bmesh.types.BMesh, center: Vector) -> None:
    bm.normal_update()
    for face in bm.faces:
        mid = face.calc_center_median()
        if (mid - center).dot(face.normal) < 0:
            face.normal_flip()
    bm.normal_update()


def add_gabled_volume(
    name: str,
    x: float,
    y: float,
    w: float,
    d: float,
    eave: float,
    peak: float,
    ridge: str,
    coll: bpy.types.Collection,
    wall_mat: bpy.types.Material,
    z0: float = 0.0,
    roof_mat: bpy.types.Material | None = None,
) -> bpy.types.Object:
    bm = bmesh.new()

    def V(co):
        return bm.verts.new(co)

    x0, x1 = x, x + w
    y0, y1 = y, y + d
    xm = (x0 + x1) * 0.5
    ym = (y0 + y1) * 0.5

    b0 = V((x0, y0, z0))
    b1 = V((x1, y0, z0))
    b2 = V((x1, y1, z0))
    b3 = V((x0, y1, z0))
    e0 = V((x0, y0, eave))
    e1 = V((x1, y0, eave))
    e2 = V((x1, y1, eave))
    e3 = V((x0, y1, eave))

    if ridge == "X":
        r0 = V((x0, ym, peak))
        r1 = V((x1, ym, peak))
        bm.faces.new([b0, b1, e1, e0])  # front
        bm.faces.new([b1, b2, e2, e1])  # right
        bm.faces.new([b2, b3, e3, e2])  # back
        bm.faces.new([b3, b0, e0, e3])  # left
        bm.faces.new([e0, e3, r0])  # left gable upper
        bm.faces.new([e1, r1, e2])  # right gable upper
        bm.faces.new([e0, r0, r1, e1])  # front roof
        bm.faces.new([e3, e2, r1, r0])  # back roof
        bm.faces.new([b0, b3, b2, b1])  # bottom
    else:
        r0 = V((xm, y0, peak))
        r1 = V((xm, y1, peak))
        bm.faces.new([b0, b1, e1, e0])  # front lower
        bm.faces.new([e0, e1, r0])  # front gable
        bm.faces.new([b1, b2, e2, e1])  # right
        bm.faces.new([b2, b3, e3, e2])  # back lower
        bm.faces.new([e2, e3, r1])  # back gable
        bm.faces.new([b3, b0, e0, e3])  # left
        bm.faces.new([e0, r0, r1, e3])  # left roof
        bm.faces.new([e1, e2, r1, r0])  # right roof
        bm.faces.new([b0, b3, b2, b1])

    flip_inward_faces(bm, Vector((xm, ym, (z0 + peak) * 0.5)))
    obj = mesh_from_bm(name, bm, coll)
    obj.data.materials.append(wall_mat)
    if roof_mat is not None:
        obj.data.materials.append(roof_mat)
        obj.data.update()
        for poly in obj.data.polygons:
            if poly.normal.z > 0.38:
                poly.material_index = 1
    return obj


def add_roof_shell(
    name: str,
    x: float,
    y: float,
    w: float,
    d: float,
    eave: float,
    peak: float,
    ridge: str,
    coll: bpy.types.Collection,
    roof_mat: bpy.types.Material,
    overhang: float = 0.38,
    thickness: float = 0.11,
) -> bpy.types.Object:
    bm = bmesh.new()
    x0, x1 = x - overhang, x + w + overhang
    y0, y1 = y - overhang, y + d + overhang
    xm = (x + x + w) * 0.5
    ym = (y + y + d) * 0.5
    z = eave + 0.01
    pk = peak + 0.02

    def quad(a, b, c, dlt):
        v0 = bm.verts.new(a)
        v1 = bm.verts.new(b)
        v2 = bm.verts.new(c)
        v3 = bm.verts.new(dlt)
        bm.faces.new([v0, v1, v2, v3])

    if ridge == "X":
        quad((x0, y0, z), (x1, y0, z), (x1, ym, pk), (x0, ym, pk))
        quad((x0, y1, z), (x0, ym, pk), (x1, ym, pk), (x1, y1, z))
    else:
        quad((x0, y0, z), (xm, y0, pk), (xm, y1, pk), (x0, y1, z))
        quad((xm, y0, pk), (x1, y0, z), (x1, y1, z), (xm, y1, pk))

    bm.normal_update()
    for face in bm.faces:
        if face.normal.z < 0:
            face.normal_flip()

    obj = mesh_from_bm(name, bm, coll)
    obj.data.materials.append(roof_mat)
    solid = obj.modifiers.new("Solidify", "SOLIDIFY")
    solid.thickness = thickness
    solid.offset = 1.0
    return obj


def add_trim_board(
    name: str,
    p0: Vector,
    p1: Vector,
    width: float,
    depth: float,
    coll: bpy.types.Collection,
    mat: bpy.types.Material,
) -> bpy.types.Object:
    direction = p1 - p0
    length = max(direction.length, 0.01)
    mid = (p0 + p1) * 0.5
    obj = add_box(name, tuple(mid), (width, depth, length), coll, mat)
    obj.rotation_euler = Vector((0.0, 0.0, 1.0)).rotation_difference(direction.normalized()).to_euler()
    return obj


def add_window(
    name: str,
    cx: float,
    cy: float,
    cz: float,
    coll: bpy.types.Collection,
    mats: dict,
    width: float = 0.82,
    height: float = 1.38,
    shutters: bool = True,
    facing: str = "-Y",
    cols: int = 2,
    rows: int = 2,
) -> None:
    if facing == "-Y":
        axis = "Y"
        sign = -1
        ft = 0.06
        fd = 0.08
        fy = cy + sign * 0.04
        add_box(f"{name}_frame_t", (cx, fy, cz + height / 2), (width + 0.12, fd, ft), coll, mats["trim"])
        add_box(f"{name}_frame_b", (cx, fy, cz - height / 2), (width + 0.12, fd, ft), coll, mats["trim"])
        add_box(f"{name}_frame_l", (cx - width / 2, fy, cz), (ft, fd, height), coll, mats["trim"])
        add_box(f"{name}_frame_r", (cx + width / 2, fy, cz), (ft, fd, height), coll, mats["trim"])
        add_box(
            f"{name}_glass",
            (cx, cy + sign * 0.02, cz),
            (width - 0.04, 0.02, height - 0.04),
            coll,
            mats["glass"],
        )
        add_box(
            f"{name}_back",
            (cx, cy + 0.04, cz),
            (width - 0.06, 0.02, height - 0.06),
            coll,
            mats["interior"],
        )
        add_box(f"{name}_sill", (cx, cy + sign * 0.05, cz - height / 2 - 0.04), (width + 0.2, 0.12, 0.07), coll, mats["trim"])
        add_box(f"{name}_mull_h", (cx, cy + sign * 0.05, cz), (width - 0.08, 0.035, 0.04), coll, mats["trim"])
        add_box(f"{name}_mull_v", (cx, cy + sign * 0.05, cz), (0.04, 0.035, height - 0.08), coll, mats["trim"])
        if shutters:
            sw, st = 0.30, 0.045
            gap = width / 2 + 0.05 + sw / 2
            for side, sx in (("L", cx - gap), ("R", cx + gap)):
                add_box(f"{name}_shutter_{side}", (sx, cy + sign * 0.02, cz), (sw, st, height + 0.04), coll, mats["shutter"])
                add_box(f"{name}_shutter_{side}_bar", (sx, cy + sign * 0.045, cz), (sw * 0.7, 0.02, 0.04), coll, mats["shutter"])
    else:
        raise ValueError(facing)
    _ = (cols, rows, axis)


def add_door(name: str, cx: float, cy: float, coll: bpy.types.Collection, mats: dict) -> None:
    width, height = 1.22, 2.12
    cz = 0.18 + height / 2
    add_box(f"{name}_frame", (cx, cy - 0.03, cz + 0.12), (width + 0.16, 0.1, height + 0.4), coll, mats["trim"])
    add_box(f"{name}_leaf", (cx, cy - 0.05, cz), (width, 0.06, height), coll, mats["trim"])
    add_box(f"{name}_back", (cx, cy + 0.04, cz), (width - 0.1, 0.02, height - 0.1), coll, mats["interior"])
    # two glass panes
    add_box(f"{name}_glass_L", (cx - 0.28, cy - 0.08, cz + 0.05), (0.46, 0.02, 1.55), coll, mats["glass"])
    add_box(f"{name}_glass_R", (cx + 0.28, cy - 0.08, cz + 0.05), (0.46, 0.02, 1.55), coll, mats["glass"])
    add_box(f"{name}_mull", (cx, cy - 0.07, cz + 0.05), (0.05, 0.04, 1.7), coll, mats["trim"])
    # transom
    add_box(f"{name}_transom_glass", (cx, cy - 0.06, cz + height / 2 + 0.18), (width - 0.08, 0.02, 0.28), coll, mats["glass"])
    add_box(f"{name}_transom_bar", (cx, cy - 0.04, cz + height / 2 + 0.18), (0.04, 0.04, 0.28), coll, mats["trim"])


def add_column(name: str, x: float, y: float, z0: float, z1: float, coll, mat) -> None:
    add_box(f"{name}_shaft", (x, y, (z0 + z1) * 0.5), (0.22, 0.22, z1 - z0), coll, mat)
    add_box(f"{name}_base", (x, y, z0 + 0.08), (0.34, 0.34, 0.16), coll, mat)
    add_box(f"{name}_cap", (x, y, z1 - 0.07), (0.34, 0.34, 0.14), coll, mat)


def add_railing(name: str, x0: float, x1: float, y: float, z0: float, coll, mat, n: int = 7) -> None:
    h = 0.88
    add_box(f"{name}_top", ((x0 + x1) * 0.5, y, z0 + h), (abs(x1 - x0), 0.05, 0.05), coll, mat)
    add_box(f"{name}_bot", ((x0 + x1) * 0.5, y, z0 + 0.08), (abs(x1 - x0), 0.04, 0.04), coll, mat)
    for i in range(n):
        t = (i + 0.5) / n
        x = x0 + (x1 - x0) * t
        add_box(f"{name}_bal{i}", (x, y, z0 + h * 0.5), (0.03, 0.03, h), coll, mat)


def add_stairs(name: str, x: float, y_front: float, width: float, coll, mat, steps: int = 4) -> None:
    for i in range(steps):
        depth = 0.32
        rise = 0.16
        cy = y_front - i * depth - depth / 2
        cz = (i + 1) * rise * 0.5 + (steps - 1 - i) * rise * 0.0
        # each step: remaining height from top
        top_z = (steps - i) * rise
        add_box(f"{name}_{i}", (x, cy, top_z / 2), (width + i * 0.02, depth, top_z), coll, mat)


def add_dormer(
    name: str,
    cx: float,
    y_front: float,
    z_base: float,
    coll,
    mats: dict,
    width: float = 1.35,
    depth: float = 1.55,
    wall_h: float = 1.25,
    peak_h: float = 2.05,
) -> None:
    x = cx - width / 2
    add_gabled_volume(
        f"{name}_body",
        x,
        y_front,
        width,
        depth,
        z_base + wall_h,
        z_base + peak_h,
        "Y",
        coll,
        mats["siding"],
        z0=z_base,
        roof_mat=mats["roof"],
    )
    add_roof_shell(
        f"{name}_roof",
        x,
        y_front,
        width,
        depth,
        z_base + wall_h,
        z_base + peak_h,
        "Y",
        coll,
        mats["roof"],
        overhang=0.16,
        thickness=0.08,
    )
    add_window(f"{name}_win", cx, y_front, z_base + 0.72, coll, mats, width=0.7, height=1.05, shutters=False)
    # white bargeboards
    peak = Vector((cx, y_front - 0.18, z_base + peak_h + 0.04))
    e_l = Vector((x - 0.12, y_front - 0.18, z_base + wall_h + 0.02))
    e_r = Vector((x + width + 0.12, y_front - 0.18, z_base + wall_h + 0.02))
    add_trim_board(f"{name}_barge_L", e_l, peak, 0.07, 0.07, coll, mats["trim"])
    add_trim_board(f"{name}_barge_R", e_r, peak, 0.07, 0.07, coll, mats["trim"])


def add_corner_trim(x: float, y: float, z0: float, z1: float, coll, mat, name: str) -> None:
    add_box(name, (x, y, (z0 + z1) * 0.5), (0.12, 0.12, z1 - z0), coll, mat)


def add_shake_triangle(
    name: str,
    x0: float,
    x1: float,
    y: float,
    z_base: float,
    peak: float,
    coll,
    mat,
) -> None:
    xm = (x0 + x1) * 0.5
    bm = bmesh.new()
    v0 = bm.verts.new((x0, y, z_base))
    v1 = bm.verts.new((x1, y, z_base))
    v2 = bm.verts.new((xm, y, peak))
    bm.faces.new([v0, v1, v2])
    obj = mesh_from_bm(name, bm, coll)
    obj.data.materials.append(mat)


def make_bush(name: str, loc, radius: float, height: float, coll, mat, seed: int = 0) -> bpy.types.Object:
    bm = bmesh.new()
    rng = random.Random(seed)
    layers = 7
    for i in range(layers):
        t = i / (layers - 1)
        z = height * (0.18 + 0.62 * t)
        r = radius * (0.45 + 0.55 * math.sin(math.pi * t) ** 0.8)
        matx = (
            Matrix.Translation(
                (
                    rng.uniform(-0.22, 0.22) * radius,
                    rng.uniform(-0.22, 0.22) * radius,
                    z,
                )
            )
            @ Matrix.Diagonal((1.15, 0.9, 0.75, 1.0))
            @ Matrix.Scale(r, 4)
        )
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0, matrix=matx)
    bmesh.ops.translate(bm, verts=bm.verts, vec=loc)
    obj = mesh_from_bm(name, bm, coll)
    obj.data.materials.append(mat)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def make_evergreen(name: str, loc, height: float, radius: float, coll, mat, seed: int = 0) -> bpy.types.Object:
    bm = bmesh.new()
    rng = random.Random(seed)
    layers = 10
    for i in range(layers):
        t = i / (layers - 1)
        z = 0.2 + t * (height - 0.25)
        r = radius * ((1.0 - t * 0.85) ** 0.7)
        r = max(0.22, r)
        offset = Vector((rng.uniform(-0.06, 0.06), rng.uniform(-0.06, 0.06), 0))
        matx = Matrix.Translation((offset.x, offset.y, z)) @ Matrix.Scale(r, 4)
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0, matrix=matx)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.08)
    bmesh.ops.translate(bm, verts=bm.verts, vec=loc)
    obj = mesh_from_bm(name, bm, coll)
    obj.data.materials.append(mat)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def make_arc_walkway(coll, mat) -> None:
    """Flat concrete ribbon from the lawn up to the brick steps."""
    pts = [
        (0.12, -3.45),
        (0.85, -4.15),
        (2.15, -5.10),
        (3.55, -6.40),
        (4.35, -8.20),
        (4.15, -10.40),
        (2.80, -13.20),
        (1.40, -16.00),
    ]
    bm = bmesh.new()
    lefts, rights = [], []
    width = 1.35
    for i, p in enumerate(pts):
        if i == 0:
            tx, ty = pts[1][0] - p[0], pts[1][1] - p[1]
        elif i == len(pts) - 1:
            tx, ty = p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]
        else:
            tx, ty = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        length = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / length, tx / length
        hw = width * 0.5
        lefts.append(bm.verts.new((p[0] + nx * hw, p[1] + ny * hw, 0.035)))
        rights.append(bm.verts.new((p[0] - nx * hw, p[1] - ny * hw, 0.035)))
    for i in range(len(pts) - 1):
        bm.faces.new([lefts[i], lefts[i + 1], rights[i + 1], rights[i]])
    obj = mesh_from_bm("Walkway", bm, coll)
    obj.data.materials.append(mat)
    solid = obj.modifiers.new("Solidify", "SOLIDIFY")
    solid.thickness = 0.05
    solid.offset = 1.0
    add_box("WalkLanding", (0.12, -3.25, 0.03), (2.3, 1.35, 0.05), coll, mat)


def make_mulch_bed(name: str, loc, rx: float, ry: float, coll, mat) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=28, radius=1.0)
    rng = random.Random(hash(name) & 0xFFFF)
    for v in bm.verts:
        v.co.x *= rx * rng.uniform(0.88, 1.08)
        v.co.y *= ry * rng.uniform(0.88, 1.08)
        v.co.z = 0.03
    bmesh.ops.translate(bm, verts=bm.verts, vec=(loc[0], loc[1], 0.0))
    obj = mesh_from_bm(name, bm, coll)
    obj.data.materials.append(mat)
    return obj


def add_world() -> None:
    world = bpy.data.worlds.new("SkyWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    tex = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.1, 1.1, 0.28)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.6
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.5
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.54
    cr.color_ramp.elements[0].color = (0, 0, 0, 1)
    cr.color_ramp.elements[1].position = 0.78
    cr.color_ramp.elements[1].color = (1, 1, 1, 1)
    mix = mix_rgb(nt, 0.0)
    zenith = nt.nodes.new("ShaderNodeRGB")
    zenith.outputs[0].default_value = srgb(0.28, 0.58, 0.92)
    cloud = nt.nodes.new("ShaderNodeRGB")
    cloud.outputs[0].default_value = srgb(0.95, 0.96, 0.98)
    nt.links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(zenith.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(cloud.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(cr.outputs["Color"], mix.inputs["Fac"])
    nt.links.new(mix.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.15
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_sun() -> None:
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 4.8
    sun.angle = math.radians(3.8)
    sun.color = (1.0, 0.96, 0.88)
    obj = bpy.data.objects.new("Sun", sun)
    obj.rotation_euler = (math.radians(52), math.radians(-6), math.radians(38))
    bpy.context.scene.collection.objects.link(obj)
    fill = bpy.data.lights.new("Fill", "AREA")
    fill.energy = 180
    fill.size = 14
    fill.color = (0.65, 0.75, 0.95)
    fill_obj = bpy.data.objects.new("Fill", fill)
    fill_obj.location = (-8, -12, 5)
    fill_obj.rotation_euler = (math.radians(65), 0, math.radians(-25))
    bpy.context.scene.collection.objects.link(fill_obj)


def add_camera() -> bpy.types.Object:
    cam = bpy.data.cameras.new("Camera")
    cam.lens = 38
    cam.sensor_width = 36
    cam.clip_end = 250
    obj = bpy.data.objects.new("Camera", cam)
    obj.location = (0.95, -25.8, 1.48)
    direction = Vector((1.05, 2.2, 4.05)) - Vector(obj.location)
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.scene.camera = obj
    return obj


def setup_render(args: dict) -> None:
    scene = bpy.context.scene
    scene.render.engine = args["engine"]
    scene.render.resolution_x, scene.render.resolution_y = args["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(RENDER_PATH)
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.15
    if args["engine"] == "CYCLES":
        scene.cycles.device = "CPU"
        scene.cycles.samples = args["samples"]
        scene.cycles.use_denoising = True
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
        scene.cycles.max_bounces = 8
        scene.cycles.transparent_max_bounces = 4
        scene.cycles.diffuse_bounces = 4
        scene.cycles.glossy_bounces = 4
        scene.render.threads_mode = "FIXED"
        scene.render.threads = 4
    else:
        eevee = scene.eevee
        if hasattr(eevee, "taa_render_samples"):
            eevee.taa_render_samples = max(32, args["samples"])
        if hasattr(eevee, "use_raytracing"):
            eevee.use_raytracing = True


def build_house(mats: dict, house: bpy.types.Collection) -> None:
    siding, roof, trim = mats["siding"], mats["roof"], mats["trim"]

    # --- Main left+center mass (ridge along X) ---
    add_gabled_volume("MainBody", -9.1, 0.0, 12.2, 8.6, 6.05, 8.15, "X", house, siding, roof_mat=roof)
    add_roof_shell("MainRoof", -9.1, 0.0, 12.2, 8.6, 6.05, 8.15, "X", house, roof, overhang=0.42)

    # Center cross-gable over the porch
    add_gabled_volume("CenterGable", -2.35, -0.12, 4.7, 4.8, 6.05, 8.55, "Y", house, siding, roof_mat=roof)
    add_roof_shell("CenterGableRoof", -2.35, -0.12, 4.7, 4.8, 6.05, 8.55, "Y", house, roof, overhang=0.28)
    peak = Vector((0.0, -0.42, 8.62))
    add_trim_board("CenterBargeL", Vector((-2.55, -0.42, 6.08)), peak, 0.08, 0.08, house, trim)
    add_trim_board("CenterBargeR", Vector((2.55, -0.42, 6.08)), peak, 0.08, 0.08, house, trim)

    # Right street-facing gable wing
    add_gabled_volume("RightWing", 3.05, 0.0, 5.7, 9.0, 6.05, 9.35, "Y", house, siding, roof_mat=roof)
    add_roof_shell("RightWingRoof", 3.05, 0.0, 5.7, 9.0, 6.05, 9.35, "Y", house, roof, overhang=0.4)
    add_shake_triangle("RightShake", 3.12, 8.68, -0.06, 5.55, 9.28, house, mats["shake"])
    rpeak = Vector((5.9, -0.45, 9.42))
    add_trim_board("RightBargeL", Vector((2.72, -0.42, 6.08)), rpeak, 0.09, 0.09, house, trim)
    add_trim_board("RightBargeR", Vector((9.08, -0.42, 6.08)), rpeak, 0.09, 0.09, house, trim)

    # Right one-story bay
    add_gabled_volume("RightBay", 8.7, 0.15, 2.55, 7.4, 3.35, 5.15, "X", house, siding, roof_mat=roof)
    add_roof_shell("RightBayRoof", 8.7, 0.15, 2.55, 7.4, 3.35, 5.15, "X", house, roof, overhang=0.3)

    # White corner boards
    for i, (x, y) in enumerate([(-9.1, 0.0), (3.05, 0.0), (8.75, 0.0), (11.22, 0.15)]):
        add_corner_trim(x, y - 0.02, 0.0, 6.05 if i < 3 else 3.35, house, trim, f"Corner{i}")

    # Foundation strip
    add_box("Foundation", (1.05, 4.3, 0.08), (20.4, 9.2, 0.18), house, mats["brick"])

    # --- Porch ---
    add_box("PorchFloor", (0.05, -1.15, 0.12), (5.15, 2.4, 0.24), house, mats["concrete"])
    add_box("PorchRoof", (0.05, -1.2, 3.18), (5.25, 2.55, 0.28), house, trim)
    add_box("PorchEntablature", (0.05, -2.38, 3.08), (5.25, 0.16, 0.42), house, trim)
    cols_x = (-2.15, -0.72, 0.72, 2.15)
    for i, cx in enumerate(cols_x):
        add_column(f"ColFront{i}", cx, -2.28, 0.24, 3.02, house, trim)
        add_column(f"ColBack{i}", cx, -0.18, 0.24, 3.02, house, trim)
    add_railing("RailL", -2.05, -0.95, -2.38, 0.24, house, trim, n=5)
    add_railing("RailR", 0.95, 2.05, -2.38, 0.24, house, trim, n=5)
    add_stairs("Steps", 0.05, -2.42, 1.85, house, mats["brick"], steps=4)

    # --- Windows & door ---
    # Left ground
    add_window("WinL1", -7.55, 0.0, 1.58, house, mats)
    add_window("WinL2", -4.55, 0.0, 1.58, house, mats)
    # Dormers on front slope of main roof
    # Front slope: y=0 z=6.05 -> y=4.3 z=8.15
    add_dormer("DormerL", -7.55, 0.08, 6.12, house, mats)
    add_dormer("DormerR", -4.55, 0.08, 6.12, house, mats)
    # Porch level
    add_window("WinPorchL", -1.55, 0.0, 1.58, house, mats, width=0.78, height=1.32)
    add_door("FrontDoor", 0.05, 0.0, house, mats)
    add_window("WinPorchR", 1.65, 0.0, 1.58, house, mats, width=0.78, height=1.32)
    # Center second floor
    add_window("WinC1", -0.85, -0.12, 4.62, house, mats)
    add_window("WinC2", 0.95, -0.12, 4.62, house, mats)
    # Right gable 2x2
    add_window("WinRU1", 4.45, 0.0, 4.62, house, mats)
    add_window("WinRU2", 7.25, 0.0, 4.62, house, mats)
    add_window("WinRL1", 4.45, 0.0, 1.58, house, mats)
    add_window("WinRL2", 7.25, 0.0, 1.58, house, mats)
    # Right bay
    add_window("WinBay", 9.95, 0.15, 1.55, house, mats, width=0.78, height=1.3)

    # Porch lanterns
    for i, x in enumerate((-0.55, 0.65)):
        add_box(f"Lantern{i}", (x, -0.12, 2.55), (0.12, 0.12, 0.22), house, mats["lantern"])


def build_landscape(mats: dict, land: bpy.types.Collection) -> None:
    add_box("Lawn", (1.0, -4.0, -0.04), (48.0, 42.0, 0.08), land, mats["grass"])
    make_arc_walkway(land, mats["concrete"])
    # Mulch beds along the facade
    make_mulch_bed("MulchFrontL", (-5.4, -1.2), 3.6, 0.95, land, mats["mulch"])
    make_mulch_bed("MulchIsland", (2.4, -4.7), 2.3, 1.45, land, mats["mulch"])
    make_mulch_bed("MulchRight", (8.6, -1.45), 2.6, 1.1, land, mats["mulch"])
    make_mulch_bed("MulchLeftEnd", (-9.8, -1.35), 1.4, 1.2, land, mats["mulch"])

    # Evergreens framing the house
    make_evergreen("TreeL1", (-10.2, -2.6, 0), 4.8, 1.45, land, mats["leaf"], seed=3)
    make_evergreen("TreeL2", (-8.5, -3.2, 0), 4.1, 1.25, land, mats["leaf"], seed=7)
    make_evergreen("TreeR1", (11.7, -2.3, 0), 6.0, 2.05, land, mats["leaf"], seed=11)
    # Background tree line
    for i, x in enumerate([-16, -13, -11, 13, 16, 18, -18, 20]):
        make_evergreen(f"BgTree{i}", (x, 10 + (i % 3) * 1.4, 0), 7.5 + (i % 4), 2.2, land, mats["leaf_dark"], seed=20 + i)

    # Shrubs
    make_bush("HedgeL1", (-7.6, -1.15, 0), 0.7, 0.85, land, mats["leaf"], 1)
    make_bush("HedgeL2", (-5.9, -1.2, 0), 0.65, 0.8, land, mats["leaf"], 2)
    make_bush("HedgeL3", (-4.4, -1.1, 0), 0.7, 0.9, land, mats["leaf"], 3)
    make_bush("HedgeDoorL", (-2.0, -1.15, 0), 0.55, 0.7, land, mats["leaf"], 4)
    make_bush("Maple", (1.7, -4.35, 0), 0.8, 1.05, land, mats["leaf_burgundy"], 5)
    make_bush("Lime1", (3.2, -4.5, 0), 0.65, 0.7, land, mats["leaf_lime"], 6)
    make_bush("Lime2", (4.4, -4.15, 0), 0.6, 0.68, land, mats["leaf_lime"], 7)
    make_bush("Lime3", (6.3, -1.35, 0), 0.6, 0.65, land, mats["leaf_lime"], 8)
    make_bush("HedgeR1", (8.3, -1.4, 0), 0.7, 0.85, land, mats["leaf"], 9)
    make_bush("HedgeR2", (10.0, -1.5, 0), 0.8, 0.95, land, mats["leaf"], 10)


def build_materials() -> dict:
    return {
        "siding": mat_siding(),
        "shake": mat_shake(),
        "roof": mat_roof(),
        "trim": mat_plain("Trim", TRIM, roughness=0.38),
        "shutter": mat_plain("Shutter", SHUTTER, roughness=0.55),
        "glass": mat_glass(),
        "brick": mat_brick(),
        "concrete": mat_plain("Concrete", CONCRETE, roughness=0.7),
        "grass": mat_grass(),
        "mulch": mat_mulch(),
        "leaf": mat_leaf("Leaf", LEAF_A),
        "leaf_dark": mat_leaf("LeafDark", srgb(0.08, 0.16, 0.06)),
        "leaf_lime": mat_leaf("LeafLime", LEAF_LIME),
        "leaf_burgundy": mat_leaf("LeafBurgundy", LEAF_BURGUNDY),
        "lantern": mat_plain("Lantern", srgb(0.08, 0.08, 0.08), roughness=0.25, metallic=0.6),
        "soil": mat_plain("Soil", SOIL, roughness=0.9),
        "interior": mat_plain("Interior", srgb(0.10, 0.11, 0.13), roughness=0.9),
    }


def main() -> None:
    args = parse_args()
    RENDER_PATH.parent.mkdir(parents=True, exist_ok=True)
    clear_scene()
    house = new_collection("House")
    land = new_collection("Landscape")
    mats = build_materials()
    build_house(mats, house)
    build_landscape(mats, land)
    add_world()
    add_sun()
    add_camera()
    setup_render(args)

    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print(f"Saved {BLEND_PATH}")
    if args["render"]:
        bpy.ops.render.render(write_still=True)
        print(f"Rendered {RENDER_PATH}")
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


if __name__ == "__main__":
    main()
