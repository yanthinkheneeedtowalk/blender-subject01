#!/usr/bin/env python3
"""Read-only inspect of hallway.blend for the Part 1 4K official pass.

Never saves. Never opens part2_basement.blend.
"""

from __future__ import annotations

import json
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "renders" / "hallway_4k_official" / "inspect.json"


def action_fcurves(action):
    curves = []
    if action is None:
        return curves
    if hasattr(action, "fcurves") and action.fcurves:
        return list(action.fcurves)
    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for bag in getattr(strip, "channelbags", []) or []:
                curves.extend(list(getattr(bag, "fcurves", []) or []))
    return curves


def cam_keys(name: str) -> dict:
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"missing": True}
    rec = {
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "lens": getattr(obj.data, "lens", None),
        "sensor_width": getattr(obj.data, "sensor_width", None),
        "clip_start": getattr(obj.data, "clip_start", None),
        "clip_end": getattr(obj.data, "clip_end", None),
        "keys": [],
    }
    ad = obj.animation_data
    action = ad.action if ad else None
    rec["action"] = action.name if action else None
    for fc in action_fcurves(action):
        if fc.data_path == "location" and fc.array_index == 1:
            rec["keys"] = [[int(k.co[0]), round(float(k.co[1]), 4)] for k in fc.keyframe_points]
    return rec


def main() -> None:
    scene = bpy.context.scene
    stop = [o.name for o in bpy.data.objects if "STOP" in o.name.upper()]
    stop += [c.name for c in bpy.data.collections if "STOP" in c.name.upper()]
    images = []
    for img in bpy.data.images:
        if img.name in {"Render Result", "Viewer Node"}:
            continue
        images.append({
            "name": img.name,
            "size": list(img.size) if img.size else [0, 0],
            "source": img.source,
            "packed": bool(img.packed_file),
            "filepath": img.filepath,
            "colorspace": getattr(img, "colorspace_settings", None) and img.colorspace_settings.name,
        })
    world = scene.world
    world_strength = None
    if world and world.node_tree:
        for n in world.node_tree.nodes:
            if n.type == "BACKGROUND":
                world_strength = n.inputs["Strength"].default_value
    view = scene.view_settings
    lights = []
    for o in bpy.data.objects:
        if o.type != "LIGHT":
            continue
        lights.append({
            "name": o.name,
            "type": o.data.type,
            "energy": o.data.energy,
            "color": list(o.data.color),
            "loc": list(o.location),
        })
    report = {
        "filepath": bpy.data.filepath,
        "engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage],
        "fps": scene.render.fps,
        "fps_base": scene.render.fps_base,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "use_motion_blur": scene.render.use_motion_blur,
        "film_transparent": scene.render.film_transparent,
        "camera": scene.camera.name if scene.camera else None,
        "objects": len(bpy.data.objects),
        "materials": len(bpy.data.materials),
        "meshes": len(bpy.data.meshes),
        "images": images,
        "stop_names": stop,
        "CAM_P105_WALK": cam_keys("CAM_P105_WALK"),
        "FINAL_DOOR_SLAB": bool(bpy.data.objects.get("FINAL_DOOR_SLAB")),
        "FINAL_DOOR_HINGE": bool(bpy.data.objects.get("FINAL_DOOR_HINGE")),
        "WALL.End": bool(bpy.data.objects.get("WALL.End")),
        "world_strength": world_strength,
        "view_transform": view.view_transform,
        "look": view.look,
        "exposure": view.exposure,
        "gamma": view.gamma,
        "lights": lights,
        "cycles": {},
        "eevee": {},
    }
    if hasattr(scene, "cycles"):
        c = scene.cycles
        report["cycles"] = {
            "device": getattr(c, "device", None),
            "samples": getattr(c, "samples", None),
            "use_denoising": getattr(c, "use_denoising", None),
            "denoiser": getattr(c, "denoiser", None),
            "max_bounces": getattr(c, "max_bounces", None),
        }
    if hasattr(scene, "eevee"):
        e = scene.eevee
        report["eevee"] = {
            "taa_render_samples": getattr(e, "taa_render_samples", None),
            "use_raytracing": getattr(e, "use_raytracing", None),
            "use_motion_blur": getattr(scene.render, "use_motion_blur", None),
        }
    prefs = bpy.context.preferences.addons.get("cycles")
    devices = []
    if prefs:
        cprefs = prefs.preferences
        try:
            cprefs.get_devices()
        except Exception as exc:
            devices.append({"error": str(exc)})
        for compute in ("CUDA", "OPTIX", "HIP", "ONEAPI", "METAL", "NONE"):
            try:
                cprefs.compute_device_type = compute
                cprefs.get_devices()
                for d in cprefs.devices:
                    devices.append({"type": d.type, "name": d.name, "use": d.use, "compute": compute})
            except Exception:
                pass
    report["cycles_devices"] = devices
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2)[:12000])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
