#!/usr/bin/env python3
"""Hard cut to black when the door is open (post, picture lock).

PHASE_1_STABLE picture currently holds the half-open door through frame 360.
Original door pass cut to black at Blender frame 349 (video n=348, 14.50 s).
This overlays a full-frame black box from that frame to the end.
Audio is copied. Scene / camera / lights / materials are not edited.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "renders" / "hallway_phase1_audio"
OUT_DIR = SRC_DIR
FPS = 24
# Blender frame 349 == 0-based video index 348.
BLACK_FROM_N = 348
JOBS = (
    (
        SRC_DIR / "phase1_audio_environment_only.mp4",
        OUT_DIR / "phase1_audio_environment_only_blackcut.mp4",
    ),
    (
        SRC_DIR / "phase1_audio_dark_ambient.mp4",
        OUT_DIR / "phase1_audio_dark_ambient_blackcut.mp4",
    ),
)


def apply(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:"
        f"enable='gte(n,{BLACK_FROM_N})'"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(dest),
    ]
    subprocess.check_call(cmd)


def probe(path: Path) -> dict:
    raw = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-print_format", "json", str(path)]
    )
    return json.loads(raw)


def main() -> None:
    for src, dest in JOBS:
        if not src.exists():
            raise SystemExit(f"missing {src}")
        apply(src, dest)
        info = probe(dest)
        print("wrote", dest, "dur", info["format"].get("duration"))


if __name__ == "__main__":
    main()
