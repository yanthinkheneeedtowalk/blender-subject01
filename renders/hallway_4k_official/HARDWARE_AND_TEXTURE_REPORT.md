# Part 1 official 4K — hardware, textures, and render plan

Original `hallway.blend` was not saved. Working copy: `renders/hallway_4k_official/hallway_4k_work.blend`.
Backup: `renders/checkpoints/part1_pre_4k_official_hallway.blend` (md5 `e2a4c51380aed23fbb95d631d02e9252`).
`part2_basement.blend` was not opened or saved.

## Picture lock (unchanged)

- No object/collection named STOP Event
- Camera `CAM_P105_WALK`, 32 mm, keys y=1.4 / 14.0 / 18.0 at frames 1 / 216 / 360
- 24 fps, frames 1–360 (15.000 s)
- Last picture frame 348 (door about half open), hard black 349–360
- World strength 0.04, AgX, exposure 0
- Original engine: EEVEE, 768×432, TAA 12, motion blur off

## Audio (kept)

- `renders/hallway_phase1_audio/mix_dark_ambient.wav` — 48 kHz stereo, 15.000 s
- Contains industrial bed, footsteps, steam, drips, dark ambient
- Muxed after the frame sequence; not re-authored

## Hardware (this environment)

- 4-core Intel Xeon, 16 GB RAM, **no GPU**
- Cycles devices: CPU only (CUDA/OptiX/HIP libraries missing)
- Measured:
  - Cycles CPU 960×540 / 32 spp: 46.6 s → **4K 128 spp ≈ 50 min/frame ≈ 288 hours for 348 frames**
  - Cycles also renders **darker than the EEVEE picture lock** (lights were authored for EEVEE). Matching Cycles would require relighting, which this pass must not do.
  - EEVEE 4K / 24 spp / volume tile 2: 554 s/frame
  - EEVEE 4K / 12 spp / volume tile 8 (density matched to 768 tile 2) + motion blur: **222 s/frame ≈ 21.5 hours**

## Alternative used (not a 768 upscale)

Native **3840×2160 EEVEE**, same GI/volume recipe as Phase 1, motion blur on.

- Test stills: 12 TAA samples (picture-lock sample count)
- Full sequence: **8 TAA samples** (native 4K; ~148 s/frame, ~14 h) because 12 spp cannot finish on this CPU
- Volume tile 8 at 4K ≈ tile 2 at 768
- Frames 1–348 PNG, 349–360 generated black
- 1080p is a lanczos downscale of the same native 4K frames

## Texture / material honesty

File images only:

| Name | Size |
| --- | --- |
| Phase 6 marks | 512×192 |
| Phase 9 stencil atlas | 1024×1024 |

Walls, floor, pipes, and most dirt are **procedural shaders**, not photographic 4K maps. Output 4K sharpens geometry, stencil edges, and shader noise; it cannot invent missing photo-texture detail. Marks/stencils will still show their native texel density.

## Test frames (3840×2160, 12 spp, motion blur)

- `tests/01_corridor_f0120.png` — typical corridor
- `tests/02_dark_f0312.png` — dark door approach
- `tests/03_fast_move_f0060.png` — faster walk segment

No fireflies, no blown highlights, exposure matches the industrial lock.
