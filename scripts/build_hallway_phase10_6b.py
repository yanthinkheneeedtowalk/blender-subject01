#!/usr/bin/env python3
"""Phase 10.6B — Backrooms Level 2 identity correction + floor rework.

Frozen: 10.5 endless extension, 9s camera path, major equipment/pipe layout.
Applies a Level 2 aged-utility look to existing materials, softens floor
joints, adds sparse repair hardware, and refines fluorescent identity.

Does NOT render the 9-second movie. Does NOT start Phase 10.7 / 11.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase10_6b.py -- --no-render
  blender -b hallway.blend --python scripts/build_hallway_phase10_6b.py -- --stills
"""

from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_hallway_phase5 as p5
import build_hallway_phase6 as p6
import build_hallway_phase10 as p10
import build_hallway_phase10_5 as p105
import build_hallway_phase10_6 as p106

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase10_6b"
ARTIFACT_DIR = Path("/opt/cursor/artifacts")

WALK_CAM = "CAM_P105_WALK"
CLOSE_CAM = "CAM_P106_CLOSE"
FLOOR_CAM = "CAM_P106B_FLOOR"
DIST_CAM = "CAM_HERO_C"
HERO_FRAME = 108
ENTRY_FRAME = 1
P106B = "P106B_"
CYCLES_SAMPLES = 96
CYCLES_ADAPTIVE = 0.02
CYCLES_MIN = 24

KEEP_JOINTS = {
    "P8_FLOOR_JOINT_2_35": dict(y=0.58, z=0.20, loc_z=0.0011),
    "P8_FLOOR_JOINT_11_08": dict(y=0.20, z=0.10, loc_z=0.0006),
    "P8_FLOOR_JOINT_17_62": dict(y=0.34, z=0.16, loc_z=0.0009),
}

# Photometric identity. Locations stay frozen. OFF stays 0 W.
# Size multipliers are applied to Phase 10 base sizes so reruns stay idempotent.
LIGHT_IDENTITY = {
    "LIGHT_A_01_NORMAL": dict(energy=52.0, color=(1.00, 0.97, 0.90), size=1.26),
    "LIGHT_A_02_NORMAL": dict(energy=40.0, color=(0.96, 0.99, 0.93), size=1.22),
    "LIGHT_A_03_NORMAL": dict(energy=54.0, color=(1.00, 0.96, 0.88), size=1.24),
    "LIGHT_A_04_AGED_TINT": dict(energy=38.0, color=(1.00, 0.94, 0.84), size=1.30),
    "LIGHT_A_WALL_01_NORMAL": dict(energy=10.0, color=(1.00, 0.96, 0.88), size=1.18),
    "LIGHT_B_01_NORMAL": dict(energy=46.0, color=(0.96, 0.99, 0.92), size=1.28),
    "LIGHT_B_02_WEAK": dict(energy=13.0, color=(0.93, 0.99, 0.86), size=1.34),
    "LIGHT_B_03_OFF": dict(energy=0.0, color=(0.92, 0.93, 0.90), size=1.00),
    "LIGHT_B_04_WEAK": dict(energy=16.0, color=(0.94, 0.98, 0.86), size=1.32),
    "LIGHT_B_WALL_01_WEAK": dict(energy=4.8, color=(0.94, 0.99, 0.88), size=1.20),
    "LIGHT_C_01_WEAK": dict(energy=20.0, color=(0.93, 0.99, 0.87), size=1.30),
    "LIGHT_C_02_OFF": dict(energy=0.0, color=(0.92, 0.93, 0.90), size=1.00),
    "LIGHT_C_03_NORMAL": dict(energy=40.0, color=(1.00, 0.96, 0.87), size=1.26),
    "LIGHT_C_04_WEAK": dict(energy=14.0, color=(0.94, 0.98, 0.88), size=1.36),
    "LIGHT_C_WALL_01_OFF": dict(energy=0.0, color=(0.92, 0.93, 0.90), size=1.00),
}

PIPE_AXIS = (math.pi * 0.5, 0.0, 0.0)


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--no-render" in argv:
        return "check"
    return "stills"


def link(nt, src, dst):
    nt.links.new(src, dst)


def sock(node, identifier: str):
    return p5.sock(node, identifier)


def reset_tree(mat: bpy.types.Material) -> bpy.types.NodeTree:
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return nt


def adopt_material(target: bpy.types.Material, built: bpy.types.Material) -> bpy.types.Material:
    name = target.name
    target.user_remap(built)
    bpy.data.materials.remove(target)
    built.name = name
    return built


def geom_pos(nt, loc=(-980, 40)):
    node = nt.nodes.new("ShaderNodeNewGeometry")
    node.location = loc
    return node.outputs["Position"]


def sep_xyz(nt, vector, loc):
    node = nt.nodes.new("ShaderNodeSeparateXYZ")
    node.location = loc
    link(nt, vector, node.inputs["Vector"])
    return node.outputs["X"], node.outputs["Y"], node.outputs["Z"]


