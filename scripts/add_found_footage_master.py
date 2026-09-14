#!/usr/bin/env python3
"""Backrooms found-footage master pass on the EXISTING backrooms.blend.

Blood silhouette, 81s camcorder performance, one corner peek, unknown-sound
reaction, escape, new entrance door, new hand rig, door interaction.
Viewport preview only. No monster. No map rebuild. No final render.

  blender -b backrooms.blend --python scripts/add_found_footage_master.py -- --check
  blender -b backrooms.blend --python scripts/add_found_footage_master.py -- --stills
  blender -b backrooms.blend --python scripts/add_found_footage_master.py -- --preview
"""

from __future__ import annotations

import math
import random
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import add_room_a_found_footage as ff  # noqa: E402

BLEND_PATH = ROOT / "backrooms.blend"
PREVIEW_DIR = ROOT / "renders" / "found_footage_master"
OSD_SEQ_DIR = ROOT / "assets" / "osd_master"
OSD_MOV = ROOT / "assets" / "osd_timer_master.mov"
SFX_DIR = ROOT / "assets" / "sfx"
SFX_MIX = SFX_DIR / "found_footage_mix.wav"

FPS = 30
DURATION = 81.0
FRAME_END = 2430
COLL = "CAM_FOUND_FOOTAGE"
DOOR_COLL = "ENTRANCE_DOOR"
HAND_COLL = "HAND_PROP"
OSD_W, OSD_H = 640, 480
BLOOD_C = (-2.28, 1.52)
HAND_IN_T = 71.15

# East-hinged door in the existing south entrance opening.
# Handle sits on the west / camera-right side when facing the leaf from inside.
HINGE = (5.655, -4.900, 0.0)
LEAF_W, LEAF_H, LEAF_T = 0.92, 2.06, 0.044
HANDLE_LOCAL = (-0.80, 0.034, 1.02)


def parse_args() -> dict:
    mode = "check"
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--preview" in argv:
        mode = "preview"
    elif "--stills" in argv:
        mode = "stills"
    return {"mode": mode}


def frame_at(t: float) -> int:
    return max(1, min(FRAME_END, int(round(1 + t * FPS))))


def insert_xyz(obj, path, frame, value, interp="BEZIER"):
    ff.insert_xyz(obj, path, frame, value, interp)


# ---------------------------------------------------------------------------
# Blood — dried pool silhouette (shape only)
# ---------------------------------------------------------------------------

def _ring(bm, ox, oy, rx, ry, n, z, bumps):
    verts = []
    for i in range(n):
        a = (2.0 * math.pi * i) / n
        r = 1.0
        for ang, w, k in bumps:
            d = (a - ang + math.pi) % (2 * math.pi) - math.pi
            if abs(d) < w:
                r += k * (1.0 - abs(d) / w) ** 1.6
        verts.append(bm.verts.new((ox + rx * r * math.cos(a), oy + ry * r * math.sin(a), z)))
    return bm.faces.new(verts)


def _puddle_radius(a: float) -> float:
    """Smooth irregular oval. Low-frequency lobes only — no spike ring."""
    r = 1.0
    r += 0.11 * math.cos(a - 0.55)
    r += 0.07 * math.cos(2.0 * a + 1.15)
    r += 0.035 * math.cos(3.0 * a - 0.40)
    # One broader pooled bulge, not a spike.
    d = (a - 5.55 + math.pi) % (2 * math.pi) - math.pi
    if abs(d) < 0.95:
        r += 0.16 * (1.0 - abs(d) / 0.95) ** 1.8
    d2 = (a - 2.15 + math.pi) % (2 * math.pi) - math.pi
    if abs(d2) < 0.55:
        r += 0.07 * (1.0 - abs(d2) / 0.55) ** 1.7
    return max(0.72, r)


def rebuild_blood() -> bpy.types.Object:
    obj = bpy.data.objects.get("BLOOD.RoomA.Dried")
    bm = bmesh.new()
    rx, ry = 0.48, 0.38
    n = 56
    verts = []
    for i in range(n):
        a = (2.0 * math.pi * i) / n
        r = _puddle_radius(a)
        verts.append(bm.verts.new((rx * r * math.cos(a), ry * r * math.sin(a), 0.0)))
    main = bm.faces.new(verts)
    # Secondary pooled lobes, kept inside the main mass so it stays one puddle.
    lobe_a = _ring(bm, -0.12, 0.10, 0.16, 0.11, 20, 0.0, ((0.3, 0.55, 0.08),))
    lobe_b = _ring(bm, 0.14, -0.11, 0.12, 0.08, 16, 0.0, ((4.1, 0.4, 0.05),))
    # Short drag / smear on the west side only.
    smear_pts = (
        (-0.30, 0.02), (-0.48, 0.06), (-0.62, 0.05), (-0.58, 0.13),
        (-0.42, 0.14), (-0.28, 0.08),
    )
    smear = bm.faces.new([bm.verts.new((x, y, 0.0)) for x, y in smear_pts])
    faces = [main, lobe_a, lobe_b, smear]
    geom = bmesh.ops.extrude_face_region(bm, geom=faces)
    for g in geom["geom"]:
        if isinstance(g, bmesh.types.BMVert):
            g.co.z = 0.007
    # 6 droplets clustered with the same event, not a perimeter ring.
    for ox, oy, s in (
        (0.38, -0.06, 0.032),
        (0.46, 0.05, 0.020),
        (0.22, -0.28, 0.024),
        (-0.08, -0.32, 0.016),
        (-0.40, -0.14, 0.018),
        (0.06, 0.30, 0.015),
    ):
        dface = _ring(bm, ox, oy, s, s * 0.72, 10, 0.0, ((0.4, 0.5, 0.10),))
        g2 = bmesh.ops.extrude_face_region(bm, geom=[dface])
        for g in g2["geom"]:
            if isinstance(g, bmesh.types.BMVert):
                g.co.z = 0.005
    mesh = bpy.data.meshes.new("BLOOD.RoomA.Dried.Puddle")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    mat = mat_rgb("MAT.DriedBlood", (0.09, 0.018, 0.012), 0.92)
    mat.diffuse_color = (0.10, 0.02, 0.015, 1.0)
    if obj is None:
        col = bpy.data.collections.get("FX_DRIED_BLOOD")
        if col is None:
            col = bpy.data.collections.new("FX_DRIED_BLOOD")
            bpy.context.scene.collection.children.link(col)
        obj = bpy.data.objects.new("BLOOD.RoomA.Dried", mesh)
        col.objects.link(obj)
    else:
        obj.data = mesh
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    obj.scale = (1.0, 1.0, 1.0)
    obj.location = (BLOOD_C[0], BLOOD_C[1], 0.007)
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    print("Blood footprint", round(max(xs) - min(xs), 3), "x", round(max(ys) - min(ys), 3),
          "verts", len(obj.data.vertices),
          "world", (round(min(xs) + BLOOD_C[0], 3), round(max(xs) + BLOOD_C[0], 3),
                    round(min(ys) + BLOOD_C[1], 3), round(max(ys) + BLOOD_C[1], 3)))
    return obj


# ---------------------------------------------------------------------------
# Door
# ---------------------------------------------------------------------------

def new_col(name: str) -> bpy.types.Collection:
    old = bpy.data.collections.get(name)
    if old is not None:
        for obj in list(old.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old)
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def box_mesh(name, x0, y0, z0, x1, y1, z1):
    mesh = bpy.data.meshes.new(name)
    v = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    f = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    mesh.from_pydata(v, [], f)
    mesh.update()
    return mesh


def mat_rgb(name, rgb, rough=0.72):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*rgb, 1.0)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = rough
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def add_mesh_obj(name, mesh, col, loc=(0, 0, 0), mat=None):
    obj = bpy.data.objects.new(name, mesh)
    obj.location = loc
    col.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    return obj


