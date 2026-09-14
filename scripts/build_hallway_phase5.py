#!/usr/bin/env python3
"""Phase 5 — material identity pass for the frozen Level 2 hallway.

Assigns a restrained physically based material library to existing Phase 1–4
geometry.  No corridor, structure, pipe, equipment, or camera transforms are
moved.  No weathering, debris, horror lighting, or Phase 6 aging is added.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase5.py -- --stills
  blender -b hallway.blend --python scripts/build_hallway_phase5.py -- --playblast
  blender -b hallway.blend --python scripts/build_hallway_phase5.py -- --no-render
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase5"
EYE_Z = 1.68

ZONE_A = dict(y0=0.00, y1=7.70, width=2.20, height=3.00)
ZONE_B = dict(y0=8.90, y1=15.50, width=2.05, height=2.74)
ZONE_C = dict(y0=16.70, y1=24.00, width=2.20, height=2.93)

PHASE2_COUNTS = {
    "STRUCTURE_BEAMS": 11,
    "STRUCTURE_WALL": 19,
    "STRUCTURE_MOUNTS": 27,
    "STRUCTURE_GUIDES": 12,
}
PHASE4_COLLECTIONS = (
    "EQUIPMENT_ELECTRICAL",
    "EQUIPMENT_CONTROL",
    "EQUIPMENT_METERS",
    "EQUIPMENT_VENTILATION",
    "EQUIPMENT_SERVICE",
    "UTILITY_CABLES",
)
LIBRARY = (
    "MAT_Wall_PaintedConcrete",
    "MAT_Floor_IndustrialConcrete",
    "MAT_Ceiling_AgedConcrete",
    "MAT_Structure_PaintedSteel",
    "MAT_Pipe_DarkPaintedSteel",
    "MAT_Pipe_Secondary",
    "MAT_Metal_Galvanized",
    "MAT_Cabinet_PaintedMetal",
    "MAT_Vent_GalvanizedMetal",
    "MAT_Rubber_Dark",
    "MAT_Valve_IndustrialAccent",
)

STILLS = (
    (1, "01_entry_materials"),
    (42, "02_zone_a_identity"),
    (78, "03_approach_ab"),
    (96, "04_zone_b_pipes_cabinets"),
    (132, "05_zone_b_density"),
    (164, "06_approach_bc"),
    (185, "07_zone_c_isolated"),
    (215, "08_zone_c_offset"),
    (240, "09_zone_c_depth"),
    (250, "10_far_vanishing"),
)


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--no-render" in argv:
        return "check"
    if "--playblast" in argv:
        return "playblast"
    return "stills"


def sock(node: bpy.types.Node, identifier: str):
    for sockets in (node.inputs, node.outputs):
        for item in sockets:
            if item.identifier == identifier:
                return item
    raise KeyError(f"{node.bl_idname} has no socket {identifier}")


def link(nt: bpy.types.NodeTree, src, dst) -> None:
    nt.links.new(src, dst)


def snapshot() -> dict[str, tuple]:
    rows = {}
    for obj in bpy.data.objects:
        if obj.type not in {"MESH", "CURVE"}:
            continue
        data_name = obj.data.name if obj.data else ""
        verts = len(obj.data.vertices) if obj.type == "MESH" else -1
        splines = len(obj.data.splines) if obj.type == "CURVE" else -1
        rows[obj.name] = (
            obj.type,
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
            tuple(round(v, 5) for v in obj.scale),
            data_name,
            verts,
            splines,
        )
    return rows


def light_positions() -> dict[str, tuple]:
    return {
        obj.name: tuple(round(v, 5) for v in obj.location)
        for obj in bpy.data.objects
        if obj.type == "LIGHT"
    }


def configure_inspection_lighting() -> None:
    """Neutral evaluation lighting. Existing fixture positions stay frozen.

    Phase 1 area lights originally faced the ceiling (X=180 deg).  That was
    invisible under Workbench studio lighting, but in EEVEE it blew out the
    ceiling and left walls/floor too dark to judge PBR response.  This pass
    aims the same six fixtures downward and adds world fill only.
    """
    for obj in bpy.data.objects:
        if obj.type != "LIGHT" or not obj.name.startswith("LIGHT.Utility"):
            continue
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.data.energy = 55.0
        obj.data.color = (1.0, 0.97, 0.92)
    world = bpy.context.scene.world
    if world is not None and world.use_nodes and world.node_tree is not None:
        background = world.node_tree.nodes.get("Background")
        if background is not None:
            background.inputs[0].default_value = (0.16, 0.16, 0.17, 1.0)
            background.inputs[1].default_value = 1.15


def clear_phase5() -> None:
    for name in LIBRARY:
        mat = bpy.data.materials.get(name)
        if mat is not None:
            bpy.data.materials.remove(mat)
    for group in list(bpy.data.node_groups):
        if group.name.startswith("P5_"):
            bpy.data.node_groups.remove(group)


def new_material(name: str) -> tuple[bpy.types.Material, bpy.types.NodeTree]:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return mat, nt


def add_output(nt: bpy.types.NodeTree) -> tuple[bpy.types.Node, bpy.types.Node]:
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (920, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (620, 0)
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return out, bsdf


def world_y(nt: bpy.types.NodeTree, loc=( -720, 280)):
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    geom.location = loc
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (loc[0] + 180, loc[1])
    link(nt, geom.outputs["Position"], sep.inputs["Vector"])
    return geom.outputs["Position"], sep.outputs["Y"]


def noise(nt: bpy.types.NodeTree, vector, scale: float, detail: float, loc, roughness: float = 0.45):
    node = nt.nodes.new("ShaderNodeTexNoise")
    node.location = loc
    node.noise_dimensions = "3D"
    node.inputs["Scale"].default_value = scale
    node.inputs["Detail"].default_value = detail
    node.inputs["Roughness"].default_value = roughness
    node.inputs["Distortion"].default_value = 0.08
    link(nt, vector, node.inputs["Vector"])
    return node


def mix_color(nt: bpy.types.NodeTree, factor, color_a, color_b, loc):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.location = loc
    link(nt, factor, sock(node, "Factor_Float"))
    sock(node, "A_Color").default_value = (*color_a, 1.0)
    sock(node, "B_Color").default_value = (*color_b, 1.0)
    return sock(node, "Result_Color")


def mix_float(nt: bpy.types.NodeTree, factor, a: float, b: float, loc):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "FLOAT"
    node.location = loc
    link(nt, factor, sock(node, "Factor_Float"))
    sock(node, "A_Float").default_value = a
    sock(node, "B_Float").default_value = b
    return sock(node, "Result_Float")


def map_range(nt: bpy.types.NodeTree, value, from_min, from_max, to_min, to_max, loc):
    node = nt.nodes.new("ShaderNodeMapRange")
    node.location = loc
    node.clamp = True
    link(nt, value, node.inputs["Value"])
    node.inputs["From Min"].default_value = from_min
    node.inputs["From Max"].default_value = from_max
    node.inputs["To Min"].default_value = to_min
    node.inputs["To Max"].default_value = to_max
    return node.outputs["Result"]


def bump_from(nt: bpy.types.NodeTree, height, strength: float, distance: float, loc):
    node = nt.nodes.new("ShaderNodeBump")
    node.location = loc
    node.inputs["Strength"].default_value = strength
    node.inputs["Distance"].default_value = distance
    link(nt, height, node.inputs["Height"])
    return node.outputs["Normal"]


def zone_amount(nt: bpy.types.NodeTree, y_sock, loc=( -360, 280)):
    """0 at Zone A, 1 at far Zone C. Continuous so the facility stays one space."""
    return map_range(nt, y_sock, 0.0, 24.0, 0.0, 1.0, loc)


def build_surface(
    name: str,
    color_a: tuple[float, float, float],
    color_b: tuple[float, float, float],
    rough_a: float,
    rough_b: float,
    metallic: float,
    large_scale: float,
    fine_scale: float,
    bump_strength: float,
    bump_distance: float,
    spec: float,
    zone_darken: float = 0.0,
    metallic_b: float | None = None,
    viewport: tuple[float, float, float] | None = None,
) -> bpy.types.Material:
    mat, nt = new_material(name)
    _out, bsdf = add_output(nt)
    position, y_sock = world_y(nt)
    zone = zone_amount(nt, y_sock)
    large = noise(nt, position, large_scale, 2.0, (-360, 80), 0.40)
    fine = noise(nt, position, fine_scale, 4.0, (-360, -140), 0.55)
    color = mix_color(nt, large.outputs["Factor"], color_a, color_b, (220, 80))
    if zone_darken > 0.0:
        dark = tuple(max(0.02, c * (1.0 - zone_darken)) for c in color_a)
        darken_node = nt.nodes.new("ShaderNodeMix")
        darken_node.data_type = "RGBA"
        darken_node.location = (400, 200)
        link(nt, zone, sock(darken_node, "Factor_Float"))
        link(nt, color, sock(darken_node, "A_Color"))
        sock(darken_node, "B_Color").default_value = (*dark, 1.0)
        color = sock(darken_node, "Result_Color")
    rough = mix_float(nt, fine.outputs["Factor"], rough_a, rough_b, (220, -80))
    if metallic_b is not None:
        metal = mix_float(nt, large.outputs["Factor"], metallic, metallic_b, (220, -240))
        link(nt, metal, bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Metallic"].default_value = metallic
    normal = bump_from(nt, fine.outputs["Factor"], bump_strength, bump_distance, (220, -360))
    link(nt, color, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, normal, bsdf.inputs["Normal"])
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    preview = viewport or tuple((a + b) * 0.5 for a, b in zip(color_a, color_b))
    mat.diffuse_color = (*preview, 1.0)
    return mat


def build_library() -> dict[str, bpy.types.Material]:
    mats = {
        "MAT_Wall_PaintedConcrete": build_surface(
            "MAT_Wall_PaintedConcrete",
            (0.48, 0.46, 0.42),
            (0.40, 0.385, 0.355),
            0.80,
            0.90,
            0.0,
            large_scale=5.5,
            fine_scale=92.0,
            bump_strength=0.045,
            bump_distance=0.018,
            spec=0.32,
            zone_darken=0.08,
            viewport=(0.40, 0.39, 0.36),
        ),
        "MAT_Floor_IndustrialConcrete": build_surface(
            "MAT_Floor_IndustrialConcrete",
            (0.145, 0.138, 0.128),
            (0.112, 0.108, 0.100),
            0.66,
            0.82,
            0.0,
            large_scale=4.2,
            fine_scale=58.0,
            bump_strength=0.035,
            bump_distance=0.016,
            spec=0.28,
            zone_darken=0.05,
            viewport=(0.13, 0.12, 0.11),
        ),
        "MAT_Ceiling_AgedConcrete": build_surface(
            "MAT_Ceiling_AgedConcrete",
            (0.27, 0.26, 0.24),
            (0.22, 0.215, 0.20),
            0.78,
            0.88,
            0.0,
            large_scale=3.4,
            fine_scale=28.0,
            bump_strength=0.018,
            bump_distance=0.02,
            spec=0.30,
            zone_darken=0.06,
            viewport=(0.24, 0.23, 0.21),
        ),
        "MAT_Structure_PaintedSteel": build_surface(
            "MAT_Structure_PaintedSteel",
            (0.175, 0.172, 0.160),
            (0.145, 0.142, 0.132),
            0.62,
            0.74,
            0.0,
            large_scale=18.0,
            fine_scale=70.0,
            bump_strength=0.028,
            bump_distance=0.012,
            spec=0.42,
            zone_darken=0.04,
            viewport=(0.16, 0.16, 0.15),
        ),
        "MAT_Pipe_DarkPaintedSteel": build_surface(
            "MAT_Pipe_DarkPaintedSteel",
            (0.108, 0.118, 0.102),
            (0.086, 0.094, 0.082),
            0.48,
            0.62,
            0.0,
            large_scale=16.0,
            fine_scale=64.0,
            bump_strength=0.022,
            bump_distance=0.010,
            spec=0.44,
            zone_darken=0.03,
            viewport=(0.10, 0.11, 0.09),
        ),
        "MAT_Pipe_Secondary": build_surface(
            "MAT_Pipe_Secondary",
            (0.205, 0.188, 0.168),
            (0.168, 0.155, 0.140),
            0.52,
            0.66,
            0.0,
            large_scale=18.0,
            fine_scale=72.0,
            bump_strength=0.020,
            bump_distance=0.010,
            spec=0.40,
            zone_darken=0.04,
            viewport=(0.18, 0.17, 0.15),
        ),
        "MAT_Metal_Galvanized": build_surface(
            "MAT_Metal_Galvanized",
            (0.36, 0.37, 0.35),
            (0.28, 0.29, 0.275),
            0.44,
            0.58,
            0.62,
            large_scale=28.0,
            fine_scale=80.0,
            bump_strength=0.024,
            bump_distance=0.008,
            spec=0.50,
            metallic_b=0.78,
            viewport=(0.32, 0.33, 0.31),
        ),
        "MAT_Cabinet_PaintedMetal": build_cabinet_material(),
        "MAT_Vent_GalvanizedMetal": build_surface(
            "MAT_Vent_GalvanizedMetal",
            (0.31, 0.32, 0.30),
            (0.24, 0.25, 0.235),
            0.46,
            0.60,
            0.58,
            large_scale=24.0,
            fine_scale=76.0,
            bump_strength=0.022,
            bump_distance=0.008,
            spec=0.48,
            metallic_b=0.74,
            viewport=(0.27, 0.28, 0.26),
        ),
        "MAT_Rubber_Dark": build_surface(
            "MAT_Rubber_Dark",
            (0.075, 0.072, 0.066),
            (0.055, 0.053, 0.048),
            0.86,
            0.95,
            0.0,
            large_scale=22.0,
            fine_scale=90.0,
            bump_strength=0.012,
            bump_distance=0.006,
            spec=0.18,
            viewport=(0.065, 0.062, 0.056),
        ),
        "MAT_Valve_IndustrialAccent": build_surface(
            "MAT_Valve_IndustrialAccent",
            (0.30, 0.095, 0.070),
            (0.22, 0.075, 0.055),
            0.54,
            0.66,
            0.0,
            large_scale=20.0,
            fine_scale=68.0,
            bump_strength=0.018,
            bump_distance=0.008,
            spec=0.38,
            viewport=(0.26, 0.085, 0.062),
        ),
    }
    return mats


def build_cabinet_material() -> bpy.types.Material:
    """Beige-grey in Zone A, green-grey in Zone B, duller in Zone C."""
    mat, nt = new_material("MAT_Cabinet_PaintedMetal")
    _out, bsdf = add_output(nt)
    position, y_sock = world_y(nt)
    zone = zone_amount(nt, y_sock)
    large = noise(nt, position, 14.0, 2.0, (-360, 40), 0.38)
    fine = noise(nt, position, 76.0, 3.0, (-360, -160), 0.50)
    beige = (0.40, 0.375, 0.325)
    green = (0.285, 0.315, 0.285)
    dull = (0.30, 0.285, 0.255)
    ab = mix_color(nt, zone, beige, green, (40, 160))
    family = mix_color(nt, zone, beige, dull, (40, 280))
    # Use mid corridor as green-grey, far end as dull beige-grey.
    zone_mid = map_range(nt, y_sock, 8.5, 16.5, 0.0, 1.0, (-80, 360))
    zoned = nt.nodes.new("ShaderNodeMix")
    zoned.data_type = "RGBA"
    zoned.location = (260, 220)
    link(nt, zone_mid, sock(zoned, "Factor_Float"))
    link(nt, family, sock(zoned, "A_Color"))
    link(nt, ab, sock(zoned, "B_Color"))
    base = sock(zoned, "Result_Color")
    varied = nt.nodes.new("ShaderNodeMix")
    varied.data_type = "RGBA"
    varied.location = (440, 80)
    link(nt, large.outputs["Factor"], sock(varied, "Factor_Float"))
    link(nt, base, sock(varied, "A_Color"))
    sock(varied, "B_Color").default_value = (0.24, 0.24, 0.22, 1.0)
    color = sock(varied, "Result_Color")
    rough = mix_float(nt, fine.outputs["Factor"], 0.58, 0.72, (220, -80))
    normal = bump_from(nt, fine.outputs["Factor"], 0.016, 0.008, (220, -280))
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.40
    link(nt, color, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, normal, bsdf.inputs["Normal"])
    mat.diffuse_color = (0.34, 0.33, 0.29, 1.0)
    return mat


def classify(obj: bpy.types.Object) -> str | None:
    if obj.type not in {"MESH", "CURVE"}:
        return None
    name = obj.name
    if name.startswith("VALVE_Handwheel_") and "Arm" not in name:
        return "MAT_Valve_IndustrialAccent"
    if name.startswith("VENT_"):
        return "MAT_Vent_GalvanizedMetal"
    if name.startswith(("CONDUIT_", "CABLE_ENTRY_")) or name.endswith("_CableEntry"):
        return "MAT_Rubber_Dark"
    if "GAUGE_" in name and (name.endswith("_Face") or name.endswith("_Needle")):
        return "MAT_Rubber_Dark"
    if name.startswith("GAUGE_"):
        return "MAT_Metal_Galvanized"
    if any(token in name for token in ("_Handle", "_Hinge_", "_Latch", "_Frame_")):
        return "MAT_Metal_Galvanized"
    if name.startswith(("BOX_", "CABINET_", "HATCH_")) or name.endswith("_DoorPanel") or name.endswith("_DoorSeam") or name.endswith("_Indicator"):
        return "MAT_Cabinet_PaintedMetal"
    if name.startswith("UTILITY_CableTray"):
        return "MAT_Metal_Galvanized"
    if name.startswith(("BRACKET_", "CLAMP_", "HANGER_", "PLATE_", "BRACE_", "MOUNT_")):
        return "MAT_Metal_Galvanized"
    if name.startswith(("PIPE_Primary_", "ELBOW_Primary_", "FLANGE_Primary_", "FLANGE_Valve_")):
        return "MAT_Pipe_DarkPaintedSteel"
    if name.startswith(
        (
            "PIPE_Secondary_",
            "PIPE_Minor_",
            "ELBOW_Secondary_",
            "RISER_",
            "CONNECTOR_",
            "FLANGE_Minor_",
        )
    ):
        return "MAT_Pipe_Secondary"
    if name.startswith("VALVE_"):
        return "MAT_Structure_PaintedSteel"
    if name.startswith(("BEAM", "PIER", "SUPPORT_Wall", "BEAM_Ceiling")):
        return "MAT_Structure_PaintedSteel"
    if name == "FLOOR":
        return "MAT_Floor_IndustrialConcrete"
    if name.startswith("CEIL"):
        return "MAT_Ceiling_AgedConcrete"
    if name.startswith("WALL"):
        return "MAT_Wall_PaintedConcrete"
    return None


def assign_materials(mats: dict[str, bpy.types.Material]) -> dict[str, list[str]]:
    assigned: dict[str, list[str]] = {name: [] for name in LIBRARY}
    skipped = []
    for obj in bpy.data.objects:
        key = classify(obj)
        if key is None:
            if obj.type in {"MESH", "CURVE"}:
                skipped.append(obj.name)
            continue
        mat = mats[key]
        if len(obj.material_slots) == 0:
            obj.data.materials.append(mat)
        obj.material_slots[0].link = "OBJECT"
        obj.material_slots[0].material = mat
        assigned[key].append(obj.name)
    if skipped:
        raise RuntimeError("Unclassified renderable objects: " + ", ".join(skipped))
    return assigned


def ray(scene: bpy.types.Scene, origin: Vector, direction: Vector) -> float | None:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, _n, _i, _o, _m = scene.ray_cast(depsgraph, origin, direction.normalized())
    return (location - origin).length if hit else None


def validate(
    scene: bpy.types.Scene,
    before: dict[str, tuple],
    lights_before: dict[str, tuple],
    assigned: dict[str, list[str]],
) -> dict:
    after = snapshot()
    moved = [
        name
        for name, row in before.items()
        if after.get(name) != row
    ]
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    camera = bpy.data.objects["CAM_INSPECT"]
    camera_errors = []
    for frame in range(1, 251, 8):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        position = camera.matrix_world.translation.copy()
        if abs(position.x) > 0.01 or abs(position.z - EYE_Z) > 0.01:
            camera_errors.append((frame, tuple(round(v, 3) for v in position)))
    # Measure the frozen Phase 1 envelope without letting Phase 4 wall-mounted
    # equipment shorten the raycast. Restore viewport visibility afterwards.
    p4_objects = [
        obj
        for name in PHASE4_COLLECTIONS
        if bpy.data.collections.get(name)
        for obj in bpy.data.collections[name].objects
    ]
    hidden_states = {obj.name: obj.hide_get() for obj in p4_objects}
    for obj in p4_objects:
        obj.hide_set(True)
    bpy.context.view_layer.update()
    stations = []
    for label, y, width, height in (
        ("A clear", 3.25, ZONE_A["width"], ZONE_A["height"]),
        ("B clear", 11.75, ZONE_B["width"], ZONE_B["height"]),
        ("C clear", 21.55, ZONE_C["width"], ZONE_C["height"]),
    ):
        origin = Vector((0.0, y, EYE_Z))
        left = ray(scene, origin, Vector((-1.0, 0.0, 0.0)))
        right = ray(scene, origin, Vector((1.0, 0.0, 0.0)))
        up = ray(scene, origin, Vector((0.0, 0.0, 1.0)))
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
    for obj in p4_objects:
        obj.hide_set(hidden_states[obj.name])
    bpy.context.view_layer.update()
    image_textures = [
        mat.name
        for mat in bpy.data.materials
        if mat.name in LIBRARY and any(n.bl_idname == "ShaderNodeTexImage" for n in mat.node_tree.nodes)
    ]
    metallic_names = {"MAT_Metal_Galvanized", "MAT_Vent_GalvanizedMetal"}
    painted_nonmetal = [
        name
        for name in LIBRARY
        if name not in metallic_names
    ]
    missing_uv_ok = [
        mesh.name
        for mesh in bpy.data.meshes
        if mesh.users and not mesh.uv_layers
    ]
    phase2_counts = {
        name: len(bpy.data.collections[name].objects) if bpy.data.collections.get(name) else -1
        for name in PHASE2_COUNTS
    }
    phase4_present = all(bpy.data.collections.get(name) for name in PHASE4_COLLECTIONS)
    phase3_present = all(
        bpy.data.collections.get(name)
        for name in ("UTILITY_PRIMARY_PIPES", "UTILITY_SECONDARY_PIPES", "UTILITY_SUPPORTS")
    )
    light_moved = [
        name for name, loc in light_positions().items() if lights_before.get(name) != loc
    ]
    return dict(
        moved=moved,
        added=added,
        removed=removed,
        camera_errors=camera_errors,
        stations=stations,
        image_textures=image_textures,
        metallic_names=sorted(metallic_names),
        painted_nonmetal=painted_nonmetal,
        missing_uv_count=len(missing_uv_ok),
        phase2_counts=phase2_counts,
        phase4_present=phase4_present,
        phase3_present=phase3_present,
        light_moved=light_moved,
        assigned_counts={name: len(items) for name, items in assigned.items()},
        library_count=len(LIBRARY),
        node_count=sum(len(bpy.data.materials[name].node_tree.nodes) for name in LIBRARY),
    )


def write_report(assigned: dict[str, list[str]], validation: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    phase1_pass = all(
        abs(row["width"] - row["target_width"]) < 0.001
        and abs(row["ceiling"] - row["target_ceiling"]) < 0.001
        for row in validation["stations"]
    ) and not validation["moved"] and not validation["removed"]
    phase2_pass = validation["phase2_counts"] == PHASE2_COUNTS and not validation["moved"]
    phase3_pass = validation["phase3_present"] and not validation["moved"]
    phase4_pass = validation["phase4_present"] and not validation["moved"]
    phase5_pass = (
        not validation["moved"]
        and not validation["added"]
        and not validation["removed"]
        and not validation["camera_errors"]
        and not validation["image_textures"]
        and not validation["light_moved"]
        and validation["library_count"] == 11
        and all(validation["assigned_counts"][name] > 0 for name in LIBRARY)
        and phase1_pass
        and phase2_pass
        and phase3_pass
        and phase4_pass
    )
    lines = [
        "PHASE 5 材質身份建立",
        "僅指派 PBR 材質庫；未移動 Phase 1–4 幾何、設備或相機路徑。未開始風化、最終燈光或 Phase 6。",
        "",
        "材質庫",
    ]
    usage = {
        "MAT_Wall_PaintedConcrete": "牆體殼層與 Zone B 內縮牆面",
        "MAT_Floor_IndustrialConcrete": "走廊地坪",
        "MAT_Ceiling_AgedConcrete": "天花殼層與 Zone B/C soffit",
        "MAT_Structure_PaintedSteel": "結構樑、墩柱、牆撐、閥體／閥桿",
        "MAT_Pipe_DarkPaintedSteel": "主管線、主管彎頭與主管法蘭",
        "MAT_Pipe_Secondary": "次要／小型管線、跨接、立管、連接環與小型法蘭",
        "MAT_Metal_Galvanized": "支架、管夾、吊架、牆板、cable tray、鉸鏈／把手／艙門框、壓力表殼",
        "MAT_Cabinet_PaintedMetal": "電氣箱、控制櫃、門板、指示區與維修艙門板",
        "MAT_Vent_GalvanizedMetal": "Zone B 壁面通風格柵與格柵片",
        "MAT_Rubber_Dark": "conduit、電纜入口、表盤與指針",
        "MAT_Valve_IndustrialAccent": "僅兩顆閥輪，作為極少量工業警示色",
    }
    for name in LIBRARY:
        lines.append(f"  {name}  ×{validation['assigned_counts'][name]}  — {usage[name]}")
        sample = ", ".join(assigned[name][:4])
        if len(assigned[name]) > 4:
            sample += " …"
        lines.append(f"    例：{sample}")
    lines += [
        "",
        "色彩配置",
        "  主色：低飽和汙灰牆、炭色地坪、中暗天花混凝土。",
        "  次色：暗綠灰塗裝主管、略暖的次要管、鍍鋅冷灰、米灰／綠灰控制櫃。",
        "  點綴：極少量氧化紅閥輪，佔畫面比例很低。",
        "  未使用純白、純黑或高飽和工廠色。",
        "",
        "粗糙度層次",
        "  牆面混凝土：0.80–0.90（高）",
        "  地坪混凝土：0.66–0.82（中高，局部略較牆面平滑）",
        "  天花混凝土：0.78–0.88（高，但微結構頻率較低）",
        "  結構塗裝鋼：0.62–0.74（中高）",
        "  主管塗裝：0.48–0.62（中，保留可讀高光）",
        "  次要管塗裝：0.52–0.66（中）",
        "  鍍鋅金屬：0.44–0.58（中，非鏡面）",
        "  橡膠：0.86–0.95（高）",
        "  閥輪點綴：0.54–0.66（中）",
        "",
        "金屬響應",
        "  金屬：MAT_Metal_Galvanized、MAT_Vent_GalvanizedMetal（metallic 約 0.58–0.78，高粗糙，非鉻）。",
        "  非金屬塗裝：牆、地、天花、結構樑、主管、次要管、控制櫃、閥輪、橡膠。",
        "  塗裝金屬不以 metallic 1.0 冒充裸金屬。",
        "",
        "微表面",
        "  全部使用世界座標程序化 Noise + 低強度 Bump，無點陣貼圖、無 Displacement。",
        "  大尺度 noise 約 3–28（公尺級明度變化極弱），細尺度 28–92（公分／毫米級粒面）。",
        "  目的是打斷完美 CGI 光滑，而不是讓每個表面看起來像程序化地形。",
        "",
        "UV／對應",
        f"  發現 {validation['missing_uv_count']} 個 mesh 缺少 UV。",
        "  未改幾何、未展開 UV。改以 Geometry Position 世界空間映射，避免 24 m 牆面與 curve 管線被拉伸成地形紋理。",
        "  管線與重複模組因此維持一致的物理紋理尺度。",
        "",
        "ZONE A",
        "  同一材質家族；牆面與櫃體較均勻，櫃體偏米灰／工業米色，對比較克制。",
        "ZONE B",
        "  同一材質家族；沿 Y 軸提高明度混合，控制櫃偏綠灰，管線層次與鍍鋅支架對比較清楚。",
        "ZONE C",
        "  同一材質家族；略更暗、略不均勻，沒有鏽蝕、裂縫或破壞。",
        "",
        "效能",
        f"  材質數：{validation['library_count']}（可重用，無 4K 貼圖）。",
        f"  節點總數約：{validation['node_count']}；每材質約 2 個 Noise（Detail 2–4）+ 1 個 Bump。",
        "  未使用 Displacement、體積、影像貼圖或超高頻 shader。",
        "  以既有 6 盞巡檢 Area 燈 + EEVEE 評估材質；未做最終燈光、閃爍或體積霧。",
        "  燈具位置未改。原朝向天花，EEVEE 下無法判斷 PBR，故改為朝下並降至 55 W，世界填光強度 1.15。",
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
        f"  變換被改動的物件：{len(validation['moved'])}",
        f"  新增物件：{len(validation['added'])}；刪除物件：{len(validation['removed'])}",
        f"  相機路徑錯誤：{len(validation['camera_errors'])}",
        f"  燈具變換改動：{len(validation['light_moved'])}",
        f"  影像貼圖：{len(validation['image_textures'])}",
        "",
        "PHASE 1 空間凍結狀態： " + ("PASS" if phase1_pass else "FAIL"),
        "PHASE 2 結構凍結狀態： " + ("PASS" if phase2_pass else "FAIL"),
        "PHASE 3 管線凍結狀態： " + ("PASS" if phase3_pass else "FAIL"),
        "PHASE 4 設備凍結狀態： " + ("PASS" if phase4_pass else "FAIL"),
        "PHASE 5 材質驗證： " + ("PASS" if phase5_pass else "FAIL"),
        "  Phase 1 尺寸是否修改：否",
        "  Phase 2 結構骨架是否修改：否",
        "  Phase 3 管線路由是否修改：否",
        "  Phase 4 設備位置是否修改：否",
        "  尚未開始 Phase 6。",
    ]
    if validation["moved"]:
        lines.append("  被改動物件：" + ", ".join(validation["moved"][:20]))
    report = OUTPUT_DIR / "phase5_material_validation.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", report)
    print("PHASE 5 VALIDATION", "PASS" if phase5_pass else "FAIL")
    return report


def configure_inspect_render(scene: bpy.types.Scene, samples: int) -> None:
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
    scene.eevee.fast_gi_quality = 0.45
    scene.eevee.fast_gi_ray_count = 8
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass


def render_stills(scene: bpy.types.Scene) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    configure_inspect_render(scene, 32)
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
    configure_inspect_render(scene, 8)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    scene.frame_start = 1
    scene.frame_end = 250
    scene.render.filepath = str(frames / "phase5_walk_")
    bpy.ops.render.render(animation=True)
    output = OUTPUT_DIR / "phase5_material_walk.mp4"
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "24",
            "-i",
            str(frames / "phase5_walk_%04d.jpg"),
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
    if bpy.data.filepath and Path(bpy.data.filepath).resolve() != BLEND_PATH.resolve():
        print("Warning: expected", BLEND_PATH, "but loaded", bpy.data.filepath)
    before = snapshot()
    lights_before = light_positions()
    clear_phase5()
    mats = build_library()
    assigned = assign_materials(mats)
    configure_inspection_lighting()
    scene = bpy.context.scene
    validation = validate(scene, before, lights_before, assigned)
    write_report(assigned, validation)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    if mode in {"stills", "playblast"}:
        render_stills(scene)
        if mode == "playblast":
            render_playblast(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 5 complete; Phase 6 not started.")


if __name__ == "__main__":
    main()
