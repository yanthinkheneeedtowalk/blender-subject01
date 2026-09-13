#!/usr/bin/env python3
"""Fast CPU preview render for an already-open .blend file.

This environment has no GPU. Unreal / EEVEE / game engines are not faster
here: they need rasterization hardware. Cycles with few samples plus
OpenImageDenoise is the path that actually finishes in seconds.

Usage:
  blender -b house.blend --python scripts/render_fast.py
  blender -b single_room.blend --python scripts/render_fast.py -- --out renders/single_room_fast.png
  blender -b house.blend --python scripts/render_fast.py -- --samples 8 --width 960
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    out = {
        "samples": 12,
        "width": 1280,
        "out": None,
    }
    i = 0
    while i < len(argv):
        if argv[i] == "--samples" and i + 1 < len(argv):
            out["samples"] = int(argv[i + 1])
            i += 1
        elif argv[i] == "--width" and i + 1 < len(argv):
            out["width"] = int(argv[i + 1])
            i += 1
        elif argv[i] == "--out" and i + 1 < len(argv):
            out["out"] = argv[i + 1]
            i += 1
        i += 1
    return out


def default_out_path() -> Path:
    blend = Path(bpy.data.filepath) if bpy.data.filepath else ROOT / "untitled.blend"
    return ROOT / "renders" / f"{blend.stem}_fast.png"


def configure_fast(args: dict) -> Path:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args["samples"]
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "use_adaptive_sampling"):
        scene.cycles.use_adaptive_sampling = True
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4

    src_w = max(1, scene.render.resolution_x)
    src_h = max(1, scene.render.resolution_y)
    width = args["width"]
    height = max(1, round(src_h * (width / src_w)))
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"

    dest = Path(args["out"]) if args["out"] else default_out_path()
    if not dest.is_absolute():
        dest = ROOT / dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(dest)
    return dest


def main() -> None:
    args = parse_args()
    dest = configure_fast(args)
    print(
        f"Fast render: {args['samples']} samples, "
        f"{bpy.context.scene.render.resolution_x}x{bpy.context.scene.render.resolution_y} -> {dest}",
        flush=True,
    )
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"Rendered {dest} in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