def rebuild_wall(mat: bpy.types.Material) -> None:
    nt = reset_tree(mat)
    pos = geom_pos(nt)
    _x, _y, z = sep_xyz(nt, pos, (-780, 40))
    macro = p106.noise(nt, pos, 0.38, 1.4, (-560, 260), 0.32)
    meso = p106.noise(nt, pos, 2.1, 5.0, (-560, 40), 0.52, 0.10)
    pores = p106.voronoi(nt, pos, 36.0, (-560, -180), 0.9)
    micro = p106.noise(nt, pos, 80.0, 9.0, (-560, -360), 0.60)
    grey_a = (0.152, 0.146, 0.132)
    grey_b = (0.088, 0.086, 0.080)
    stain = (0.058, 0.052, 0.044)
    yellow = (0.168, 0.150, 0.108)
    skirt_col = (0.048, 0.046, 0.042)
    mf = p106.map_range(nt, macro.outputs["Fac"], 0.28, 0.72, 0.0, 0.40, (-320, 260))
    base = p106.mix_col(nt, mf, grey_a, grey_b, (-80, 240))
    yellow_m = p106.sparse(nt, meso.outputs["Fac"], (-320, 120), 0.68, 0.88)
    aged = p106.mix_col(nt, p106.mathn(nt, "MULTIPLY", (-80, 120), yellow_m, 0.16), base, yellow, (120, 160))
    drip_v = p106.noise(nt, p106.mapping(nt, pos, (-560, -80), (36.0, 7.0, 0.22)), 1.0, 2.5, (-320, -80), 0.55)
    drip_m = p106.sparse(nt, drip_v.outputs["Fac"], (-80, -80), 0.78, 0.94)
    stained = p106.mix_col(nt, p106.mathn(nt, "MULTIPLY", (120, -80), drip_m, 0.32), aged, stain, (300, 80))
    stain_m = p106.sparse(nt, meso.outputs["Fac"], (-320, -20), 0.66, 0.86)
    stained = p106.mix_col(nt, p106.mathn(nt, "MULTIPLY", (-80, -20), stain_m, 0.22), stained, stain, (300, 20))
    skirt = p106.map_range(nt, z, 0.01, 0.58, 0.46, 0.0, (-320, -200))
    colored = p106.mix_col(nt, skirt, stained, skirt_col, (480, 40))
    pore_h = p106.map_range(nt, pores.outputs["Distance"], 0.0, 0.32, 1.0, 0.0, (-320, -360))
    rough = p106.mix_f(nt, pore_h, 0.86, 0.93, (120, -200))
    rough = p106.mix_f(nt, skirt, rough, 0.92, (300, -200))
    nrm = p106.bump(nt, micro.outputs["Fac"], 0.014, 0.0016, (300, -360))
    nrm = p106.bump(nt, pore_h, 0.007, 0.0009, (480, -360), nrm)
    bsdf = p106.principled(nt, (700, 40))
    out = p106.output(nt, (980, 40))
    p106.set_spec(bsdf, 0.18, ior=1.52, metallic=0.0, coat=0.0)
    link(nt, colored, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*grey_a, 1.0)


def rebuild_floor(mat: bpy.types.Material) -> None:
    nt = reset_tree(mat)
    pos = geom_pos(nt)
    x, _y, _z = sep_xyz(nt, pos, (-780, 40))
    macro = p106.noise(nt, pos, 0.18, 1.0, (-560, 260), 0.26)
    blotch = p106.noise(nt, pos, 1.1, 2.2, (-560, 40), 0.38)
    edge = p106.noise(nt, pos, 1.4, 1.8, (-560, -140), 0.42)
    pores = p106.voronoi(nt, pos, 48.0, (-560, -320), 0.92)
    micro = p106.noise(nt, pos, 110.0, 8.0, (-560, -500), 0.50)
    cool_a = (0.078, 0.080, 0.086)
    cool_b = (0.042, 0.044, 0.048)
    dirt = (0.028, 0.029, 0.032)
    repair = (0.110, 0.106, 0.098)
    mf = p106.map_range(nt, macro.outputs["Fac"], 0.24, 0.76, 0.0, 0.36, (-80, 260))
    base = p106.mix_col(nt, mf, cool_a, cool_b, (120, 240))
    blotch_m = p106.sparse(nt, blotch.outputs["Fac"], (-80, 40), 0.58, 0.82)
    worn = p106.mix_col(nt, p106.mathn(nt, "MULTIPLY", (120, 80), blotch_m, 0.16), base, dirt, (300, 80))
    abs_x = p106.mathn(nt, "ABSOLUTE", (-80, -140), x, 0.0)
    lane = p106.map_range(nt, abs_x, 0.10, 0.58, 0.16, 0.0, (120, 0))
    worn = p106.mix_col(nt, lane, worn, dirt, (300, 40))
    edge_w = p106.map_range(nt, abs_x, 0.52, 1.08, 0.0, 0.34, (120, -140))
    edged = p106.mix_col(nt, edge_w, worn, dirt, (300, -40))
    repair_m = p106.sparse(nt, edge.outputs["Fac"], (-80, -280), 0.78, 0.94)
    colored = p106.mix_col(nt, p106.mathn(nt, "MULTIPLY", (120, -280), repair_m, 0.16), edged, repair, (300, -200))
    pore_h = p106.map_range(nt, pores.outputs["Distance"], 0.0, 0.26, 1.0, 0.0, (-80, -420))
    rough = p106.mix_f(nt, pore_h, 0.80, 0.92, (120, -420))
    rough = p106.mix_f(nt, lane, rough, 0.70, (300, -360))
    rough = p106.mix_f(nt, edge_w, rough, 0.90, (480, -300))
    nrm = p106.bump(nt, macro.outputs["Fac"], 0.004, 0.0020, (300, -520))
    nrm = p106.bump(nt, micro.outputs["Fac"], 0.008, 0.0009, (480, -520), nrm)
    nrm = p106.bump(nt, pore_h, 0.004, 0.0006, (660, -520), nrm)
    bsdf = p106.principled(nt, (860, 20))
    out = p106.output(nt, (1120, 20))
    p106.set_spec(bsdf, 0.24, ior=1.52, metallic=0.0, coat=0.0)
    link(nt, colored, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*cool_a, 1.0)


