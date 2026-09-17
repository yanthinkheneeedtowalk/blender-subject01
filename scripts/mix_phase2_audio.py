#!/usr/bin/env python3
"""Spatial mixdown for the Phase 2 review camera.

Camera XYZ is interpolated from CAM_P2_REVIEW keys.  Sector stems fade by
distance so transitions stay continuous — no hard track cuts.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
P1 = ROOT / "assets" / "hallway_phase1_environment"
P2 = ROOT / "assets" / "hallway_phase2_spatial"
OUT = ROOT / "renders" / "hallway_phase2_spatial" / "phase2_mixdown.wav"
SR = 44100
FPS = 24
FRAMES = 720
DURATION = FRAMES / FPS

ROUTE = (
    (1, (0.00, 1.85, 1.68)),
    (40, (0.00, 4.55, 1.68)),
    (72, (0.02, 6.20, 1.68)),
    (120, (-2.20, 6.12, 1.68)),
    (160, (-3.25, 6.12, 1.68)),
    (210, (-4.35, 8.15, 1.42)),
    (280, (-4.36, 9.40, 1.36)),
    (340, (-4.36, 8.05, 1.46)),
    (400, (-4.08, 3.40, 1.68)),
    (455, (-4.40, 1.18, 1.68)),
    (510, (-6.95, 1.16, 1.68)),
    (555, (-4.38, 2.35, 1.68)),
    (600, (-4.35, 6.12, 1.68)),
    (645, (-7.00, 6.42, 1.68)),
    (685, (-3.05, 6.16, 1.68)),
    (720, (0.00, 7.15, 1.68)),
)

SOURCES = (
    dict(file="p2_amb_level2.wav", loc=None, vol=0.78, dist=1.0, dmax=99.0, spatial=False, pack="p2"),
    dict(file="p2_rare_structure.wav", loc=None, vol=0.38, dist=1.0, dmax=99.0, spatial=False, pack="p2"),
    dict(file="p2_pipe_dense_rumble.wav", loc=(-3.05, 6.20, 1.55), vol=0.70, dist=1.4, dmax=7.5, spatial=True, pack="p2"),
    dict(file="p2_hot_steam.wav", loc=(-4.40, 10.90, 1.40), vol=0.66, dist=1.2, dmax=8.0, spatial=True, pack="p2"),
    dict(file="p2_thermal_tick.wav", loc=(-3.52, 10.85, 2.18), vol=0.44, dist=1.0, dmax=7.0, spatial=True, pack="p2"),
    dict(file="p2_vent_fan.wav", loc=(-5.30, 2.85, 2.00), vol=0.60, dist=1.2, dmax=8.5, spatial=True, pack="p2"),
    dict(file="p2_maint_hum.wav", loc=(-6.80, 6.40, 1.20), vol=0.48, dist=0.9, dmax=6.0, spatial=True, pack="p2"),
    dict(file="p2_shaft_reverb.wav", loc=(-5.00, 7.22, 3.40), vol=0.52, dist=1.5, dmax=7.5, spatial=True, pack="p2"),
    dict(file="p2_steam_hub.wav", loc=(-2.55, 7.28, 2.38), vol=0.72, dist=0.9, dmax=8.0, spatial=True, pack="p2"),
    dict(file="p2_steam_hot_a.wav", loc=(-3.52, 10.85, 2.22), vol=0.78, dist=0.8, dmax=8.5, spatial=True, pack="p2"),
    dict(file="p2_steam_hot_b.wav", loc=(-5.22, 12.40, 2.18), vol=0.74, dist=0.8, dmax=8.5, spatial=True, pack="p2"),
    dict(file="local_pipe_rumble.wav", loc=(0.84, 14.62, 2.20), vol=0.42, dist=1.4, dmax=11.0, spatial=True, pack="p1"),
    dict(file="local_electrical_hum.wav", loc=(1.02, 10.70, 1.36), vol=0.22, dist=1.0, dmax=8.0, spatial=True, pack="p1"),
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


def camera_samples(n: int) -> np.ndarray:
    frames = np.linspace(1.0, FRAMES, n)
    keys = np.array([k[0] for k in ROUTE], dtype=np.float64)
    locs = np.array([k[1] for k in ROUTE], dtype=np.float64)
    out = np.empty((n, 3), dtype=np.float64)
    for i, f in enumerate(frames):
        if f <= keys[0]:
            out[i] = locs[0]
            continue
        if f >= keys[-1]:
            out[i] = locs[-1]
            continue
        idx = int(np.searchsorted(keys, f) - 1)
        t = (f - keys[idx]) / (keys[idx + 1] - keys[idx])
        # Ease slightly so sector entries are not linear snaps.
        t = t * t * (3.0 - 2.0 * t)
        out[i] = locs[idx] * (1.0 - t) + locs[idx + 1] * t
    return out


def attenuate(dist: np.ndarray, ref: float, dmax: float) -> np.ndarray:
    g = ref / np.maximum(dist, 0.35)
    g = np.clip(g, 0.0, 1.0)
    g = np.where(dist > dmax, g * np.clip(1.0 - (dist - dmax) / 4.5, 0.0, 1.0), g)
    return g


def mix() -> Path:
    n = int(DURATION * SR)
    cam = camera_samples(n)
    acc = np.zeros((n, 2), dtype=np.float64)
    for src in SOURCES:
        pack = P2 if src["pack"] == "p2" else P1
        path = pack / src["file"]
        if not path.exists():
            print("skip missing", path)
            continue
        data = read_wav(path)
        if data.shape[0] < n:
            reps = int(np.ceil(n / data.shape[0]))
            data = np.tile(data, (reps, 1))
        data = data[:n]
        if not src["spatial"]:
            acc += data * src["vol"]
            continue
        x, y, z = src["loc"]
        dist = np.sqrt((x - cam[:, 0]) ** 2 + (y - cam[:, 1]) ** 2 + (z - cam[:, 2]) ** 2)
        gain = attenuate(dist, src["dist"], src["dmax"]) * src["vol"]
        pan = np.clip((x - cam[:, 0]) / 2.4, -0.85, 0.85)
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
    print("wrote", OUT, "peak", float(peak), "dur", DURATION)
    return OUT


if __name__ == "__main__":
    mix()
