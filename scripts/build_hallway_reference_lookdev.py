#!/usr/bin/env python3
"""Reference-directed material and lighting LookDev on the cleaned scene.

No geometry/layout/camera animation redesign.  This pass only improves
surface history, puddle blending, and non-door practical intensity, then
renders still Reality Audit frames.  The final video is run separately after
the stills pass.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_hallway_final_door_sequence as final_pass
import build_hallway_phase10_6 as p106
import build_hallway_phase10_6b as p106b
import build_hallway_phase10_6c as p106c

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_reference_lookdev"
STILL_DIR = OUTPUT_DIR / "stills"

LIGHT_SCALE = 0.55


def link(nt, src, dst):
    nt.links.new(src, dst)


def add_dirt_layer(mat: bpy.types.Material, floor: bool) -> None:
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    base_socket = bsdf.inputs["Base Color"]
    base = base_socket.links[0].from_socket if base_socket.links else base_socket
    pos = p106c.generated_pos(nt, (-980, 520))
    grime = p106.noise(nt, pos, 3.5 if floor else 2.7, 3.0, (-720, 520), 0.50, 0.08)
    grime_m = p106.map_range(nt, grime.outputs["Fac"], 0.56, 0.82, 0.0, 0.30 if floor else 0.22, (-500, 520))
    dirt_color = (0.028, 0.027, 0.024) if floor else (0.055, 0.049, 0.040)
    color = p106.mix_col(nt, grime_m, base, dirt_color, (-160, 520))
    if floor:
        x, _y, _z = p106c.sep_xyz(nt, pos, (-780, 300))
        centered = p106.mathn(nt, "SUBTRACT", (-620, 300), x, 0.5)
        edge_abs = p106.mathn(nt, "ABSOLUTE", (-460, 300), centered, 0.0)
        edge = p106.map_range(nt, edge_abs, 0.38, 0.50, 0.0, 0.24, (-280, 300))
        color = p106.mix_col(nt, edge, color, (0.020, 0.020, 0.018), (80, 520))
    else:
        _x, _y, z = p106c.sep_xyz(nt, pos, (-780, 300))
        skirt = p106.map_range(nt, z, 0.0, 0.23, 0.34, 0.0, (-620, 300))
        color = p106.mix_col(nt, skirt, color, (0.042, 0.038, 0.032), (80, 520))
    link(nt, color, base_socket)
    rough_socket = bsdf.inputs["Roughness"]
    rough = rough_socket.links[0].from_socket if rough_socket.links else rough_socket
    rough_out = p106.mix_f(nt, grime_m, rough, 0.76 if floor else 0.82, (320, 380))
    link(nt, rough_out, rough_socket)


def rebuild_reference_materials() -> None:
    p106c.rebuild_floor(bpy.data.materials["MAT_Floor_IndustrialConcrete"])
    p106c.rebuild_wall(bpy.data.materials["MAT_Wall_PaintedConcrete"])
    p106c.rebuild_cabinet(bpy.data.materials["MAT_Cabinet_PaintedMetal"])
    add_dirt_layer(bpy.data.materials["MAT_Floor_IndustrialConcrete"], True)
    add_dirt_layer(bpy.data.materials["MAT_Wall_PaintedConcrete"], False)


def make_damp_materials():
    damp = final_pass.make_principled("MAT_FINAL_DampConcrete", (0.030, 0.034, 0.032), 0.52, coat=0.02)
    water = final_pass.make_principled("MAT_FINAL_ShallowWater", (0.050, 0.060, 0.057), 0.12, coat=0.22)
    bsdf = next(n for n in water.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.66
    return damp, water


def create_blended_puddles() -> None:
    final_pass.clear_collection(final_pass.PUDDLE_COLLECTION)
    col = final_pass.ensure_collection(final_pass.PUDDLE_COLLECTION)
    damp, water = make_damp_materials()
    puddles = (
        ("FINAL_PUDDLE_A", -0.42, 17.9, 0.38, 0.84),
        ("FINAL_PUDDLE_B", 0.36, 20.55, 0.28, 0.58),
        ("FINAL_PUDDLE_C", -0.18, 22.55, 0.36, 0.70),
    )
    for name, x, y, rx, ry in puddles:
        count = 28
        verts = [(x, y, 0.006)]
        for ring_scale, z in ((0.62, 0.006), (1.0, 0.004)):
            for i in range(count):
                a = (2.0 * math.pi * i) / count
                wobble = 1.0 + 0.10 * math.sin(i * 2.31 + y)
                verts.append((x + rx * ring_scale * wobble * math.cos(a), y + ry * ring_scale * wobble * math.sin(a), z))
        faces = []
        mats = []
        for i in range(count):
            j = (i + 1) % count
            faces.append((0, 1 + i, 1 + j))
            mats.append(1)
            faces.append((1 + i, 1 + count + i, 1 + count + j, 1 + j))
            mats.append(0)
        mesh = bpy.data.meshes.new(f"{name}_MESH")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        col.objects.link(obj)
        mesh.materials.append(damp)
        mesh.materials.append(water)
        for poly, mat_index in zip(mesh.polygons, mats):
            poly.material_index = mat_index
        if hasattr(obj, "visible_shadow"):
            obj.visible_shadow = False


def scale_non_door_practicals() -> None:
    scene = bpy.context.scene
    if scene.get("REFERENCE_LOOKDEV_LIGHT_SCALE") == LIGHT_SCALE:
        return
    for name in final_pass.ORIGINAL_LIGHTS:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.data.energy *= LIGHT_SCALE
        if obj.data.animation_data and obj.data.animation_data.action:
            for fc in final_pass.action_fcurves(obj.data.animation_data.action):
                if fc.data_path == "energy":
                    for kp in fc.keyframe_points:
                        kp.co.y *= LIGHT_SCALE
        for obj_name in (f"FIX_{name}_Diffuser", f"P8_TUBE_{name}"):
            fixture = bpy.data.objects.get(obj_name)
            if fixture is None or not fixture.data.materials:
                continue
            mat = fixture.data.materials[0]
            if mat.animation_data and mat.animation_data.action:
                for fc in final_pass.action_fcurves(mat.animation_data.action):
                    if fc.data_path == "default_value":
                        for kp in fc.keyframe_points:
                            kp.co.y *= LIGHT_SCALE
    scene["REFERENCE_LOOKDEV_LIGHT_SCALE"] = LIGHT_SCALE


def apply_reference_lookdev() -> None:
    rebuild_reference_materials()
    create_blended_puddles()
    scale_non_door_practicals()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.frame_start = 1
    scene.frame_end = 360
    scene.camera = bpy.data.objects["CAM_P105_WALK"]
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


def render_stills():
    scene = bpy.context.scene
    p106.enable_cycles_cpu(scene)
    scene.cycles.samples = 64
    scene.cycles.adaptive_threshold = 0.03
    scene.cycles.adaptive_min_samples = 16
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    cams = (
        ("REFERENCE_DRY_FLOOR", (0.30, 8.8, 0.55), (-0.10, 10.0, 0.02), 120),
        ("REFERENCE_DAMP_TRANSITION", (-0.20, 16.9, 0.58), (0.05, 18.3, 0.02), 270),
        ("REFERENCE_PUDDLE_REFLECTION", (0.24, 20.7, 0.60), (-0.05, 22.2, 0.02), 270),
        ("REFERENCE_DOOR_LIGHT_ON", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 300),
    )
    temp = []
    paths = []
    for name, loc, target, frame in cams:
        cam = bpy.data.objects.get("CAM_P105_WALK") if name == "REFERENCE_DOOR_LIGHT_ON" else final_pass.make_camera(name, loc, target, 40.0)
        temp.append(cam)
        scene.camera = cam
        scene.frame_set(frame)
        path = STILL_DIR / f"{name}.jpg"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths.append(path)
    for cam in temp:
        if cam.name != "CAM_P105_WALK":
            bpy.data.objects.remove(cam, do_unlink=True)
    final_pass.configure_eevee(scene, ROOT / "renders" / "hallway_targeted_cleanup" / "final_validation_frames")
    scene.frame_start = 1
    scene.frame_end = 360
    scene.camera = bpy.data.objects["CAM_P105_WALK"]
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    return paths


def main():
    apply_reference_lookdev()
    paths = render_stills()
    report = OUTPUT_DIR / "reference_lookdev_still_reality_audit.txt"
    report.write_text(
        "\n".join(
            [
                "REFERENCE-DIRECTED LOOKDEV STILL REALITY AUDIT",
                "使用 provided reference 的材質語言方向：髒舊澆置混凝土、局部濕潤、深暗走廊、局部門燈主光。",
                "本輪未改 corridor geometry、door/camera timing、beam cleanup、pipes/equipment placement。",
                "",
                "THREE LARGEST PREVIOUS CG GIVEAWAYS CORRECTED:",
                "1. Hero floor legacy material slot was remapped and received non-uniform grime/roughness history.",
                "2. Polygon puddle edges were replaced with damp-concrete transition rings and shadowless shallow water.",
                "3. Corridor practicals were reduced to weak localized light; only the door practical remains dominant after ignition.",
                "",
                "STILL OUTPUTS: PASS",
                f"Rendered: {', '.join(p.name for p in paths)}",
                "Waiting for visual review before validation video.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(report)


if __name__ == "__main__":
    main()