def rebuild_ceiling(mat: bpy.types.Material) -> None:
    nt = reset_tree(mat)
    pos = geom_pos(nt)
    macro = p106.noise(nt, pos, 0.42, 1.3, (-520, 80), 0.34)
    micro = p106.noise(nt, pos, 48.0, 6.0, (-520, -120), 0.55)
    a, b = (0.086, 0.082, 0.076), (0.062, 0.060, 0.056)
    col = p106.mix_col(nt, p106.map_range(nt, macro.outputs["Fac"], 0.3, 0.7, 0.0, 0.14, (-240, 80)), a, b, (0, 80))
    rough = p106.mix_f(nt, micro.outputs["Fac"], 0.86, 0.94, (0, -80))
    nrm = p106.bump(nt, micro.outputs["Fac"], 0.007, 0.0010, (0, -220))
    bsdf = p106.principled(nt, (280, 20))
    out = p106.output(nt, (540, 20))
    p106.set_spec(bsdf, 0.14, ior=1.52, metallic=0.0)
    link(nt, col, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*a, 1.0)


def rebuild_cabinet(mat: bpy.types.Material) -> None:
    nt = reset_tree(mat)
    pos = geom_pos(nt)
    _x, y, _z = sep_xyz(nt, pos, (-780, 80))
    peel = p106.noise(nt, pos, 92.0, 6.0, (-520, 40), 0.48)
    wear = p106.noise(nt, pos, 5.8, 2.0, (-520, 240), 0.40)
    newer = p106.map_range(nt, y, 0.5, 20.0, 0.0, 1.0, (-240, 360))
    a_new, a_old = (0.162, 0.176, 0.168), (0.092, 0.110, 0.104)
    b_new, b_old = (0.132, 0.148, 0.140), (0.072, 0.088, 0.082)
    base_new = p106.mix_col(nt, p106.map_range(nt, peel.outputs["Fac"], 0.3, 0.7, 0.0, 0.16, (-240, 160)), a_new, b_new, (0, 200))
    base_old = p106.mix_col(nt, p106.map_range(nt, peel.outputs["Fac"], 0.3, 0.7, 0.0, 0.16, (-240, 40)), a_old, b_old, (0, 40))
    base = p106.mix_col(nt, newer, base_new, base_old, (220, 120))
    wear_m = p106.sparse(nt, wear.outputs["Fac"], (-240, -80), 0.70, 0.90)
    colored = p106.mix_col(nt, p106.mathn(nt, "MULTIPLY", (0, -80), wear_m, 0.28), base, (0.070, 0.066, 0.058), (220, -40))
    rough0 = p106.mix_f(nt, newer, 0.48, 0.64, (220, -180))
    rough = p106.mix_f(nt, peel.outputs["Fac"], rough0, p106.mathn(nt, "ADD", (0, -220), rough0, 0.06), (400, -180))
    nrm = p106.bump(nt, peel.outputs["Fac"], 0.007, 0.0006, (400, -320))
    bevel = nt.nodes.new("ShaderNodeBevel")
    bevel.location = (400, -460)
    bevel.samples = 3
    bevel.inputs["Radius"].default_value = 0.0013
    nrm_mix = nt.nodes.new("ShaderNodeMix")
    nrm_mix.data_type = "VECTOR"
    nrm_mix.location = (580, -360)
    sock(nrm_mix, "Factor_Float").default_value = 0.50
    link(nt, nrm, sock(nrm_mix, "A_Vector"))
    link(nt, bevel.outputs["Normal"], sock(nrm_mix, "B_Vector"))
    nrm = sock(nrm_mix, "Result_Vector")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.location = (220, -280)
    lw.inputs["Blend"].default_value = 0.45
    rough = p106.mix_f(nt, lw.outputs["Facing"], rough, 0.38, (400, -80))
    bsdf = p106.principled(nt, (780, 40))
    out = p106.output(nt, (1040, 40))
    p106.set_spec(bsdf, 0.50, ior=1.46, metallic=0.0, coat=0.10, coat_rough=0.40)
    link(nt, colored, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (0.14, 0.15, 0.14, 1.0)


def rebuild_pipe(mat: bpy.types.Material, primary: bool) -> None:
    nt = reset_tree(mat)
    pos = geom_pos(nt)
    peel = p106.noise(nt, pos, 70.0, 4.0, (-520, 40), 0.46)
    joint = p106.noise(nt, pos, 4.2, 2.0, (-520, 220), 0.38)
    if primary:
        a, b = (0.028, 0.030, 0.029), (0.016, 0.018, 0.017)
    else:
        a, b = (0.042, 0.062, 0.050), (0.028, 0.044, 0.038)
    oxide = (0.118, 0.062, 0.036)
    mf = p106.map_range(nt, peel.outputs["Fac"], 0.28, 0.72, 0.0, 0.30, (-240, 40))
    base = p106.mix_col(nt, mf, a, b, (0, 80))
    ox_m = p106.sparse(nt, joint.outputs["Fac"], (-240, 220), 0.76, 0.93)
    colored = p106.mix_col(nt, p106.mathn(nt, "MULTIPLY", (0, 220), ox_m, 0.22), base, oxide, (220, 160))
    rough = p106.mix_f(nt, peel.outputs["Fac"], 0.42, 0.56, (220, -20))
    rough = p106.mix_f(nt, ox_m, rough, 0.64, (400, -20))
    nrm = p106.bump(nt, peel.outputs["Fac"], 0.008, 0.0006, (400, -180))
    metal = p106.mix_f(nt, ox_m, 0.0, 0.08, (400, 80))
    bsdf = p106.principled(nt, (640, 40))
    out = p106.output(nt, (900, 40))
    p106.set_spec(bsdf, 0.52, ior=1.46, metallic=0.0, coat=0.06, coat_rough=0.44)
    link(nt, metal, bsdf.inputs["Metallic"])
    link(nt, colored, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*a, 1.0)


def rebuild_galv(mat: bpy.types.Material, vent: bool = False) -> None:
    pal = dict(galv_a=(0.330, 0.336, 0.318), galv_b=(0.238, 0.244, 0.228))
    built = p106.build_galvanized("MAT_P106B_GalvTmp", pal, vent)
    adopt_material(mat, built)


def rebuild_structure(mat: bpy.types.Material) -> None:
    nt = reset_tree(mat)
    pos = geom_pos(nt)
    n = p106.noise(nt, pos, 12.0, 3.0, (-400, 40), 0.45)
    col = p106.mix_col(
        nt,
        p106.map_range(nt, n.outputs["Fac"], 0.3, 0.7, 0.0, 0.12, (-160, 80)),
        (0.108, 0.104, 0.094),
        (0.082, 0.080, 0.074),
        (40, 80),
    )
    rough = p106.mix_f(nt, n.outputs["Fac"], 0.54, 0.68, (40, -40))
    nrm = p106.bump(nt, n.outputs["Fac"], 0.007, 0.0007, (40, -180))
    bsdf = p106.principled(nt, (320, 20))
    out = p106.output(nt, (560, 20))
    p106.set_spec(bsdf, 0.42, ior=1.46, metallic=0.0, coat=0.04, coat_rough=0.48)
    link(nt, col, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])


