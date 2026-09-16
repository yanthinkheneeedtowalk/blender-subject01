#!/usr/bin/env python3
"""Final temporal LookDev correction before the master render.

Applies only material/light-strength corrections to the accepted cleaned
scene, then renders short Cycles diagnostics and representative stills.
The existing camera/door animation is not authored here.
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
import build_hallway_phase10_6 as p106
import build_hallway_phase10_6b as p106b
import build_hallway_phase10_6c as p106c
import build_hallway_reference_lookdev as ref

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_final_temporal_lookdev"
DIAG_A = OUTPUT_DIR / "diagnostic_denoise_on"
DIAG_B = OUTPUT_DIR / "diagnostic_denoise_off_high_samples"
STILL_DIR = OUTPUT_DIR / "stills"
DIAG_START, DIAG_END = 120, 143


def action_fcurves(action):
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    yield fc


def scale_non_door_practicals(scale: float = 0.65) -> None:
    scene = bpy.context.scene
    if scene.get("TEMPORAL_LOOKDEV_LIGHT_SCALE") == scale:
        return
    for name in final_pass.ORIGINAL_LIGHTS:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.data.energy *= scale
        if obj.data.animation_data and obj.data.animation_data.action:
            for fc in action_fcurves(obj.data.animation_data.action):
                if fc.data_path == "energy":
                    for kp in fc.keyframe_points:
                        kp.co.y *= scale
        for obj_name in (f"FIX_{name}_Diffuser", f"P8_TUBE_{name}"):
            fixture = bpy.data.objects.get(obj_name)
            if fixture is None or not fixture.data.materials:
                continue
            mat = fixture.data.materials[0]
            if mat.animation_data and mat.animation_data.action:
                for fc in action_fcurves(mat.animation_data.action):
                    if fc.data_path == "default_value":
                        for kp in fc.keyframe_points:
                            kp.co.y *= scale
    scene["TEMPORAL_LOOKDEV_LIGHT_SCALE"] = scale


def apply_lookdev() -> None:
    # Reuse the validated concrete/wall rebuild and reference-directed grime,
    # then reduce only non-door practicals. Door fixture data is untouched.
    ref.rebuild_reference_materials()
    ref.create_blended_puddles()
    scale_non_door_practicals(0.65)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.frame_start = 1
    scene.frame_end = 360
    scene.camera = bpy.data.objects[final_pass.WALK_CAM]
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))


def configure_cycles(scene, samples, denoise):
    p106.enable_cycles_cpu(scene)
    scene.cycles.samples = samples
    scene.cycles.adaptive_threshold = 0.03
    scene.cycles.adaptive_min_samples = 16
    scene.cycles.use_denoising = denoise
    scene.render.resolution_x = 768
    scene.render.resolution_y = 432
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_compositing = False


def render_diagnostic(label: str, samples: int, denoise: bool) -> list[Path]:
    scene = bpy.context.scene
    directory = DIAG_A if denoise else DIAG_B
    directory.mkdir(parents=True, exist_ok=True)
    configure_cycles(scene, samples, denoise)
    scene.camera = bpy.data.objects[final_pass.WALK_CAM]
    paths = []
    for frame in range(DIAG_START, DIAG_END + 1):
        scene.frame_set(frame)
        path = directory / f"frame_{frame:04d}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths.append(path)
    return paths


def diagnostics_json():
    import numpy as np
    from PIL import Image

    def stats(directory):
        means = []
        walls = []
        for path in sorted(directory.glob("frame_*.png")):
            a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
            means.append(float(a.mean()))
            # Stable broad wall ROIs; avoid the dark door event and floor.
            walls.append(float(np.concatenate((a[100:330, 0:210], a[100:330, 558:768]), axis=1).mean()))
        return {
            "count": len(means),
            "global_mean_range": [min(means), max(means)] if means else [],
            "wall_mean_range": [min(walls), max(walls)] if walls else [],
            "wall_temporal_std": float(np.std(walls)) if walls else None,
        }

    result = {
        "section": [DIAG_START, DIAG_END],
        "intentional_light_changes": "none; door event begins at frame 191+",
        "denoise_on": stats(DIAG_A),
        "denoise_off_high_samples": stats(DIAG_B),
        "interpretation": (
            "Compare wall_temporal_std and matched frame images. Any wall "
            "change in this section is unintentional because no practical "
            "light keyframes change."
        ),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "temporal_diagnostic_results.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def render_stills():
    scene = bpy.context.scene
    configure_cycles(scene, 64, True)
    STILL_DIR.mkdir(parents=True, exist_ok=True)
    dry = ref.make_camera("TEMP_DRY_FLOOR", (0.30, 8.8, 0.55), (-0.10, 10.0, 0.02), 40.0)
    damp = ref.make_camera("TEMP_DAMP_TRANSITION", (-0.20, 16.9, 0.58), (0.05, 18.3, 0.02), 38.0)
    puddle = ref.make_camera("TEMP_PUDDLE_REFLECTION", (0.24, 20.7, 0.60), (-0.05, 22.2, 0.02), 40.0)
    walk = bpy.data.objects[final_pass.WALK_CAM]
    jobs = (
        ("DARK_CORRIDOR", walk, 120),
        ("DIRTY_CONCRETE_FLOOR", dry, 120),
        ("DAMP_DRY_PUDDLE", puddle, 270),
        ("DOOR_LIGHT_ON", walk, 300),
        ("DOOR_HALF_OPEN", walk, 348),
    )
    paths = []
    for name, cam, frame in jobs:
        scene.camera = cam
        scene.frame_set(frame)
        path = STILL_DIR / f"{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths.append(path)
    for cam in (dry, damp, puddle):
        bpy.data.objects.remove(cam, do_unlink=True)
    final_pass.configure_eevee(scene, ROOT / "renders" / "hallway_targeted_cleanup" / "final_validation_frames")
    scene.frame_start = 1
    scene.frame_end = 360
    scene.camera = walk
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    return paths


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    mode = "diagnostic" if "--diagnostic" in argv else "stills" if "--stills" in argv else "setup"
    apply_lookdev()
    if mode == "diagnostic":
        render_diagnostic("denoise_on", 64, True)
        render_diagnostic("denoise_off_high_samples", 128, False)
        print(diagnostics_json())
    elif mode == "stills":
        print("stills", render_stills())
    else:
        print("LookDev setup complete")


if __name__ == "__main__":
    main()
