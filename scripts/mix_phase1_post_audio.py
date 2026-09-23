#!/usr/bin/env python3
"""Mix PHASE_1_STABLE post-audio onto the existing 15 s review picture lock.

Does not touch hallway.blend. Two muxed MP4s:
  environment-only (no dark ambient, no lofi)
  dark-ambient complete (environment + end-corridor swell)
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STEM = ROOT / "assets" / "hallway_phase1_audio"
PIC = ROOT / "renders" / "hallway_phase1_environment" / "phase1_stable_rollback_review.mp4"
OUT_DIR = ROOT / "renders" / "hallway_phase1_audio"
SR = 48000
FPS = 24
FRAMES = 360
DURATION = FRAMES / FPS
EAR_X, EAR_Z = 0.0, 1.68

# Frozen CAM_P105_WALK Y keys.
CAM_KEYS = ((1, 1.4), (216, 14.0), (360, 18.0))

ENV_SOURCES = (
    dict(file="drone_industrial.wav", loc=None, vol=0.78, dist=1.0, dmax=99.0, spatial=False, lp=None),
    dict(file="vent_airflow.wav", loc=(-1.00, 12.05, 1.68), vol=0.52, dist=1.2, dmax=9.0, spatial=True, lp=1800.0),
    dict(file="electrical_metal.wav", loc=(1.02, 10.70, 1.36), vol=0.34, dist=1.0, dmax=8.0, spatial=True, lp=3500.0),
    dict(file="drone_industrial.wav", loc=(0.84, 14.62, 2.20), vol=0.28, dist=1.4, dmax=11.0, spatial=True, lp=900.0),
    dict(file="steam_hiss_a.wav", loc=(0.84, 14.62, 2.43), vol=0.70, dist=0.85, dmax=8.5, spatial=True, lp=7000.0),
    dict(file="steam_hiss_b.wav", loc=(1.01, 15.09, 2.43), vol=0.70, dist=0.85, dmax=8.5, spatial=True, lp=7000.0),
    dict(file="steam_hiss_c.wav", loc=(-0.84, 17.84, 2.46), vol=0.72, dist=0.85, dmax=8.5, spatial=True, lp=7000.0),
    dict(file="water_drip.wav", loc=(-0.42, 17.90, 0.12), vol=0.48, dist=0.9, dmax=7.5, spatial=True, lp=6000.0),
    dict(file="water_drip.wav", loc=(0.55, 15.09, 0.10), vol=0.32, dist=0.9, dmax=7.0, spatial=True, lp=6000.0),
    dict(file="footsteps.wav", loc=None, vol=0.62, dist=1.0, dmax=99.0, spatial=False, lp=None),
    dict(file="cloth_rustle.wav", loc=None, vol=0.38, dist=1.0, dmax=99.0, spatial=False, lp=None),
)

DARK_EXTRA = dict(file="dark_ambient.wav", loc=None, vol=1.0, dist=1.0, dmax=99.0, spatial=False, lp=None)


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
        raise RuntimeError(f"sr {sr} in {path}, expected {SR}")
    return stereo


def write_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1.0, 1.0) * 32000.0).astype(np.int16)
    with wave.open(str(path), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", path)


def lp(x: np.ndarray, cutoff: float) -> np.ndarray:
    taps = max(5, int(SR / max(cutoff, 1.0)))
    if taps % 2 == 0:
        taps += 1
    kernel = np.hanning(taps)
    kernel /= kernel.sum()
    if x.ndim == 1:
        return np.convolve(x, kernel, mode="same")
    return np.stack([np.convolve(x[:, c], kernel, mode="same") for c in range(x.shape[1])], axis=1)


def camera_y(n: int) -> np.ndarray:
    frames = np.linspace(1.0, FRAMES, n)
    y = np.empty(n)
    for i, f in enumerate(frames):
        if f <= 216:
            t = (f - 1.0) / 215.0
            y[i] = 1.4 + 12.6 * t
        else:
            t = (f - 216.0) / 144.0
            y[i] = 14.0 + 4.0 * t
    return y


def attenuate(dist: np.ndarray, ref: float, dmax: float) -> np.ndarray:
    g = ref / np.maximum(dist, 0.35)
    g = np.clip(g, 0.0, 1.0)
    g = np.where(dist > dmax, g * np.clip(1.0 - (dist - dmax) / 4.0, 0.0, 1.0), g)
    return g


def corridor_reverb(x: np.ndarray, wet: np.ndarray) -> np.ndarray:
    """Feedforward corridor taps. wet is 0..1 per sample."""
    out = x.copy()
    taps = ((0.018, 0.20), (0.029, 0.14), (0.047, 0.10), (0.078, 0.07), (0.12, 0.045), (0.19, 0.03))
    for delay_s, g in taps:
        d = int(delay_s * SR)
        echo = np.zeros_like(x)
        echo[d:] = x[:-d] * g
        out += echo * wet[:, None]
    return out


def limiter(x: np.ndarray, ceiling: float = 0.89) -> np.ndarray:
    """Peak-only limiter. No makeup gain — that would erase a dark-end swell."""
    peak = np.max(np.abs(x)) or 1.0
    if peak > ceiling:
        x = x / peak * ceiling
    return x


def makeup(x: np.ndarray, target: float = 0.78) -> tuple[np.ndarray, float]:
    peak = np.max(np.abs(x)) or 1.0
    scale = target / peak
    return x * scale, scale


def mix_layers(sources, cam_y: np.ndarray, n: int) -> np.ndarray:
    acc = np.zeros((n, 2), dtype=np.float64)
    for src in sources:
        path = STEM / src["file"]
        data = read_wav(path)
        if data.shape[0] < n:
            data = np.concatenate([data, np.zeros((n - data.shape[0], 2))], axis=0)
        data = data[:n]
        if src.get("lp"):
            data = lp(data, src["lp"])
        if not src["spatial"]:
            acc += data * src["vol"]
            continue
        x, y, z = src["loc"]
        dist = np.sqrt((x - EAR_X) ** 2 + (y - cam_y) ** 2 + (z - EAR_Z) ** 2)
        gain = attenuate(dist, src["dist"], src["dmax"]) * src["vol"]
        # Distance HF loss: extra LP when far.
        far = np.clip((dist - 2.0) / 10.0, 0.0, 1.0)
        if np.mean(far) > 0.15:
            dull = lp(data, 1600.0)
            data = data * (1.0 - far[:, None] * 0.65) + dull * (far[:, None] * 0.65)
        pan = np.clip(x / 1.15, -0.85, 0.85)
        left = gain * (1.0 - 0.5 * (pan + 1.0))
        right = gain * (0.5 * (pan + 1.0))
        acc[:, 0] += data[:, 0] * left
        acc[:, 1] += data[:, 1] * right
    return acc


def dark_gain(cam_y: np.ndarray) -> np.ndarray:
    # Dead-end / door isolation from y~14 (slowdown) to y=18.
    g = np.clip((cam_y - 12.5) / 5.5, 0.0, 1.0)
    g = g * g * (3.0 - 2.0 * g)
    return 0.08 + 0.72 * g


def bed(n: int, cam_y: np.ndarray) -> np.ndarray:
    acc = mix_layers(ENV_SOURCES, cam_y, n)
    wet = 0.22 + 0.18 * np.clip((cam_y - 8.0) / 10.0, 0.0, 1.0)
    return corridor_reverb(acc, wet)


def mix_environment(n: int, cam_y: np.ndarray, scale: float) -> np.ndarray:
    return limiter(bed(n, cam_y) * scale)


def mix_dark(n: int, cam_y: np.ndarray, scale: float) -> np.ndarray:
    acc = bed(n, cam_y) * scale
    dark = read_wav(STEM / DARK_EXTRA["file"])
    if dark.shape[0] < n:
        dark = np.concatenate([dark, np.zeros((n - dark.shape[0], 2))])
    dark = dark[:n]
    g = dark_gain(cam_y)
    # Extra after shared makeup so the dead-end swell is not limiter-erased.
    acc += dark * ((0.03 + 0.88 * g)[:, None])
    return limiter(acc)


def mux(wav: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(PIC),
        "-i", str(wav),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-shortest",
        "-movflags", "+faststart",
        str(dest),
    ]
    subprocess.check_call(cmd)


def main() -> None:
    if not PIC.exists():
        raise SystemExit(f"missing picture lock {PIC}")
    n = int(DURATION * SR)
    cam_y = camera_y(n)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _, scale = makeup(bed(n, cam_y), target=0.78)
    env = mix_environment(n, cam_y, scale)
    dark = mix_dark(n, cam_y, scale)
    env_wav = OUT_DIR / "mix_environment.wav"
    dark_wav = OUT_DIR / "mix_dark_ambient.wav"
    write_wav(env_wav, env)
    write_wav(dark_wav, dark)
    env_mp4 = OUT_DIR / "phase1_audio_environment_only.mp4"
    dark_mp4 = OUT_DIR / "phase1_audio_dark_ambient.mp4"
    mux(env_wav, env_mp4)
    mux(dark_wav, dark_mp4)
    print("env", env_mp4)
    print("dark", dark_mp4)


if __name__ == "__main__":
    main()
