#!/usr/bin/env python3
"""Time Cycles CPU vs EEVEE on the Part 1 working copy. Does not save hallway.blend."""

from __future__ import annotations

import json
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "renders" / "hallway_4k_official" / "hallway_4k_work.blend"
PART1 = ROOT / "hallway.blend"
OUT_DIR = ROOT / "renders" / "hallway_4k_official" / "bench"
REPORT = ROOT / "renders" / "hallway_4k_official" / "bench.json"


def configure_cycles(scene, samples: int) -> None:
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.03
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 3
    scene.cycles.transmission_bounces = 4
    scene.cycles.transparent_max_bounces = 4
    scene.cycles.volume_bounces = 1
    scene.render.use_persistent_data = True
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    if hasattr(scene.render, "motion_blur_position"):
        scene.render.motion_blur_position = "CENTER"


def configure_eevee(scene, samples: int) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = samples
    scene.eevee.use_raytracing = True
    scene.eevee.use_fast_gi = True
    try:
        scene.eevee.fast_gi_method = "AMBIENT_OCCLUSION_ONLY"
    except TypeError:
        pass
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.render.use_persistent_data = True


def render_one(scene, frame, w, h, path: Path) -> float:
    scene.camera = bpy.data.objects["CAM_P105_WALK"]
    scene.frame_set(frame)
    scene.render.resolution_x = w
    scene.render.resolution_y = h
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(path)
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    t0 = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    dt = time.perf_counter() - t0
    print(f"RENDERED {path.name} {w}x{h} {dt:.2f}s")
    return dt


def main() -> None:
    if Path(bpy.data.filepath).resolve() == PART1.resolve():
        raise SystemExit("refusing to benchmark inside hallway.blend")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    jobs = []

    configure_cycles(scene, 32)
    dt = render_one(scene, 120, 960, 540, OUT_DIR / "cycles_960x540_s32_f120.png")
    jobs.append({"engine": "CYCLES", "res": [960, 540], "samples": 32, "frame": 120, "seconds": round(dt, 2)})

    configure_eevee(scene, 24)
    dt = render_one(scene, 120, 3840, 2160, OUT_DIR / "eevee_4k_s24_f120.png")
    jobs.append({"engine": "EEVEE", "res": [3840, 2160], "samples": 24, "frame": 120, "seconds": round(dt, 2)})

    # Scale estimates for 348 picture frames (1-348) + 12 black encoded.
    cyc = next(j for j in jobs if j["engine"] == "CYCLES")
    eev = next(j for j in jobs if j["engine"] == "EEVEE")
    # 4K / 960x540 = 16x pixels
    cycles_4k_s32 = cyc["seconds"] * 16
    cycles_4k_s128 = cycles_4k_s32 * (128 / 32)
    cycles_full_s128_h = cycles_4k_s128 * 348 / 3600
    eevee_full_s64_h = eev["seconds"] * (64 / 24) * 348 / 3600
    report = {
        "jobs": jobs,
        "hardware": "4-core Xeon CPU, no GPU",
        "estimates_hours": {
            "cycles_cpu_4k_128spp_348f": round(cycles_full_s128_h, 2),
            "eevee_4k_64spp_348f": round(eevee_full_s64_h, 2),
        },
        "cycles_4k_s32_sec_per_frame_est": round(cycles_4k_s32, 1),
        "cycles_4k_s128_sec_per_frame_est": round(cycles_4k_s128, 1),
        "eevee_4k_s24_sec_per_frame": eev["seconds"],
    }
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
