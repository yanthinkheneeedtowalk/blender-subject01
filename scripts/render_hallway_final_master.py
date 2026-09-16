#!/usr/bin/env python3
"""Render the accepted temporal LookDev scene as the final master.

Unlike ``build_hallway_final_door_sequence.py --final``, this entry point
does not rerun the older scene-setup pass.  It reapplies the accepted
reference-directed materials and puddles, then renders the existing 15-second
door event without replacing that LookDev work.

Modes:
  --smoke   render representative frames and print their dimensions
  --master  render frames 1-348, add the intentional black tail, and encode
            the 360-frame / 15-second H.264 master
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_hallway_final_door_sequence as final_pass
import build_hallway_final_temporal_lookdev as temporal

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "renders" / "hallway_final_master"
VIDEO_PATH = OUTPUT_DIR / "FINAL_BACKROOMS_LEVEL2_TEMPORAL_LOOKDEV_MASTER.mp4"
REPORT_PATH = OUTPUT_DIR / "final_master_validation.json"
FRAME_DIR = Path("/tmp/hallway_final_master_frames")
SMOKE_DIR = Path("/tmp/hallway_final_master_smoke")

FINAL_END = final_pass.FINAL_END
CUT_FRAME = final_pass.CUT_FRAME
RES_X = final_pass.RES_X
RES_Y = final_pass.RES_Y
FPS = final_pass.FPS
SMOKE_FRAMES = (1, 191, 241, CUT_FRAME)


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--smoke" in argv:
        return "smoke"
    if "--master" in argv:
        return "master"
    return "master"


def prepare_scene() -> bpy.types.Scene:
    # This is intentionally the temporal LookDev pass, not final_pass.setup_scene().
    temporal.apply_lookdev()
    scene = bpy.context.scene
    final_pass.configure_eevee(scene, FRAME_DIR)
    scene.camera = bpy.data.objects[final_pass.WALK_CAM]
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.fps = FPS
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    scene.frame_start = 1
    scene.frame_end = CUT_FRAME
    return scene


def clear_frame_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def render_smoke(scene: bpy.types.Scene) -> dict:
    clear_frame_dir(SMOKE_DIR)
    scene.render.filepath = str(SMOKE_DIR / "smoke_")
    rendered = []
    for frame in SMOKE_FRAMES:
        scene.frame_set(frame)
        scene.render.filepath = str(SMOKE_DIR / f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        rendered.append(str(SMOKE_DIR / f"frame_{frame:04d}.png"))
    result = {
        "mode": "smoke",
        "frames": list(SMOKE_FRAMES),
        "resolution": [RES_X, RES_Y],
        "files": rendered,
    }
    print(json.dumps(result, indent=2))
    return result


def render_master(scene: bpy.types.Scene) -> dict:
    clear_frame_dir(FRAME_DIR)
    scene.frame_start = 1
    scene.frame_end = CUT_FRAME
    scene.render.filepath = str(FRAME_DIR / "frame_")
    bpy.ops.render.render(animation=True)
    rendered_scene_frames = len(list(FRAME_DIR.glob("frame_*.png")))
    if rendered_scene_frames != CUT_FRAME:
        raise RuntimeError(
            f"Expected {CUT_FRAME} scene frames, found {rendered_scene_frames}"
        )

    black_frames = FINAL_END - CUT_FRAME
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={RES_X}x{RES_Y}:r={FPS}",
            "-frames:v",
            str(black_frames),
            "-start_number",
            str(CUT_FRAME + 1),
            str(FRAME_DIR / "frame_%04d.png"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    total_frames = len(list(FRAME_DIR.glob("frame_*.png")))
    if total_frames != FINAL_END:
        raise RuntimeError(f"Expected {FINAL_END} total frames, found {total_frames}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-start_number",
            "1",
            "-i",
            str(FRAME_DIR / "frame_%04d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(VIDEO_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_frames",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(VIDEO_PATH),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = {
        "mode": "master",
        "source_scene_frames": rendered_scene_frames,
        "black_tail_frames": black_frames,
        "total_frames": total_frames,
        "fps": FPS,
        "resolution": [RES_X, RES_Y],
        "video": str(VIDEO_PATH),
        "ffprobe": json.loads(probe.stdout),
    }
    REPORT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    scene = prepare_scene()
    if parse_mode() == "smoke":
        render_smoke(scene)
    else:
        render_master(scene)
    scene.frame_start = 1
    scene.frame_end = FINAL_END
    scene.frame_set(1)
    scene.camera = bpy.data.objects[final_pass.WALK_CAM]
    bpy.ops.wm.save_as_mainfile(filepath=str(temporal.BLEND_PATH))


if __name__ == "__main__":
    main()