def _append_box(bm, x0, y0, z0, x1, y1, z1):
    vs = [
        bm.verts.new((x0, y0, z0)), bm.verts.new((x1, y0, z0)),
        bm.verts.new((x1, y1, z0)), bm.verts.new((x0, y1, z0)),
        bm.verts.new((x0, y0, z1)), bm.verts.new((x1, y0, z1)),
        bm.verts.new((x1, y1, z1)), bm.verts.new((x0, y1, z1)),
    ]
    bm.faces.new((vs[0], vs[1], vs[2], vs[3]))
    bm.faces.new((vs[4], vs[7], vs[6], vs[5]))
    bm.faces.new((vs[0], vs[4], vs[5], vs[1]))
    bm.faces.new((vs[1], vs[5], vs[6], vs[2]))
    bm.faces.new((vs[2], vs[6], vs[7], vs[3]))
    bm.faces.new((vs[3], vs[7], vs[4], vs[0]))


def build_door(col):
    wood = mat_rgb("MAT.DoorLeaf", (0.68, 0.62, 0.52), 0.78)
    paint = mat_rgb("MAT.DoorFrame", (0.58, 0.54, 0.46), 0.72)
    metal = mat_rgb("MAT.DoorHandle", (0.78, 0.76, 0.70), 0.28)
    jamb_w = 0.13
    frame_y0, frame_y1 = -5.00, -4.80
    z_head = 2.08
    fbm = bmesh.new()
    _append_box(fbm, 4.60, frame_y0, 0.0, 4.60 + jamb_w, frame_y1, z_head)
    _append_box(fbm, 5.80 - jamb_w, frame_y0, 0.0, 5.80, frame_y1, z_head)
    _append_box(fbm, 4.60, frame_y0, z_head, 5.80, frame_y1, 2.20)
    fmesh = bpy.data.meshes.new("Door_Frame")
    fbm.to_mesh(fmesh)
    fbm.free()
    frame = add_mesh_obj("Door_Frame", fmesh, col, mat=paint)

    hinge = ff.make_empty("Door_Hinge_Pivot", col, 0.08)
    hinge.location = HINGE
    hinge.rotation_mode = "XYZ"
    # Leaf extends west from the east hinge. Slight panel recess on both faces.
    lbm = bmesh.new()
    _append_box(lbm, -(LEAF_W - 0.012), -LEAF_T * 0.5, 0.018, -0.006, LEAF_T * 0.5, LEAF_H)
    # Shallow panel inset on the interior (+Y) face.
    _append_box(lbm, -(LEAF_W - 0.07), 0.018, 0.16, -0.06, 0.024, LEAF_H - 0.16)
    # Handle backplate
    _append_box(lbm, -0.86, 0.020, 0.92, -0.74, 0.028, 1.14)
    lmesh = bpy.data.meshes.new("Door_Leaf")
    lbm.to_mesh(lmesh)
    lbm.free()
    leaf = add_mesh_obj("Door_Leaf", lmesh, col, loc=(0.0, 0.0, 0.0), mat=wood)
    leaf.parent = hinge
    leaf.matrix_parent_inverse.identity()
    # Lever handle: shaft into the room (+Y) and a bar toward the west (-X).
    hbm = bmesh.new()
    _append_box(hbm, -0.012, 0.000, -0.012, 0.012, 0.058, 0.012)
    _append_box(hbm, -0.108, 0.042, -0.010, 0.012, 0.062, 0.010)
    hmesh = bpy.data.meshes.new("Door_Handle")
    hbm.to_mesh(hmesh)
    hbm.free()
    handle = add_mesh_obj("Door_Handle", hmesh, col, loc=(0, 0, 0), mat=metal)
    handle.parent = leaf
    handle.location = HANDLE_LOCAL
    handle.rotation_mode = "XYZ"
    return hinge, leaf, handle, frame


def build_beyond(col):
    """Dark undefined space past the threshold. Not a next level."""
    dark = mat_rgb("MAT.BeyondVoid", (0.012, 0.012, 0.014), 0.95)
    add_mesh_obj("BEYOND.Floor", box_mesh("BEYOND.Floor", 4.50, -6.50, -0.04, 5.90, -5.04, 0.0), col, mat=dark)
    add_mesh_obj("BEYOND.West", box_mesh("BEYOND.West", 4.48, -6.50, 0.0, 4.58, -5.04, 2.40), col, mat=dark)
    add_mesh_obj("BEYOND.East", box_mesh("BEYOND.East", 5.82, -6.50, 0.0, 5.92, -5.04, 2.40), col, mat=dark)
    add_mesh_obj("BEYOND.South", box_mesh("BEYOND.South", 4.50, -6.52, 0.0, 5.90, -6.40, 2.40), col, mat=dark)
    add_mesh_obj("BEYOND.Ceil", box_mesh("BEYOND.Ceil", 4.50, -6.50, 2.38, 5.90, -5.04, 2.50), col, mat=dark)


# ---------------------------------------------------------------------------
# Hand mesh + armature
# ---------------------------------------------------------------------------

def _add_taper_box(bm, x0, y0, z0, x1, y1, z1):
    vs = [
        bm.verts.new((x0, y0, z0)), bm.verts.new((x1, y0, z0)),
        bm.verts.new((x1, y1, z0)), bm.verts.new((x0, y1, z0)),
        bm.verts.new((x0, y0, z1)), bm.verts.new((x1, y0, z1)),
        bm.verts.new((x1, y1, z1)), bm.verts.new((x0, y1, z1)),
    ]
    bm.faces.new((vs[0], vs[1], vs[2], vs[3]))
    bm.faces.new((vs[4], vs[7], vs[6], vs[5]))
    bm.faces.new((vs[0], vs[4], vs[5], vs[1]))
    bm.faces.new((vs[1], vs[5], vs[6], vs[2]))
    bm.faces.new((vs[2], vs[6], vs[7], vs[3]))
    bm.faces.new((vs[3], vs[7], vs[4], vs[0]))
    return vs