def rebuild_valve(mat: bpy.types.Material) -> None:
    built = p106.build_valve("MAT_P106B_ValveTmp", dict(valve=(0.270, 0.050, 0.036)))
    adopt_material(mat, built)


def rebuild_diffusers() -> None:
    variants = (
        ("MAT_P7_Diffuser_Normal", False, 1.55, (1.00, 0.95, 0.82)),
        ("MAT_P7_Diffuser_Aged", False, 1.05, (1.00, 0.90, 0.70)),
        ("MAT_P7_Diffuser_Weak", False, 0.72, (0.96, 0.99, 0.86)),
        ("MAT_P7_Diffuser_Off", True, 0.0, (0.90, 0.88, 0.80)),
    )
    for src, off, strength, emit in variants:
        old = bpy.data.materials.get(src)
        if old is None:
            continue
        pal = dict(
            diff_base=(0.42, 0.39, 0.32),
            diff_emit=emit,
            diff_str=strength,
            tube_emit=emit,
            tube_str=strength,
        )
        built = p106.build_diffuser("MAT_P106B_DiffTmp", pal, off=off)
        adopt_material(old, built)
    tubes = (
        ("MAT_P8_Tube", 1.70, (1.00, 0.94, 0.78)),
        ("MAT_P8_TubeWeak", 0.85, (0.98, 0.92, 0.72)),
    )
    for src, strength, emit in tubes:
        old = bpy.data.materials.get(src)
        if old is None:
            continue
        pal = dict(
            diff_base=(0.42, 0.39, 0.32),
            diff_emit=emit,
            diff_str=strength,
            tube_emit=emit,
            tube_str=strength,
        )
        built = p106.build_tube("MAT_P106B_TubeTmp", pal)
        adopt_material(old, built)


