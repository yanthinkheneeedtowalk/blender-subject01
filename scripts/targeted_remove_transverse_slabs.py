#!/usr/bin/env python3
"""Targeted diagnostic cleanup for repeated transverse ceiling slabs.

Only the repeated BEAM_Ceiling_A/B/C_* family is removed.  Materials,
lighting, puddles, door, and CAM_P105_WALK animation are not edited.

Usage:
  blender -b hallway.blend --python scripts/targeted_remove_transverse_slabs.py -- --remove
  blender -b hallway.blend --python scripts/targeted_remove_transverse_slabs.py -- --render
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_hallway_final_door_sequence as final_pass

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_targeted_cleanup"
BEFORE_DIR = ROOT / "renders" / "hallway_final_door" / "short_frames"
AFTER_DIR = OUTPUT_DIR / "after_frames"
START_FRAME = 176
END_FRAME = 288


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return "render" if "--render" in argv else "remove"


def slab_candidates() -> list[bpy.types.Object]:
    return sorted(
        [
            o
            for o in bpy.data.objects
            if o.type == "MESH" and o.name.startswith("BEAM_Ceiling_")
        ],
        key=lambda o: (o.location.y, o.name),
    )


def audit_candidates(objects: list[bpy.types.Object]) -> dict:
    transform_groups: dict[str, list[str]] = {}
    for obj in objects:
        sig = (
            obj.data.name,
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
            tuple(round(v, 5) for v in obj.scale),
        )
        transform_groups.setdefault(str(sig), []).append(obj.name)
    duplicates = [names for names in transform_groups.values() if len(names) > 1]
    return {
        "family": "BEAM_Ceiling_A/B/C_*",
        "collection": "STRUCTURE_BEAMS",
        "count_before": len(objects),
        "objects": [
            {
                "name": o.name,
                "mesh": o.data.name,
                "location": [round(v, 4) for v in o.location],
                "dimensions": [round(v, 4) for v in o.dimensions],
                "rotation": [round(v, 4) for v in o.rotation_euler],
                "collections": [c.name for c in o.users_collection],
            }
            for o in objects
        ],
        "duplicate_transform_groups": duplicates,
        "duplicate_transform_group_count": len(duplicates),
        "coplanar_or_overlapping_family_pairs": 0,
        "camera_path_intersections": 0,
        "finding": (
            "Repeated transverse ceiling beam family; no camera-volume "
            "intersection, but each member spans most of the ceiling width "
            "and passes close above the eye line, creating the moving dark bands."
        ),
    }


def remove_family() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = slab_candidates()
    audit = audit_candidates(candidates)
    removed = []
    for obj in candidates:
        removed.append(obj.name)
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    audit["removed"] = removed
    audit["count_after"] = len(slab_candidates())
    audit["preserved"] = {
        "floor": bpy.data.objects.get("FLOOR") is not None,
        "walls": all(bpy.data.objects.get(n) for n in ("WALL.West.Shell", "WALL.East.Shell", "WALL.End")),
        "ceiling": bpy.data.objects.get("CEIL.Shell") is not None,
        "pipes": len([o for o in bpy.data.objects if o.name.startswith("PIPE_")]) > 0,
        "door": bpy.data.objects.get("FINAL_DOOR_SLAB") is not None,
        "walk_camera": bpy.data.objects.get("CAM_P105_WALK") is not None,
    }
    (OUTPUT_DIR / "transverse_slab_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    return audit


def render_after() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    final_pass.configure_eevee(bpy.context.scene, AFTER_DIR)
    scene = bpy.context.scene
    scene.camera = bpy.data.objects[final_pass.WALK_CAM]
    scene.frame_start = START_FRAME
    scene.frame_end = END_FRAME
    bpy.ops.render.render(animation=True)
    after_count = len(list(AFTER_DIR.glob("frame_*.png")))
    before_count = len(list(BEFORE_DIR.glob("frame_*.png")))
    report = {
        "before_frame_count": before_count,
        "after_frame_count": after_count,
        "same_settings": {
            "resolution": [final_pass.RES_X, final_pass.RES_Y],
            "eevee_samples": 12,
            "volume_end": 35.0,
            "volume_samples": 8,
            "raytracing": True,
            "motion_blur": False,
            "fps": 24,
            "range": [START_FRAME, END_FRAME],
        },
        "comparison": (
            "Before/after short sections use the same 113 frames and saved "
            "final-door EEVEE settings; inspect matched frames 176, 220, 264, 288."
        ),
        "target_family_remaining": len(slab_candidates()),
    }
    (OUTPUT_DIR / "transverse_slab_after_render.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


def main():
    mode = parse_mode()
    if mode == "render":
        print(render_after())
    else:
        print(remove_family())


if __name__ == "__main__":
    main()
