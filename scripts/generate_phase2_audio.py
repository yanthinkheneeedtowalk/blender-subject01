#!/usr/bin/env python3
"""Phase 2 sector audio stems.

30s / 24 fps aligned loops for the review camera route.  Reuses the Phase 1
synthesis vocabulary (brown noise, bandpass, event envelopes) so the Level
still sounds like one industrial plant, with distinct sector identities.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_level2_audio as g1

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "hallway_phase2_spatial"
SR = 44100
FPS = 24
DURATION = 720 / FPS
N = int(DURATION * SR)


def write(path: Path, samples: np.ndarray) -> None:
    g1.write_wav_fast(path, samples, SR)


def lp(x, cutoff):
    return g1.one_pole_lowpass(x, cutoff, SR)


def hp(x, cutoff):
    return g1.one_pole_highpass(x, cutoff, SR)


def bp(x, lo, hi):
    return g1.bandpass(x, lo, hi, SR)


def loop_fade(stereo: np.ndarray, seconds: float = 0.7) -> np.ndarray:
    fade = int(seconds * SR)
    head = stereo[:fade].copy()
    tail = stereo[-fade:].copy()
    w = np.linspace(0.0, 1.0, fade)[:, None]
    stereo[-fade:] = tail * (1.0 - w) + head * w
    stereo[:fade] = head * (1.0 - w) + tail * w
    return stereo


def to_stereo(mono: np.ndarray, rng: np.random.Generator, delay_s: float = 0.012) -> np.ndarray:
    delay = int(delay_s * SR)
    left = mono.copy()
    right = np.concatenate([np.zeros(delay), mono[:-delay]])
    right += 0.008 * bp(rng.standard_normal(N), 300.0, 1800.0)
    return np.stack([left, right], axis=1)


def pipe_dense(rng: np.random.Generator) -> np.ndarray:
    t = np.arange(N) / SR
    rumble = lp(g1.brown_noise(N, rng), 55.0)
    rumble = hp(rumble, 14.0)
    pulse = 0.45 * np.sin(2 * math.pi * 22.0 * t) + 0.22 * np.sin(2 * math.pi * 11.0 * t)
    metal = bp(rng.standard_normal(N), 80.0, 280.0)
    mono = 0.55 * rumble + 0.18 * pulse + 0.16 * metal
    peak = np.max(np.abs(mono)) or 1.0
    return loop_fade(to_stereo(mono / peak * 0.42, rng, 0.018))


def hot_steam(rng: np.random.Generator) -> np.ndarray:
    hiss = bp(rng.standard_normal(N), 700.0, 5200.0)
    pressure = bp(rng.standard_normal(N), 120.0, 700.0)
    t = np.arange(N) / SR
    swell = 0.65 + 0.35 * np.sin(2 * math.pi * 0.09 * t)
    # Occasional pressure release, not a jumpscare.
    env = np.ones(N) * 0.35
    for start_t, dur in ((9.6, 2.4), (11.8, 2.8), (14.2, 2.2)):
        i0 = int(start_t * SR)
        n = int(dur * SR)
        env[i0 : i0 + n] += g1.event_envelope(n, 0, int(0.35 * SR), int(0.7 * n), n)
    mono = (0.55 * hiss + 0.35 * pressure) * swell * np.clip(env, 0.0, 1.4)
    peak = np.max(np.abs(mono)) or 1.0
    return loop_fade(to_stereo(mono / peak * 0.38, rng, 0.009))


def thermal_tick(rng: np.random.Generator) -> np.ndarray:
    x = np.zeros(N)
    times = (2.4, 5.1, 8.05, 10.7, 12.9, 15.8, 19.4, 23.1, 26.6)
    for k, start_t in enumerate(times):
        i0 = int(start_t * SR)
        dur = int(0.11 * SR)
        tt = np.arange(dur) / SR
        ping = np.sin(2 * math.pi * (640 - 90 * tt) * tt) * np.exp(-tt * 28.0)
        ping += 0.25 * np.sin(2 * math.pi * 180 * tt) * np.exp(-tt * 16.0)
        ping += 0.06 * rng.standard_normal(dur) * np.exp(-tt * 40.0)
        j1 = min(N, i0 + dur)
        x[i0:j1] += ping[: j1 - i0] * (0.62 if k % 2 == 0 else 0.40)
    peak = np.max(np.abs(x)) or 1.0
    return to_stereo(x / peak * 0.22, rng, 0.006)


def vent_fan(rng: np.random.Generator) -> np.ndarray:
    t = np.arange(N) / SR
    air = bp(rng.standard_normal(N), 180.0, 1400.0)
    blade = np.sin(2 * math.pi * 29.5 * t) * (0.55 + 0.45 * np.sin(2 * math.pi * 0.17 * t))
    blade += 0.35 * np.sin(2 * math.pi * 59.0 * t)
    motor = 0.12 * np.sin(2 * math.pi * 58.7 * t)
    mono = 0.42 * air + 0.28 * blade + motor
    peak = np.max(np.abs(mono)) or 1.0
    return loop_fade(to_stereo(mono / peak * 0.34, rng, 0.015))


def maint_hum(rng: np.random.Generator) -> np.ndarray:
    t = np.arange(N) / SR
    hum = 0.7 * np.sin(2 * math.pi * 120.0 * t) + 0.28 * np.sin(2 * math.pi * 60.0 * t)
    hiss = 0.08 * bp(rng.standard_normal(N), 900.0, 3500.0)
    room = 0.12 * lp(g1.brown_noise(N, rng), 90.0)
    mono = hum + hiss + room
    peak = np.max(np.abs(mono)) or 1.0
    return loop_fade(to_stereo(mono / peak * 0.16, rng, 0.022))


def shaft_reverb(rng: np.random.Generator) -> np.ndarray:
    t = np.arange(N) / SR
    body = lp(g1.brown_noise(N, rng), 140.0)
    body = hp(body, 28.0)
    drip_like = np.zeros(N)
    for start_t in (3.2, 7.8, 14.6, 21.4, 27.0):
        i0 = int(start_t * SR)
        dur = int(0.55 * SR)
        tt = np.arange(dur) / SR
        ping = np.sin(2 * math.pi * (220 - 40 * tt) * tt) * np.exp(-tt * 3.2)
        j1 = min(N, i0 + dur)
        drip_like[i0:j1] += ping[: j1 - i0] * 0.18
    # Cheap enclosed feeling: delayed copy.
    delay = int(0.085 * SR)
    echo = np.concatenate([np.zeros(delay), body[:-delay]]) * 0.45
    mono = 0.70 * body + 0.22 * echo + drip_like + 0.08 * np.sin(2 * math.pi * 38.0 * t)
    peak = np.max(np.abs(mono)) or 1.0
    return loop_fade(to_stereo(mono / peak * 0.30, rng, 0.028), 0.9)


def steam_event(start_f, peak_f, hold_f, end_f, rng) -> np.ndarray:
    noise = bp(rng.standard_normal(N), 800.0, 6200.0)
    noise += 0.22 * bp(rng.standard_normal(N), 180.0, 800.0)
    env = g1.event_envelope(
        N,
        int((start_f - 1) / FPS * SR),
        int((peak_f - 1) / FPS * SR),
        int((hold_f - 1) / FPS * SR),
        int((end_f - 1) / FPS * SR),
    )
    x = noise * env
    peak = np.max(np.abs(x)) or 1.0
    return to_stereo(x / peak * 0.44, rng, 0.007)


def extend_phase1_loop(path: Path) -> np.ndarray:
    import wave

    with wave.open(str(path), "r") as w:
        nch = w.getnchannels()
        n = w.getnframes()
        raw = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    stereo = raw.reshape(-1, nch) if nch == 2 else np.stack([raw, raw], axis=1)
    reps = int(math.ceil(N / stereo.shape[0])) + 1
    tiled = np.tile(stereo, (reps, 1))[:N]
    return loop_fade(tiled, 0.4)


def main() -> None:
    rng = np.random.default_rng(2202)
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "p2_pipe_dense_rumble.wav", pipe_dense(rng))
    write(OUT / "p2_hot_steam.wav", hot_steam(rng))
    write(OUT / "p2_thermal_tick.wav", thermal_tick(rng))
    write(OUT / "p2_vent_fan.wav", vent_fan(rng))
    write(OUT / "p2_maint_hum.wav", maint_hum(rng))
    write(OUT / "p2_shaft_reverb.wav", shaft_reverb(rng))
    write(OUT / "p2_steam_hub.wav", steam_event(110, 135, 175, 230, rng))
    write(OUT / "p2_steam_hot_a.wav", steam_event(230, 260, 310, 390, rng))
    write(OUT / "p2_steam_hot_b.wav", steam_event(250, 285, 340, 420, rng))
    p1_amb = ROOT / "assets" / "hallway_phase1_environment" / "amb_level2_loop.wav"
    if p1_amb.exists():
        write(OUT / "p2_amb_level2.wav", extend_phase1_loop(p1_amb) * 0.92)
        rare = ROOT / "assets" / "hallway_phase1_environment" / "rare_distant_structure.wav"
        if rare.exists():
            write(OUT / "p2_rare_structure.wav", extend_phase1_loop(rare) * 0.70)
    print("phase2 audio pack ready", OUT)


if __name__ == "__main__":
    main()
