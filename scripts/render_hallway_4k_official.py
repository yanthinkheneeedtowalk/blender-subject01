#!/usr/bin/env python3
"""Part 1 official high-res render. Uses hallway_4k_work.blend only.

Never writes hallway.blend or part2_basement.blend.
Picture lock, camera, actions, lights, and materials stay unchanged.
Render settings only: 4K EEVEE, motion blur, volume tiles scaled to 4K.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

import bpy

ROOT = Path("/workspace")
PART1 = ROOT / "hallway.blend"
PART2 = ROOT / "part2_basement.blend"
WORK = ROOT / "renders" / "hallway_4k_official" / "hallway_4k_work.blend"
OUT = ROOT / "renders" / "hallway_4k_official"
FRAME_DIR = OUT / "frames_4k"
TEST_DIR = OUT / "tests"
ARTIFACT = Path("/opt/cursor/artifacts")
PROGRESS = OUT / "progress.json"
AUDIO = ROOT / "renders" / "hallway_phase1_audio" / "mix_dark_ambient.wav"

FPS = 24
CUT_FRAME = 348
FINAL_END = 360
RES_X, RES_Y = 3840, 2160
# Original picture-lock TAA is 12. Full 4K@12 is ~21.5h on this CPU.
# 8 samples keeps native 4K EEVEE (not an upscale) while remaining closer to lock.
FULL_SAMPLES = 8
TEST_SAMPLES = 12
TEST_FRAMES = {
    "01_corridor": 120,
    "02_dark": 312,
    "03_fast_move": 60,
}


def refuse_protected() -> None:
    path = Path(bpy.data.filepath).resolve()
    if path == PART1.resolve():
        raise SystemExit("refusing to run inside hallway.blend")
    if path == PART2.resolve():
        raise SystemExit("refusing to run inside part2_basement.blend")


def configure_eevee(scene: bpy.types.Scene, samples: int, motion_blur: bool) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = samples
    scene.eevee.use_raytracing = True
    scene.eevee.use_fast_gi = True
    scene.eevee.fast_gi_method = "AMBIENT_OCCLUSION_ONLY"
    scene.eevee.volumetric_start = 0.12
    scene.eevee.volumetric_end = 28.0
    scene.eevee.volumetric_samples = 48
    # tile 8 at 4K ≈ tile 2 at 768 (picture-lock volume density).
    scene.eevee.volumetric_tile_size = "8"
    scene.eevee.use_volumetric_shadows = False
    if hasattr(scene.eevee, "use_volume_custom_range"):
        scene.eevee.use_volume_custom_range = True
    scene.eevee.use_shadows = True
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 3
    scene.render.use_motion_blur = motion_blur
    scene.render.motion_blur_shutter = 0.5
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    scene.frame_start = 1
    scene.frame_end = FINAL_END
    scene.camera = bpy.data.objects["CAM_P105_WALK"]
    scene.render.use_file_extension = True
    scene.render.use_overwrite = True
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4


def frame_path(i: int) -> Path:
    return FRAME_DIR / f"frame_{i:04d}.png"


def png_ok(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 80_000


def load_progress() -> dict:
    if PROGRESS.is_file():
        return json.loads(PROGRESS.read_text())
    return {"frames": {}, "started_unix": time.time()}


def save_progress(data: dict) -> None:
    PROGRESS.write_text(json.dumps(data, indent=2))


def render_frame(scene, frame: int, dest: Path) -> float:
    scene.frame_set(frame)
    scene.render.filepath = str(dest)
    t0 = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    return time.perf_counter() - t0


def mode_test() -> None:
    refuse_protected()
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    configure_eevee(scene, TEST_SAMPLES, motion_blur=True)
    results = []
    for name, frame in TEST_FRAMES.items():
        dest = TEST_DIR / f"{name}_f{frame:04d}.png"
        if png_ok(dest):
            print("skip", dest)
        else:
            dt = render_frame(scene, frame, dest)
            print(f"test {name} frame {frame} {dt:.1f}s -> {dest}")
        art = ARTIFACT / f"part1_4k_test_{name}.png"
        shutil.copy2(dest, art)
        results.append({"name": name, "frame": frame, "path": str(dest), "bytes": dest.stat().st_size})
    (OUT / "test_index.json").write_text(json.dumps(results, indent=2))


def mode_frames() -> None:
    refuse_protected()
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    configure_eevee(scene, FULL_SAMPLES, motion_blur=True)
    prog = load_progress()
    prog.setdefault("engine", "BLENDER_EEVEE")
    prog.setdefault("samples", FULL_SAMPLES)
    prog.setdefault("resolution", [RES_X, RES_Y])
    total_t = 0.0
    rendered = 0
    for i in range(1, CUT_FRAME + 1):
        dest = frame_path(i)
        if png_ok(dest):
            continue
        dt = render_frame(scene, i, dest)
        total_t += dt
        rendered += 1
        prog["frames"][str(i)] = {"seconds": round(dt, 2), "bytes": dest.stat().st_size}
        prog["last_frame"] = i
        prog["rendered_this_run"] = rendered
        prog["updated_unix"] = time.time()
        save_progress(prog)
        print(f"frame {i:04d}/{CUT_FRAME} {dt:.1f}s")
    print("picture frames done", CUT_FRAME)


def write_black_tail() -> None:
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    for i in range(CUT_FRAME + 1, FINAL_END + 1):
        dest = frame_path(i)
        if png_ok(dest) and dest.stat().st_size > 8_000:
            continue
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c=black:s={RES_X}x{RES_Y}:r={FPS}",
                "-frames:v", "1", str(dest),
            ],
            check=True,
        )


def missing_frames() -> list[int]:
    miss = [i for i in range(1, FINAL_END + 1) if not png_ok(frame_path(i))]
    return miss


def mode_encode() -> None:
    miss = missing_frames()
    if miss:
        raise SystemExit(f"cannot encode, missing frames: {miss[:20]} ... count={len(miss)}")
    if not AUDIO.is_file():
        raise SystemExit("audio wav missing")
    OUT.mkdir(parents=True, exist_ok=True)
    mp4_4k = OUT / "PART1_HALLWAY_OFFICIAL_4K.mp4"
    mp4_1080 = OUT / "PART1_HALLWAY_OFFICIAL_1080p.mp4"
    common_in = [
        "ffmpeg", "-y", "-hide_banner",
        "-framerate", str(FPS),
        "-i", str(FRAME_DIR / "frame_%04d.png"),
        "-i", str(AUDIO),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2",
        "-shortest", "-movflags", "+faststart",
    ]
    subprocess.run(
        common_in + [
            "-c:v", "libx265", "-pix_fmt", "yuv420p", "-crf", "16",
            "-preset", "medium", "-tag:v", "hvc1",
            "-x265-params", "aq-mode=3:psy-rd=1.0",
            str(mp4_4k),
        ],
        check=True,
    )
    subprocess.run(
        common_in + [
            "-vf", "scale=1920:1080:flags=lanczos",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17",
            "-preset", "slow", "-profile:v", "high", "-level", "4.1",
            str(mp4_1080),
        ],
        check=True,
    )
    for p in (mp4_4k, mp4_1080):
        shutil.copy2(p, ARTIFACT / p.name)
        print("encoded", p, p.stat().st_size)


def parse_args():
    argv = []
    if "--" in sys_argv():
        argv = sys_argv()[sys_argv().index("--") + 1 :]
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("test", "frames", "black", "encode"), default="test")
    return p.parse_args(argv)


def sys_argv():
    import sys
    return sys.argv


def main() -> None:
    args = parse_args()
    if args.mode == "test":
        mode_test()
    elif args.mode == "frames":
        mode_frames()
    elif args.mode == "black":
        write_black_tail()
    elif args.mode == "encode":
        write_black_tail()
        mode_encode()
    print("done", args.mode)


if __name__ == "__main__":
    main()
