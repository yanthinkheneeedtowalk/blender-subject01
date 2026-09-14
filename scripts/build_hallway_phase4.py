#!/usr/bin/env python3
"""Phase 4 — functional equipment and maintenance infrastructure.

This is an additive pass over the frozen Phase 3 hallway.  It explains a
small number of existing utility lines with cabinets, junction boxes, gauges,
one ventilation grille, service hatches, and short cable/conduit entries.
Previous phase geometry and the existing inspection camera are never moved.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase4.py -- --stills
  blender -b hallway.blend --python scripts/build_hallway_phase4.py -- --playblast
  blender -b hallway.blend --python scripts/build_hallway_phase4.py -- --no-render
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
OUTPUT_DIR = ROOT / "renders" / "hallway_phase4"
EYE_Z = 1.68

ZONE_A = dict(y0=0.00, y1=7.70, width=2.20, height=3.00)
ZONE_B = dict(y0=8.90, y1=15.50, width=2.05, height=2.74)
ZONE_C = dict(y0=16.70, y1=24.00, width=2.20, height=2.93)

PHASE4_COLLECTIONS = (
    "EQUIPMENT_ELECTRICAL",
    "EQUIPMENT_CONTROL",
    "EQUIPMENT_METERS",
    "EQUIPMENT_VENTILATION",
    "EQUIPMENT_SERVICE",
    "UTILITY_CABLES",
)

STILLS = (
    (1, "01_entry_function"),
    (42, "02_zone_a_equipment"),
    (78, "03_approach_ab"),
    (96, "04_zone_b_control"),
    (132, "05_zone_b_maintenance"),
    (164, "06_approach_bc"),
    (185, "07_zone_c_isolated"),
    (215, "08_zone_c_gauge"),
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


def collection(name: str) -> bpy.types.Collection:
    result = bpy.data.collections.get(name)
    if result is None:
        result = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(result)
    return result


def clear_phase4() -> None:
    for name in PHASE4_COLLECTIONS:
        col = bpy.data.collections.get(name)
        if col is None:
            continue
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials):
        for datablock in list(datablocks):
            if datablock.users == 0 and datablock.name.startswith("P4_"):
                datablocks.remove(datablock)


def material(
    name: str, color: tuple[float, float, float], roughness: float = 0.78
) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
    return mat


def box_mesh(name: str, dims: tuple[float, float, float], mat: bpy.types.Material) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=dims)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    mesh.materials.append(mat)
    return mesh


def cylinder_mesh(
    name: str,
    radius: float,
    depth: float,
    mat: bpy.types.Material,
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
    mesh.materials.append(mat)
    return mesh


def add_bevel(obj: bpy.types.Object, width: float = 0.012) -> None:
    bevel = obj.modifiers.new("Bevel_FunctionalEquipment", "BEVEL")
    bevel.width = width
    bevel.segments = 2
    bevel.limit_method = "ANGLE"


def instance(
    name: str,
    mesh: bpy.types.Mesh,
    loc: tuple[float, float, float],
    col: bpy.types.Collection,
    module_type: str,
    zone: str,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bevel_width: float | None = None,
    interface: bool = False,
    accessible_z: tuple[float, float] | None = None,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.rotation_euler = rotation
    obj.scale = (1.0, 1.0, 1.0)
    col.objects.link(obj)
    obj["phase"] = 4
    obj["module_type"] = module_type
    obj["zone"] = zone
    if interface:
        obj["functional_interface"] = True
    if accessible_z is not None:
        obj["accessible_z"] = accessible_z
    if bevel_width is not None:
        add_bevel(obj, bevel_width)
    return obj


def curve(
    name: str,
    points: list[tuple[float, float, float]],
    radius: float,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    zone: str,
    interface: bool = False,
) -> bpy.types.Object:
    data = bpy.data.curves.new(f"P4_{name}_CURVE", "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 2
    data.resolution_v = 6
    data.bevel_depth = radius
    data.bevel_resolution = 2
    data.fill_mode = "FULL"
    data.use_fill_caps = True
    spline = data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (*co, 1.0)
    data.materials.append(mat)
    obj = bpy.data.objects.new(name, data)
    col.objects.link(obj)
    obj["phase"] = 4
    obj["module_type"] = "MODULE_Conduit"
    obj["zone"] = zone
    if interface:
        obj["functional_interface"] = True
    return obj


def wall_info(zone: str, side: str) -> tuple[float, float]:
    half = {"A": ZONE_A["width"], "B": ZONE_B["width"], "C": ZONE_C["width"]}[zone] * 0.5
    sign = -1.0 if side == "L" else 1.0
    return sign * half, sign


def build_modules(mats: dict[str, bpy.types.Material]) -> dict[str, bpy.types.Mesh]:
    return {
        "box_s": box_mesh("P4_MODULE_ElectricalBox_S_MESH", (0.12, 0.34, 0.50), mats["body"]),
        "box_m": box_mesh("P4_MODULE_ControlCabinet_M_MESH", (0.16, 0.55, 0.85), mats["body"]),
        "box_l": box_mesh("P4_MODULE_ControlCabinet_L_MESH", (0.18, 0.65, 1.00), mats["body"]),
        "panel_s": box_mesh("P4_MODULE_ElectricalBox_S_Door_MESH", (0.014, 0.28, 0.42), mats["panel"]),
        "panel_m": box_mesh("P4_MODULE_ControlCabinet_M_Door_MESH", (0.014, 0.48, 0.72), mats["panel"]),
        "panel_l": box_mesh("P4_MODULE_ControlCabinet_L_Door_MESH", (0.014, 0.58, 0.86), mats["panel"]),
        "seam": box_mesh("P4_MODULE_CabinetDoorSeam_MESH", (0.008, 0.012, 0.70), mats["dark"]),
        "hinge": box_mesh("P4_MODULE_CabinetHinge_MESH", (0.025, 0.035, 0.10), mats["dark"]),
        "handle": box_mesh("P4_MODULE_CabinetHandle_MESH", (0.035, 0.025, 0.09), mats["metal"]),
        "indicator": box_mesh("P4_MODULE_CabinetIndicator_MESH", (0.012, 0.075, 0.035), mats["indicator"]),
        "cable_entry": box_mesh("P4_MODULE_CableEntry_MESH", (0.05, 0.08, 0.045), mats["dark"]),
        "hatch": box_mesh("P4_MODULE_ServiceHatch_MESH", (0.028, 0.58, 0.68), mats["body"]),
        "hatch_frame_v": box_mesh("P4_MODULE_ServiceHatchFrameV_MESH", (0.035, 0.045, 0.76), mats["metal"]),
        "hatch_frame_h": box_mesh("P4_MODULE_ServiceHatchFrameH_MESH", (0.035, 0.66, 0.045), mats["metal"]),
        "vent_body": box_mesh("P4_MODULE_VentBody_MESH", (0.045, 0.58, 0.36), mats["body"]),
        "vent_slat": box_mesh("P4_MODULE_VentSlat_MESH", (0.014, 0.46, 0.025), mats["dark"]),
        "gauge_body": cylinder_mesh("P4_MODULE_PressureGaugeBody_MESH", 0.10, 0.065, mats["metal"], 16),
        "gauge_face": cylinder_mesh("P4_MODULE_PressureGaugeFace_MESH", 0.082, 0.018, mats["panel"], 16),
        "gauge_needle": box_mesh("P4_MODULE_PressureGaugeNeedle_MESH", (0.010, 0.014, 0.060), mats["indicator"]),
        "gauge_bracket": box_mesh("P4_MODULE_PressureGaugeBracket_MESH", (0.08, 0.12, 0.04), mats["metal"]),
        "conduit_entry": cylinder_mesh("P4_MODULE_ConduitEntry_MESH", 0.022, 0.18, mats["cable"], 10),
    }


def cabinet(
    name: str,
    zone: str,
    side: str,
    y: float,
    z: float,
    size: str,
    col: bpy.types.Collection,
    meshes: dict[str, bpy.types.Mesh],
    mats: dict[str, bpy.types.Material],
    module_type: str,
) -> dict[str, float]:
    dims = {
        "s": (0.12, 0.34, 0.50),
        "m": (0.16, 0.55, 0.85),
        "l": (0.18, 0.65, 1.00),
    }[size]
    wall, sign = wall_info(zone, side)
    depth, width, height = dims
    body_x = wall - sign * depth * 0.5
    front_x = wall - sign * depth
    panel_mesh = meshes[f"panel_{size}"]
    body_collection = col
    accessible = (z - height * 0.5, z + height * 0.5)
    instance(
        name,
        meshes[f"box_{size}"],
        (body_x, y, z),
        body_collection,
        module_type,
        zone,
        bevel_width=0.014,
        accessible_z=accessible,
    )
    instance(
        f"{name}_DoorPanel",
        panel_mesh,
        (front_x - sign * 0.009, y, z),
        body_collection,
        "MODULE_CabinetDoor",
        zone,
        bevel_width=0.006,
        accessible_z=accessible,
    )
    seam_height = height - 0.10
    instance(
        f"{name}_DoorSeam",
        meshes["seam"],
        (front_x - sign * 0.018, y + width * 0.5 - 0.035, z),
        body_collection,
        "MODULE_CabinetDoorSeam",
        zone,
    )
    for index, hinge_z in enumerate((z - height * 0.28, z + height * 0.28), start=1):
        instance(
            f"{name}_Hinge_{index:02d}",
            meshes["hinge"],
            (front_x - sign * 0.020, y - width * 0.5 + 0.035, hinge_z),
            body_collection,
            "MODULE_CabinetHinge",
            zone,
        )
    instance(
        f"{name}_Handle",
        meshes["handle"],
        (front_x - sign * 0.024, y - width * 0.5 + 0.11, z),
        body_collection,
        "MODULE_CabinetHandle",
        zone,
    )
    instance(
        f"{name}_Indicator",
        meshes["indicator"],
        (front_x - sign * 0.020, y + width * 0.10, z + height * 0.27),
        body_collection,
        "MODULE_CabinetIndicator",
        zone,
    )
    instance(
        f"{name}_CableEntry",
        meshes["cable_entry"],
        (wall - sign * 0.035, y, z + height * 0.5 + 0.025),
        body_collection,
        "MODULE_CableEntry",
        zone,
        interface=True,
    )
    return dict(wall=wall, sign=sign, front_x=front_x, top=z + height * 0.5, center_z=z)


def add_cabinets(
    collections: dict[str, bpy.types.Collection],
    meshes: dict[str, bpy.types.Mesh],
    mats: dict[str, bpy.types.Material],
) -> dict[str, dict[str, float]]:
    anchors = {}
    anchors["A_junction"] = cabinet(
        "BOX_Junction_A_01", "A", "R", 3.20, 1.62, "s",
        collections["EQUIPMENT_ELECTRICAL"], meshes, mats, "MODULE_ElectricalBox_S",
    )
    anchors["B_control"] = cabinet(
        "CABINET_Control_B_01", "B", "R", 10.70, 1.36, "m",
        collections["EQUIPMENT_CONTROL"], meshes, mats, "MODULE_ControlCabinet_M",
    )
    anchors["B_service"] = cabinet(
        "CABINET_Service_B_02", "B", "R", 13.25, 1.28, "l",
        collections["EQUIPMENT_ELECTRICAL"], meshes, mats, "MODULE_ControlCabinet_L",
    )
    anchors["C_control"] = cabinet(
        "CABINET_Control_C_01", "C", "R", 19.35, 1.42, "m",
        collections["EQUIPMENT_CONTROL"], meshes, mats, "MODULE_ControlCabinet_M",
    )
    return anchors


def wall_gauge(
    name: str,
    zone: str,
    side: str,
    y: float,
    z: float,
    collections: dict[str, bpy.types.Collection],
    meshes: dict[str, bpy.types.Mesh],
) -> None:
    col = collections["EQUIPMENT_METERS"]
    wall, sign = wall_info(zone, side)
    axis_rotation = (0.0, math.pi * 0.5, 0.0)
    face_x = wall - sign * 0.085
    instance(
        name,
        meshes["gauge_body"],
        (wall - sign * 0.035, y, z),
        col,
        "MODULE_PressureGauge",
        zone,
        rotation=axis_rotation,
        bevel_width=0.006,
        accessible_z=(z - 0.10, z + 0.10),
    )
    instance(
        f"{name}_Face",
        meshes["gauge_face"],
        (face_x, y, z),
        col,
        "MODULE_PressureGaugeFace",
        zone,
        rotation=axis_rotation,
    )
    instance(
        f"{name}_Needle",
        meshes["gauge_needle"],
        (face_x - sign * 0.012, y, z + 0.008),
        col,
        "MODULE_PressureGaugeNeedle",
        zone,
    )
    instance(
        f"{name}_Bracket",
        meshes["gauge_bracket"],
        (wall - sign * 0.045, y, z - 0.13),
        col,
        "MODULE_PressureGaugeBracket",
        zone,
    )


def pipe_mounted_gauge(
    name: str,
    x: float,
    y: float,
    z: float,
    zone: str,
    collections: dict[str, bpy.types.Collection],
    meshes: dict[str, bpy.types.Mesh],
) -> None:
    col = collections["EQUIPMENT_METERS"]
    # Face points back toward the approaching player (-Y).
    rotation = (math.pi * 0.5, 0.0, 0.0)
    instance(
        name,
        meshes["gauge_body"],
        (x, y, z),
        col,
        "MODULE_PressureGauge",
        zone,
        rotation=rotation,
        bevel_width=0.006,
        interface=True,
        accessible_z=(z - 0.10, z + 0.10),
    )
    instance(
        f"{name}_Face",
        meshes["gauge_face"],
        (x, y - 0.045, z),
        col,
        "MODULE_PressureGaugeFace",
        zone,
        rotation=rotation,
    )
    instance(
        f"{name}_Needle",
        meshes["gauge_needle"],
        (x, y - 0.057, z + 0.008),
        col,
        "MODULE_PressureGaugeNeedle",
        zone,
    )
    instance(
        f"{name}_Bracket",
        meshes["gauge_bracket"],
        (x, y, z + 0.17),
        col,
        "MODULE_PressureGaugeBracket",
        zone,
        interface=True,
    )


def add_gauges(
    collections: dict[str, bpy.types.Collection],
    meshes: dict[str, bpy.types.Mesh],
) -> int:
    wall_gauge("GAUGE_Pressure_A_01", "A", "R", 3.78, 1.86, collections, meshes)
    wall_gauge("GAUGE_Pressure_B_01", "B", "R", 14.25, 1.86, collections, meshes)
    pipe_mounted_gauge("GAUGE_Pressure_C_01", -0.36, 20.55, 2.10, "C", collections, meshes)
    return 3


def add_service_hatch(
    name: str,
    zone: str,
    side: str,
    y: float,
    z: float,
    collections: dict[str, bpy.types.Collection],
    meshes: dict[str, bpy.types.Mesh],
) -> None:
    col = collections["EQUIPMENT_SERVICE"]
    wall, sign = wall_info(zone, side)
    depth = 0.028
    front = wall - sign * depth
    instance(
        name,
        meshes["hatch"],
        (wall - sign * depth * 0.5, y, z),
        col,
        "MODULE_ServiceHatch",
        zone,
        bevel_width=0.006,
        accessible_z=(z - 0.34, z + 0.34),
    )
    for suffix, yy in (("Left", y - 0.31), ("Right", y + 0.31)):
        instance(
            f"{name}_Frame_{suffix}",
            meshes["hatch_frame_v"],
            (front - sign * 0.010, yy, z),
            col,
            "MODULE_ServiceHatchFrame",
            zone,
        )
    for suffix, zz in (("Bottom", z - 0.36), ("Top", z + 0.36)):
        instance(
            f"{name}_Frame_{suffix}",
            meshes["hatch_frame_h"],
            (front - sign * 0.010, y, zz),
            col,
            "MODULE_ServiceHatchFrame",
            zone,
        )
    instance(
        f"{name}_Latch",
        meshes["handle"],
        (front - sign * 0.018, y + 0.20, z),
        col,
        "MODULE_ServiceHatchLatch",
        zone,
    )


def add_vent(
    collections: dict[str, bpy.types.Collection],
    meshes: dict[str, bpy.types.Mesh],
) -> int:
    col = collections["EQUIPMENT_VENTILATION"]
    zone = "B"
    wall, sign = wall_info(zone, "L")
    y, z = 12.05, 1.68
    front = wall - sign * 0.045
    instance(
        "VENT_Wall_B_01",
        meshes["vent_body"],
        (wall - sign * 0.0225, y, z),
        col,
        "MODULE_Vent",
        zone,
        bevel_width=0.008,
        accessible_z=(z - 0.18, z + 0.18),
    )
    for index, zz in enumerate((z - 0.10, z, z + 0.10), start=1):
        instance(
            f"VENT_Wall_B_01_Slat_{index:02d}",
            meshes["vent_slat"],
            (front - sign * 0.014, y, zz),
            col,
            "MODULE_VentSlat",
            zone,
        )
    return 1


def add_conduits(
    anchors: dict[str, dict[str, float]],
    collections: dict[str, bpy.types.Collection],
    mats: dict[str, bpy.types.Material],
    meshes: dict[str, bpy.types.Mesh],
) -> int:
    col = collections["UTILITY_CABLES"]
    entries = (
        ("CONDUIT_Junction_A_01", [(0.96, 3.20, 2.05), (0.96, 3.20, 1.86)], "A"),
        ("CONDUIT_Control_B_01", [(0.94, 10.70, 2.08), (0.94, 10.70, 1.81)], "B"),
        ("CONDUIT_Service_B_01", [(0.94, 13.25, 2.08), (0.94, 13.25, 1.79)], "B"),
        ("CONDUIT_Control_C_01", [(0.96, 19.35, 2.08), (0.96, 19.35, 1.87)], "C"),
    )
    for name, points, zone in entries:
        curve(name, points, 0.018, col, mats["cable"], zone, interface=True)
    # Short cabinet-to-wall cable entry sleeves, not a new cable network.
    for index, (name, zone, y, z) in enumerate(
        (
            ("CABLE_ENTRY_A_01", "A", 3.20, 1.86),
            ("CABLE_ENTRY_B_01", "B", 10.70, 1.81),
            ("CABLE_ENTRY_B_02", "B", 13.25, 1.79),
            ("CABLE_ENTRY_C_01", "C", 19.35, 1.87),
        ),
        start=1,
    ):
        instance(
            name,
            meshes["conduit_entry"],
            (0.975 if zone != "B" else 0.94, y, z),
            col,
            "MODULE_ConduitEntry",
            zone,
            rotation=(0.0, math.pi * 0.5, 0.0),
            interface=True,
        )
    return len(entries)


def bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners))),
        Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners))),
    )


def overlap(a: tuple[Vector, Vector], b: tuple[Vector, Vector], epsilon: float = 0.0) -> bool:
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


def validate(
    scene: bpy.types.Scene,
    equipment: dict[str, object],
) -> dict[str, object]:
    p4_objects = [
        obj
        for name in PHASE4_COLLECTIONS
        for obj in bpy.data.collections[name].objects
    ]
    p4_meshes = [obj for obj in p4_objects if obj.type == "MESH"]
    p3_objects = [
        obj
        for name in ("UTILITY_PRIMARY_PIPES", "UTILITY_SECONDARY_PIPES")
        for obj in bpy.data.collections[name].objects
        if obj.type in {"MESH", "CURVE"}
    ]
    p2_beams = list(bpy.data.collections["STRUCTURE_BEAMS"].objects)
    camera = bpy.data.objects["CAM_INSPECT"]
    camera_errors = []
    camera_hits = []
    min_side = 99.0
    min_walkable_width = 99.0
    min_overhead = 99.0
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
            min_side = min(min_side, left, right)
            min_walkable_width = min(min_walkable_width, left + right)
        if up is not None:
            min_overhead = min(min_overhead, up + position.z)
        for obj in p4_meshes:
            low, high = bounds(obj)
            if low.x <= position.x <= high.x and low.y <= position.y <= high.y and low.z <= position.z <= high.z:
                camera_hits.append((frame, obj.name))

    equipment_pipe_conflicts = []
    equipment_beam_conflicts = []
    for obj in p4_meshes:
        obj_bounds = bounds(obj)
        intentional = bool(obj.get("functional_interface"))
        for pipe in p3_objects:
            if overlap(obj_bounds, bounds(pipe), epsilon=0.003) and not intentional:
                equipment_pipe_conflicts.append((obj.name, pipe.name))
        for beam in p2_beams:
            if overlap(obj_bounds, bounds(beam), epsilon=0.003) and not intentional:
                equipment_beam_conflicts.append((obj.name, beam.name))

    generic_names = [
        obj.name
        for obj in p4_objects
        if re.match(r"^(Cube|Cylinder|Curve|Plane|Torus)(\.|$)", obj.name)
    ]
    unapplied_scales = [
        obj.name
        for obj in p4_objects
        if any(abs(value - 1.0) > 1e-6 for value in obj.scale)
    ]
    below_floor = [
        obj.name for obj in p4_meshes if bounds(obj)[0].z < -1e-5
    ]
    access_errors = []
    for obj in p4_objects:
        if "accessible_z" not in obj:
            continue
        low, high = obj["accessible_z"]
        if low < 0.20 or high > 2.20:
            access_errors.append((obj.name, low, high))

    # Measure the frozen Phase 1 envelope without letting new wall-mounted
    # equipment shorten the raycast. Restore all Phase 4 viewport states after
    # these three spatial checks.
    hidden_states = {obj.name: obj.hide_get() for obj in p4_objects}
    for obj in p4_objects:
        obj.hide_set(True)
    bpy.context.view_layer.update()
    station_rows = []
    for label, y, width, height in (
        ("A clear", 3.25, ZONE_A["width"], ZONE_A["height"]),
        ("B clear", 11.75, ZONE_B["width"], ZONE_B["height"]),
        ("C clear", 21.55, ZONE_C["width"], ZONE_C["height"]),
    ):
        origin = Vector((0.0, y, EYE_Z))
        left = ray(scene, origin, Vector((-1.0, 0.0, 0.0)))
        right = ray(scene, origin, Vector((1.0, 0.0, 0.0)))
        up = ray(scene, origin, Vector((0.0, 0.0, 1.0)))
        station_rows.append(
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
    return dict(
        camera_errors=camera_errors,
        camera_hits=camera_hits,
        min_side=min_side,
        min_walkable_width=min_walkable_width,
        min_overhead=min_overhead,
        equipment_pipe_conflicts=equipment_pipe_conflicts,
        equipment_beam_conflicts=equipment_beam_conflicts,
        generic_names=generic_names,
        unapplied_scales=unapplied_scales,
        below_floor=below_floor,
        access_errors=access_errors,
        stations=station_rows,
        object_count=len(p4_objects),
        mesh_count=len(p4_meshes),
    )


def write_report(
    scene: bpy.types.Scene,
    equipment: dict[str, object],
    validation: dict[str, object],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    phase1_pass = all(
        abs(row["width"] - row["target_width"]) < 0.001
        and abs(row["ceiling"] - row["target_ceiling"]) < 0.001
        for row in validation["stations"]
    )
    phase2_pass = all(
        len(bpy.data.collections[name].objects) == expected
        for name, expected in (
            ("STRUCTURE_BEAMS", 11),
            ("STRUCTURE_WALL", 19),
            ("STRUCTURE_MOUNTS", 27),
            ("STRUCTURE_GUIDES", 12),
        )
    )
    phase3_pass = all(
        bpy.data.collections[name].objects
        for name in ("UTILITY_PRIMARY_PIPES", "UTILITY_SECONDARY_PIPES", "UTILITY_SUPPORTS")
    )
    phase4_pass = (
        not validation["camera_errors"]
        and not validation["camera_hits"]
        and not validation["equipment_pipe_conflicts"]
        and not validation["equipment_beam_conflicts"]
        and not validation["generic_names"]
        and not validation["unapplied_scales"]
        and not validation["below_floor"]
        and not validation["access_errors"]
        and validation["min_walkable_width"] >= 1.75
        and validation["min_overhead"] >= 2.05
    )
    report = OUTPUT_DIR / "phase4_equipment_validation.txt"
    lines = [
        "PHASE 4 功能設備與維修基礎設施",
        "本次為增量設備階段；未移動 Phase 1、Phase 2、Phase 3 的任何既有物件。",
        "",
        "電氣設備",
        "  共 4 組具功能意義的控制櫃／接線盒：",
        "  BOX_Junction_A_01：Zone A 右牆 y=3.20",
        "  CABINET_Control_B_01：Zone B 右牆 y=10.70",
        "  CABINET_Service_B_02：Zone B 右牆 y=13.25",
        "  CABINET_Control_C_01：Zone C 右牆 y=19.35",
        "  每組包含櫃體、門板／門縫、鉸鏈、把手、指示區與電纜入口。",
        "",
        "管線接口",
        "  Zone A 右側次要 utility line 透過短垂直 conduit 接入 BOX_Junction_A_01。",
        "  Zone B 右側次要 utility line 接入 CABINET_Control_B_01；服務櫃另有平行電纜入口。",
        "  Zone C 右側次要 utility line 接入 CABINET_Control_C_01。",
        "  Zone C 壓力表安裝於既有偏置主管與閥件區域下方。",
        "",
        "壓力表／儀表",
        f"  共 {equipment['gauges']} 個：A 右牆 y=3.78、B 右牆 y=14.25、C 管線下掛式 y=20.55。",
        "",
        "通風",
        "  Zone B 左牆 y=12.05、z=1.68 設置 1 組克制的壁面通風格柵，含 3 條格柵片。",
        "",
        "電纜系統",
        f"  {equipment['conduits']} 組短 conduit 入口沿用 Phase 3 右側 cable tray／服務區域；未新增線束網路。",
        "",
        "維修艙門",
        "  共 2 個從屬式維修艙門：Zone B 左牆 y=10.20、Zone C 右牆 y=22.20，皆位於低位且可由人員操作。",
        "",
        "分區特徵",
        "  Zone A：單一小型接線盒、1 個壓力表與整齊的短 conduit 入口。",
        "  Zone B：2 組控制櫃、1 個壓力表、1 組通風格柵、2 個維修艙門，功能接口密度最高。",
        "  Zone C：孤立控制櫃、1 個管線下掛式壓力表與 1 個低位維修艙門，規律性降低但沒有損壞。",
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
        "第一人稱／幾何驗證",
        f"  Phase 4 新增物件：{validation['object_count']}；其中 mesh 物件：{validation['mesh_count']}",
        f"  相機最小單側淨空：{validation['min_side']:.3f} m",
        f"  設備周邊最小可行走寬度：{validation['min_walkable_width']:.3f} m",
        f"  相機最小上方淨空：{validation['min_overhead']:.3f} m",
        f"  相機路徑錯誤：{len(validation['camera_errors'])}",
        f"  相機／設備碰撞：{len(validation['camera_hits'])}",
        f"  設備／Phase 3 管線非預期衝突：{len(validation['equipment_pipe_conflicts'])}",
        f"  設備／Phase 2 樑架非預期衝突：{len(validation['equipment_beam_conflicts'])}",
        f"  可達高度錯誤：{len(validation['access_errors'])}",
        f"  泛用名稱：{len(validation['generic_names'])}；未套用縮放：{len(validation['unapplied_scales'])}；低於地面：{len(validation['below_floor'])}",
        "",
        "效能與模組化",
        "  控制櫃尺寸、門板、鉸鏈、把手、通風格柵、壓力表、艙門與 conduit 入口均重用 linked mesh。",
        "  僅製作中等細節輪廓；未加入最終材質、最終燈光、線束、垃圾、碎屑或破壞效果。",
        "",
        "PHASE 1 空間凍結狀態： " + ("PASS" if phase1_pass else "FAIL"),
        "PHASE 2 結構凍結狀態： " + ("PASS" if phase2_pass else "FAIL"),
        "PHASE 3 管線凍結狀態： " + ("PASS" if phase3_pass else "FAIL"),
        "PHASE 4 設備驗證： " + ("PASS" if phase4_pass else "FAIL"),
        "  Phase 1 尺寸是否修改：否",
        "  Phase 2 結構骨架是否修改：否",
        "  Phase 3 主管線路由是否修改：否",
        "  尚未開始 Phase 5。",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", report)
    return report


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
    scene.render.filepath = str(frames / "phase4_walk_")
    bpy.ops.render.render(animation=True)
    output = OUTPUT_DIR / "phase4_equipment_walk.mp4"
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "24",
            "-i",
            str(frames / "phase4_walk_%04d.jpg"),
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
    clear_phase4()
    cols = {name: collection(name) for name in PHASE4_COLLECTIONS}
    mats = {
        "body": material("MAT.Phase4.EquipmentBody", (0.25, 0.25, 0.23), 0.78),
        "panel": material("MAT.Phase4.EquipmentPanel", (0.16, 0.17, 0.16), 0.72),
        "metal": material("MAT.Phase4.EquipmentMetal", (0.32, 0.32, 0.29), 0.68),
        "dark": material("MAT.Phase4.EquipmentDark", (0.10, 0.11, 0.10), 0.80),
        "indicator": material("MAT.Phase4.Indicator", (0.38, 0.36, 0.28), 0.68),
        "cable": material("MAT.Phase4.Conduit", (0.18, 0.18, 0.17), 0.75),
    }
    meshes = build_modules(mats)
    anchors = add_cabinets(cols, meshes, mats)
    gauges = add_gauges(cols, meshes)
    add_service_hatch("HATCH_Service_B_01", "B", "L", 10.20, 0.78, cols, meshes)
    add_service_hatch("HATCH_Service_C_01", "C", "R", 22.20, 0.78, cols, meshes)
    vents = add_vent(cols, meshes)
    conduits = add_conduits(anchors, cols, mats, meshes)
    equipment = dict(anchors=anchors, gauges=gauges, vents=vents, conduits=conduits)
    scene = bpy.context.scene
    validation = validate(scene, equipment)
    write_report(scene, equipment, validation)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    if mode in {"stills", "playblast"}:
        render_stills(scene)
        if mode == "playblast":
            render_playblast(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 4 complete; Phase 5 not started.")


if __name__ == "__main__":
    main()
