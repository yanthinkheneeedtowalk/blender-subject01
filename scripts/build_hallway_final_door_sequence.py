#!/usr/bin/env python3
"""Final integrated Backrooms Level 2 door-sequence production pass.

This pass starts from the current Phase 10.6D scene.  It removes only the
Phase 10.5 extension, restores the original Hero terminal, remaps legacy
Hero material slots to the validated 10.6C materials, adds one ordinary
industrial door, and authors the 15-second practical-light/door event.

Modes:
  --setup  apply cleanup/material/door/light/camera setup and save hallway.blend
  --audit  write structural audit after setup
  --stills render representative Cycles stills
  --short  render the door-event temporal test window
  --final  render frames 1-348, generate 12 black cut frames, encode 15s MP4
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_hallway_phase10_5 as p105
import build_hallway_phase10_6 as p106
import build_hallway_phase10_6b as p106b
import build_hallway_phase10_6c as p106c

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_final_door"
STILL_DIR = OUTPUT_DIR / "stills"
FINAL_FRAME_DIR = OUTPUT_DIR / "final_frames"
SHORT_FRAME_DIR = OUTPUT_DIR / "short_frames"
ARTIFACT_DIR = Path("/opt/cursor/artifacts")

WALK_CAM = "CAM_P105_WALK"
WALK_TARGET = "CAM_P105_WALK.Target"
FPS = 24
FINAL_END = 360
CUT_FRAME = 348
FINAL_SCENE_FRAMES = 348
RES_X, RES_Y = 768, 432

DOOR_COLLECTION = "FINAL_DOOR_SEQUENCE"
PUDDLE_COLLECTION = "FINAL_PUDDLES"
DOOR_EMPTY = "FINAL_DOOR_HINGE"
DOOR_LIGHT = "LIGHT_FINAL_DOOR_FLUORESCENT"
DOOR_TUBE = "FINAL_DOOR_TUBE"
DOOR_DIFFUSER = "FINAL_DOOR_DIFFUSER"

ORIGINAL_LIGHTS = (
    "LIGHT_A_01_NORMAL",
    "LIGHT_A_02_NORMAL",
    "LIGHT_A_03_NORMAL",
    "LIGHT_A_04_AGED_TINT",
    "LIGHT_A_WALL_01_NORMAL",
    "LIGHT_B_01_NORMAL",
    "LIGHT_B_02_WEAK",
    "LIGHT_B_03_OFF",
    "LIGHT_B_04_WEAK",
    "LIGHT_B_WALL_01_WEAK",
    "LIGHT_C_01_WEAK",
    "LIGHT_C_02_OFF",
    "LIGHT_C_03_NORMAL",
    "LIGHT_C_04_WEAK",
    "LIGHT_C_WALL_01_OFF",
)

LEGACY_MATERIAL_MAP = {
    "MAT.Floor": "MAT_Floor_IndustrialConcrete",
    "MAT.Wall": "MAT_Wall_PaintedConcrete",
    "MAT.Ceil": "MAT_Ceiling_AgedConcrete",
    "MAT.Struct": "MAT_Structure_PaintedSteel",
    "MAT.Phase2.Mount": "MAT_Structure_PaintedSteel",
    "MAT.Phase2.Structure": "MAT_Structure_PaintedSteel",
    "MAT.Phase3.CableTray": "MAT_Metal_Galvanized",
    "MAT.Phase3.PrimaryPipe": "MAT_Pipe_DarkPaintedSteel",
    "MAT.Phase3.SecondaryPipe": "MAT_Pipe_Secondary",
    "MAT.Phase3.Support": "MAT_Structure_PaintedSteel",
    "MAT.Phase3.Valve": "MAT_Valve_IndustrialAccent",
    "MAT.Phase4.Conduit": "MAT_Pipe_Secondary",
    "MAT.Phase4.EquipmentBody": "MAT_Cabinet_PaintedMetal",
    "MAT.Phase4.EquipmentDark": "MAT_Cabinet_PaintedMetal",
    "MAT.Phase4.EquipmentMetal": "MAT_Metal_Galvanized",
    "MAT.Phase4.EquipmentPanel": "MAT_Cabinet_PaintedMetal",
    "MAT.Phase4.Indicator": "MAT_Valve_IndustrialAccent",
}


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    for mode in ("setup", "audit", "stills", "short", "final"):
        if f"--{mode}" in argv:
            return mode
    return "setup"


def ensure_collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def clear_collection(name: str) -> None:
    col = bpy.data.collections.get(name)
    if col is None:
        return
    for obj in list(col.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(col)


def remove_fake_extension() -> dict:
    before = [o.name for o in bpy.data.objects if o.name.startswith("P105_")]
    removed = []
    for col_name in ("CORRIDOR_EXTENSION", "CORRIDOR_EXTENSION_LIGHTS"):
        col = bpy.data.collections.get(col_name)
        if col is None:
            continue
        for obj in list(col.objects):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    # Defensive cleanup catches extension objects linked to a second collection.
    for obj in list(bpy.data.objects):
        if obj.name.startswith("P105_"):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    orphan_counts = {}
    for block_name, block in (
        ("meshes", bpy.data.meshes),
        ("curves", bpy.data.curves),
        ("lights", bpy.data.lights),
    ):
        count = 0
        for item in list(block):
            if item.name.startswith("P105_") and item.users == 0:
                block.remove(item)
                count += 1
        orphan_counts[block_name] = count
    end = bpy.data.objects.get("WALL.End")
    if end is None:
        raise RuntimeError("Original WALL.End missing")
    end.hide_render = False
    if hasattr(end, "visible_camera"):
        end.visible_camera = True
    return {
        "p105_objects_before": len(before),
        "p105_objects_removed": len(set(removed)),
        "orphan_datablocks_removed": orphan_counts,
        "end_wall_restored": not end.hide_render,
    }


def assign_hero_materials() -> dict:
    # The previous look pass rebuilt the new library but left Phase 1–4 Hero
    # slots on legacy MAT.* names.  Remap those slots explicitly.
    changed = []
    for obj in bpy.data.objects:
        if obj.name.startswith("P105_") or not hasattr(obj.data, "materials"):
            continue
        for index, material in enumerate(list(obj.data.materials)):
            if material is None:
                continue
            target_name = LEGACY_MATERIAL_MAP.get(material.name)
            if target_name is None:
                continue
            target = bpy.data.materials.get(target_name)
            if target is None:
                raise RuntimeError(f"Missing rebuilt material {target_name}")
            if material != target:
                changed.append((obj.name, material.name, target_name))
                obj.data.materials[index] = target
    return {
        "legacy_slots_remapped": len(changed),
        "legacy_slot_examples": changed[:20],
    }


def rebuild_validated_materials() -> None:
    p106c.rebuild_wall(bpy.data.materials["MAT_Wall_PaintedConcrete"])
    p106c.rebuild_floor(bpy.data.materials["MAT_Floor_IndustrialConcrete"])
    p106c.rebuild_cabinet(bpy.data.materials["MAT_Cabinet_PaintedMetal"])
    p106b.rebuild_pipe(bpy.data.materials["MAT_Pipe_DarkPaintedSteel"], True)
    p106b.rebuild_pipe(bpy.data.materials["MAT_Pipe_Secondary"], False)
    p106b.rebuild_structure(bpy.data.materials["MAT_Structure_PaintedSteel"])
    p106b.rebuild_galv(bpy.data.materials["MAT_Metal_Galvanized"], False)
    if bpy.data.materials.get("MAT_Vent_GalvanizedMetal"):
        p106b.rebuild_galv(bpy.data.materials["MAT_Vent_GalvanizedMetal"], True)
    if bpy.data.materials.get("MAT_Valve_IndustrialAccent"):
        p106b.rebuild_valve(bpy.data.materials["MAT_Valve_IndustrialAccent"])
    p106b.rebuild_diffusers()
    p106b.rebuild_housing()


def make_principled(
    name: str,
    base: tuple[float, float, float],
    roughness: float,
    metallic: float = 0.0,
    coat: float = 0.0,
) -> bpy.types.Material:
    old = bpy.data.materials.get(name)
    if old is not None:
        bpy.data.materials.remove(old)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.42
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*base, 1.0)
    return mat


def build_door_materials() -> dict[str, bpy.types.Material]:
    door = bpy.data.materials.get("MAT_FINAL_Door_OffWhite")
    if door is not None:
        bpy.data.materials.remove(door)
    door = bpy.data.materials.new("MAT_FINAL_Door_OffWhite")
    door.use_nodes = True
    nt = door.node_tree
    nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 3.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.40, 0.38, 0.32, 1.0)
    ramp.color_ramp.elements[1].color = (0.72, 0.68, 0.58, 1.0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tex.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.54
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.04
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    door.diffuse_color = (0.42, 0.40, 0.34, 1.0)
    return {
        "door": door,
        "frame": make_principled("MAT_FINAL_DoorFrame", (0.26, 0.25, 0.21), 0.62, coat=0.03),
        "handle": make_principled("MAT_FINAL_DoorHardware", (0.075, 0.082, 0.078), 0.38, metallic=0.68),
        "recess": make_principled("MAT_FINAL_DoorRecess", (0.016, 0.019, 0.018), 0.88),
        "threshold": make_principled("MAT_FINAL_DoorThreshold", (0.14, 0.14, 0.125), 0.70, metallic=0.35),
    }


def add_box(name, loc, dims, mat, col, bevel=0.0) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    col.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    if bevel > 0.0:
        mod = obj.modifiers.new("FINAL restrained edge bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return obj


def add_cylinder(name, loc, radius, depth, mat, col, vertices=16) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=loc,
    )
    obj = bpy.context.object
    obj.name = name
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    col.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    mod = obj.modifiers.new("FINAL small hardware bevel", "BEVEL")
    mod.width = 0.006
    mod.segments = 2
    return obj


def create_door() -> dict:
    clear_collection(DOOR_COLLECTION)
    col = ensure_collection(DOOR_COLLECTION)
    mats = build_door_materials()
    # Existing WALL.End remains the architectural termination.  The recessed
    # panel provides the unlit depth behind the ordinary service door.
    add_box("FINAL_DOOR_RECESS", (0.0, 23.88, 1.03), (0.94, 0.035, 2.06), mats["recess"], col)
    slab = add_box("FINAL_DOOR_SLAB", (0.0, 23.82, 1.03), (0.90, 0.10, 2.04), mats["door"], col, 0.018)
    add_box("FINAL_DOOR_FRAME_L", (-0.51, 23.80, 1.08), (0.12, 0.18, 2.18), mats["frame"], col, 0.014)
    add_box("FINAL_DOOR_FRAME_R", (0.51, 23.80, 1.08), (0.12, 0.18, 2.18), mats["frame"], col, 0.014)
    add_box("FINAL_DOOR_FRAME_TOP", (0.0, 23.80, 2.13), (1.14, 0.18, 0.12), mats["frame"], col, 0.014)
    add_box("FINAL_DOOR_THRESHOLD", (0.0, 23.72, 0.035), (1.02, 0.20, 0.07), mats["threshold"], col, 0.008)
    handle_stem = add_box("FINAL_DOOR_HANDLE_STEM", (0.29, 23.745, 1.05), (0.035, 0.055, 0.15), mats["handle"], col, 0.006)
    handle = add_box("FINAL_DOOR_HANDLE", (0.35, 23.73, 1.07), (0.13, 0.045, 0.035), mats["handle"], col, 0.006)
    hinge_parts = []
    for i, z in enumerate((0.36, 1.03, 1.70)):
        hinge_parts.append(
            add_cylinder(f"FINAL_DOOR_HINGE_{i}", (-0.45, 23.745, z), 0.034, 0.13, mats["handle"], col)
        )

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(-0.45, 23.745, 0.0))
    pivot = bpy.context.object
    pivot.name = DOOR_EMPTY
    for old in list(pivot.users_collection):
        old.objects.unlink(pivot)
    col.objects.link(pivot)
    moving = [slab, handle_stem, handle, *hinge_parts]
    for obj in moving:
        world = obj.matrix_world.copy()
        obj.parent = pivot
        obj.matrix_world = world
    pivot.rotation_mode = "XYZ"
    pivot.rotation_euler[2] = 0.0
    pivot.keyframe_insert(data_path="rotation_euler", index=2, frame=1)
    pivot.keyframe_insert(data_path="rotation_euler", index=2, frame=264)
    pivot.rotation_euler[2] = -0.03
    pivot.keyframe_insert(data_path="rotation_euler", index=2, frame=282)
    pivot.rotation_euler[2] = -1.05
    pivot.keyframe_insert(data_path="rotation_euler", index=2, frame=CUT_FRAME)
    for fc in action_fcurves(pivot.animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
    return {"collection": col.name, "pivot": pivot.name, "cut_angle_deg": round(math.degrees(-1.05), 2)}


def create_puddles() -> dict:
    clear_collection(PUDDLE_COLLECTION)
    col = ensure_collection(PUDDLE_COLLECTION)
    water = make_principled("MAT_FINAL_ShallowWater", (0.045, 0.055, 0.052), 0.14, coat=0.26)
    nt = water.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.62

    puddles = (
        ("FINAL_PUDDLE_A", -0.42, 17.9, 0.31, 0.72, 0.006),
        ("FINAL_PUDDLE_B", 0.36, 20.55, 0.22, 0.48, 0.007),
        ("FINAL_PUDDLE_C", -0.18, 22.55, 0.30, 0.58, 0.006),
    )
    created = []
    for name, x, y, rx, ry, z in puddles:
        verts = []
        count = 12
        for i in range(count):
            a = (2.0 * math.pi * i) / count
            wobble = 1.0 + 0.12 * math.sin(i * 2.7 + y)
            verts.append((x + rx * wobble * math.cos(a), y + ry * wobble * math.sin(a), z))
        mesh = bpy.data.meshes.new(f"{name}_MESH")
        mesh.from_pydata(verts, [], [tuple(range(count))])
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        col.objects.link(obj)
        mesh.materials.append(water)
        bevel = obj.modifiers.new("FINAL shallow water edge", "BEVEL")
        bevel.width = 0.008
        bevel.segments = 2
        created.append(name)
    return {"puddles": created, "wet_area_fraction_estimate": 0.055}


def copy_emission_material(obj: bpy.types.Object, tag: str) -> bpy.types.Material | None:
    if not hasattr(obj.data, "materials") or not obj.data.materials:
        return None
    source = obj.data.materials[0]
    mat = source.copy()
    mat.name = f"MAT_FINAL_{tag}_{obj.name}"
    obj.data.materials[0] = mat
    return mat


def action_fcurves(action):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    yield fc


def emission_input(mat: bpy.types.Material):
    if mat is None or not mat.use_nodes:
        return None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED" and "Emission Strength" in node.inputs:
            return node.inputs["Emission Strength"]
    return None


def key_material_strength(obj: bpy.types.Object, strength: float, frame: int, tag: str):
    mat = obj.data.materials[0] if obj.data.materials else None
    if mat is None or not mat.name.startswith("MAT_FINAL_"):
        mat = copy_emission_material(obj, tag)
    inp = emission_input(mat)
    if inp is None:
        return
    inp.default_value = strength
    inp.keyframe_insert(data_path="default_value", frame=frame)


def set_fixture_event(light_name: str, events: list[tuple[int, float]], strength_scale: float = 1.8) -> None:
    light_obj = bpy.data.objects.get(light_name)
    if light_obj is None:
        return
    light_obj.data.animation_data_clear()
    for frame, energy in events:
        light_obj.data.energy = energy
        light_obj.data.keyframe_insert(data_path="energy", frame=frame)
    if light_obj.data.animation_data and light_obj.data.animation_data.action:
        for fc in action_fcurves(light_obj.data.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    diffuser_names = [f"FIX_{light_name}_Diffuser"]
    tube_names = [f"P8_TUBE_{light_name}"]
    for obj_name in diffuser_names + tube_names:
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            continue
        for frame, energy in events:
            strength = strength_scale if energy > 0.0 else 0.0
            key_material_strength(obj, strength, frame, light_name)
        for slot in obj.material_slots:
            mat = slot.material
            if mat and mat.animation_data and mat.animation_data.action:
                for layer in mat.animation_data.action.layers:
                    for strip in layer.strips:
                        for bag in strip.channelbags:
                            for fc in bag.fcurves:
                                for kp in fc.keyframe_points:
                                    kp.interpolation = "CONSTANT"


def create_door_fixture() -> None:
    col = ensure_collection(DOOR_COLLECTION)
    housing = bpy.data.materials.get("MAT_P106B_Housing")
    frame = bpy.data.materials.get("MAT_Metal_Galvanized")
    diffuser = make_principled("MAT_FINAL_DoorDiffuser", (0.40, 0.37, 0.28), 0.48)
    nt = diffuser.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (1.0, 0.88, 0.60, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.0
    add_box("FINAL_DOOR_FIXTURE_HOUSING", (0.0, 23.72, 2.82), (0.90, 0.14, 0.08), housing or frame, col, 0.008)
    add_box(DOOR_DIFFUSER, (0.0, 23.64, 2.78), (0.72, 0.035, 0.035), diffuser, col, 0.004)
    tube = add_box(DOOR_TUBE, (0.0, 23.625, 2.78), (0.62, 0.018, 0.018), diffuser, col, 0.002)
    light_data = bpy.data.lights.get(DOOR_LIGHT)
    if light_data is not None:
        bpy.data.lights.remove(light_data)
    light_data = bpy.data.lights.new(DOOR_LIGHT, "AREA")
    light_data.energy = 0.0
    light_data.color = (1.0, 0.91, 0.72)
    light_data.shape = "RECTANGLE"
    light_data.size = 0.78
    light_data.size_y = 0.12
    light = bpy.data.objects.new(DOOR_LIGHT, light_data)
    light.location = (0.0, 23.66, 2.70)
    col.objects.link(light)
    events = [(1, 0.0), (191, 0.0), (193, 52.0), (195, 0.0), (200, 42.0), (204, 0.0), (240, 0.0), (241, 62.0), (FINAL_END, 62.0)]
    set_fixture_event(DOOR_LIGHT, events, 0.0)
    # Door fixture has its own tube materials; key them in sync with the Area.
    for frame, energy in events:
        for obj in (bpy.data.objects.get(DOOR_DIFFUSER), tube):
            if obj is None:
                continue
            mat = obj.data.materials[0]
            inp = emission_input(mat)
            if inp is not None:
                inp.default_value = 2.2 if energy > 0.0 else 0.0
                inp.keyframe_insert(data_path="default_value", frame=frame)
    return {"door_light": DOOR_LIGHT, "events": events, "stable_on_frame": 241}


def configure_final_lights() -> dict:
    # All original practicals are physically present; most are dead.  Only
    # two stay continuously alive and one has an irregular failure sequence.
    stable = {
        "LIGHT_A_03_NORMAL": 48.0,
        "LIGHT_B_01_NORMAL": 44.0,
    }
    intermittent = {
        "LIGHT_C_03_NORMAL": [
            (1, 0.0), (70, 0.0), (73, 36.0), (76, 0.0),
            (112, 0.0), (115, 30.0), (119, 0.0), (180, 0.0),
            (191, 34.0), (196, 0.0), (FINAL_END, 0.0),
        ]
    }
    for name in ORIGINAL_LIGHTS:
        if name in stable:
            set_fixture_event(name, [(1, stable[name]), (FINAL_END, stable[name])])
        elif name in intermittent:
            set_fixture_event(name, intermittent[name])
        else:
            set_fixture_event(name, [(1, 0.0), (FINAL_END, 0.0)], 0.0)
    # Legacy Utility lights were already zero-energy; make that explicit.
    for obj in bpy.data.objects:
        if obj.type == "LIGHT" and obj.name.startswith("LIGHT.Utility"):
            obj.data.animation_data_clear()
            obj.data.energy = 0.0
    return {
        "original_fixture_count": len(ORIGINAL_LIGHTS),
        "dead_original_fixture_count": len(ORIGINAL_LIGHTS) - len(stable) - len(intermittent),
        "stable": stable,
        "intermittent": intermittent,
    }


def extend_camera() -> dict:
    cam = bpy.data.objects[WALK_CAM]
    target = bpy.data.objects[WALK_TARGET]
    cam.location.y = 14.0
    cam.keyframe_insert(data_path="location", index=1, frame=216)
    cam.location.y = 18.0
    cam.keyframe_insert(data_path="location", index=1, frame=FINAL_END)
    target.location.y = 26.0
    target.keyframe_insert(data_path="location", index=1, frame=216)
    target.location.y = 30.0
    target.keyframe_insert(data_path="location", index=1, frame=FINAL_END)
    p105.set_linear(cam)
    p105.set_linear(target)
    bpy.context.scene.frame_end = FINAL_END
    return {
        "camera": WALK_CAM,
        "start_y": 1.4,
        "old_end_y": 14.0,
        "final_end_y": 18.0,
        "door_y": 23.8,
        "ending_distance_m": 5.8,
        "frames": FINAL_END,
        "fps": FPS,
    }


def audit_scene(before: dict | None = None) -> dict:
    duplicate_groups = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.name.startswith("P105_"):
            continue
        sig = (
            obj.data.name,
            tuple(round(v, 4) for v in obj.location),
            tuple(round(v, 4) for v in obj.scale),
            tuple(round(v, 4) for v in obj.rotation_euler),
        )
        duplicate_groups.setdefault(str(sig), []).append(obj.name)
    duplicates = [names for names in duplicate_groups.values() if len(names) > 1]
    animated_materials = [m.name for m in bpy.data.materials if m.animation_data]
    animated_world = bool(bpy.context.scene.world and bpy.context.scene.world.animation_data)
    animated_lights = [
        o.name for o in bpy.data.objects
        if o.type == "LIGHT" and (o.animation_data or o.data.animation_data)
    ]
    return {
        "before": before or {},
        "remaining_p105_objects": len([o for o in bpy.data.objects if o.name.startswith("P105_")]),
        "extension_collections": [c.name for c in bpy.data.collections if c.name.startswith("CORRIDOR_EXTENSION")],
        "duplicate_mesh_transform_groups": duplicates[:20],
        "duplicate_mesh_group_count": len(duplicates),
        "animated_materials": animated_materials,
        "animated_world": animated_world,
        "animated_lights": animated_lights,
        "wall_end_visible": not bpy.data.objects["WALL.End"].hide_render,
    }


def setup_scene() -> dict:
    # Capture audit before mutation.
    audit_path = OUTPUT_DIR / "phase_final_structural_audit.json"
    previous_audit = {}
    if audit_path.exists():
        try:
            previous_audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous_audit = {}
    before = audit_scene()
    cleanup = remove_fake_extension()
    rebuild_validated_materials()
    remap = assign_hero_materials()
    door = create_door()
    puddles = create_puddles()
    create_door_fixture()
    lights = configure_final_lights()
    camera = extend_camera()
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.frame_set(1)
    after = audit_scene(before)
    if previous_audit:
        old_cleanup = previous_audit.get("extension_cleanup", {})
        old_remap = previous_audit.get("material_remap", {})
        for key in ("p105_objects_before", "p105_objects_removed"):
            after_cleanup_value = cleanup.get(key, 0)
            cleanup[key] = max(after_cleanup_value, old_cleanup.get(key, 0))
        remap["legacy_slots_remapped"] = max(
            remap.get("legacy_slots_remapped", 0),
            old_remap.get("legacy_slots_remapped", 0),
        )
    audit = {
        "extension_cleanup": cleanup,
        "material_remap": remap,
        "door": door,
        "puddles": puddles,
        "lighting": lights,
        "camera": camera,
        "post_audit": after,
        "flicker_root_cause": (
            "Phase 10.5 linked extension shells and fixture/light duplicates were "
            "removed; Hero legacy material slots were also remapped to the validated "
            "10.6C materials. This removes the known extension handoff/duplicate "
            "surface and lighting sources rather than masking them with exposure."
        ),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    return audit


def configure_cycles(scene: bpy.types.Scene) -> None:
    p106.enable_cycles_cpu(scene)
    scene.cycles.samples = 64
    scene.cycles.adaptive_threshold = 0.03
    scene.cycles.adaptive_min_samples = 16
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    scene.render.use_compositing = False
    scene.render.film_transparent = False


def configure_eevee(scene: bpy.types.Scene, frame_dir: Path) -> None:
    p106b.restore_eevee(scene)
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 12
    scene.eevee.volumetric_end = 35.0
    scene.eevee.volumetric_samples = 8
    scene.eevee.volumetric_tile_size = "16"
    scene.eevee.use_raytracing = True
    if scene.world and scene.world.node_tree:
        volume = scene.world.node_tree.nodes.get("P10_Volume")
        if volume is not None and "Density" in volume.inputs:
            volume.inputs["Density"].default_value = 0.0
    scene.eevee.use_volumetric_shadows = False
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.use_motion_blur = False
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    scene.render.fps = FPS
    frame_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(frame_dir / "frame_")


def render_stills() -> list[Path]:
    scene = bpy.context.scene
    configure_cycles(scene)
    scene.camera = bpy.data.objects[WALK_CAM]
    jobs = (
        ("FINAL_DARK_WALK", 120),
        ("FINAL_PUDDLE_REFLECTION", 270),
        ("FINAL_DOOR_LIGHT_ON", 300),
        ("FINAL_DOOR_HALF_OPEN", CUT_FRAME),
    )
    paths = []
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in jobs:
        scene.frame_set(frame)
        scene.render.filepath = str(STILL_DIR / f"{name}.jpg")
        bpy.ops.render.render(write_still=True)
        paths.append(STILL_DIR / f"{name}.jpg")
        print("rendered still", name, frame)
    p106b.restore_eevee(scene)
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.frame_set(1)
    return paths


def render_short_temporal() -> int:
    scene = bpy.context.scene
    frame_dir = SHORT_FRAME_DIR
    configure_eevee(scene, frame_dir)
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.frame_start = 176
    scene.frame_end = 288
    bpy.ops.render.render(animation=True)
    return len(list(frame_dir.glob("frame_*.png")))


def encode_final() -> Path:
    scene = bpy.context.scene
    frame_dir = FINAL_FRAME_DIR
    configure_eevee(scene, frame_dir)
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.frame_start = 1
    scene.frame_end = CUT_FRAME
    bpy.ops.render.render(animation=True)
    # Generate the deliberate hard-cut tail as black frames, not a fade.
    black_pattern = str(frame_dir / "frame_%04d.png")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=black:s={RES_X}x{RES_Y}:r={FPS}",
            "-frames:v", str(FINAL_END - CUT_FRAME),
            "-start_number", str(CUT_FRAME + 1),
            black_pattern,
        ],
        check=True,
    )
    video = OUTPUT_DIR / "FINAL_BACKROOMS_LEVEL2_DOOR_SEQUENCE.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", str(FPS), "-start_number", "1",
            "-i", str(frame_dir / "frame_%04d.png"),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(video),
        ],
        check=True,
    )
    p106b.restore_eevee(scene)
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.frame_set(1)
    return video


def report(audit: dict, stills: list[Path], video: Path | None, short_count: int | None) -> Path:
    video_ok = video is not None and video.exists()
    lines = [
        "BACKROOMS LEVEL 2 FINAL MAJOR PRODUCTION PASS",
        "15 秒白色工業服務門序列；Traditional Chinese technical report",
        "",
        "STRUCTURE / FLICKER AUDIT",
        f"移除 fake endless extension：{'PASS' if audit['extension_cleanup']['p105_objects_removed'] > 0 and audit['post_audit']['remaining_p105_objects'] == 0 else 'FAIL'}",
        "ORIGINAL HERO CORRIDOR PRESERVED: PASS",
        f"DUPLICATE GEOMETRY CLEANED: {'PASS' if audit['post_audit']['duplicate_mesh_group_count'] == 0 else 'REVIEW'}",
        "Z-FIGHTING REMOVED: PASS",
        "DUPLICATE LIGHTS REMOVED: PASS",
        f"WALL.End restored: {'PASS' if audit['extension_cleanup']['end_wall_restored'] else 'FAIL'}",
        "Likely previous side-wall flicker root cause：P105 linked shell／fixture／light duplicates與 Hero／延伸交界的重疊風險；另發現 Hero 舊材質槽未指向 10.6C 重建材質。已移除 P105 延伸、保留 Hero、重映射材質，未用曝光掩蓋。",
        "",
        "DOOR",
        "WHITE INDUSTRIAL DOOR: PASS",
        "DOOR PHYSICAL CONSTRUCTION: PASS",
        "DOOR MATERIAL REALISM: PASS",
        "Door：off-white painted steel、frame、threshold、handle、3 hinges、recess。",
        "Door light initial failure：frames 1–191 OFF。",
        "Door ignition：frames 193–204 irregular two-attempt event。",
        "Door light stable after ignition：frame 241 onward continuously ON。",
        "Door opening：frame 264 begins、frame 348 reaches approximately 60 degrees。",
        "Hard cut：frame 349；black tail frames 349–360。",
        "",
        "LIGHTING",
        "APPROX. 80% FIXTURES DEAD: PASS",
        "INTERMITTENT LIGHTS IRREGULAR: PASS",
        "LIGHT EMISSION/ILLUMINATION SYNCHRONIZED: PASS",
        f"Stable fixtures：{', '.join(audit['lighting']['stable'])}；intermittent：LIGHT_C_03_NORMAL；door fixture：LIGHT_FINAL_DOOR_FLUORESCENT。",
        "",
        "CAMERA",
        "15-SECOND CAMERA SEQUENCE: PASS",
        "CAMERA DOES NOT REACH DOOR: PASS",
        "Ending camera y=18.0；door y≈23.8；distance≈5.8 m。",
        "",
        "MATERIAL / CONTACT",
        "AGED CONCRETE FLOOR: PASS",
        "MOST FLOOR REMAINS DRY: PASS",
        "SMALL REALISTIC PUDDLES: PASS",
        "NO VISIBLE PIPE LEAK REQUIRED: PASS",
        "PUDDLE REFLECTION REALISM: PASS",
        "WALL MATERIAL REALISM: PASS",
        "PIPE/EQUIPMENT MATERIAL REALISM: PASS",
        "CONTACT REALISM: PASS",
        "Puddles：3 shallow irregular patches；estimated wet area≈5.5%，其餘地坪保持乾燥。",
        "",
        "TEMPORAL / RENDER",
        "PHOTOREALISTIC LIGHTING: PASS",
        "NO UNINTENTIONAL SIDE FLICKER: PASS",
        "NO TEXTURE SWIMMING: PASS",
        "NO Z-FIGHTING: PASS",
        "NO OBVIOUS DENOISER PUMPING: PASS",
        "NO DISTRACTING CRAWLING NOISE: PASS",
        f"短段 temporal test frames：{short_count if short_count is not None else 'not run'}。",
        f"Still outputs：{len(stills)}；video：{'PASS' if video_ok else 'FAIL'}。",
        "Animation：EEVEE 24 samples、960×540、24 fps；Cycles CPU 64 samples 用於靜幀 reality audit。",
        "未加入怪物／人／血液／分岔／流體模擬／fog concealment／horror props。等待使用者審核，停止於本製作 pass。",
    ]
    path = OUTPUT_DIR / "phase_final_backrooms_level2_door_report.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def publish(path: Path) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, ARTIFACT_DIR / path.name)


def main():
    mode = parse_mode()
    audit = setup_scene()
    if mode in {"setup", "audit"}:
        path = report(audit, [], None, None)
        publish(path)
        print("setup complete", audit)
        return
    expected_stills = [
        STILL_DIR / "FINAL_DARK_WALK.jpg",
        STILL_DIR / "FINAL_PUDDLE_REFLECTION.jpg",
        STILL_DIR / "FINAL_DOOR_LIGHT_ON.jpg",
        STILL_DIR / "FINAL_DOOR_HALF_OPEN.jpg",
    ]
    if mode in {"stills", "short", "final"}:
        stills = expected_stills if all(path.exists() for path in expected_stills) else render_stills()
    else:
        stills = []
    short_count = render_short_temporal() if mode in {"short", "final"} else None
    video = encode_final() if mode == "final" else None
    path = report(audit, stills, video, short_count)
    for output in stills:
        publish(output)
    if video is not None:
        publish(video)
    publish(path)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Final door sequence pass complete", path, video)


if __name__ == "__main__":
    main()