def build_hand_mesh() -> bpy.types.Mesh:
    bm = bmesh.new()
    # Palm — slightly thicker, with a wrist stump. Fingers +Y, back of hand +Z.
    _add_taper_box(bm, -0.046, -0.012, -0.016, 0.044, 0.098, 0.024)
    _add_taper_box(bm, -0.038, -0.062, -0.014, 0.036, -0.008, 0.020)
    # Thenar / thumb pad
    _add_taper_box(bm, -0.058, 0.004, -0.012, -0.028, 0.055, 0.018)
    # Fingers: index, middle, ring, little — 3 phalanges, tapered, knuckle overlap
    fingers = (
        (0.028, 0.092, 0.080, 0.019),
        (0.007, 0.096, 0.088, 0.020),
        (-0.014, 0.094, 0.080, 0.018),
        (-0.033, 0.090, 0.066, 0.015),
    )
    for x, y0, length, width in fingers:
        sl = length / 3.0
        for i in range(3):
            taper = 1.0 - 0.16 * i
            w = width * taper
            h = 0.017 * taper
            ya = y0 + i * sl - 0.003
            yb = y0 + (i + 1) * sl + 0.001
            _add_taper_box(bm, x - w * 0.5, ya, 0.000, x + w * 0.5, yb, h + 0.004)
    # Thumb — 3 phalanges, opposed along -X / +Y
    thumb = (
        (-0.052, 0.018, 0.000, 0.024, 0.030, 0.018),
        (-0.072, 0.040, 0.002, 0.022, 0.026, 0.016),
        (-0.090, 0.058, 0.002, 0.018, 0.022, 0.014),
    )
    ang = math.radians(-42)
    for cx, cy, cz, sx, sy, sz in thumb:
        corners = []
        for dx, dy, dz in (
            (-sx * 0.5, 0.0, -sz * 0.35), (sx * 0.5, 0.0, -sz * 0.35),
            (sx * 0.5, sy, -sz * 0.35), (-sx * 0.5, sy, -sz * 0.35),
            (-sx * 0.5, 0.0, sz * 0.65), (sx * 0.5, 0.0, sz * 0.65),
            (sx * 0.5, sy, sz * 0.65), (-sx * 0.5, sy, sz * 0.65),
        ):
            rx = dx * math.cos(ang) - dy * math.sin(ang)
            ry = dx * math.sin(ang) + dy * math.cos(ang)
            corners.append((cx + rx, cy + ry, cz + dz))
        vs = [bm.verts.new(p) for p in corners]
        bm.faces.new((vs[0], vs[1], vs[2], vs[3]))
        bm.faces.new((vs[4], vs[7], vs[6], vs[5]))
        bm.faces.new((vs[0], vs[4], vs[5], vs[1]))
        bm.faces.new((vs[1], vs[5], vs[6], vs[2]))
        bm.faces.new((vs[2], vs[6], vs[7], vs[3]))
        bm.faces.new((vs[3], vs[7], vs[4], vs[0]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0018)
    bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=1)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for _ in range(2):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=0.35, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    skin = mat_rgb("MAT.HandSkin", (0.52, 0.36, 0.28), 0.52)
    mesh = bpy.data.meshes.new("HAND.Mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(skin)
    return mesh


def _ebone(arm, name, head, tail, parent=None):
    b = arm.edit_bones.new(name)
    b.head = Vector(head)
    b.tail = Vector(tail)
    if parent is not None:
        b.parent = parent
        b.use_connect = True
    return b


def build_hand_rig(col):
    mesh = build_hand_mesh()
    mesh_obj = bpy.data.objects.new("HAND.Mesh", mesh)
    col.objects.link(mesh_obj)
    arm_data = bpy.data.armatures.new("HAND.Armature")
    arm_obj = bpy.data.objects.new("HAND.Rig", arm_data)
    col.objects.link(arm_obj)
    arm_obj.location = (0, 0, 0)
    mesh_obj.location = (0, 0, 0)
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    wrist = _ebone(arm_data, "Wrist", (0.0, -0.05, 0.004), (0.0, 0.02, 0.006))
    palm = _ebone(arm_data, "Palm", (0.0, 0.02, 0.006), (0.0, 0.090, 0.008), wrist)
    palm.use_connect = True
    # Fingers
    specs = [
        ("Index", 0.028, 0.090, 0.078),
        ("Middle", 0.008, 0.092, 0.086),
        ("Ring", -0.012, 0.090, 0.078),
        ("Little", -0.030, 0.086, 0.064),
    ]
    for name, x, y0, length in specs:
        sl = length / 3.0
        p = palm
        connect = False
        y = y0
        for i in range(3):
            b = arm_data.edit_bones.new(f"{name}.{i+1:02d}")
            b.head = Vector((x, y, 0.008))
            b.tail = Vector((x, y + sl, 0.008))
            b.parent = p
            b.use_connect = connect
            p = b
            connect = True
            y += sl
    # Thumb
    t0 = arm_data.edit_bones.new("Thumb.01")
    t0.head = Vector((-0.038, 0.012, 0.006))
    t0.tail = Vector((-0.055, 0.038, 0.008))
    t0.parent = palm
    t0.use_connect = False
    t1 = arm_data.edit_bones.new("Thumb.02")
    t1.head = t0.tail.copy()
    t1.tail = Vector((-0.068, 0.058, 0.010))
    t1.parent = t0
    t1.use_connect = True
    t2 = arm_data.edit_bones.new("Thumb.03")
    t2.head = t1.tail.copy()
    t2.tail = Vector((-0.078, 0.074, 0.010))
    t2.parent = t1
    t2.use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in arm_obj.pose.bones:
        pb.rotation_mode = "XYZ"
    mesh_obj.parent = arm_obj
    mesh_obj.parent_type = "ARMATURE"
    # Automatic weights
    bpy.ops.object.select_all(action="DESELECT")
    mesh_obj.select_set(True)
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except Exception as exc:
        print("ARMATURE_AUTO failed", exc)
        mesh_obj.parent = arm_obj
        mesh_obj.parent_type = "ARMATURE"
    assign_hand_weights(mesh_obj, arm_obj)
    root = ff.make_empty("HAND.World", col, 0.06)
    arm_obj.parent = root
    arm_obj.location = (0, 0, 0)
    root.location = (5.05, -4.20, 1.20)
    root.rotation_euler = (math.radians(78), math.radians(6), math.radians(90))
    root.scale = (0.001, 0.001, 0.001)
    for o in (root, arm_obj, mesh_obj):
        o.hide_render = True
        o.hide_viewport = True
    return root, arm_obj, mesh_obj


def assign_hand_weights(mesh_obj, arm_obj):
    """Deterministic vertex groups so fingers actually curl around the lever."""
    mesh = mesh_obj.data
    names = [b.name for b in arm_obj.data.bones]
    for name in names:
        vg = mesh_obj.vertex_groups.get(name) or mesh_obj.vertex_groups.new(name=name)
        vg.add(range(len(mesh.vertices)), 0.0, "REPLACE")
    bands = {
        "Wrist": lambda x, y, z: y < 0.018,
        "Palm": lambda x, y, z: 0.018 <= y < 0.092 and x > -0.048,
        "Index.01": lambda x, y, z: 0.018 < x and 0.090 <= y < 0.118,
        "Index.02": lambda x, y, z: 0.018 < x and 0.118 <= y < 0.146,
        "Index.03": lambda x, y, z: 0.018 < x and y >= 0.146,
        "Middle.01": lambda x, y, z: 0.0 < x <= 0.018 and 0.094 <= y < 0.124,
        "Middle.02": lambda x, y, z: 0.0 < x <= 0.018 and 0.124 <= y < 0.154,
        "Middle.03": lambda x, y, z: 0.0 < x <= 0.018 and y >= 0.154,
        "Ring.01": lambda x, y, z: -0.024 <= x <= 0.0 and 0.092 <= y < 0.120,
        "Ring.02": lambda x, y, z: -0.024 <= x <= 0.0 and 0.120 <= y < 0.148,
        "Ring.03": lambda x, y, z: -0.024 <= x <= 0.0 and y >= 0.148,
        "Little.01": lambda x, y, z: x < -0.024 and x > -0.048 and 0.088 <= y < 0.112,
        "Little.02": lambda x, y, z: x < -0.024 and x > -0.048 and 0.112 <= y < 0.134,
        "Little.03": lambda x, y, z: x < -0.024 and x > -0.048 and y >= 0.134,
        "Thumb.01": lambda x, y, z: x <= -0.048 and y < 0.040,
        "Thumb.02": lambda x, y, z: x <= -0.048 and 0.040 <= y < 0.062,
        "Thumb.03": lambda x, y, z: x <= -0.048 and y >= 0.062,
    }
    for i, v in enumerate(mesh.vertices):
        x, y, z = v.co
        for name, pred in bands.items():
            if pred(x, y, z) and name in mesh_obj.vertex_groups:
                mesh_obj.vertex_groups[name].add([i], 1.0, "REPLACE")
                break


def key_hide(obj, t, hide: bool):
    f = frame_at(t)
    obj.hide_viewport = hide
    obj.hide_render = hide
    obj.keyframe_insert("hide_viewport", frame=f)
    obj.keyframe_insert("hide_render", frame=f)
    if obj.name == "HAND.World":
        s = 0.001 if hide else 1.0
        obj.scale = (s, s, s)
        obj.keyframe_insert("scale", frame=f)


def pose_curl(arm, t, curl, thumb_opp=0.0):
    f = frame_at(t)
    names = {
        "Index": (0.9, 1.1, 0.7),
        "Middle": (1.0, 1.15, 0.75),
        "Ring": (0.95, 1.05, 0.7),
        "Little": (0.85, 1.0, 0.65),
    }
    for finger, w in names.items():
        for i, ww in enumerate(w, start=1):
            pb = arm.pose.bones.get(f"{finger}.{i:02d}")
            if pb is None:
                continue
            pb.rotation_euler = (math.radians(curl * ww * 42.0), 0.0, 0.0)
            pb.keyframe_insert("rotation_euler", frame=f)
    th = [
        ("Thumb.01", (math.radians(8 * curl), math.radians(-25 * thumb_opp), math.radians(-18 * thumb_opp))),
        ("Thumb.02", (math.radians(18 * curl), 0.0, math.radians(-8 * thumb_opp))),
        ("Thumb.03", (math.radians(12 * curl), 0.0, 0.0)),
    ]
    for name, rot in th:
        pb = arm.pose.bones.get(name)
        if pb is None:
            continue
        pb.rotation_euler = rot
        pb.keyframe_insert("rotation_euler", frame=f)


def animate_hand_and_door(hand_root, arm, mesh_obj, hinge, handle):
    for obj in (hand_root, arm, mesh_obj):
        key_hide(obj, 0.0, True)
        key_hide(obj, HAND_IN_T - 0.05, True)
        key_hide(obj, HAND_IN_T, False)
    # Handle is at ~ (4.89, -4.87, 1.02). Camera looks south; handle is camera-right.
    keys = [
        (HAND_IN_T, (5.00, -3.88, 1.26), (74, 6, 92), 0.05, 0.05),
        (71.35, (4.92, -4.40, 1.12), (86, 0, 78), 0.28, 0.22),
        (71.55, (4.84, -4.68, 1.08), (90, -2, 72), 0.16, 0.12),
        (71.72, (4.94, -4.50, 1.14), (82, 4, 82), 0.08, 0.08),
        (72.05, (4.86, -4.78, 1.05), (94, -4, 68), 0.62, 0.72),
        (72.35, (4.850, -4.838, 1.038), (96, -4, 66), 0.95, 0.95),
        (73.20, (4.78, -4.96, 1.03), (96, -10, 56), 1.0, 1.0),
        (74.50, (4.62, -5.16, 1.06), (88, -14, 42), 0.95, 0.9),
        (76.40, (4.55, -5.28, 1.16), (68, -8, 28), 0.40, 0.35),
        (78.20, (4.70, -5.02, 1.32), (46, -4, 14), 0.10, 0.05),
        (80.40, (4.85, -4.90, 1.42), (20, 0, 6), 0.0, 0.0),
    ]
    for t, loc, eul, curl, opp in keys:
        f = frame_at(t)
        insert_xyz(hand_root, "location", f, loc)
        insert_xyz(hand_root, "rotation_euler", f, tuple(math.radians(a) for a in eul))
        pose_curl(arm, t, curl, opp)
    for t, deg in ((0.0, 0.0), (72.20, 0.0), (72.45, 42.0), (73.10, 48.0), (74.20, 22.0), (81.0, 16.0)):
        handle.rotation_euler = (math.radians(deg), 0.0, 0.0)
        handle.keyframe_insert("rotation_euler", frame=frame_at(t))
    # East hinge: +Z swings the west-extending leaf south (outward).
    for t, deg in (
        (0.0, 0.0), (72.40, 0.0), (73.20, 22.0), (74.40, 52.0),
        (75.80, 78.0), (77.20, 88.0), (81.0, 90.0),
    ):
        hinge.rotation_euler = (0.0, 0.0, math.radians(deg))
        hinge.keyframe_insert("rotation_euler", frame=frame_at(t))
    ff.shape_sparse_fcurves(hand_root)
    ff.shape_sparse_fcurves(hinge)
    ff.shape_sparse_fcurves(handle)


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

def _tone(sr, n, fn):
    return [max(-1.0, min(1.0, fn(i / sr))) for i in range(n)]


def write_wav(path: Path, samples, sr=44100):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32000)) for s in samples)
        w.writeframes(frames)


