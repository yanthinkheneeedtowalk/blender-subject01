#!/usr/bin/env python3
"""Raise dust opacity so the photo stays unreadable. Renders 01-03 only."""

from pathlib import Path
import bpy

BLEND = Path("/workspace/part2_basement.blend")
PART1 = Path("/workspace/hallway.blend")
STILL_DIR = Path("/workspace/renders/part2_basement/stills")
ARTIFACT = Path("/opt/cursor/artifacts")
CHECKPOINT = Path("/workspace/renders/checkpoints/part2_basement_detail.blend")


def main():
    if Path(bpy.data.filepath).resolve() == PART1.resolve():
        raise SystemExit("refusing hallway.blend")
    mat = bpy.data.materials["MAT_P2_Dust"]
    nt = mat.node_tree
    # Remap noise so it never punches dust alpha to a hole.
    mul = next(n for n in nt.nodes if n.type == "MATH" and n.operation == "MULTIPLY")
    n1 = next(n for n in nt.nodes if n.type == "TEX_NOISE" and abs(n.inputs["Scale"].default_value - 9.0) < 0.1)
    rng = nt.nodes.new("ShaderNodeMapRange")
    rng.inputs["From Min"].default_value = 0.0
    rng.inputs["From Max"].default_value = 1.0
    rng.inputs["To Min"].default_value = 0.72
    rng.inputs["To Max"].default_value = 1.0
    for link in list(nt.links):
        if link.to_node == mul and link.from_node == n1:
            nt.links.remove(link)
    nt.links.new(n1.outputs["Fac"], rng.inputs["Value"])
    # mul input 1 was noise; keep input 0 as colorramp alpha
    nt.links.new(rng.outputs["Result"], mul.inputs[1])

    cr = next(n for n in nt.nodes if n.type == "VALTORGB")
    cr.color_ramp.elements[0].color = (0.30, 0.27, 0.21, 0.70)
    if len(cr.color_ramp.elements) > 2:
        cr.color_ramp.elements[1].color = (0.34, 0.30, 0.24, 0.82)
    cr.color_ramp.elements[-1].color = (0.38, 0.34, 0.27, 0.95)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    orig = scene.camera
    jobs = [
        ("CAM_P2_WIDE", "01_wide.png"),
        ("CAM_P2_SIT", "02_sit_fps.png"),
        ("CAM_P2_DESK", "03_desk_close.png"),
    ]
    for cam, fname in jobs:
        scene.camera = bpy.data.objects[cam]
        scene.frame_set(1)
        path = STILL_DIR / fname
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        (ARTIFACT / f"part2_detail_{fname}").write_bytes(path.read_bytes())
        print("still", path)
    scene.camera = orig
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    import shutil
    shutil.copy2(BLEND, CHECKPOINT)
    shutil.copy2(BLEND, ARTIFACT / "part2_basement.blend")
    print("saved", BLEND.stat().st_size)
    print("done")


if __name__ == "__main__":
    main()