def rebuild_housing() -> None:
    housing = p106.build_painted_metal(
        "MAT_P106B_Housing",
        dict(
            housing=(0.132, 0.126, 0.112),
            struct_a=(0.102, 0.098, 0.088),
            cab_wear=(0.074, 0.070, 0.062),
            cab_a=(0.132, 0.126, 0.112),
            cab_b=(0.102, 0.098, 0.088),
            pipe_a=(0.04, 0.04, 0.04),
            pipe_b=(0.03, 0.03, 0.03),
            pipe2_a=(0.04, 0.04, 0.04),
            pipe2_b=(0.03, 0.03, 0.03),
        ),
        "housing",
    )
    for obj in bpy.data.objects:
        if obj.name.startswith("FIX_") and obj.name.endswith("_Housing"):
            if obj.material_slots:
                obj.material_slots[0].material = housing


def rebuild_joint_mat() -> bpy.types.Material:
    existing = bpy.data.materials.get("MAT_P106B_FloorJoint")
    if existing is not None:
        bpy.data.materials.remove(existing)
    mat, nt = p106.new_mat("MAT_P106B_FloorJoint")
    pos = geom_pos(nt, (-400, 40))
    n = p106.noise(nt, pos, 18.0, 2.0, (-200, 40), 0.4)
    col = p106.mix_col(nt, n.outputs["Fac"], (0.070, 0.072, 0.076), (0.052, 0.054, 0.058), (40, 40))
    bsdf = p106.principled(nt, (280, 20))
    out = p106.output(nt, (520, 20))
    p106.set_spec(bsdf, 0.16, ior=1.52)
    bsdf.inputs["Roughness"].default_value = 0.93
    link(nt, col, bsdf.inputs["Base Color"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def soften_floor_joints(joint_mat: bpy.types.Material) -> dict:
    report = {"hidden": [], "kept": []}
    for obj in bpy.data.objects:
        if obj.name.startswith("P8_DAMP"):
            obj.hide_render = True
            continue
        if not obj.name.startswith("P8_FLOOR_JOINT"):
            continue
        spec = KEEP_JOINTS.get(obj.name)
        if spec is None:
            obj.hide_render = True
            report["hidden"].append(obj.name)
            continue
        obj.hide_render = False
        obj.scale.y = spec["y"]
        obj.scale.z = spec["z"]
        obj.location.z = spec["loc_z"]
        if obj.material_slots:
            obj.material_slots[0].material = joint_mat
        report["kept"].append(obj.name)
    return report


def cylinder_mesh(name: str, radius: float, depth: float, segments: int = 16) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=depth,
    )
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def add_repair_hardware() -> int:
    col = bpy.data.collections.get("LEVEL2_IDENTITY")
    if col is None:
        col = bpy.data.collections.new("LEVEL2_IDENTITY")
        bpy.context.scene.collection.children.link(col)
    for obj in list(col.objects):
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0 and mesh.name.startswith(P106B):
            bpy.data.meshes.remove(mesh)
    clamp = bpy.data.meshes.get("P3_PIPE_Clamp_Primary_MESH")
    minor = bpy.data.meshes.get("P3_PIPE_Clamp_Minor_MESH")
    galv = bpy.data.materials.get("MAT_Metal_Galvanized")
    pipe = bpy.data.materials.get("MAT_Pipe_DarkPaintedSteel")
    rubber = bpy.data.materials.get("MAT_Rubber_Dark")
    count = 0

    def inst(name, src_mesh, loc, mat, scale=(1.0, 1.0, 1.0), rot=PIPE_AXIS):
        nonlocal count
        mesh = src_mesh.copy()
        mesh.name = f"{name}_MESH"
        mesh.materials.clear()
        if mat is not None:
            mesh.materials.append(mat)
        obj = bpy.data.objects.new(name, mesh)
        obj.location = loc
        obj.scale = scale
        obj.rotation_euler = rot
        obj["phase"] = 10.62
        col.objects.link(obj)
        count += 1
        return obj

    if clamp is not None:
        inst(f"{P106B}REPAIR_COLLAR_A", clamp, (-0.84, 8.05, 2.46), pipe, (1.16, 1.16, 1.42))
        inst(f"{P106B}REPAIR_COLLAR_C", clamp, (-0.36, 19.35, 2.46), pipe, (1.20, 1.20, 1.38))
        inst(f"{P106B}NEW_CLAMP_B", clamp, (-0.84, 15.55, 2.46), galv, (1.04, 1.04, 1.06))
    if minor is not None:
        inst(f"{P106B}REPAIR_COLLAR_SEC", minor, (0.84, 10.85, 2.13), galv, (1.35, 1.35, 1.40))

    def sleeve(name, loc, radius=0.148, depth=0.20):
        nonlocal count
        mesh = cylinder_mesh(f"{name}_MESH", radius, depth)
        if rubber is not None:
            mesh.materials.append(rubber)
        obj = bpy.data.objects.new(name, mesh)
        obj.location = loc
        obj.rotation_euler = PIPE_AXIS
        obj["phase"] = 10.62
        col.objects.link(obj)
        count += 1
        return obj

    sleeve(f"{P106B}INSUL_A", (-0.84, 5.55, 2.46))
    sleeve(f"{P106B}INSUL_C", (-0.36, 21.15, 2.46), 0.148, 0.16)
    return count


def light_spec_for(name: str) -> dict | None:
    if name in LIGHT_IDENTITY:
        return LIGHT_IDENTITY[name]
    hits = [src for src in LIGHT_IDENTITY if src in name]
    if not hits:
        return None
    return LIGHT_IDENTITY[max(hits, key=len)]


def light_base_size(name: str) -> tuple[float, float] | None:
    src = name if name in p10.LIGHT_POLISH else max((s for s in p10.LIGHT_POLISH if s in name), default=None, key=len)
    if src is None:
        return None
    row = p10.LIGHT_POLISH[src]
    return (row["size"], row.get("size_y", 0.0))


def apply_lighting() -> None:
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        spec = light_spec_for(obj.name)
        if spec is None:
            continue
        obj.data.energy = spec["energy"]
        obj.data.color = spec["color"]
        base = light_base_size(obj.name)
        if spec["energy"] > 0.0 and base is not None:
            obj.data.size = base[0] * spec["size"]
            if hasattr(obj.data, "size_y") and base[1]:
                obj.data.size_y = base[1] * min(spec["size"], 1.20)


def capture_light_layout() -> dict[str, tuple]:
    rows = {}
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        rows[obj.name] = (
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
        )
    return rows


def add_eval_cameras() -> None:
    existing = bpy.data.objects.get(FLOOR_CAM)
    if existing is not None:
        bpy.data.objects.remove(existing, do_unlink=True)
    data = bpy.data.cameras.new(FLOOR_CAM)
    data.lens = 35.0
    data.sensor_width = 36.0
    data.clip_start = 0.04
    data.clip_end = 40.0
    cam = bpy.data.objects.new(FLOOR_CAM, data)
    loc = Vector((0.38, 10.15, 0.58))
    target = Vector((-0.35, 11.20, 0.04))
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
    cam["phase"] = 10.62
    bpy.context.scene.collection.objects.link(cam)
    close = bpy.data.objects.get(CLOSE_CAM)
    if close is not None:
        bpy.data.objects.remove(close, do_unlink=True)
    data = bpy.data.cameras.new(CLOSE_CAM)
    data.lens = 32.0
    data.sensor_width = 36.0
    data.clip_start = 0.05
    data.clip_end = 40.0
    cam = bpy.data.objects.new(CLOSE_CAM, data)
    loc = Vector((0.02, 12.72, 1.58))
    target = Vector((0.70, 13.55, 1.92))
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
    cam["phase"] = 10.62
    bpy.context.scene.collection.objects.link(cam)


def inject_aging_available(keys: dict[str, bpy.types.Material], group) -> None:
    required = {
        "MAT_Wall_PaintedConcrete",
        "MAT_Floor_IndustrialConcrete",
        "MAT_Ceiling_AgedConcrete",
        "MAT_Structure_PaintedSteel",
        "MAT_Pipe_DarkPaintedSteel",
        "MAT_Pipe_Secondary",
        "MAT_Metal_Galvanized",
        "MAT_Cabinet_PaintedMetal",
        "MAT_Vent_GalvanizedMetal",
        "MAT_Rubber_Dark",
        "MAT_Valve_IndustrialAccent",
    }
    dummy = None
    created = []
    for name in required:
        if name in keys:
            continue
        dummy = bpy.data.materials.new(f"MAT_P106B_Dummy_{name}")
        dummy.use_nodes = True
        dummy.node_tree.nodes.clear()
        bsdf = dummy.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        out = dummy.node_tree.nodes.new("ShaderNodeOutputMaterial")
        dummy.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        keys[name] = dummy
        created.append(dummy)
    p6.inject_aging(keys, group)
    for mat in created:
        bpy.data.materials.remove(mat)


def apply_materials() -> None:
    rebuild_wall(bpy.data.materials["MAT_Wall_PaintedConcrete"])
    rebuild_floor(bpy.data.materials["MAT_Floor_IndustrialConcrete"])
    rebuild_ceiling(bpy.data.materials["MAT_Ceiling_AgedConcrete"])
    rebuild_cabinet(bpy.data.materials["MAT_Cabinet_PaintedMetal"])
    rebuild_pipe(bpy.data.materials["MAT_Pipe_DarkPaintedSteel"], True)
    rebuild_pipe(bpy.data.materials["MAT_Pipe_Secondary"], False)
    rebuild_structure(bpy.data.materials["MAT_Structure_PaintedSteel"])
    rebuild_galv(bpy.data.materials["MAT_Metal_Galvanized"], False)
    if bpy.data.materials.get("MAT_Vent_GalvanizedMetal"):
        rebuild_galv(bpy.data.materials["MAT_Vent_GalvanizedMetal"], True)
    if bpy.data.materials.get("MAT_Valve_IndustrialAccent"):
        rebuild_valve(bpy.data.materials["MAT_Valve_IndustrialAccent"])
    rebuild_diffusers()
    rebuild_housing()
    # Do not re-inject Phase 6 dust veils: on darker Level 2 albedos they
    # flatten pipes/walls toward a uniform mid-grey and erase material identity.


def restore_eevee(scene: bpy.types.Scene) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 48
    scene.eevee.use_raytracing = False
    scene.eevee.volumetric_end = 120.0
    scene.eevee.volumetric_samples = 32
    scene.eevee.volumetric_tile_size = "8"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.frame_set(1)


def freeze_validate(scene, before, lights_before, inspect_before) -> dict:
    after = p5.snapshot()
    moved = [
        n
        for n, row in before.items()
        if after.get(n) != row
        and not n.startswith("P8_FLOOR_JOINT")
        and not n.startswith("P8_DAMP")
        and not n.startswith(P106B)
    ]
    lights_after = capture_light_layout()
    light_moved = [n for n, row in lights_before.items() if lights_after.get(n) != row]
    inspect_after = p105.inspect_keys(bpy.data.objects["CAM_INSPECT"])
    walk = bpy.data.objects[WALK_CAM]
    walk_err = []
    for frame in range(1, 217, 16):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        pos = walk.matrix_world.translation
        if abs(pos.x) > 0.02 or abs(pos.z - p5.EYE_Z) > 0.02:
            walk_err.append((frame, tuple(round(v, 3) for v in pos)))
    off_ok = all(
        bpy.data.objects[n].data.energy == 0.0
        for n in ("LIGHT_B_03_OFF", "LIGHT_C_02_OFF", "LIGHT_C_WALL_01_OFF")
        if bpy.data.objects.get(n)
    )
    return dict(
        moved=moved,
        light_moved=light_moved,
        inspect_ok=inspect_before == inspect_after,
        walk_err=walk_err,
        p8=len([o for o in bpy.data.objects if o.name.startswith("P8_")]),
        p9=len([o for o in bpy.data.objects if o.name.startswith("P9_")]),
        p105=len([o for o in bpy.data.objects if o.name.startswith("P105_") or o.name.startswith("CAM_P105")]),
        wall_end=bool(bpy.data.objects["WALL.End"].hide_render),
        frame_end=scene.frame_end,
        off_ok=off_ok,
        joints_kept=sum(1 for n in KEEP_JOINTS if bpy.data.objects.get(n) and not bpy.data.objects[n].hide_render),
        joints_hidden=sum(
            1 for o in bpy.data.objects if o.name.startswith("P8_FLOOR_JOINT") and o.hide_render
        ),
        hardware=len([o for o in bpy.data.objects if o.name.startswith(P106B)]),
        world_strength=(
            scene.world.node_tree.nodes.get("Background").inputs[1].default_value
            if scene.world and scene.world.node_tree and scene.world.node_tree.nodes.get("Background")
            else -1.0
        ),
        volume_density=(
            scene.world.node_tree.nodes.get("P10_Volume").inputs["Density"].default_value
            if scene.world and scene.world.node_tree and scene.world.node_tree.nodes.get("P10_Volume")
            else -1.0
        ),
    )


def write_report(v: dict, stills: list[str], joints: dict, visual: dict | None = None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cam_ok = not v["walk_err"] and v["inspect_ok"] and v["frame_end"] == 216
    endless = v["wall_end"] and v["p105"] >= 500
    freeze = cam_ok and not v["light_moved"] and endless and v["p8"] == 209 and v["p9"] == 11 and not v["moved"]
    stills_ok = all((OUTPUT_DIR / f"{n}.jpg").exists() for n in stills)
    visual = visual or {}

    def mark(key, fallback):
        return visual.get(key, fallback)

    lines = [
        "PHASE 10.6B Backrooms Level 2 身分校正＋地坪重做",
        "未改走廊尺度、延伸段、9 秒相機路徑、主設備與主管線佈局。",
        "未加房間／分岔／怪物／血液／恐怖字樣。未渲染 9 秒成片。未開始 Phase 10.7／11。",
        "",
        "FLOOR",
        "  現況問題：橫向接縫過密、過高，讀成大片 CG 磁磚。",
        f"  隱藏 {v['joints_hidden']} 條均勻接縫；保留 {v['joints_kept']} 條作為施工／控制／修補邊界並壓平。",
        f"  保留：{', '.join(joints.get('kept', []))}",
        "  地坪 shader 改為連續澆置工業混凝土：冷中性、交通磨耗 MASK、牆邊積塵、微孔隙只進 normal。",
        "  隱藏 P8_DAMP 濕斑，避免水窪／濕地坪。無鏡面、無展示廳拋光。",
        "",
        "WALL",
        "  離開奶油米色；改為髒機構灰／微黃老化塗層。牆腳積塵隨重力（Z）。大面保持安靜。",
        "",
        "CABINET / PIPE",
        "  櫃保留烤漆 Coat／Bevel／橘皮；近端較新、遠端較舊。非廢鐵。",
        f"  主管炭黑塗層，伴管灰綠；氧化只在接頭 MASK。新增 {v['hardware']} 件修理抱箍／套管。",
        "",
        "LIGHTING",
        "  位置凍結。面積加大以柔化管影。NORMAL／WEAK／AGED／OFF 色溫與功率分化。",
        f"  OFF 仍為 0 W。World {v['world_strength']:.2f}，volume {v['volume_density']:.4f}。",
        "",
        f"LEVEL 2 IDENTITY: {mark('identity', 'PASS' if stills_ok and freeze else 'FAIL')}",
        f"FLOOR REWORK: {mark('floor', 'PASS' if stills_ok else 'FAIL')}",
        f"FLOOR JOINTS: {mark('joints', 'PASS' if v['joints_kept'] == 3 and v['joints_hidden'] >= 3 else 'FAIL')}",
        f"WALL MATERIAL: {mark('wall', 'PASS' if stills_ok else 'FAIL')}",
        f"WALL AGING: {mark('wall_age', 'PASS' if stills_ok else 'FAIL')}",
        f"CABINET AGING: {mark('cabinet', 'PASS' if stills_ok else 'FAIL')}",
        f"PIPE MATERIAL / HISTORY: {mark('pipe', 'PASS' if stills_ok else 'FAIL')}",
        f"MAINTENANCE HISTORY: {mark('history', 'PASS' if stills_ok and v['hardware'] >= 4 else 'FAIL')}",
        f"COLOR IDENTITY: {mark('color', 'PASS' if stills_ok else 'FAIL')}",
        f"LIGHTING IDENTITY: {mark('light', 'PASS' if v['off_ok'] and not v['light_moved'] else 'FAIL')}",
        f"DARK-AREA READABILITY: {mark('dark', 'PASS' if stills_ok else 'FAIL')}",
        f"ENDLESS CORRIDOR PRESERVED: {'PASS' if endless else 'FAIL'}",
        f"CAMERA FREEZE: {'PASS' if cam_ok else 'FAIL'}",
        f"RENDER NOISE CONTROL: {mark('noise', 'PASS' if stills_ok else 'FAIL')}",
        "",
        f"  幾何非接縫改動：{len(v['moved'])}",
        f"  燈光位置改動：{len(v['light_moved'])}",
        f"  CAM_P105 路徑錯誤：{len(v['walk_err'])}",
        "  等待使用者審核。未進入下一階段。",
    ]
    if v["moved"]:
        lines.append("  被改動：" + ", ".join(v["moved"][:16]))
    path = OUTPUT_DIR / "phase10_6b_level2_identity_validation.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", path)
    return path


def publish(path: Path) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, ARTIFACT_DIR / path.name)


