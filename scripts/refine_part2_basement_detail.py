#!/usr/bin/env python3
"""In-place static detail pass for part2_basement.blend.

Never writes hallway.blend. Does not edit CAM_P105_WALK, door actions,
RIG cables 01-06 spline data, or any character / story animation.
"""

from __future__ import annotations

import json
import math
import random
import shutil
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND = ROOT / "part2_basement.blend"
PART1 = ROOT / "hallway.blend"
OUT_DIR = ROOT / "renders" / "part2_basement"
STILL_DIR = OUT_DIR / "stills"
ARTIFACT = Path("/opt/cursor/artifacts")
REPORT = OUT_DIR / "PART2_BASEMENT_DETAIL_REPORT.md"
CHECKPOINT = ROOT / "renders" / "checkpoints" / "part2_basement_detail.blend"
QA_JSON = OUT_DIR / "detail_qa.json"

Y0, LENGTH, WIDTH, HEIGHT = 24.22, 5.50, 4.50, 2.50
X0, X1 = -WIDTH / 2.0, WIDTH / 2.0
Y1 = Y0 + LENGTH

DESK = (0.08, 27.22, 0.0)
CHAIR = (0.04, 26.48, 0.0)
DESK_TOP_Z = 0.75

RNG = random.Random(3303)

COL_ARCH = "P2_ARCH"
COL_FURN = "P2_FURNITURE"
COL_FRAME = "P2_FRAME_CLOTH"
COL_PROPS = "P2_DESK_PROPS"
COL_CLUTTER = "P2_CLUTTER"
COL_CABLES = "P2_CABLES"
COL_LIGHTS = "P2_LIGHTS"
COL_CAMS = "P2_CAMERAS"

RIG_NAMES = [f"P2_CABLE_RIG_{i:02d}" for i in range(1, 7)]


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


def sock(node, ident: str):
    for s in list(node.inputs) + list(node.outputs):
        if s.identifier == ident or s.name == ident:
            return s
    raise KeyError(ident)


def select_only(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def delete_object(obj: bpy.types.Object) -> None:
    mesh = obj.data if obj.type in {"MESH", "CURVE"} else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        if isinstance(mesh, bpy.types.Mesh):
            bpy.data.meshes.remove(mesh)
        elif isinstance(mesh, bpy.types.Curve):
            bpy.data.curves.remove(mesh)


def snap_ground(obj: bpy.types.Object, z: float = 0.0) -> None:
    deps = bpy.context.evaluated_depsgraph_get()
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    minz = min(c.z for c in corners)
    obj.location.z += z - minz


def principled(name, color, rough=0.72, spec=0.35, metallic=0.0) -> bpy.types.Material:
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (280, 0)
    out.location = (560, 0)
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    bsdf.inputs["Metallic"].default_value = metallic
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
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
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=radius, depth=depth, location=loc, rotation=rot
    )
    obj = bpy.context.object
    obj.name = name
    if mat:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    return link(obj, collection)


