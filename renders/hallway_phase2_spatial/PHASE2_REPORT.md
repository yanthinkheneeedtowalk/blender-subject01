# Phase 2 Report — Level 2 Spatial Expansion

## Completion Gate

| Gate | Result |
| --- | --- |
| PHASE 1 PROTECTED | PASS |
| SPATIAL EXPANSION | PASS |
| PREVIEW GATE | PASS |
| TECHNICAL QA | PASS |
| ART DIRECTION | PASS |
| FULL ANIMATION | PASS |
| AUDIO | PASS |

**PASS — Ready for Phase 3**

Phase 3 was not started.

## Spatial Areas Added

West of Zone A, a T-junction at y≈6.2 opens into a pipe-dense hub. From the hub:

- **Normal Utility Corridor** — frozen Phase 1 24 m corridor. Unmodified.
- **Pipe-Dense Hub** — crossing ceiling/wall pipes, brackets, riser + valve that forces a sidestep, service platform + two steps.
- **Hot Steam Sector** — north corridor with 0.32 m floor drop and three steps, denser hot pipes, extra steam sockets, wet patches.
- **Ventilation Sector** — south corridor with ducts, grille, fan, maintenance panel, slightly cooler local practicals.
- **Dead End (L)** — west of ventilation, sealed industrial gate.
- **Maintenance Room** — west of hub. Bench, shelf, open panel, cart, wrench, broken valve wheel. Sparse abandonment.
- **Maintenance Shaft** — vertical well above hub NW with ladder and grate. Camera looks, does not fly through.
- **East Dead End** — locked maintenance door stub off the original corridor.

## Geometry Changes

Additive `PHASE2_*` collections only. Openings are boolean-cut into `WALL.West.Shell` / `WALL.East.Shell`. Original corridor modules, weathering, and door sequence are not rebuilt.

Source of truth: `scripts/build_hallway_phase2_spatial.py` (`--setup` / `--stills` / `--render`). Checkpoint: `renders/checkpoints/phase2_pre_spatial_expansion.blend`.

## Audio Changes

Phase 1 bed extended, not replaced. New 30 s stems in `assets/hallway_phase2_spatial/`. `mix_phase2_audio.py` distance-attenuates along `CAM_P2_REVIEW`.

Mixdown RMS by region (no silent windows, peak 0.87):

- corridor start 0.18
- hub / pipe-dense 0.18
- hot 0.20
- vent 0.19
- dead end 0.12 (quieter)
- maintenance 0.22 (local electrical)
- corridor end 0.17

## Camera Route

`CAM_P2_REVIEW`, 32 mm, 720 frames / 30 s / 24 fps / 768×432. `CAM_P105_WALK` keys unchanged (y=1.4 / 14.0 / 18.0).

Corridor → west T → hub / shaft → hot drop → vent L / sealed gate → maintenance → return north down original corridor.

## Performance Impact

| | Objects | Materials | Lights |
| --- | ---: | ---: | ---: |
| Phase 1 checkpoint | 663 | 42 | 22 |
| Phase 2 | 819 | 45 | 32 |
| Delta | +156 | +3 | +10 |

Full animation: 720 frames, 26343 s wall (~36.6 s/frame including Blender animation op), EEVEE 12 TAA samples.

## Preview Gate Result

Stills at frames 1, 180, 280, 360, 400, 630, 720: **PASS**.

Warm dirty-yellow, deep shadows, no grey-bright begin/end, openings raycast-confirmed, steam not oval/billboard.

## Regression Test

After `--setup`:

- `CAM_P105_WALK` keys unchanged
- world strength 0.04
- world volume density 0
- no `LIGHT_P1_FILL*`
- Phase 1 steam sockets present
- ending MP4 still shows original corridor + door sequence

## Final Animation QA

File: `renders/hallway_phase2_spatial/phase2_spatial_expansion_review.mp4` (h264 + aac, 30.0 s, 768×432, 24 fps).

Watched beginning / 25% / 50% / 75% / ending plus hot, vent, junction, dead-end, maintenance:

- No camera wall clip, no geometry pop, no z-fighting
- No grey-bright corridor regression
- Steam: localized haze, no oval blob, no camera fog, no whiteout
- Door sequence intact at the end
- Junction + hub + ladder + side room read as a plant, not a single path
- No entities, no Clockwork anomalies
- Audio continuous; dead-end quieter than hot/maintenance

## Known Issues

- New rooms use simple blockout furniture (same language as Phase 1 utility meshes).
- Hot-sector steam is a lit haze, not a large opaque jet.
- Ventilation L-turn is darker than the hub (blocked sightline + cooler local practicals).
- A flange can sit close to a hot-sector ceiling pipe.
