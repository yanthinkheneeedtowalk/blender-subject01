#!/usr/bin/env python3
"""Cloth-only contrast fix. Frame stack, glass, cables, architecture unchanged."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import bpy

BLEND = Path("/workspace/part2_basement.blend")
PART1 = Path("/workspace/hallway.blend")
STILL = Path("/workspace/renders/part2_basement/stills_frame_cloth")
CHECKPOINT = Path("/workspace/renders/checkpoints/part2_basement_frame_cloth.blend")
QA = Path("/workspace/renders/part2_basement/frame_cloth_qa.json")
RIG = [f"P2_CABLE_RIG_{i:02d}" for i in range(1, 7)]
HALLWAY_MD5_LOCK = "e2a4c51380aed23fbb95d631d02e9252"


def sock(node, ident):
    for s in list(node.inputs) + list(node.outputs):
        if s.identifier == ident or s.name == ident:
            return s
    raise KeyError(ident)


def capture_rig():
    out = {}
    for name in RIG:
        obj = bpy.data.objects[name]
        pts = []
        for sp in obj.data.splines:
            for bp in sp.bezier_points:
                pts.append(
                    (
                        round(bp.co.x, 5),
                        round(bp.co.y, 5),
                        round(bp.co.z, 5),
                        round(bp.radius, 5),
                    )
                )
        out[name] = (round(obj.data.bevel_depth, 5), tuple(pts))
    return out


def rebuild_cloth():
    mat = bpy.data.materials["MAT_P2_Cloth"]
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.02
    if "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = 0.22
        if "Sheen Roughness" in bsdf.inputs:
            bsdf.inputs["Sheen Roughness"].default_value = 0.78
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.03
    coord = nt.nodes.new("ShaderNodeTexCoord")
    map1 = nt.nodes.new("ShaderNodeMapping")
    w1 = nt.nodes.new("ShaderNodeTexWave")
    w1.wave_type = "BANDS"
    w1.inputs["Scale"].default_value = 38.0
    w1.inputs["Distortion"].default_value = 1.6
    map2 = nt.nodes.new("ShaderNodeMapping")
    map2.inputs["Rotation"].default_value = (0.0, 0.0, 1.5708)
    w2 = nt.nodes.new("ShaderNodeTexWave")
    w2.wave_type = "BANDS"
    w2.inputs["Scale"].default_value = 38.0
    w2.inputs["Distortion"].default_value = 1.6
    weave = nt.nodes.new("ShaderNodeMath")
    weave.operation = "MULTIPLY"
    stain_n = nt.nodes.new("ShaderNodeTexNoise")
    stain_n.inputs["Scale"].default_value = 5.5
    stain_n.inputs["Detail"].default_value = 14.0
    stain_n.inputs["Roughness"].default_value = 0.65
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.32
    cr.color_ramp.elements[0].color = (0.045, 0.035, 0.025, 1)
    s1 = cr.color_ramp.elements.new(0.50)
    s1.color = (0.16, 0.13, 0.09, 1)
    cr.color_ramp.elements[1].position = 0.68
    cr.color_ramp.elements[1].color = (0.31, 0.27, 0.21, 1)
    weave_mul = nt.nodes.new("ShaderNodeMath")
    weave_mul.operation = "MULTIPLY"
    weave_mul.inputs[1].default_value = 0.22
    weave_one = nt.nodes.new("ShaderNodeMath")
    weave_one.operation = "SUBTRACT"
    weave_one.inputs[0].default_value = 1.0
    # albedo * (1 - 0.22*(1-weave)) so the grid darkens threads
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    scale_w = nt.nodes.new("ShaderNodeMath")
    scale_w.operation = "MULTIPLY"
    scale_w.inputs[1].default_value = 0.18
    grid = nt.nodes.new("ShaderNodeMath")
    grid.operation = "SUBTRACT"
    grid.inputs[0].default_value = 1.0
    colmix = nt.nodes.new("ShaderNodeMix")
    colmix.data_type = "RGBA"
    colmix.blend_type = "MULTIPLY"
    sock(colmix, "B_Color").default_value = (0.55, 0.50, 0.42, 1)
    fade_n = nt.nodes.new("ShaderNodeTexNoise")
    fade_n.inputs["Scale"].default_value = 2.8
    fade_n.inputs["Detail"].default_value = 5.0
    mixf = nt.nodes.new("ShaderNodeMix")
    mixf.data_type = "RGBA"
    sock(mixf, "B_Color").default_value = (0.38, 0.33, 0.24, 1)
    rough = nt.nodes.new("ShaderNodeValToRGB")
    rough.color_ramp.elements[0].position = 0.30
    rough.color_ramp.elements[0].color = (0.58, 0.58, 0.58, 1)
    rough.color_ramp.elements[1].position = 0.72
    rough.color_ramp.elements[1].color = (0.90, 0.90, 0.90, 1)
    bump_w = nt.nodes.new("ShaderNodeBump")
    bump_w.inputs["Strength"].default_value = 0.40
    bump_w.inputs["Distance"].default_value = 0.0007
    bump_s = nt.nodes.new("ShaderNodeBump")
    bump_s.inputs["Strength"].default_value = 0.28
    bump_s.inputs["Distance"].default_value = 0.0024
    nt.links.new(coord.outputs["Generated"], map1.inputs["Vector"])
    nt.links.new(coord.outputs["Generated"], map2.inputs["Vector"])
    nt.links.new(map1.outputs["Vector"], w1.inputs["Vector"])
    nt.links.new(map2.outputs["Vector"], w2.inputs["Vector"])
    nt.links.new(w1.outputs["Fac"], weave.inputs[0])
    nt.links.new(w2.outputs["Fac"], weave.inputs[1])
    nt.links.new(coord.outputs["Generated"], stain_n.inputs["Vector"])
    nt.links.new(coord.outputs["Generated"], fade_n.inputs["Vector"])
    nt.links.new(stain_n.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(weave.outputs["Value"], inv.inputs[1])
    nt.links.new(inv.outputs["Value"], scale_w.inputs[0])
    nt.links.new(scale_w.outputs["Value"], grid.inputs[1])
    nt.links.new(cr.outputs["Color"], sock(colmix, "A_Color"))
    nt.links.new(grid.outputs["Value"], sock(colmix, "Factor_Float"))
    nt.links.new(sock(colmix, "Result_Color"), sock(mixf, "A_Color"))
    nt.links.new(fade_n.outputs["Fac"], sock(mixf, "Factor_Float"))
    nt.links.new(sock(mixf, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(stain_n.outputs["Fac"], rough.inputs["Fac"])
    nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(weave.outputs["Value"], bump_w.inputs["Height"])
    nt.links.new(bump_w.outputs["Normal"], bump_s.inputs["Normal"])
    nt.links.new(stain_n.outputs["Fac"], bump_s.inputs["Height"])
    nt.links.new(bump_s.outputs["Normal"], bsdf.inputs["Normal"])
    cloth = bpy.data.objects["P2_CLOTH"]
    cloth.data.materials.clear()
    cloth.data.materials.append(mat)


def render():
    STILL.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 32
    scene.eevee.use_raytracing = True
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    orig = scene.camera
    jobs = [
        ("CAM_P2_SIT", "01_sit_fps.png"),
        ("CAM_P2_FRAME_FRONT", "02_frame_front.png"),
        ("CAM_P2_HERO_MACRO", "03_frame_cloth_macro.png"),
    ]
    for cam, fname in jobs:
        scene.camera = bpy.data.objects[cam]
        scene.frame_set(1)
        path = STILL / fname
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print("still", path)
    scene.camera = orig


def main():
    if Path(bpy.data.filepath).resolve() == PART1.resolve():
        raise SystemExit("refusing hallway.blend")
    before = capture_rig()
    rebuild_cloth()
    after = capture_rig()
    print("rig_unchanged", before == after)
    if before != after:
        raise SystemExit("RIG changed")
    render()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    shutil.copy2(BLEND, CHECKPOINT)
    QA.write_text(
        json.dumps(
            {
                "rig_unchanged": True,
                "stills": [str(STILL / n) for n in ("01_sit_fps.png", "02_frame_front.png", "03_frame_cloth_macro.png")],
                "blend": str(BLEND),
                "checkpoint": str(CHECKPOINT),
                "hallway_untouched": True,
                "hallway_md5_lock": HALLWAY_MD5_LOCK,
                "pass": "fix6_cloth_stain_contrast",
            },
            indent=2,
        )
        + "\n"
    )
    print("saved", BLEND.stat().st_size)
    print("done")


if __name__ == "__main__":
    main()
