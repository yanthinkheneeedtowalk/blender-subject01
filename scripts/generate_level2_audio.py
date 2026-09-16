#!/usr/bin/env python3
"""Procedural Backrooms Level 2 (Pipe Dreams) audio bed.

No licensed / user-supplied Level 2 ambience was present in the workspace,
so this generator authors a seamless industrial utility loop plus timed
local stems that match the Phase 1 steam sockets and drip locations.

Outputs 15.0s / 24 fps aligned WAV files under assets/hallway_phase1_environment/.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "hallway_phase1_environment"
SR = 44100
DURATION = 15.0
N = int(DURATION * SR)
FPS = 24


def frame_to_sample(frame: int) -> int:
    return int((frame - 1) / FPS * SR)


def write_wav(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    import wave
    import struct

    path.parent.mkdir(parents=True, exist_ok=True)
    if samples.ndim == 1:
        stereo = np.stack([samples, samples], axis=1)
    else:
        stereo = samples
    stereo = np.clip(stereo, -1.0, 1.0)
    with wave.open(str(path), "w") as w:
        w.setnchannels(2 if stereo.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = (stereo * 32000.0).astype(np.int16)
        w.writeframes(frames.tobytes() if False else struct.pack("<" + "h" * frames.size, *frames.reshape(-1).tolist()))


def write_wav_fast(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(samples, -1.0, 1.0)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    pcm = (data * 32000.0).astype(np.int16)
    with wave.open(str(path), "w") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    print("wrote", path, "dur", data.shape[0] / sr)


def one_pole_lowpass(x: np.ndarray, cutoff: float, sr: int = SR) -> np.ndarray:
    taps = max(5, int(sr / max(cutoff, 1.0)))
    if taps % 2 == 0:
        taps += 1
    kernel = np.hanning(taps)
    kernel /= kernel.sum()
    return np.convolve(x, kernel, mode="same")


def one_pole_highpass(x: np.ndarray, cutoff: float, sr: int = SR) -> np.ndarray:
    return x - one_pole_lowpass(x, cutoff, sr)


def bandpass(x: np.ndarray, lo: float, hi: float, sr: int = SR) -> np.ndarray:
    return one_pole_lowpass(one_pole_highpass(x, lo, sr), hi, sr)


def envelope(n: int, attack: int, release: int) -> np.ndarray:
    env = np.ones(n, dtype=np.float64)
    if attack > 0:
        env[:attack] = np.linspace(0.0, 1.0, attack)
    if release > 0:
        env[-release:] = np.linspace(1.0, 0.0, release)
    return env


def event_envelope(n: int, start: int, peak: int, hold: int, end: int) -> np.ndarray:
    env = np.zeros(n, dtype=np.float64)
    start = max(0, start)
    end = min(n, end)
    peak = min(max(peak, start + 1), end)
    hold = min(max(hold, peak), end)
    if peak > start:
        env[start:peak] = np.linspace(0.0, 1.0, peak - start)
    if hold > peak:
        env[peak:hold] = 1.0
    if end > hold:
        t = np.linspace(0.0, 1.0, end - hold)
        env[hold:end] = (1.0 - t) ** 1.6
    return env


def brown_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    x = np.cumsum(rng.standard_normal(n))
    x -= x.mean()
    peak = np.max(np.abs(x)) or 1.0
    return x / peak


def make_ambience(rng: np.random.Generator) -> np.ndarray:
    t = np.arange(N) / SR
    rumble = brown_noise(N, rng)
    rumble = one_pole_lowpass(rumble, 90.0)
    rumble = one_pole_highpass(rumble, 22.0)
    air = bandpass(rng.standard_normal(N), 180.0, 1600.0)
    hiss = bandpass(rng.standard_normal(N), 2500.0, 7000.0)
    elec = (
        0.55 * np.sin(2 * math.pi * 60.0 * t)
        + 0.28 * np.sin(2 * math.pi * 120.0 * t)
        + 0.12 * np.sin(2 * math.pi * 180.0 * t)
    )
    slow = 0.55 + 0.45 * np.sin(2 * math.pi * 0.07 * t)
    machine = np.sin(2 * math.pi * 27.5 * t) * (0.55 + 0.45 * np.sin(2 * math.pi * 0.11 * t))
    machine += 0.35 * np.sin(2 * math.pi * 41.0 * t + 0.4)
    pipe_res = bandpass(rumble + 0.25 * rng.standard_normal(N), 70.0, 240.0)
    mono = (
        0.22 * rumble * slow
        + 0.055 * air
        + 0.012 * hiss
        + 0.010 * elec
        + 0.045 * machine
        + 0.08 * pipe_res
    )
    # Decorrelated stereo: short delay + extra air on one side.
    delay = int(0.011 * SR)
    left = mono.copy()
    right = np.concatenate([np.zeros(delay), mono[:-delay]])
    right += 0.012 * bandpass(rng.standard_normal(N), 400.0, 2200.0)
    left += 0.010 * bandpass(rng.standard_normal(N), 350.0, 1800.0)
    stereo = np.stack([left, right], axis=1)
    # Crossfade 0.85s to hide the loop cut.
    fade = int(0.85 * SR)
    head = stereo[:fade].copy()
    tail = stereo[-fade:].copy()
    w = np.linspace(0.0, 1.0, fade)[:, None]
    stereo[-fade:] = tail * (1.0 - w) + head * w
    stereo[:fade] = head * (1.0 - w) + tail * w
    peak = np.max(np.abs(stereo)) or 1.0
    return stereo / peak * 0.38


def make_loop_mono(kind: str, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(N) / SR
    if kind == "pipe_rumble":
        x = one_pole_lowpass(brown_noise(N, rng), 70.0)
        x += 0.35 * np.sin(2 * math.pi * 38.0 * t)
        x += 0.18 * np.sin(2 * math.pi * 19.5 * t)
        x = one_pole_highpass(x, 16.0)
        gain = 0.42
    elif kind == "vent_hum":
        x = bandpass(rng.standard_normal(N), 90.0, 900.0)
        x += 0.08 * np.sin(2 * math.pi * 58.7 * t)
        x *= 0.55 + 0.45 * np.sin(2 * math.pi * 0.23 * t)
        gain = 0.28
    elif kind == "electrical":
        x = (
            0.7 * np.sin(2 * math.pi * 120.0 * t)
            + 0.35 * np.sin(2 * math.pi * 60.0 * t)
            + 0.12 * bandpass(rng.standard_normal(N), 800.0, 4000.0)
        )
        gain = 0.18
    elif kind == "metal_tick":
        x = np.zeros(N)
        for k, start_t in enumerate((1.15, 3.85, 7.40, 10.95, 13.55)):
            i0 = int(start_t * SR)
            dur = int(0.09 * SR)
            tt = np.arange(dur) / SR
            ping = np.sin(2 * math.pi * (920 - 180 * tt) * tt) * np.exp(-tt * 38.0)
            ping += 0.35 * np.sin(2 * math.pi * 240 * tt) * np.exp(-tt * 22.0)
            ping += 0.08 * rng.standard_normal(dur) * np.exp(-tt * 50.0)
            j1 = min(N, i0 + dur)
            x[i0:j1] += ping[: j1 - i0] * (0.55 if k % 2 == 0 else 0.38)
        gain = 0.22
    elif kind == "drip":
        x = np.zeros(N)
        times = [0.42, 1.38, 2.55, 3.20, 4.48, 5.72, 6.10, 7.88, 8.95, 9.40, 11.05, 12.30, 13.18, 14.42]
        for i, start_t in enumerate(times):
            i0 = int(start_t * SR)
            dur = int(0.22 * SR)
            tt = np.arange(dur) / SR
            drop = np.sin(2 * math.pi * (1750 - 900 * tt) * tt) * np.exp(-tt * 18.0)
            drop += 0.4 * np.sin(2 * math.pi * 420 * tt) * np.exp(-tt * 14.0)
            splash = bandpass(rng.standard_normal(dur), 1200.0, 6000.0) * np.exp(-tt * 28.0)
            sig = 0.75 * drop + 0.18 * splash
            j1 = min(N, i0 + dur)
            x[i0:j1] += sig[: j1 - i0] * (0.7 if i % 3 else 1.0)
        gain = 0.26
    else:
        raise ValueError(kind)
    fade = int(0.12 * SR)
    x[:fade] *= np.linspace(0.0, 1.0, fade)
    x[-fade:] *= np.linspace(1.0, 0.0, fade)
    peak = np.max(np.abs(x)) or 1.0
    return x / peak * gain


def make_steam_hiss(start_f: int, peak_f: int, hold_f: int, end_f: int, rng: np.random.Generator) -> np.ndarray:
    noise = bandpass(rng.standard_normal(N), 900.0, 6500.0)
    noise += 0.25 * bandpass(rng.standard_normal(N), 250.0, 900.0)
    env = event_envelope(
        N,
        frame_to_sample(start_f),
        frame_to_sample(peak_f),
        frame_to_sample(hold_f),
        frame_to_sample(end_f),
    )
    x = noise * env
    peak = np.max(np.abs(x)) or 1.0
    return x / peak * 0.48


def make_rare(rng: np.random.Generator) -> np.ndarray:
    x = np.zeros(N)
    # Distant metallic impact ~4.8s, structural groan ~11.4s. Quiet, not a jumpscare.
    i0 = int(4.80 * SR)
    dur = int(1.6 * SR)
    tt = np.arange(dur) / SR
    impact = np.sin(2 * math.pi * (92 - 18 * tt) * tt) * np.exp(-tt * 2.4)
    impact += 0.5 * np.sin(2 * math.pi * 46 * tt) * np.exp(-tt * 1.8)
    impact += 0.12 * bandpass(rng.standard_normal(dur), 80.0, 600.0) * np.exp(-tt * 3.0)
    x[i0 : i0 + dur] += impact * 0.22

    i1 = int(11.35 * SR)
    dur2 = int(2.4 * SR)
    tt = np.arange(dur2) / SR
    groan = np.sin(2 * math.pi * (48 - 9 * tt) * tt) * (1.0 - tt / (dur2 / SR))
    groan += 0.4 * np.sin(2 * math.pi * 29 * tt)
    groan += 0.16 * brown_noise(dur2, rng)[:dur2]
    groan *= np.exp(-tt * 0.55)
    x[i1 : min(N, i1 + dur2)] += groan[: min(dur2, N - i1)] * 0.16
    peak = np.max(np.abs(x)) or 1.0
    return x / peak * 0.20


def main() -> None:
    rng = np.random.default_rng(2102)
    OUT.mkdir(parents=True, exist_ok=True)
    write_wav_fast(OUT / "amb_level2_loop.wav", make_ambience(rng))
    write_wav_fast(OUT / "local_pipe_rumble.wav", make_loop_mono("pipe_rumble", rng))
    write_wav_fast(OUT / "local_vent_hum.wav", make_loop_mono("vent_hum", rng))
    write_wav_fast(OUT / "local_electrical_hum.wav", make_loop_mono("electrical", rng))
    write_wav_fast(OUT / "local_water_drip.wav", make_loop_mono("drip", rng))
    write_wav_fast(OUT / "local_metal_tick.wav", make_loop_mono("metal_tick", rng))
    write_wav_fast(OUT / "local_steam_hiss_a.wav", make_steam_hiss(36, 52, 78, 108, rng))
    write_wav_fast(OUT / "local_steam_hiss_b.wav", make_steam_hiss(150, 168, 198, 228, rng))
    write_wav_fast(OUT / "local_steam_hiss_c.wav", make_steam_hiss(240, 258, 300, 330, rng))
    write_wav_fast(OUT / "rare_distant_structure.wav", make_rare(rng))
    print("audio pack ready", OUT)


if __name__ == "__main__":
    main()
