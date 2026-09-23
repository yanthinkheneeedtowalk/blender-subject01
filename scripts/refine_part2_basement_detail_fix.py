#!/usr/bin/env python3
"""QA fix pass on the already-refined part2_basement.blend.

Corrects cobblestone walls, desk dust sheet, paper-thin cloth, crate floor
clip, and desk camera crop. Does not touch hallway.blend or RIG cables.
"""

from __future__ import annotations

import json
import math
import random
import shutil
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND = ROOT / "part2_basement.blend"
PART1 = ROOT / "hallway.blend"
STILL_DIR = ROOT / "renders" / "part2_basement" / "stills"
ARTIFACT = Path("/opt/cursor/artifacts")
CHECKPOINT = ROOT / "renders" / "checkpoints" / "part2_basement_detail.blend"
QA_JSON = ROOT / "renders" / "part2_basement" / "detail_qa.json"

DESK = (0.08, 27.22, 0.0)
CHAIR = (0.04, 26.48, 0.0)
DESK_TOP_Z = 0.75
COL_FRAME = "P2_FRAME_CLOTH"
COL_CLUTTER = "P2_CLUTTER"
COL_ARCH = "P2_ARCH"
COL_PROPS = "P2_DESK_PROPS"
RIG_NAMES = [f"P2_CABLE_RIG_{i:02d}" for i in range(1, 7)]


def col(name: str):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def link(obj, collection):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def sock(node, ident: str):
    for s in list(node.inputs) + list(node.outputs):
        if s.identifier == ident or s.name == ident:
            return s
    raise KeyError(ident)


def select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def delete_object(obj):
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and data.users == 0:
        if isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)


def snap_ground(obj, z=0.0):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    minz = min(c.z for c in corners)
    obj.location.z += z - minz


def apply_modifiers(obj):
    select_only(obj)
    deps = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(deps))
    old = obj.data
    obj.modifiers.clear()
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def shade_smooth(obj):
    if obj.type != "MESH":
        return
    select_only(obj)
    try:
        bpy.ops.object.shade_smooth()
    except Exception:
        for p in obj.data.polygons:
            p.use_smooth = True


