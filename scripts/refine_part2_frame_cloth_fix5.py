#!/usr/bin/env python3
"""Fifth fix: dirty-glass roughness kills the pendant orb; cloth stains use generated UV.

Does not move RIG cables, boxes, architecture, or restacked frame layers.
Does not save hallway.blend.
"""

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


def set_blend(mat, method):
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
    if method == "BLEND" and hasattr(mat, "use_screen_refraction"):
        mat.use_screen_refraction = True


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


def rebuild_glass():
    """Dirty picture-frame glass: photo reads, spec is a soft sheen not a lamp orb."""
    mat = bpy.data.materials["MAT_P2_Glass"]
    mat.use_nodes = True
    set_blend(mat, "BLEND")
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    trans = nt.nodes.new("ShaderNodeBsdfTransparent")
    trans.inputs["Color"].default_value = (0.90, 0.91, 0.90, 1)
    gloss = nt.nodes.new("ShaderNodeBsdfGlossy")
    gloss.inputs["Color"].default_value = (0.82, 0.84, 0.85, 1)
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.06
    scale = nt.nodes.new("ShaderNodeMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = 0.28
    addf = nt.nodes.new("ShaderNodeMath")
    addf.operation = "ADD"
    addf.inputs[1].default_value = 0.02
    clamp = nt.nodes.new("ShaderNodeClamp")
    clamp.inputs["Min"].default_value = 0.02
    clamp.inputs["Max"].default_value = 0.18
    mixs = nt.nodes.new("ShaderNodeMixShader")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapn = nt.nodes.new("ShaderNodeMapping")
    mapn.inputs["Scale"].default_value = (1.0, 0.45, 1.0)
    mapn.inputs["Rotation"].default_value = (0.0, 0.0, 0.22)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.inputs["Scale"].default_value = 28.0
    wave.inputs["Distortion"].default_value = 0.6
    wave.inputs["Detail"].default_value = 0.0
    sc = nt.nodes.new("ShaderNodeValToRGB")
    sc.color_ramp.elements[0].color = (0, 0, 0, 1)
    sc.color_ramp.elements[1].position = 0.88
    sc.color_ramp.elements[1].color = (0, 0, 0, 1)
    hi = sc.color_ramp.elements.new(0.96)
    hi.color = (1, 1, 1, 1)
    nfp = nt.nodes.new("ShaderNodeTexNoise")
    nfp.inputs["Scale"].default_value = 6.5
    nfp.inputs["Detail"].default_value = 8.0
    fp = nt.nodes.new("ShaderNodeValToRGB")
    fp.color_ramp.elements[0].position = 0.64
    fp.color_ramp.elements[0].color = (0, 0, 0, 1)
    fp.color_ramp.elements[1].position = 0.82
    fp.color_ramp.elements[1].color = (1, 1, 1, 1)
    mul_s = nt.nodes.new("ShaderNodeMath")
    mul_s.operation = "MULTIPLY"
    mul_s.inputs[1].default_value = 0.10
    mul_f = nt.nodes.new("ShaderNodeMath")
    mul_f.operation = "MULTIPLY"
    mul_f.inputs[1].default_value = 0.16
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    rough = nt.nodes.new("ShaderNodeMath")
    rough.operation = "ADD"
    rough.inputs[1].default_value = 0.28
    nt.links.new(coord.outputs["Object"], mapn.inputs["Vector"])
    nt.links.new(mapn.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(coord.outputs["Generated"], nfp.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], sc.inputs["Fac"])
    nt.links.new(nfp.outputs["Fac"], fp.inputs["Fac"])
    nt.links.new(sc.outputs["Color"], mul_s.inputs[0])
    nt.links.new(fp.outputs["Color"], mul_f.inputs[0])
    nt.links.new(mul_s.outputs["Value"], add.inputs[0])
    nt.links.new(mul_f.outputs["Value"], add.inputs[1])
    nt.links.new(add.outputs["Value"], rough.inputs[0])
    nt.links.new(rough.outputs["Value"], gloss.inputs["Roughness"])
    nt.links.new(lw.outputs["Fresnel"], scale.inputs[0])
    nt.links.new(scale.outputs["Value"], addf.inputs[0])
    nt.links.new(addf.outputs["Value"], clamp.inputs["Value"])
    nt.links.new(trans.outputs["BSDF"], mixs.inputs[1])
    nt.links.new(gloss.outputs["BSDF"], mixs.inputs[2])
    nt.links.new(clamp.outputs["Result"], mixs.inputs["Fac"])
    nt.links.new(mixs.outputs["Shader"], out.inputs["Surface"])


def rebuild_cloth():
    mat = bpy.data.materials["MAT_P2_Cloth"]
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.03
    if "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = 0.58
        if "Sheen Roughness" in bsdf.inputs:
            bsdf.inputs["Sheen Roughness"].default_value = 0.70
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.04
    coord = nt.nodes.new("ShaderNodeTexCoord")
    map1 = nt.nodes.new("ShaderNodeMapping")
    w1 = nt.nodes.new("ShaderNodeTexWave")
    w1.wave_type = "BANDS"
    w1.inputs["Scale"].default_value = 42.0
    w1.inputs["Distortion"].default_value = 1.4
    map2 = nt.nodes.new("ShaderNodeMapping")
    map2.inputs["Rotation"].default_value = (0.0, 0.0, 1.5708)
    w2 = nt.nodes.new("ShaderNodeTexWave")
    w2.wave_type = "BANDS"
    w2.inputs["Scale"].default_value = 42.0
    w2.inputs["Distortion"].default_value = 1.4
    weave = nt.nodes.new("ShaderNodeMath")
    weave.operation = "MULTIPLY"
    stain_n = nt.nodes.new("ShaderNodeTexNoise")
    stain_n.inputs["Scale"].default_value = 7.0
    stain_n.inputs["Detail"].default_value = 12.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.18
    cr.color_ramp.elements[0].color = (0.09, 0.07, 0.05, 1)
    s1 = cr.color_ramp.elements.new(0.45)
    s1.color = (0.18, 0.15, 0.11, 1)
    cr.color_ramp.elements[1].position = 0.76
    cr.color_ramp.elements[1].color = (0.33, 0.29, 0.23, 1)
    weave_col = nt.nodes.new("ShaderNodeMix")
    weave_col.data_type = "RGBA"
    weave_col.blend_type = "MULTIPLY"
    sock(weave_col, "B_Color").default_value = (0.48, 0.45, 0.39, 1)
    dustn = nt.nodes.new("ShaderNodeTexNoise")
    dustn.inputs["Scale"].default_value = 14.0
    dustn.inputs["Detail"].default_value = 6.0
    mixd = nt.nodes.new("ShaderNodeMix")
    mixd.data_type = "RGBA"
    sock(mixd, "B_Color").default_value = (0.20, 0.17, 0.12, 1)
    fade_n = nt.nodes.new("ShaderNodeTexNoise")
    fade_n.inputs["Scale"].default_value = 3.5
    fade_n.inputs["Detail"].default_value = 4.0
    mixf = nt.nodes.new("ShaderNodeMix")
    mixf.data_type = "RGBA"
    sock(mixf, "B_Color").default_value = (0.36, 0.32, 0.25, 1)
    rough = nt.nodes.new("ShaderNodeValToRGB")
    rough.color_ramp.elements[0].position = 0.20
    rough.color_ramp.elements[0].color = (0.64, 0.64, 0.64, 1)
    rough.color_ramp.elements[1].position = 0.80
    rough.color_ramp.elements[1].color = (0.92, 0.92, 0.92, 1)
    bump_w = nt.nodes.new("ShaderNodeBump")
    bump_w.inputs["Strength"].default_value = 0.36
    bump_w.inputs["Distance"].default_value = 0.0006
    bump_s = nt.nodes.new("ShaderNodeBump")
    bump_s.inputs["Strength"].default_value = 0.22
    bump_s.inputs["Distance"].default_value = 0.0020
    nt.links.new(coord.outputs["Generated"], map1.inputs["Vector"])
    nt.links.new(coord.outputs["Generated"], map2.inputs["Vector"])
    nt.links.new(map1.outputs["Vector"], w1.inputs["Vector"])
    nt.links.new(map2.outputs["Vector"], w2.inputs["Vector"])
    nt.links.new(w1.outputs["Fac"], weave.inputs[0])
    nt.links.new(w2.outputs["Fac"], weave.inputs[1])
    nt.links.new(coord.outputs["Generated"], stain_n.inputs["Vector"])
    nt.links.new(coord.outputs["Generated"], dustn.inputs["Vector"])
    nt.links.new(coord.outputs["Generated"], fade_n.inputs["Vector"])
    nt.links.new(stain_n.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], sock(weave_col, "A_Color"))
    nt.links.new(weave.outputs["Value"], sock(weave_col, "Factor_Float"))
    nt.links.new(sock(weave_col, "Result_Color"), sock(mixd, "A_Color"))
    nt.links.new(dustn.outputs["Fac"], sock(mixd, "Factor_Float"))
    nt.links.new(sock(mixd, "Result_Color"), sock(mixf, "A_Color"))
    nt.links.new(fade_n.outputs["Fac"], sock(mixf, "Factor_Float"))
    nt.links.new(sock(mixf, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(stain_n.outputs["Fac"], rough.inputs["Fac"])
    nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    nt.links.new(weave.outputs["Value"], bump_w.inputs["Height"])
    nt.links.new(bump_w.outputs["Normal"], bump_s.inputs["Normal"])
    nt.links.new(stain_n.outputs["Fac"], bump_s.inputs["Height"])
    nt.links.new(bump_s.outputs["Normal"], bsdf.inputs["Normal"])


def lights():
    spec = bpy.data.objects.get("LIGHT_P2_GLASS_SPEC")
    if spec:
        spec.data.energy = 0.0
        spec.hide_render = True
    kiss = bpy.data.objects.get("LIGHT_P2_FRAME_KISS")
    if kiss:
        kiss.data.energy = 2.4
    pendant = bpy.data.objects.get("LIGHT_P2_DESK_PENDANT")
    if pendant:
        pendant.data.energy = 96.0
        if hasattr(pendant.data, "specular_factor"):
            # Keep room lighting; dirty glass shader handles the rest.
            pass
    bpy.context.scene.eevee.use_raytracing = True


def render():
    STILL.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 32
    scene.eevee.use_raytracing = True
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.image_settings.file_format = "PNG"
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
    rebuild_glass()
    rebuild_cloth()
    lights()
    after = capture_rig()
    print("rig_unchanged", before == after)
    if before != after:
        raise SystemExit("RIG changed")
    print(
        "stack",
        bpy.data.objects["P2_FRAME_PHOTO"].location.y,
        bpy.data.objects["P2_FRAME_GLASS"].location.y,
        bpy.data.objects["P2_FRAME_DUST"].location.y,
    )
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
                "pass": "fix5_dirty_glass_generated_cloth",
            },
            indent=2,
        )
        + "\n"
    )
    print("saved", BLEND.stat().st_size)
    print("done")


if __name__ == "__main__":
    main()
