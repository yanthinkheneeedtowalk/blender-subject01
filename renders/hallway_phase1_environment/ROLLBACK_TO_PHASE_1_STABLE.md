# Rollback to PHASE_1_STABLE

Phase 2 Spatial Expansion was rejected by human QA and is not adopted.

## Archive (do not use as construction base)

- Git tag: `phase2_failed_archive`
- Git branch: `cursor/phase2-failed-archive-8333`
- Original PR branch (history preserved): `cursor/hallway-phase2-spatial-8333`
- Checkpoint blend on that branch: `renders/checkpoints/phase2_failed_archive.blend`
- Archive commit: `1156bd3d297fc31db0791f06f4a27bb769abb35d`

## Restored working version

- ROLLBACK SOURCE = `e3409ae66c9c67017ef619e1f99fc34214d020c6`
- Message: Add Phase 1 look-restore review animation with audio.
- Branch: `cursor/rollback-phase1-stable-8333`
- ACTIVE BLEND = `hallway.blend` (byte-identical to that commit; not resaved)

## Verification (no reconstruction)

Inspected restored blend:

- objects 663 / materials 42 / lights 22
- Phase 2 objects, collections, materials, `CAM_P2_REVIEW`, `PHASE2_SPATIAL` = none
- Phase 1 steam sockets present
- `CAM_P105_WALK` keys y=1.4 / 14.0 / 18.0
- world strength 0.04, world volume 0, no fill lights

Three verification frames (CAM_P105_WALK, no full animation):

- beginning f0001
- middle f0180
- ending f0360
