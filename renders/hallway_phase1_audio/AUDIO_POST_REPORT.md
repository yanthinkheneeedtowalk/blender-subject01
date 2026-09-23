# Phase 1 audio post — report

Picture lock only. Scene / camera / lights / materials / animation were not edited.

## Version note (STOP Event)

- This environment booted on `cursor/hallway-phase6-8333` with a 307 KB inspection `hallway.blend`.
- No repository object named `STOP Event` was found. No rollback was performed.
- The film just reviewed is PHASE_1_STABLE (`CAM_P105_WALK` 1–360).
- Audio work uses that picture lock. Phase 6 git history was not rewritten.
- Working `hallway.blend` is the Phase 1.1 look-restore file (10 885 045 B), unchanged by this pass.
- Boot blend backup: `renders/checkpoints/pre_audio_workspace_hallway.blend`

## Picture lock

- `renders/hallway_phase1_environment/phase1_stable_rollback_review.mp4`
- 768×432, 24 fps, 360 frames, 15.000 s
- Video stream copied (not re-rendered). MD5 of video frames matches the picture lock on both outputs.

## Outputs

- Environment only: `renders/hallway_phase1_audio/phase1_audio_environment_only.mp4`
- Dark ambient complete: `renders/hallway_phase1_audio/phase1_audio_dark_ambient.mp4`
- Mix WAVs: `mix_environment.wav`, `mix_dark_ambient.wav` (48 kHz stereo)
- Optional stem only (not muxed): `assets/hallway_phase1_audio/lofi_slowed_reverb_OPTIONAL.wav`

Both MP4s: H.264 copy + AAC 48 kHz stereo 192 kbps, 15.000 s, 360 video frames.

## Track list (original synthesis, see `assets/hallway_phase1_audio/LICENSE.txt`)

| Stem | Role |
| --- | --- |
| `drone_industrial.wav` | Continuous low industrial drone / pipe bed |
| `vent_airflow.wav` | Duct airflow, spatial at (−1.00, 12.05, 1.68) |
| `electrical_metal.wav` | Weak 60/120 Hz hum + metal ticks, spatial at (1.02, 10.70, 1.36) |
| `steam_hiss_a/b/c.wav` | Timed to existing steam sockets (frames 36–108, 150–228, 240–330) |
| `water_drip.wav` | Floor drips near y≈15.1 and y≈17.9 |
| `footsteps.wav` | Synced to CAM_P105_WALK speed; ducked after frame 216 (door approach) |
| `cloth_rustle.wav` | Follows walk speed; reduced when slowing |
| `dark_ambient.wav` | Isolation swell toward y=18 (complete mix only) |
| `lofi_slowed_reverb_OPTIONAL.wav` | Optional; not in either default MP4 |

## Mix notes

- Stereo pan from source X; distance gain + high-frequency loss
- Narrow-corridor feedforward taps (wetter toward the far end)
- Dark mix uses the same makeup as the environment bed, then adds the swell so the door-end is louder instead of being limiter-matched
- Dark/env RMS ratio ≈ 1.00 at the start, ≈ 1.20 in the last second
- Peak-only limiter ceiling 0.89; measured peak 0.76 (env) / 0.82 (dark); clip count 0; no silent seconds
- RMS second-to-second jump ≤ 0.051
- No stingers, drums, or melody

## QA

- A/V duration both 15.000 s
- Video frames 360, fps 24 (copied; frame MD5 identical to picture lock)
- Audio 48000 Hz stereo AAC; mux vs mix WAV correlation 0.9997
- `hallway.blend` not saved by this pass

## Unresolved

- Live Blender inspect was unavailable in this session (`blender` not on PATH). Footstep timing uses the frozen CAM_P105_WALK Y keys from `mix_phase1_audio.py` (1.4 → 14.0 @ f216 → 18.0 @ f360), not a new bake.
- CAM_P105_WALK has no separate peek animation; “stop / peek” is the post-216 slowdown only.
- No licensed recorded Foley library was present; all motion is synthesized (boot thump + scrape, not recorded shoes).
- Lo-Fi / Slowed + Reverb exists only as a separate stem and is not in either MP4.
