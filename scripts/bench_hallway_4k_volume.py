#!/usr/bin/env python3
"""Time EEVEE 4K with volume tiles matched to the 768 picture-lock density."""

from __future__ import annotations

import json
import time
from pathlib import Path

import bpy

PART1 = Path("/workspace/hallway.blend")
OUT = Path("/workspace/renders/hallway_4k_official/bench")
REPORT = Path("/workspace/renders/hallway_4k_official/bench_volume.json")


def main():
    if Path(bpy.data.filepath).resolve() == PART1.resolve():
        raise SystemExit("refusing hallway.blend")
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 12
    scene.eevee.use_raytracing = True
    scene.eevee.use_fast_gi = True
    scene.eevee.fast_gi_method = "AMBIENT_OCCLUSION_ONLY"
    scene.eevee.volumetric_start = 0.12
    scene.eevee.volumetric_end = 28.0
    scene.eevee.volumetric_samples = 48
    scene.eevee.volumetric_tile_size = "8"
    scene.eevee.use_volumetric_shadows = False
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.render.resolution_x = 3840
    scene.render.resolution_y = 2160
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_compositing = False
    scene.camera = bpy.data.objects["CAM_P105_WALK"]
    scene.frame_set(120)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "eevee_4k_s12_tile8_mb_f120.png"
    scene.render.filepath = str(path)
    t0 = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    dt = time.perf_counter() - t0
    rec = {
        "seconds": round(dt, 2),
        "samples": 12,
        "tile": 8,
        "motion_blur": True,
        "hours_348": round(dt * 348 / 3600, 2),
    }
    REPORT.write_text(json.dumps(rec, indent=2))
    print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()
