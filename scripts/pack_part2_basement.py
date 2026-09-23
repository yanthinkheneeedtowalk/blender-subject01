#!/usr/bin/env python3
"""Pack all external data into part2_basement.blend. Does not touch hallway.blend."""

from __future__ import annotations

import json
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
BLEND = ROOT / "part2_basement.blend"
PART1 = ROOT / "hallway.blend"
OUT = ROOT / "renders" / "part2_basement" / "pack_verify.json"


def main() -> None:
    if Path(bpy.data.filepath).resolve() == PART1.resolve():
        raise SystemExit("refusing to pack inside hallway.blend")
    before = []
    for img in bpy.data.images:
        before.append({
            "name": img.name,
            "filepath": img.filepath,
            "packed": bool(img.packed_file),
            "size": list(img.size) if img.size else [0, 0],
            "source": img.source,
        })
    bpy.ops.file.pack_all()
    after = []
    unpacked = []
    for img in bpy.data.images:
        packed = bool(img.packed_file)
        rec = {
            "name": img.name,
            "filepath": img.filepath,
            "packed": packed,
            "size": list(img.size) if img.size else [0, 0],
            "source": img.source,
        }
        after.append(rec)
        if img.source == "FILE" and not packed and img.name not in {"Render Result", "Viewer Node"}:
            unpacked.append(img.name)
    p2_cols = sorted(c.name for c in bpy.data.collections if c.name.startswith("P2_"))
    required = [
        "WALL.End", "FLOOR", "CAM_P105_WALK", "FINAL_DOOR_SLAB",
        "P2_DESK_TOP", "P2_CHAIR_SEAT", "P2_FRAME_OUTER", "P2_CLOTH",
        "P2_CABLE_RIG_01", "CAM_P2_SIT", "CAM_P2_WIDE", "LIGHT_P2_DESK_PENDANT",
    ]
    missing = [n for n in required if bpy.data.objects.get(n) is None]
    report = {
        "blend": bpy.data.filepath,
        "objects": len(bpy.data.objects),
        "materials": len(bpy.data.materials),
        "lights": len([o for o in bpy.data.objects if o.type == "LIGHT"]),
        "cameras": [o.name for o in bpy.data.objects if o.type == "CAMERA"],
        "p2_collections": p2_cols,
        "images_before": before,
        "images_after": after,
        "unpacked_file_images": unpacked,
        "missing_required": missing,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if unpacked:
        raise SystemExit(f"unpack failed: {unpacked}")
    if missing:
        raise SystemExit(f"missing objects: {missing}")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=False)
    print("saved packed", BLEND, "bytes", BLEND.stat().st_size)


if __name__ == "__main__":
    main()