def make_soundtrack():
    sr = 22050
    n = int(DURATION * sr) + sr
    mix = [0.0] * n
    rng = random.Random(3)

    def add(t0, samples, gain=1.0):
        i0 = int(t0 * sr)
        for i, s in enumerate(samples):
            j = i0 + i
            if 0 <= j < n:
                mix[j] += gain * s

    # Fluorescent buzz throughout
    buzz = []
    for i in range(n):
        t = i / sr
        s = 0.012 * math.sin(2 * math.pi * 120 * t)
        s += 0.006 * math.sin(2 * math.pi * 240 * t)
        s += 0.004 * math.sin(2 * math.pi * 59.8 * t)
        s += 0.003 * (rng.random() - 0.5)
        buzz.append(s)
    add(0.0, buzz, 1.0)

    def thumm(dur=1.7):
        m = int(dur * sr)
        out = []
        for i in range(m):
            t = i / sr
            env = math.exp(-t * 2.4) * (1.0 - t / dur)
            s = 0.9 * math.sin(2 * math.pi * 38 * t) * env
            s += 0.55 * math.sin(2 * math.pi * 22 * t) * env
            s += 0.12 * (rng.random() - 0.5) * env
            out.append(s)
        return out

    def grind(dur=2.3):
        m = int(dur * sr)
        out = []
        for i in range(m):
            t = i / sr
            env = min(1.0, t / 0.15) * math.exp(-t * 0.55)
            f = 62.0 - 18.0 * (t / dur)
            s = 0.45 * math.sin(2 * math.pi * f * t) * env
            s += 0.35 * math.sin(2 * math.pi * (f * 0.5) * t) * env
            s += 0.28 * (rng.random() - 0.5) * env
            s += 0.12 * math.sin(2 * math.pi * 17 * t) * env
            out.append(s)
        return out

    def thud(dur=0.45):
        m = int(dur * sr)
        out = []
        for i in range(m):
            t = i / sr
            env = math.exp(-t * 9.0)
            s = 1.0 * math.sin(2 * math.pi * 48 * t) * env
            s += 0.7 * math.sin(2 * math.pi * 29 * t) * env
            s += 0.2 * (rng.random() - 0.5) * env
            out.append(s)
        return out

    add(56.15, thumm(), 0.85)
    add(59.45, grind(), 0.70)
    add(62.55, thud(), 1.15)
    write_wav(SFX_MIX, mix, sr)
    print("Wrote", SFX_MIX)
    return SFX_MIX


def vibrate_lights(scene):
    names = (
        "LIGHT.HallB.03.Housing", "LIGHT.HallB.03.Lamp",
        "LIGHT.Main.01.Housing", "LIGHT.Main.01.Lamp",
        "LIGHT.HallB.02.Housing", "LIGHT.HallB.02.Lamp",
    )
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        z0 = obj.location.z
        loc0 = obj.location.copy()
        for t, dz in ((0.0, 0.0), (62.50, 0.0), (62.58, 0.006), (62.70, -0.004), (62.90, 0.002), (63.20, 0.0)):
            obj.location = (loc0.x, loc0.y, z0 + dz)
            obj.keyframe_insert("location", frame=frame_at(t))


# ---------------------------------------------------------------------------
# Camera animation
# ---------------------------------------------------------------------------

