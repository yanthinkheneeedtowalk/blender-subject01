# Part 2 basement — static scene report

Part 1 `hallway.blend` was not saved. Working copy: `part2_basement.blend`.
Backup: `renders/checkpoints/part1_pre_part2_hallway.blend`.

## STOP Event

No object or collection named STOP Event was found in the live PHASE_1_STABLE inspect.
`CAM_P105_WALK` keys remain y=1.4 / 14.0 / 18.0. World strength 0.04. Objects 663 before Part 2 build.

## Room size (interior)

- Length (Y): 5.50 m  (24.22 → 29.72)
- Width (X): 4.50 m  (-2.25 → 2.25)
- Height (Z): 2.50 m
- Single exit through existing `FINAL_DOOR` / punched `WALL.End`

## Connection

Existing end door at y≈23.8 is the only original doorway. Part 2 opens a door-sized hole in `WALL.End` on the copy and hides `FINAL_DOOR_RECESS` so the basement is visible through that door. Corridor walls, floor, camera, door Action, and timeline are not rewritten.

`FINAL_DOOR_HINGEAction` is left intact; the connection still uses frame 348 (half-open) without inserting keys.

## Collections

- `P2_ARCH`
- `P2_CABLES`
- `P2_CAMERAS`
- `P2_CLUTTER`
- `P2_CONNECTION`
- `P2_DESK_PROPS`
- `P2_FRAME_CLOTH`
- `P2_FURNITURE`
- `P2_LIGHTS`

## Frame / cloth

- `P2_FRAME_ROOT`
- `P2_FRAME_OUTER`
- `P2_FRAME_PHOTO`
- `P2_FRAME_GLASS`
- `P2_FRAME_DUST`
- `P2_CLOTH`

## Desk props (independent meshes)

- `P2_PAPER_0`
- `P2_PAPER_1`
- `P2_METAL_BRACKET`
- `P2_BOLT_A`
- `P2_BOLT_B`
- `P2_TOOL_PLIERS_BODY`
- `P2_TOOL_SCREWDRIVER`
- `P2_RUBBER_GASKET`

## Cables reserved for later deformation

- `P2_CABLE_RIG_01`
- `P2_CABLE_RIG_02`
- `P2_CABLE_RIG_03`
- `P2_CABLE_RIG_04`
- `P2_CABLE_RIG_05`
- `P2_CABLE_RIG_06`

All cables are independent Bezier curves with bevel. Fill cables: P2_CABLE_RIG_01, P2_CABLE_RIG_02, P2_CABLE_RIG_03, P2_CABLE_RIG_04, P2_CABLE_RIG_05, P2_CABLE_RIG_06, P2_CABLE_FILL_00, P2_CABLE_FILL_01, P2_CABLE_FILL_02, P2_CABLE_FILL_03, P2_CABLE_FILL_04, P2_CABLE_FILL_05, P2_CABLE_FILL_06, P2_CABLE_FILL_07.

## External assets

None. Materials and the blurred photo are original procedural / generated content.

## Space check (static only)

- Sit camera `CAM_P2_SIT` at chair, eye z=1.18 m, 32 mm, sees frame, cloth, desk, and room beyond.
- Wide camera `CAM_P2_WIDE` from the southwest corner.
- Clearance chair → east clutter wall ≈ 1.1 m for stand / stagger / hit / kneel.
- Desk front keeps an open hand zone between frame and cloth.

## Known issues / not done this round

- Cardboard is unflapped boxes; wear is shader noise, not unique painted damage maps.
- Cloth is a wrinkled grid, not a simulated rag. Dust on the glass is a thin alpha slab.
- Photo is a blurred unidentifiable generated image (no faces, no skull).
- `WALL.End` hole and hidden recess exist only on the Part 2 copy.
- No character, cloth sim, rigid body, cable motion, black liquid, or story animation.

## Stills

- `/workspace/renders/part2_basement/stills/01_wide.png`
- `/workspace/renders/part2_basement/stills/02_sit_fps.png`
- `/workspace/renders/part2_basement/stills/03_desk_close.png`
- `/workspace/renders/part2_basement/stills/04_cables_clutter.png`
- `/workspace/renders/part2_basement/stills/05_connection.png`
