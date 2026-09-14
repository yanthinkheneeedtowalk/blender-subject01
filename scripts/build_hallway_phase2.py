#!/usr/bin/env python3
"""Phase 2 — structural skeleton for the frozen Level 2 hallway.

This script loads the Phase 1 hallway and adds only restrained industrial
structure.  It intentionally does not rebuild, resize, or rematerial the
Phase 1 corridor.  No detailed pipes, final lighting, props, animation,
entities, or horror events are created here.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase2.py -- --stills
  blender -b hallway.blend --python scripts/build_hallway_phase2.py -- --playblast
  blender -b hallway.blend --python scripts/build_hallway_phase2.py -- --no-render
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase2"
EYE_Z = 1.68
LENGTH = 24.0
WALL_T = 0.20

# These are the frozen Phase 1 envelope values.  They are read here for
# validation only; Phase 2 never uses them to move Phase 1 geometry.
ZONE_A = dict(y0=0.00, y1=7.70, width=2.20, height=3.00)
ZONE_B = dict(y0=8.90, y1=15.50, width=2.05, height=2.74)
ZONE_C = dict(y0=16.70, y1=24.00, width=2.20, height=2.93)
TRANS_AB = dict(y0=7.70, y1=8.90)
TRANS_BC = dict(y0=15.50, y1=16.70)

PHASE2_COLLECTIONS = (
    "STRUCTURE_BEAMS",
    "STRUCTURE_WALL",
    "STRUCTURE_MOUNTS",
    "STRUCTURE_GUIDES",
)

STILLS = (
    (1, "01_entry_baseline"),
    (42, "02_zone_a_structure"),
    (78, "03_approach_ab"),
    (96, "04_zone_b_entry"),
    (132, "05_zone_b_dense"),
    (164, "06_approach_bc"),
    (185, "07_release_bc"),
    (215, "08_zone_c_irregular"),
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


def clear_phase2() -> None:
    for name in PHASE2_COLLECTIONS:
        collection = bpy.data.collections.get(name)
        if collection is None:
            continue
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(collection)


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
    """Make a clean unit-origin module mesh with applied dimensions."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=dims)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    mesh.materials.append(material)
    return mesh


