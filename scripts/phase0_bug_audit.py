#!/usr/bin/env python3
"""Read-only Phase 0 scene audit.

Writes static_audit.json and does not alter or save the Blender scene.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_hallway_phase10_5 as p105

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "renders" / "phase0_bug_stabilization"


def action_fcurves(action):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    yield fc


def audit() -> dict:
    scene = bpy.context.scene
    camera = scene.camera
    duplicate_meshes = defaultdict(list)
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.name.startswith("P105_"):
            continue
        sig = (
            obj.data.name,
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
            tuple(round(v, 5) for v in obj.scale),
        )
        duplicate_meshes[str(sig)].append(obj.name)
    duplicate_meshes = [names for names in duplicate_meshes.values() if len(names) > 1]

    duplicate_lights = defaultdict(list)
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        sig = (
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
            round(obj.data.energy, 4),
        )
        duplicate_lights[str(sig)].append(obj.name)
    duplicate_lights = [names for names in duplicate_lights.values() if len(names) > 1]

    broken_images = []
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                path = Path(bpy.path.abspath(node.image.filepath))
                if node.image.source == "FILE" and not path.exists():
                    broken_images.append((mat.name, node.name, str(path)))

    animated_materials = [m.name for m in bpy.data.materials if m.animation_data]
    animated_lights = []
    for obj in bpy.data.objects:
        if obj.type == "LIGHT" and (obj.animation_data or obj.data.animation_data):
            animated_lights.append(obj.name)
    animated_world = bool(scene.world and scene.world.animation_data)
    animated_exposure = False
    if scene.animation_data and scene.animation_data.action:
        animated_exposure = any(
            fc.data_path == "view_settings.exposure"
            for fc in action_fcurves(scene.animation_data.action)
        )

    zero_scale = [
        obj.name
        for obj in bpy.data.objects
        if obj.type in {"MESH", "CURVE"} and any(abs(v) < 1e-6 for v in obj.scale)
    ]
    extreme_scale = [
        (obj.name, tuple(round(v, 4) for v in obj.scale))
        for obj in bpy.data.objects
        if obj.type in {"MESH", "CURVE"}
        and any(abs(v) > 10.0 or (0.0 < abs(v) < 0.1) for v in obj.scale)
    ]

    return {
        "environment": {
            "blender": bpy.app.version_string,
            "render_engine": scene.render.engine,
            "scene": scene.name,
            "camera": camera.name if camera else None,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "fps": scene.render.fps,
            "frame_range": [scene.frame_start, scene.frame_end],
            "view_transform": scene.view_settings.view_transform,
            "exposure": scene.view_settings.exposure,
            "world_strength": (
                scene.world.node_tree.nodes["Background"].inputs[1].default_value
                if scene.world and scene.world.node_tree and scene.world.node_tree.nodes.get("Background")
                else None
            ),
            "objects": len(bpy.data.objects),
            "materials": len(bpy.data.materials),
            "lights": len([o for o in bpy.data.objects if o.type == "LIGHT"]),
            "collections": sorted(c.name for c in bpy.data.collections),
        },
        "geometry": {
            "p105_objects": len([o for o in bpy.data.objects if o.name.startswith("P105_")]),
            "extension_collections": [c.name for c in bpy.data.collections if c.name.startswith("CORRIDOR_EXTENSION")],
            "duplicate_mesh_transform_groups": duplicate_meshes[:50],
            "duplicate_mesh_group_count": len(duplicate_meshes),
            "duplicate_light_transform_groups": duplicate_lights[:50],
            "duplicate_light_group_count": len(duplicate_lights),
            "zero_scale_objects": zero_scale,
            "extreme_scale_objects": extreme_scale[:50],
            "wall_end_visible": not bpy.data.objects["WALL.End"].hide_render
            if bpy.data.objects.get("WALL.End")
            else False,
        },
        "materials": {
            "broken_image_paths": broken_images,
            "animated_materials": animated_materials,
            "legacy_surface_slots": {
                name: [
                    m.name for m in bpy.data.objects[name].data.materials
                ]
                for name in ("FLOOR", "WALL.West.Shell", "WALL.End", "CEIL.Shell")
                if bpy.data.objects.get(name)
            },
        },
        "animation": {
            "camera_keys": p105.inspect_keys(camera) if camera and camera.name == "CAM_P105_WALK" else [],
            "target_keys": (
                p105.inspect_keys(bpy.data.objects["CAM_P105_WALK.Target"])
                if bpy.data.objects.get("CAM_P105_WALK.Target")
                else []
            ),
            "animated_lights": animated_lights,
            "animated_world": animated_world,
            "animated_exposure": animated_exposure,
        },
        "classification": {
            "confirmed_bug_candidates": [],
            "suspected": [
                "部分管線與牆面交界：可能是合理 penetration，未見充分證據，不修改。",
                "部分暗區資訊不足：可能是設計／LookDev，不視為 Bug。",
            ],
            "art_direction_gaps_deferred": [
                "模組重複感",
                "表面老化與鏽蝕不足",
                "局部設備與管線老化世代不一致",
                "部分表面偏平整",
            ],
        },
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = audit()
    path = OUT / "static_audit.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(path)
    print(json.dumps(data["environment"], ensure_ascii=False))


if __name__ == "__main__":
    main()
