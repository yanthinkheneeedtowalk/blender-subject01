#!/usr/bin/env python3
"""Synthesize PHASE_1_STABLE post-audio stems.

Original procedural synthesis (no third-party samples). Deterministic seed.
48 kHz stereo WAV stems for the 15 s CAM_P105_WALK review.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "hallway_phase1_audio"
SR = 48000
FPS = 24
FRAMES = 360
DURATION = FRAMES / FPS
N = int(DURATION * SR)
RNG = np.random.default_rng(2102)


def write_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(samples, -1.0, 1.0)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    pcm = (data * 32000.0).astype(np.int16)
    with wave.open(str(path), "w") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", path, "dur", data.shape[0] / SR)


def lp(x: np.ndarray, cutoff: float) -> np.ndarray:
    taps = max(5, int(SR / max(cutoff, 1.0)))
    if taps % 2 == 0:
        taps += 1
    kernel = np.hanning(taps)
    kernel /= kernel.sum()
    if x.ndim == 1:
        return np.convolve(x, kernel, mode="same")
    return np.stack([np.convolve(x[:, c], kernel, mode="same") for c in range(x.shape[1])], axis=1)


def hp(x: np.ndarray, cutoff: float) -> np.ndarray:
    return x - lp(x, cutoff)


def bp(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return lp(hp(x, lo), hi)


def brown(n: int) -> np.ndarray:
    x = np.cumsum(RNG.standard_normal(n))
    x -= x.mean()
    peak = np.max(np.abs(x)) or 1.0
    return x / peak


def fade_edges(x: np.ndarray, seconds: float = 0.04) -> np.ndarray:
    n = int(seconds * SR)
    if n <= 0:
        return x
    env = np.ones(x.shape[0], dtype=np.float64)
    env[:n] *= np.linspace(0.0, 1.0, n)
    env[-n:] *= np.linspace(1.0, 0.0, n)
    if x.ndim == 2:
        env = env[:, None]
    return x * env


def to_stereo(mono: np.ndarray, delay_s: float = 0.012) -> np.ndarray:
    delay = int(delay_s * SR)
    left = mono.copy()
    right = np.concatenate([np.zeros(delay), mono[:-delay]]) if delay else mono.copy()
    return np.stack([left, right], axis=1)


def normalize(x: np.ndarray, peak: float = 0.5) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def industrial_drone() -> np.ndarray:
    t = np.arange(N) / SR
    rumble = lp(brown(N), 70.0)
    rumble = hp(rumble, 16.0)
    beat = 0.55 + 0.45 * np.sin(2 * math.pi * 0.07 * t)
    machine = 0.22 * np.sin(2 * math.pi * 27.4 * t) * (0.6 + 0.4 * np.sin(2 * math.pi * 0.11 * t))
    machine += 0.12 * np.sin(2 * math.pi * 41.0 * t + 0.4)
    pipe = bp(rumble + 0.2 * RNG.standard_normal(N), 50.0, 180.0)
    mono = 0.62 * rumble * beat + 0.18 * machine + 0.28 * pipe
    return fade_edges(normalize(to_stereo(mono, 0.018), 0.55), 0.08)


def vent_airflow() -> np.ndarray:
    t = np.arange(N) / SR
    air = bp(RNG.standard_normal(N), 140.0, 1600.0)
    swirl = 0.55 + 0.45 * np.sin(2 * math.pi * 0.23 * t)
    blade = 0.08 * np.sin(2 * math.pi * 58.7 * t)
    mono = air * swirl * 0.55 + blade
    return fade_edges(normalize(to_stereo(mono, 0.009), 0.40), 0.06)


def electrical_metal() -> np.ndarray:
    t = np.arange(N) / SR
    hum = 0.55 * np.sin(2 * math.pi * 60.0 * t) + 0.28 * np.sin(2 * math.pi * 120.0 * t)
    hiss = 0.10 * bp(RNG.standard_normal(N), 800.0, 4500.0)
    ticks = np.zeros(N)
    for start_t in (1.15, 3.85, 7.40, 10.95, 13.55):
        i0 = int(start_t * SR)
        dur = int(0.09 * SR)
        tt = np.arange(dur) / SR
        ping = np.sin(2 * math.pi * (920 - 180 * tt) * tt) * np.exp(-tt * 38.0)
        ping += 0.35 * np.sin(2 * math.pi * 240 * tt) * np.exp(-tt * 22.0)
        j1 = min(N, i0 + dur)
        ticks[i0:j1] += ping[: j1 - i0] * 0.45
    resonance = bp(brown(N), 180.0, 520.0) * 0.18
    mono = 0.22 * hum + hiss + ticks + resonance
    return fade_edges(normalize(to_stereo(mono, 0.007), 0.32), 0.04)


def steam_event(start_f: int, peak_f: int, hold_f: int, end_f: int) -> np.ndarray:
    noise = bp(RNG.standard_normal(N), 900.0, 6200.0)
    noise += 0.22 * bp(RNG.standard_normal(N), 200.0, 800.0)
    env = np.zeros(N)
    s0 = int((start_f - 1) / FPS * SR)
    p0 = int((peak_f - 1) / FPS * SR)
    h0 = int((hold_f - 1) / FPS * SR)
    e0 = int((end_f - 1) / FPS * SR)
    p0 = min(max(p0, s0 + 1), e0)
    h0 = min(max(h0, p0), e0)
    if p0 > s0:
        env[s0:p0] = np.linspace(0.0, 1.0, p0 - s0)
    if h0 > p0:
        env[p0:h0] = 1.0
    if e0 > h0:
        t = np.linspace(0.0, 1.0, e0 - h0)
        env[h0:e0] = (1.0 - t) ** 1.6
    x = noise * env
    return fade_edges(normalize(to_stereo(x, 0.006), 0.48), 0.02)


def drips() -> np.ndarray:
    x = np.zeros(N)
    times = (0.42, 1.38, 2.55, 4.48, 6.10, 7.88, 9.40, 11.05, 12.30, 13.18, 14.42)
    for i, start_t in enumerate(times):
        i0 = int(start_t * SR)
        dur = int(0.22 * SR)
        tt = np.arange(dur) / SR
        drop = np.sin(2 * math.pi * (1750 - 900 * tt) * tt) * np.exp(-tt * 18.0)
        drop += 0.4 * np.sin(2 * math.pi * 420 * tt) * np.exp(-tt * 14.0)
        splash = bp(RNG.standard_normal(dur), 1200.0, 6000.0) * np.exp(-tt * 28.0)
        sig = 0.75 * drop + 0.18 * splash
        j1 = min(N, i0 + dur)
        x[i0:j1] += sig[: j1 - i0] * (0.7 if i % 3 else 1.0)
    return fade_edges(normalize(to_stereo(x, 0.004), 0.28), 0.02)


def camera_speed() -> np.ndarray:
    """m/s along CAM_P105_WALK Y keys used by the picture-lock mix."""
    t = np.arange(N) / SR
    frames = 1.0 + t * FPS
    y = np.empty(N)
    for i, f in enumerate(frames):
        if f <= 216:
            u = (f - 1.0) / 215.0
            y[i] = 1.4 + 12.6 * u
        else:
            u = (f - 216.0) / 144.0
            y[i] = 14.0 + 4.0 * u
    # Speed from dy; smooth so footfall gating is not clicky.
    dy = np.diff(y, prepend=y[0]) * SR
    speed = lp(np.abs(dy), 8.0)
    return y, speed


def footsteps_and_cloth() -> tuple[np.ndarray, np.ndarray]:
    _y, speed = camera_speed()
    # Stride ~0.72 m. Mute below creep threshold (stop / peek / door approach).
    stride = 0.72
    interval = np.clip(stride / np.maximum(speed, 0.12), 0.38, 1.35)
    foot = np.zeros(N)
    cloth = np.zeros(N)
    t = 0.42
    left = True
    while t < DURATION - 0.05:
        i0 = int(t * SR)
        spd = float(speed[min(i0, N - 1)])
        if spd < 0.28:
            t += 0.12
            continue
        dur = int(0.12 * SR)
        tt = np.arange(dur) / SR
        thump = np.sin(2 * math.pi * (78 - 22 * tt) * tt) * np.exp(-tt * 28.0)
        scrape = bp(RNG.standard_normal(dur), 400.0, 2800.0) * np.exp(-tt * 40.0)
        step = (0.72 * thump + 0.22 * scrape) * (0.35 + 0.65 * min(spd / 1.4, 1.0))
        j1 = min(N, i0 + dur)
        foot[i0:j1] += step[: j1 - i0] * (1.0 if left else 0.92)
        rust_n = int(0.18 * SR)
        rust = bp(RNG.standard_normal(rust_n), 200.0, 1800.0) * np.exp(-np.arange(rust_n) / SR * 14.0)
        j2 = min(N, i0 + rust_n)
        cloth[i0:j2] += rust[: j2 - i0] * (0.18 + 0.22 * min(spd / 1.4, 1.0))
        left = not left
        t += float(interval[min(i0, N - 1)])
    # Cloth also follows continuous speed (fabric while walking).
    cloth += bp(RNG.standard_normal(N), 180.0, 1400.0) * (np.clip(speed / 1.5, 0.0, 1.0) * 0.04)
    # Approach / peek: frames 216-360 are slower — extra duck of motion.
    frames = 1.0 + np.arange(N) / SR * FPS
    duck = np.where(frames >= 216.0, 0.55, 1.0)
    duck = lp(duck, 4.0)
    foot *= duck
    cloth *= 0.65 + 0.35 * duck
    foot_st = to_stereo(foot, 0.0008)
    # Slight L/R offset for alternating feet.
    foot_st[:, 0] *= 1.06
    foot_st[:, 1] *= 0.94
    return fade_edges(normalize(foot_st, 0.36), 0.03), fade_edges(normalize(to_stereo(cloth, 0.003), 0.22), 0.03)


def dark_ambient() -> np.ndarray:
    t = np.arange(N) / SR
    body = lp(brown(N), 90.0)
    body = hp(body, 18.0)
    hollow = bp(RNG.standard_normal(N), 80.0, 400.0)
    slow = 0.5 + 0.5 * np.sin(2 * math.pi * 0.045 * t)
    # Distant pressure, not a scare stinger.
    tone = 0.08 * np.sin(2 * math.pi * 36.5 * t) + 0.05 * np.sin(2 * math.pi * 54.0 * t + 0.7)
    mono = 0.70 * body * slow + 0.22 * hollow + tone
    # Corridor-end swell from mix script, applied again at mix time; keep stem full.
    return fade_edges(normalize(to_stereo(mono, 0.028), 0.50), 0.12)


def lofi_optional() -> np.ndarray:
    """Optional separate stem: slowed + dark reverb. Not used in default mux."""
    base = industrial_drone()[:, 0] + 0.35 * dark_ambient()[:, 0]
    # Cheap "slowed": resample by 0.92 then pad.
    idx = np.linspace(0, N - 1, int(N * 0.92))
    slow = np.interp(np.arange(N), np.linspace(0, N - 1, idx.size), np.interp(idx, np.arange(N), base))
    wet = lp(slow, 2400.0)
    d = int(0.09 * SR)
    echo = np.concatenate([np.zeros(d), wet[:-d]]) * 0.45
    mono = 0.7 * wet + echo
    return fade_edges(normalize(to_stereo(mono, 0.022), 0.40), 0.2)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write_wav(OUT / "drone_industrial.wav", industrial_drone())
    write_wav(OUT / "vent_airflow.wav", vent_airflow())
    write_wav(OUT / "electrical_metal.wav", electrical_metal())
    write_wav(OUT / "steam_hiss_a.wav", steam_event(36, 52, 78, 108))
    write_wav(OUT / "steam_hiss_b.wav", steam_event(150, 168, 198, 228))
    write_wav(OUT / "steam_hiss_c.wav", steam_event(240, 258, 300, 330))
    write_wav(OUT / "water_drip.wav", drips())
    foot, cloth = footsteps_and_cloth()
    write_wav(OUT / "footsteps.wav", foot)
    write_wav(OUT / "cloth_rustle.wav", cloth)
    write_wav(OUT / "dark_ambient.wav", dark_ambient())
    write_wav(OUT / "lofi_slowed_reverb_OPTIONAL.wav", lofi_optional())
    (OUT / "LICENSE.txt").write_text(
        "All stems in this directory are original procedural synthesis created for this\n"
        "project. No third-party sample libraries or copyrighted recordings were used.\n"
        "License: original work for this repository.\n"
    )
    print("stems ready", OUT)


if __name__ == "__main__":
    main()