def look_at(cam, target):
    cam.rotation_euler = (Vector(target) - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()


def principled_bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def set_blend(mat, method="HASHED"):
    if hasattr(mat, "blend_method"):
        try:
            mat.blend_method = method
        except TypeError:
            pass
    if hasattr(mat, "surface_render_method"):
        try:
            mat.surface_render_method = "DITHERED" if method == "HASHED" else "BLENDED"
        except TypeError:
            pass


def capture_rig():
    out = {}
    for name in RIG_NAMES:
        obj = bpy.data.objects.get(name)
        if obj is None:
            out[name] = None
            continue
        pts = []
        for sp in obj.data.splines:
            for bp in sp.bezier_points:
                pts.append([round(bp.co.x, 5), round(bp.co.y, 5), round(bp.co.z, 5)])
        out[name] = {"bevel": round(obj.data.bevel_depth, 5), "points": pts}
    return out


def rebuild_concrete(name: str, seed: float, vertical: bool):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (420, 0)
    out.location = (700, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.12
    bsdf.inputs["Metallic"].default_value = 0.0

    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    if vertical:
        mapping.inputs["Scale"].default_value = (1.0, 0.18 + seed * 0.04, 1.55)
    else:
        mapping.inputs["Scale"].default_value = (1.2, 1.0, 0.16)

    n_large = nt.nodes.new("ShaderNodeTexNoise")
    n_large.inputs["Scale"].default_value = 2.6 + seed * 0.4
    n_large.inputs["Detail"].default_value = 8.0
    n_large.inputs["Roughness"].default_value = 0.55

    n_grit = nt.nodes.new("ShaderNodeTexNoise")
    n_grit.inputs["Scale"].default_value = 70.0 + seed * 5.0
    n_grit.inputs["Detail"].default_value = 11.0
    n_grit.inputs["Roughness"].default_value = 0.70

    n_damp = nt.nodes.new("ShaderNodeTexNoise")
    n_damp.inputs["Scale"].default_value = 1.8 + seed * 0.3
    n_damp.inputs["Detail"].default_value = 6.0
    n_damp.inputs["Roughness"].default_value = 0.45

    # Hairline cracks only — isolate a thin edge, do not tile the wall.
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
    col_dry.color_ramp.elements[0].position = 0.20
    col_dry.color_ramp.elements[0].color = (0.11, 0.105, 0.09, 1)
    mid = col_dry.color_ramp.elements.new(0.48)
    mid.color = (0.20, 0.19, 0.165, 1)
    col_dry.color_ramp.elements[1].position = 0.82
    col_dry.color_ramp.elements[1].color = (0.29, 0.27, 0.23, 1)

    damp_mask = nt.nodes.new("ShaderNodeValToRGB")
    damp_mask.color_ramp.elements[0].position = 0.34
    damp_mask.color_ramp.elements[0].color = (0.08, 0.10, 0.09, 1)
    damp_mask.color_ramp.elements[1].position = 0.70
    damp_mask.color_ramp.elements[1].color = (1, 1, 1, 1)

    mix_damp = nt.nodes.new("ShaderNodeMix")
    mix_damp.data_type = "RGBA"
    mix_damp.blend_type = "MULTIPLY"
    sock(mix_damp, "Factor_Float").default_value = 0.48

    mix_crack = nt.nodes.new("ShaderNodeMix")
    mix_crack.data_type = "RGBA"
    mix_crack.blend_type = "MULTIPLY"
    sock(mix_crack, "Factor_Float").default_value = 0.18

    mix_grit = nt.nodes.new("ShaderNodeMix")
    mix_grit.data_type = "RGBA"
    mix_grit.blend_type = "MULTIPLY"
    sock(mix_grit, "Factor_Float").default_value = 0.16

    rough = nt.nodes.new("ShaderNodeValToRGB")
    rough.color_ramp.elements[0].position = 0.28
    rough.color_ramp.elements[0].color = (0.40, 0.40, 0.40, 1)
    rough.color_ramp.elements[1].position = 0.82
    rough.color_ramp.elements[1].color = (0.95, 0.95, 0.95, 1)

    bump_c = nt.nodes.new("ShaderNodeBump")
    bump_c.inputs["Strength"].default_value = 0.12
    bump_c.inputs["Distance"].default_value = 0.012
    bump_g = nt.nodes.new("ShaderNodeBump")
    bump_g.inputs["Strength"].default_value = 0.16
    bump_g.inputs["Distance"].default_value = 0.006

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
    nt.links.new(sock(mix_crack, "Result_Color"), sock(mix_grit, "A_Color"))
    nt.links.new(n_grit.outputs["Fac"], sock(mix_grit, "B_Color"))
    nt.links.new(sock(mix_grit, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(n_damp.outputs["Fac"], rough.inputs["Fac"])
    nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(vor.outputs["Distance"], bump_c.inputs["Height"])
    nt.links.new(bump_c.outputs["Normal"], bump_g.inputs["Normal"])
    nt.links.new(n_grit.outputs["Fac"], bump_g.inputs["Height"])
    nt.links.new(bump_g.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def rebuild_dust_mat():
    mat = bpy.data.materials.get("MAT_P2_Dust")
    if mat is None:
        mat = bpy.data.materials.new("MAT_P2_Dust")
    mat.use_nodes = True
    set_blend(mat, "HASHED")
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.98
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.02
    coord = nt.nodes.new("ShaderNodeTexCoord")
    # Corner-heavy film using object coords centered on the plane.
    mapn = nt.nodes.new("ShaderNodeMapping")
    mapn.inputs["Scale"].default_value = (6.0, 1.0, 7.5)
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 9.0
    n1.inputs["Detail"].default_value = 12.0
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 55.0
    n2.inputs["Detail"].default_value = 6.0
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    subx = nt.nodes.new("ShaderNodeMath")
    subx.operation = "SUBTRACT"
    subx.inputs[1].default_value = 0.0
    absx = nt.nodes.new("ShaderNodeMath")
    absx.operation = "ABSOLUTE"
    absz = nt.nodes.new("ShaderNodeMath")
    absz.operation = "ABSOLUTE"
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    # Generated 0-1 → distance from center.
    subz = nt.nodes.new("ShaderNodeMath")
    subz.operation = "SUBTRACT"
    subx.inputs[1].default_value = 0.5
    subz.inputs[1].default_value = 0.5
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.04
    cr.color_ramp.elements[0].color = (0.28, 0.25, 0.20, 0.52)
    mid = cr.color_ramp.elements.new(0.38)
    mid.color = (0.32, 0.29, 0.23, 0.72)
    cr.color_ramp.elements[1].position = 0.78
    cr.color_ramp.elements[1].color = (0.38, 0.34, 0.27, 0.94)
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    specks = nt.nodes.new("ShaderNodeValToRGB")
    specks.color_ramp.elements[0].position = 0.55
    specks.color_ramp.elements[0].color = (0.35, 0.35, 0.35, 1)
    specks.color_ramp.elements[1].position = 0.85
    specks.color_ramp.elements[1].color = (1, 1, 1, 1)
    mul2 = nt.nodes.new("ShaderNodeMath")
    mul2.operation = "MULTIPLY"
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.28
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["X"], subx.inputs[0])
    nt.links.new(sep.outputs["Z"], subz.inputs[0])
    nt.links.new(subx.outputs["Value"], absx.inputs[0])
    nt.links.new(subz.outputs["Value"], absz.inputs[0])
    nt.links.new(absx.outputs["Value"], add.inputs[0])
    nt.links.new(absz.outputs["Value"], add.inputs[1])
    nt.links.new(add.outputs["Value"], cr.inputs["Fac"])
    nt.links.new(coord.outputs["Object"], n1.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n2.inputs["Vector"])
    nt.links.new(n2.outputs["Fac"], specks.inputs["Fac"])
    nt.links.new(cr.outputs["Alpha"], mul.inputs[0])
    nt.links.new(n1.outputs["Fac"], mul.inputs[1])
    nt.links.new(mul.outputs["Value"], mul2.inputs[0])
    nt.links.new(specks.outputs["Color"], mul2.inputs[1])
    nt.links.new(mul2.outputs["Value"], bsdf.inputs["Alpha"])
    nt.links.new(cr.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(n1.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def rebuild_glass_mat():
    mat = bpy.data.materials.get("MAT_P2_Glass")
    if mat is None:
        return
    set_blend(mat, "HASHED")
    bsdf = principled_bsdf(mat)
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.86
    bsdf.inputs["Alpha"].default_value = 0.16
    bsdf.inputs["Roughness"].default_value = 0.14


def rebuild_cloth_mat():
    mat = bpy.data.materials.get("MAT_P2_Cloth")
    if mat is None:
        mat = bpy.data.materials.new("MAT_P2_Cloth")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.93
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.05
    coord = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 8.5
    n1.inputs["Detail"].default_value = 12.0
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 32.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.18
    cr.color_ramp.elements[0].color = (0.06, 0.065, 0.055, 1)
    stain = cr.color_ramp.elements.new(0.42)
    stain.color = (0.11, 0.09, 0.07, 1)
    cr.color_ramp.elements[1].position = 0.82
    cr.color_ramp.elements[1].color = (0.20, 0.18, 0.15, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.42
    bump.inputs["Distance"].default_value = 0.004
    nt.links.new(coord.outputs["Object"], n1.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n2.inputs["Vector"])
    nt.links.new(n1.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def rebuild_cloth_mesh():
    old = bpy.data.objects.get("P2_CLOTH")
    loc = (0.048, 27.118, DESK_TOP_Z + 0.012)
    rot_z = math.radians(26.0)
    if old:
        loc = (old.location.x, old.location.y, DESK_TOP_Z + 0.012)
        rot_z = old.rotation_euler[2]
        delete_object(old)
    c = col(COL_FRAME)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=28, y_subdivisions=22, size=1.0, location=loc)
    cloth = bpy.context.object
    cloth.name = "P2_CLOTH"
    cloth.scale = (0.176, 0.132, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    rng = random.Random(4411)
    for v in cloth.data.vertices:
        x, y = v.co.x, v.co.y
        fold = 0.0075 * math.sin((x + 0.02) * 22.0) * math.cos(y * 9.0)
        wrinkle = 0.0032 * math.sin(x * 48.0 + y * 18.0) * math.cos(y * 36.0)
        wrinkle += 0.0020 * math.sin(x * 70.0) * math.sin(y * 54.0)
        v.co.z += fold + wrinkle
        edge = max(abs(x) / 0.088, abs(y) / 0.066)
        if edge > 0.86:
            v.co.x += rng.uniform(-0.006, 0.006)
            v.co.y += rng.uniform(-0.007, 0.005)
            if rng.random() < 0.28:
                v.co.x += rng.choice((-1.0, 1.0)) * rng.uniform(0.004, 0.011)
                v.co.y += rng.choice((-1.0, 1.0)) * rng.uniform(0.003, 0.009)
            v.co.z += rng.uniform(-0.001, 0.003)
    cloth.rotation_euler = (0.045, -0.03, rot_z)
    cloth.data.materials.clear()
    cloth.data.materials.append(bpy.data.materials["MAT_P2_Cloth"])
    solid = cloth.modifiers.new("thickness", "SOLIDIFY")
    solid.thickness = 0.0085
    solid.offset = 1.0
    sub = cloth.modifiers.new("sub", "SUBSURF")
    sub.levels = 2
    sub.render_levels = 2
    apply_modifiers(cloth)
    shade_smooth(cloth)
    link(cloth, c)
    corners = [cloth.matrix_world @ Vector(ch) for ch in cloth.bound_box]
    minz = min(ch.z for ch in corners)
    cloth.location.z += (DESK_TOP_Z + 0.0015) - minz


def delete_named_prefix(prefix: str):
    for obj in list(bpy.data.objects):
        if obj.name.startswith(prefix):
            delete_object(obj)


def fix_crates():
    specs = {
        "P2_CRATE_PLASTIC": (0.46, 0.32, 0.22),
        "P2_CRATE_GREY": (0.38, 0.28, 0.16),
        "P2_CRATE_BLUE": (0.34, 0.26, 0.14),
    }
    for name, (sx, sy, sz) in specs.items():
        body = bpy.data.objects.get(name)
        if body is None:
            continue
        for child in list(body.children):
            delete_object(child)
        snap_ground(body, 0.0)
        t = 0.018
        mat = body.data.materials[0] if body.data.materials else None
        collection = body.users_collection[0]
        # Walls sit on the bottom plate, height sz, no floor clip.
        walls = [
            (0.0, sy * 0.5 - t * 0.5, sx, t, sz),
            (0.0, -sy * 0.5 + t * 0.5, sx, t, sz),
            (sx * 0.5 - t * 0.5, 0.0, t, sy - 2 * t, sz),
            (-sx * 0.5 + t * 0.5, 0.0, t, sy - 2 * t, sz),
        ]
        zc = body.location.z + t * 0.5 + sz * 0.5
        created = []
        for i, (dx, dy, wx, wy, wz) in enumerate(walls):
            bpy.ops.mesh.primitive_cube_add(
                size=1.0, location=(body.location.x + dx, body.location.y + dy, zc)
            )
            w = bpy.context.object
            w.name = f"{name}_W{i}"
            w.scale = (wx, wy, wz)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            if mat:
                w.data.materials.clear()
                w.data.materials.append(mat)
            link(w, collection)
            created.append(w)
        select_only(body)
        for w in created:
            w.select_set(True)
        bpy.ops.object.join()
        body = bpy.context.object
        body.name = name
        snap_ground(body, 0.0)
        shade_smooth(body)


def shade_clutter():
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if obj.name.startswith(("P2_BOX_", "P2_CRATE", "P2_CRT", "P2_KEYBOARD", "P2_DRAWER", "P2_STOOL", "P2_LEAN")):
            shade_smooth(obj)


def tune_hero_camera_and_light():
    desk = bpy.data.objects.get("CAM_P2_DESK")
    if desk:
        desk.location = (0.18, 26.70, 1.08)
        desk.data.lens = 35.0
        look_at(desk, (-0.06, 27.14, 0.84))
    sit = bpy.data.objects.get("CAM_P2_SIT")
    if sit:
        sit.location = (CHAIR[0] + 0.02, CHAIR[1] + 0.10, 1.18)
        look_at(sit, (DESK[0] - 0.10, DESK[1] - 0.02, 0.84))
    kiss = bpy.data.objects.get("LIGHT_P2_FRAME_KISS")
    if kiss:
        kiss.data.energy = 8.5
        kiss.location = (-0.04, 26.88, 1.02)


def render_stills():
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
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
        scene.camera = bpy.data.objects[cam_name]
        scene.frame_set(frame)
        path = STILL_DIR / fname
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        (ARTIFACT / f"part2_detail_{fname}").write_bytes(path.read_bytes())
        paths.append(path)
        print("still", path)
    scene.camera = orig_cam
    scene.frame_set(orig_frame)
    return paths


def main():
    if Path(bpy.data.filepath).resolve() == PART1.resolve():
        raise SystemExit("refusing to run inside hallway.blend")
    rig_before = capture_rig()
    rebuild_concrete("MAT_P2_Wall", 0.35, True)
    rebuild_concrete("MAT_P2_Floor", 1.15, False)
    rebuild_concrete("MAT_P2_Ceil", 2.05, False)
    rebuild_dust_mat()
    rebuild_glass_mat()
    rebuild_cloth_mat()
    delete_named_prefix("P2_WALL_DRIP_")
    film = bpy.data.objects.get("P2_DESK_DUST_FILM")
    if film:
        delete_object(film)
    rebuild_cloth_mesh()
    fix_crates()
    shade_clutter()
    tune_hero_camera_and_light()
    rig_after = capture_rig()
    print("rig_unchanged", rig_before == rig_after)
    crate_issues = []
    for name in ("P2_CRATE_PLASTIC", "P2_CRATE_GREY", "P2_CRATE_BLUE"):
        obj = bpy.data.objects.get(name)
        if not obj:
            crate_issues.append(f"missing {name}")
            continue
        minz = min((obj.matrix_world @ Vector(c)).z for c in obj.bound_box)
        print(name, "minz", round(minz, 4))
        if minz < -0.02:
            crate_issues.append(f"{name} minz={minz:.3f}")
    print("crate_issues", crate_issues)
    render_stills()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    shutil.copy2(BLEND, CHECKPOINT)
    shutil.copy2(BLEND, ARTIFACT / "part2_basement.blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    print("saved", BLEND, BLEND.stat().st_size)
    print("done")


if __name__ == "__main__":
    main()
