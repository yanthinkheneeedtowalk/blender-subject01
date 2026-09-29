#!/usr/bin/env python3
"""Read-only inspect of frame/cloth/cables/lights in part2_basement.blend."""

from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Vector

OUT = Path("/workspace/renders/part2_basement/frame_cloth_inspect.json")


def dump_mat(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        return None
    rec = {"name": name, "blend": getattr(mat, "blend_method", None)}
    if hasattr(mat, "surface_render_method"):
        rec["surface_render_method"] = mat.surface_render_method
    if not mat.use_nodes:
        return rec
    rec["nodes"] = []
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        rec["principled"] = {}
        for key in ("Base Color", "Roughness", "Metallic", "Specular IOR Level", "Transmission Weight", "Alpha", "IOR"):
            if key in bsdf.inputs:
                val = bsdf.inputs[key].default_value
                rec["principled"][key] = list(val) if hasattr(val, "__iter__") and not isinstance(val, str) else val
    rec["node_types"] = sorted({n.type for n in mat.node_tree.nodes})
    return rec


def main():
    names = [
        "P2_FRAME_ROOT", "P2_FRAME_OUTER", "P2_FRAME_GLASS", "P2_FRAME_PHOTO",
        "P2_FRAME_DUST", "P2_FRAME_STAIN", "P2_CLOTH",
        "CAM_P2_SIT", "CAM_P2_DESK", "CAM_P2_WIDE",
        "LIGHT_P2_DESK_PENDANT", "LIGHT_P2_FRAME_KISS", "LIGHT_P2_CLUTTER_KICK",
        "LIGHT_P2_FLOOR_GLANCE", "LIGHT_P2_ROOM_CONTOUR",
    ]
    objs = {}
    for n in names:
        o = bpy.data.objects.get(n)
        if o is None:
            objs[n] = None
            continue
        rec = {
            "type": o.type,
            "loc": [round(v, 5) for v in o.location],
            "rot": [round(v, 5) for v in o.rotation_euler],
            "dim": [round(v, 5) for v in o.dimensions],
            "parent": o.parent.name if o.parent else None,
            "mats": [s.material.name for s in o.material_slots if s.material],
            "verts": len(o.data.vertices) if o.type == "MESH" else None,
        }
        if o.type == "LIGHT":
            rec["energy"] = o.data.energy
            rec["color"] = list(o.data.color)
            rec["ltype"] = o.data.type
        if o.type == "CAMERA":
            rec["lens"] = o.data.lens
        objs[n] = rec
    cables = []
    for o in bpy.data.objects:
        if o.name.startswith("P2_CABLE_"):
            cables.append({
                "name": o.name,
                "type": o.type,
                "bevel": getattr(o.data, "bevel_depth", None) if o.type == "CURVE" else None,
            })
    photo = bpy.data.images.get("P2_PHOTO_BLUR")
    report = {
        "filepath": bpy.data.filepath,
        "objects": objs,
        "cables": cables,
        "materials": {
            n: dump_mat(n)
            for n in ("MAT_P2_Glass", "MAT_P2_Dust", "MAT_P2_Cloth", "MAT_P2_Photo", "MAT_P2_Frame", "MAT_P2_Cable")
        },
        "photo_image": None if photo is None else {
            "size": list(photo.size),
            "packed": bool(photo.packed_file),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("filepath", "photo_image")}, indent=2))
    for n, rec in objs.items():
        print(n, rec)
    print("cables", len(cables))
    for n, m in report["materials"].items():
        print("MAT", n, None if m is None else m.get("principled"), m.get("node_types") if m else None)


if __name__ == "__main__":
    main()