def apply_modifiers(obj: bpy.types.Object) -> None:
    select_only(obj)
    deps = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(deps)
    mesh = bpy.data.meshes.new_from_object(eval_obj)
    old = obj.data
    obj.modifiers.clear()
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def mesh_from_bm(name, bm, mat, collection, loc=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    if mat:
        mesh.materials.append(mat)
    return link(obj, collection)


def capture_rig_cables() -> dict:
    out = {}
    for name in RIG_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "CURVE":
            out[name] = None
            continue
        pts = []
        for sp in obj.data.splines:
            for bp in sp.bezier_points:
                pts.append([round(bp.co.x, 5), round(bp.co.y, 5), round(bp.co.z, 5)])
        out[name] = {"bevel": round(obj.data.bevel_depth, 5), "points": pts}
    return out


def look_at(cam, target) -> None:
    direction = Vector(target) - Vector(cam.location)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def rebuild_concrete(name: str, seed: float, vertical: bool) -> bpy.types.Material:
    mat = principled(name, (0.20, 0.19, 0.17), rough=0.94, spec=0.12)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    if vertical:
        mapping.inputs["Scale"].default_value = (1.0, 0.22 + seed * 0.05, 1.35)
    else:
        mapping.inputs["Scale"].default_value = (1.15, 1.0, 0.18)

    n_large = nt.nodes.new("ShaderNodeTexNoise")
    n_large.inputs["Scale"].default_value = 3.4 + seed
    n_large.inputs["Detail"].default_value = 9.0
    n_large.inputs["Roughness"].default_value = 0.62

    n_grit = nt.nodes.new("ShaderNodeTexNoise")
    n_grit.inputs["Scale"].default_value = 62.0 + seed * 6.0
    n_grit.inputs["Detail"].default_value = 12.0
    n_grit.inputs["Roughness"].default_value = 0.72

    n_damp = nt.nodes.new("ShaderNodeTexNoise")
    n_damp.inputs["Scale"].default_value = 2.1 + seed * 0.4
    n_damp.inputs["Detail"].default_value = 7.0
    n_damp.inputs["Roughness"].default_value = 0.48

    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = 4.2 + seed * 0.4
    vor.inputs["Randomness"].default_value = 0.85

    crack = nt.nodes.new("ShaderNodeValToRGB")
    crack.color_ramp.elements[0].position = 0.0
    crack.color_ramp.elements[0].color = (0.06, 0.055, 0.05, 1)
    crack.color_ramp.elements[1].position = 0.012
    crack.color_ramp.elements[1].color = (1, 1, 1, 1)

    col_dry = nt.nodes.new("ShaderNodeValToRGB")
    col_dry.color_ramp.elements[0].position = 0.22
    col_dry.color_ramp.elements[0].color = (0.10, 0.10, 0.09, 1)
    col_dry.color_ramp.elements[1].position = 0.78
    col_dry.color_ramp.elements[1].color = (0.31, 0.29, 0.24, 1)
    mid = col_dry.color_ramp.elements.new(0.48)
    mid.color = (0.19, 0.185, 0.17, 1)

    damp_mask = nt.nodes.new("ShaderNodeValToRGB")
    damp_mask.color_ramp.elements[0].position = 0.38
    damp_mask.color_ramp.elements[0].color = (0.07, 0.09, 0.08, 1)
    damp_mask.color_ramp.elements[1].position = 0.72
    damp_mask.color_ramp.elements[1].color = (1, 1, 1, 1)

    mix_damp = nt.nodes.new("ShaderNodeMix")
    mix_damp.data_type = "RGBA"
    mix_damp.blend_type = "MULTIPLY"
    sock(mix_damp, "Factor_Float").default_value = 0.55

    mix_crack = nt.nodes.new("ShaderNodeMix")
    mix_crack.data_type = "RGBA"
    mix_crack.blend_type = "MULTIPLY"
    sock(mix_crack, "Factor_Float").default_value = 0.18

    grit_mix = nt.nodes.new("ShaderNodeMix")
    grit_mix.data_type = "RGBA"
    grit_mix.blend_type = "MULTIPLY"
    sock(grit_mix, "Factor_Float").default_value = 0.22

    rough_map = nt.nodes.new("ShaderNodeValToRGB")
    rough_map.color_ramp.elements[0].position = 0.30
    rough_map.color_ramp.elements[0].color = (0.42, 0.42, 0.42, 1)
    rough_map.color_ramp.elements[1].position = 0.85
    rough_map.color_ramp.elements[1].color = (0.96, 0.96, 0.96, 1)

    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.012

    bump2 = nt.nodes.new("ShaderNodeBump")
    bump2.inputs["Strength"].default_value = 0.18
    bump2.inputs["Distance"].default_value = 0.008

    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], n_large.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], n_damp.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n_grit.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    nt.links.new(n_large.outputs["Fac"], col_dry.inputs["Fac"])
    nt.links.new(n_damp.outputs["Fac"], damp_mask.inputs["Fac"])
    nt.links.new(vor.outputs["Distance"], crack.inputs["Fac"])
    nt.links.new(col_dry.outputs["Color"], sock(mix_damp, "A_Color"))
    nt.links.new(damp_mask.outputs["Color"], sock(mix_damp, "B_Color"))
    nt.links.new(sock(mix_damp, "Result_Color"), sock(mix_crack, "A_Color"))
    nt.links.new(crack.outputs["Color"], sock(mix_crack, "B_Color"))
    nt.links.new(sock(mix_crack, "Result_Color"), sock(grit_mix, "A_Color"))
    nt.links.new(n_grit.outputs["Fac"], sock(grit_mix, "B_Color"))
    nt.links.new(sock(grit_mix, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(n_damp.outputs["Fac"], rough_map.inputs["Fac"])
    nt.links.new(rough_map.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bump2.inputs["Normal"])
    nt.links.new(n_grit.outputs["Fac"], bump2.inputs["Height"])
    nt.links.new(bump2.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def rebuild_wood(name: str, color, seed: float, dusty: bool) -> bpy.types.Material:
    mat = principled(name, color, rough=0.82, spec=0.18)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapn = nt.nodes.new("ShaderNodeMapping")
    mapn.inputs["Scale"].default_value = (5.4 + seed, 0.28, 1.0)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 16.0 + seed
    noise.inputs["Detail"].default_value = 10.0
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 48.0 + seed * 4.0
    wave.inputs["Distortion"].default_value = 4.5
    wave.inputs["Detail"].default_value = 6.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (color[0] * 0.38, color[1] * 0.36, color[2] * 0.32, 1)
    cr.color_ramp.elements[1].color = (
        min(color[0] * 1.18, 1),
        min(color[1] * 1.12, 1),
        min(color[2] * 1.05, 1),
        1,
    )
    scratch = nt.nodes.new("ShaderNodeValToRGB")
    scratch.color_ramp.elements[0].position = 0.46
    scratch.color_ramp.elements[0].color = (0.07, 0.06, 0.05, 1)
    scratch.color_ramp.elements[1].position = 0.52
    scratch.color_ramp.elements[1].color = (1, 1, 1, 1)
    mix_s = nt.nodes.new("ShaderNodeMix")
    mix_s.data_type = "RGBA"
    mix_s.blend_type = "MULTIPLY"
    sock(mix_s, "Factor_Float").default_value = 0.28
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    nt.links.new(coord.outputs["Object"], mapn.inputs["Vector"])
    nt.links.new(mapn.outputs["Vector"], noise.inputs["Vector"])
    nt.links.new(mapn.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(wave.outputs["Fac"], scratch.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], sock(mix_s, "A_Color"))
    nt.links.new(scratch.outputs["Color"], sock(mix_s, "B_Color"))
    if dusty:
        dust_n = nt.nodes.new("ShaderNodeTexNoise")
        dust_n.inputs["Scale"].default_value = 9.5
        dust_n.inputs["Detail"].default_value = 8.0
        dust_cr = nt.nodes.new("ShaderNodeValToRGB")
        dust_cr.color_ramp.elements[0].position = 0.40
        dust_cr.color_ramp.elements[0].color = (0.34, 0.31, 0.26, 1)
        dust_cr.color_ramp.elements[1].position = 0.78
        dust_cr.color_ramp.elements[1].color = (1, 1, 1, 1)
        mix_d = nt.nodes.new("ShaderNodeMix")
        mix_d.data_type = "RGBA"
        mix_d.blend_type = "MULTIPLY"
        sock(mix_d, "Factor_Float").default_value = 0.38
        nt.links.new(coord.outputs["Object"], dust_n.inputs["Vector"])
        nt.links.new(dust_n.outputs["Fac"], dust_cr.inputs["Fac"])
        nt.links.new(sock(mix_s, "Result_Color"), sock(mix_d, "A_Color"))
        nt.links.new(dust_cr.outputs["Color"], sock(mix_d, "B_Color"))
        nt.links.new(sock(mix_d, "Result_Color"), bsdf.inputs["Base Color"])
    else:
        nt.links.new(sock(mix_s, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.86
    return mat


def rebuild_cardboard() -> bpy.types.Material:
    mat = principled("MAT_P2_Cardboard", (0.30, 0.22, 0.13), rough=0.90, spec=0.08)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    info = nt.nodes.new("ShaderNodeObjectInfo")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 14.0
    n1.inputs["Detail"].default_value = 10.0
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 48.0
    n2.inputs["Detail"].default_value = 6.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.18
    cr.color_ramp.elements[0].color = (0.16, 0.11, 0.06, 1)
    cr.color_ramp.elements[1].position = 0.82
    cr.color_ramp.elements[1].color = (0.42, 0.32, 0.18, 1)
    extra = cr.color_ramp.elements.new(0.48)
    extra.color = (0.28, 0.21, 0.12, 1)
    mix_r = nt.nodes.new("ShaderNodeMix")
    mix_r.data_type = "RGBA"
    mix_r.blend_type = "MIX"
    sock(mix_r, "Factor_Float").default_value = 0.35
    tint = nt.nodes.new("ShaderNodeValToRGB")
    tint.color_ramp.elements[0].color = (0.72, 0.62, 0.42, 1)
    tint.color_ramp.elements[1].color = (1.15, 1.0, 0.88, 1)
    mix_t = nt.nodes.new("ShaderNodeMix")
    mix_t.data_type = "RGBA"
    mix_t.blend_type = "MULTIPLY"
    sock(mix_t, "Factor_Float").default_value = 0.45
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.26
    nt.links.new(coord.outputs["Object"], n1.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n2.inputs["Vector"])
    nt.links.new(n1.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(info.outputs["Random"], tint.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], sock(mix_t, "A_Color"))
    nt.links.new(tint.outputs["Color"], sock(mix_t, "B_Color"))
    nt.links.new(sock(mix_t, "Result_Color"), sock(mix_r, "A_Color"))
    nt.links.new(n2.outputs["Fac"], sock(mix_r, "B_Color"))
    sock(mix_r, "Factor_Float").default_value = 0.18
    nt.links.new(sock(mix_r, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def rebuild_tape() -> bpy.types.Material:
    return principled("MAT_P2_Tape", (0.42, 0.32, 0.12), rough=0.48, spec=0.28)


def rebuild_cable() -> bpy.types.Material:
    mat = principled("MAT_P2_Cable", (0.018, 0.018, 0.02), rough=0.58, spec=0.22)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 38.0
    n.inputs["Detail"].default_value = 5.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (0.01, 0.01, 0.012, 1)
    cr.color_ramp.elements[1].color = (0.05, 0.05, 0.055, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(coord.outputs["Object"], n.inputs["Vector"])
    nt.links.new(n.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.64
    return mat


def rebuild_glass() -> bpy.types.Material:
    mat = principled("MAT_P2_Glass", (0.62, 0.64, 0.66), rough=0.18, spec=0.85)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.78
    bsdf.inputs["Alpha"].default_value = 0.28
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    if hasattr(mat, "use_screen_refraction"):
        mat.use_screen_refraction = True
    if hasattr(mat, "surface_render_method"):
        try:
            mat.surface_render_method = "BLENDED"
        except TypeError:
            pass
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapn = nt.nodes.new("ShaderNodeMapping")
    mapn.inputs["Scale"].default_value = (28.0, 0.45, 6.0)
    mapn.inputs["Rotation"].default_value = (0.0, 0.0, 0.35)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.inputs["Scale"].default_value = 22.0
    wave.inputs["Distortion"].default_value = 8.0
    wave.inputs["Detail"].default_value = 4.0
    nse = nt.nodes.new("ShaderNodeTexNoise")
    nse.inputs["Scale"].default_value = 70.0
    nse.inputs["Detail"].default_value = 8.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.42
    cr.color_ramp.elements[0].color = (0.08, 0.08, 0.08, 1)
    cr.color_ramp.elements[1].position = 0.58
    cr.color_ramp.elements[1].color = (0.55, 0.55, 0.55, 1)
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MAXIMUM"
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.0015
    nt.links.new(coord.outputs["Object"], mapn.inputs["Vector"])
    nt.links.new(mapn.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], nse.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], mix.inputs[0])
    nt.links.new(nse.outputs["Fac"], mix.inputs[1])
    nt.links.new(mix.outputs["Value"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(mix.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def rebuild_dust() -> bpy.types.Material:
    mat = principled("MAT_P2_Dust", (0.30, 0.27, 0.22), rough=0.98, spec=0.02)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    if hasattr(mat, "blend_method"):
        mat.blend_method = "BLEND"
    if hasattr(mat, "surface_render_method"):
        try:
            mat.surface_render_method = "BLENDED"
        except TypeError:
            pass
    coord = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 6.5
    n1.inputs["Detail"].default_value = 10.0
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 22.0
    n2.inputs["Detail"].default_value = 8.0
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    # Corner-heavy vignette in generated UV-like space.
    math_x = nt.nodes.new("ShaderNodeMath")
    math_x.operation = "ABSOLUTE"
    math_z = nt.nodes.new("ShaderNodeMath")
    math_z.operation = "ABSOLUTE"
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    cr_a = nt.nodes.new("ShaderNodeValToRGB")
    cr_a.color_ramp.elements[0].position = 0.12
    cr_a.color_ramp.elements[0].color = (0.12, 0.12, 0.12, 0.18)
    cr_a.color_ramp.elements[1].position = 0.78
    cr_a.color_ramp.elements[1].color = (1, 1, 1, 0.92)
    mid = cr_a.color_ramp.elements.new(0.42)
    mid.color = (0.55, 0.52, 0.46, 0.55)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.45
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(coord.outputs["Generated"], n1.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n2.inputs["Vector"])
    nt.links.new(sep.outputs["X"], math_x.inputs[0])
    nt.links.new(sep.outputs["Z"], math_z.inputs[0])
    nt.links.new(math_x.outputs["Value"], add.inputs[0])
    nt.links.new(math_z.outputs["Value"], add.inputs[1])
    nt.links.new(add.outputs["Value"], cr_a.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY"
    nt.links.new(cr_a.outputs["Color"], mix.inputs[0])
    nt.links.new(n1.outputs["Fac"], mix.inputs[1])
    nt.links.new(mix.outputs["Value"], bsdf.inputs["Alpha"])
    colmix = nt.nodes.new("ShaderNodeMix")
    colmix.data_type = "RGBA"
    sock(colmix, "Factor_Float").default_value = 0.4
    sock(colmix, "A_Color").default_value = (0.33, 0.30, 0.24, 1)
    sock(colmix, "B_Color").default_value = (0.18, 0.16, 0.13, 1)
    nt.links.new(n2.outputs["Fac"], sock(colmix, "Factor_Float"))
    nt.links.new(sock(colmix, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(n1.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def rebuild_cloth() -> bpy.types.Material:
    mat = principled("MAT_P2_Cloth", (0.16, 0.15, 0.13), rough=0.92, spec=0.06)
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 11.0
    n1.inputs["Detail"].default_value = 12.0
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 28.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.22
    cr.color_ramp.elements[0].color = (0.05, 0.055, 0.048, 1)
    cr.color_ramp.elements[1].position = 0.80
    cr.color_ramp.elements[1].color = (0.22, 0.20, 0.16, 1)
    stain = cr.color_ramp.elements.new(0.40)
    stain.color = (0.10, 0.09, 0.07, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.55
    bump.inputs["Distance"].default_value = 0.006
    nt.links.new(coord.outputs["Object"], n1.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n2.inputs["Vector"])
    nt.links.new(n1.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def extra_mats() -> dict:
    return {
        "tape": rebuild_tape(),
        "interior": principled("MAT_P2_BoxInterior", (0.10, 0.08, 0.05), 0.95, spec=0.04),
        "rust": bpy.data.materials.get("MAT_P2_Rust")
        or principled("MAT_P2_Rust", (0.22, 0.10, 0.05), 0.74, metallic=0.22),
        "metal": bpy.data.materials.get("MAT_P2_Metal")
        or principled("MAT_P2_Metal", (0.16, 0.16, 0.17), 0.48, metallic=0.55),
        "plastic": bpy.data.materials.get("MAT_P2_Plastic")
        or principled("MAT_P2_Plastic", (0.12, 0.18, 0.16), 0.58),
        "plastic_b": principled("MAT_P2_PlasticGrey", (0.18, 0.17, 0.16), 0.62),
        "plastic_c": principled("MAT_P2_PlasticBlue", (0.08, 0.12, 0.18), 0.55),
        "paper": bpy.data.materials.get("MAT_P2_Paper")
        or principled("MAT_P2_Paper", (0.40, 0.36, 0.28), 0.88),
        "handle": bpy.data.materials.get("MAT_P2_Handle")
        or principled("MAT_P2_Handle", (0.08, 0.09, 0.10), 0.42, metallic=0.3),
        "chair": bpy.data.materials.get("MAT_P2_Chair"),
        "cable": bpy.data.materials.get("MAT_P2_Cable"),
        "cardboard": bpy.data.materials.get("MAT_P2_Cardboard"),
        "crt": principled("MAT_P2_CRT", (0.07, 0.07, 0.08), 0.45, metallic=0.15),
        "screen": principled("MAT_P2_DeadScreen", (0.02, 0.025, 0.03), 0.35, spec=0.4),
        "rubber": principled("MAT_P2_Rubber", (0.04, 0.04, 0.04), 0.7),
        "stain": principled("MAT_P2_Stain", (0.08, 0.07, 0.05), 0.95, spec=0.04),
    }


def upgrade_materials() -> dict:
    rebuild_concrete("MAT_P2_Wall", 0.35, vertical=True)
    rebuild_concrete("MAT_P2_Floor", 1.15, vertical=False)
    rebuild_concrete("MAT_P2_Ceil", 2.05, vertical=False)
    rebuild_wood("MAT_P2_Desk", (0.13, 0.085, 0.05), 0.4, dusty=True)
    rebuild_wood("MAT_P2_Chair", (0.10, 0.075, 0.048), 1.6, dusty=True)
    rebuild_wood("MAT_P2_Frame", (0.11, 0.07, 0.04), 2.4, dusty=True)
    rebuild_cardboard()
    rebuild_cable()
    rebuild_glass()
    rebuild_dust()
    rebuild_cloth()
    rust = bpy.data.materials.get("MAT_P2_Rust")
    if rust:
        bsdf = next((n for n in rust.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.24, 0.11, 0.05, 1)
            bsdf.inputs["Roughness"].default_value = 0.78
    return extra_mats()


# ---------------------------------------------------------------------------
# Architecture wear
# ---------------------------------------------------------------------------

def add_wear_decals(mats: dict) -> None:
    c = col(COL_ARCH)
    stain = mats["stain"]
    if hasattr(stain, "blend_method"):
        stain.blend_method = "BLEND"
    bsdf = next(n for n in stain.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Alpha"].default_value = 0.55

    # Floor damp patches
    patches = [
        ((-0.85, 25.35, 0.004), (0.85, 0.55, 0.006), 0.4),
        ((1.05, 26.80, 0.004), (0.70, 1.10, 0.006), -0.3),
        ((-1.40, 28.20, 0.004), (0.95, 0.70, 0.006), 0.7),
        ((0.20, 28.70, 0.004), (0.60, 0.45, 0.006), -0.2),
        ((-0.10, 26.90, 0.003), (0.40, 0.90, 0.005), 0.15),
    ]
    for i, (loc, size, rot) in enumerate(patches):
        p = box(f"P2_FLOOR_DAMP_{i:02d}", loc, size, stain, c)
        p.rotation_euler[2] = rot

    # Wall drip stains (slightly off the wall to avoid z-fight)
    drips = [
        ("W", (-2.248, 25.80, 1.35), (0.012, 0.28, 1.55)),
        ("W", (-2.248, 27.60, 1.10), (0.012, 0.22, 1.90)),
        ("E", (2.248, 26.40, 1.20), (0.012, 0.34, 1.70)),
        ("E", (2.248, 28.20, 0.95), (0.012, 0.18, 1.40)),
        ("N", (-1.10, 29.718, 1.40), (0.40, 0.012, 1.60)),
        ("N", (0.85, 29.718, 1.15), (0.28, 0.012, 1.85)),
    ]
    for i, (_side, loc, size) in enumerate(drips):
        box(f"P2_WALL_DRIP_{i:02d}", loc, size, stain, c)

    # Jagged floor crack
    bm = bmesh.new()
    pts = [
        (-0.4, 25.6, 0.006),
        (-0.15, 25.85, 0.006),
        (0.12, 26.15, 0.006),
        (0.05, 26.55, 0.006),
        (0.28, 26.95, 0.006),
        (0.18, 27.40, 0.006),
        (-0.05, 27.85, 0.006),
        (0.10, 28.30, 0.006),
    ]
    verts = []
    for i, (x, y, z) in enumerate(pts):
        w = 0.012 + (i % 3) * 0.006
        verts.append(bm.verts.new((x - w, y, z)))
        verts.append(bm.verts.new((x + w, y, z)))
    bm.verts.ensure_lookup_table()
    for i in range(len(pts) - 1):
        a, b = i * 2, i * 2 + 1
        c0, d = (i + 1) * 2, (i + 1) * 2 + 1
        bm.faces.new((bm.verts[a], bm.verts[c0], bm.verts[d], bm.verts[b]))
    mesh_from_bm("P2_FLOOR_CRACK", bm, stain, c)

    # Wall crack on east
    bm = bmesh.new()
    pts = [(2.242, 26.9, 0.15), (2.242, 26.95, 0.55), (2.242, 26.88, 1.05), (2.242, 27.02, 1.55), (2.242, 26.92, 2.05)]
    for i, (x, y, z) in enumerate(pts):
        w = 0.010 + (i % 2) * 0.006
        bm.verts.new((x, y - w, z))
        bm.verts.new((x, y + w, z))
    bm.verts.ensure_lookup_table()
    for i in range(len(pts) - 1):
        a, b = i * 2, i * 2 + 1
        c0, d = (i + 1) * 2, (i + 1) * 2 + 1
        bm.faces.new((bm.verts[a], bm.verts[b], bm.verts[d], bm.verts[c0]))
    mesh_from_bm("P2_WALL_CRACK_E", bm, stain, c)


# ---------------------------------------------------------------------------
# Cartons
# ---------------------------------------------------------------------------

def dent_mesh(obj: bpy.types.Object, amount: float, keep_bottom: bool = True) -> None:
    mesh = obj.data
    rng = random.Random(hash(obj.name) & 0xFFFFFFFF)
    zs = [v.co.z for v in mesh.vertices]
    minz, maxz = min(zs), max(zs)
    for v in mesh.vertices:
        if keep_bottom and (v.co.z - minz) < (maxz - minz) * 0.08:
            continue
        v.co.x += rng.uniform(-amount, amount)
        v.co.y += rng.uniform(-amount, amount)
        v.co.z += rng.uniform(-amount * 0.6, amount * 0.35)


def make_carton(name: str, loc_xy, size, mats: dict, collection, z_bottom=0.0, kind="closed") -> bpy.types.Object:
    sx, sy, sz = size
    wall = max(0.006, min(sx, sy) * 0.025)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= sx
        v.co.y *= sy
        v.co.z *= sz
    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=2)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    maxz = max(v.co.z for v in bm.verts)
    if kind in {"open", "crushed"}:
        top_faces = [f for f in list(bm.faces) if all(abs(v.co.z - maxz) < 1e-5 for v in f.verts)]
        bmesh.ops.delete(bm, geom=top_faces, context="FACES")
        try:
            bmesh.ops.solidify(bm, geom=list(bm.faces), thickness=wall)
        except Exception:
            pass
    rng = random.Random((hash(name) & 0xFFFF) ^ 917)
    for v in bm.verts:
        if kind != "closed" or abs(v.co.z - maxz) > 1e-5:
            v.co.x += rng.uniform(-0.008, 0.008) * sx
            v.co.y += rng.uniform(-0.008, 0.008) * sy
            if v.co.z > -sz * 0.42:
                v.co.z += rng.uniform(-0.01, 0.006) * sz
    loc = (loc_xy[0], loc_xy[1], z_bottom + sz * 0.5)
    obj = mesh_from_bm(name, bm, mats["cardboard"], collection, loc)
    obj.data.materials.append(mats["interior"])
    # Flaps
    flap_h = min(sx, sy) * (0.22 if kind != "crushed" else 0.12)
    flap_t = 0.004
    top_z = z_bottom + sz + flap_t * 0.5
    if kind in {"open", "closed", "crushed"}:
        specs = [
            (0.0, sy * 0.5 + flap_h * 0.15, sx * 0.92, flap_h, rng.uniform(0.4, 1.6) if kind != "closed" else rng.uniform(-0.15, 0.2)),
            (0.0, -sy * 0.5 - flap_h * 0.15, sx * 0.92, flap_h, rng.uniform(-1.6, -0.4) if kind != "closed" else rng.uniform(-0.2, 0.15)),
        ]
        if kind != "closed" or rng.random() > 0.35:
            specs.append((sx * 0.5 + flap_h * 0.12, 0.0, flap_h, sy * 0.72, rng.uniform(-1.2, 1.2)))
        for i, (dx, dy, fw, fd, rx) in enumerate(specs):
            if kind == "closed" and rng.random() < 0.25:
                continue
            if kind == "open" and rng.random() < 0.12:
                continue
            fl = box(
                f"{name}_FLAP_{i}",
                (loc_xy[0] + dx, loc_xy[1] + dy, top_z if kind != "crushed" else z_bottom + sz * 0.55),
                (fw, fd if abs(dx) < 0.01 else flap_t + 0.01, flap_t if kind == "closed" else flap_t),
                mats["cardboard"],
                collection,
            )
            if abs(dx) < 0.01:
                fl.rotation_euler[0] = rx if kind != "closed" else rng.uniform(-0.12, 0.12)
            else:
                fl.rotation_euler[1] = rx * 0.5
                fl.scale = (1.0, fd / max(fd, 0.02), 1.0)
            fl.parent = obj
            fl.matrix_parent_inverse = obj.matrix_world.inverted()
    # Tape
    if kind == "closed":
        n_tape = rng.randint(1, 3)
        for i in range(n_tape):
            along = rng.choice(["x", "y"])
            if along == "x":
                t = box(
                    f"{name}_TAPE_{i}",
                    (loc_xy[0], loc_xy[1] + rng.uniform(-sy * 0.12, sy * 0.12), z_bottom + sz + 0.003),
                    (sx * rng.uniform(0.85, 1.02), 0.018, 0.003),
                    mats["tape"],
                    collection,
                )
            else:
                t = box(
                    f"{name}_TAPE_{i}",
                    (loc_xy[0] + rng.uniform(-sx * 0.12, sx * 0.12), loc_xy[1], z_bottom + sz + 0.003),
                    (0.016, sy * rng.uniform(0.80, 1.02), 0.003),
                    mats["tape"],
                    collection,
                )
            t.rotation_euler[2] = rng.uniform(-0.08, 0.08)
            t.parent = obj
            t.matrix_parent_inverse = obj.matrix_world.inverted()
    obj.rotation_euler[2] = rng.uniform(-0.38, 0.38)
    if kind == "crushed":
        obj.rotation_euler[0] = rng.uniform(-0.12, 0.12)
        obj.rotation_euler[1] = rng.uniform(-0.10, 0.10)
    elif z_bottom < 0.02 and kind != "closed":
        obj.rotation_euler[0] = rng.uniform(-0.08, 0.10)
        obj.rotation_euler[1] = rng.uniform(-0.07, 0.07)
    elif z_bottom < 0.02:
        obj.rotation_euler[0] = rng.uniform(-0.04, 0.05)
        obj.rotation_euler[1] = rng.uniform(-0.03, 0.04)
    dent_mesh(obj, 0.012 if kind != "crushed" else 0.02)
    snap_ground(obj, z_bottom)
    obj.location.x += rng.uniform(-0.045, 0.045)
    obj.location.y += rng.uniform(-0.045, 0.045)
    return obj


def rebuild_boxes(mats: dict) -> None:
    c = col(COL_CLUTTER)
    doomed = [o for o in list(c.objects) if o.name.startswith("P2_BOX_")]
    for o in doomed:
        delete_object(o)

    # East clutter wall — keep the same neighborhood, break the cube grid.
    east_cols = [
        (1.36, 26.42, [("closed", 0.40, 0.34, 0.30), ("open", 0.36, 0.32, 0.26), ("crushed", 0.38, 0.28, 0.10)]),
        (1.74, 26.52, [("closed", 0.34, 0.30, 0.42), ("open", 0.32, 0.28, 0.22)]),
        (1.46, 26.92, [("open", 0.38, 0.33, 0.28), ("closed", 0.34, 0.30, 0.36)]),
        (1.84, 27.02, [("closed", 0.36, 0.34, 0.24), ("open", 0.30, 0.28, 0.40)]),
        (1.38, 27.38, [("closed", 0.44, 0.36, 0.34), ("crushed", 0.40, 0.30, 0.12), ("open", 0.32, 0.28, 0.22)]),
        (1.78, 27.52, [("open", 0.32, 0.30, 0.30), ("closed", 0.38, 0.32, 0.26)]),
        (1.44, 27.92, [("closed", 0.38, 0.34, 0.32), ("open", 0.30, 0.28, 0.20)]),
        (1.82, 28.08, [("open", 0.36, 0.32, 0.38), ("crushed", 0.28, 0.26, 0.10)]),
        (1.50, 28.44, [("closed", 0.34, 0.32, 0.28), ("open", 0.30, 0.26, 0.24)]),
        (1.88, 28.50, [("open", 0.30, 0.28, 0.32)]),
        (1.22, 28.22, [("crushed", 0.26, 0.22, 0.09)]),
        (1.28, 26.18, [("open", 0.28, 0.24, 0.20)]),
    ]
    n = 0
    for x, y, stack in east_cols:
        z = 0.0
        for kind, sx, sy, sz in stack:
            make_carton(f"P2_BOX_WALL_{n:02d}", (x, y), (sx, sy, sz), mats, c, z_bottom=z, kind=kind)
            z += sz + (0.002 if kind != "crushed" else 0.0)
            n += 1

    west_cols = [
        (-1.86, 25.12, [("closed", 0.38, 0.30, 0.32), ("open", 0.30, 0.26, 0.20)]),
        (-1.68, 25.58, [("open", 0.28, 0.32, 0.24)]),
        (-1.92, 26.82, [("closed", 0.34, 0.28, 0.36), ("crushed", 0.26, 0.24, 0.10)]),
        (-1.58, 28.52, [("open", 0.40, 0.32, 0.28)]),
        (-1.84, 29.02, [("closed", 0.36, 0.36, 0.34), ("open", 0.28, 0.26, 0.18)]),
        (-1.96, 27.32, [("crushed", 0.28, 0.26, 0.11)]),
        (-1.50, 24.72, [("open", 0.32, 0.24, 0.22)]),
        (-1.72, 27.85, [("closed", 0.26, 0.30, 0.20)]),
    ]
    k = 0
    for x, y, stack in west_cols:
        z = 0.0
        for kind, sx, sy, sz in stack:
            make_carton(f"P2_BOX_WEST_{k:02d}", (x, y), (sx, sy, sz), mats, c, z_bottom=z, kind=kind)
            z += sz + 0.002
            k += 1

    north = [
        ((-0.70, 29.28), ("closed", 0.40, 0.28, 0.22)),
        ((0.55, 29.20), ("open", 0.36, 0.32, 0.26)),
        ((-0.20, 29.40), ("crushed", 0.30, 0.24, 0.10)),
        ((0.15, 29.18), ("open", 0.28, 0.22, 0.18)),
        ((-1.10, 29.35), ("closed", 0.24, 0.30, 0.20)),
    ]
    for i, ((x, y), (kind, sx, sy, sz)) in enumerate(north):
        make_carton(f"P2_BOX_NORTH_{i:02d}", (x, y), (sx, sy, sz), mats, c, z_bottom=0.0, kind=kind)

    # A few on their sides in the east pile gap (still against the wall)
    side = make_carton("P2_BOX_SIDE_00", (1.58, 26.18), (0.42, 0.22, 0.28), mats, c, kind="open")
    side.rotation_euler[0] = math.radians(88.0)
    snap_ground(side, 0.0)


def make_crate(name, loc, size, mat, collection) -> bpy.types.Object:
    sx, sy, sz = size
    t = 0.018
    body = box(name, loc, (sx, sy, t), mat, collection, 0.003)
    walls = [
        (0.0, sy * 0.5 - t * 0.5, sz * 0.5, sx, t, sz),
        (0.0, -sy * 0.5 + t * 0.5, sz * 0.5, sx, t, sz),
        (sx * 0.5 - t * 0.5, 0.0, sz * 0.5, t, sy - 2 * t, sz),
        (-sx * 0.5 + t * 0.5, 0.0, sz * 0.5, t, sy - 2 * t, sz),
    ]
    for i, (dx, dy, dz, wx, wy, wz) in enumerate(walls):
        w = box(f"{name}_W{i}", (loc[0] + dx, loc[1] + dy, loc[2] - size[2] * 0.5 + dz + t * 0.5), (wx, wy, wz), mat, collection, 0.002)
        w.parent = body
        w.matrix_parent_inverse = body.matrix_world.inverted()
    return body


def add_extra_clutter(mats: dict) -> None:
    c = col(COL_CLUTTER)
    # Replace the simple plastic crate with a real crate.
    old = bpy.data.objects.get("P2_CRATE_PLASTIC")
    crate_loc = (-1.75, 26.20, 0.02)
    if old:
        crate_loc = (old.location.x, old.location.y, 0.02)
        delete_object(old)
    crate = make_crate("P2_CRATE_PLASTIC", (crate_loc[0], crate_loc[1], 0.02), (0.46, 0.32, 0.26), mats["plastic"], c)
    crate.rotation_euler[2] = 0.32
    snap_ground(crate, 0.0)

    crate2 = make_crate("P2_CRATE_GREY", (-1.55, 25.78, 0.02), (0.38, 0.28, 0.18), mats["plastic_b"], c)
    crate2.rotation_euler[2] = -0.45
    snap_ground(crate2, 0.0)

    crate3 = make_crate("P2_CRATE_BLUE", (1.55, 28.85, 0.02), (0.34, 0.26, 0.16), mats["plastic_c"], c)
    crate3.rotation_euler[2] = 0.55
    snap_ground(crate3, 0.0)

    # Old CRT on east floor, not in the chair path.
    crt = box("P2_CRT_BODY", (1.22, 28.62, 0.16), (0.36, 0.28, 0.30), mats["crt"], c, 0.006)
    crt.rotation_euler[2] = 0.35
    snap_ground(crt, 0.0)
    scr = box("P2_CRT_SCREEN", (1.18, 28.50, 0.18), (0.30, 0.04, 0.22), mats["screen"], c)
    scr.rotation_euler[2] = 0.35
    snap_ground(scr, 0.06)

    # Keyboard, slightly warped.
    kb = box("P2_KEYBOARD", (1.18, 26.72, 0.02), (0.36, 0.13, 0.028), mats["plastic_b"], c, 0.002)
    kb.rotation_euler[2] = -0.55
    kb.rotation_euler[0] = 0.08
    snap_ground(kb, 0.0)

    # Dead PSU already exists; add a second brick and an open drive cage.
    box("P2_PSU_BRICK", (1.70, 26.62, 0.66), (0.16, 0.22, 0.08), mats["metal"], c, 0.002)
    box("P2_DRIVE_CAGE", (1.68, 27.55, 1.16), (0.20, 0.26, 0.06), mats["metal"], c, 0.002)
    cylinder("P2_FAN_HUB", (1.72, 27.05, 1.62), 0.055, 0.03, mats["plastic_b"], c, 10, rot=(math.pi * 0.5, 0, 0.2))
    box("P2_PCI_BRACKET", (1.62, 27.22, 1.15), (0.14, 0.02, 0.08), mats["metal"], c, 0.001).rotation_euler[2] = 0.4

    # Metal parts pile west of desk, against west wall — not in sit path.
    for i, (xy, sz, rot) in enumerate((
        ((-1.95, 26.45), (0.22, 0.06, 0.04), 0.7),
        ((-1.82, 26.52), (0.16, 0.05, 0.03), -0.4),
        ((-1.88, 26.38), (0.10, 0.10, 0.04), 0.2),
    )):
        p = box(f"P2_METAL_PART_{i}", (xy[0], xy[1], 0.03), sz, mats["rust"], c, 0.002)
        p.rotation_euler[2] = rot
        snap_ground(p, 0.0)

    cylinder("P2_PIPE_SCRAP", (-1.62, 27.55, 0.03), 0.028, 0.55, mats["rust"], c, 10, rot=(1.25, 0.1, 0.4))
    snap_ground(bpy.data.objects["P2_PIPE_SCRAP"], 0.0)
    cylinder("P2_PAINT_CAN", (-1.48, 26.55, 0.09), 0.055, 0.16, mats["metal"], c, 12)
    snap_ground(bpy.data.objects["P2_PAINT_CAN"], 0.0)
    cylinder("P2_PAINT_CAN_B", (1.15, 27.95, 0.08), 0.048, 0.14, mats["rust"], c, 12)
    snap_ground(bpy.data.objects["P2_PAINT_CAN_B"], 0.0)

    # Discarded furniture: leaning board + stool on side.
    board = box("P2_LEAN_BOARD", (-2.05, 28.15, 0.55), (0.04, 0.42, 1.05), mats["chair"], c, 0.003)
    board.rotation_euler[1] = 0.18
    board.rotation_euler[2] = 0.08
    snap_ground(board, 0.0)
    stool = box("P2_STOOL_SEAT", (-1.35, 28.20, 0.04), (0.28, 0.28, 0.04), mats["chair"], c, 0.003)
    stool.rotation_euler[0] = 1.25
    stool.rotation_euler[2] = 0.6
    snap_ground(stool, 0.0)
    leg = box("P2_STOOL_LEG", (-1.22, 28.08, 0.03), (0.032, 0.032, 0.32), mats["chair"], c)
    leg.rotation_euler[0] = 0.9
    leg.rotation_euler[2] = -0.4
    snap_ground(leg, 0.0)

    # Scattered tools near clutter wall / desk legs, leaving sit space.
    tools = [
        ("P2_WRENCH", (0.92, 26.55, 0.02), (0.18, 0.04, 0.018), mats["metal"], -0.8),
        ("P2_HAMMER_HEAD", (1.05, 27.55, 0.03), (0.08, 0.04, 0.04), mats["metal"], 0.4),
        ("P2_HAMMER_HANDLE", (0.98, 27.52, 0.025), (0.22, 0.025, 0.022), mats["chair"], 0.4),
        ("P2_TAPE_ROLL", (0.78, 27.85, 0.03), None, mats["tape"], 0.0),
        ("P2_SCREW_HEAP", (1.10, 26.95, 0.015), (0.06, 0.05, 0.012), mats["rust"], 0.3),
    ]
    for name, loc, size, mat, rot in tools:
        if name == "P2_TAPE_ROLL":
            obj = cylinder(name, loc, 0.035, 0.028, mat, c, 14, rot=(math.pi * 0.5, 0, 0.3))
        else:
            obj = box(name, loc, size, mat, c, 0.002)
            obj.rotation_euler[2] = rot
        snap_ground(obj, 0.0)

    # Extension block under desk back edge (not in knee space of the chair).
    strip = box("P2_POWER_STRIP", (0.42, 27.52, 0.03), (0.28, 0.06, 0.032), mats["plastic_b"], c, 0.002)
    strip.rotation_euler[2] = 0.25
    snap_ground(strip, 0.0)

    # Empty drawer carcass west-north.
    drawer = box("P2_DRAWER", (-1.70, 28.95, 0.07), (0.40, 0.28, 0.12), mats["chair"], c, 0.003)
    drawer.rotation_euler[2] = -0.55
    snap_ground(drawer, 0.0)

    # Tiny floor debris near cables / desk.
    for i in range(10):
        x = RNG.uniform(-0.9, 1.05)
        y = RNG.uniform(25.4, 28.6)
        # Keep the immediate sit rectangle free of debris piles; tiny bits OK at edges.
        sz = RNG.uniform(0.008, 0.018)
        bit = box(
            f"P2_DEBRIS_{i:02d}",
            (x, y, 0.01),
            (RNG.uniform(0.02, 0.05), RNG.uniform(0.015, 0.04), sz),
            mats["rust"] if i % 3 else mats["metal"],
            c,
        )
        bit.rotation_euler[2] = RNG.uniform(-1.5, 1.5)
        snap_ground(bit, 0.0)


# ---------------------------------------------------------------------------
# Frame / cloth / desk
# ---------------------------------------------------------------------------

def rebuild_cloth_mesh(mats: dict) -> None:
    old = bpy.data.objects.get("P2_CLOTH")
    loc = (0.045, 27.115, DESK_TOP_Z + 0.010)
    rot_z = math.radians(24.0)
    if old:
        loc = (old.location.x, old.location.y, DESK_TOP_Z + 0.010)
        rot_z = old.rotation_euler[2]
        delete_object(old)
    c = col(COL_FRAME)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=20, y_subdivisions=16, size=1.0, location=loc)
    cloth = bpy.context.object
    cloth.name = "P2_CLOTH"
    cloth.scale = (0.168, 0.125, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    mesh = cloth.data
    rng = random.Random(4411)
    for v in mesh.vertices:
        x, y = v.co.x, v.co.y
        wr = (
            0.011 * math.sin(x * 34.0 + 0.4) * math.cos(y * 28.0)
            + 0.007 * math.sin(x * 18.0 - y * 22.0)
            + 0.004 * math.cos(x * 52.0) * math.sin(y * 40.0)
            + rng.uniform(-0.0025, 0.0035)
        )
        v.co.z += wr
        # Irregular perimeter
        edge = max(abs(x) / 0.084, abs(y) / 0.0625)
        if edge > 0.82:
            v.co.x += rng.uniform(-0.007, 0.007)
            v.co.y += rng.uniform(-0.008, 0.006)
            if rng.random() < 0.22:
                v.co.x += rng.choice((-1, 1)) * rng.uniform(0.004, 0.012)
                v.co.y += rng.choice((-1, 1)) * rng.uniform(0.003, 0.010)
    cloth.rotation_euler = (0.06, -0.04, rot_z)
    cloth.data.materials.clear()
    cloth.data.materials.append(mats["cardboard"] if False else bpy.data.materials["MAT_P2_Cloth"])
    solid = cloth.modifiers.new("thickness", "SOLIDIFY")
    solid.thickness = 0.0075
    solid.offset = 1.0
    apply_modifiers(cloth)
    # Extra fold ridge
    for v in cloth.data.vertices:
        if 0.01 < v.co.x < 0.05:
            v.co.z += 0.004 * math.sin(v.co.y * 40.0)
    link(cloth, c)
    # Rest on desk: snap lowest vertex to desk top.
    corners = [cloth.matrix_world @ Vector(ch) for ch in cloth.bound_box]
    minz = min(ch.z for ch in corners)
    cloth.location.z += (DESK_TOP_Z + 0.001) - minz


def wear_frame() -> None:
    outer = bpy.data.objects.get("P2_FRAME_OUTER")
    if outer and outer.type == "MESH":
        rng = random.Random(19)
        for v in outer.data.vertices:
            # Chip corners more than faces.
            if abs(v.co.x) > 0.09 and abs(v.co.z) > 0.11:
                v.co.x += rng.uniform(-0.0025, 0.0015)
                v.co.z += rng.uniform(-0.0025, 0.0015)
                v.co.y += rng.uniform(-0.001, 0.001)
            else:
                v.co.x += rng.uniform(-0.0008, 0.0008)
                v.co.z += rng.uniform(-0.0008, 0.0008)
        bevel = next((m for m in outer.modifiers if m.type == "BEVEL"), None)
        if bevel:
            bevel.width = 0.0045
            bevel.segments = 3

    dust = bpy.data.objects.get("P2_FRAME_DUST")
    root = bpy.data.objects.get("P2_FRAME_ROOT")
    if dust is None or root is None:
        return
    c = col(COL_FRAME)
    local = dust.location.copy()
    delete_object(dust)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=18, y_subdivisions=22, size=1.0, location=(0, 0, 0))
    dust = bpy.context.object
    dust.name = "P2_FRAME_DUST"
    dust.scale = (0.168, 0.218, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    dust.rotation_euler[0] = math.radians(90.0)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    rng = random.Random(77)
    for v in dust.data.vertices:
        clump = 0.0018 * math.sin(v.co.x * 40.0) * math.cos(v.co.z * 36.0)
        # Heavier in corners, thinner mid (uneven long-term dust).
        corner = (abs(v.co.x) / 0.084) ** 2 + (abs(v.co.z) / 0.109) ** 2
        v.co.y -= 0.0012 + clump + corner * 0.0035 + rng.uniform(0.0, 0.0012)
    solid = dust.modifiers.new("thickness", "SOLIDIFY")
    solid.thickness = 0.0022
    solid.offset = -1.0
    apply_modifiers(dust)
    dust.data.materials.clear()
    dust.data.materials.append(bpy.data.materials["MAT_P2_Dust"])
    link(dust, c)
    dust.parent = root
    dust.location = local
    dust.location.y = -0.0135

    # Long-term stain along the bottom of the outer frame (independent mesh).
    stain = box("P2_FRAME_STAIN", (0.0, -0.015, -0.11), (0.20, 0.004, 0.04), bpy.data.materials.get("MAT_P2_Stain"), c)
    stain.parent = root
    stain.matrix_parent_inverse = root.matrix_world.inverted()
    if hasattr(stain.data.materials[0], "blend_method"):
        stain.data.materials[0].blend_method = "BLEND"
    bsdf = next(n for n in stain.data.materials[0].node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Alpha"].default_value = 0.55


def add_desk_detail(mats: dict) -> None:
    c = col(COL_PROPS)
    # Thin dust film on the desk, with a clearer patch around frame/cloth.
    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=14, y_subdivisions=10, size=1.0, location=(DESK[0] + 0.06, DESK[1] + 0.04, DESK_TOP_Z + 0.0012)
    )
    film = bpy.context.object
    film.name = "P2_DESK_DUST_FILM"
    film.scale = (1.22, 0.58, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    film.data.materials.append(bpy.data.materials["MAT_P2_Dust"])
    link(film, c)
    # Push verts down (clearer) near the hero props.
    for v in film.data.vertices:
        world = film.matrix_world @ v.co
        if -0.32 < world.x < 0.20 and 26.98 < world.y < 27.28:
            v.co.z -= 0.0008

    extras = [
        ("P2_WASHER_A", cylinder, (DESK[0] - 0.58, DESK[1] - 0.18, DESK_TOP_Z + 0.004), dict(radius=0.009, depth=0.004, verts=10)),
        ("P2_WASHER_B", cylinder, (DESK[0] - 0.55, DESK[1] - 0.14, DESK_TOP_Z + 0.004), dict(radius=0.007, depth=0.003, verts=10)),
        ("P2_TAPE_NUB", box, (DESK[0] + 0.58, DESK[1] + 0.26, DESK_TOP_Z + 0.012), dict(size=(0.05, 0.05, 0.022))),
        ("P2_FUSE", box, (DESK[0] + 0.50, DESK[1] - 0.26, DESK_TOP_Z + 0.008), dict(size=(0.04, 0.014, 0.012))),
        ("P2_CRUMPLE", box, (DESK[0] + 0.36, DESK[1] + 0.24, DESK_TOP_Z + 0.006), dict(size=(0.07, 0.05, 0.01))),
        ("P2_RUST_FLAKE", box, (DESK[0] - 0.62, DESK[1] + 0.08, DESK_TOP_Z + 0.003), dict(size=(0.03, 0.02, 0.004))),
    ]
    for name, fn, loc, kw in extras:
        if fn is cylinder:
            obj = cylinder(name, loc, kw["radius"], kw["depth"], mats["metal"], c, kw["verts"])
        else:
            mat = mats["tape"] if "TAPE" in name else mats["paper"] if "CRUMPLE" in name else mats["handle"] if "FUSE" in name else mats["rust"]
            obj = box(name, loc, kw["size"], mat, c, 0.001)
            obj.rotation_euler[2] = RNG.uniform(-0.8, 0.8)
        if "CRUMPLE" in name:
            dent_mesh(obj, 0.008, keep_bottom=False)


# ---------------------------------------------------------------------------
# Cables
# ---------------------------------------------------------------------------

def bezier_cable(name, pts, radius, mat, collection, point_radius=None) -> bpy.types.Object:
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 14
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    curve.fill_mode = "FULL"
    curve.twist_mode = "MINIMUM"
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(pts) - 1)
    for i, (bp, p) in enumerate(zip(spline.bezier_points, pts)):
        bp.co = Vector(p)
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
        bp.radius = 1.0 if point_radius is None else point_radius[i]
    obj = bpy.data.objects.new(name, curve)
    if mat:
        obj.data.materials.append(mat)
    return link(obj, collection)


def coil_pts(cx, cy, cz, radius, turns, z_step=0.0035, wobble=0.04) -> list:
    pts = []
    steps = int(turns * 12)
    for i in range(steps + 1):
        t = i / 12.0
        ang = t * math.tau
        r = radius * (1.0 + 0.10 * math.sin(i * 0.7))
        pts.append((
            cx + r * math.cos(ang) + RNG.uniform(-wobble, wobble) * 0.15,
            cy + r * math.sin(ang) + RNG.uniform(-wobble, wobble) * 0.15,
            cz + i * z_step,
        ))
    return pts


def add_detail_cables(mats: dict) -> None:
    c = col(COL_CABLES)
    mat = mats["cable"]
    paths = [
        # From west junction box down to floor then to desk.
        (0.028, [(-2.02, 25.40, 1.38), (-1.85, 25.55, 0.85), (-1.55, 25.85, 0.22),
                 (-1.10, 26.15, 0.04), (-0.55, 26.45, 0.026), (0.05, 26.70, 0.024)]),
        # From PSU toward desk legs and center.
        (0.022, [(1.62, 27.40, 0.18), (1.25, 27.28, 0.06), (0.85, 27.10, 0.028),
                 (0.48, 26.92, 0.024), (0.22, 26.70, 0.030), (-0.05, 26.48, 0.024)]),
        # Clutter-wall drape.
        (0.030, [(1.92, 27.85, 0.55), (1.70, 27.60, 0.22), (1.42, 27.28, 0.05),
                 (1.05, 27.05, 0.028), (0.62, 26.88, 0.024), (0.18, 26.95, 0.026)]),
        # Around front-left desk leg.
        (0.024, [(-0.95, 26.55, 0.026), (-0.62, 26.78, 0.032), (-0.50, 26.96, 0.028),
                 (-0.58, 27.18, 0.024), (-0.40, 27.40, 0.028), (-0.05, 27.55, 0.022)]),
        # Around front-right desk leg.
        (0.020, [(0.95, 26.55, 0.024), (0.72, 26.80, 0.030), (0.68, 27.00, 0.026),
                 (0.78, 27.22, 0.024), (0.55, 27.45, 0.028), (0.22, 27.58, 0.022)]),
        # Floor-center tangle.
        (0.032, [(-0.55, 26.85, 0.028), (-0.15, 27.05, 0.034), (0.22, 26.92, 0.026),
                 (0.48, 27.18, 0.032), (0.10, 27.38, 0.024), (-0.28, 27.22, 0.030)]),
        (0.018, [(0.05, 26.40, 0.022), (0.35, 26.62, 0.028), (0.12, 26.88, 0.024),
                 (-0.18, 27.05, 0.030), (0.08, 27.28, 0.024), (0.38, 27.08, 0.026)]),
        # From CRT / east corner.
        (0.026, [(1.22, 28.62, 0.16), (0.95, 28.35, 0.05), (0.55, 28.05, 0.028),
                 (0.18, 27.75, 0.024), (-0.15, 27.48, 0.028), (-0.48, 27.15, 0.022)]),
        # North wall to center.
        (0.021, [(-0.80, 29.35, 0.024), (-0.40, 28.95, 0.030), (0.05, 28.55, 0.024),
                 (0.35, 28.15, 0.028), (0.15, 27.75, 0.024), (-0.22, 27.55, 0.026)]),
        # West wall along floor.
        (0.027, [(-2.10, 24.70, 0.18), (-1.85, 24.95, 0.05), (-1.45, 25.25, 0.028),
                 (-0.95, 25.55, 0.024), (-0.45, 25.85, 0.028), (0.05, 25.65, 0.022)]),
        # Door threshold into room.
        (0.019, [(-0.28, 24.30, 0.022), (-0.05, 24.65, 0.028), (0.22, 25.05, 0.024),
                 (0.08, 25.45, 0.030), (-0.18, 25.80, 0.024), (-0.42, 26.15, 0.026)]),
        # Power strip feed.
        (0.016, [(0.42, 27.52, 0.04), (0.28, 27.38, 0.028), (0.05, 27.22, 0.024),
                 (-0.22, 27.05, 0.028), (-0.48, 26.82, 0.024), (-0.70, 26.55, 0.022)]),
        # High drape from shelf.
        (0.023, [(1.88, 27.15, 1.12), (1.55, 27.05, 0.55), (1.22, 26.85, 0.12),
                 (0.85, 26.65, 0.04), (0.48, 26.48, 0.026), (0.12, 26.35, 0.022)]),
        # Behind chair, still on floor.
        (0.025, [(-0.55, 26.15, 0.024), (-0.15, 26.05, 0.030), (0.22, 26.18, 0.024),
                 (0.48, 26.40, 0.028), (0.28, 26.62, 0.024), (-0.08, 26.55, 0.026)]),
        # Extra east-west across center.
        (0.029, [(1.45, 26.85, 0.026), (0.95, 26.95, 0.032), (0.45, 27.12, 0.024),
                 (0.05, 27.00, 0.030), (-0.40, 26.82, 0.024), (-0.85, 26.65, 0.028)]),
        (0.017, [(1.35, 27.65, 0.022), (0.95, 27.48, 0.028), (0.55, 27.62, 0.024),
                 (0.22, 27.40, 0.030), (-0.05, 27.58, 0.024), (-0.38, 27.72, 0.026)]),
        # Thin signal cable.
        (0.012, [(-1.95, 27.32, 0.14), (-1.55, 27.15, 0.05), (-1.05, 26.95, 0.026),
                 (-0.55, 26.75, 0.022), (-0.15, 26.58, 0.026), (0.22, 26.42, 0.022)]),
        # Thick feeder from north-east.
        (0.034, [(1.95, 29.20, 0.028), (1.35, 28.85, 0.036), (0.75, 28.45, 0.026),
                 (0.28, 28.05, 0.032), (-0.10, 27.70, 0.024), (-0.42, 27.35, 0.028)]),
        # Loop near broken furniture.
        (0.020, [(-1.55, 28.85, 0.024), (-1.15, 28.55, 0.030), (-0.75, 28.25, 0.024),
                 (-0.45, 27.95, 0.028), (-0.15, 27.70, 0.024), (0.18, 27.48, 0.026)]),
        # Under-desk bundle.
        (0.022, [(-0.50, 27.48, 0.024), (-0.15, 27.42, 0.032), (0.18, 27.35, 0.024),
                 (0.48, 27.28, 0.028), (0.70, 27.18, 0.024), (0.55, 26.95, 0.026)]),
    ]
    for i, (rad, pts) in enumerate(paths):
        bezier_cable(f"P2_CABLE_DETAIL_{i:02d}", pts, rad, mat, c)

    coils = [
        ((0.18, 27.05, 0.018), 0.11, 2.4, 0.024),
        ((-0.35, 26.72, 0.018), 0.09, 2.1, 0.018),
        ((0.55, 26.58, 0.018), 0.08, 1.8, 0.020),
        ((1.05, 27.22, 0.018), 0.10, 2.0, 0.026),
        ((-1.05, 25.95, 0.018), 0.12, 2.6, 0.022),
        ((0.02, 28.15, 0.018), 0.09, 1.9, 0.016),
        ((1.35, 26.40, 0.018), 0.07, 1.6, 0.019),
        ((-0.72, 27.85, 0.018), 0.08, 1.7, 0.021),
    ]
    for i, ((cx, cy, cz), radius, turns, rad) in enumerate(coils):
        bezier_cable(f"P2_CABLE_COIL_{i:02d}", coil_pts(cx, cy, cz, radius, turns), rad, mat, c)

    # Short stubs coming out of equipment.
    stubs = [
        (0.014, [(1.74, 27.40, 0.26), (1.74, 27.40, 0.12), (1.68, 27.32, 0.04), (1.55, 27.18, 0.024)]),
        (0.016, [(-2.00, 25.40, 1.38), (-1.92, 25.48, 0.95), (-1.78, 25.62, 0.35), (-1.62, 25.78, 0.04)]),
        (0.013, [(1.70, 26.90, 1.18), (1.55, 26.82, 0.70), (1.38, 26.70, 0.20), (1.18, 26.55, 0.028)]),
        (0.015, [(0.42, 27.52, 0.045), (0.50, 27.48, 0.028), (0.62, 27.35, 0.024), (0.78, 27.18, 0.026)]),
    ]
    for i, (rad, pts) in enumerate(stubs):
        bezier_cable(f"P2_CABLE_STUB_{i:02d}", pts, rad, mat, c)


# ---------------------------------------------------------------------------
# Lights / cameras
# ---------------------------------------------------------------------------

def tune_lights() -> None:
    c = col(COL_LIGHTS)
    pendant = bpy.data.objects.get("LIGHT_P2_DESK_PENDANT")
    if pendant:
        pendant.data.energy = 108.0
        pendant.data.color = (1.0, 0.76, 0.46)
        pendant.data.shadow_soft_size = 0.18
    contour = bpy.data.objects.get("LIGHT_P2_ROOM_CONTOUR")
    if contour:
        contour.data.energy = 11.5
        contour.data.size = 2.1
        contour.data.color = (0.82, 0.70, 0.52)
    led = bpy.data.objects.get("LIGHT_P2_PSU_LED")
    if led:
        led.data.energy = 0.55

    def add_light(name, ltype, loc, energy, color, **kw):
        existing = bpy.data.objects.get(name)
        if existing:
            delete_object(existing)
        bpy.ops.object.light_add(type=ltype, location=loc)
        obj = bpy.context.object
        obj.name = name
        obj.data.energy = energy
        obj.data.color = color
        if ltype == "POINT":
            obj.data.shadow_soft_size = kw.get("soft", 0.2)
            obj.data.use_shadow = kw.get("shadow", True)
        if ltype == "AREA":
            obj.data.size = kw.get("size", 1.0)
            obj.data.shape = kw.get("shape", "DISK")
            obj.data.use_shadow = kw.get("shadow", True)
        if "rot" in kw:
            obj.rotation_euler = kw["rot"]
        if "size_y" in kw and ltype == "AREA":
            obj.data.shape = "RECTANGLE"
            obj.data.size = kw["size"]
            obj.data.size_y = kw["size_y"]
        return link(obj, c)

    add_light(
        "LIGHT_P2_CLUTTER_KICK",
        "AREA",
        (1.15, 27.25, 1.85),
        26.0,
        (0.98, 0.80, 0.52),
        size=0.9,
        size_y=1.4,
        rot=(math.radians(55), 0.0, math.radians(-18)),
    )
    add_light(
        "LIGHT_P2_FLOOR_GLANCE",
        "AREA",
        (-0.15, 25.55, 0.42),
        16.0,
        (0.92, 0.76, 0.52),
        size=1.3,
        size_y=0.6,
        rot=(math.radians(72), 0.0, math.radians(12)),
    )
    add_light(
        "LIGHT_P2_WEST_FILL",
        "POINT",
        (-1.55, 28.35, 2.05),
        14.0,
        (0.78, 0.68, 0.50),
        soft=0.35,
        shadow=True,
    )
    add_light(
        "LIGHT_P2_FRAME_KISS",
        "POINT",
        (-0.02, 26.92, 1.05),
        6.5,
        (1.0, 0.82, 0.55),
        soft=0.08,
        shadow=True,
    )


def tune_cameras() -> None:
    c = col(COL_CAMS)
    wide = bpy.data.objects.get("CAM_P2_WIDE")
    if wide:
        wide.location = (-1.62, 24.78, 1.52)
        wide.data.lens = 22.0
        look_at(wide, (0.25, 27.35, 0.78))

    sit = bpy.data.objects.get("CAM_P2_SIT")
    if sit:
        sit.location = (CHAIR[0] + 0.02, CHAIR[1] + 0.10, 1.18)
        sit.data.lens = 32.0
        look_at(sit, (DESK[0] - 0.10, DESK[1] - 0.02, 0.84))

    desk = bpy.data.objects.get("CAM_P2_DESK")
    if desk:
        desk.location = (DESK[0] + 0.16, DESK[1] - 0.52, 1.05)
        desk.data.lens = 40.0
        look_at(desk, (DESK[0] - 0.08, DESK[1] + 0.02, 0.86))

    floor = bpy.data.objects.get("CAM_P2_FLOOR")
    if floor:
        floor.location = (0.12, 25.95, 0.48)
        floor.data.lens = 24.0
        look_at(floor, (0.15, 27.15, 0.04))

    existing = bpy.data.objects.get("CAM_P2_CLUTTER")
    if existing:
        delete_object(existing)
    bpy.ops.object.camera_add(location=(0.55, 26.55, 1.05))
    cl = bpy.context.object
    cl.name = "CAM_P2_CLUTTER"
    cl.data.lens = 28.0
    cl.data.sensor_width = 36.0
    cl.data.clip_start = 0.05
    cl.data.clip_end = 40.0
    look_at(cl, (1.55, 27.35, 0.55))
    link(cl, c)


# ---------------------------------------------------------------------------
# QA / render / pack
# ---------------------------------------------------------------------------

def qa_scene(rig_before: dict) -> dict:
    issues = []
    floaters = []
    for obj in bpy.data.objects:
        if not obj.name.startswith("P2_"):
            continue
        if obj.type not in {"MESH", "CURVE"}:
            continue
        if obj.name.startswith("P2_WALL") or obj.name.startswith("P2_CEIL") or obj.name.startswith("P2_FLOOR"):
            continue
        if "PIPE_0" in obj.name or "LAMP" in obj.name or "ELEC" in obj.name or "DRIP" in obj.name or "CRACK" in obj.name:
            continue
        if obj.parent and obj.parent.name.startswith("P2_FRAME"):
            continue
        if obj.parent and "BOX" in obj.parent.name:
            continue
        deps = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(deps)
        bb = [obj.matrix_world @ Vector(ch) for ch in ev.bound_box]
        minz = min(ch.z for ch in bb)
        maxz = max(ch.z for ch in bb)
        if obj.type == "CURVE":
            if minz < -0.02:
                issues.append(f"cable_below_floor {obj.name} minz={minz:.3f}")
            continue
        # Grounded clutter / furniture should not hover.
        if obj.name.startswith(("P2_BOX_", "P2_CRATE", "P2_KEYBOARD", "P2_WRENCH", "P2_HAMMER", "P2_DEBRIS", "P2_STOOL", "P2_DRAWER", "P2_CRT", "P2_LEAN", "P2_PAINT", "P2_PIPE_SCRAP", "P2_METAL_PART", "P2_BROKEN", "P2_POWER", "P2_TAPE_ROLL", "P2_SCREW", "P2_FAN_HUB")):
            if minz > 0.04:
                floaters.append({"name": obj.name, "minz": round(minz, 4)})
            if minz < -0.03:
                issues.append(f"clip_floor {obj.name} minz={minz:.3f}")
        if maxz > HEIGHT + 0.05 and "SHELF" not in obj.name:
            issues.append(f"above_ceiling {obj.name} maxz={maxz:.3f}")

    rig_after = capture_rig_cables()
    rig_ok = rig_before == rig_after
    if not rig_ok:
        issues.append("RIG cable points changed")

    missing_rig = [n for n in RIG_NAMES if bpy.data.objects.get(n) is None]
    frame_parts = ["P2_FRAME_OUTER", "P2_FRAME_GLASS", "P2_FRAME_PHOTO", "P2_FRAME_DUST", "P2_CLOTH"]
    missing_frame = [n for n in frame_parts if bpy.data.objects.get(n) is None]

    cables = [o.name for o in bpy.data.objects if o.name.startswith("P2_CABLE_")]
    report = {
        "objects": len(bpy.data.objects),
        "p2_objects": len([o for o in bpy.data.objects if o.name.startswith("P2_")]),
        "cables": sorted(cables),
        "cable_count": len(cables),
        "rig_unchanged": rig_ok,
        "missing_rig": missing_rig,
        "missing_frame": missing_frame,
        "floaters": floaters,
        "issues": issues,
        "desk": [round(v, 3) for v in bpy.data.objects["P2_DESK_TOP"].location],
        "chair": [round(v, 3) for v in bpy.data.objects["P2_CHAIR_SEAT"].location],
        "hallway_untouched": True,
    }
    QA_JSON.write_text(json.dumps(report, indent=2))
    return report


def configure_preview(scene: bpy.types.Scene) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 32
    scene.eevee.use_raytracing = True
    scene.eevee.use_fast_gi = True
    scene.eevee.fast_gi_method = "AMBIENT_OCCLUSION_ONLY"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.use_motion_blur = False
    scene.render.use_compositing = False


def render_stills() -> list[Path]:
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    configure_preview(scene)
    orig_cam = scene.camera
    orig_frame = scene.frame_current
    jobs = [
        ("CAM_P2_WIDE", 1, "01_wide.png"),
        ("CAM_P2_SIT", 1, "02_sit_fps.png"),
        ("CAM_P2_DESK", 1, "03_desk_close.png"),
        ("CAM_P2_FLOOR", 1, "04_cables_floor.png"),
        ("CAM_P2_CLUTTER", 1, "05_clutter_wall.png"),
    ]
    paths = []
    for cam_name, frame, fname in jobs:
        cam = bpy.data.objects[cam_name]
        scene.camera = cam
        scene.frame_set(frame)
        path = STILL_DIR / fname
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        dest = ARTIFACT / f"part2_detail_{fname}"
        dest.write_bytes(path.read_bytes())
        paths.append(path)
        print("still", path)
    scene.camera = orig_cam
    scene.frame_set(orig_frame)
    return paths


def pack_and_save() -> None:
    if Path(bpy.data.filepath).resolve() == PART1.resolve():
        raise SystemExit("refusing to save hallway.blend")
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BLEND, CHECKPOINT)
    art = ARTIFACT / "part2_basement.blend"
    shutil.copy2(BLEND, art)
    print("saved", BLEND, "bytes", BLEND.stat().st_size)
    print("checkpoint", CHECKPOINT)


def write_report(qa: dict, stills: list[Path]) -> None:
    text = f"""# Part 2 basement — static detail pass

Part 1 `hallway.blend` was not saved. Working copy: `part2_basement.blend`.
Pre-detail backup: `renders/checkpoints/part2_basement_pre_detail.blend`.
This checkpoint: `renders/checkpoints/part2_basement_detail.blend`.

## Scope

Static scene / materials / props / lighting only.
No character, rig, camera animation, black liquid, photo mutation, red text, or cable motion.

## Preserved

- Room interior 5.50 x 4.50 x 2.50 m, y 24.22–29.72
- Desk `{qa['desk']}`, chair `{qa['chair']}`
- FINAL_DOOR connection / WALL.End hole (copy only)
- Independent frame parts: OUTER / GLASS / PHOTO / DUST + cloth
- `P2_CABLE_RIG_01`–`06` spline data unchanged: `{qa['rig_unchanged']}`

## This pass

- Worn concrete (damp, grit, cracks) on walls/floor/ceiling plus drip / crack decals
- Cartons rebuilt with flaps, dents, tape, open tops, crushed units, irregular tilt
- Extra junk: crates, CRT, keyboard, metal parts, leaning board, stool, tools, cans
- Thick wrinkled cloth; uneven frame dust; glass scratch roughness; desk dust film
- Detail / coil / stub cables added; RIG cables left intact; all cables static
- Desk key light retained; clutter kicker + floor glance + west fill for silhouettes

## Counts

- Objects in file: {qa['objects']}
- P2 objects: {qa['p2_objects']}
- P2 cables: {qa['cable_count']}
- Float suspects: {len(qa['floaters'])}
- Issues: {qa['issues'] or 'none'}

## Stills

{chr(10).join(f"- `{p}`" for p in stills)}

## Not done

- Character, wrap animation, black liquid, photo identity, story beats
"""
    REPORT.write_text(text)
    (ARTIFACT / "PART2_BASEMENT_DETAIL_REPORT.md").write_text(text)


def main() -> None:
    if Path(bpy.data.filepath).resolve() == PART1.resolve():
        raise SystemExit("refusing to run inside hallway.blend")
    if Path(bpy.data.filepath).resolve() != BLEND.resolve():
        raise SystemExit(f"expected {BLEND}, got {bpy.data.filepath}")
    if bpy.data.objects.get("P2_DESK_TOP") is None:
        raise SystemExit("P2_DESK_TOP missing — wrong file")

    rig_before = capture_rig_cables()
    mats = upgrade_materials()
    add_wear_decals(mats)
    rebuild_boxes(mats)
    add_extra_clutter(mats)
    rebuild_cloth_mesh(mats)
    wear_frame()
    add_desk_detail(mats)
    add_detail_cables(mats)
    tune_lights()
    tune_cameras()
    qa = qa_scene(rig_before)
    print(json.dumps({k: qa[k] for k in ("cable_count", "rig_unchanged", "floaters", "issues", "missing_frame")}, indent=2))
    stills = render_stills()
    pack_and_save()
    write_report(qa, stills)
    bpy.context.scene.camera = bpy.data.objects.get("CAM_P2_WIDE")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    print("done")


if __name__ == "__main__":
    main()
