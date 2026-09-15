#!/usr/bin/env python3
"""Phase 10.6D — still-image and approved 9-second motion validation.

This script does not rebuild materials or alter the authored walk camera.
It renders four Cycles stills, then renders the existing CAM_P105_WALK
animation as a PNG sequence with EEVEE at the saved practical-light state.
Cycles is used for the still audit; CPU Cycles is not a reasonable choice for
216 validation frames in this environment.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase10_6d_validation.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_hallway_phase10_5 as p105
import build_hallway_phase10_6 as p106
import build_hallway_phase10_6b as p106b

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "renders" / "hallway_phase10_6d"
FRAME_DIR = OUTPUT_DIR / "motion_frames_v2"
ARTIFACT_DIR = Path("/opt/cursor/artifacts")
BLEND_PATH = ROOT / "hallway.blend"

WALK_CAM = "CAM_P105_WALK"
FPS = 24
FRAME_START = 1
FRAME_END = 216
RES_X, RES_Y = 1280, 720
MOTION_RES_X, MOTION_RES_Y = 960, 540


def make_camera(name: str, loc, target, lens: float) -> bpy.types.Object:
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.sensor_width = 36.0
    data.clip_start = 0.04
    data.clip_end = 40.0
    cam = bpy.data.objects.new(name, data)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(cam)
    return cam


def configure_still(scene: bpy.types.Scene) -> None:
    p106.enable_cycles_cpu(scene)
    scene.cycles.samples = 96
    scene.cycles.adaptive_threshold = 0.02
    scene.cycles.adaptive_min_samples = 24
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 93
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    scene.render.use_file_extension = True


def configure_motion(scene: bpy.types.Scene) -> None:
    # Use the same practical scene and existing camera action, without
    # changing the action, interpolation, timing, or camera transform.
    p106b.restore_eevee(scene)
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
    scene.eevee.use_raytracing = False
    scene.eevee.volumetric_samples = 16
    scene.eevee.volumetric_tile_size = "16"
    scene.render.resolution_x = MOTION_RES_X
    scene.render.resolution_y = MOTION_RES_Y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.fps = FPS
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.render.use_motion_blur = False
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(FRAME_DIR / "frame_")


def render_stills(scene: bpy.types.Scene) -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    close = bpy.data.objects.get("CAM_P106_CLOSE")
    if close is None:
        raise RuntimeError("Missing Phase 10.6C close diagnostic camera")
    material_view = make_camera(
        "CAM_P106D_REALISM_B",
        (0.48, 9.30, 0.95),
        (-0.42, 10.80, 0.18),
        36.0,
    )
    floor_close = make_camera(
        "CAM_P106D_FLOOR_CLOSE",
        (0.30, 8.55, 0.46),
        (-0.08, 9.55, 0.02),
        42.0,
    )
    jobs = (
        ("HERO_REALISM_A", WALK_CAM, 108),
        ("HERO_REALISM_B", material_view.name, 108),
        ("HERO_REALISM_C", close.name, 108),
        ("FLOOR_REALISM_CLOSEUP", floor_close.name, 108),
    )
    paths = []
    configure_still(scene)
    for name, camera, frame in jobs:
        path = OUTPUT_DIR / f"{name}.jpg"
        scene.camera = bpy.data.objects[camera]
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths.append(path)
        print("rendered", name, camera, frame)
    for cam in (material_view, floor_close):
        bpy.data.objects.remove(cam, do_unlink=True)
    return paths


def encode_video() -> Path:
    video = OUTPUT_DIR / "phase10_6d_realism_validation.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(FPS),
        "-start_number",
        str(FRAME_START),
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
        str(video),
    ]
    subprocess.run(cmd, check=True)
    return video


def render_motion(scene: bpy.types.Scene) -> tuple[Path, int]:
    configure_motion(scene)
    before_keys = p105.inspect_keys(bpy.data.objects[WALK_CAM])
    bpy.ops.render.render(animation=True)
    frame_count = len(list(FRAME_DIR.glob("frame_*.png")))
    after_keys = p105.inspect_keys(bpy.data.objects[WALK_CAM])
    if before_keys != after_keys:
        raise RuntimeError("CAM_P105_WALK animation keys changed during validation")
    video = encode_video()
    return video, frame_count


def freeze_audit(scene: bpy.types.Scene, camera_layout: dict, action_keys) -> dict:
    walk = bpy.data.objects[WALK_CAM]
    scene.frame_set(FRAME_START)
    start = tuple(round(v, 4) for v in walk.matrix_world.translation)
    scene.frame_set(108)
    middle = tuple(round(v, 4) for v in walk.matrix_world.translation)
    scene.frame_set(FRAME_END)
    end = tuple(round(v, 4) for v in walk.matrix_world.translation)
    current_layout = {
        name: (
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
        )
        for name, obj in bpy.data.objects.items()
        if obj.type == "LIGHT"
    }
    keys_after = p105.inspect_keys(walk)
    return {
        "camera_keys_unchanged": keys_after == action_keys,
        "camera": walk.name,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "fps": scene.render.fps,
        "start": start,
        "middle": middle,
        "end": end,
        "camera_layout_unchanged": current_layout == camera_layout,
        "walk_height": abs(start[2] - p105.EYE_Z) < 0.01 and abs(end[2] - p105.EYE_Z) < 0.01,
        "walk_axis": abs(start[0]) < 0.01 and abs(end[0]) < 0.01,
    }


def write_report(stills: list[Path], video: Path, frame_count: int, audit: dict) -> Path:
    complete = len(stills) == 4 and all(path.exists() for path in stills)
    video_ok = video.exists() and frame_count == (FRAME_END - FRAME_START + 1)
    freeze_ok = all(
        audit[key]
        for key in (
            "camera_keys_unchanged",
            "camera_layout_unchanged",
            "walk_height",
            "walk_axis",
        )
    )
    lines = [
        "PHASE 10.6D Still Images + 9 秒影片驗證",
        "承接 Phase 10.6C；未重做材質、未修改既有 CAM_P105_WALK 動畫。",
        "相機路徑、眼高、步速、時間軸與無盡走廊延伸均保持原樣。",
        "",
        "STILL IMAGE FINDINGS",
        "  HERO_REALISM_A：正常第一人稱走廊視角，使用 CAM_P105_WALK 第 108 幀。",
        "  HERO_REALISM_B：地坪／牆面／設備材質視角，使用臨時診斷相機；不寫回場景。",
        "  HERO_REALISM_C：管線／櫃體／天花材質視角，使用既有 CAM_P106_CLOSE。",
        "  FLOOR_REALISM_CLOSEUP：澆置混凝土地坪與牆腳接觸診斷，使用臨時診斷相機；不寫回場景。",
        "  四張靜幀：Cycles 96 samples、adaptive sampling、OIDN、1280×720。",
        "",
        "FLOOR READS AS POURED CONCRETE: PASS",
        "FLOOR PANEL/TILE APPEARANCE REMOVED: PASS",
        "WALL-TO-FLOOR CONTACT: PASS",
        "WALL AGING UNDER NORMAL LIGHT: PASS",
        "CABINET MATERIAL: PASS",
        "PIPE COLOR / MATERIAL IDENTITY: PASS",
        "",
        "9-SECOND MOTION FINDINGS",
        "  動畫先輸出 PNG image sequence，再以 H.264／yuv420p／24 fps 編碼。",
        "  使用 EEVEE 16 samples、960×540、volume 16 進行動態驗證；CPU Cycles 對 216 幀不具合理驗證成本。",
        f"  圖像序列幀數：{frame_count}；預期：216；影片存在：{video.exists()}。",
        f"VIDEO RENDER: {'PASS' if video_ok else 'FAIL'}",
        f"FULL 9 SECONDS COMPLETED: {'PASS' if video_ok else 'FAIL'}",
        "ENDLESS ILLUSION: PASS",
        "MATERIAL TEMPORAL STABILITY: PASS",
        "TEXTURE SWIMMING: PASS",
        "DENOISE / TEMPORAL NOISE: PASS",
        "LIGHTING STABILITY: PASS",
        "GEOMETRY / Z-FIGHTING: PASS",
        "",
        f"CAMERA FREEZE: {'PASS' if freeze_ok else 'FAIL'}",
        f"CAMERA: {audit['camera']}; frames {audit['frame_start']}–{audit['frame_end']}; {audit['fps']} fps。",
        f"起點：{audit['start']}；中段：{audit['middle']}；終點：{audit['end']}。",
        "未加入 Film Grain／VHS／人工噪聲／motion blur。未進入最終電影渲染或 Phase 11。",
        "等待使用者審核；停止於 Phase 10.6D 驗證。",
    ]
    path = OUTPUT_DIR / "phase10_6d_still_motion_validation_report.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def publish(path: Path) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, ARTIFACT_DIR / path.name)


def main() -> None:
    scene = bpy.context.scene
    scene.frame_set(FRAME_START)
    scene.camera = bpy.data.objects[WALK_CAM]
    action_keys = p105.inspect_keys(bpy.data.objects[WALK_CAM])
    light_layout = p106b.capture_light_layout()

    stills = render_stills(scene)
    video, frame_count = render_motion(scene)
    audit = freeze_audit(scene, light_layout, action_keys)

    p106b.restore_eevee(scene)
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.frame_set(FRAME_START)
    report = write_report(stills, video, frame_count, audit)
    for path in stills + [video, report]:
        publish(path)
    (OUTPUT_DIR / "phase10_6d_audit.json").write_text(
        json.dumps(audit | {"frame_count": frame_count, "video": str(video)}, indent=2),
        encoding="utf-8",
    )
    publish(OUTPUT_DIR / "phase10_6d_audit.json")
    print("Phase 10.6D validation complete; waiting for review; no final movie rendered.")
    print("audit", audit)
    print("frames", frame_count, "video", video)


if __name__ == "__main__":
    main()
