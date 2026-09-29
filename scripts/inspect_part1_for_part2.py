#!/usr/bin/env python3
"""Read-only inspect of Part 1 hallway.blend. Does not save."""

from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "renders" / "part2_basement" / "part1_inspect.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

STOP_HITS = []
for coll in bpy.data.collections:
    if "stop" in coll.name.lower():
        STOP_HITS.append(("collection", coll.name))
for obj in bpy.data.objects:
    n = obj.name.lower()
    if "stop" in n or n == "stop event" or "stopevent" in n.replace(" ", "").replace("_", ""):
        STOP_HITS.append(("object", obj.name, obj.type, tuple(round(v, 4) for v in obj.location)))

key_names = [
    "WALL.End", "WALL.Start", "WALL.West.Shell", "WALL.East.Shell", "FLOOR", "CEIL.Shell",
    "FINAL_DOOR_SLAB", "FINAL_DOOR_HINGE", "FINAL_DOOR_RECESS", "FINAL_DOOR_FRAME_L",
    "FINAL_DOOR_FRAME_R", "CAM_P105_WALK", "CAM_P105_WALK.Target",
]


def bounds(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return {
        "min": [round(min(xs), 4), round(min(ys), 4), round(min(zs), 4)],
        "max": [round(max(xs), 4), round(max(ys), 4), round(max(zs), 4)],
        "loc": [round(v, 4) for v in obj.location],
        "hide_render": bool(obj.hide_render),
        "hide_viewport": bool(obj.hide_viewport),
        "type": obj.type,
    }


objs = {}
for name in key_names:
    obj = bpy.data.objects.get(name)
    objs[name] = bounds(obj) if obj else None

def action_fcurves(action):
    if action is None:
        return
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    yield fc


cam = bpy.data.objects.get("CAM_P105_WALK")
cam_keys = []
if cam and cam.animation_data and cam.animation_data.action:
    for fc in action_fcurves(cam.animation_data.action):
        if fc.data_path == "location":
            cam_keys.append({
                "axis": "xyz"[fc.array_index],
                "keys": [[kp.co.x, round(kp.co.y, 4)] for kp in fc.keyframe_points],
            })

scene = bpy.context.scene
report = {
    "blend": bpy.data.filepath,
    "blender": bpy.app.version_string,
    "objects": len(bpy.data.objects),
    "materials": len(bpy.data.materials),
    "lights": len([o for o in bpy.data.objects if o.type == "LIGHT"]),
    "cameras": [o.name for o in bpy.data.objects if o.type == "CAMERA"],
    "collections": sorted(c.name for c in bpy.data.collections),
    "frame_range": [scene.frame_start, scene.frame_end],
    "fps": scene.render.fps,
    "resolution": [scene.render.resolution_x, scene.render.resolution_y],
    "camera": scene.camera.name if scene.camera else None,
    "engine": scene.render.engine,
    "world": scene.world.name if scene.world else None,
    "world_strength": None,
    "stop_hits": STOP_HITS,
    "key_objects": objs,
    "cam_location_keys": cam_keys,
    "actions": [a.name for a in bpy.data.actions],
}
if scene.world and scene.world.node_tree:
    bg = next((n for n in scene.world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg:
        report["world_strength"] = bg.inputs["Strength"].default_value

OUT.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
print("wrote", OUT)
