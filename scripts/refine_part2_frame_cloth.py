#!/usr/bin/env python3
"""Part 2 hero-prop pass: frame glass/dust/photo, cloth, cable rubber, local lights.

Does not rebuild architecture, boxes, clutter, or cable paths.
Never writes hallway.blend. Never opens a save on part2 connection objects.
"""

from __future__ import annotations

import json
import math
import random
import shutil
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path("/workspace")
BLEND = ROOT / "part2_basement.blend"
PART1 = ROOT / "hallway.blend"
OUT = ROOT / "renders" / "part2_basement"
STILL = OUT / "stills_frame_cloth"
ARTIFACT = Path("/opt/cursor/artifacts")
CHECKPOINT = ROOT / "renders" / "checkpoints" / "part2_basement_frame_cloth.blend"
QA = OUT / "frame_cloth_qa.json"

RIG = [f"P2_CABLE_RIG_{i:02d}" for i in range(1, 7)]
RNG = random.Random(7711)


def sock(node, ident: str):
    for s in list(node.inputs) + list(node.outputs):
        if s.identifier == ident or s.name == ident:
            return s
    raise KeyError(ident)


def look_at(obj, target) -> None:
    obj.rotation_euler = (Vector(target) - Vector(obj.location)).to_track_quat("-Z", "Y").to_euler()


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


def capture_rig() -> dict:
    out = {}
    for name in RIG:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "CURVE":
            out[name] = None
            continue
        pts = []
        for sp in obj.data.splines:
            for bp in sp.bezier_points:
                pts.append([round(bp.co.x, 5), round(bp.co.y, 5), round(bp.co.z, 5), round(bp.radius, 4)])
        out[name] = {"bevel": round(obj.data.bevel_depth, 5), "points": pts}
    return out


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


# ---------------------------------------------------------------------------
# Photo — still unidentifiable, but not a blank card.
# ---------------------------------------------------------------------------

def enrich_photo() -> None:
    img = bpy.data.images.get("P2_PHOTO_BLUR")
    if img is None:
        return
    w, h = int(img.size[0]), int(img.size[1])
    n = w * h
    px = list(img.pixels)
    rng = random.Random(19)
    for i in range(n):
        x = i % w
        y = i // w
        u = x / max(w - 1, 1)
        v = y / max(h - 1, 1)
        # Soft chemical mottling, not a figure.
        m1 = 0.5 + 0.5 * math.sin((u * 7.3 + 0.2) * math.pi) * math.cos((v * 5.1 + 0.4) * math.pi)
        m2 = 0.5 + 0.5 * math.sin((u * 13.0 - v * 9.0) * math.pi * 0.7)
        vig = 1.0 - 0.38 * (((u - 0.5) * 1.7) ** 2 + ((v - 0.48) * 1.5) ** 2)
        grain = rng.uniform(-0.04, 0.04)
        base_r, base_g, base_b = 0.22, 0.18, 0.13
        tone = 0.55 + 0.28 * m1 + 0.12 * m2
        r = max(0.0, min(1.0, base_r * tone * vig + grain * 0.6))
        g = max(0.0, min(1.0, base_g * tone * vig + grain * 0.45))
        b = max(0.0, min(1.0, base_b * tone * vig + grain * 0.25))
        o = i * 4
        # Mix with existing packed pixels so we do not replace identity with a new picture.
        pr, pg, pb = px[o], px[o + 1], px[o + 2]
        px[o] = pr * 0.35 + r * 0.65
        px[o + 1] = pg * 0.35 + g * 0.65
        px[o + 2] = pb * 0.35 + b * 0.65
        px[o + 3] = 1.0
    img.pixels = px
    mat = bpy.data.materials.get("MAT_P2_Photo")
    if mat:
        bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Roughness"].default_value = 0.92
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.12


# ---------------------------------------------------------------------------
# Glass
# ---------------------------------------------------------------------------

