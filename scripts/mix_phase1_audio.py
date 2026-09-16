#!/usr/bin/env python3
"""Spatial mixdown for Phase 1 review video.

Blender 5.2 mixdown did not reliably emit a WAV in this environment, so the
review MP4 is mixed here from the same stems placed as Speakers / VSE strips
in the scene.  Distance attenuation follows CAM_P105_WALK Y keys.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "assets" / "hallway_phase1_environment"
OUT = ROOT / "renders" / "hallway_phase1_environment" / "phase1_mixdown.wav"
SR = 44100
FPS = 24
FRAMES = 360
DURATION = FRAMES / FPS

# Camera Y keys from the frozen CAM_P105_WALK animation.
CAM_KEYS = ((1, 1.4), (216, 14.0), (360, 18.0))
EAR_X, EAR_Z = 0.0, 1.68

SOURCES = (
    dict(file="amb_level2_loop.wav", loc=None, vol=0.90, dist=1.0, dmax=99.0, spatial=False),
    dict(file="rare_distant_structure.wav", loc=None, vol=0.55, dist=1.0, dmax=99.0, spatial=False),
    dict(file="local_pipe_rumble.wav", loc=(0.84, 14.62, 2.20), vol=0.70, dist=1.4, dmax=11.0, spatial=True),
    dict(file="local_vent_hum.wav", loc=(-1.00, 12.05, 1.68), vol=0.55, dist=1.1, dmax=9.0, spatial=True),
    dict(file="local_electrical_hum.wav", loc=(1.02, 10.70, 1.36), vol=0.38, dist=1.0, dmax=8.0, spatial=True),
    dict(file="local_water_drip.wav", loc=(-0.42, 17.90, 0.12), vol=0.62, dist=0.9, dmax=7.5, spatial=True),
    dict(file="local_water_drip.wav", loc=(0.55, 15.09, 0.10), vol=0.40, dist=0.9, dmax=7.0, spatial=True),
    dict(file="local_metal_tick.wav", loc=(-0.84, 17.84, 2.46), vol=0.42, dist=1.2, dmax=10.0, spatial=True),
    dict(file="local_steam_hiss_a.wav", loc=(0.84, 14.62, 2.43), vol=0.80, dist=0.8, dmax=8.5, spatial=True),
    dict(file="local_steam_hiss_b.wav", loc=(1.01, 15.09, 2.43), vol=0.80, dist=0.8, dmax=8.5, spatial=True),
    dict(file="local_steam_hiss_c.wav", loc=(-0.84, 17.84, 2.46), vol=0.80, dist=0.8, dmax=8.5, spatial=True),
)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "r") as w:
        nch = w.getnchannels()
        n = w.getnframes()
        sr = w.getframerate()
        raw = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    if nch == 2:
        stereo = raw.reshape(-1, 2)
    else:
        stereo = np.stack([raw, raw], axis=1)
    if sr != SR:
        raise RuntimeError(f"unexpected sample rate {sr} in {path}")
    return stereo


def camera_y_samples(n: int) -> np.ndarray:
    frames = np.linspace(1.0, FRAMES, n)
    y = np.empty(n, dtype=np.float64)
    for i, f in enumerate(frames):
        if f <= 216:
            t = (f - 1.0) / 215.0
            y[i] = 1.4 + (14.0 - 1.4) * t
        else:
            t = (f - 216.0) / 144.0
            y[i] = 14.0 + (18.0 - 14.0) * t
    return y


def attenuate(dist: np.ndarray, ref: float, dmax: float) -> np.ndarray:
    g = ref / np.maximum(dist, 0.35)
    g = np.clip(g, 0.0, 1.0)
    g = np.where(dist > dmax, g * np.clip(1.0 - (dist - dmax) / 4.0, 0.0, 1.0), g)
    return g


def mix() -> Path:
    n = int(DURATION * SR)
    cam_y = camera_y_samples(n)
    acc = np.zeros((n, 2), dtype=np.float64)
    for src in SOURCES:
        path = ASSET / src["file"]
        data = read_wav(path)
        if data.shape[0] < n:
            pad = np.zeros((n - data.shape[0], 2))
            data = np.concatenate([data, pad], axis=0)
        data = data[:n]
        if not src["spatial"]:
            acc += data * src["vol"]
            continue
        x, y, z = src["loc"]
        dist = np.sqrt((x - EAR_X) ** 2 + (y - cam_y) ** 2 + (z - EAR_Z) ** 2)
        gain = attenuate(dist, src["dist"], src["dmax"]) * src["vol"]
        pan = np.clip(x / 1.15, -0.85, 0.85)
        left = gain * (1.0 - 0.5 * (pan + 1.0))
        right = gain * (0.5 * (pan + 1.0))
        acc[:, 0] += data[:, 0] * left
        acc[:, 1] += data[:, 1] * right
    peak = np.max(np.abs(acc)) or 1.0
    acc = acc / peak * 0.89
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(acc, -1.0, 1.0) * 32000.0).astype(np.int16)
    with wave.open(str(OUT), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", OUT, "peak", float(peak))
    return OUT


if __name__ == "__main__":
    mix()
