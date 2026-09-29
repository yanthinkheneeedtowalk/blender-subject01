#!/usr/bin/env python3
"""Dump frame layer local bounds. Read-only besides printing."""
import bpy

names = [
    "P2_FRAME_ROOT",
    "P2_FRAME_OUTER",
    "P2_FRAME_GLASS",
    "P2_FRAME_PHOTO",
    "P2_FRAME_DUST",
    "P2_FRAME_STAIN",
    "P2_CLOTH",
]
for name in names:
    obj = bpy.data.objects.get(name)
    if obj is None:
        print(name, "MISSING")
        continue
    print("===", name, obj.type, "parent=", obj.parent.name if obj.parent else None)
    print("  loc", tuple(round(v, 5) for v in obj.location))
    print("  dim", tuple(round(v, 5) for v in obj.dimensions))
    if obj.type == "MESH":
        xs = [v.co.x for v in obj.data.vertices]
        ys = [v.co.y for v in obj.data.vertices]
        zs = [v.co.z for v in obj.data.vertices]
        print("  verts", len(obj.data.vertices))
        print("  x", round(min(xs), 5), round(max(xs), 5))
        print("  y", round(min(ys), 5), round(max(ys), 5))
        print("  z", round(min(zs), 5), round(max(zs), 5))
        print("  mats", [s.material.name if s.material else None for s in obj.material_slots])
    mw = obj.matrix_world
    print("  world", tuple(round(v, 5) for v in mw.translation))

photo = bpy.data.materials.get("MAT_P2_Photo")
if photo:
    print("PHOTO blend", getattr(photo, "blend_method", None), getattr(photo, "surface_render_method", None))
    for n in photo.node_tree.nodes:
        print("  node", n.type, n.name)
glass = bpy.data.materials.get("MAT_P2_Glass")
if glass:
    print("GLASS blend", getattr(glass, "blend_method", None), getattr(glass, "surface_render_method", None))
dust = bpy.data.materials.get("MAT_P2_Dust")
if dust:
    print("DUST blend", getattr(dust, "blend_method", None), getattr(dust, "surface_render_method", None))
