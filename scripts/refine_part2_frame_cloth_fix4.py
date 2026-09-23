#!/usr/bin/env python3
"""Fourth fix: kill the blown glass orb, keep faint photo, dirty the cloth.

Does not move RIG cables, boxes, architecture, or the restacked frame layers.
Does not save hallway.blend.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import bpy
from mathutils import Vector

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


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - Vector(obj.location)).to_track_quat("-Z", "Y").to_euler()


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
    mat = bpy.data.materials["MAT_P2_Glass"]
    mat.use_nodes = True
    set_blend(mat, "BLEND")
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    trans = nt.nodes.new("ShaderNodeBsdfTransparent")
    trans.inputs["Color"].default_value = (0.91, 0.92, 0.91, 1)
    gloss = nt.nodes.new("ShaderNodeBsdfGlossy")
    gloss.inputs["Color"].default_value = (0.88, 0.90, 0.91, 1)
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.08
    scale = nt.nodes.new("ShaderNodeMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = 0.42
    base = nt.nodes.new("ShaderNodeMath")
    base.operation = "ADD"
    base.inputs[1].default_value = 0.03
    clamp = nt.nodes.new("ShaderNodeClamp")
    clamp.inputs["Min"].default_value = 0.025
    clamp.inputs["Max"].default_value = 0.32
    mixs = nt.nodes.new("ShaderNodeMixShader")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapn = nt.nodes.new("ShaderNodeMapping")
    mapn.inputs["Scale"].default_value = (1.0, 0.35, 1.0)
    mapn.inputs["Rotation"].default_value = (0.0, 0.0, 0.18)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.inputs["Scale"].default_value = 36.0
    wave.inputs["Distortion"].default_value = 0.8
    wave.inputs["Detail"].default_value = 1.0
    sc = nt.nodes.new("ShaderNodeValToRGB")
    sc.color_ramp.elements[0].color = (0, 0, 0, 1)
    sc.color_ramp.elements[1].position = 0.86
    sc.color_ramp.elements[1].color = (0, 0, 0, 1)
    hi = sc.color_ramp.elements.new(0.94)
    hi.color = (0.7, 0.7, 0.7, 1)
    nfp = nt.nodes.new("ShaderNodeTexNoise")
    nfp.inputs["Scale"].default_value = 7.5
    nfp.inputs["Detail"].default_value = 8.0
    fp = nt.nodes.new("ShaderNodeValToRGB")
    fp.color_ramp.elements[0].position = 0.66
    fp.color_ramp.elements[0].color = (0, 0, 0, 1)
    fp.color_ramp.elements[1].position = 0.84
    fp.color_ramp.elements[1].color = (1, 1, 1, 1)
    mul_s = nt.nodes.new("ShaderNodeMath")
    mul_s.operation = "MULTIPLY"
    mul_s.inputs[1].default_value = 0.14
    mul_f = nt.nodes.new("ShaderNodeMath")
    mul_f.operation = "MULTIPLY"
    mul_f.inputs[1].default_value = 0.20
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    rough = nt.nodes.new("ShaderNodeMath")
    rough.operation = "ADD"
    rough.inputs[1].default_value = 0.09
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.025
    bump.inputs["Distance"].default_value = 0.0001
    nt.links.new(coord.outputs["Object"], mapn.inputs["Vector"])
    nt.links.new(mapn.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], nfp.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], sc.inputs["Fac"])
    nt.links.new(nfp.outputs["Fac"], fp.inputs["Fac"])
    nt.links.new(sc.outputs["Color"], mul_s.inputs[0])
    nt.links.new(fp.outputs["Color"], mul_f.inputs[0])
    nt.links.new(mul_s.outputs["Value"], add.inputs[0])
    nt.links.new(mul_f.outputs["Value"], add.inputs[1])
    nt.links.new(add.outputs["Value"], rough.inputs[0])
    nt.links.new(rough.outputs["Value"], gloss.inputs["Roughness"])
    nt.links.new(mul_s.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], gloss.inputs["Normal"])
    nt.links.new(lw.outputs["Fresnel"], scale.inputs[0])
    nt.links.new(scale.outputs["Value"], base.inputs[0])
    nt.links.new(base.outputs["Value"], clamp.inputs["Value"])
    nt.links.new(trans.outputs["BSDF"], mixs.inputs[1])
    nt.links.new(gloss.outputs["BSDF"], mixs.inputs[2])
    nt.links.new(clamp.outputs["Result"], mixs.inputs["Fac"])
    nt.links.new(mixs.outputs["Shader"], out.inputs["Surface"])


def rebuild_dust():
    mat = bpy.data.materials["MAT_P2_Dust"]
    mat.use_nodes = True
    set_blend(mat, "HASHED")
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.98
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.015
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    absx = nt.nodes.new("ShaderNodeMath")
    absx.operation = "ABSOLUTE"
    absz = nt.nodes.new("ShaderNodeMath")
    absz.operation = "ABSOLUTE"
    divx = nt.nodes.new("ShaderNodeMath")
    divx.operation = "DIVIDE"
    divx.inputs[1].default_value = 0.084
    divz = nt.nodes.new("ShaderNodeMath")
    divz.operation = "DIVIDE"
    divz.inputs[1].default_value = 0.109
    px = nt.nodes.new("ShaderNodeMath")
    px.operation = "POWER"
    px.inputs[1].default_value = 3.4
    pz = nt.nodes.new("ShaderNodeMath")
    pz.operation = "POWER"
    pz.inputs[1].default_value = 3.4
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.00
    cr.color_ramp.elements[0].color = (0.34, 0.31, 0.24, 0.10)
    mid = cr.color_ramp.elements.new(0.20)
    mid.color = (0.36, 0.32, 0.25, 0.22)
    edge = cr.color_ramp.elements.new(0.46)
    edge.color = (0.39, 0.35, 0.27, 0.55)
    cr.color_ramp.elements[1].position = 0.80
    cr.color_ramp.elements[1].color = (0.44, 0.39, 0.30, 0.92)
    speck = nt.nodes.new("ShaderNodeTexNoise")
    speck.inputs["Scale"].default_value = 150.0
    speck.inputs["Detail"].default_value = 8.0
    sm = nt.nodes.new("ShaderNodeMapRange")
    sm.inputs["To Min"].default_value = 0.70
    sm.inputs["To Max"].default_value = 1.20
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    clampn = nt.nodes.new("ShaderNodeClamp")
    clampn.inputs["Min"].default_value = 0.08
    clampn.inputs["Max"].default_value = 0.92
    colmix = nt.nodes.new("ShaderNodeMix")
    colmix.data_type = "RGBA"
    sock(colmix, "A_Color").default_value = (0.40, 0.36, 0.28, 1)
    sock(colmix, "B_Color").default_value = (0.24, 0.21, 0.16, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.00022
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["X"], absx.inputs[0])
    nt.links.new(sep.outputs["Z"], absz.inputs[0])
    nt.links.new(absx.outputs["Value"], divx.inputs[0])
    nt.links.new(absz.outputs["Value"], divz.inputs[0])
    nt.links.new(divx.outputs["Value"], px.inputs[0])
    nt.links.new(divz.outputs["Value"], pz.inputs[0])
    nt.links.new(px.outputs["Value"], add.inputs[0])
    nt.links.new(pz.outputs["Value"], add.inputs[1])
    nt.links.new(add.outputs["Value"], cr.inputs["Fac"])
    nt.links.new(coord.outputs["Object"], speck.inputs["Vector"])
    nt.links.new(speck.outputs["Fac"], sm.inputs["Value"])
    nt.links.new(cr.outputs["Alpha"], mul.inputs[0])
    nt.links.new(sm.outputs["Result"], mul.inputs[1])
    nt.links.new(mul.outputs["Value"], clampn.inputs["Value"])
    nt.links.new(clampn.outputs["Result"], bsdf.inputs["Alpha"])
    nt.links.new(speck.outputs["Fac"], sock(colmix, "Factor_Float"))
    nt.links.new(sock(colmix, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(speck.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


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
        bsdf.inputs["Sheen Weight"].default_value = 0.62
        if "Sheen Roughness" in bsdf.inputs:
            bsdf.inputs["Sheen Roughness"].default_value = 0.66
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.04
    coord = nt.nodes.new("ShaderNodeTexCoord")
    map1 = nt.nodes.new("ShaderNodeMapping")
    w1 = nt.nodes.new("ShaderNodeTexWave")
    w1.wave_type = "BANDS"
    w1.inputs["Scale"].default_value = 150.0
    w1.inputs["Distortion"].default_value = 1.3
    w1.inputs["Detail"].default_value = 2.0
    map2 = nt.nodes.new("ShaderNodeMapping")
    map2.inputs["Rotation"].default_value = (0.0, 0.0, 1.5708)
    w2 = nt.nodes.new("ShaderNodeTexWave")
    w2.wave_type = "BANDS"
    w2.inputs["Scale"].default_value = 150.0
    w2.inputs["Distortion"].default_value = 1.3
    weave = nt.nodes.new("ShaderNodeMath")
    weave.operation = "MULTIPLY"
    stain_n = nt.nodes.new("ShaderNodeTexNoise")
    stain_n.inputs["Scale"].default_value = 4.6
    stain_n.inputs["Detail"].default_value = 12.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.14
    cr.color_ramp.elements[0].color = (0.10, 0.08, 0.06, 1)
    s1 = cr.color_ramp.elements.new(0.40)
    s1.color = (0.20, 0.17, 0.13, 1)
    cr.color_ramp.elements[1].position = 0.78
    cr.color_ramp.elements[1].color = (0.34, 0.30, 0.24, 1)
    weave_col = nt.nodes.new("ShaderNodeMix")
    weave_col.data_type = "RGBA"
    weave_col.blend_type = "MULTIPLY"
    sock(weave_col, "B_Color").default_value = (0.50, 0.47, 0.41, 1)
    dustn = nt.nodes.new("ShaderNodeTexNoise")
    dustn.inputs["Scale"].default_value = 9.0
    dustn.inputs["Detail"].default_value = 6.0
    mixd = nt.nodes.new("ShaderNodeMix")
    mixd.data_type = "RGBA"
    sock(mixd, "B_Color").default_value = (0.22, 0.19, 0.14, 1)
    fade_n = nt.nodes.new("ShaderNodeTexNoise")
    fade_n.inputs["Scale"].default_value = 2.2
    fade_n.inputs["Detail"].default_value = 4.0
    mixf = nt.nodes.new("ShaderNodeMix")
    mixf.data_type = "RGBA"
    sock(mixf, "B_Color").default_value = (0.38, 0.34, 0.27, 1)
    rough = nt.nodes.new("ShaderNodeValToRGB")
    rough.color_ramp.elements[0].position = 0.18
    rough.color_ramp.elements[0].color = (0.66, 0.66, 0.66, 1)
    rough.color_ramp.elements[1].position = 0.80
    rough.color_ramp.elements[1].color = (0.92, 0.92, 0.92, 1)
    bump_w = nt.nodes.new("ShaderNodeBump")
    bump_w.inputs["Strength"].default_value = 0.32
    bump_w.inputs["Distance"].default_value = 0.0005
    bump_s = nt.nodes.new("ShaderNodeBump")
    bump_s.inputs["Strength"].default_value = 0.20
    bump_s.inputs["Distance"].default_value = 0.0018
    nt.links.new(coord.outputs["Object"], map1.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], map2.inputs["Vector"])
    nt.links.new(map1.outputs["Vector"], w1.inputs["Vector"])
    nt.links.new(map2.outputs["Vector"], w2.inputs["Vector"])
    nt.links.new(w1.outputs["Fac"], weave.inputs[0])
    nt.links.new(w2.outputs["Fac"], weave.inputs[1])
    nt.links.new(coord.outputs["Object"], stain_n.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], dustn.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], fade_n.inputs["Vector"])
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
        spec.data.energy = 1.8
        spec.data.size = 0.28
        spec.data.color = (1.0, 0.90, 0.72)
        spec.data.use_shadow = False
        spec.location = (-0.55, 26.20, 1.55)
        look_at(spec, (-0.14, 27.14, 0.90))
    kiss = bpy.data.objects.get("LIGHT_P2_FRAME_KISS")
    if kiss:
        kiss.data.energy = 2.6
    pendant = bpy.data.objects.get("LIGHT_P2_DESK_PENDANT")
    if pendant:
        pendant.data.energy = 96.0
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
    photo = bpy.data.objects["P2_FRAME_PHOTO"]
    glass = bpy.data.objects["P2_FRAME_GLASS"]
    dust = bpy.data.objects["P2_FRAME_DUST"]
    print("stack", photo.location.y, glass.location.y, dust.location.y)
    before = capture_rig()
    rebuild_glass()
    rebuild_dust()
    rebuild_cloth()
    lights()
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
                "pass": "fix4_soft_spec_dirty_cloth",
                "stack": {
                    "photo_y": photo.location.y,
                    "glass_y": glass.location.y,
                    "dust_y": dust.location.y,
                },
            },
            indent=2,
        )
        + "\n"
    )
    print("saved", BLEND.stat().st_size)
    print("done")


if __name__ == "__main__":
    main()