def add_instance(
    name: str,
    mesh: bpy.types.Mesh,
    location: tuple[float, float, float],
    collection: bpy.types.Collection,
    module_type: str,
    zone: str,
    rotation_z: float = 0.0,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.rotation_euler = (0.0, 0.0, rotation_z)
    obj.scale = (1.0, 1.0, 1.0)
    collection.objects.link(obj)
    obj["phase"] = 2
    obj["module_type"] = module_type
    obj["zone"] = zone
    return obj


def build_module_meshes(materials: dict[str, bpy.types.Material]) -> dict[str, bpy.types.Mesh]:
    """Create one mesh per reusable module type; placements share these meshes."""
    return {
        "beam_a": make_box_mesh(
            "MODULE_CeilingBeam_A_MESH", (ZONE_A["width"] - 0.16, 0.16, 0.10), materials["structure"]
        ),
        "beam_b": make_box_mesh(
            "MODULE_CeilingBeam_B_MESH", (ZONE_B["width"] - 0.16, 0.14, 0.08), materials["structure"]
        ),
        "beam_c": make_box_mesh(
            "MODULE_CeilingBeam_C_MESH", (ZONE_C["width"] - 0.16, 0.18, 0.09), materials["structure"]
        ),
        # Only 1 mm of the rib face projects into the walkable envelope.
        "wall_support": make_box_mesh(
            "MODULE_WallSupport_MESH", (0.021, 0.14, 2.50), materials["structure"]
        ),
        "rail_short": make_box_mesh(
            "MODULE_UtilityRail_Short_MESH", (0.026, 0.62, 0.055), materials["mount"]
        ),
        "rail_long": make_box_mesh(
            "MODULE_UtilityRail_Long_MESH", (0.026, 1.05, 0.055), materials["mount"]
        ),
        "bracket": make_box_mesh(
            "MODULE_PipeMountBracket_MESH", (0.18, 0.12, 0.055), materials["mount"]
        ),
        "brace": make_box_mesh(
            "MODULE_CeilingSideBrace_MESH", (0.06, 0.14, 0.16), materials["mount"]
        ),
    }


def zone_at(y: float) -> str:
    if y < TRANS_AB["y0"]:
        return "A"
    if y < TRANS_AB["y1"]:
        return "TRANS_AB"
    if y < TRANS_BC["y0"]:
        return "B"
    if y < TRANS_BC["y1"]:
        return "TRANS_BC"
    return "C"


def add_ceiling_beams(
    collection: bpy.types.Collection, meshes: dict[str, bpy.types.Mesh]
) -> list[float]:
    """Place a controlled rhythm while leaving the Phase 1 envelope intact."""
    placements: list[tuple[str, float, float, str]] = []
    # A: orderly, approximately 2.5–2.7 m spacing.
    placements += [
        ("A", 1.70, 2.95, "01"),
        ("A", 4.25, 2.95, "02"),
        ("A", 6.85, 2.95, "03"),
    ]
    # B: denser and slightly shallower because the frozen ceiling is lower.
    placements += [
        ("B", 9.35, 2.70, "01"),
        ("B", 10.90, 2.70, "02"),
        ("B", 12.45, 2.70, "03"),
        ("B", 14.00, 2.70, "04"),
        ("B", 15.15, 2.70, "05"),
    ]
    # C: a more relaxed rhythm with small, controlled spacing variation.
    placements += [
        ("C", 17.85, 2.885, "01"),
        ("C", 20.55, 2.885, "02"),
        ("C", 22.95, 2.885, "03"),
    ]
    for zone, y, z, index in placements:
        mesh = meshes[f"beam_{zone.lower()}"]
        add_instance(
            f"BEAM_Ceiling_{zone}_{index}",
            mesh,
            (0.0, y, z - mesh.dimensions.z * 0.5),
            collection,
            "MODULE_CeilingBeam",
            zone,
        )
    return [y for _zone, y, _z, _index in placements]


def wall_rib_x(half_width: float, side: str) -> float:
    # Keep the visible face one millimetre inside the frozen walkable envelope.
    if side == "L":
        return -half_width - 0.0105
    return half_width + 0.0105


def add_wall_supports(
    collection: bpy.types.Collection, meshes: dict[str, bpy.types.Mesh]
) -> list[float]:
    placements = [
        # Zone A: regular paired supports.
        ("A", 2.15, ("L", "R")),
        ("A", 4.95, ("L", "R")),
        ("A", 7.20, ("L", "R")),
        # B: more frequent supports, but still flush to the existing walls.
        ("B", 9.65, ("L", "R")),
        ("B", 11.25, ("L", "R")),
        ("B", 12.85, ("L", "R")),
        ("B", 14.45, ("L", "R")),
        # C: alternating supports create depth without becoming a room sequence.
        ("C", 17.95, ("L",)),
        ("C", 19.45, ("R",)),
        ("C", 21.20, ("L", "R")),
        ("C", 23.10, ("R",)),
    ]
    for zone, y, sides in placements:
        width = {"A": ZONE_A["width"], "B": ZONE_B["width"], "C": ZONE_C["width"]}[zone]
        for side in sides:
            add_instance(
                f"SUPPORT_Wall_{'Left' if side == 'L' else 'Right'}_{zone}_{y:04.2f}".replace(
                    ".", "_"
                ),
                meshes["wall_support"],
                (wall_rib_x(width * 0.5, side), y, 1.35),
                collection,
                "MODULE_WallSupport",
                zone,
            )
    return [y for _zone, y, _sides in placements]


def add_utility_rails(
    collection: bpy.types.Collection, meshes: dict[str, bpy.types.Mesh]
) -> list[float]:
    placements = [
        # A: two restrained service rails.
        ("A", 2.90, "L", 2.30, "short"),
        ("A", 5.75, "R", 2.28, "long"),
        # B: more mounting infrastructure around the future pipe band.
        ("B", 9.55, "L", 2.22, "short"),
        ("B", 10.85, "R", 2.22, "short"),
        ("B", 12.15, "L", 2.22, "long"),
        ("B", 13.45, "R", 2.22, "short"),
        ("B", 14.70, "L", 2.22, "short"),
        # C: fewer rails, with a slight left/right imbalance.
        ("C", 18.35, "R", 2.42, "long"),
        ("C", 20.95, "L", 2.38, "short"),
        ("C", 22.75, "R", 2.44, "short"),
    ]
    for zone, y, side, z, length_key in placements:
        width = {"A": ZONE_A["width"], "B": ZONE_B["width"], "C": ZONE_C["width"]}[zone]
        half = width * 0.5
        side_sign = -1.0 if side == "L" else 1.0
        # Rails sit on the wall surface and stay above the eye line.
        x = side_sign * (half + 0.008)
        add_instance(
            f"MOUNT_UtilityRail_{'Left' if side == 'L' else 'Right'}_{zone}_{y:04.2f}".replace(
                ".", "_"
            ),
            meshes[f"rail_{length_key}"],
            (x, y, z),
            collection,
            "MODULE_UtilityMountRail",
            zone,
        )
    return [y for _zone, y, _side, _z, _length in placements]


def add_pipe_mounts(
    collection: bpy.types.Collection, meshes: dict[str, bpy.types.Mesh]
) -> list[float]:
    """Small support shoes only; no pipe geometry is created."""
    placements = [
        ("A", 1.70, "L", 2.48),
        ("A", 4.25, "R", 2.48),
        ("A", 6.85, "L", 2.48),
        ("B", 9.35, "L", 2.36),
        ("B", 10.90, "R", 2.36),
        ("B", 12.45, "L", 2.36),
        ("B", 14.00, "R", 2.36),
        ("B", 15.15, "L", 2.36),
        ("C", 17.85, "R", 2.54),
        ("C", 20.55, "L", 2.54),
        ("C", 22.95, "R", 2.54),
    ]
    for zone, y, side, z in placements:
        width = {"A": ZONE_A["width"], "B": ZONE_B["width"], "C": ZONE_C["width"]}[zone]
        half = width * 0.5
        side_sign = -1.0 if side == "L" else 1.0
        # The bracket extends only 18 cm from the wall, well above the path.
        x = side_sign * (half - 0.09)
        rotation = 0.0 if side == "L" else math.pi
        add_instance(
            f"MOUNT_Pipe_{'Left' if side == 'L' else 'Right'}_{zone}_{y:04.2f}".replace(
                ".", "_"
            ),
            meshes["bracket"],
            (x, y, z),
            collection,
            "MODULE_PipeMountBracket",
            zone,
            rotation_z=rotation,
        )
    return [y for _zone, y, _side, _z in placements]


def add_ceiling_side_braces(
    collection: bpy.types.Collection, meshes: dict[str, bpy.types.Mesh]
) -> None:
    # Braces sit beside, rather than below, the future longitudinal pipe bands.
    placements = (
        ("A", 3.55, -0.78, 2.84),
        ("A", 6.10, 0.78, 2.84),
        ("B", 10.15, -0.70, 2.57),
        ("B", 13.10, 0.70, 2.57),
        ("C", 18.95, -0.78, 2.77),
        ("C", 22.10, 0.78, 2.77),
    )
    for zone, y, x, z in placements:
        side = "L" if x < 0 else "R"
        add_instance(
            f"BRACE_CeilingSide_{side}_{zone}_{y:04.2f}".replace(".", "_"),
            meshes["brace"],
            (x, y, z),
            collection,
            "MODULE_CeilingSideBrace",
            zone,
        )


def add_pipe_guides(collection: bpy.types.Collection) -> list[dict[str, object]]:
    """Viewport-only reservation markers for Phase 3, not pipe geometry."""
    guides = (
        ("A", 0.40, 7.30, -0.86, 2.46, 0.18, "upper-left wall pipe band"),
        ("A", 0.40, 7.30, 0.86, 2.46, 0.18, "upper-right wall pipe band"),
        ("B", 9.05, 15.35, -0.80, 2.37, 0.16, "upper-left wall pipe band"),
        ("B", 9.05, 15.35, 0.80, 2.37, 0.16, "upper-right wall pipe band"),
        ("C", 16.85, 23.70, -0.86, 2.54, 0.18, "upper-left wall pipe band"),
        ("C", 16.85, 23.70, 0.86, 2.54, 0.18, "upper-right wall pipe band"),
        ("A", 0.40, 7.30, -0.52, 2.76, 0.16, "left ceiling-side cable tray"),
        ("A", 0.40, 7.30, 0.52, 2.76, 0.16, "right ceiling-side cable tray"),
        ("B", 9.05, 15.35, -0.48, 2.56, 0.14, "left ceiling-side cable tray"),
        ("B", 9.05, 15.35, 0.48, 2.56, 0.14, "right ceiling-side cable tray"),
        ("C", 16.85, 23.70, -0.52, 2.70, 0.16, "left ceiling-side cable tray"),
        ("C", 16.85, 23.70, 0.52, 2.70, 0.16, "right ceiling-side cable tray"),
    )
    result = []
    for zone, y0, y1, x, z, radius, purpose in guides:
        side = "Left" if x < 0 else "Right"
        kind = "Pipe" if "pipe" in purpose else "CableTray"
        empty = bpy.data.objects.new(f"GUIDE_{kind}Zone_{side}_{zone}", None)
        empty.empty_display_type = "CUBE"
        empty.empty_display_size = radius * 2.0
        empty.hide_render = True
        empty.location = (x, (y0 + y1) * 0.5, z)
        empty["phase"] = 2
        empty["reserved_for"] = purpose
        empty["y_start"] = y0
        empty["y_end"] = y1
        empty["clear_radius"] = radius
        empty["do_not_model_in_phase"] = "Phase 3 pipe/cable construction"
        collection.objects.link(empty)
        result.append(
            dict(zone=zone, y0=y0, y1=y1, x=x, z=z, radius=radius, purpose=purpose)
        )
    return result


def build_structure() -> dict[str, object]:
    clear_phase2()
    collections = {
        name: get_or_create_collection(name) for name in PHASE2_COLLECTIONS
    }
    materials = {
        "structure": ensure_material("MAT.Phase2.Structure", (0.29, 0.28, 0.26), 0.76),
        "mount": ensure_material("MAT.Phase2.Mount", (0.22, 0.22, 0.20), 0.74),
    }
    meshes = build_module_meshes(materials)
    beam_y = add_ceiling_beams(collections["STRUCTURE_BEAMS"], meshes)
    support_y = add_wall_supports(collections["STRUCTURE_WALL"], meshes)
    rail_y = add_utility_rails(collections["STRUCTURE_MOUNTS"], meshes)
    bracket_y = add_pipe_mounts(collections["STRUCTURE_MOUNTS"], meshes)
    add_ceiling_side_braces(collections["STRUCTURE_MOUNTS"], meshes)
    guides = add_pipe_guides(collections["STRUCTURE_GUIDES"])
    return dict(
        collections=collections,
        meshes=meshes,
        beam_y=beam_y,
        support_y=support_y,
        rail_y=rail_y,
        bracket_y=bracket_y,
        guides=guides,
    )


def ray(scene: bpy.types.Scene, origin: Vector, direction: Vector) -> float | None:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hit, location, _normal, _index, _object, _matrix = scene.ray_cast(
        depsgraph, origin, direction.normalized()
    )
    return (location - origin).length if hit else None


def sample_scale(scene: bpy.types.Scene) -> dict[str, object]:
    """Measure frozen clear stations and local structural clearance."""
    clear_stations = (
        ("A clear", 3.25, ZONE_A),
        ("B clear", 11.75, ZONE_B),
        ("C clear", 21.55, ZONE_C),
    )
    station_rows = []
    for label, y, zone in clear_stations:
        origin = Vector((0.0, y, EYE_Z))
        left = ray(scene, origin, Vector((-1.0, 0.0, 0.0)))
        right = ray(scene, origin, Vector((1.0, 0.0, 0.0)))
        up = ray(scene, origin, Vector((0.0, 0.0, 1.0)))
        down = ray(scene, origin, Vector((0.0, 0.0, -1.0)))
        station_rows.append(
            dict(
                label=label,
                y=y,
                width=(left + right) if left is not None and right is not None else None,
                ceiling=(up + EYE_Z) if up is not None else None,
                floor=down,
                expected_width=zone["width"],
                expected_ceiling=zone["height"],
            )
        )

    local_rows = []
    for i in range(0, 241):
        y = 0.25 + i * 0.098
        origin = Vector((0.0, y, EYE_Z))
        left = ray(scene, origin, Vector((-1.0, 0.0, 0.0)))
        right = ray(scene, origin, Vector((1.0, 0.0, 0.0)))
        up = ray(scene, origin, Vector((0.0, 0.0, 1.0)))
        if left is not None and right is not None and up is not None:
            local_rows.append((y, left + right, up + EYE_Z))
    return dict(stations=station_rows, local=local_rows)


def write_report(
    scene: bpy.types.Scene, structure: dict[str, object], measurements: dict[str, object]
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "phase2_structural_validation.txt"
    collections = structure["collections"]
    lines = [
        "PHASE 2 STRUCTURAL VALIDATION",
        "Phase 1 envelope preserved; no detailed pipes or final look added.",
        "",
        "COLLECTIONS",
        *[f"  {name}: {len(collections[name].objects)} objects" for name in PHASE2_COLLECTIONS],
        "",
        "REUSABLE MODULE MESHES",
        *[
            f"  {mesh.name}: shared by {sum(1 for obj in bpy.data.objects if obj.data == mesh)} instances"
            for mesh in structure["meshes"].values()
        ],
        "",
        "STRUCTURAL RHYTHM",
        f"  ceiling beam Y positions: {', '.join(f'{y:.2f}' for y in structure['beam_y'])}",
        f"  wall support Y positions: {', '.join(f'{y:.2f}' for y in structure['support_y'])}",
        f"  utility rail Y positions: {', '.join(f'{y:.2f}' for y in structure['rail_y'])}",
        "",
        "FROZEN CLEAR STATIONS",
        "  label       y       measured width   measured ceiling   target width   target ceiling",
    ]
    for row in measurements["stations"]:
        lines.append(
            f"  {row['label']:10s} {row['y']:5.2f}    {row['width']:.3f} m          "
            f"{row['ceiling']:.3f} m          {row['expected_width']:.3f} m       "
            f"{row['expected_ceiling']:.3f} m"
        )
    widths = [row[1] for row in measurements["local"]]
    clearances = [row[2] for row in measurements["local"]]
    lines += [
        "",
        "LOCAL STRUCTURE CHECK",
        f"  minimum sampled width at eye height: {min(widths):.3f} m",
        f"  minimum sampled overhead clearance from floor: {min(clearances):.3f} m",
        "",
        "PIPE / CABLE RESERVATIONS",
        *[
            f"  {guide['zone']} {guide['purpose']}: y={guide['y0']:.2f}–{guide['y1']:.2f}, "
            f"x={guide['x']:.2f}, z={guide['z']:.2f}, clear radius={guide['radius']:.2f} m"
            for guide in structure["guides"]
        ],
        "",
        "OBJECT RULES",
        "  Phase 1 objects were not resized or moved.",
        "  No doors, branches, rooms, detailed pipes, valves, props, final lights, or animation were added.",
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
    scene.render.filepath = str(frames / "phase2_walk_")
    bpy.ops.render.render(animation=True)
    output = OUTPUT_DIR / "phase2_structural_walk.mp4"
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "24",
            "-i",
            str(frames / "phase2_walk_%04d.jpg"),
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
    structure = build_structure()
    scene = bpy.context.scene
    measurements = sample_scale(scene)
    report = write_report(scene, structure, measurements)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    if mode in {"stills", "playblast"}:
        render_stills(scene)
        if mode == "playblast":
            render_playblast(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 2 complete; Phase 3 not started.")


if __name__ == "__main__":
    main()