# t, x, y, z, yaw_deg
ROOT_KEYS = [
    # Floor: ~0.9 m from puddle so the oval silhouette reads. Accidental roll.
    (0.00, -2.860, 2.240, 0.090, -140.0),
    (1.90, -2.859, 2.241, 0.091, -139.2),
    (2.12, -2.848, 2.252, 0.098, -136.0),
    (2.18, -2.844, 2.248, 0.082, -133.5),
    (2.26, -2.828, 2.230, 0.100, -142.0),
    (2.40, -2.822, 2.222, 0.090, -140.0),
    (2.85, -2.824, 2.222, 0.089, -140.0),
    (3.10, -2.824, 2.222, 0.090, -140.4),
    (3.22, -2.868, 2.255, 0.128, -148.0),
    (3.38, -2.848, 2.232, 0.295, -128.0),
    (3.55, -2.832, 2.218, 0.495, -144.0),
    (3.72, -2.840, 2.208, 0.645, -134.0),
    (3.88, -2.822, 2.200, 0.845, -142.0),
    (4.10, -2.810, 2.196, 1.075, -136.0),
    (4.32, -2.798, 2.190, 1.305, -143.0),
    (4.55, -2.782, 2.184, 1.532, -138.0),
    (4.85, -2.772, 2.180, 1.612, -136.0),
    (5.20, -2.768, 2.182, 1.606, -138.0),
    (5.70, -2.766, 2.184, 1.598, -140.0),
    # Blood inspect: lean toward the puddle, dwell, recoil, raise
    (6.20, -2.740, 2.150, 1.568, -144.0),
    (6.90, -2.718, 2.122, 1.542, -146.0),
    (7.60, -2.714, 2.118, 1.538, -145.0),
    (8.30, -2.732, 2.140, 1.558, -142.0),
    (9.20, -2.750, 2.168, 1.584, -138.0),
    (10.20, -2.760, 2.190, 1.600, -124.0),
    # Look-around. ROOT lags HEAD. No L-C-R scan.
    (11.40, -2.768, 2.210, 1.606, -98.0),
    (12.90, -2.776, 2.240, 1.608, -44.0),
    (14.40, -2.784, 2.268, 1.610, -10.0),
    (15.80, -2.788, 2.282, 1.610, 10.0),
    (17.00, -2.780, 2.290, 1.610, -12.0),
    (18.40, -2.768, 2.302, 1.610, -50.0),
    (19.30, -2.756, 2.314, 1.610, -64.0),
    # Walk Room A: west along south, north, then east to the door. Not through center.
    (19.90, -2.88, 2.38, 1.612, -28.0),
    (21.20, -3.42, 2.22, 1.610, 8.0),
    (22.10, -3.72, 2.22, 1.608, 22.0),
    (22.80, -3.88, 2.38, 1.606, 28.0),
    (23.50, -3.92, 2.42, 1.606, 18.0),
    (24.40, -3.70, 2.85, 1.608, -12.0),
    (25.60, -3.18, 3.28, 1.610, -48.0),
    (26.80, -2.62, 3.38, 1.608, -74.0),
    (28.00, -2.18, 3.22, 1.604, -88.0),
    (29.20, -1.98, 3.08, 1.600, -90.0),
    (30.50, -1.90, 2.98, 1.598, -90.0),
    (31.40, -1.88, 2.92, 1.598, -88.0),  # 28 cm behind east wall
    (32.50, -1.88, 2.92, 1.598, -90.0),
    (36.00, -1.87, 2.91, 1.598, -88.0),
    (38.80, -1.86, 2.90, 1.598, -86.0),
    # Curve into Corr A after second peek. HEAD already looking in.
    (39.40, -1.82, 2.98, 1.600, -80.0),
    (39.80, -1.70, 3.12, 1.604, -72.0),
    (40.20, -1.50, 3.24, 1.606, -88.0),
    (40.70, -1.22, 3.30, 1.608, -112.0),
    (41.40, -0.78, 3.18, 1.608, -158.0),
    (42.20, -0.52, 2.80, 1.606, 180.0),
    (43.40, -0.48, 2.36, 1.606, 178.0),
    (44.80, -0.44, 1.82, 1.604, 176.0),
    (46.20, -0.40, 1.36, 1.602, 178.0),
    (47.40, -0.48, 1.06, 1.600, 168.0),
    (48.40, -0.58, 0.62, 1.598, 132.0),
    # Hall B east toward Main
    (49.40, -0.18, 0.22, 1.598, -90.0),
    (51.00, 0.38, 0.18, 1.598, -88.0),
    (52.60, 0.92, 0.16, 1.596, -90.0),
    (54.20, 1.38, 0.18, 1.596, -86.0),
    (55.80, 1.64, 0.20, 1.596, -92.0),
    (56.10, 1.66, 0.20, 1.596, -90.0),  # freeze
    (56.45, 1.66, 0.20, 1.596, -55.0),
    (56.80, 1.66, 0.20, 1.596, -12.0),  # body follows look-back toward west
    (57.50, 1.66, 0.20, 1.596, -8.0),
    (58.80, 1.66, 0.20, 1.596, -36.0),
    (60.00, 1.66, 0.19, 1.596, -110.0),  # correct toward Main / sound
    (61.40, 1.66, 0.18, 1.596, -100.0),
    (62.80, 1.66, 0.16, 1.596, -92.0),
    # Run through Main to the entrance. Keep x>=2.02 while y<=-0.80.
    (63.15, 1.70, 0.04, 1.600, -120.0),
    (63.40, 2.04, -0.42, 1.610, -145.0),
    (63.65, 2.16, -0.84, 1.612, -155.0),
    (63.95, 2.28, -1.58, 1.610, -125.0),
    (64.30, 2.90, -2.28, 1.606, -100.0),
    (64.70, 3.85, -2.42, 1.600, -100.0),
    (65.10, 4.70, -2.55, 1.592, -95.0),
    (65.50, 5.18, -3.05, 1.585, -160.0),
    (66.10, 5.22, -3.70, 1.575, 180.0),
    (66.80, 5.20, -3.82, 1.568, 180.0),
    # Face the closed door; handle is camera-right (west).
    (68.20, 5.12, -3.95, 1.558, 182.0),
    (69.40, 5.10, -4.02, 1.550, 184.0),
    (70.60, 5.08, -4.08, 1.542, 186.0),
    (71.20, 5.06, -4.12, 1.534, 186.0),
    (71.55, 5.04, -4.14, 1.518, 188.0),
    (71.80, 5.06, -4.12, 1.528, 186.0),
    (72.30, 5.04, -4.16, 1.514, 186.0),
    (73.20, 5.06, -4.22, 1.524, 184.0),
    (74.40, 5.10, -4.32, 1.534, 182.0),
    (75.60, 5.14, -4.48, 1.542, 180.0),
    (76.80, 5.18, -4.70, 1.548, 180.0),
    (78.00, 5.20, -4.86, 1.550, 180.0),
    (81.00, 5.20, -4.92, 1.546, 178.0),
]