def rebuild_glass() -> None:
    mat = bpy.data.materials.get("MAT_P2_Glass") or bpy.data.materials.new("MAT_P2_Glass")
    mat.use_nodes = True
    set_blend(mat, "BLEND")
    if hasattr(mat, "use_screen_refraction"):
        mat.use_screen_refraction = True
    if hasattr(mat, "refraction_depth"):
        try:
            mat.refraction_depth = 0.004
        except TypeError:
            pass
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (520, 0)
    out.location = (780, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (0.78, 0.82, 0.84, 1.0)
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.92
    bsdf.inputs["Alpha"].default_value = 0.18
    bsdf.inputs["IOR"].default_value = 1.52
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 1.0
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.22
        bsdf.inputs["Coat Roughness"].default_value = 0.06
    coord = nt.nodes.new("ShaderNodeTexCoord")
    # Hairline scratches
    map_s = nt.nodes.new("ShaderNodeMapping")
    map_s.inputs["Scale"].default_value = (42.0, 0.35, 8.0)
    map_s.inputs["Rotation"].default_value = (0.0, 0.0, 0.41)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.inputs["Scale"].default_value = 18.0
    wave.inputs["Distortion"].default_value = 9.0
    wave.inputs["Detail"].default_value = 5.0
    scratch = nt.nodes.new("ShaderNodeValToRGB")
    scratch.color_ramp.elements[0].position = 0.46
    scratch.color_ramp.elements[0].color = (0.04, 0.04, 0.04, 1)
    scratch.color_ramp.elements[1].position = 0.52
    scratch.color_ramp.elements[1].color = (0.22, 0.22, 0.22, 1)
    # Fingerprint / smudge islands
    n_fp = nt.nodes.new("ShaderNodeTexNoise")
    n_fp.inputs["Scale"].default_value = 9.5
    n_fp.inputs["Detail"].default_value = 8.0
    n_fp.inputs["Roughness"].default_value = 0.55
    fp = nt.nodes.new("ShaderNodeValToRGB")
    fp.color_ramp.elements[0].position = 0.58
    fp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1)
    fp.color_ramp.elements[1].position = 0.72
    fp.color_ramp.elements[1].color = (0.55, 0.55, 0.55, 1)
    # Irregular dirt film on glass (separate from the dust mesh)
    n_dirt = nt.nodes.new("ShaderNodeTexNoise")
    n_dirt.inputs["Scale"].default_value = 6.2
    n_dirt.inputs["Detail"].default_value = 10.0
    dirt = nt.nodes.new("ShaderNodeValToRGB")
    dirt.color_ramp.elements[0].position = 0.38
    dirt.color_ramp.elements[0].color = (0.12, 0.12, 0.12, 1)
    dirt.color_ramp.elements[1].position = 0.70
    dirt.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1)
    add1 = nt.nodes.new("ShaderNodeMath")
    add1.operation = "ADD"
    add2 = nt.nodes.new("ShaderNodeMath")
    add2.operation = "ADD"
    rough = nt.nodes.new("ShaderNodeMath")
    rough.operation = "ADD"
    rough.inputs[1].default_value = 0.045
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.0008
    nt.links.new(coord.outputs["Object"], map_s.inputs["Vector"])
    nt.links.new(map_s.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n_fp.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n_dirt.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], scratch.inputs["Fac"])
    nt.links.new(n_fp.outputs["Fac"], fp.inputs["Fac"])
    nt.links.new(n_dirt.outputs["Fac"], dirt.inputs["Fac"])
    nt.links.new(scratch.outputs["Color"], add1.inputs[0])
    nt.links.new(fp.outputs["Color"], add1.inputs[1])
    nt.links.new(add1.outputs["Value"], add2.inputs[0])
    nt.links.new(dirt.outputs["Color"], add2.inputs[1])
    nt.links.new(add2.outputs["Value"], rough.inputs[0])
    nt.links.new(rough.outputs["Value"], bsdf.inputs["Roughness"])
    nt.links.new(add2.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    glass = bpy.data.objects.get("P2_FRAME_GLASS")
    if glass:
        glass.data.materials.clear()
        glass.data.materials.append(mat)


# ---------------------------------------------------------------------------
# Dust — heavy at corners/edges, thin in the center so the photo reads faintly.
# ---------------------------------------------------------------------------

def rebuild_dust() -> None:
    mat = bpy.data.materials.get("MAT_P2_Dust") or bpy.data.materials.new("MAT_P2_Dust")
    mat.use_nodes = True
    set_blend(mat, "HASHED")
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.97
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.02
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    # Distance from pane center in generated 0-1 space.
    subx = nt.nodes.new("ShaderNodeMath")
    subx.operation = "SUBTRACT"
    subx.inputs[1].default_value = 0.5
    subz = nt.nodes.new("ShaderNodeMath")
    subz.operation = "SUBTRACT"
    subz.inputs[1].default_value = 0.5
    absx = nt.nodes.new("ShaderNodeMath")
    absx.operation = "ABSOLUTE"
    absz = nt.nodes.new("ShaderNodeMath")
    absz.operation = "ABSOLUTE"
    # Lighter weight on Z so it is an edge/corner vignette, not one blob.
    powx = nt.nodes.new("ShaderNodeMath")
    powx.operation = "POWER"
    powx.inputs[1].default_value = 2.4
    powz = nt.nodes.new("ShaderNodeMath")
    powz.operation = "POWER"
    powz.inputs[1].default_value = 2.4
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.02
    cr.color_ramp.elements[0].color = (0.30, 0.27, 0.22, 0.10)
    mid = cr.color_ramp.elements.new(0.28)
    mid.color = (0.33, 0.30, 0.24, 0.32)
    cr.color_ramp.elements[1].position = 0.62
    cr.color_ramp.elements[1].color = (0.38, 0.34, 0.27, 0.92)
    n_clump = nt.nodes.new("ShaderNodeTexNoise")
    n_clump.inputs["Scale"].default_value = 14.0
    n_clump.inputs["Detail"].default_value = 11.0
    n_speck = nt.nodes.new("ShaderNodeTexNoise")
    n_speck.inputs["Scale"].default_value = 90.0
    n_speck.inputs["Detail"].default_value = 6.0
    clump = nt.nodes.new("ShaderNodeMapRange")
    clump.inputs["To Min"].default_value = 0.55
    clump.inputs["To Max"].default_value = 1.15
    speck = nt.nodes.new("ShaderNodeMapRange")
    speck.inputs["To Min"].default_value = 0.75
    speck.inputs["To Max"].default_value = 1.05
    mul1 = nt.nodes.new("ShaderNodeMath")
    mul1.operation = "MULTIPLY"
    mul2 = nt.nodes.new("ShaderNodeMath")
    mul2.operation = "MULTIPLY"
    clamp = nt.nodes.new("ShaderNodeClamp")
    clamp.inputs["Min"].default_value = 0.04
    clamp.inputs["Max"].default_value = 0.95
    colmix = nt.nodes.new("ShaderNodeMix")
    colmix.data_type = "RGBA"
    sock(colmix, "A_Color").default_value = (0.34, 0.31, 0.25, 1)
    sock(colmix, "B_Color").default_value = (0.22, 0.20, 0.16, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.0012
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["X"], subx.inputs[0])
    nt.links.new(sep.outputs["Z"], subz.inputs[0])
    nt.links.new(subx.outputs["Value"], absx.inputs[0])
    nt.links.new(subz.outputs["Value"], absz.inputs[0])
    nt.links.new(absx.outputs["Value"], powx.inputs[0])
    nt.links.new(absz.outputs["Value"], powz.inputs[0])
    nt.links.new(powx.outputs["Value"], add.inputs[0])
    nt.links.new(powz.outputs["Value"], add.inputs[1])
    nt.links.new(add.outputs["Value"], cr.inputs["Fac"])
    nt.links.new(coord.outputs["Object"], n_clump.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n_speck.inputs["Vector"])
    nt.links.new(n_clump.outputs["Fac"], clump.inputs["Value"])
    nt.links.new(n_speck.outputs["Fac"], speck.inputs["Value"])
    nt.links.new(cr.outputs["Alpha"], mul1.inputs[0])
    nt.links.new(clump.outputs["Result"], mul1.inputs[1])
    nt.links.new(mul1.outputs["Value"], mul2.inputs[0])
    nt.links.new(speck.outputs["Result"], mul2.inputs[1])
    nt.links.new(mul2.outputs["Value"], clamp.inputs["Value"])
    nt.links.new(clamp.outputs["Result"], bsdf.inputs["Alpha"])
    nt.links.new(n_speck.outputs["Fac"], sock(colmix, "Factor_Float"))
    nt.links.new(sock(colmix, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(n_clump.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    dust = bpy.data.objects.get("P2_FRAME_DUST")
    if dust is None or dust.type != "MESH":
        return
    dust.data.materials.clear()
    dust.data.materials.append(mat)
    # Thickness: keep the pane, puff corners, thin the center. Local Y is toward the sitter.
    rng = random.Random(77)
    for v in dust.data.vertices:
        nx = abs(v.co.x) / 0.084
        nz = abs(v.co.z) / 0.109
        corner = min(1.0, (nx ** 2 + nz ** 2) * 0.72)
        v.co.y = -0.0006 - corner * 0.0024 - rng.uniform(0.0, 0.00025)
    dust.location.y = -0.0132


# ---------------------------------------------------------------------------
# Cloth — keep mesh, replace clay look with worn fabric.
# ---------------------------------------------------------------------------

def rebuild_cloth() -> None:
    mat = bpy.data.materials.get("MAT_P2_Cloth") or bpy.data.materials.new("MAT_P2_Cloth")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.04
    if "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = 0.55
        if "Sheen Roughness" in bsdf.inputs:
            bsdf.inputs["Sheen Roughness"].default_value = 0.72
        if "Sheen Tint" in bsdf.inputs:
            try:
                bsdf.inputs["Sheen Tint"].default_value = (0.22, 0.20, 0.16, 1)
            except TypeError:
                pass
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.035
        if "Subsurface Radius" in bsdf.inputs:
            bsdf.inputs["Subsurface Radius"].default_value = (0.4, 0.2, 0.1)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    map_w = nt.nodes.new("ShaderNodeMapping")
    map_w.inputs["Scale"].default_value = (92.0, 92.0, 1.0)
    weave = nt.nodes.new("ShaderNodeTexWave")
    weave.wave_type = "BANDS"
    weave.bands_direction = "DIAGONAL"
    weave.inputs["Scale"].default_value = 64.0
    weave.inputs["Distortion"].default_value = 1.2
    weave.inputs["Detail"].default_value = 3.0
    weave2 = nt.nodes.new("ShaderNodeTexWave")
    weave2.wave_type = "BANDS"
    weave2.inputs["Scale"].default_value = 64.0
    weave2.inputs["Distortion"].default_value = 1.0
    map_w2 = nt.nodes.new("ShaderNodeMapping")
    map_w2.inputs["Rotation"].default_value = (0.0, 0.0, 1.5708)
    map_w2.inputs["Scale"].default_value = (92.0, 92.0, 1.0)
    mulw = nt.nodes.new("ShaderNodeMath")
    mulw.operation = "MULTIPLY"
    n_stain = nt.nodes.new("ShaderNodeTexNoise")
    n_stain.inputs["Scale"].default_value = 7.5
    n_stain.inputs["Detail"].default_value = 10.0
    n_fade = nt.nodes.new("ShaderNodeTexNoise")
    n_fade.inputs["Scale"].default_value = 3.2
    n_fade.inputs["Detail"].default_value = 6.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.18
    cr.color_ramp.elements[0].color = (0.07, 0.065, 0.05, 1)
    stain = cr.color_ramp.elements.new(0.42)
    stain.color = (0.12, 0.09, 0.06, 1)
    cr.color_ramp.elements[1].position = 0.78
    cr.color_ramp.elements[1].color = (0.20, 0.17, 0.13, 1)
    mix_stain = nt.nodes.new("ShaderNodeMix")
    mix_stain.data_type = "RGBA"
    mix_stain.blend_type = "MULTIPLY"
    sock(mix_stain, "Factor_Float").default_value = 0.55
    fade = nt.nodes.new("ShaderNodeMix")
    fade.data_type = "RGBA"
    fade.blend_type = "MIX"
    sock(fade, "B_Color").default_value = (0.28, 0.24, 0.18, 1)
    sock(fade, "Factor_Float").default_value = 0.22
    rough_cr = nt.nodes.new("ShaderNodeValToRGB")
    rough_cr.color_ramp.elements[0].position = 0.25
    rough_cr.color_ramp.elements[0].color = (0.62, 0.62, 0.62, 1)
    rough_cr.color_ramp.elements[1].position = 0.80
    rough_cr.color_ramp.elements[1].color = (0.95, 0.95, 0.95, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.48
    bump.inputs["Distance"].default_value = 0.0018
    bump2 = nt.nodes.new("ShaderNodeBump")
    bump2.inputs["Strength"].default_value = 0.22
    bump2.inputs["Distance"].default_value = 0.0006
    nt.links.new(coord.outputs["Object"], map_w.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], map_w2.inputs["Vector"])
    nt.links.new(map_w.outputs["Vector"], weave.inputs["Vector"])
    nt.links.new(map_w2.outputs["Vector"], weave2.inputs["Vector"])
    nt.links.new(weave.outputs["Fac"], mulw.inputs[0])
    nt.links.new(weave2.outputs["Fac"], mulw.inputs[1])
    nt.links.new(coord.outputs["Object"], n_stain.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n_fade.inputs["Vector"])
    nt.links.new(n_stain.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], sock(mix_stain, "A_Color"))
    nt.links.new(mulw.outputs["Value"], sock(mix_stain, "B_Color"))
    sock(mix_stain, "Factor_Float").default_value = 0.28
    nt.links.new(sock(mix_stain, "Result_Color"), sock(fade, "A_Color"))
    nt.links.new(n_fade.outputs["Fac"], sock(fade, "Factor_Float"))
    sock(fade, "Factor_Float").default_value = 0.18
    nt.links.new(n_fade.outputs["Fac"], sock(fade, "Factor_Float"))
    nt.links.new(sock(fade, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(n_stain.outputs["Fac"], rough_cr.inputs["Fac"])
    nt.links.new(rough_cr.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(n_stain.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bump2.inputs["Normal"])
    nt.links.new(mulw.outputs["Value"], bump2.inputs["Height"])
    nt.links.new(bump2.outputs["Normal"], bsdf.inputs["Normal"])
    cloth = bpy.data.objects.get("P2_CLOTH")
    if cloth:
        cloth.data.materials.clear()
        cloth.data.materials.append(mat)


# ---------------------------------------------------------------------------
# Cable rubber + floor contact (non-RIG only)
# ---------------------------------------------------------------------------

def rebuild_cable() -> None:
    mat = bpy.data.materials.get("MAT_P2_Cable") or bpy.data.materials.new("MAT_P2_Cable")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.18
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.08
        bsdf.inputs["Coat Roughness"].default_value = 0.45
    coord = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 28.0
    n1.inputs["Detail"].default_value = 8.0
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 55.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (0.008, 0.008, 0.01, 1)
    cr.color_ramp.elements[1].color = (0.035, 0.035, 0.04, 1)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    sock(mix, "Factor_Float").default_value = 0.22
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    bump.inputs["Distance"].default_value = 0.002
    rough = nt.nodes.new("ShaderNodeValToRGB")
    rough.color_ramp.elements[0].position = 0.30
    rough.color_ramp.elements[0].color = (0.42, 0.42, 0.42, 1)
    rough.color_ramp.elements[1].position = 0.78
    rough.color_ramp.elements[1].color = (0.78, 0.78, 0.78, 1)
    nt.links.new(coord.outputs["Object"], n1.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    nt.links.new(n1.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], sock(mix, "A_Color"))
    nt.links.new(vor.outputs["Distance"], sock(mix, "B_Color"))
    nt.links.new(sock(mix, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(n1.outputs["Fac"], rough.inputs["Fac"])
    nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def tweak_non_rig_cables() -> None:
    rng = random.Random(2202)
    for obj in bpy.data.objects:
        if obj.type != "CURVE" or not obj.name.startswith("P2_CABLE_"):
            continue
        if obj.name in RIG:
            continue
        bevel = obj.data.bevel_depth
        for sp in obj.data.splines:
            for i, bp in enumerate(sp.bezier_points):
                # Gentle thickness variation along the curve.
                bp.radius = max(0.55, min(1.45, 0.82 + 0.28 * math.sin(i * 0.7 + rng.random()) + rng.uniform(-0.08, 0.08)))
                # Sit on the floor: keep contact without burying the bevel.
                if bp.co.z < 0.12:
                    min_z = bevel * max(bp.radius, 0.8) * 0.92 + 0.001
                    if bp.co.z < min_z:
                        bp.co.z = min_z
                    elif bp.co.z < 0.045 and bp.co.z > min_z + 0.012:
                        bp.co.z = min_z + rng.uniform(0.0, 0.004)


# ---------------------------------------------------------------------------
# Lights / cameras
# ---------------------------------------------------------------------------

def tune_lights() -> None:
    pendant = bpy.data.objects.get("LIGHT_P2_DESK_PENDANT")
    if pendant:
        pendant.data.energy = 96.0
        pendant.data.shadow_soft_size = 0.20
    kiss = bpy.data.objects.get("LIGHT_P2_FRAME_KISS")
    if kiss:
        # Weaker fill so glass can read; keep the frame visible from the sit camera.
        kiss.data.energy = 4.2
        kiss.location = (-0.06, 26.82, 1.00)
    existing = bpy.data.objects.get("LIGHT_P2_GLASS_SPEC")
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)
    bpy.ops.object.light_add(type="AREA", location=(-0.22, 26.62, 1.22))
    spec = bpy.context.object
    spec.name = "LIGHT_P2_GLASS_SPEC"
    spec.data.energy = 7.5
    spec.data.color = (1.0, 0.90, 0.72)
    spec.data.size = 0.12
    spec.data.shape = "DISK"
    spec.data.use_shadow = False
    look_at(spec, (-0.14, 27.14, 0.90))
    link(spec, col("P2_LIGHTS"))


def tune_cameras() -> None:
    c = col("P2_CAMERAS")
    sit = bpy.data.objects.get("CAM_P2_SIT")
    if sit:
        sit.location = (0.06, 26.58, 1.18)
        sit.data.lens = 32.0
        look_at(sit, (-0.10, 27.14, 0.86))
    # Frontal frame
    front = bpy.data.objects.get("CAM_P2_FRAME_FRONT")
    if front is None:
        bpy.ops.object.camera_add()
        front = bpy.context.object
        front.name = "CAM_P2_FRAME_FRONT"
        link(front, c)
    front.location = (-0.20, 26.78, 0.94)
    front.data.lens = 50.0
    front.data.sensor_width = 36.0
    front.data.clip_start = 0.04
    look_at(front, (-0.14, 27.145, 0.89))
    # Material macro: frame + cloth
    macro = bpy.data.objects.get("CAM_P2_HERO_MACRO")
    if macro is None:
        bpy.ops.object.camera_add()
        macro = bpy.context.object
        macro.name = "CAM_P2_HERO_MACRO"
        link(macro, c)
    macro.location = (0.05, 26.88, 0.98)
    macro.data.lens = 55.0
    macro.data.sensor_width = 36.0
    macro.data.clip_start = 0.03
    look_at(macro, (-0.04, 27.13, 0.84))


def render_stills() -> list[Path]:
    STILL.mkdir(parents=True, exist_ok=True)
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 32
    scene.eevee.use_raytracing = True
    scene.eevee.use_fast_gi = True
    try:
        scene.eevee.fast_gi_method = "AMBIENT_OCCLUSION_ONLY"
    except TypeError:
        pass
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.use_motion_blur = False
    scene.render.use_compositing = False
    orig = scene.camera
    jobs = [
        ("CAM_P2_SIT", "01_sit_fps.png"),
        ("CAM_P2_FRAME_FRONT", "02_frame_front.png"),
        ("CAM_P2_HERO_MACRO", "03_frame_cloth_macro.png"),
    ]
    paths = []
    for cam, fname in jobs:
        scene.camera = bpy.data.objects[cam]
        scene.frame_set(1)
        path = STILL / fname
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        shutil.copy2(path, ARTIFACT / f"part2_frame_{fname}")
        paths.append(path)
        print("still", path, path.stat().st_size)
    scene.camera = orig
    return paths


def main() -> None:
    if Path(bpy.data.filepath).resolve() == PART1.resolve():
        raise SystemExit("refusing hallway.blend")
    if bpy.data.objects.get("P2_FRAME_GLASS") is None:
        raise SystemExit("frame missing")
    before = capture_rig()
    enrich_photo()
    rebuild_glass()
    rebuild_dust()
    rebuild_cloth()
    rebuild_cable()
    tweak_non_rig_cables()
    tune_lights()
    tune_cameras()
    after = capture_rig()
    rig_ok = before == after
    print("rig_unchanged", rig_ok)
    if not rig_ok:
        raise SystemExit("RIG cable data changed")
    paths = render_stills()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    shutil.copy2(BLEND, CHECKPOINT)
    shutil.copy2(BLEND, ARTIFACT / "part2_basement.blend")
    QA.write_text(json.dumps({
        "rig_unchanged": rig_ok,
        "stills": [str(p) for p in paths],
        "blend": str(BLEND),
        "checkpoint": str(CHECKPOINT),
        "hallway_untouched": True,
    }, indent=2))
    print("saved", BLEND, BLEND.stat().st_size)
    print("done")


if __name__ == "__main__":
    main()
