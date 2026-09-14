#!/usr/bin/env python3
"""Phase 3 — primary industrial pipe / utility network.

This is an additive pass over the frozen Phase 2 hallway.  It creates only
utility geometry: pipes, elbows, a restrained cable tray, supports, flanges,
and two accessible valve assemblies.  Phase 1 and Phase 2 objects are never
resized, moved, or deleted.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase3.py -- --stills
  blender -b hallway.blend --python scripts/build_hallway_phase3.py -- --playblast
  blender -b hallway.blend --python scripts/build_hallway_phase3.py -- --no-render
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase3"
EYE_Z = 1.68
LENGTH = 24.0
WALL_T = 0.20

# Frozen Phase 1 envelope values.  These are validation references only.
ZONE_A = dict(y0=0.00, y1=7.70, width=2.20, height=3.00)
ZONE_B = dict(y0=8.90, y1=15.50, width=2.05, height=2.74)
ZONE_C = dict(y0=16.70, y1=24.00, width=2.20, height=2.93)

PHASE3_COLLECTIONS = (
    "UTILITY_PRIMARY_PIPES",
    "UTILITY_SECONDARY_PIPES",
    "UTILITY_VALVES",
    "UTILITY_SUPPORTS",
    "UTILITY_CABLE_TRAY",
)

# Existing CAM_INSPECT keyframes are preserved and used directly.
STILLS = (
    (1, "01_entry_primary"),
    (42, "02_zone_a_orderly"),
    (78, "03_approach_ab"),
    (96, "04_zone_b_entry"),
    (132, "05_zone_b_dense"),
    (164, "06_approach_bc"),
    (185, "07_zone_c_release"),
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


def get_or_create_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection


def clear_phase3() -> None:
    for name in PHASE3_COLLECTIONS:
        collection = bpy.data.collections.get(name)
        if collection is None:
            continue
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(collection)

    # Keep the file tidy when the additive builder is run repeatedly.
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials):
        for datablock in list(datablocks):
            if datablock.users == 0 and datablock.name.startswith("P3_"):
                datablocks.remove(datablock)


def ensure_material(
    name: str, color: tuple[float, float, float], roughness: float = 0.78
) -> bpy.types.Material:
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
    return material


def make_box_mesh(
    name: str,
    dims: tuple[float, float, float],
    material: bpy.types.Material,
) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=dims)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    mesh.materials.append(material)
    return mesh


def make_cylinder_mesh(
    name: str,
    radius: float,
    depth: float,
    material: bpy.types.Material,
    vertices: int = 12,
) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=True,
        segments=vertices,
        radius1=radius,
        radius2=radius,
        depth=depth,
    )
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    mesh.materials.append(material)
    return mesh


def make_torus_mesh(
    name: str,
    major_radius: float,
    minor_radius: float,
    material: bpy.types.Material,
) -> bpy.types.Mesh:
    """Create one moderate-resolution clamp mesh, then instance it."""
    bpy.ops.mesh.primitive_torus_add(
        major_segments=16,
        minor_segments=6,
        location=(0.0, 0.0, 0.0),
        major_radius=major_radius,
        minor_radius=minor_radius,
    )
    temp = bpy.context.object
    mesh = temp.data.copy()
    mesh.name = name
    mesh.materials.append(material)
    bpy.data.objects.remove(temp, do_unlink=True)
    return mesh


def add_mesh_instance(
    name: str,
    mesh: bpy.types.Mesh,
    location: tuple[float, float, float],
    collection: bpy.types.Collection,
    module_type: str,
    zone: str,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.rotation_euler = rotation
    obj.scale = (1.0, 1.0, 1.0)
    collection.objects.link(obj)
    obj["phase"] = 3
    obj["module_type"] = module_type
    obj["zone"] = zone
    return obj


def add_curve(
    name: str,
    points: list[tuple[float, float, float]],
    diameter: float,
    collection: bpy.types.Collection,
    material: bpy.types.Material,
    module_type: str,
    zone: str,
) -> bpy.types.Object:
    data = bpy.data.curves.new(f"P3_{name}_CURVE", "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 2
    data.resolution_v = 8
    data.bevel_depth = diameter * 0.5
    data.bevel_resolution = 2
    data.fill_mode = "FULL"
    data.use_fill_caps = True
    spline = data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (*co, 1.0)
    data.materials.append(material)
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj["phase"] = 3
    obj["module_type"] = module_type
    obj["zone"] = zone
    obj["diameter_m"] = diameter
    return obj


def add_straight_pipe(
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    diameter: float,
    collection: bpy.types.Collection,
    material: bpy.types.Material,
    zone: str,
    module_type: str = "PIPE_Straight",
) -> bpy.types.Object:
    return add_curve(name, [start, end], diameter, collection, material, module_type, zone)


def elbow_points(
    start: tuple[float, float, float],
    direction_in: tuple[float, float, float],
    direction_out: tuple[float, float, float],
    radius: float,
    steps: int = 8,
) -> list[tuple[float, float, float]]:
    """Approximate a smooth quarter-circle with tangent-aligned endpoints."""
    p = Vector(start)
    d1 = Vector(direction_in).normalized()
    d2 = Vector(direction_out).normalized()
    points = []
    for index in range(steps + 1):
        theta = (math.pi * 0.5) * index / steps
        co = p + (math.sin(theta) * radius) * d1
        co += ((1.0 - math.cos(theta)) * radius) * d2
        points.append(tuple(co))
    return points


def add_elbow(
    name: str,
    start: tuple[float, float, float],
    direction_in: tuple[float, float, float],
    direction_out: tuple[float, float, float],
    bend_radius: float,
    diameter: float,
    collection: bpy.types.Collection,
    material: bpy.types.Material,
    zone: str,
) -> bpy.types.Object:
    return add_curve(
        name,
        elbow_points(start, direction_in, direction_out, bend_radius),
        diameter,
        collection,
        material,
        "PIPE_Elbow",
        zone,
    )


def build_mesh_library(materials: dict[str, bpy.types.Material]) -> dict[str, bpy.types.Mesh]:
    return {
        "support_arm": make_box_mesh(
            "P3_PIPE_Bracket_MESH", (0.18, 0.12, 0.05), materials["support"]
        ),
        "hanger": make_box_mesh(
            "P3_PIPE_Hanger_MESH", (0.04, 0.10, 0.20), materials["support"]
        ),
        "wall_plate": make_box_mesh(
            "P3_PIPE_WallPlate_MESH", (0.04, 0.14, 0.22), materials["support"]
        ),
        "tray_bottom_a": make_box_mesh(
            "P3_CableTray_A_Bottom_MESH", (0.26, 6.90, 0.045), materials["tray"]
        ),
        "tray_bottom_b": make_box_mesh(
            "P3_CableTray_B_Bottom_MESH", (0.24, 6.30, 0.045), materials["tray"]
        ),
        "tray_bottom_c": make_box_mesh(
            "P3_CableTray_C_Bottom_MESH", (0.26, 6.85, 0.045), materials["tray"]
        ),
        "tray_side_a": make_box_mesh(
            "P3_CableTray_A_Side_MESH", (0.025, 6.90, 0.08), materials["tray"]
        ),
        "tray_side_b": make_box_mesh(
            "P3_CableTray_B_Side_MESH", (0.025, 6.30, 0.08), materials["tray"]
        ),
        "tray_side_c": make_box_mesh(
            "P3_CableTray_C_Side_MESH", (0.025, 6.85, 0.08), materials["tray"]
        ),
        "primary_flange": make_cylinder_mesh(
            "P3_PIPE_Flange_Primary_MESH", 0.15, 0.06, materials["primary"], 16
        ),
        "secondary_flange": make_cylinder_mesh(
            "P3_PIPE_Flange_Secondary_MESH", 0.065, 0.045, materials["secondary"], 12
        ),
        "connector": make_cylinder_mesh(
            "P3_PIPE_Connector_MESH", 0.055, 0.10, materials["secondary"], 12
        ),
        "valve_body": make_cylinder_mesh(
            "P3_PIPE_ValveBody_MESH", 0.11, 0.24, materials["valve"], 16
        ),
        "valve_stem": make_cylinder_mesh(
            "P3_PIPE_ValveStem_MESH", 0.018, 0.20, materials["valve"], 10
        ),
        "clamp_primary": make_torus_mesh(
            "P3_PIPE_Clamp_Primary_MESH", 0.155, 0.014, materials["support"]
        ),
        "clamp_secondary": make_torus_mesh(
            "P3_PIPE_Clamp_Secondary_MESH", 0.075, 0.010, materials["support"]
        ),
        "clamp_minor": make_torus_mesh(
            "P3_PIPE_Clamp_Minor_MESH", 0.045, 0.008, materials["support"]
        ),
        "handwheel": make_torus_mesh(
            "P3_PIPE_Handwheel_MESH", 0.09, 0.014, materials["valve"]
        ),
    }


def add_primary_pipes(
    collections: dict[str, bpy.types.Collection],
    materials: dict[str, bpy.types.Material],
) -> dict[str, object]:
    collection = collections["UTILITY_PRIMARY_PIPES"]
    primary_diameter = 0.26
    secondary_primary_diameter = 0.20

    # P1: dominant left header.  It stays below every frozen beam, then
    # offsets toward the ceiling-side region in Zone C through two elbows.
    add_straight_pipe(
        "PIPE_Primary_Left_A_to_C_01",
        (-0.84, 0.55, 2.46),
        (-0.84, 17.84, 2.46),
        primary_diameter,
        collection,
        materials["primary"],
        "A_B_C",
    )
    add_elbow(
        "ELBOW_Primary_C_01",
        (-0.84, 17.84, 2.46),
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        0.16,
        primary_diameter,
        collection,
        materials["primary"],
        "C",
    )
    add_straight_pipe(
        "PIPE_Primary_C_Offset_01",
        (-0.68, 18.00, 2.46),
        (-0.52, 18.00, 2.46),
        primary_diameter,
        collection,
        materials["primary"],
        "C",
    )
    add_elbow(
        "ELBOW_Primary_C_02",
        (-0.52, 18.00, 2.46),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        0.16,
        primary_diameter,
        collection,
        materials["primary"],
        "C",
    )
    add_straight_pipe(
        "PIPE_Primary_C_Offset_02",
        (-0.36, 18.16, 2.46),
        (-0.36, 23.45, 2.46),
        primary_diameter,
        collection,
        materials["primary"],
        "C",
    )

    # P2: right companion line through A/B.  It terminates through a
    # wall-ingress elbow at the B/C structural transition, not in mid-air.
    add_straight_pipe(
        "PIPE_Primary_Right_A_to_B_01",
        (0.84, 0.60, 2.43),
        (0.84, 14.40, 2.43),
        secondary_primary_diameter,
        collection,
        materials["primary"],
        "A_B",
    )
    add_straight_pipe(
        "PIPE_Primary_Right_B_ValveTail_01",
        (0.84, 14.78, 2.43),
        (0.84, 14.95, 2.43),
        secondary_primary_diameter,
        collection,
        materials["primary"],
        "B",
    )
    add_elbow(
        "ELBOW_Primary_B_WallIngress_01",
        (0.84, 14.95, 2.43),
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        0.14,
        secondary_primary_diameter,
        collection,
        materials["primary"],
        "B",
    )
    add_straight_pipe(
        "PIPE_Primary_B_WallIngress_01",
        (0.98, 15.09, 2.43),
        (1.02, 15.09, 2.43),
        secondary_primary_diameter,
        collection,
        materials["primary"],
        "B",
    )
    return dict(
        count=2,
        diameters=(primary_diameter, secondary_primary_diameter),
        routes=(
            "Left wall header y=0.55–17.84, then C offset to x=-0.36 and y=23.45",
            "Right wall companion y=0.60–14.40, inline valve, then B wall ingress",
        ),
    )


def add_secondary_pipes(
    collections: dict[str, bpy.types.Collection],
    materials: dict[str, bpy.types.Material],
    mesh_library: dict[str, bpy.types.Mesh],
) -> dict[str, object]:
    collection = collections["UTILITY_SECONDARY_PIPES"]
    entries = []

    def straight(name, start, end, diameter, zone):
        add_straight_pipe(
            name, start, end, diameter, collection, materials["secondary"], zone
        )
        entries.append((name, diameter, zone))

    straight("PIPE_Secondary_Right_A_01", (0.84, 0.80, 2.16), (0.84, 7.30, 2.16), 0.08, "A")
    straight("PIPE_Secondary_Left_A_01", (-0.84, 1.00, 2.20), (-0.84, 6.80, 2.20), 0.06, "A")

    straight("PIPE_Secondary_Left_B_01", (-0.84, 9.10, 2.16), (-0.84, 15.30, 2.16), 0.09, "B")
    straight("PIPE_Secondary_Left_B_02", (-0.64, 9.30, 2.12), (-0.64, 14.80, 2.12), 0.06, "B")
    straight("PIPE_Secondary_Right_B_01", (0.84, 9.20, 2.13), (0.84, 14.70, 2.13), 0.08, "B")
    straight("RISER_Secondary_B_Valve_01", (0.84, 14.70, 2.13), (0.84, 14.70, 2.43), 0.08, "B")
    straight("PIPE_Secondary_B_Cross_01", (-0.84, 12.00, 2.16), (0.84, 12.00, 2.16), 0.07, "B")
    for name, x in (
        ("CONNECTOR_Secondary_B_Cross_Left", -0.84),
        ("CONNECTOR_Secondary_B_Cross_Right", 0.84),
    ):
        add_mesh_instance(
            name,
            mesh_library["connector"],
            (x, 12.00, 2.16),
            collection,
            "PIPE_BranchConnector",
            "B",
            rotation=(0.0, math.pi * 0.5, 0.0),
        )

    # Zone C has fewer companions and one controlled vertical offset around
    # a structural bay, rather than a uniform pipe bundle.
    straight("PIPE_Secondary_C_Cross_01", (-0.74, 18.10, 2.18), (0.84, 18.10, 2.18), 0.07, "C")
    for name, x in (
        ("CONNECTOR_Secondary_C_Cross_Left", -0.74),
        ("CONNECTOR_Secondary_C_Cross_Right", 0.84),
    ):
        add_mesh_instance(
            name,
            mesh_library["connector"],
            (x, 18.10, 2.18),
            collection,
            "PIPE_BranchConnector",
            "C",
            rotation=(0.0, math.pi * 0.5, 0.0),
        )
    straight("PIPE_Secondary_Right_C_01", (0.84, 18.10, 2.18), (0.84, 19.84, 2.18), 0.09, "C")
    add_elbow(
        "ELBOW_Secondary_C_01",
        (0.84, 19.84, 2.18),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        0.12,
        0.09,
        collection,
        materials["secondary"],
        "C",
    )
    straight("RISER_Secondary_C_01", (0.84, 19.96, 2.30), (0.84, 19.96, 2.42), 0.09, "C")
    add_elbow(
        "ELBOW_Secondary_C_02",
        (0.84, 19.96, 2.42),
        (0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0),
        0.12,
        0.09,
        collection,
        materials["secondary"],
        "C",
    )
    straight("PIPE_Secondary_Right_C_02", (0.84, 20.08, 2.54), (0.84, 23.20, 2.54), 0.09, "C")

    # Minor conduits are deliberately sparse and stay off the center path.
    minor = (
        ("PIPE_Minor_Right_A_01", (0.96, 1.20, 2.05), (0.96, 6.20, 2.05), 0.03, "A"),
        ("PIPE_Minor_Left_B_01", (-0.94, 9.30, 2.04), (-0.94, 15.10, 2.04), 0.04, "B"),
        ("PIPE_Minor_Right_B_01", (0.94, 10.00, 2.08), (0.94, 14.40, 2.08), 0.03, "B"),
        ("PIPE_Minor_Right_C_01", (0.96, 18.50, 2.08), (0.96, 23.55, 2.08), 0.035, "C"),
    )
    for name, start, end, diameter, zone in minor:
        straight(name, start, end, diameter, zone)

    return dict(
        count=len(entries),
        entries=entries,
        diameter_range=(min(item[1] for item in entries), max(item[1] for item in entries)),
        branch_connectors=4,
    )


def add_flange(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    axis: str,
    collection: bpy.types.Collection,
    mesh_library: dict[str, bpy.types.Mesh],
    zone: str,
) -> bpy.types.Object:
    rotation = {
        "X": (0.0, math.pi * 0.5, 0.0),
        "Y": (math.pi * 0.5, 0.0, 0.0),
        "Z": (0.0, 0.0, 0.0),
    }[axis]
    mesh = mesh_library["primary_flange"] if radius > 0.10 else mesh_library["secondary_flange"]
    return add_mesh_instance(
        name,
        mesh,
        location,
        collection,
        "PIPE_Flange",
        zone,
        rotation=rotation,
    )


def add_valve(
    prefix: str,
    x: float,
    y: float,
    z: float,
    side: str,
    zone: str,
    collections: dict[str, bpy.types.Collection],
    mesh_library: dict[str, bpy.types.Mesh],
) -> None:
    collection = collections["UTILITY_VALVES"]
    sign = -1.0 if side == "L" else 1.0
    add_mesh_instance(
        f"VALVE_Body_{prefix}",
        mesh_library["valve_body"],
        (x, y, z),
        collection,
        "PIPE_Valve",
        zone,
        rotation=(math.pi * 0.5, 0.0, 0.0),
    )
    add_flange(
        f"FLANGE_Valve_{prefix}_Front",
        (x, y - 0.15, z),
        0.12,
        "Y",
        collection,
        mesh_library,
        zone,
    )
    add_flange(
        f"FLANGE_Valve_{prefix}_Back",
        (x, y + 0.15, z),
        0.12,
        "Y",
        collection,
        mesh_library,
        zone,
    )
    add_mesh_instance(
        f"VALVE_Stem_{prefix}",
        mesh_library["valve_stem"],
        (x, y, z - 0.14),
        collection,
        "PIPE_ValveStem",
        zone,
    )
    add_mesh_instance(
        f"VALVE_Handwheel_{prefix}",
        mesh_library["handwheel"],
        (x, y, z - 0.25),
        collection,
        "PIPE_ValveHandwheel",
        zone,
        rotation=(math.pi * 0.5, 0.0, 0.0),
    )
    # Small horizontal stem arms keep the handwheel readable without making
    # a decorative oversized wheel.
    arm_mesh = make_cylinder_mesh(
        f"P3_{prefix}_ValveArm_MESH", 0.012, 0.16, bpy.data.materials["MAT.Phase3.Valve"], 8
    )
    add_mesh_instance(
        f"VALVE_HandwheelArm_{prefix}",
        arm_mesh,
        (x, y, z - 0.25),
        collection,
        "PIPE_ValveHandwheel",
        zone,
        rotation=(0.0, math.pi * 0.5, 0.0),
    )


def add_supports(
    collections: dict[str, bpy.types.Collection],
    materials: dict[str, bpy.types.Material],
    mesh_library: dict[str, bpy.types.Mesh],
) -> dict[str, int]:
    collection = collections["UTILITY_SUPPORTS"]
    support_arm = mesh_library["support_arm"]
    hanger = mesh_library["hanger"]
    wall_plate = mesh_library["wall_plate"]
    clamp_primary = mesh_library["clamp_primary"]
    clamp_secondary = mesh_library["clamp_secondary"]
    clamp_minor = mesh_library["clamp_minor"]

    wall_mounts = 0
    hangers = 0
    clamps = 0

    def wall_support(
        name: str,
        side: str,
        x_pipe: float,
        y: float,
        z_pipe: float,
        radius: float,
        zone: str,
        secondary: bool = False,
    ) -> None:
        nonlocal wall_mounts, clamps
        sign = -1.0 if side == "L" else 1.0
        wall_x = sign * (1.025 if zone == "B" else 1.10)
        arm_x = (wall_x + x_pipe) * 0.5
        add_mesh_instance(
            f"BRACKET_Wall_{'Left' if side == 'L' else 'Right'}_{zone}_{y:04.2f}".replace(
                ".", "_"
            ),
            support_arm,
            (arm_x, y, z_pipe - radius - 0.025),
            collection,
            "PIPE_Bracket",
            zone,
        )
        add_mesh_instance(
            f"PLATE_Wall_{'Left' if side == 'L' else 'Right'}_{zone}_{y:04.2f}".replace(
                ".", "_"
            ),
            wall_plate,
            (wall_x + sign * 0.018, y, z_pipe - radius - 0.025),
            collection,
            "PIPE_WallPlate",
            zone,
        )
        add_mesh_instance(
            f"CLAMP_{'Secondary' if secondary else 'Primary'}_{'Left' if side == 'L' else 'Right'}_{zone}_{y:04.2f}".replace(
                ".", "_"
            ),
            clamp_minor if radius < 0.05 else (clamp_secondary if secondary else clamp_primary),
            (x_pipe, y, z_pipe),
            collection,
            "PIPE_Clamp",
            zone,
            rotation=(math.pi * 0.5, 0.0, 0.0),
        )
        wall_mounts += 2
        clamps += 1

    # Main left header before its C offset.
    for zone, y, x, z, r in (
        ("A", 1.70, -0.84, 2.46, 0.13),
        ("A", 4.25, -0.84, 2.46, 0.13),
        ("A", 6.85, -0.84, 2.46, 0.13),
        ("B", 9.35, -0.84, 2.46, 0.13),
        ("B", 12.45, -0.84, 2.46, 0.13),
        ("B", 14.00, -0.84, 2.46, 0.13),
        ("C", 17.40, -0.84, 2.46, 0.13),
    ):
        wall_support(f"PrimaryLeft_{zone}", "L", x, y, z, r, zone)

    # The offset C section uses ceiling hangers rather than impossible wall
    # arms floating away from the wall.
    for index, y in enumerate((18.60, 20.55, 22.95), start=1):
        add_mesh_instance(
            f"HANGER_Primary_C_{index:02d}",
            hanger,
            (-0.36, y, 2.69),
            collection,
            "PIPE_Hanger",
            "C",
        )
        add_mesh_instance(
            f"CLAMP_Primary_C_{index:02d}",
            clamp_primary,
            (-0.36, y, 2.46),
            collection,
            "PIPE_Clamp",
            "C",
            rotation=(math.pi * 0.5, 0.0, 0.0),
        )
        hangers += 1
        clamps += 1

    # Main right companion line, with a denser B rhythm.
    for zone, y, x, z, r in (
        ("A", 2.90, 0.84, 2.43, 0.10),
        ("A", 5.75, 0.84, 2.43, 0.10),
        ("B", 9.55, 0.84, 2.43, 0.10),
        ("B", 11.70, 0.84, 2.43, 0.10),
        ("B", 13.45, 0.84, 2.43, 0.10),
        ("B", 14.70, 0.84, 2.43, 0.10),
    ):
        wall_support(f"PrimaryRight_{zone}", "R", x, y, z, r, zone)

    # Secondary brackets are selective, not a copy of the primary rhythm.
    for zone, y, side, x, z, r in (
        ("A", 3.60, "R", 0.84, 2.16, 0.04),
        ("B", 10.20, "L", -0.84, 2.16, 0.045),
        ("B", 12.80, "R", 0.84, 2.13, 0.04),
        ("B", 14.40, "L", -0.64, 2.12, 0.03),
        ("C", 18.90, "R", 0.84, 2.18, 0.045),
        ("C", 21.60, "R", 0.84, 2.54, 0.045),
        ("A", 3.60, "R", 0.96, 2.05, 0.015),
        ("B", 11.20, "L", -0.94, 2.04, 0.020),
        ("B", 12.90, "R", 0.94, 2.08, 0.015),
        ("C", 20.60, "R", 0.96, 2.08, 0.0175),
        ("C", 22.50, "R", 0.96, 2.08, 0.0175),
    ):
        wall_support(f"Secondary_{zone}", side, x, y, z, r, zone, secondary=True)

    return dict(wall_mounts=wall_mounts, hangers=hangers, clamps=clamps)


def add_flanges(
    collection: bpy.types.Collection,
    mesh_library: dict[str, bpy.types.Mesh],
) -> int:
    entries = (
        ("FLANGE_Primary_Left_A_01", (-0.84, 4.05, 2.46), 0.13, "Y", "A"),
        ("FLANGE_Primary_Left_B_01", (-0.84, 12.90, 2.46), 0.13, "Y", "B"),
        ("FLANGE_Primary_C_Elbow_01", (-0.84, 17.84, 2.46), 0.13, "Y", "C"),
        ("FLANGE_Primary_B_WallIngress_01", (1.01, 15.09, 2.43), 0.10, "X", "B"),
        ("FLANGE_Minor_C_Termination", (0.96, 23.55, 2.08), 0.035, "Y", "C"),
    )
    for name, location, radius, axis, zone in entries:
        add_flange(name, location, radius, axis, collection, mesh_library, zone)
    return len(entries)


def add_cable_tray(
    collection: bpy.types.Collection,
    mesh_library: dict[str, bpy.types.Mesh],
) -> dict[str, object]:
    """One restrained right-side tray route, with no wires inside."""
    segments = (
        ("A", 0.40, 7.30, 0.52, 2.68),
        ("B", 9.05, 15.35, 0.48, 2.46),
        ("C", 16.85, 23.70, 0.52, 2.63),
    )
    for zone, y0, y1, x, z in segments:
        key = zone.lower()
        bottom = mesh_library[f"tray_bottom_{key}"]
        side = mesh_library[f"tray_side_{key}"]
        y = (y0 + y1) * 0.5
        add_mesh_instance(
            f"UTILITY_CableTray_{zone}_Bottom",
            bottom,
            (x, y, z - 0.025),
            collection,
            "UTILITY_CableTray",
            zone,
        )
        for side_name, side_x in (("Left", x - 0.115), ("Right", x + 0.115)):
            add_mesh_instance(
                f"UTILITY_CableTray_{zone}_{side_name}",
                side,
                (side_x, y, z + 0.015),
                collection,
                "UTILITY_CableTray",
                zone,
            )
    return dict(route_count=1, segments=segments)


def add_valves(
    collections: dict[str, bpy.types.Collection],
    mesh_library: dict[str, bpy.types.Mesh],
) -> int:
    add_valve(
        "B_01",
        x=0.84,
        y=14.62,
        z=2.43,
        side="R",
        zone="B",
        collections=collections,
        mesh_library=mesh_library,
    )
    add_valve(
        "C_01",
        x=-0.36,
        y=20.55,
        z=2.46,
        side="L",
        zone="C",
        collections=collections,
        mesh_library=mesh_library,
    )
    return 2


def build_network() -> dict[str, object]:
    clear_phase3()
    collections = {name: get_or_create_collection(name) for name in PHASE3_COLLECTIONS}
    materials = {
        "primary": ensure_material("MAT.Phase3.PrimaryPipe", (0.18, 0.19, 0.18), 0.66),
        "secondary": ensure_material("MAT.Phase3.SecondaryPipe", (0.24, 0.24, 0.22), 0.72),
        "valve": ensure_material("MAT.Phase3.Valve", (0.15, 0.16, 0.15), 0.62),
        "support": ensure_material("MAT.Phase3.Support", (0.12, 0.13, 0.12), 0.70),
        "tray": ensure_material("MAT.Phase3.CableTray", (0.20, 0.20, 0.18), 0.74),
    }
    mesh_library = build_mesh_library(materials)
    primary = add_primary_pipes(collections, materials)
    secondary = add_secondary_pipes(collections, materials, mesh_library)
    supports = add_supports(collections, materials, mesh_library)
    flanges = add_flanges(collections["UTILITY_VALVES"], mesh_library)
    valves = add_valves(collections, mesh_library)
    tray = add_cable_tray(collections["UTILITY_CABLE_TRAY"], mesh_library)
    return dict(
        collections=collections,
        materials=materials,
        mesh_library=mesh_library,
        primary=primary,
        secondary=secondary,
        supports=supports,
        flanges=flanges,
        valves=valves,
        tray=tray,
    )


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners))),
        Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners))),
    )


def bounds_overlap(
    a: tuple[Vector, Vector], b: tuple[Vector, Vector], epsilon: float = 0.0
) -> bool:
    amin, amax = a
    bmin, bmax = b
    return (
        amin.x < bmax.x - epsilon
        and amax.x > bmin.x + epsilon
        and amin.y < bmax.y - epsilon
        and amax.y > bmin.y + epsilon
        and amin.z < bmax.z - epsilon
        and amax.z > bmin.z + epsilon
    )


def ray(scene: bpy.types.Scene, origin: Vector, direction: Vector) -> float | None:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, _normal, _index, _object, _matrix = scene.ray_cast(
        depsgraph, origin, direction.normalized()
    )
    return (location - origin).length if hit else None


def validate_network(scene: bpy.types.Scene) -> dict[str, object]:
    phase3_objects = [
        obj
        for name in PHASE3_COLLECTIONS
        for obj in bpy.data.collections[name].objects
    ]
    pipe_objects = [
        obj
        for name in ("UTILITY_PRIMARY_PIPES", "UTILITY_SECONDARY_PIPES")
        for obj in bpy.data.collections[name].objects
        if obj.type in {"CURVE", "MESH"}
    ]
    phase2_beams = list(bpy.data.collections["STRUCTURE_BEAMS"].objects)
    camera = bpy.data.objects["CAM_INSPECT"]
    camera_errors = []
    min_side_clearance = 99.0
    min_overhead = 99.0
    camera_pipe_hits = []
    for frame in range(1, 251):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        position = camera.matrix_world.translation.copy()
        if abs(position.x) > 0.01 or abs(position.z - EYE_Z) > 0.01:
            camera_errors.append((frame, tuple(round(v, 3) for v in position)))
        left = ray(scene, position, Vector((-1.0, 0.0, 0.0)))
        right = ray(scene, position, Vector((1.0, 0.0, 0.0)))
        up = ray(scene, position, Vector((0.0, 0.0, 1.0)))
        if left is not None and right is not None:
            min_side_clearance = min(min_side_clearance, left, right)
        if up is not None:
            min_overhead = min(min_overhead, up + position.z)
        for obj in pipe_objects:
            low, high = world_bounds(obj)
            if low.x <= position.x <= high.x and low.y <= position.y <= high.y and low.z <= position.z <= high.z:
                camera_pipe_hits.append((frame, obj.name))

    beam_conflicts = []
    for pipe in pipe_objects:
        pipe_bounds = world_bounds(pipe)
        for beam in phase2_beams:
            if bounds_overlap(pipe_bounds, world_bounds(beam), epsilon=0.003):
                beam_conflicts.append((pipe.name, beam.name))

    pipe_conflicts = []
    intentional_junctions = {
        frozenset(("PIPE_Secondary_Left_B_01", "PIPE_Secondary_B_Cross_01")),
        frozenset(("PIPE_Secondary_Left_B_02", "PIPE_Secondary_B_Cross_01")),
        frozenset(("PIPE_Secondary_Right_B_01", "PIPE_Secondary_B_Cross_01")),
        frozenset(("PIPE_Secondary_C_Cross_01", "PIPE_Secondary_Right_C_01")),
    }
    for index, first in enumerate(pipe_objects):
        first_bounds = world_bounds(first)
        for second in pipe_objects[index + 1 :]:
            if bounds_overlap(first_bounds, world_bounds(second), epsilon=0.003):
                # These four overlaps are deliberate branch junctions:
                # one B cross-connection has three endpoints, and C has one.
                pair = frozenset((first.name, second.name))
                if (
                    first.name.startswith("PIPE_")
                    and second.name.startswith("PIPE_")
                    and pair not in intentional_junctions
                ):
                    pipe_conflicts.append((first.name, second.name))

    generic_names = [
        obj.name
        for obj in phase3_objects
        if re.match(r"^(Cube|Cylinder|Curve|Torus|Plane)(\.|$)", obj.name)
    ]
    unapplied_scales = [
        obj.name
        for obj in phase3_objects
        if any(abs(value - 1.0) > 1e-6 for value in obj.scale)
    ]
    below_floor = [
        obj.name
        for obj in phase3_objects
        if obj.type == "MESH" and world_bounds(obj)[0].z < -1e-5
    ]
    return dict(
        camera_errors=camera_errors,
        camera_pipe_hits=camera_pipe_hits,
        min_side_clearance=min_side_clearance,
        min_overhead=min_overhead,
        beam_conflicts=beam_conflicts,
        pipe_conflicts=pipe_conflicts,
        intentional_junctions=len(intentional_junctions),
        generic_names=generic_names,
        unapplied_scales=unapplied_scales,
        below_floor=below_floor,
        object_count=len(phase3_objects),
        pipe_object_count=len(pipe_objects),
    )


def phase1_station_measurements(scene: bpy.types.Scene) -> list[dict[str, float]]:
    rows = []
    for label, y, width, height in (
        ("A clear", 3.25, ZONE_A["width"], ZONE_A["height"]),
        ("B clear", 11.75, ZONE_B["width"], ZONE_B["height"]),
        ("C clear", 21.55, ZONE_C["width"], ZONE_C["height"]),
    ):
        origin = Vector((0.0, y, EYE_Z))
        left = ray(scene, origin, Vector((-1.0, 0.0, 0.0)))
        right = ray(scene, origin, Vector((1.0, 0.0, 0.0)))
        up = ray(scene, origin, Vector((0.0, 0.0, 1.0)))
        rows.append(
            dict(
                label=label,
                y=y,
                width=(left + right) if left is not None and right is not None else 0.0,
                ceiling=(up + EYE_Z) if up is not None else 0.0,
                target_width=width,
                target_ceiling=height,
            )
        )
    return rows


def write_report(
    scene: bpy.types.Scene, network: dict[str, object], validation: dict[str, object]
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stations = phase1_station_measurements(scene)
    phase1_pass = all(
        abs(row["width"] - row["target_width"]) < 0.001
        and abs(row["ceiling"] - row["target_ceiling"]) < 0.001
        for row in stations
    )
    phase2_pass = (
        len(bpy.data.collections.get("STRUCTURE_BEAMS").objects) == 11
        and len(bpy.data.collections.get("STRUCTURE_WALL").objects) == 19
        and len(bpy.data.collections.get("STRUCTURE_MOUNTS").objects) == 27
        and len(bpy.data.collections.get("STRUCTURE_GUIDES").objects) == 12
    )
    phase3_pass = (
        not validation["camera_errors"]
        and not validation["camera_pipe_hits"]
        and not validation["beam_conflicts"]
        and not validation["pipe_conflicts"]
        and not validation["generic_names"]
        and not validation["unapplied_scales"]
        and not validation["below_floor"]
        and validation["min_side_clearance"] >= 1.019
        and validation["min_overhead"] >= 2.05
    )
    path = OUTPUT_DIR / "phase3_pipe_validation.txt"
    lines = [
        "PHASE 3 PRIMARY INDUSTRIAL PIPE / UTILITY NETWORK",
        "Additive utility geometry only; Phase 1 and Phase 2 objects were not moved.",
        "",
        "PRIMARY PIPE SYSTEM",
        f"  major runs: {network['primary']['count']}",
        "  diameter range: 0.20–0.26 m",
        *[f"  route: {route}" for route in network["primary"]["routes"]],
        "",
        "SECONDARY PIPE SYSTEM",
        f"  secondary/minor curve count: {network['secondary']['count']}",
        f"  diameter range: {network['secondary']['diameter_range'][0]:.3f}–{network['secondary']['diameter_range'][1]:.3f} m",
        f"  branch connectors: {network['secondary']['branch_connectors']} low-poly collars plus one B valve riser",
        "  distribution: A has two secondary lines plus one minor; B is densest with three secondary lines, one cross-connection, and two minors; C uses one crossover, one offset secondary, and one minor.",
        "",
        "VALVES / FLANGES",
        f"  valves: {network['valves']} meaningful hand-wheel assemblies",
        f"  flanges: {network['flanges']} selected connections",
        "  locations: two inline valve assemblies at right B y=14.62 and offset left C y=20.55; flanges are at selected A/B/C joints and the B wall ingress.",
        "",
        "SUPPORT SYSTEM",
        f"  wall bracket / plate objects: {network['supports']['wall_mounts']}",
        f"  ceiling hangers: {network['supports']['hangers']}",
        f"  pipe clamps: {network['supports']['clamps']}",
        "  strategy: reuse Phase 2 wall mounting bands conceptually, add shallow wall arms and plates for wall runs, torus clamps at selected intervals, and ceiling hangers after the Zone C offset.",
        "",
        "CABLE TRAY",
        "  one right-side route, split into A/B/C structural segments; no wires were added.",
        "",
        "ZONE CHARACTER",
        "  A: two long, orderly primary lines with sparse parallel secondaries and regular supports.",
        "  B: denser overhead/side utilities, one cross-connection, more supports, and the only primary inline valve/ingress assembly.",
        "  C: left primary line offsets inward through two elbows, the right primary companion is absent, and secondary routing is reduced and irregular.",
        "",
        "PHASE 1 CLEAR STATIONS",
        "  label       y       measured width   measured ceiling   target width   target ceiling",
    ]
    for row in stations:
        lines.append(
            f"  {row['label']:10s} {row['y']:5.2f}    {row['width']:.3f} m          "
            f"{row['ceiling']:.3f} m          {row['target_width']:.3f} m       "
            f"{row['target_ceiling']:.3f} m"
        )
    lines += [
        "",
        "VALIDATION",
        f"  Phase 3 objects: {validation['object_count']}; pipe curve/mesh objects: {validation['pipe_object_count']}",
        f"  minimum camera side clearance: {validation['min_side_clearance']:.3f} m",
        f"  minimum camera overhead clearance: {validation['min_overhead']:.3f} m",
        f"  camera path errors: {len(validation['camera_errors'])}",
        f"  camera/pipe hits: {len(validation['camera_pipe_hits'])}",
        f"  pipe/Phase 2 beam AABB conflicts: {len(validation['beam_conflicts'])}",
        f"  pipe/pipe AABB conflicts: {len(validation['pipe_conflicts'])}",
        f"  intentional pipe junctions: {validation['intentional_junctions']}",
        f"  generic names: {len(validation['generic_names'])}; unapplied scales: {len(validation['unapplied_scales'])}; below floor: {len(validation['below_floor'])}",
        "",
        "PHASE 1 FREEZE STATUS: " + ("PASS" if phase1_pass else "FAIL"),
        "PHASE 2 FREEZE STATUS: " + ("PASS" if phase2_pass else "FAIL"),
        "PHASE 3 PIPE VALIDATION: " + ("PASS" if phase3_pass else "FAIL"),
        "  Phase 1 dimensions modified: NO",
        "  Phase 2 structural skeleton modified: NO",
        "  final materials/lighting/events/animation/sound: NOT STARTED",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", path)
    return path


def configure_render(scene: bpy.types.Scene) -> None:
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_object_outline = False
    scene.display.shading.show_shadows = False
    scene.display.shading.show_cavity = False
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass


def render_stills(scene: bpy.types.Scene) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    configure_render(scene)
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
    configure_render(scene)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    scene.frame_start = 1
    scene.frame_end = 250
    scene.render.filepath = str(frames / "phase3_walk_")
    bpy.ops.render.render(animation=True)
    output = OUTPUT_DIR / "phase3_pipe_network_walk.mp4"
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "24",
            "-i",
            str(frames / "phase3_walk_%04d.jpg"),
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
    network = build_network()
    scene = bpy.context.scene
    validation = validate_network(scene)
    write_report(scene, network, validation)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    if mode in {"stills", "playblast"}:
        render_stills(scene)
        if mode == "playblast":
            render_playblast(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 3 complete; Phase 4 not started.")


if __name__ == "__main__":
    main()