LOOK_KEYS = [
    (0.00, -16.0, 8.0),
    (1.90, -15.0, 6.0),
    (2.14, -10.0, -4.0),
    (2.28, 0.0, 8.0),
    (2.50, -14.0, 4.0),
    (3.10, -14.0, 5.0),
    (3.30, 0.0, -8.0),
    (3.50, -18.0, 10.0),
    (3.75, -6.0, -6.0),
    (4.10, -12.0, 4.0),
    (4.50, -10.0, 2.0),
    (5.20, -12.0, 1.0),
    (5.70, -14.0, -2.0),
    (6.20, -26.0, -4.0),
    (6.80, -38.0, -6.0),
    (7.30, -42.0, -8.0),
    (7.80, -40.0, -6.0),
    (8.50, -28.0, -4.0),
    (9.30, -14.0, 0.0),
    (10.20, -8.0, 6.0),
    (10.55, -6.0, 8.0),
    (10.85, 4.0, 10.0),
    (11.15, 6.0, 12.0),
    (11.35, 4.0, 10.0),
    (11.90, -6.0, 6.0),
    (12.40, -6.0, 38.0),
    (12.90, -7.0, 52.0),
    (13.25, -6.0, 58.0),
    (13.55, -6.0, 52.0),
    (14.40, -7.0, 16.0),
    (15.00, -12.0, 6.0),
    (15.50, -14.0, 2.0),
    (16.00, -8.0, -4.0),
    (16.50, -7.0, -16.0),
    (17.00, -6.0, -22.0),
    (17.40, -6.5, -20.0),
    (18.10, -6.0, 10.0),
    (18.60, -6.5, 16.0),
    (19.20, -6.0, 4.0),
    (19.70, -6.5, -8.0),
    (20.40, -6.0, -2.0),
    (21.30, -7.0, 16.0),
    (22.20, -6.5, 22.0),
    (22.80, -7.0, 18.0),
    (23.60, -6.5, 4.0),
    (24.80, -6.0, -6.0),
    (26.20, -6.5, 4.0),
    (27.50, -6.0, 4.0),
    (28.80, -6.0, 2.0),
    (30.40, -6.0, 6.0),
    (31.40, -5.5, 8.0),
    (32.10, -5.5, 6.0),
    (32.45, -5.0, 12.0),
    (32.85, -5.5, 16.0),
    (33.30, -6.0, 15.0),
    (33.80, -5.5, 14.0),
    (34.20, -6.0, 8.0),
    (34.70, -6.0, 5.0),
    (35.20, -6.5, 4.0),
    (35.70, -5.5, 8.0),
    (36.15, -5.0, 14.0),
    (36.70, -5.5, 18.0),
    (37.30, -6.0, 16.0),
    (38.00, -6.0, 12.0),
    (38.80, -6.5, 6.0),
    (39.50, -6.0, 2.0),
    (40.30, -6.5, -8.0),
    (41.20, -6.0, 4.0),
    (42.20, -6.5, 2.0),
    (44.00, -6.0, 8.0),
    (45.40, -7.0, -6.0),
    (46.80, -6.0, 4.0),
    (48.20, -6.5, 10.0),
    (49.40, -6.0, 4.0),
    (51.20, -6.5, 8.0),
    (53.00, -6.0, -4.0),
    (54.60, -6.5, 6.0),
    (55.90, -6.0, 2.0),
    # freeze → look back ~100° (west down Hall B) with overshoot
    (56.15, -4.0, 4.0),
    (56.28, -3.0, 22.0),
    (56.42, -3.5, 58.0),
    (56.55, -4.0, 92.0),
    (56.70, -4.5, 108.0),
    (56.84, -4.0, 100.0),
    (57.40, -4.5, 96.0),
    (58.20, -5.0, 72.0),
    (58.90, -6.0, 28.0),
    (59.50, -6.0, -6.0),
    (60.10, -6.5, -18.0),
    (60.70, -6.0, -16.0),
    (61.40, -6.5, -8.0),
    (62.40, -6.0, 2.0),
    (63.00, -5.0, 8.0),
    (63.50, -4.0, 4.0),
    (64.40, -3.5, 6.0),
    (65.40, -5.0, -2.0),
    (66.40, -6.0, 2.0),
    (67.40, -12.0, -6.0),
    (68.40, -18.0, -10.0),
    (69.60, -26.0, -12.0),
    (70.80, -34.0, -14.0),
    (71.30, -38.0, -16.0),
    (71.55, -30.0, -10.0),
    (72.10, -40.0, -18.0),
    (73.20, -24.0, -10.0),
    (74.60, -14.0, -6.0),
    (76.40, -8.0, -2.0),
    (78.20, -6.0, 0.0),
    (81.00, -5.0, 0.0),
]

ROLL_KEYS = [
    (0.00, 27.0), (1.90, 26.2), (2.14, 32.0), (2.26, 21.0), (2.50, 28.0),
    (3.10, 26.5), (3.30, 18.0), (3.48, 36.0), (3.70, -12.0), (3.92, 14.0),
    (4.20, -8.0), (4.50, 4.0), (4.85, -0.8), (5.40, 0.3), (8.00, 0.4),
    (22.10, 0.6), (32.90, 0.8), (33.40, 1.3), (34.50, 0.3),
    (36.80, 1.5), (38.50, 0.4), (56.70, 1.6), (57.40, 0.4),
    (62.60, 0.9), (63.40, 2.8), (64.20, -2.2), (65.20, 3.4),
    (66.20, -1.8), (67.40, 2.2), (68.80, 1.0), (71.40, 2.4),
    (72.20, -1.2), (73.00, 1.6), (76.00, 0.8), (81.00, 0.3),
]

# Peek translation in HEAD local. Facing east, -X is north.
PEEK_KEYS = [
    (0.00, 0.0, 0.0, 0.0),
    (31.80, 0.0, 0.0, 0.0),
    (32.20, -0.03, 0.010, -0.004),
    (32.70, -0.09, 0.030, -0.012),
    (33.20, -0.11, 0.040, -0.016),
    (33.70, -0.10, 0.036, -0.014),
    (34.15, -0.05, 0.012, -0.006),
    (34.70, -0.045, 0.008, -0.004),
    (35.20, -0.048, 0.010, -0.004),
    (35.80, -0.08, 0.025, -0.010),
    (36.40, -0.175, 0.060, -0.020),
    (37.10, -0.200, 0.072, -0.024),
    (37.80, -0.190, 0.068, -0.020),
    (38.60, -0.12, 0.040, -0.010),
    (39.30, -0.04, 0.010, -0.002),
    (40.20, 0.0, 0.0, 0.0),
    (81.00, 0.0, 0.0, 0.0),
]

WALK_SPANS = [(19.80, 22.70), (23.55, 31.10), (39.50, 55.90), (66.10, 68.00)]
RUN_SPANS = [(63.15, 66.05)]
STEP_DURS = (0.61, 0.67, 0.58, 0.64, 0.70, 0.60, 0.66, 0.59, 0.71, 0.63)


def span_w(t, spans, fade):
    best = 0.0
    for a, b in spans:
        if a <= t <= b:
            edge = min(t - a, b - t, fade) / fade
            best = max(best, max(0.0, min(1.0, edge)) ** 1.3)
    return best


def build_steps(durs, until):
    steps, t, i = [], 0.0, 0
    while t < until + 2:
        d = durs[i % len(durs)]
        side = 1 if i % 2 == 0 else -1
        az = 0.011 + 0.008 * ((i * 3) % 5) / 4.0
        ax = 0.008 + 0.008 * ((i * 2) % 4) / 3.0
        ay = 0.004 + 0.005 * ((i * 5) % 3) / 2.0
        steps.append((t, t + d, az, ax, ay, side))
        t += d
        i += 1
    return steps


STEPS = build_steps(STEP_DURS, DURATION)


def _step_vert(u):
    if u < 0.12:
        return ff.lerp(0.0, -0.28, u / 0.12)
    if u < 0.28:
        return ff.lerp(-0.28, 0.06, (u - 0.12) / 0.16)
    if u < 0.52:
        return ff.lerp(0.06, 1.0, (u - 0.28) / 0.24)
    if u < 0.78:
        return ff.lerp(1.0, 0.16, (u - 0.52) / 0.26)
    return ff.lerp(0.16, 0.0, (u - 0.78) / 0.22)


def _step_lat(u, side):
    if u < 0.16:
        k = 1.0
    elif u < 0.46:
        k = ff.lerp(1.0, 0.08, (u - 0.16) / 0.30)
    else:
        k = ff.lerp(0.08, -1.0, (u - 0.46) / 0.54)
    return side * k


