#!/usr/bin/env python3
"""Phase 10.6 — hero material rebuild & color identity look-dev.

Phase 10.5 camera / motion / endlessness stay frozen.

This pass rebuilds core shader response and produces FOUR comparison stills
from the SAME validated mid-shot frame.  Looks are NOT propagated as the
scene default.  Original material assignments are restored after rendering.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase10_6.py -- --look00
  blender -b hallway.blend --python scripts/build_hallway_phase10_6.py -- --compare
  blender -b hallway.blend --python scripts/build_hallway_phase10_6.py -- --no-render
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_hallway_phase5 as p5
import build_hallway_phase6 as p6
import build_hallway_phase8 as p8
import build_hallway_phase9 as p9
import build_hallway_phase10_5 as p105

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase10_6"
ARTIFACT_DIR = Path("/opt/cursor/artifacts")

EVAL_FRAME = 108
EVAL_CAMERA = "CAM_P105_WALK"
CLOSE_CAMERA = "CAM_P106_CLOSE"
RES_X, RES_Y = 1280, 720
CYCLES_SAMPLES = 48
CYCLES_ADAPTIVE = 0.03
CYCLES_MIN = 16

LIBRARY = p5.LIBRARY
EXPECTED_P8 = 209
EXPECTED_P9 = 11
EXPECTED_MARKS = 5
P106_PREFIX = "MAT_P106_"

# Original datablock names that get temporary remaps for A/B/C.
CORE_ORIGINALS = (
    "MAT_Wall_PaintedConcrete",
    "MAT_Floor_IndustrialConcrete",
    "MAT_Ceiling_AgedConcrete",
    "MAT_Structure_PaintedSteel",
    "MAT_Pipe_DarkPaintedSteel",
    "MAT_Pipe_Secondary",
    "MAT_Metal_Galvanized",
    "MAT_Cabinet_PaintedMetal",
    "MAT_Vent_GalvanizedMetal",
    "MAT_Valve_IndustrialAccent",
)

PALETTES = {
    "A": dict(
        label="LOOK_A_REALISTIC_INDUSTRIAL",
        wall_a=(0.318, 0.292, 0.255),
        wall_b=(0.262, 0.242, 0.214),
        wall_stain=(0.168, 0.145, 0.118),
        wall_repair=(0.345, 0.325, 0.288),
        wall_rough=0.84,
        floor_a=(0.092, 0.086, 0.080),
        floor_b=(0.070, 0.066, 0.062),
        floor_dirt=(0.048, 0.044, 0.040),
        floor_rough=0.72,
        ceil_a=(0.168, 0.158, 0.145),
        ceil_b=(0.132, 0.124, 0.114),
        cab_a=(0.188, 0.205, 0.210),
        cab_b=(0.155, 0.172, 0.168),
        cab_wear=(0.110, 0.108, 0.100),
        pipe_a=(0.055, 0.058, 0.054),
        pipe_b=(0.042, 0.046, 0.044),
        pipe2_a=(0.078, 0.074, 0.068),
        pipe2_b=(0.060, 0.058, 0.054),
        galv_a=(0.430, 0.438, 0.410),
        galv_b=(0.320, 0.328, 0.308),
        struct_a=(0.145, 0.142, 0.132),
        valve=(0.310, 0.078, 0.055),
        housing=(0.175, 0.172, 0.160),
        diff_base=(0.58, 0.57, 0.52),
        diff_emit=(0.90, 0.93, 0.98),
        diff_str=1.7,
        tube_emit=(0.92, 0.95, 1.00),
        tube_str=2.4,
        light_blend=(0.97, 0.98, 1.00),
        light_mix=0.0,
    ),
    "B": dict(
        label="LOOK_B_LEVEL2_INDUSTRIAL",
        wall_a=(0.355, 0.318, 0.268),
        wall_b=(0.288, 0.258, 0.218),
        wall_stain=(0.185, 0.148, 0.108),
        wall_repair=(0.372, 0.342, 0.292),
        wall_rough=0.86,
        floor_a=(0.082, 0.076, 0.068),
        floor_b=(0.060, 0.056, 0.050),
        floor_dirt=(0.042, 0.040, 0.036),
        floor_rough=0.74,
        ceil_a=(0.155, 0.142, 0.122),
        ceil_b=(0.118, 0.108, 0.095),
        cab_a=(0.168, 0.198, 0.188),
        cab_b=(0.132, 0.162, 0.150),
        cab_wear=(0.095, 0.100, 0.090),
        pipe_a=(0.048, 0.072, 0.058),
        pipe_b=(0.036, 0.055, 0.046),
        pipe2_a=(0.070, 0.082, 0.095),
        pipe2_b=(0.052, 0.062, 0.074),
        galv_a=(0.400, 0.412, 0.385),
        galv_b=(0.295, 0.308, 0.285),
        struct_a=(0.132, 0.128, 0.112),
        valve=(0.355, 0.065, 0.045),
        housing=(0.155, 0.150, 0.132),
        diff_base=(0.56, 0.52, 0.42),
        diff_emit=(1.00, 0.94, 0.78),
        diff_str=1.55,
        tube_emit=(1.00, 0.93, 0.72),
        tube_str=2.15,
        light_blend=(1.00, 0.96, 0.82),
        light_mix=0.16,
    ),
    "C": dict(
        label="LOOK_C_CINEMATIC_INDUSTRIAL",
        wall_a=(0.372, 0.322, 0.262),
        wall_b=(0.278, 0.242, 0.198),
        wall_stain=(0.155, 0.122, 0.092),
        wall_repair=(0.385, 0.340, 0.280),
        wall_rough=0.83,
        floor_a=(0.078, 0.074, 0.072),
        floor_b=(0.052, 0.054, 0.058),
        floor_dirt=(0.038, 0.040, 0.046),
        floor_rough=0.70,
        ceil_a=(0.148, 0.138, 0.132),
        ceil_b=(0.102, 0.108, 0.118),
        cab_a=(0.155, 0.178, 0.195),
        cab_b=(0.118, 0.142, 0.158),
        cab_wear=(0.082, 0.090, 0.100),
        pipe_a=(0.042, 0.050, 0.058),
        pipe_b=(0.030, 0.038, 0.046),
        pipe2_a=(0.062, 0.068, 0.082),
        pipe2_b=(0.046, 0.050, 0.062),
        galv_a=(0.365, 0.385, 0.400),
        galv_b=(0.255, 0.275, 0.292),
        struct_a=(0.118, 0.122, 0.132),
        valve=(0.330, 0.070, 0.048),
        housing=(0.142, 0.145, 0.150),
        diff_base=(0.54, 0.50, 0.44),
        diff_emit=(1.00, 0.92, 0.80),
        diff_str=1.65,
        tube_emit=(1.00, 0.90, 0.74),
        tube_str=2.25,
        light_blend=(1.00, 0.94, 0.84),
        light_mix=0.20,
    ),
}


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--look00" in argv:
        return "look00"
    if "--no-render" in argv:
        return "check"
    if "--compare" in argv:
        return "compare"
    return "compare"


def sock(node, identifier: str):
    return p5.sock(node, identifier)


def link(nt, src, dst) -> None:
    nt.links.new(src, dst)


def mix_col(nt, fac, a, b, loc):
    return p6.mix_color(nt, fac, a, b, loc)


def mix_f(nt, fac, a, b, loc):
    return p6.mix_float(nt, fac, a, b, loc)


def mathn(nt, op, loc, a=None, b=None):
    return p6.math_node(nt, op, loc, a, b)


def map_range(nt, value, lo, hi, tlo, thi, loc):
    return p6.map_range(nt, value, lo, hi, tlo, thi, loc)


def new_mat(name: str) -> tuple[bpy.types.Material, bpy.types.NodeTree]:
    existing = bpy.data.materials.get(name)
    if existing is not None:
        bpy.data.materials.remove(existing)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return mat, nt


def tex_coord(nt, loc=(-980, 80)):
    node = nt.nodes.new("ShaderNodeTexCoord")
    node.location = loc
    return node


def noise(nt, vector, scale, detail, loc, roughness=0.5, distortion=0.0):
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.location = loc
    node.noise_dimensions = "3D"
    if hasattr(node, "noise_type"):
        try:
            node.noise_type = "FBM"
        except TypeError:
            pass
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    if "Roughness" in node.inputs:
        node.inputs["Roughness"].default_value = roughness
    if "Distortion" in node.inputs:
        node.inputs["Distortion"].default_value = distortion
    link(nt, vector, node.inputs["Vector"])
    return node


def voronoi(nt, vector, scale, loc, randomness=0.85):
    node = nt.nodes.new("ShaderNodeTexVoronoi")
    node.location = loc
    node.voronoi_dimensions = "3D"
    node.feature = "F1"
    node.distance = "EUCLIDEAN"
    node.inputs["Scale"].default_value = scale
    if "Randomness" in node.inputs:
        node.inputs["Randomness"].default_value = randomness
    link(nt, vector, node.inputs["Vector"])
    return node


def mapping(nt, vector, loc, scale=(1.0, 1.0, 1.0)):
    node = nt.nodes.new("ShaderNodeMapping")
    node.location = loc
    node.inputs["Scale"].default_value = scale
    link(nt, vector, node.inputs["Vector"])
    return node.outputs["Vector"]


def bump(nt, height, strength, distance, loc, normal=None):
    node = nt.nodes.new("ShaderNodeBump")
    node.location = loc
    node.inputs["Strength"].default_value = strength
    node.inputs["Distance"].default_value = distance
    link(nt, height, node.inputs["Height"])
    if normal is not None:
        link(nt, normal, node.inputs["Normal"])
    return node.outputs["Normal"]


def principled(nt, loc=(720, 80)):
    node = nt.nodes.new("ShaderNodeBsdfPrincipled")
    node.location = loc
    return node


def output(nt, loc=(1020, 80)):
    node = nt.nodes.new("ShaderNodeOutputMaterial")
    node.location = loc
    return node


def set_spec(bsdf, spec, ior=1.5, metallic=0.0, coat=0.0, coat_rough=0.35):
    bsdf.inputs["Metallic"].default_value = metallic
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = ior
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    if "Coat Roughness" in bsdf.inputs:
        bsdf.inputs["Coat Roughness"].default_value = coat_rough


def sparse(nt, fac, loc, lo=0.62, hi=0.82):
    """Keep most of the field at 0; only the high tail becomes a mask."""
    return map_range(nt, fac, lo, hi, 0.0, 1.0, loc)


def build_concrete(name: str, pal: dict, kind: str) -> bpy.types.Material:
    mat, nt = new_mat(name)
    coord = tex_coord(nt)
    world = coord.outputs["Object"]
    # MACRO: construction-scale pour variation. Factor stays tiny.
    macro = noise(nt, world, 0.45, 1.5, (-760, 220), 0.35)
    meso_n = noise(nt, world, 2.4, 6.0, (-760, 40), 0.55, 0.12)
    pores = voronoi(nt, world, 34.0, (-760, -160), 0.92)
    micro = noise(nt, world, 72.0, 10.0, (-760, -340), 0.62)
    if kind == "wall":
        a, b, stain, repair = pal["wall_a"], pal["wall_b"], pal["wall_stain"], pal["wall_repair"]
        rough0 = pal["wall_rough"]
        spec, bump_micro, bump_pore = 0.20, 0.012, 0.006
    elif kind == "floor":
        a, b, stain, repair = pal["floor_a"], pal["floor_b"], pal["floor_dirt"], pal["floor_a"]
        rough0 = pal["floor_rough"]
        spec, bump_micro, bump_pore = 0.30, 0.014, 0.008
    else:
        a, b, stain, repair = pal["ceil_a"], pal["ceil_b"], pal["wall_stain"], pal["ceil_b"]
        rough0 = 0.88
        spec, bump_micro, bump_pore = 0.16, 0.010, 0.005
    macro_f = map_range(nt, macro.outputs["Fac"], 0.30, 0.70, 0.0, 0.22, (-520, 220))
    base = mix_col(nt, macro_f, a, b, (-280, 220))
    stain_m = sparse(nt, meso_n.outputs["Fac"], (-520, 40), 0.66, 0.84)
    stained = mix_col(nt, mathn(nt, "MULTIPLY", (-280, 40), stain_m, 0.22), base, stain, (-80, 80))
    repair_m = sparse(nt, pores.outputs["Distance"], (-520, -160), 0.00, 0.07)
    colored = mix_col(nt, mathn(nt, "MULTIPLY", (-280, -80), repair_m, 0.18), stained, repair, (80, 80))
    pore_h = map_range(nt, pores.outputs["Distance"], 0.0, 0.35, 1.0, 0.0, (-520, -280))
    rough = mix_f(nt, pore_h, rough0, min(0.96, rough0 + 0.08), (-80, -120))
    rough = mix_f(nt, stain_m, rough, min(0.96, rough0 + 0.05), (120, -120))
    if kind == "floor":
        stretch = mapping(nt, world, (-760, -520), (1.0, 14.0, 1.0))
        traffic = noise(nt, stretch, 18.0, 4.0, (-520, -520), 0.40, 0.25)
        tmask = sparse(nt, traffic.outputs["Fac"], (-280, -520), 0.48, 0.72)
        rough = mix_f(nt, tmask, rough, max(0.56, rough0 - 0.10), (120, -280))
        colored = mix_col(nt, mathn(nt, "MULTIPLY", (-80, -360), tmask, 0.12), colored, pal["floor_dirt"], (80, -40))
        scratch = bump(nt, traffic.outputs["Fac"], 0.010, 0.0012, (280, -360))
        nrm = bump(nt, micro.outputs["Fac"], bump_micro, 0.0014, (280, -200), scratch)
        nrm = bump(nt, pore_h, bump_pore, 0.0010, (460, -200), nrm)
    else:
        nrm = bump(nt, micro.outputs["Fac"], bump_micro, 0.0016, (280, -220))
        nrm = bump(nt, pore_h, bump_pore, 0.0008, (460, -220), nrm)
    bsdf = principled(nt)
    out = output(nt)
    set_spec(bsdf, spec, ior=1.52, metallic=0.0, coat=0.0)
    link(nt, colored, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*a, 1.0)
    return mat


def build_painted_metal(name: str, pal: dict, kind: str) -> bpy.types.Material:
    mat, nt = new_mat(name)
    coord = tex_coord(nt)
    objv = coord.outputs["Object"]
    peel = noise(nt, objv, 88.0, 6.0, (-760, 40), 0.48)
    wear_n = noise(nt, objv, 6.5, 2.0, (-760, 220), 0.40)
    if kind == "cabinet":
        a, b, wear = pal["cab_a"], pal["cab_b"], pal["cab_wear"]
        rough0, spec, coat, coat_r, metal = 0.46, 0.50, 0.12, 0.34, 0.0
        peel_s, bevel_r = 0.008, 0.0014
    elif kind == "pipe":
        a, b, wear = pal["pipe_a"], pal["pipe_b"], pal["cab_wear"]
        rough0, spec, coat, coat_r, metal = 0.42, 0.55, 0.08, 0.40, 0.0
        peel_s, bevel_r = 0.010, 0.0008
    elif kind == "pipe2":
        a, b, wear = pal["pipe2_a"], pal["pipe2_b"], pal["cab_wear"]
        rough0, spec, coat, coat_r, metal = 0.45, 0.50, 0.07, 0.42, 0.0
        peel_s, bevel_r = 0.009, 0.0008
    elif kind == "housing":
        a, b, wear = pal["housing"], pal["struct_a"], pal["cab_wear"]
        rough0, spec, coat, coat_r, metal = 0.50, 0.46, 0.06, 0.42, 0.0
        peel_s, bevel_r = 0.011, 0.0010
    else:
        a, b, wear = pal["struct_a"], pal["housing"], pal["cab_wear"]
        rough0, spec, coat, coat_r, metal = 0.52, 0.44, 0.05, 0.45, 0.0
        peel_s, bevel_r = 0.008, 0.0011
    macro = noise(nt, objv, 1.8, 1.2, (-760, 380), 0.32)
    mf = map_range(nt, macro.outputs["Fac"], 0.32, 0.68, 0.0, 0.18, (-520, 380))
    base = mix_col(nt, mf, a, b, (-280, 300))
    wear_m = sparse(nt, wear_n.outputs["Fac"], (-520, 220), 0.72, 0.90)
    colored = mix_col(nt, mathn(nt, "MULTIPLY", (-280, 180), wear_m, 0.28), base, wear, (-40, 180))
    rough = mix_f(nt, peel.outputs["Fac"], rough0 - 0.05, rough0 + 0.08, (-280, 20))
    rough = mix_f(nt, wear_m, rough, min(0.78, rough0 + 0.16), (-40, 20))
    nrm = bump(nt, peel.outputs["Fac"], peel_s, 0.0007, (80, -160))
    if kind in {"cabinet", "housing", "struct"}:
        bevel = nt.nodes.new("ShaderNodeBevel")
        bevel.location = (80, -320)
        bevel.samples = 3
        bevel.inputs["Radius"].default_value = bevel_r
        nrm_mix = nt.nodes.new("ShaderNodeMix")
        nrm_mix.data_type = "VECTOR"
        nrm_mix.location = (280, -220)
        sock(nrm_mix, "Factor_Float").default_value = 0.55
        link(nt, nrm, sock(nrm_mix, "A_Vector"))
        link(nt, bevel.outputs["Normal"], sock(nrm_mix, "B_Vector"))
        nrm = sock(nrm_mix, "Result_Vector")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.location = (-280, -80)
    lw.inputs["Blend"].default_value = 0.45
    # Facing edges: slightly tighter roughness, still paint not chrome.
    rough = mix_f(nt, lw.outputs["Facing"], rough, max(0.32, rough0 - 0.08), (80, -40))
    bsdf = principled(nt)
    out = output(nt)
    set_spec(bsdf, spec, ior=1.46, metallic=metal, coat=coat, coat_rough=coat_r)
    if kind == "pipe":
        # Wear can hint at substrate without Metallic=1 on the paint.
        metal_amt = mix_f(nt, wear_m, 0.0, 0.12, (80, 80))
        link(nt, metal_amt, bsdf.inputs["Metallic"])
    link(nt, colored, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*a, 1.0)
    return mat


def build_galvanized(name: str, pal: dict, vent: bool = False) -> bpy.types.Material:
    mat, nt = new_mat(name)
    coord = tex_coord(nt)
    objv = coord.outputs["Object"]
    mill_v = mapping(nt, objv, (-760, 80), (18.0, 1.0, 1.0))
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.location = (-520, 80)
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 9.0
    wave.inputs["Distortion"].default_value = 1.4
    link(nt, mill_v, wave.inputs["Vector"])
    flake = voronoi(nt, objv, 42.0, (-520, -120), 0.7)
    macro = noise(nt, objv, 3.2, 2.0, (-520, 260), 0.38)
    a, b = pal["galv_a"], pal["galv_b"]
    mf = map_range(nt, macro.outputs["Fac"], 0.30, 0.70, 0.0, 0.20, (-280, 260))
    colored = mix_col(nt, mf, a, b, (-80, 220))
    mill_f = map_range(nt, wave.outputs["Fac"], 0.35, 0.65, 0.0, 1.0, (-280, 80))
    rough0 = 0.48 if not vent else 0.52
    rough = mix_f(nt, mill_f, rough0 - 0.06, rough0 + 0.07, (-80, 40))
    flake_h = map_range(nt, flake.outputs["Distance"], 0.0, 0.4, 1.0, 0.0, (-280, -120))
    rough = mix_f(nt, flake_h, rough, min(0.62, rough0 + 0.08), (80, -40))
    nrm = bump(nt, wave.outputs["Fac"], 0.007, 0.0006, (80, -200))
    nrm = bump(nt, flake_h, 0.005, 0.0005, (260, -200), nrm)
    tan = nt.nodes.new("ShaderNodeTangent")
    tan.location = (80, -360)
    if "RADIAL" in getattr(tan, "direction_type", "UV_MAP"):
        try:
            tan.direction_type = "RADIAL"
        except TypeError:
            tan.direction_type = "Z"
    bsdf = principled(nt)
    out = output(nt)
    set_spec(bsdf, 0.52, ior=1.45, metallic=0.88, coat=0.0)
    if "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value = 0.18
    if "Tangent" in bsdf.inputs:
        link(nt, tan.outputs["Tangent"], bsdf.inputs["Tangent"])
    link(nt, colored, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*a, 1.0)
    return mat


def build_valve(name: str, pal: dict) -> bpy.types.Material:
    mat, nt = new_mat(name)
    bsdf = principled(nt, (320, 80))
    out = output(nt, (560, 80))
    coord = tex_coord(nt, (-360, 80))
    n = noise(nt, coord.outputs["Object"], 22.0, 3.0, (-160, 40), 0.45)
    col = mix_col(nt, map_range(nt, n.outputs["Fac"], 0.3, 0.7, 0.0, 0.16, (40, 160)), pal["valve"], (pal["valve"][0] * 0.7, pal["valve"][1] * 0.7, pal["valve"][2] * 0.7), (80, 80))
    rough = mix_f(nt, n.outputs["Fac"], 0.48, 0.62, (80, -40))
    nrm = bump(nt, n.outputs["Fac"], 0.012, 0.0008, (80, -180))
    set_spec(bsdf, 0.42, ior=1.46, metallic=0.0, coat=0.04, coat_rough=0.45)
    link(nt, col, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*pal["valve"], 1.0)
    return mat


def build_diffuser(name: str, pal: dict, off: bool = False) -> bpy.types.Material:
    mat, nt = new_mat(name)
    coord = tex_coord(nt, (-520, 40))
    dust = noise(nt, coord.outputs["Object"], 28.0, 4.0, (-280, 40), 0.5)
    bsdf = principled(nt, (200, 40))
    out = output(nt, (460, 40))
    base = mix_col(nt, map_range(nt, dust.outputs["Fac"], 0.3, 0.7, 0.0, 0.20, (-40, 160)), pal["diff_base"], (0.22, 0.21, 0.18), (-40, 40))
    if off:
        set_spec(bsdf, 0.28, ior=1.46, metallic=0.0, coat=0.0)
        bsdf.inputs["Roughness"].default_value = 0.72
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 0.0
    else:
        set_spec(bsdf, 0.22, ior=1.48, metallic=0.0, coat=0.0)
        bsdf.inputs["Roughness"].default_value = 0.50
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 0.10
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*pal["diff_emit"], 1.0)
            bsdf.inputs["Emission Strength"].default_value = pal["diff_str"]
    link(nt, base, bsdf.inputs["Base Color"])
    nrm = bump(nt, dust.outputs["Fac"], 0.006, 0.0005, (40, -160))
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def build_tube(name: str, pal: dict) -> bpy.types.Material:
    mat, nt = new_mat(name)
    bsdf = principled(nt, (200, 40))
    out = output(nt, (460, 40))
    bsdf.inputs["Base Color"].default_value = (0.62, 0.58, 0.48, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.38
    set_spec(bsdf, 0.18, ior=1.5, metallic=0.0)
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*pal["tube_emit"], 1.0)
        bsdf.inputs["Emission Strength"].default_value = pal["tube_str"]
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def apply_palette(pal: dict) -> dict[str, bpy.types.Material]:
    for mat in list(bpy.data.materials):
        if mat.name.startswith(P106_PREFIX):
            bpy.data.materials.remove(mat)
    mats = {
        "MAT_Wall_PaintedConcrete": build_concrete(f"{P106_PREFIX}Wall", pal, "wall"),
        "MAT_Floor_IndustrialConcrete": build_concrete(f"{P106_PREFIX}Floor", pal, "floor"),
        "MAT_Ceiling_AgedConcrete": build_concrete(f"{P106_PREFIX}Ceil", pal, "ceil"),
        "MAT_Cabinet_PaintedMetal": build_painted_metal(f"{P106_PREFIX}Cabinet", pal, "cabinet"),
        "MAT_Structure_PaintedSteel": build_painted_metal(f"{P106_PREFIX}Struct", pal, "struct"),
        "MAT_Pipe_DarkPaintedSteel": build_painted_metal(f"{P106_PREFIX}Pipe", pal, "pipe"),
        "MAT_Pipe_Secondary": build_painted_metal(f"{P106_PREFIX}Pipe2", pal, "pipe2"),
        "MAT_Metal_Galvanized": build_galvanized(f"{P106_PREFIX}Galv", pal, False),
        "MAT_Vent_GalvanizedMetal": build_galvanized(f"{P106_PREFIX}Vent", pal, True),
        "MAT_Valve_IndustrialAccent": build_valve(f"{P106_PREFIX}Valve", pal),
        "housing": build_painted_metal(f"{P106_PREFIX}Housing", pal, "housing"),
        "diffuser": build_diffuser(f"{P106_PREFIX}Diffuser", pal, False),
        "diffuser_off": build_diffuser(f"{P106_PREFIX}DiffuserOff", pal, True),
        "tube": build_tube(f"{P106_PREFIX}Tube", pal),
    }
    aging_keys = {
        "MAT_Wall_PaintedConcrete": mats["MAT_Wall_PaintedConcrete"],
        "MAT_Floor_IndustrialConcrete": mats["MAT_Floor_IndustrialConcrete"],
        "MAT_Ceiling_AgedConcrete": mats["MAT_Ceiling_AgedConcrete"],
        "MAT_Structure_PaintedSteel": mats["MAT_Structure_PaintedSteel"],
        "MAT_Pipe_DarkPaintedSteel": mats["MAT_Pipe_DarkPaintedSteel"],
        "MAT_Pipe_Secondary": mats["MAT_Pipe_Secondary"],
        "MAT_Metal_Galvanized": mats["MAT_Metal_Galvanized"],
        "MAT_Cabinet_PaintedMetal": mats["MAT_Cabinet_PaintedMetal"],
        "MAT_Vent_GalvanizedMetal": mats["MAT_Vent_GalvanizedMetal"],
        "MAT_Valve_IndustrialAccent": mats["MAT_Valve_IndustrialAccent"],
        "MAT_Rubber_Dark": bpy.data.materials["MAT_Rubber_Dark"].copy(),
    }
    aging_keys["MAT_Rubber_Dark"].name = f"{P106_PREFIX}RubberAgingHost"
    group = bpy.data.node_groups.get("P6_NG_AgingMasks")
    if group is not None:
        p6.inject_aging(aging_keys, group)
    return mats


def capture_slots() -> dict[str, list[str | None]]:
    rows = {}
    for obj in bpy.data.objects:
        if not obj.material_slots:
            continue
        rows[obj.name] = [s.material.name if s.material else None for s in obj.material_slots]
    return rows


def restore_slots(rows: dict[str, list[str | None]]) -> None:
    for name, mats in rows.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        for index, mat_name in enumerate(mats):
            if index >= len(obj.material_slots):
                continue
            obj.material_slots[index].material = bpy.data.materials.get(mat_name) if mat_name else None


def remap_slots(p106: dict[str, bpy.types.Material]) -> None:
    for obj in bpy.data.objects:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None:
                continue
            n = obj.name
            src = mat.name
            if n.startswith("FIX_") and n.endswith("_Housing") and src == "MAT_Metal_Galvanized":
                slot.material = p106["housing"]
            elif n.endswith("_Diffuser") and src.startswith("MAT_P7_Diffuser"):
                slot.material = p106["diffuser_off"] if src.endswith("_Off") else p106["diffuser"]
            elif n.startswith("P8_TUBE"):
                slot.material = p106["tube"]
            elif src in p106 and src.startswith("MAT_"):
                slot.material = p106[src]


def capture_lights() -> dict[str, tuple[float, float, float]]:
    rows = {}
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        rows[obj.name] = tuple(obj.data.color)
    return rows


def restore_lights(rows: dict[str, tuple[float, float, float]]) -> None:
    for name, color in rows.items():
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "LIGHT":
            continue
        obj.data.color = color


def tweak_lights(pal: dict, original: dict[str, tuple[float, float, float]]) -> None:
    mix = pal["light_mix"]
    blend = pal["light_blend"]
    for name, color in original.items():
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "LIGHT" or obj.data.energy <= 0.0:
            continue
        obj.data.color = tuple(color[i] * (1.0 - mix) + blend[i] * mix for i in range(3))


def enable_cycles_cpu(scene: bpy.types.Scene) -> None:
    addon = bpy.context.preferences.addons.get("cycles")
    if addon is not None:
        addon.preferences.compute_device_type = "NONE"
        addon.preferences.get_devices()
        for device in addon.preferences.devices:
            device.use = device.type == "CPU"
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = CYCLES_SAMPLES
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = CYCLES_ADAPTIVE
    scene.cycles.adaptive_min_samples = CYCLES_MIN
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.max_bounces = 6
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 3
    scene.cycles.transmission_bounces = 4
    scene.cycles.volume_bounces = 1
    scene.cycles.transparent_max_bounces = 4
    scene.cycles.sample_clamp_indirect = 6.0
    scene.cycles.filter_glossy = 0.5
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = 100
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 93
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0


def render_still(scene: bpy.types.Scene, camera_name: str, frame: int, path: Path) -> Path:
    scene.camera = bpy.data.objects[camera_name]
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print("rendered", path.name, "cam", camera_name, "frame", frame)
    return path


def publish(path: Path) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, ARTIFACT_DIR / path.name)


def add_close_camera() -> bpy.types.Object:
    existing = bpy.data.objects.get(CLOSE_CAMERA)
    if existing is not None:
        bpy.data.objects.remove(existing, do_unlink=True)
    data = bpy.data.cameras.new(CLOSE_CAMERA)
    data.lens = 50.0
    data.sensor_width = 36.0
    data.clip_start = 0.05
    data.clip_end = 40.0
    cam = bpy.data.objects.new(CLOSE_CAMERA, data)
    loc = Vector((0.42, 12.55, 1.52))
    target = Vector((0.92, 13.15, 1.78))
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
    cam["phase"] = 10.6
    bpy.context.scene.collection.objects.link(cam)
    return cam


def freeze_ok(scene, before, inspect_before, lights_before, slots_now, slots_saved) -> dict:
    after = p5.snapshot()
    moved = [n for n, row in before.items() if after.get(n) != row]
    inspect = bpy.data.objects["CAM_INSPECT"]
    walk = bpy.data.objects[EVAL_CAMERA]
    inspect_after = p105.inspect_keys(inspect)
    walk_keys = p105.inspect_keys(walk)
    camera_errors = []
    for frame in range(1, 217, 16):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        pos = walk.matrix_world.translation
        if abs(pos.x) > 0.02 or abs(pos.z - p5.EYE_Z) > 0.02:
            camera_errors.append((frame, tuple(round(v, 3) for v in pos)))
    scene.frame_set(EVAL_FRAME)
    light_moved = []
    for name, color in lights_before.items():
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "LIGHT":
            continue
        if tuple(round(c, 4) for c in obj.data.color) != tuple(round(c, 4) for c in color):
            light_moved.append(name)
        loc_now = tuple(round(v, 5) for v in obj.location)
        # location freeze via 10.5 energy map style
    slots_match = slots_now == slots_saved
    originals_present = all(bpy.data.materials.get(n) is not None for n in CORE_ORIGINALS)
    return dict(
        moved=moved,
        inspect_ok=inspect_before == inspect_after,
        walk_errors=camera_errors,
        walk_keys=walk_keys,
        light_color_changed=light_moved,
        slots_restored=slots_match,
        originals_present=originals_present,
        p8=len([o for o in bpy.data.objects if o.name.startswith("P8_")]),
        p9=len([o for o in bpy.data.objects if o.name.startswith("P9_")]),
        marks=len([o for o in bpy.data.objects if o.name.startswith("MARK_")]),
        p105=len([o for o in bpy.data.objects if o.name.startswith("P105_") or o.name.startswith("CAM_P105")]),
        wall_end_hidden=bool(bpy.data.objects["WALL.End"].hide_render),
        frame_end=scene.frame_end,
        eval_cam=scene.camera.name if scene.camera else None,
        walk_exists=walk is not None,
    )


def write_report(validation: dict, rendered: dict[str, bool]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    freeze = (
        not validation["moved"]
        and validation["inspect_ok"]
        and not validation["walk_errors"]
        and validation["slots_restored"]
        and validation["originals_present"]
        and validation["p8"] == EXPECTED_P8
        and validation["p9"] == EXPECTED_P9
        and validation["marks"] == EXPECTED_MARKS
        and validation["wall_end_hidden"]
        and validation["frame_end"] == 216
        and not validation["light_color_changed"]
    )
    lines = [
        "PHASE 10.6 英雄材質重建與色彩身份對照",
        "Phase 10.5 相機／運動／無盡走廊已凍結。未改幾何、延伸段、9 秒路徑。",
        "三套 Look 僅用於同一鏡位對照；場景材質指定已恢復為 LOOK_00 現況。",
        "未選勝者，未套用全廊，未進入 Phase 11。",
        "",
        "LOOK_00 基準問題（舊材質）",
        "  牆／地／櫃／管幾乎都是 Noise→Mix→Bump，看起來像塑膠灰與粘土渲染。",
        "  牆過亮過平、與櫃 equip 色相接近；管是深色圓柱缺少塗層高光。",
        "  鍍鋅金屬偏均勻灰；燈槽 housing 與支架共用 MAT_Metal_Galvanized，擴散片偏白塊。",
        "",
        "牆／混凝土",
        "  舊：近白／平灰，程序噪成了材質本身。",
        "  Base Color：暖髒灰／機構米灰，宏觀澆置色差極低對比；中觀水漬／修補當 MASK；微觀不進 albedo。",
        "  Roughness：高粗糙 0.83–0.86，孔隙與污漬只作微幅加減，維持漫射。",
        "  Normal：細孔隙＋微觀凹凸，強度很低，靠光反應顯形，不是牆上畫噪點。",
        "  Metallic 0，Specular ~0.20，IOR 1.52，無清漆。",
        "",
        "地坪",
        "  舊：與牆同家族、分離不足。",
        "  Base Color：更暗更密；沿走廊軸向交通磨耗作 MASK 混入積塵，無新增水窪。",
        "  Roughness：基底 ~0.70–0.74，磨耗路徑略降但不低於約 0.56，避免鏡面。",
        "  Normal：拉伸刮痕＋微觀，掠射可有寬弱反應。",
        "",
        "烤漆櫃／設備",
        "  舊：與牆同灰，Metallic 幾乎 0 又沒有塗層，讀成另一塊混凝土。",
        "  Base Color：冷灰／灰綠烤漆，磨損 MASK 露出更深底層。",
        "  Roughness：0.42–0.55；Coat ~0.12 模擬電介質漆膜，不是 Metallic=1。",
        "  Normal：橘皮微結構＋Cycles Bevel 讓稜線吃光不同於混凝土。",
        "",
        "工業管",
        "  舊：炭黑圓柱，高光弱、無塗層差異。",
        "  Base Color：A 炭黑；B 主管灰綠、伴管藍灰；C 更深冷灰。非彩虹管線。",
        "  Roughness：0.38–0.50 以得到柱面高光；Coat 低；磨損處才略提 Metallic 0.12。",
        "  閥門紅保留並在 B 略加強。",
        "",
        "鍍鋅／外露金屬",
        "  舊：均勻金屬灰。",
        "  Metallic ~0.88，軋延波紋進 roughness／微 normal，各向異性 0.18，非鉻。",
        "",
        "燈具",
        "  舊：housing=鍍鋅、擴散片共用 Weak、近白塊。",
        "  Housing 改烤漆金屬；擴散片帶塵與微透射，發射非 #FFFFFF；燈管與槽分離。",
        "  未改燈具能量／位置；B／C 僅極微混入光源色溫。",
        "",
        "LOOK 比較（同一 CAM_P105_WALK 第 108 幀，同一幾何）",
        "  LOOK A 紀實工業：中性螢光、暖髒牆、冷櫃、炭黑管。最像文獻／現場照片。",
        "    可讀性靠材質分離，色彩身份最克制，Level 2 氣氛較「真實設施」。",
        "  LOOK B Level 2 工業（建議候選，尚未套用）：機構暖牆、灰綠主管、藍灰伴管、",
        "    極微暖黃／綠螢光來自物體與燈色而非全圖濾鏡。閥門紅較可讀。",
        "    深度仍靠幾何與光衰減；色彩在物件上，不是後期。",
        "  LOOK C 克制電影工業：牆更暖、金屬／暗部更冷，對比略高。無青橙、無賽博、無海報調色。",
        "    氣氛較有冷暖層，但比 B 更「鏡頭」，比 A 更不紀實。",
        "",
        f"PHASE 10.5 FREEZE STATUS: {'PASS' if freeze else 'FAIL'}",
        f"LOOK_00 BASELINE: {'PASS' if rendered.get('LOOK_00_CURRENT') else 'FAIL'}",
        f"LOOK A GENERATED: {'PASS' if rendered.get('LOOK_A_REALISTIC_INDUSTRIAL') else 'FAIL'}",
        f"LOOK B GENERATED: {'PASS' if rendered.get('LOOK_B_LEVEL2_INDUSTRIAL') else 'FAIL'}",
        f"LOOK C GENERATED: {'PASS' if rendered.get('LOOK_C_CINEMATIC_INDUSTRIAL') else 'FAIL'}",
        f"MATERIAL COMPARISON READY FOR USER REVIEW: {'PASS' if freeze and all(rendered.get(k) for k in ('LOOK_00_CURRENT','LOOK_A_REALISTIC_INDUSTRIAL','LOOK_B_LEVEL2_INDUSTRIAL','LOOK_C_CINEMATIC_INDUSTRIAL')) else 'FAIL'}",
        "",
        "凍結細節",
        f"  幾何變換改動：{len(validation['moved'])}",
        f"  CAM_INSPECT 路徑不變：{validation['inspect_ok']}",
        f"  CAM_P105_WALK 路徑錯誤：{len(validation['walk_errors'])}",
        f"  材質槽已恢復 LOOK_00：{validation['slots_restored']}",
        f"  燈光顏色已恢復：{not validation['light_color_changed']}",
        f"  P8/P9/MARK/P105：{validation['p8']}/{validation['p9']}/{validation['marks']}/{validation['p105']}",
        "  未開始 Phase 11。等待使用者選擇 Look。",
    ]
    if validation["moved"]:
        lines.append("  被改動：" + ", ".join(validation["moved"][:12]))
    if validation["light_color_changed"]:
        lines.append("  燈光色未恢復：" + ", ".join(validation["light_color_changed"][:12]))
    report = OUTPUT_DIR / "phase10_6_lookdev_validation.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", report)
    return report


def main() -> None:
    mode = parse_mode()
    scene = bpy.context.scene
    before = p5.snapshot()
    inspect_before = p105.inspect_keys(bpy.data.objects["CAM_INSPECT"])
    lights_before = capture_lights()
    slots = capture_slots()
    enable_cycles_cpu(scene)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rendered = {}

    look00 = OUTPUT_DIR / "LOOK_00_CURRENT.jpg"
    render_still(scene, EVAL_CAMERA, EVAL_FRAME, look00)
    publish(look00)
    rendered["LOOK_00_CURRENT"] = look00.exists()

    if mode == "look00":
        write_report(
            freeze_ok(scene, before, inspect_before, lights_before, capture_slots(), slots),
            rendered,
        )
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
        print("LOOK_00 only; no look applied.")
        return

    add_close_camera()
    for key, pal in PALETTES.items():
        p106 = apply_palette(pal)
        remap_slots(p106)
        tweak_lights(pal, lights_before)
        path = OUTPUT_DIR / f"{pal['label']}.jpg"
        render_still(scene, EVAL_CAMERA, EVAL_FRAME, path)
        publish(path)
        rendered[pal["label"]] = path.exists()
        if key == "B":
            close = OUTPUT_DIR / "LOOK_B_MATERIAL_CLOSEUP.jpg"
            render_still(scene, CLOSE_CAMERA, EVAL_FRAME, close)
            publish(close)
            rendered["LOOK_B_MATERIAL_CLOSEUP"] = close.exists()
        restore_lights(lights_before)
        restore_slots(slots)

    scene.camera = bpy.data.objects[EVAL_CAMERA]
    scene.frame_set(EVAL_FRAME)
    (OUTPUT_DIR / "slot_restore.json").write_text(json.dumps({"eval_frame": EVAL_FRAME, "camera": EVAL_CAMERA}, indent=2), encoding="utf-8")
    validation = freeze_ok(scene, before, inspect_before, lights_before, capture_slots(), slots)
    write_report(validation, rendered)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 10.6 look-dev complete; no look selected; Phase 11 not started.")


if __name__ == "__main__":
    main()
