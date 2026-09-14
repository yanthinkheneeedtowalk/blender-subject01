#!/usr/bin/env python3
"""Phase 7 — final lighting and visibility control.

Adds industrial fluorescent fixtures and motivated area lights over the
frozen Phase 1–6 corridor.  Geometry, materials, aging, camera path, and
zone dimensions are not redesigned.  Phase 1 placeholder lights are
deactivated in place (locations unchanged) and replaced by visible fixtures.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase7.py -- --no-render
  blender -b hallway.blend --python scripts/build_hallway_phase7.py -- --stills
  blender -b hallway.blend --python scripts/build_hallway_phase7.py -- --playblast
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_hallway_phase5 as p5

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase7"
EYE_Z = p5.EYE_Z
ZONE_A = p5.ZONE_A
ZONE_B = p5.ZONE_B
ZONE_C = p5.ZONE_C
PHASE2_COUNTS = p5.PHASE2_COUNTS
PHASE4_COLLECTIONS = p5.PHASE4_COLLECTIONS
LIBRARY = p5.LIBRARY
PHASE1_LIGHTS = tuple(f"LIGHT.Utility.{i:02d}" for i in range(1, 7))
P7_PREFIXES = ("FIX_", "LIGHT_A_", "LIGHT_B_", "LIGHT_C_", "P7_")

STILLS = (
    (1, "01_entry_distance"),
    (42, "02_zone_a_readable"),
    (78, "03_approach_ab"),
    (96, "04_zone_b_unstable"),
    (132, "05_zone_b_shadows"),
    (164, "06_approach_bc"),
    (185, "07_zone_c_isolation"),
    (215, "08_zone_c_uncertainty"),
    (240, "09_far_end_falloff"),
    (250, "10_terminal_silhouette"),
)

# Ceiling strips sit in beam gaps. Lengths vary so the original regular
# facility grid is no longer identical from fixture to fixture.
# state, zone, y, z, length, x, energy_w, color, cutoff, spread
CEILING_FIXTURES = (
    ("LIGHT_A_01_NORMAL", "A", 0.95, 2.78, 0.82, 0.00, 78.0, (0.96, 0.98, 1.00), 6.8, 2.40),
    ("LIGHT_A_02_NORMAL", "A", 2.16, 2.78, 0.58, 0.05, 72.0, (0.97, 0.98, 0.99), 6.6, 2.45),
    ("LIGHT_A_03_NORMAL", "A", 3.50, 2.78, 0.88, -0.04, 80.0, (0.95, 0.98, 1.00), 6.8, 2.35),
    ("LIGHT_A_04_AGED_TINT", "A", 6.18, 2.78, 0.82, 0.03, 64.0, (1.00, 0.96, 0.86), 6.2, 2.30),
    ("LIGHT_B_01_NORMAL", "B", 10.12, 2.575, 0.88, 0.02, 58.0, (0.94, 0.98, 1.00), 5.4, 2.25),
    ("LIGHT_B_02_WEAK", "B", 11.68, 2.575, 0.88, -0.06, 22.0, (0.92, 1.00, 0.84), 5.0, 2.15),
    ("LIGHT_B_03_OFF", "B", 13.22, 2.575, 0.88, 0.04, 0.0, (0.90, 0.92, 0.88), 0.8, 2.20),
    ("LIGHT_B_04_WEAK", "B", 14.58, 2.575, 0.70, -0.02, 18.0, (0.95, 1.00, 0.80), 4.8, 2.10),
    ("LIGHT_C_01_WEAK", "C", 17.22, 2.72, 0.78, 0.05, 20.0, (0.93, 1.00, 0.86), 4.6, 2.20),
    ("LIGHT_C_02_OFF", "C", 18.54, 2.72, 0.82, -0.05, 0.0, (0.90, 0.92, 0.88), 0.8, 2.20),
    ("LIGHT_C_03_NORMAL", "C", 19.90, 2.72, 0.72, 0.03, 48.0, (0.97, 0.98, 0.96), 3.5, 2.30),
    ("LIGHT_C_04_OFF", "C", 21.72, 2.72, 0.90, -0.03, 0.0, (0.90, 0.92, 0.88), 0.8, 2.20),
)

# Wall bulkheads: (name, zone, x, y, z, yaw_y_deg, energy, color, cutoff, state)
# yaw_y_deg 90 points -X (from east wall); -90 points +X (from west wall).
WALL_FIXTURES = (
    ("LIGHT_A_WALL_01_NORMAL", "A", 1.062, 3.22, 2.20, 90.0, 16.0, (0.98, 0.97, 0.94), 3.6, "NORMAL"),
    ("LIGHT_B_WALL_01_WEAK", "B", -0.987, 11.18, 1.96, -90.0, 7.0, (0.94, 1.00, 0.82), 3.0, "WEAK"),
    ("LIGHT_C_WALL_01_OFF", "C", 1.062, 21.48, 2.10, 90.0, 0.0, (0.90, 0.92, 0.88), 0.8, "OFF"),
)


def parse_mode() -> str:
    return p5.parse_mode()


def sock(node, identifier: str):
    return p5.sock(node, identifier)


def link(nt, src, dst) -> None:
    nt.links.new(src, dst)


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def state_of(name: str) -> str:
    if name.endswith("_OFF"):
        return "OFF"
    if name.endswith("_WEAK"):
        return "WEAK"
    if name.endswith("_AGED_TINT"):
        return "AGED_TINT"
    return "NORMAL"


def box_mesh(name: str, dims: tuple[float, float, float]) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=dims)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def assign_mat(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def make_emission_material(
    name: str,
    base: tuple[float, float, float],
    emit: tuple[float, float, float],
    strength: float,
    roughness: float,
) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (360, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (80, 0)
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    else:
        try:
            sock(bsdf, "Emission Color").default_value = (*emit, 1.0)
            sock(bsdf, "Emission Strength").default_value = strength
        except KeyError:
            pass
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*emit, 1.0)
    return mat


def make_housing_material() -> bpy.types.Material:
    existing = bpy.data.materials.get("MAT_Metal_Galvanized")
    if existing is not None:
        return existing
    mat = bpy.data.materials.new("MAT_P7_Housing")
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.38, 0.39, 0.37, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.62
    bsdf.inputs["Roughness"].default_value = 0.48
    return mat


def build_materials() -> dict[str, bpy.types.Material]:
    housing = make_housing_material()
    return {
        "housing": housing,
        "NORMAL": make_emission_material(
            "MAT_P7_Diffuser_Normal",
            (0.72, 0.74, 0.70),
            (0.90, 0.95, 1.00),
            11.0,
            0.42,
        ),
        "AGED_TINT": make_emission_material(
            "MAT_P7_Diffuser_Aged",
            (0.70, 0.68, 0.60),
            (1.00, 0.94, 0.80),
            7.5,
            0.48,
        ),
        "WEAK": make_emission_material(
            "MAT_P7_Diffuser_Weak",
            (0.55, 0.56, 0.48),
            (0.82, 0.92, 0.70),
            2.6,
            0.55,
        ),
        "OFF": make_emission_material(
            "MAT_P7_Diffuser_Off",
            (0.22, 0.23, 0.21),
            (0.18, 0.19, 0.17),
            0.0,
            0.62,
        ),
    }


def clear_phase7() -> None:
    seen = set()
    for name in (
        "LIGHTING_FIXTURES",
        "LIGHTING_ACTIVE",
        "LIGHTING_WEAK",
        "LIGHTING_OFF",
        "LIGHTING_GUIDES",
    ):
        col = bpy.data.collections.get(name)
        if col is None:
            continue
        for obj in list(col.objects):
            if obj.name in seen:
                continue
            seen.add(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    for mat in list(bpy.data.materials):
        if mat.name.startswith("MAT_P7_"):
            bpy.data.materials.remove(mat)
    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith("P7_") and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def deactivate_phase1_lights() -> list[str]:
    """Keep Phase 1 lights in place but remove their contribution."""
    names = []
    for name in PHASE1_LIGHTS:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "LIGHT":
            continue
        obj.data.energy = 0.0
        obj.data.use_shadow = False
        obj.hide_render = True
        obj.hide_viewport = True
        obj["phase7_replaced"] = True
        names.append(name)
    return names


def configure_world(scene: bpy.types.Scene) -> dict:
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("WORLD.Hallway")
        scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is None:
        background = world.node_tree.nodes.new("ShaderNodeBackground")
        out = world.node_tree.nodes.get("World Output")
        if out is not None:
            world.node_tree.links.new(background.outputs["Background"], out.inputs["Surface"])
    # Restrained fill so unlit pockets keep a physical darkness floor.
    background.inputs[0].default_value = (0.028, 0.031, 0.036, 1.0)
    background.inputs[1].default_value = 0.16
    chosen = "Standard"
    for candidate in ("AgX", "Khronos PBR Neutral", "Filmic", "Standard"):
        try:
            scene.view_settings.view_transform = candidate
            chosen = candidate
            break
        except TypeError:
            continue
    look = "None"
    for candidate in ("None", "AgX - Punchy", "Medium Contrast", "None"):
        try:
            scene.view_settings.look = candidate
            look = candidate
            if candidate != "AgX - Punchy":
                break
        except TypeError:
            continue
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    try:
        scene.display_settings.display_device = "sRGB"
    except TypeError:
        pass
    return {
        "view_transform": scene.view_settings.view_transform,
        "look": scene.view_settings.look,
        "exposure": scene.view_settings.exposure,
        "chosen_attempt": chosen,
        "look_attempt": look,
        "world_strength": background.inputs[1].default_value,
        "world_color": tuple(round(v, 3) for v in background.inputs[0].default_value[:3]),
    }


def configure_eevee(scene: bpy.types.Scene, samples: int) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    scene.eevee.taa_render_samples = samples
    scene.eevee.use_shadows = True
    scene.eevee.use_raytracing = False
    scene.eevee.use_fast_gi = True
    scene.eevee.fast_gi_method = "GLOBAL_ILLUMINATION"
    scene.eevee.fast_gi_quality = 0.40
    scene.eevee.fast_gi_ray_count = 10
    scene.eevee.clamp_surface_indirect = 1.15
    scene.eevee.indirect_light_intensity = 0.78
    scene.eevee.use_volumetric_shadows = False
    scene.eevee.shadow_ray_count = 2
    scene.eevee.shadow_step_count = 8
    scene.eevee.shadow_resolution_scale = 1.0


def add_object(name: str, mesh: bpy.types.Mesh, loc, col, mat, scale=(1.0, 1.0, 1.0), rot=(0.0, 0.0, 0.0)):
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.scale = scale
    obj.rotation_euler = rot
    obj["phase"] = 7
    assign_mat(obj, mat)
    col.objects.link(obj)
    return obj


def add_area_light(
    name: str,
    loc,
    rot,
    size_x: float,
    size_y: float,
    energy: float,
    color,
    cutoff: float,
    spread: float,
    state: str,
    zone: str,
) -> bpy.types.Object:
    data = bpy.data.lights.new(name, "AREA")
    data.shape = "RECTANGLE"
    data.size = size_x
    data.size_y = size_y
    data.energy = energy
    data.color = color
    data.normalize = True
    data.spread = spread
    data.specular_factor = 0.85
    data.use_custom_distance = True
    data.cutoff_distance = cutoff
    data.use_shadow = energy > 0.0
    data.shadow_filter_radius = 1.6 if state == "WEAK" else 1.1
    data.shadow_maximum_resolution = 0.0025 if zone == "A" else 0.0035
    obj = bpy.data.objects.new(name, data)
    obj.location = loc
    obj.rotation_euler = rot
    obj["phase"] = 7
    obj["state"] = state
    obj["zone"] = zone
    dest = {
        "OFF": "LIGHTING_OFF",
        "WEAK": "LIGHTING_WEAK",
        "AGED_TINT": "LIGHTING_ACTIVE",
        "NORMAL": "LIGHTING_ACTIVE",
    }[state]
    collection(dest).objects.link(obj)
    return obj


def build_ceiling_fixtures(mats: dict[str, bpy.types.Material]) -> list[str]:
    housing_mesh = box_mesh("P7_STRIP_HOUSING", (0.13, 1.0, 0.048))
    diffuser_mesh = box_mesh("P7_STRIP_DIFFUSER", (0.088, 0.92, 0.012))
    cap_mesh = box_mesh("P7_STRIP_CAP", (0.138, 0.028, 0.052))
    stem_mesh = box_mesh("P7_STRIP_STEM", (0.018, 0.018, 0.10))
    fix_col = collection("LIGHTING_FIXTURES")
    names = []
    for name, zone, y, z, length, x, energy, color, cutoff, spread in CEILING_FIXTURES:
        state = state_of(name)
        housing_z = z + 0.028
        stem_len = {"A": 0.14, "B": 0.07, "C": 0.12}[zone]
        stem_z = housing_z + 0.024 + stem_len * 0.5
        add_object(
            f"FIX_{name}_Housing",
            housing_mesh,
            (x, y, housing_z),
            fix_col,
            mats["housing"],
            scale=(1.0, length, 1.0),
        )
        add_object(
            f"FIX_{name}_Diffuser",
            diffuser_mesh,
            (x, y, z + 0.004),
            fix_col,
            mats[state],
            scale=(1.0, length, 1.0),
        )
        for side, sy in (("N", y + length * 0.48), ("S", y - length * 0.48)):
            add_object(
                f"FIX_{name}_Cap_{side}",
                cap_mesh,
                (x, sy, housing_z),
                fix_col,
                mats["housing"],
            )
            add_object(
                f"FIX_{name}_Stem_{side}",
                stem_mesh,
                (x, sy, stem_z),
                fix_col,
                mats["housing"],
                scale=(1.0, 1.0, stem_len / 0.10),
            )
        add_area_light(
            name,
            (x, y, z - 0.018),
            (0.0, 0.0, 0.0),
            0.09,
            length * 0.90,
            energy,
            color,
            cutoff,
            spread,
            state,
            zone,
        )
        names.append(name)
    return names


def build_wall_fixtures(mats: dict[str, bpy.types.Material]) -> list[str]:
    housing_mesh = box_mesh("P7_WALL_HOUSING", (0.07, 0.20, 0.12))
    diffuser_mesh = box_mesh("P7_WALL_DIFFUSER", (0.012, 0.16, 0.085))
    fix_col = collection("LIGHTING_FIXTURES")
    names = []
    for name, zone, x, y, z, yaw, energy, color, cutoff, state in WALL_FIXTURES:
        rot = (0.0, 0.0, 0.0)
        add_object(f"FIX_{name}_Housing", housing_mesh, (x, y, z), fix_col, mats["housing"])
        inward = -0.042 if yaw > 0 else 0.042
        add_object(
            f"FIX_{name}_Diffuser",
            diffuser_mesh,
            (x + inward, y, z),
            fix_col,
            mats[state],
        )
        light_x = x + inward * 1.6
        add_area_light(
            name,
            (light_x, y, z),
            (0.0, math.radians(yaw), 0.0),
            0.085,
            0.16,
            energy,
            color,
            cutoff,
            2.05,
            state,
            zone,
        )
        names.append(name)
    return names


def p7_objects() -> list[bpy.types.Object]:
    return [
        obj
        for obj in bpy.data.objects
        if obj.name.startswith(P7_PREFIXES) or obj.name.startswith("FIX_")
    ]


def validate(scene, before, legacy_lights) -> dict:
    after = p5.snapshot()
    original = {
        k: v
        for k, v in before.items()
        if not k.startswith(P7_PREFIXES) and not k.startswith("FIX_")
    }
    after_core = {
        k: v
        for k, v in after.items()
        if not k.startswith(P7_PREFIXES) and not k.startswith("FIX_")
    }
    moved = [name for name, row in original.items() if after_core.get(name) != row]
    removed = sorted(set(original) - set(after_core))
    added_core = sorted(set(after_core) - set(original))
    camera = bpy.data.objects["CAM_INSPECT"]
    camera_errors = []
    for frame in range(1, 251, 8):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        position = camera.matrix_world.translation.copy()
        if abs(position.x) > 0.01 or abs(position.z - EYE_Z) > 0.01:
            camera_errors.append((frame, tuple(round(v, 3) for v in position)))
    p4_objects = [
        obj
        for name in PHASE4_COLLECTIONS
        if bpy.data.collections.get(name)
        for obj in bpy.data.collections[name].objects
    ]
    extra = p7_objects()
    markings = [
        obj
        for obj in bpy.data.objects
        if obj.name.startswith("MARK_")
    ]
    hidden_states = {obj.name: obj.hide_get() for obj in p4_objects + extra + markings}
    for obj in p4_objects + extra + markings:
        obj.hide_set(True)
    bpy.context.view_layer.update()
    stations = []
    for label, y, width, height in (
        ("A clear", 3.25, ZONE_A["width"], ZONE_A["height"]),
        ("B clear", 11.75, ZONE_B["width"], ZONE_B["height"]),
        ("C clear", 21.55, ZONE_C["width"], ZONE_C["height"]),
    ):
        origin = Vector((0.0, y, EYE_Z))
        left = p5.ray(scene, origin, Vector((-1.0, 0.0, 0.0)))
        right = p5.ray(scene, origin, Vector((1.0, 0.0, 0.0)))
        up = p5.ray(scene, origin, Vector((0.0, 0.0, 1.0)))
        stations.append(
            dict(
                label=label,
                y=y,
                width=(left + right) if left is not None and right is not None else 0.0,
                ceiling=(up + EYE_Z) if up is not None else 0.0,
                target_width=width,
                target_ceiling=height,
            )
        )
    for obj in p4_objects + extra + markings:
        obj.hide_set(hidden_states.get(obj.name, False))
    bpy.context.view_layer.update()
    lights = [obj for obj in bpy.data.objects if obj.type == "LIGHT" and obj.name.startswith("LIGHT_")]
    by_state = {"NORMAL": 0, "WEAK": 0, "OFF": 0, "AGED_TINT": 0}
    by_zone = {"A": {"NORMAL": 0, "WEAK": 0, "OFF": 0, "AGED_TINT": 0}, "B": {"NORMAL": 0, "WEAK": 0, "OFF": 0, "AGED_TINT": 0}, "C": {"NORMAL": 0, "WEAK": 0, "OFF": 0, "AGED_TINT": 0}}
    shadow_casters = 0
    for obj in lights:
        state = obj.get("state") or state_of(obj.name)
        zone = obj.get("zone") or "A"
        by_state[state] = by_state.get(state, 0) + 1
        if zone in by_zone and state in by_zone[zone]:
            by_zone[zone][state] += 1
        if obj.data.energy > 0.0 and obj.data.use_shadow:
            shadow_casters += 1
    legacy_ok = all(
        bpy.data.objects.get(name) is not None
        and bpy.data.objects[name].data.energy == 0.0
        for name in PHASE1_LIGHTS
        if bpy.data.objects.get(name)
    )
    aging_ok = bpy.data.node_groups.get("P6_NG_AgingMasks") is not None
    library_ok = all(bpy.data.materials.get(name) for name in LIBRARY)
    named_ok = all(not obj.name.startswith("Area") and not obj.name.startswith("Point") and not obj.name.startswith("Light.") for obj in lights)
    return dict(
        moved=moved,
        removed=removed,
        added_core=added_core,
        camera_errors=camera_errors,
        stations=stations,
        phase2_counts={
            name: len(bpy.data.collections[name].objects) if bpy.data.collections.get(name) else -1
            for name in PHASE2_COUNTS
        },
        phase3_present=all(
            bpy.data.collections.get(n)
            for n in ("UTILITY_PRIMARY_PIPES", "UTILITY_SECONDARY_PIPES", "UTILITY_SUPPORTS")
        ),
        phase4_present=all(bpy.data.collections.get(n) for n in PHASE4_COLLECTIONS),
        markings=len([o for o in bpy.data.objects if o.name.startswith("MARK_")]),
        library_ok=library_ok,
        aging_ok=aging_ok,
        light_count=len(lights),
        by_state=by_state,
        by_zone=by_zone,
        shadow_casters=shadow_casters,
        fixture_meshes=len([o for o in bpy.data.objects if o.name.startswith("FIX_")]),
        legacy_ok=legacy_ok,
        legacy_lights=legacy_lights,
        named_ok=named_ok,
        world_strength=scene.world.node_tree.nodes["Background"].inputs[1].default_value
        if scene.world and scene.world.node_tree and scene.world.node_tree.nodes.get("Background")
        else -1.0,
        view_transform=scene.view_settings.view_transform,
        exposure=scene.view_settings.exposure,
        engine=scene.render.engine,
    )


def operational_ratio(zone_counts: dict) -> float:
    total = sum(zone_counts.values())
    if total <= 0:
        return 0.0
    on = zone_counts["NORMAL"] + zone_counts["WEAK"] + zone_counts["AGED_TINT"]
    return on / total


def write_report(validation: dict, color: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    phase1_pass = all(
        abs(row["width"] - row["target_width"]) < 0.001
        and abs(row["ceiling"] - row["target_ceiling"]) < 0.001
        for row in validation["stations"]
    ) and not validation["moved"] and not validation["removed"]
    phase2_pass = validation["phase2_counts"] == PHASE2_COUNTS and not validation["moved"]
    phase3_pass = validation["phase3_present"] and not validation["moved"]
    phase4_pass = validation["phase4_present"] and not validation["moved"]
    phase5_pass = validation["library_ok"] and not validation["moved"]
    phase6_pass = validation["aging_ok"] and validation["markings"] == 5 and not validation["moved"]
    a_ratio = operational_ratio(validation["by_zone"]["A"])
    b_ratio = operational_ratio(validation["by_zone"]["B"])
    c_ratio = operational_ratio(validation["by_zone"]["C"])
    phase7_pass = (
        phase1_pass
        and phase2_pass
        and phase3_pass
        and phase4_pass
        and phase5_pass
        and phase6_pass
        and not validation["camera_errors"]
        and not validation["added_core"]
        and validation["legacy_ok"]
        and validation["named_ok"]
        and validation["light_count"] == 15
        and 0.80 - 1e-6 <= a_ratio <= 1.0
        and 0.60 - 1e-6 <= b_ratio <= 0.80 + 1e-6
        and 0.30 - 1e-6 <= c_ratio <= 0.60 + 1e-6
        and validation["by_zone"]["B"]["OFF"] >= 1
        and validation["by_zone"]["C"]["OFF"] >= 1
        and validation["world_strength"] < 0.35
        and validation["exposure"] == 0.0
    )
    bz = validation["by_zone"]
    lines = [
        "PHASE 7 最終照明與能見度控制",
        "未移動 Phase 1–6 走廊幾何、管線、設備、材質或老化。相機路徑不變。",
        "Phase 1 六盞 LIGHT.Utility.* 位置保留，能量歸零並隱藏，改由可見燈具照明。",
        "",
        "RENDER / COLOR MANAGEMENT",
        f"  引擎：{validation['engine']}",
        f"  視圖轉換：{validation['view_transform']}  look={color.get('look')}",
        f"  曝光：{validation['exposure']:.2f}（不以極端曝光解照明）",
        f"  World 顏色 {color.get('world_color')} 強度 {validation['world_strength']:.3f}",
        "  Fast GI 作為有限間接光，避免無燈區變成 RGB 0 空洞。",
        "  無 volumetric fog、無 raytracing。",
        "",
        "LIGHT FIXTURES",
        "  類型：天花工業日光燈槽（housing + diffuser + 端蓋 + 短吊桿）與少量壁掛工作燈。",
        f"  數量：天花 12 + 壁燈 3 = {validation['light_count']} 盞 Area Light；燈具網格 {validation['fixture_meshes']}。",
        "  實作：RECTANGLE Area Light（normalize 瓦特），沿走廊拉長，不把燈管當成點光源。",
        "  發射片只負責燈具外觀；場景照明以 Area Light 為主。",
        f"  陰影投射燈：{validation['shadow_casters']}（OFF 不投射）。",
        "",
        "ZONE A",
        f"  狀態：NORMAL {bz['A']['NORMAL']} / AGED_TINT {bz['A']['AGED_TINT']} / WEAK {bz['A']['WEAK']} / OFF {bz['A']['OFF']}  運轉比 {a_ratio:.0%}",
        "  策略：四盞天花全運轉，間距不完全相等；A_04 略暖、略弱。東牆 PN-04 旁一盞工作燈。",
        "  能見度：可讀牆、管、地坪、設備與走廊方向。對比中等，不是展示廳。",
        "",
        "ZONE B",
        f"  狀態：NORMAL {bz['B']['NORMAL']} / WEAK {bz['B']['WEAK']} / OFF {bz['B']['OFF']}  運轉比 {b_ratio:.0%}",
        "  策略：AB 樑後故意空一拍；B_03 實體熄燈；兩盞 WEAK；西牆維修區弱壁燈。",
        "  能見度：仍可走，但節奏不穩、管線陰影更深、明暗交替更明顯。",
        "",
        "ZONE C",
        f"  狀態：NORMAL {bz['C']['NORMAL']} / WEAK {bz['C']['WEAK']} / OFF {bz['C']['OFF']}  運轉比 {c_ratio:.0%}",
        "  策略：C_02／C_04 熄燈；C_03 是最後一盞完整工作燈且 cutoff 3.5 m；遠端壁燈為 OFF。",
        "  能見度：可辨地坪與牆輪廓，遠處細節不確定。",
        "",
        "FAR END",
        "  以照明而非改牆解決：C_04 OFF、C_03 短距離、World 極弱、無遠距填充。",
        "  終端牆保留極弱形體，不純黑遮住。既有梁、管、艙門打斷視線。",
        "",
        "SHADOWS",
        "  由真實燈具與既有管／樑／設備投射，無假陰影 decal。",
        "  EEVEE shadows + Fast GI；OFF 燈不投影。",
        "",
        "COLOR TEMPERATURE",
        "  基準：偏冷工業白 (0.95–0.98, 0.98, 1.00)。",
        "  變化：AGED_TINT 微暖、WEAK 微綠老化、壁燈略中性。沒有藍／綠／橙分區。",
        "",
        "MATERIAL INTERACTION",
        "  保留 Phase 5/6 材質與老化 mask。照明用來顯現 roughness、水痕與金屬高光，不重做老化。",
        "",
        "FIRST-PERSON VALIDATION",
        "  既有 CAM_INSPECT 路徑：START→A→B→C→FAR END。",
        "  不以同等亮度貫穿整廊。",
        "",
        "PERFORMANCE",
        f"  Area Light {validation['light_count']} 盞；陰影燈 {validation['shadow_casters']}。",
        "  每燈 use_custom_distance；OFF 關閉陰影；共用 housing/diffuser mesh。",
        "  無 volumetric、無數百盞燈、無高解析陰影池堆疊。",
        "",
        "PHASE 1 空間凍結量測點",
        "  標籤       y       實測寬度       實測天花高度       目標寬度       目標天花高度",
    ]
    for row in validation["stations"]:
        lines.append(
            f"  {row['label']:10s} {row['y']:5.2f}    {row['width']:.3f} m       "
            f"{row['ceiling']:.3f} m          {row['target_width']:.3f} m       "
            f"{row['target_ceiling']:.3f} m"
        )
    lines += [
        "",
        "凍結／驗證細節",
        f"  核心物件變換改動：{len(validation['moved'])}",
        f"  核心物件刪除：{len(validation['removed'])}；非燈具新增：{len(validation['added_core'])}",
        f"  相機路徑錯誤：{len(validation['camera_errors'])}",
        f"  Phase 1 佔位燈停用：{', '.join(validation['legacy_lights']) or '無'}",
        "",
        "PHASE 1 空間凍結狀態： " + ("PASS" if phase1_pass else "FAIL"),
        "PHASE 2 結構凍結狀態： " + ("PASS" if phase2_pass else "FAIL"),
        "PHASE 3 管線凍結狀態： " + ("PASS" if phase3_pass else "FAIL"),
        "PHASE 4 設備凍結狀態： " + ("PASS" if phase4_pass else "FAIL"),
        "PHASE 5 材質凍結狀態： " + ("PASS" if phase5_pass else "FAIL"),
        "PHASE 6 老化凍結狀態： " + ("PASS" if phase6_pass else "FAIL"),
        "PHASE 7 照明驗證： " + ("PASS" if phase7_pass else "FAIL"),
        "  Phase 1 尺寸是否修改：否",
        "  Phase 2 結構骨架是否修改：否",
        "  Phase 3 管線路由是否修改：否",
        "  Phase 4 設備位置是否修改：否",
        "  Phase 5 材質名稱／分類是否保留：是",
        "  Phase 6 老化節點組／5 個標記是否保留：是",
        "  Phase 1 佔位燈：位置未改，能量歸零（Phase 7 允許調整燈具）",
        "  尚未開始 Phase 8。",
    ]
    if validation["moved"]:
        lines.append("  被改動物件：" + ", ".join(validation["moved"][:20]))
    if validation["added_core"]:
        lines.append("  非預期新增：" + ", ".join(validation["added_core"][:20]))
    report = OUTPUT_DIR / "phase7_lighting_validation.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", report)
    print("PHASE 7 VALIDATION", "PASS" if phase7_pass else "FAIL")
    print("ratios A/B/C", round(a_ratio, 3), round(b_ratio, 3), round(c_ratio, 3))
    print("view_transform", validation["view_transform"], "exposure", validation["exposure"])
    return report


def render_stills(scene: bpy.types.Scene) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    configure_eevee(scene, 48)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    for frame, label in STILLS:
        scene.frame_set(frame)
        scene.render.filepath = str(OUTPUT_DIR / f"{label}.jpg")
        bpy.ops.render.render(write_still=True)
        print("still", label, "frame", frame)


def render_playblast(scene: bpy.types.Scene) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = OUTPUT_DIR / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    configure_eevee(scene, 12)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    scene.frame_start = 1
    scene.frame_end = 250
    scene.render.filepath = str(frames / "phase7_walk_")
    bpy.ops.render.render(animation=True)
    output = OUTPUT_DIR / "phase7_lighting_walk.mp4"
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "24",
            "-i",
            str(frames / "phase7_walk_%04d.jpg"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "20",
            str(output),
        ]
    )
    print("playblast", output)
    return output


def main() -> None:
    mode = parse_mode()
    scene = bpy.context.scene
    before = p5.snapshot()
    clear_phase7()
    collection("LIGHTING_FIXTURES")
    collection("LIGHTING_ACTIVE")
    collection("LIGHTING_WEAK")
    collection("LIGHTING_OFF")
    guides = collection("LIGHTING_GUIDES")
    guide = bpy.data.objects.new("LIGHTING_STATE_GUIDE", None)
    guide.empty_display_type = "PLAIN_AXES"
    guide.empty_display_size = 0.12
    guide.location = (0.0, 12.0, 2.4)
    guide.hide_render = True
    guide["phase"] = 7
    guide["states"] = "NORMAL WEAK OFF AGED_TINT"
    guides.objects.link(guide)
    mats = build_materials()
    build_ceiling_fixtures(mats)
    build_wall_fixtures(mats)
    legacy = deactivate_phase1_lights()
    color = configure_world(scene)
    configure_eevee(scene, 48)
    validation = validate(scene, before, legacy)
    write_report(validation, color)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    if mode in {"stills", "playblast"}:
        render_stills(scene)
        if mode == "playblast":
            render_playblast(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 7 complete; Phase 8 not started.")


if __name__ == "__main__":
    main()