def body_offset(t):
    ww = span_w(t, WALK_SPANS, 0.28)
    rw = span_w(t, RUN_SPANS, 0.22)
    w = max(ww, rw)
    scale = 1.0 + 1.15 * rw
    x = y = z = 0.0
    roll = pitch = yaw = 0.0
    if w > 1e-4:
        for a, b, az, ax, ay, side in STEPS:
            if a <= t <= b:
                u = (t - a) / max(1e-6, b - a)
                z = w * az * scale * _step_vert(u)
                x = w * ax * scale * _step_lat(u, side)
                y = w * ay * scale * (1.0 if u < 0.5 else -0.4)
                roll = w * math.radians((0.32 + 0.7 * rw) * _step_lat(u, side))
                pitch = w * math.radians(-0.20 * scale * _step_vert(u))
                yaw = w * math.radians(0.10 * side)
                break
    idle = 1.0 - w
    br = 3.4 + 0.9 * math.sin(t * 0.11)
    z += (0.0016 + 0.0012 * idle) * math.sin(t * 2 * math.pi / max(3.1, br))
    x += idle * 0.0005 * math.sin(t * 0.47 + 0.8)
    if 2.10 <= t <= 2.55:
        env = (1.0 - (t - 2.10) / 0.45) ** 1.5
        z += 0.004 * env * (1 if t < 2.28 else -1)
    return x, y, z, pitch, roll, yaw


def hand_cam(t):
    hx = 0.0010 * math.sin(t * 4.6 + 0.3) + 0.0004 * math.sin(t * 1.5)
    hy = 0.0008 * math.sin(t * 3.7 + 1.1)
    hz = 0.0006 * math.sin(t * 3.1 + 0.7)
    rx = math.radians(0.05 * math.sin(t * 3.5))
    ry = math.radians(0.04 * math.sin(t * 4.4 + 1.2))
    rz = math.radians(0.05 * math.sin(t * 5.0 + 0.8))
    if 71.4 <= t <= 71.8:
        k = 1.0 - abs(t - 71.6) / 0.2
        hx += 0.002 * k
        rz += math.radians(0.35 * k)
    return hx, hy, hz, rx, ry, rz


def animate_cam(root, body, head, hand, cam):
    for t, x, y, z, yaw in ROOT_KEYS:
        insert_xyz(root, "location", frame_at(t), (x, y, z))
        insert_xyz(root, "rotation_euler", frame_at(t), (0.0, 0.0, math.radians(yaw)))
    for t, roll in ROLL_KEYS:
        insert_xyz(cam, "rotation_euler", frame_at(t), (0.0, 0.0, math.radians(roll)))
    ff.shape_sparse_fcurves(root)
    ff.shape_sparse_fcurves(cam)
    dt = 1.0 / FPS
    t = 0.0
    last = -1
    while t <= DURATION + 1e-6:
        f = frame_at(t)
        if f != last:
            w = max(span_w(t, WALK_SPANS, 0.28), span_w(t, RUN_SPANS, 0.22))
            dense = w > 0.02 or (f % 3 == 1) or t < 6.2 or t > 70.5
            if dense:
                bx, by, bz, bp, br, bya = body_offset(t)
                insert_xyz(body, "location", f, (bx, by, bz))
                insert_xyz(body, "rotation_euler", f, (bp, br, bya))
                pitch, hyaw = ff.sample_keys(LOOK_KEYS, t, 2)
                pitch -= math.degrees(bp) * 0.62
                hyaw -= math.degrees(bya) * 0.58
                insert_xyz(head, "rotation_euler", f, (math.radians(90.0 + pitch), 0.0, math.radians(hyaw)))
                px, py, pz = ff.sample_keys(PEEK_KEYS, t, 3)
                insert_xyz(head, "location", f, (px - 0.62 * bx, py - 0.30 * by, pz - 0.22 * bz))
            if dense or (f % 4 == 1):
                hx, hy, hz, hrx, hry, hrz = hand_cam(t)
                insert_xyz(hand, "location", f, (hx, hy, hz))
                insert_xyz(hand, "rotation_euler", f, (hrx, hry, hrz))
            last = f
        t += dt
    ff.add_noise_mods(hand, "location", 13.0, 0.00028, 1.6)
    ff.add_noise_mods(hand, "rotation_euler", 18.0, 0.00022, 3.1)


def build_rig(col):
    root = ff.make_empty("POV_ROOT", col, 0.22)
    body = ff.make_empty("BODY_MOTION", col, 0.12)
    head = ff.make_empty("HEAD_MOTION", col, 0.10)
    hand = ff.make_empty("HAND_MOTION", col, 0.08)
    data = bpy.data.cameras.new("CAM_MAIN")
    data.lens = 28.0
    data.sensor_width = 36.0
    data.sensor_height = 27.0
    data.sensor_fit = "HORIZONTAL"
    data.clip_start = 0.03
    data.clip_end = 60.0
    data.dof.use_dof = False
    cam = bpy.data.objects.new("CAM_MAIN", data)
    col.objects.link(cam)
    osd = ff.make_empty("CAM_OSD", col, 0.04)
    osd.parent = None
    root.location = (-2.86, 2.24, 0.090)
    root.rotation_euler = (0.0, 0.0, math.radians(-140.0))
    head.rotation_mode = "XYZ"
    head.rotation_euler = (math.radians(74.0), 0.0, math.radians(8.0))
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = (0.0, 0.0, math.radians(27.0))
    ff.parent_local(body, root)
    ff.parent_local(head, body)
    ff.parent_local(hand, head)
    ff.parent_local(cam, hand)
    bpy.context.scene.camera = cam
    return root, body, head, hand, cam


# ---------------------------------------------------------------------------
# OSD
# ---------------------------------------------------------------------------

def write_osd_sequence():
    last = OSD_SEQ_DIR / f"osd_{FRAME_END:04d}.png"
    if OSD_MOV.exists() and last.exists():
        print("OSD master exists, skipping rebuild")
        return OSD_MOV
    OSD_SEQ_DIR.mkdir(parents=True, exist_ok=True)
    img = ff.ensure_osd_scratch()
    cache = {}
    for f in range(1, FRAME_END + 1):
        key = ff.osd_cache_key(f)
        src = OSD_SEQ_DIR / f"src_{key[0]:03d}_{int(key[1])}_{int(key[2])}.png"
        if key not in cache:
            img.pixels = ff.build_osd_pixels(f)
            img.filepath_raw = str(src)
            img.file_format = "PNG"
            img.save()
            cache[key] = src
        dst = OSD_SEQ_DIR / f"osd_{f:04d}.png"
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        try:
            dst.symlink_to(cache[key].name)
        except OSError:
            shutil.copyfile(cache[key], dst)
    subprocess.check_call(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", "30",
         "-i", str(OSD_SEQ_DIR / "osd_%04d.png"), "-c:v", "png", "-pix_fmt", "rgba", str(OSD_MOV)]
    )
    print("OSD unique", len(cache), OSD_MOV)
    return OSD_MOV


def load_osd_movie():
    existing = bpy.data.images.get("OSD_TIMER")
    if existing is not None:
        bpy.data.images.remove(existing)
    img = bpy.data.images.load(str(OSD_MOV), check_existing=False)
    img.name = "OSD_TIMER"
    img.source = "MOVIE"
    iu = getattr(img, "image_user", None)
    if iu is not None:
        iu.frame_duration = FRAME_END
        iu.frame_start = 1
        iu.use_auto_refresh = True
    return img


def setup_osd(scene, cam, osd_img):
    ff.setup_osd_compositor(scene, osd_img)
    ff.attach_camera_osd(cam, osd_img)
    scene.render.use_compositing = False
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.resolution_x = OSD_W
    scene.render.resolution_y = OSD_H


# ---------------------------------------------------------------------------
# Checks / preview
# ---------------------------------------------------------------------------

