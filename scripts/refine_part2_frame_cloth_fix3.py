#!/usr/bin/env python3
"""Third fix: pull photo/glass/dust in front of the solid wooden outer.

The outer is an 8-vert block. Photo/glass were inside it, so thinning the
dust revealed the wood grain and looked like a torn hole.

Does not move RIG cables, boxes, or architecture. Does not save hallway.blend.
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
    if method == "OPAQUE":
        if hasattr(mat, "surface_render_method"):
            try:
                mat.surface_render_method = "DITHERED"
            except TypeError:
                pass


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


def restack_layers():
    """Camera (-Y) -> dust -> glass -> photo -> wooden outer front."""
    photo = bpy.data.objects["P2_FRAME_PHOTO"]
    glass = bpy.data.objects["P2_FRAME_GLASS"]
    dust = bpy.data.objects["P2_FRAME_DUST"]
    # Outer front is local y = -0.01486. Keep each layer independent.
    photo.location.y = -0.0164
    glass.location.y = -0.0199
    dust.location.y = -0.0215
    print(
        "stack",
        "photo",
        photo.location.y,
        "glass",
        glass.location.y,
        "dust",
        dust.location.y,
    )


def opaque_photo():
    mat = bpy.data.materials["MAT_P2_Photo"]
    set_blend(mat, "OPAQUE")
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Alpha"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.94
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.0
    mix = next((n for n in mat.node_tree.nodes if n.type == "MIX"), None)
    if mix is not None:
        # Keep a faint chemical wash, but do not punch a hole.
        sock(mix, "Factor_Float").default_value = 0.12
        sock(mix, "B_Color").default_value = (0.22, 0.17, 0.12, 1)


def rebuild_glass():
    mat = bpy.data.materials["MAT_P2_Glass"]
    mat.use_nodes = True
    set_blend(mat, "BLEND")
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    trans = nt.nodes.new("ShaderNodeBsdfTransparent")
    trans.inputs["Color"].default_value = (0.92, 0.93, 0.93, 1)
    gloss = nt.nodes.new("ShaderNodeBsdfGlossy")
    gloss.inputs["Color"].default_value = (0.96, 0.97, 0.98, 1)
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.10
    scale = nt.nodes.new("ShaderNodeMath")
    scale.operation = "MULTIPLY"
    scale.inputs[1].default_value = 0.55
    base = nt.nodes.new("ShaderNodeMath")
    base.operation = "ADD"
    base.inputs[1].default_value = 0.035
    clamp = nt.nodes.new("ShaderNodeClamp")
    clamp.inputs["Min"].default_value = 0.03
    clamp.inputs["Max"].default_value = 0.48
    mixs = nt.nodes.new("ShaderNodeMixShader")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapn = nt.nodes.new("ShaderNodeMapping")
    mapn.inputs["Scale"].default_value = (1.0, 0.10, 1.0)
    mapn.inputs["Rotation"].default_value = (0.0, 0.0, 0.27)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.inputs["Scale"].default_value = 42.0
    wave.inputs["Distortion"].default_value = 1.2
    wave.inputs["Detail"].default_value = 1.0
    sc = nt.nodes.new("ShaderNodeValToRGB")
    sc.color_ramp.elements[0].color = (0, 0, 0, 1)
    sc.color_ramp.elements[1].position = 0.92
    sc.color_ramp.elements[1].color = (0, 0, 0, 1)
    hi = sc.color_ramp.elements.new(0.97)
    hi.color = (1, 1, 1, 1)
    nfp = nt.nodes.new("ShaderNodeTexNoise")
    nfp.inputs["Scale"].default_value = 8.5
    nfp.inputs["Detail"].default_value = 8.0
    fp = nt.nodes.new("ShaderNodeValToRGB")
    fp.color_ramp.elements[0].position = 0.70
    fp.color_ramp.elements[0].color = (0, 0, 0, 1)
    fp.color_ramp.elements[1].position = 0.86
    fp.color_ramp.elements[1].color = (1, 1, 1, 1)
    mul_s = nt.nodes.new("ShaderNodeMath")
    mul_s.operation = "MULTIPLY"
    mul_s.inputs[1].default_value = 0.18
    mul_f = nt.nodes.new("ShaderNodeMath")
    mul_f.operation = "MULTIPLY"
    mul_f.inputs[1].default_value = 0.16
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    rough = nt.nodes.new("ShaderNodeMath")
    rough.operation = "ADD"
    rough.inputs[1].default_value = 0.04
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.03
    bump.inputs["Distance"].default_value = 0.00012
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
    glass = bpy.data.objects["P2_FRAME_GLASS"]
    glass.data.materials.clear()
    glass.data.materials.append(mat)


def rebuild_dust():
    mat = bpy.data.materials["MAT_P2_Dust"]
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
    px.inputs[1].default_value = 4.0
    pz = nt.nodes.new("ShaderNodeMath")
    pz.operation = "POWER"
    pz.inputs[1].default_value = 4.0
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.00
    cr.color_ramp.elements[0].color = (0.36, 0.33, 0.26, 0.06)
    mid = cr.color_ramp.elements.new(0.24)
    mid.color = (0.37, 0.33, 0.26, 0.16)
    edge = cr.color_ramp.elements.new(0.50)
    edge.color = (0.39, 0.35, 0.28, 0.42)
    cr.color_ramp.elements[1].position = 0.84
    cr.color_ramp.elements[1].color = (0.43, 0.38, 0.30, 0.88)
    speck = nt.nodes.new("ShaderNodeTexNoise")
    speck.inputs["Scale"].default_value = 170.0
    speck.inputs["Detail"].default_value = 8.0
    sm = nt.nodes.new("ShaderNodeMapRange")
    sm.inputs["To Min"].default_value = 0.72
    sm.inputs["To Max"].default_value = 1.18
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    clamp = nt.nodes.new("ShaderNodeClamp")
    clamp.inputs["Min"].default_value = 0.04
    clamp.inputs["Max"].default_value = 0.88
    colmix = nt.nodes.new("ShaderNodeMix")
    colmix.data_type = "RGBA"
    sock(colmix, "A_Color").default_value = (0.41, 0.37, 0.30, 1)
    sock(colmix, "B_Color").default_value = (0.27, 0.24, 0.19, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.0002
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
    nt.links.new(mul.outputs["Value"], clamp.inputs["Value"])
    nt.links.new(clamp.outputs["Result"], bsdf.inputs["Alpha"])
    nt.links.new(speck.outputs["Fac"], sock(colmix, "Factor_Float"))
    nt.links.new(sock(colmix, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(speck.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    dust = bpy.data.objects["P2_FRAME_DUST"]
    dust.data.materials.clear()
    dust.data.materials.append(mat)


def cameras_and_light():
    sit = bpy.data.objects["CAM_P2_SIT"]
    sit.location = (0.06, 26.58, 1.18)
    sit.data.lens = 32.0
    look_at(sit, (-0.10, 27.14, 0.86))
    front = bpy.data.objects["CAM_P2_FRAME_FRONT"]
    front.location = (-0.18, 26.52, 0.96)
    front.data.lens = 38.0
    look_at(front, (-0.14, 27.14, 0.89))
    macro = bpy.data.objects["CAM_P2_HERO_MACRO"]
    macro.location = (0.16, 26.78, 0.90)
    macro.data.lens = 40.0
    look_at(macro, (-0.02, 27.13, 0.82))
    spec = bpy.data.objects.get("LIGHT_P2_GLASS_SPEC")
    if spec:
        spec.data.energy = 8.0
        spec.data.size = 0.09
        spec.location = (-0.42, 26.40, 1.38)
        look_at(spec, (-0.14, 27.14, 0.90))
    kiss = bpy.data.objects.get("LIGHT_P2_FRAME_KISS")
    if kiss:
        kiss.data.energy = 3.0
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
    before = capture_rig()
    restack_layers()
    opaque_photo()
    rebuild_glass()
    rebuild_dust()
    cameras_and_light()
    after = capture_rig()
    print("rig_unchanged", before == after)
    if before != after:
        raise SystemExit("RIG changed")
    render()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
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
                "pass": "fix3_restack_opaque_photo",
                "stack": {
                    "photo_y": bpy.data.objects["P2_FRAME_PHOTO"].location.y,
                    "glass_y": bpy.data.objects["P2_FRAME_GLASS"].location.y,
                    "dust_y": bpy.data.objects["P2_FRAME_DUST"].location.y,
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