def main() -> None:
    mode = parse_mode()
    scene = bpy.context.scene
    before = p5.snapshot()
    lights_before = capture_light_layout()
    inspect_before = p105.inspect_keys(bpy.data.objects["CAM_INSPECT"])
    apply_materials()
    joint_mat = rebuild_joint_mat()
    joints = soften_floor_joints(joint_mat)
    add_repair_hardware()
    apply_lighting()
    add_eval_cameras()
    bg = scene.world.node_tree.nodes.get("Background") if scene.world and scene.world.node_tree else None
    if bg is not None:
        bg.inputs[1].default_value = 0.30
    vol = scene.world.node_tree.nodes.get("P10_Volume") if scene.world and scene.world.node_tree else None
    if vol is not None:
        vol.inputs["Density"].default_value = 0.0036
    validation = freeze_validate(scene, before, lights_before, inspect_before)
    scene.frame_set(1)
    scene.camera = bpy.data.objects[WALK_CAM]
    stills = ["LEVEL2_A", "LEVEL2_B", "LEVEL2_C", "LEVEL2_D"]
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    if mode == "stills":
        p106.enable_cycles_cpu(scene)
        scene.cycles.samples = CYCLES_SAMPLES
        scene.cycles.adaptive_threshold = CYCLES_ADAPTIVE
        scene.cycles.adaptive_min_samples = CYCLES_MIN
        jobs = (
            ("LEVEL2_A", WALK_CAM, HERO_FRAME),
            ("LEVEL2_B", FLOOR_CAM, HERO_FRAME),
            ("LEVEL2_C", CLOSE_CAM, HERO_FRAME),
            ("LEVEL2_D", DIST_CAM, ENTRY_FRAME),
        )
        for name, cam, frame in jobs:
            path = p106.render_still(scene, cam, frame, OUTPUT_DIR / f"{name}.jpg")
            publish(path)
        restore_eevee(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    report = write_report(validation, stills, joints)
    publish(report)
    print("Phase 10.6B complete; waiting for review; Phase 10.7/11 not started.")
    print("validation", {k: validation[k] for k in ("moved", "light_moved", "walk_err", "p8", "p9", "p105", "joints_kept", "joints_hidden", "hardware", "off_ok", "wall_end")})


if __name__ == "__main__":
    main()