def look_vector(cam):
    return (cam.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()


def cam_roll_deg(cam):
    mw = cam.matrix_world.to_3x3()
    right = (mw @ Vector((1, 0, 0))).normalized()
    up = (mw @ Vector((0, 1, 0))).normalized()
    return math.degrees(math.atan2(right.dot(Vector((0, 0, 1))), up.dot(Vector((0, 0, 1)))))


def collision_report():
    dg = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    cam = bpy.data.objects["CAM_MAIN"]
    problems = []
    dirs = [Vector((1, 0, 0)), Vector((-1, 0, 0)), Vector((0, 1, 0)), Vector((0, -1, 0)),
            Vector((0.7, 0.7, 0)), Vector((-0.7, 0.7, 0))]
    skip = ("BLOOD", "OSD", "CAM_", "HAND", "Door_", "BEYOND")
    for f in range(1, FRAME_END + 1, 4):
        scene.frame_set(f)
        dg.update()
        p = cam.matrix_world.translation.copy()
        t = (f - 1) / 30.0
        r = 0.12 if 31.5 <= t <= 40.5 or t >= 71.0 else 0.18
        if t < 3.1 and (p.z < 0.04 or p.z > 0.18):
            problems.append(f"f{f} floor z {p.z:.3f}")
        elif t > 6.0 and t < 70.0 and (p.z < 1.32 or p.z > 1.85):
            problems.append(f"f{f} height {p.z:.3f}")
        if t >= 6.0 and abs(cam_roll_deg(cam)) > 12.0 and t < 62.5:
            problems.append(f"f{f} roll {cam_roll_deg(cam):.1f}")
        for d in dirs:
            hit, loc, nor, idx, obj, mat = scene.ray_cast(dg, p, d)
            if not hit or obj is None:
                continue
            if any(s in obj.name for s in skip):
                continue
            if (loc - p).length < r:
                problems.append(f"f{f} clip {(loc-p).length:.3f} {obj.name}")
                break
    return problems


def print_sanity():
    labels = (
        (0.0, "floor"), (2.25, "contact"), (4.2, "pickup"), (5.7, "settled"),
        (7.3, "blood"), (13.2, "look west"), (17.2, "notice exit"),
        (22.5, "walk pause"), (31.3, "pre-peek"), (33.2, "peek1"),
        (34.7, "retract"), (37.1, "peek2"), (41.0, "enter corr"),
        (46.0, "corr A"), (55.9, "hall B"), (56.8, "lookback"),
        (60.5, "listen"), (63.6, "run"), (68.5, "entrance"),
        (71.5, "hand miss"), (72.4, "grip"), (75.6, "door open"),
        (78.0, "cut"),
    )
    scene = bpy.context.scene
    for t, lab in labels:
        scene.frame_set(frame_at(t))
        bpy.context.evaluated_depsgraph_get().update()
        cam = bpy.data.objects["CAM_MAIN"]
        p = cam.matrix_world.translation
        v = look_vector(cam)
        yaw = math.degrees(math.atan2(-v.x, v.y))
        print(f"  t={t:5.2f} {lab:12s} ({p.x:6.2f},{p.y:6.2f},{p.z:5.2f}) "
              f"yaw={yaw:7.1f} roll={cam_roll_deg(cam):5.1f}")


STILLS = (
    (1, "floor"), (68, "contact"), (160, "pickup"), (220, "blood"),
    (400, "look"), (996, "peek1"), (1042, "retract"), (1114, "peek2"),
    (1680, "hallb"), (1705, "lookback"), (1910, "run"),
    (2056, "entrance"), (2146, "hand"), (2172, "grip"), (2233, "swing"), (2270, "door"), (2341, "cut"),
)


def overlay_osd(jpg: Path, frame: int):
    src = OSD_SEQ_DIR / f"osd_{frame:04d}.png"
    if not src.exists():
        png = jpg.with_suffix(".osd.png")
        img = ff.paint_osd_image(frame)
        img.filepath_raw = str(png)
        img.file_format = "PNG"
        img.save()
        src = png
    tmp = jpg.with_suffix(".comp.jpg")
    subprocess.check_call(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(jpg), "-i", str(src),
         "-filter_complex", "overlay=0:0", "-q:v", "3", str(tmp)]
    )
    tmp.replace(jpg)


def render_stills(scene):
    out = PREVIEW_DIR / "check"
    out.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.image_settings.file_format = "JPEG"
    scene.render.use_compositing = False
    for f, lab in STILLS:
        scene.frame_set(f)
        path = out / f"{lab}_{f:04d}.jpg"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        overlay_osd(path, f)
        print("still", path)
    return out


def render_preview(scene):
    frames = PREVIEW_DIR / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.filepath = str(frames / "frame_")
    scene.render.image_settings.file_format = "JPEG"
    scene.render.use_compositing = False
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    bpy.ops.render.render(animation=True)
    osd_dir = PREVIEW_DIR / "osd"
    osd_dir.mkdir(parents=True, exist_ok=True)
    for f in range(1, FRAME_END + 1):
        src = OSD_SEQ_DIR / f"osd_{f:04d}.png"
        dst = osd_dir / f"osd_{f:04d}.png"
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.symlink_to(src)
    out = PREVIEW_DIR / "found_footage_master_preview.mp4"
    subprocess.check_call(
        ["ffmpeg", "-y", "-framerate", "30", "-i", str(frames / "frame_%04d.jpg"),
         "-framerate", "30", "-i", str(osd_dir / "osd_%04d.png"),
         "-i", str(SFX_MIX),
         "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
         "-map", "[v]", "-map", "2:a",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-c:a", "aac", "-shortest", str(out)]
    )
    print("Wrote", out)
    return out


def clear_cam_take():
    if COLL in bpy.data.collections:
        col = bpy.data.collections[COLL]
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    keep = {"BLOOD.RoomA.Dried"}
    for obj in list(bpy.data.objects):
        if obj.name in keep:
            continue
        if obj.name.startswith("OSD_") or obj.name in {
            "POV_ROOT", "BODY_MOTION", "HEAD_MOTION", "HAND_MOTION",
            "CAM_MAIN", "CAM_OSD", "CAM_PATH_GUIDE",
        }:
            bpy.data.objects.remove(obj, do_unlink=True)


def main():
    args = parse_args()
    scene = bpy.context.scene
    ff.hide_previous_take()
    clear_cam_take()
    blood = rebuild_blood()
    print("Blood rebuilt", tuple(round(x, 3) for x in blood.dimensions))
    door_col = new_col(DOOR_COLL)
    hinge, leaf, handle, frame = build_door(door_col)
    build_beyond(door_col)
    hand_col = new_col(HAND_COLL)
    hand_root, arm, hand_mesh = build_hand_rig(hand_col)
    col = ff.new_col(COLL)
    root, body, head, hand, cam = build_rig(col)
    animate_cam(root, body, head, hand, cam)
    animate_hand_and_door(hand_root, arm, hand_mesh, hinge, handle)
    vibrate_lights(scene)
    ff.unregister_osd_handler()
    write_osd_sequence()
    osd_img = load_osd_movie()
    setup_osd(scene, cam, osd_img)
    make_soundtrack()
    print("Sanity:")
    print_sanity()
    problems = collision_report()
    print("Collision/horizon hits", len(problems))
    for line in problems[:30]:
        print(" ", line)
    print("Door objects", [o.name for o in door_col.objects])
    bpy.context.view_layer.update()
    print("Door leaf", tuple(round(x, 3) for x in leaf.dimensions),
          "hinge", tuple(round(x, 3) for x in hinge.location))
    print("Handle world", tuple(round(x, 3) for x in handle.matrix_world.translation))
    print("Hand bones", [b.name for b in arm.data.bones])
    print("Hand verts", len(hand_mesh.data.vertices))
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH, "frames", 1, FRAME_END)
    if args["mode"] == "stills":
        render_stills(scene)
    elif args["mode"] == "preview":
        render_preview(scene)


if __name__ == "__main__":
    main()
