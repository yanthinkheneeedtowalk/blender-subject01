#!/usr/bin/env python3
"""Replace low-frequency dust blob with fine grain. Hero stills only."""

from pathlib import Path
import math
import random
import shutil

import bpy
from mathutils import Vector

BLEND = Path("/workspace/part2_basement.blend")
PART1 = Path("/workspace/hallway.blend")
STILL_DIR = Path("/workspace/renders/part2_basement/stills")
ARTIFACT = Path("/opt/cursor/artifacts")
CHECKPOINT = Path("/workspace/renders/checkpoints/part2_basement_detail.blend")


def sock(node, ident):
    for s in list(node.inputs) + list(node.outputs):
        if s.identifier == ident or s.name == ident:
            return s
    raise KeyError(ident)


def set_blend(mat, method="HASHED"):
    if hasattr(mat, "blend_method"):
        try:
            mat.blend_method = method
        except TypeError:
            pass


def rebuild_dust_mat():
    mat = bpy.data.materials.get("MAT_P2_Dust") or bpy.data.materials.new("MAT_P2_Dust")
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
    n_fine = nt.nodes.new("ShaderNodeTexNoise")
    n_fine.inputs["Scale"].default_value = 85.0
    n_fine.inputs["Detail"].default_value = 12.0
    n_speck = nt.nodes.new("ShaderNodeTexNoise")
    n_speck.inputs["Scale"].default_value = 160.0
    n_speck.inputs["Detail"].default_value = 6.0
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
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
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.05
    cr.color_ramp.elements[0].color = (0.32, 0.29, 0.23, 0.62)
    mid = cr.color_ramp.elements.new(0.40)
    mid.color = (0.34, 0.31, 0.25, 0.78)
    cr.color_ramp.elements[1].position = 0.80
    cr.color_ramp.elements[1].color = (0.38, 0.34, 0.27, 0.92)
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["To Min"].default_value = 0.78
    rng.inputs["To Max"].default_value = 1.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["X"], subx.inputs[0])
    nt.links.new(sep.outputs["Z"], subz.inputs[0])
    nt.links.new(subx.outputs["Value"], absx.inputs[0])
    nt.links.new(subz.outputs["Value"], absz.inputs[0])
    nt.links.new(absx.outputs["Value"], add.inputs[0])
    nt.links.new(absz.outputs["Value"], add.inputs[1])
    nt.links.new(add.outputs["Value"], cr.inputs["Fac"])
    nt.links.new(coord.outputs["Object"], n_fine.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], n_speck.inputs["Vector"])
    nt.links.new(n_fine.outputs["Fac"], rng.inputs["Value"])
    nt.links.new(cr.outputs["Alpha"], mul.inputs[0])
    nt.links.new(rng.outputs["Result"], mul.inputs[1])
    nt.links.new(mul.outputs["Value"], bsdf.inputs["Alpha"])
    colmix = nt.nodes.new("ShaderNodeMix")
    colmix.data_type = "RGBA"
    sock(colmix, "A_Color").default_value = (0.33, 0.30, 0.24, 1)
    sock(colmix, "B_Color").default_value = (0.28, 0.25, 0.20, 1)
    nt.links.new(n_speck.outputs["Fac"], sock(colmix, "Factor_Float"))
    nt.links.new(sock(colmix, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(n_speck.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def flatten_dust_mesh():
    dust = bpy.data.objects.get("P2_FRAME_DUST")
    if dust is None or dust.type != "MESH":
        return
    rng = random.Random(77)
    # Keep a thin slab; only fine grain, no large island.
    for v in dust.data.vertices:
        # Plane is in XZ; thickness along Y.
        v.co.y = -0.0011 + rng.uniform(-0.00025, 0.00025)
        if abs(v.co.x) > 0.07 or abs(v.co.z) > 0.09:
            v.co.y -= 0.0006


def render_hero():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    orig = scene.camera
    for cam, fname in (
        ("CAM_P2_WIDE", "01_wide.png"),
        ("CAM_P2_SIT", "02_sit_fps.png"),
        ("CAM_P2_DESK", "03_desk_close.png"),
    ):
        scene.camera = bpy.data.objects[cam]
        scene.frame_set(1)
        path = STILL_DIR / fname
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        (ARTIFACT / f"part2_detail_{fname}").write_bytes(path.read_bytes())
        print("still", path)
    scene.camera = orig


def main():
    if Path(bpy.data.filepath).resolve() == PART1.resolve():
        raise SystemExit("refusing hallway.blend")
    rebuild_dust_mat()
    flatten_dust_mesh()
    render_hero()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    shutil.copy2(BLEND, CHECKPOINT)
    shutil.copy2(BLEND, ARTIFACT / "part2_basement.blend")
    print("saved", BLEND.stat().st_size)
    print("done")


if __name__ == "__main__":
    main()
