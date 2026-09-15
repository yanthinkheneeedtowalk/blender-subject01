#!/usr/bin/env python3
"""Phase 8 — hero environment geometry and micro-detail polish.

Additive construction / installation detail over the frozen Phase 1–7
corridor.  Macro layout, primary routing, equipment anchors, materials,
aging, and Phase 7 lighting behaviour are not redesigned.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase8.py -- --no-render
  blender -b hallway.blend --python scripts/build_hallway_phase8.py -- --stills
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_hallway_phase5 as p5
import build_hallway_phase7 as p7

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase8"
EYE_Z = p5.EYE_Z
ZONE_A = p5.ZONE_A
ZONE_B = p5.ZONE_B
ZONE_C = p5.ZONE_C
PHASE2_COUNTS = p5.PHASE2_COUNTS
PHASE4_COLLECTIONS = p5.PHASE4_COLLECTIONS
LIBRARY = p5.LIBRARY
P8_PREFIXES = ("P8_", "CAM_HERO_")
COLLECTIONS = (
    "POLISH_WALLS",
    "POLISH_FLOOR",
    "POLISH_PIPES",
    "POLISH_EQUIPMENT",
    "POLISH_SUPPORTS",
    "POLISH_FIXTURES",
    "POLISH_CAMERAS",
)

STILLS = (
    ("SHOT_A_zone_a_establishment", "CAM_HERO_A"),
    ("SHOT_B_zone_b_density", "CAM_HERO_B"),
    ("SHOT_C_zone_c_isolation", "CAM_HERO_C"),
    ("REVIEW_entrance", "CAM_INSPECT", 1),
    ("REVIEW_trans_ab", "CAM_INSPECT", 78),
    ("REVIEW_trans_bc", "CAM_INSPECT", 164),
    ("REVIEW_zone_c", "CAM_INSPECT", 185),
    ("REVIEW_lookback", "CAM_HERO_LOOKBACK"),
)

XA, XB, XC = 1.10, 1.025, 1.10


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--no-render" in argv:
        return "check"
    return "stills"


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def wall_x(zone: str, side: str) -> float:
    half = {"A": XA, "B": XB, "C": XC}[zone]
    return -half if side == "L" else half


def interior_offset(zone: str, side: str, inset: float = 0.004) -> float:
    x = wall_x(zone, side)
    return x + (-inset if side == "R" else inset)


def box_mesh(name: str, dims: tuple[float, float, float]) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=dims)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def cylinder_mesh(name: str, radius: float, depth: float, segments: int = 12) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius,
        depth=depth,
    )
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def torus_mesh(name: str, major: float, minor: float, major_n: int = 14, minor_n: int = 6) -> bpy.types.Mesh:
    bpy.ops.mesh.primitive_torus_add(
        major_segments=major_n,
        minor_segments=minor_n,
        location=(0.0, 0.0, 0.0),
        major_radius=major,
        minor_radius=minor,
    )
    temp = bpy.context.object
    mesh = temp.data.copy()
    mesh.name = name
    bpy.data.objects.remove(temp, do_unlink=True)
    return mesh


def bolt_mesh() -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new("P8_BOLT_MESH")
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=6, radius1=0.007, radius2=0.007, depth=0.010
    )
    geom = bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=8, radius1=0.004, radius2=0.004, depth=0.016
    )
    bmesh.ops.translate(bm, verts=geom["verts"], vec=(0.0, 0.0, -0.011))
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return mesh


def assign(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def shade_smooth(obj: bpy.types.Object) -> None:
    try:
        obj.data.shade_smooth()
    except Exception:
        pass


def add_bevel(obj: bpy.types.Object, width: float = 0.0025) -> None:
    if any(mod.name == "Bevel_P8" for mod in obj.modifiers):
        return
    mod = obj.modifiers.new("Bevel_P8", "BEVEL")
    mod.width = width
    mod.segments = 2
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(30.0)


def place(
    name: str,
    mesh: bpy.types.Mesh,
    loc,
    col: bpy.types.Collection,
    mat: bpy.types.Material,
    scale=(1.0, 1.0, 1.0),
    rot=(0.0, 0.0, 0.0),
    bevel: float | None = None,
    smooth: bool = False,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    obj.scale = scale
    obj.rotation_euler = rot
    obj["phase"] = 8
    assign(obj, mat)
    col.objects.link(obj)
    if bevel:
        add_bevel(obj, bevel)
    if smooth:
        shade_smooth(obj)
    return obj


def mat_or(name: str, fallback: str, color, rough: float, metal: float = 0.0) -> bpy.types.Material:
    existing = bpy.data.materials.get(name) or bpy.data.materials.get(fallback)
    if existing is not None and existing.name == name:
        return existing
    if existing is not None and name not in bpy.data.materials:
        # Build a small dedicated polish material rather than mutating Phase 5.
        pass
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    return mat


def build_materials() -> dict[str, bpy.types.Material]:
    return {
        "wall": bpy.data.materials["MAT_Wall_PaintedConcrete"],
        "floor": bpy.data.materials["MAT_Floor_IndustrialConcrete"],
        "steel": bpy.data.materials["MAT_Metal_Galvanized"],
        "pipe": bpy.data.materials["MAT_Pipe_DarkPaintedSteel"],
        "pipe2": bpy.data.materials["MAT_Pipe_Secondary"],
        "cabinet": bpy.data.materials["MAT_Cabinet_PaintedMetal"],
        "rubber": bpy.data.materials["MAT_Rubber_Dark"],
        "accent": bpy.data.materials["MAT_Valve_IndustrialAccent"],
        "nameplate": mat_or("MAT_P8_Nameplate", "", (0.42, 0.41, 0.37), 0.46, 0.55),
        "weld": mat_or("MAT_P8_Weld", "", (0.16, 0.15, 0.14), 0.58, 0.72),
        "tube": mat_or("MAT_P8_Tube", "", (0.78, 0.82, 0.80), 0.28, 0.05),
        "tube_weak": mat_or("MAT_P8_TubeWeak", "", (0.74, 0.76, 0.62), 0.38, 0.04),
        "damp": mat_or("MAT_P8_Damp", "", (0.12, 0.13, 0.12), 0.34, 0.0),
    }


def clear_phase8() -> None:
    seen = set()
    for name in COLLECTIONS:
        col = bpy.data.collections.get(name)
        if col is None:
            continue
        for obj in list(col.objects):
            if obj.name in seen:
                continue
            seen.add(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    for obj in list(bpy.data.objects):
        if obj.name.startswith("CAM_HERO_"):
            bpy.data.objects.remove(obj, do_unlink=True)
        if obj.name.startswith("FIX_") and "Bevel_P8" in obj.modifiers:
            obj.modifiers.remove(obj.modifiers["Bevel_P8"])
    for mat in list(bpy.data.materials):
        if mat.name.startswith("MAT_P8_"):
            bpy.data.materials.remove(mat)
    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith("P8_") and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def meshes() -> dict[str, bpy.types.Mesh]:
    return {
        "seam_v": box_mesh("P8_SEAM_V", (0.007, 0.012, 1.0)),
        "seam_h": box_mesh("P8_SEAM_H", (0.007, 1.0, 0.010)),
        "patch": box_mesh("P8_PATCH", (0.006, 0.22, 0.16)),
        "remnant": box_mesh("P8_REMNANT_PLATE", (0.008, 0.07, 0.09)),
        "skirt": box_mesh("P8_SKIRT", (0.018, 1.0, 0.028)),
        "joint": box_mesh("P8_FLOOR_JOINT", (1.0, 0.012, 0.004)),
        "floor_patch": box_mesh("P8_FLOOR_PATCH", (0.28, 0.42, 0.005)),
        "crack": box_mesh("P8_FLOOR_CRACK", (0.22, 0.004, 0.003)),
        "damp": cylinder_mesh("P8_DAMP", 0.11, 0.003, 10),
        "form_tie": cylinder_mesh("P8_FORM_TIE", 0.011, 0.008, 8),
        "collar": cylinder_mesh("P8_COLLAR", 0.16, 0.036, 14),
        "collar_s": cylinder_mesh("P8_COLLAR_S", 0.12, 0.030, 12),
        "collar_plate": box_mesh("P8_COLLAR_PLATE", (0.22, 0.012, 0.22)),
        "weld_p": torus_mesh("P8_WELD_PRIMARY", 0.132, 0.0036),
        "weld_s": torus_mesh("P8_WELD_SECONDARY", 0.042, 0.0028),
        "weld_m": torus_mesh("P8_WELD_MED", 0.102, 0.0032),
        "band": torus_mesh("P8_ID_BAND", 0.134, 0.008, 16, 6),
        "band_s": torus_mesh("P8_ID_BAND_S", 0.104, 0.007, 14, 6),
        "bolt": bolt_mesh(),
        "plate_bolt": cylinder_mesh("P8_PLATE_BOLT", 0.006, 0.010, 6),
        "name_a": box_mesh("P8_NAMEPLATE_A", (0.004, 0.10, 0.036)),
        "name_b": box_mesh("P8_NAMEPLATE_B", (0.004, 0.13, 0.042)),
        "name_c": box_mesh("P8_NAMEPLATE_C", (0.004, 0.11, 0.034)),
        "foot": box_mesh("P8_CAB_FOOT", (0.04, 0.04, 0.018)),
        "gland": cylinder_mesh("P8_GLAND", 0.016, 0.028, 10),
        "button": cylinder_mesh("P8_BUTTON", 0.009, 0.008, 10),
        "knockout": cylinder_mesh("P8_KNOCKOUT", 0.012, 0.004, 10),
        "hasp": box_mesh("P8_HASP", (0.012, 0.018, 0.034)),
        "latch": box_mesh("P8_LATCH_BODY", (0.016, 0.028, 0.022)),
        "clip": box_mesh("P8_FIXTURE_CLIP", (0.018, 0.012, 0.010)),
        "tube": cylinder_mesh("P8_TUBE", 0.016, 1.0, 10),
        "mount_plate": box_mesh("P8_FIXTURE_MOUNT", (0.05, 0.05, 0.008)),
        "washer": cylinder_mesh("P8_HANGER_NUT", 0.014, 0.008, 8),
        "vent_slot": box_mesh("P8_CAB_SLOT", (0.004, 0.09, 0.008)),
    }


def polish_walls(ms, mats) -> int:
    col = collection("POLISH_WALLS")
    n = 0
    # Vertical pour / panel joints. Irregular, not a full grid. Quiet spans remain.
    vertical = (
        ("A", "L", 1.18, 2.55),
        ("A", "L", 3.92, 2.55),
        ("A", "L", 6.38, 2.55),
        ("A", "R", 2.08, 2.55),
        ("A", "R", 5.12, 2.55),
        ("B", "L", 9.82, 2.32),
        ("B", "L", 12.58, 2.32),
        ("B", "R", 11.38, 2.32),
        ("C", "L", 18.42, 2.48),
        ("C", "L", 21.78, 2.48),
        ("C", "R", 20.72, 2.48),
    )
    for zone, side, y, height in vertical:
        x = interior_offset(zone, side)
        place(
            f"P8_SEAM_V_{zone}_{side}_{y:.2f}".replace(".", "_"),
            ms["seam_v"],
            (x, y, height * 0.5 + 0.03),
            col,
            mats["wall"],
            scale=(1.0, 1.0, height),
        )
        n += 1
    # Horizontal lift joints only in selected bays (poured in two lifts).
    horizontals = (
        ("A", "L", 1.55, 0.95, 1.22),
        ("B", "L", 13.85, 1.15, 1.16),
        ("C", "R", 17.95, 1.05, 1.20),
    )
    for zone, side, y, length, z in horizontals:
        x = interior_offset(zone, side)
        place(
            f"P8_SEAM_H_{zone}_{side}_{y:.2f}".replace(".", "_"),
            ms["seam_h"],
            (x, y, z),
            col,
            mats["wall"],
            scale=(1.0, length, 1.0),
        )
        n += 1
    patches = (
        ("A", "R", 5.62, 1.42, 1.15, 1.10),
        ("B", "L", 10.88, 0.82, 0.90, 0.85),
        ("C", "L", 21.12, 1.36, 1.05, 0.95),
    )
    for zone, side, y, z, sy, sz in patches:
        x = interior_offset(zone, side, 0.003)
        place(
            f"P8_PATCH_{zone}_{side}_{y:.2f}".replace(".", "_"),
            ms["patch"],
            (x, y, z),
            col,
            mats["wall"],
            scale=(1.0, sy, sz),
        )
        n += 1
    remnants = (
        ("A", "L", 7.08, 1.88),
        ("B", "R", 12.22, 1.72),
        ("C", "R", 17.58, 1.54),
    )
    for zone, side, y, z in remnants:
        x = interior_offset(zone, side, 0.005)
        place(
            f"P8_REMNANT_{zone}_{side}_{y:.2f}".replace(".", "_"),
            ms["remnant"],
            (x, y, z),
            col,
            mats["steel"],
            bevel=0.0015,
        )
        n += 1
    ties = (
        ("A", "L", 2.55, 1.55),
        ("A", "R", 6.05, 1.90),
        ("B", "L", 14.15, 1.40),
        ("B", "R", 9.60, 1.68),
        ("C", "L", 19.85, 1.22),
    )
    for zone, side, y, z in ties:
        x = interior_offset(zone, side, 0.003)
        rot = (0.0, math.pi * 0.5, 0.0)
        place(
            f"P8_FORMTIE_{zone}_{side}_{y:.2f}".replace(".", "_"),
            ms["form_tie"],
            (x, y, z),
            col,
            mats["wall"],
            rot=rot,
            smooth=True,
        )
        n += 1
    capped = (
        ("A", "R", 4.42, 2.02, 0.016),
        ("B", "L", 13.92, 1.70, 0.018),
        ("C", "L", 19.02, 1.98, 0.014),
    )
    for zone, side, y, z, r in capped:
        x = interior_offset(zone, side, 0.008)
        place(
            f"P8_CAPPED_{zone}_{side}_{y:.2f}".replace(".", "_"),
            ms["gland"],
            (x, y, z),
            col,
            mats["steel"],
            scale=(r / 0.016, r / 0.016, 1.15),
            rot=(0.0, math.pi * 0.5, 0.0),
            smooth=True,
            bevel=0.001,
        )
        n += 1
    return n


def polish_floor(ms, mats) -> int:
    col = collection("POLISH_FLOOR")
    n = 0
    # Saw-cut control joints, irregular, aligned loosely with wall pours.
    joints = (2.35, 5.72, 8.28, 11.08, 14.88, 17.62, 20.92)
    widths = {2.35: 2.05, 5.72: 2.05, 8.28: 1.95, 11.08: 1.90, 14.88: 1.90, 17.62: 2.05, 20.92: 2.05}
    for y in joints:
        w = widths[y]
        place(
            f"P8_FLOOR_JOINT_{y:.2f}".replace(".", "_"),
            ms["joint"],
            (0.02 if y in {11.08, 20.92} else 0.0, y, 0.002),
            col,
            mats["floor"],
            scale=(w, 1.0, 1.0),
        )
        n += 1
    place("P8_FLOOR_PATCH_B", ms["floor_patch"], (0.16, 12.28, 0.0025), col, mats["floor"], scale=(0.85, 0.70, 1.0))
    place("P8_FLOOR_PATCH_C", ms["floor_patch"], (-0.22, 19.72, 0.0025), col, mats["floor"], scale=(0.55, 0.48, 1.0))
    n += 2
    place("P8_FLOOR_CRACK_A", ms["crack"], (0.34, 4.18, 0.002), col, mats["floor"], rot=(0.0, 0.0, 0.22))
    place("P8_FLOOR_CRACK_B", ms["crack"], (-0.28, 13.05, 0.002), col, mats["floor"], rot=(0.0, 0.0, -0.35), scale=(1.35, 1.0, 1.0))
    n += 2
    place("P8_DAMP_B_VALVE", ms["damp"], (0.42, 14.70, 0.0018), col, mats["damp"], smooth=True, scale=(0.85, 1.15, 1.0))
    place("P8_DAMP_C", ms["damp"], (-0.18, 21.25, 0.0018), col, mats["damp"], smooth=True, scale=(0.55, 0.70, 1.0))
    n += 2
    skirts = (
        ("A", "R", 1.15, 1.10),
        ("B", "L", 10.35, 0.85),
        ("C", "R", 18.95, 0.95),
        ("C", "L", 22.35, 0.90),
    )
    for zone, side, y, length in skirts:
        x = interior_offset(zone, side, 0.010)
        place(
            f"P8_SKIRT_{zone}_{side}_{y:.2f}".replace(".", "_"),
            ms["skirt"],
            (x, y, 0.014),
            col,
            mats["floor"],
            scale=(1.0, length, 1.0),
        )
        n += 1
    return n


def ring_bolts(prefix, origin, axis: str, radius: float, count: int, skip: int | None, ms, mats, col) -> int:
    ox, oy, oz = origin
    n = 0
    for i in range(count):
        if skip is not None and i == skip:
            continue
        ang = (2.0 * math.pi * i) / count
        if axis == "Y":
            loc = (ox + radius * math.cos(ang), oy, oz + radius * math.sin(ang))
            rot = (math.pi * 0.5, 0.0, 0.0)
        else:
            loc = (ox, oy + radius * math.cos(ang), oz + radius * math.sin(ang))
            rot = (0.0, math.pi * 0.5, 0.0)
        place(f"{prefix}_{i:02d}", ms["bolt"], loc, col, mats["steel"], rot=rot, smooth=True)
        n += 1
    return n


def polish_pipes(ms, mats) -> int:
    col = collection("POLISH_PIPES")
    n = 0
    # Hero-visible flange bolts. Distant joints stay as existing discs.
    n += ring_bolts("P8_BOLT_FLANGE_A", (-0.84, 4.05, 2.46), "Y", 0.168, 8, None, ms, mats, col)
    n += ring_bolts("P8_BOLT_FLANGE_B", (-0.84, 12.90, 2.46), "Y", 0.168, 8, None, ms, mats, col)
    n += ring_bolts("P8_BOLT_VALVE_B_F", (0.84, 14.47, 2.43), "Y", 0.148, 8, None, ms, mats, col)
    n += ring_bolts("P8_BOLT_VALVE_B_B", (0.84, 14.77, 2.43), "Y", 0.148, 8, 5, ms, mats, col)
    n += ring_bolts("P8_BOLT_INGRESS_B", (1.01, 15.09, 2.43), "X", 0.132, 8, None, ms, mats, col)
    n += ring_bolts("P8_BOLT_ELBOW_C", (-0.84, 17.84, 2.46), "Y", 0.168, 8, 2, ms, mats, col)
    n += ring_bolts("P8_BOLT_VALVE_C", (-0.36, 20.55, 2.46), "Y", 0.148, 6, None, ms, mats, col)
    welds = (
        ("P8_WELD_A_FLANGE", ms["weld_p"], (-0.84, 3.96, 2.46), (math.pi * 0.5, 0.0, 0.0)),
        ("P8_WELD_B_CROSS_L", ms["weld_s"], (-0.84, 12.00, 2.16), (0.0, math.pi * 0.5, 0.0)),
        ("P8_WELD_B_CROSS_R", ms["weld_s"], (0.84, 12.00, 2.16), (0.0, math.pi * 0.5, 0.0)),
        ("P8_WELD_B_VALVE", ms["weld_m"], (0.84, 14.32, 2.43), (math.pi * 0.5, 0.0, 0.0)),
        ("P8_WELD_C_ELBOW", ms["weld_p"], (-0.84, 17.72, 2.46), (math.pi * 0.5, 0.0, 0.0)),
        ("P8_WELD_C_CROSS", ms["weld_s"], (0.84, 18.10, 2.18), (0.0, math.pi * 0.5, 0.0)),
        ("P8_WELD_C_VALVE", ms["weld_m"], (-0.36, 20.42, 2.46), (math.pi * 0.5, 0.0, 0.0)),
    )
    for name, mesh, loc, rot in welds:
        place(name, mesh, loc, col, mats["weld"], rot=rot, smooth=True)
        n += 1
    # Wall penetration collars: start-wall implication is skipped; real ingress only.
    place(
        "P8_COLLAR_B_INGRESS",
        ms["collar_s"],
        (1.018, 15.09, 2.43),
        col,
        mats["steel"],
        rot=(0.0, math.pi * 0.5, 0.0),
        smooth=True,
        bevel=0.002,
    )
    place(
        "P8_COLLAR_B_INGRESS_PLATE",
        ms["collar_plate"],
        (1.028, 15.09, 2.43),
        col,
        mats["steel"],
        rot=(0.0, 0.0, 0.0),
        scale=(0.55, 1.0, 0.85),
        bevel=0.002,
    )
    n += 2
    bands = (
        ("P8_BAND_A_LEFT", ms["band"], (-0.84, 2.82, 2.46), mats["accent"]),
        ("P8_BAND_B_RIGHT", ms["band_s"], (0.84, 11.82, 2.43), mats["rubber"]),
        ("P8_BAND_C_OFFSET", ms["band"], (-0.36, 22.35, 2.46), mats["rubber"]),
    )
    for name, mesh, loc, mat in bands:
        place(name, mesh, loc, col, mat, rot=(math.pi * 0.5, 0.0, 0.0), smooth=True)
        n += 1
    return n


def polish_equipment(ms, mats) -> int:
    col = collection("POLISH_EQUIPMENT")
    n = 0
    # Blank nameplate holders for later Phase 9 artwork.
    plates = (
        ("P8_NAME_A", ms["name_a"], (0.966, 3.20, 1.78)),
        ("P8_NAME_B_CTRL", ms["name_b"], (0.846, 10.70, 1.68)),
        ("P8_NAME_B_SVC", ms["name_b"], (0.821, 13.25, 1.62), (1.15, 1.10, 1.0)),
        ("P8_NAME_C", ms["name_c"], (0.916, 19.42, 1.72)),
    )
    for item in plates:
        name, mesh, loc = item[0], item[1], item[2]
        scale = item[3] if len(item) > 3 else (1.0, 1.0, 1.0)
        place(name, mesh, loc, col, mats["nameplate"], scale=scale, bevel=0.001)
        n += 1
    feet = (
        ("A", 0.975, 3.04, 1.36),
        ("A", 0.975, 3.36, 1.36),
        ("B", 0.945, 10.46, 0.925),
        ("B", 0.945, 10.94, 0.925),
        ("B2", 0.935, 12.96, 0.77),
        ("B2", 0.935, 13.54, 0.77),
        ("C", 1.020, 19.11, 0.985),
        ("C", 1.020, 19.59, 0.985),
    )
    for tag, x, y, z in feet:
        place(f"P8_FOOT_{tag}_{y:.2f}".replace(".", "_"), ms["foot"], (x, y, z), col, mats["steel"], bevel=0.0015)
        n += 1
    glands = (
        (0.975, 3.20, 1.90, "A"),
        (0.940, 10.58, 1.805, "B"),
        (0.935, 13.08, 1.805, "B2"),
        (0.935, 13.42, 1.805, "B2b"),
        (1.020, 19.35, 1.875, "C"),
    )
    for x, y, z, tag in glands:
        place(
            f"P8_GLAND_{tag}",
            ms["gland"],
            (x, y, z),
            col,
            mats["rubber"],
            rot=(0.0, 0.0, 0.0),
            smooth=True,
        )
        n += 1
    # Zone B control: two industrial pushbuttons. C gets an unused knockout instead.
    place("P8_BTN_B_01", ms["button"], (0.845, 10.62, 1.50), col, mats["accent"], rot=(0.0, math.pi * 0.5, 0.0), smooth=True)
    place("P8_BTN_B_02", ms["button"], (0.845, 10.78, 1.50), col, mats["steel"], rot=(0.0, math.pi * 0.5, 0.0), smooth=True)
    place("P8_KNOCK_C", ms["knockout"], (0.920, 19.52, 1.28), col, mats["cabinet"], rot=(0.0, math.pi * 0.5, 0.0), smooth=True)
    place("P8_HASP_B", ms["hasp"], (0.821, 13.12, 1.18), col, mats["steel"], bevel=0.001)
    place("P8_LATCH_B", ms["latch"], (0.821, 13.12, 1.16), col, mats["steel"], bevel=0.001)
    n += 5
    place("P8_SLOT_B_01", ms["vent_slot"], (0.845, 10.70, 1.08), col, mats["cabinet"])
    place("P8_SLOT_B_02", ms["vent_slot"], (0.845, 10.70, 1.10), col, mats["cabinet"])
    n += 2
    return n


def polish_supports(ms, mats) -> int:
    col = collection("POLISH_SUPPORTS")
    n = 0
    # Bolts on hero-visible wall plates only.
    plates = (
        ("A_L_4_25", -1.082, 4.25, 2.305),
        ("A_R_2_90", 1.082, 2.90, 2.305),
        ("B_L_12_45", -1.007, 12.45, 2.305),
        ("B_R_13_45", 1.007, 13.45, 2.275),
        ("B_L_14_00", -1.007, 14.00, 2.305),
        ("C_L_17_40", -1.082, 17.40, 2.305),
    )
    for tag, x, y, z in plates:
        for i, dy, dz in ((1, -0.018, 0.022), (2, 0.018, -0.022)):
            place(
                f"P8_PLATEBOLT_{tag}_{i}",
                ms["plate_bolt"],
                (x, y + dy, z + dz),
                col,
                mats["steel"],
                rot=(0.0, math.pi * 0.5, 0.0),
                smooth=True,
            )
            n += 1
    for i, y in enumerate((18.60, 20.55, 22.95), start=1):
        place(f"P8_HANGER_NUT_{i:02d}", ms["washer"], (-0.36, y, 2.585), col, mats["steel"], smooth=True)
        n += 1
    return n


def polish_fixtures(ms, mats) -> int:
    col = collection("POLISH_FIXTURES")
    n = 0
    for spec in p7.CEILING_FIXTURES:
        name, zone, y, z, length, x, energy, _color, _cut, _spread = spec
        state = p7.state_of(name)
        # Mounting plates at stem tops, and clips on the housing.
        stem_len = {"A": 0.14, "B": 0.07, "C": 0.12}[zone]
        housing_z = z + 0.028
        plate_z = housing_z + 0.024 + stem_len + 0.004
        for side, sy in (("N", y + length * 0.48), ("S", y - length * 0.48)):
            place(
                f"P8_FIXPLATE_{name}_{side}",
                ms["mount_plate"],
                (x, sy, plate_z),
                col,
                mats["steel"],
                bevel=0.001,
            )
            place(
                f"P8_FIXCLIP_{name}_{side}",
                ms["clip"],
                (x, sy, z + 0.016),
                col,
                mats["steel"],
                bevel=0.001,
            )
            n += 2
        if energy > 0.0:
            tube_mat = mats["tube_weak"] if state in {"WEAK", "AGED_TINT"} else mats["tube"]
            place(
                f"P8_TUBE_{name}",
                ms["tube"],
                (x, y, z + 0.006),
                col,
                tube_mat,
                scale=(1.0, 1.0, length * 0.86),
                rot=(math.pi * 0.5, 0.0, 0.0),
                smooth=True,
            )
            n += 1
    for spec in p7.WALL_FIXTURES:
        name, zone, x, y, z, yaw, energy, _c, _cut, state = spec
        inward = -0.048 if yaw > 0 else 0.048
        place(
            f"P8_WALLCLIP_{name}",
            ms["clip"],
            (x + inward * 0.2, y + 0.07, z + 0.05),
            col,
            mats["steel"],
            bevel=0.001,
        )
        n += 1
    # Restrain existing fixture edges without moving them.
    for obj in bpy.data.objects:
        if not obj.name.startswith("FIX_"):
            continue
        if any(token in obj.name for token in ("Housing", "Cap", "Stem")):
            add_bevel(obj, 0.0028)
    return n


def aim_camera(name: str, loc, target, lens: float = 32.0) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.sensor_width = 36.0
    data.sensor_fit = "HORIZONTAL"
    data.clip_start = 0.06
    data.clip_end = 40.0
    cam = bpy.data.objects.new(name, data)
    cam.location = loc
    direction = Vector(target) - Vector(loc)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam["phase"] = 8
    collection("POLISH_CAMERAS").objects.link(cam)
    return cam


def add_hero_cameras() -> list[str]:
    # First-person, existing composition. Architecture is not moved to invent shots.
    aim_camera("CAM_HERO_A", (0.18, 1.92, 1.62), (0.62, 4.35, 1.48), 30.0)
    aim_camera("CAM_HERO_B", (0.16, 11.42, 1.60), (0.48, 14.55, 1.55), 28.0)
    aim_camera("CAM_HERO_C", (0.20, 18.05, 1.62), (0.42, 21.15, 1.50), 30.0)
    aim_camera("CAM_HERO_LOOKBACK", (0.08, 21.15, 1.66), (0.0, 12.4, 1.55), 32.0)
    return ["CAM_HERO_A", "CAM_HERO_B", "CAM_HERO_C", "CAM_HERO_LOOKBACK"]


def light_signature() -> dict[str, tuple]:
    rows = {}
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        data = obj.data
        rows[obj.name] = (
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
            round(float(data.energy), 4),
            tuple(round(c, 4) for c in data.color),
            round(float(getattr(data, "cutoff_distance", 0.0)), 4),
        )
    return rows


def fixture_signature() -> dict[str, tuple]:
    rows = {}
    for obj in bpy.data.objects:
        if not obj.name.startswith("FIX_"):
            continue
        rows[obj.name] = (
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
            tuple(round(v, 5) for v in obj.scale),
        )
    return rows


def is_core(name: str) -> bool:
    return not name.startswith(P8_PREFIXES)


def validate(scene, before, lights_before, fixtures_before, counts) -> dict:
    after = p5.snapshot()
    original = {k: v for k, v in before.items() if is_core(k)}
    after_core = {k: v for k, v in after.items() if is_core(k)}
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
    hide_list = [
        obj
        for obj in bpy.data.objects
        if obj.name.startswith(P8_PREFIXES)
        or obj.name.startswith("MARK_")
        or obj.name.startswith("FIX_")
        or (obj.users_collection and any(c.name.startswith("POLISH_") for c in obj.users_collection))
        or (obj.users_collection and any(c.name in PHASE4_COLLECTIONS for c in obj.users_collection))
    ]
    hidden = {obj.name: obj.hide_get() for obj in hide_list}
    for obj in hide_list:
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
    for obj in hide_list:
        obj.hide_set(hidden.get(obj.name, False))
    bpy.context.view_layer.update()
    lights_after = light_signature()
    light_changed = [name for name, row in lights_before.items() if lights_after.get(name) != row]
    fixtures_after = fixture_signature()
    fixture_moved = [name for name, row in fixtures_before.items() if fixtures_after.get(name) != row]
    p8_count = len([o for o in bpy.data.objects if o.name.startswith("P8_")])
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
        library_ok=all(bpy.data.materials.get(name) for name in LIBRARY),
        aging_ok=bpy.data.node_groups.get("P6_NG_AgingMasks") is not None,
        markings=len([o for o in bpy.data.objects if o.name.startswith("MARK_")]),
        light_changed=light_changed,
        fixture_moved=fixture_moved,
        p8_count=p8_count,
        p8_meshes=len([m for m in bpy.data.meshes if m.name.startswith("P8_")]),
        counts=counts,
        hero_cams=all(bpy.data.objects.get(n) for n in ("CAM_HERO_A", "CAM_HERO_B", "CAM_HERO_C")),
        inspect_is_camera=scene.camera.name == "CAM_INSPECT" if scene.camera else False,
    )


def write_report(validation: dict) -> Path:
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
    phase7_pass = not validation["light_changed"] and not validation["fixture_moved"]
    phase8_pass = (
        phase1_pass
        and phase2_pass
        and phase3_pass
        and phase4_pass
        and phase5_pass
        and phase6_pass
        and phase7_pass
        and not validation["camera_errors"]
        and not validation["added_core"]
        and validation["hero_cams"]
        and validation["p8_count"] > 40
    )
    c = validation["counts"]
    lines = [
        "PHASE 8 英雄環境幾何與微細節打磨",
        "未改變走廊長度、Zone 尺寸、主管路由、主要設備錨點、材質庫、老化或 Phase 7 燈光行為。",
        "Phase 7 燈具位置／能量不變；僅為 FIX_ housing／端蓋／吊桿加上 Bevel_P8 倒角。",
        "",
        "WALL POLISH",
        "  細節：不規則垂直澆置／板塊接縫、局部水平分層縫、三處修補塊、三處拆除殘件、五處模板拉桿孔、三處封堵穿管。",
        "  建造邏輯：接縫對應可澆置的板塊與兩層澆置，不是整牆程序化格子。大面積安靜牆面保留。",
        f"  物件：{c['walls']}",
        "",
        "FLOOR POLISH",
        "  細節：七條不規則鋸切伸縮縫、兩處淺修補、兩條細裂縫、兩處極小潮濕斑、四段不連續牆腳積垢。",
        "  接觸：牆腳裙邊不連續，避免一條均勻 AO 黑線。無大水窪、無鏡面。",
        f"  物件：{c['floor']}",
        "",
        "PIPE POLISH",
        "  法蘭螺栓：A 左 y=4.05、B 左 y=12.90、B 閥前後、B 穿牆、C 彎頭、C 閥（C 閥 6 顆，B 閥後側缺 1 顆）。",
        "  焊縫：選定真實接頭的細環，不誇張。",
        "  穿牆：B 右牆 ingress 加套管＋牆板。",
        "  識別環：A 左主管、B 右伴管、C 偏移段（幾何環，無文字 decal）。",
        f"  物件：{c['pipes']}",
        "",
        "EQUIPMENT POLISH",
        "  空白銘牌座、櫃腳、額外 cable gland、B 控制櫃按鈕、B 維修櫃搭扣、C 未使用封口、兩道通風槽。",
        "  無內部電子、無科幻面板。",
        f"  物件：{c['equipment']}",
        "",
        "SUPPORT HARDWARE",
        "  僅英雄可見牆板加螺栓；C 段吊架加螺帽／墊圈。",
        f"  物件：{c['supports']}",
        "",
        "LIGHT FIXTURE GEOMETRY",
        "  吊點底板、夾片、ON／WEAK 燈管剪影。OFF 保持空燈槽。",
        "  既有 FIX_ 物件加 2.8 mm 倒角，不改位置、尺度、燈光能量。",
        f"  新增物件：{c['fixtures']}",
        "",
        "SHADING",
        "  金屬件 Bevel 2 段、螺栓／套管／焊縫 shade smooth。混凝土不倒成圓角。",
        "",
        "REPETITION",
        "  識別：四櫃模組相同、法蘭無螺栓、燈槽為光盒子、牆面無接縫。",
        "  處理：C 銘牌偏移、B 多 gland／搭扣／按鈕、C 封口、閥螺栓缺顆、OFF 無燈管、接縫不規則。",
        "",
        "HERO CLUSTERS",
        "  Zone A：y≈2–5 接線盒＋PN-04＋左主管法蘭螺栓＋牆縫＋地坪伸縮縫。",
        "  Zone B：y≈11.4–15.1 交叉管焊縫、雙櫃、閥螺栓、穿牆套管、潮濕斑。最密。",
        "  Zone C：y≈18–22 孤立櫃、偏移管識別環、吊閥螺栓、修補塊。較少但可記。",
        "",
        "PERFORMANCE",
        f"  新增 P8 物件 {validation['p8_count']}，共用網格 {validation['p8_meshes']}。",
        "  螺栓／接縫／燈管皆 instance。無 subdivision，無遠距全螺栓。",
        "",
        "SCREENSHOT TEST",
        "  SHOT A：Zone A 入口偏右，建立可讀的接線盒／管／牆縫。",
        "  SHOT B：Zone B 中段看向閥件與雙櫃，工業密度。",
        "  SHOT C：Zone C 看向孤立櫃與吊閥，低密度隔離。",
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
        f"  核心物件刪除：{len(validation['removed'])}；非打磨新增：{len(validation['added_core'])}",
        f"  相機路徑錯誤：{len(validation['camera_errors'])}",
        f"  Phase 7 燈光改動：{len(validation['light_changed'])}",
        f"  Phase 7 燈具變換改動：{len(validation['fixture_moved'])}",
        "",
        "PHASE 1 空間凍結狀態： " + ("PASS" if phase1_pass else "FAIL"),
        "PHASE 2 結構凍結狀態： " + ("PASS" if phase2_pass else "FAIL"),
        "PHASE 3 管線凍結狀態： " + ("PASS" if phase3_pass else "FAIL"),
        "PHASE 4 設備凍結狀態： " + ("PASS" if phase4_pass else "FAIL"),
        "PHASE 5 材質凍結狀態： " + ("PASS" if phase5_pass else "FAIL"),
        "PHASE 6 老化凍結狀態： " + ("PASS" if phase6_pass else "FAIL"),
        "PHASE 7 照明凍結狀態： " + ("PASS" if phase7_pass else "FAIL"),
        "PHASE 8 英雄打磨驗證： " + ("PASS" if phase8_pass else "FAIL"),
        "  Phase 7 燈具：位置／能量未改；housing／帽蓋／吊桿僅加倒角。",
        "  尚未開始 Phase 9。",
    ]
    if validation["moved"]:
        lines.append("  被改動物件：" + ", ".join(validation["moved"][:20]))
    if validation["light_changed"]:
        lines.append("  燈光改動：" + ", ".join(validation["light_changed"][:12]))
    if validation["fixture_moved"]:
        lines.append("  燈具變換改動：" + ", ".join(validation["fixture_moved"][:12]))
    report = OUTPUT_DIR / "phase8_hero_polish_validation.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", report)
    print("PHASE 8 VALIDATION", "PASS" if phase8_pass else "FAIL")
    print("p8_count", validation["p8_count"], "meshes", validation["p8_meshes"])
    return report


def render_stills(scene: bpy.types.Scene) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    p7.configure_eevee(scene, 48)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    inspect = bpy.data.objects["CAM_INSPECT"]
    for item in STILLS:
        label = item[0]
        cam_name = item[1]
        scene.camera = bpy.data.objects[cam_name]
        if len(item) == 3:
            scene.frame_set(item[2])
        scene.render.filepath = str(OUTPUT_DIR / f"{label}.jpg")
        bpy.ops.render.render(write_still=True)
        print("still", label)
    scene.camera = inspect
    scene.frame_set(1)


def main() -> None:
    mode = parse_mode()
    scene = bpy.context.scene
    before = p5.snapshot()
    lights_before = light_signature()
    fixtures_before = fixture_signature()
    clear_phase8()
    for name in COLLECTIONS:
        collection(name)
    mats = build_materials()
    ms = meshes()
    counts = dict(
        walls=polish_walls(ms, mats),
        floor=polish_floor(ms, mats),
        pipes=polish_pipes(ms, mats),
        equipment=polish_equipment(ms, mats),
        supports=polish_supports(ms, mats),
        fixtures=polish_fixtures(ms, mats),
    )
    add_hero_cameras()
    scene.camera = bpy.data.objects["CAM_INSPECT"]
    validation = validate(scene, before, lights_before, fixtures_before, counts)
    write_report(validation)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    print("counts", counts)
    if mode == "stills":
        render_stills(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 8 complete; Phase 9 not started.")


if __name__ == "__main__":
    main()
