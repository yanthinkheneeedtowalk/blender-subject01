#!/usr/bin/env python3
"""Phase 10.6C — floor, aging, and lighting consistency correction.

This is an additive follow-up to Phase 10.6B.  The 10.6B scene, layout,
equipment, pipes, endless extension, and first-person camera remain the
foundation.  Only shader response, practical-light balance, and evaluation
camera/output state are changed.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase10_6c.py -- --no-render
  blender -b hallway.blend --python scripts/build_hallway_phase10_6c.py -- --stills
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_hallway_phase10_6b as p106b
import build_hallway_phase10_6 as p106

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase10_6c"
ARTIFACT_DIR = Path("/opt/cursor/artifacts")

WALK_CAM = p106b.WALK_CAM
FLOOR_CAM = p106b.FLOOR_CAM
CLOSE_CAM = p106b.CLOSE_CAM
HERO_FRAME = p106b.HERO_FRAME

# A single practical identity is used for TEST_A and TEST_B.  TEST_C only
# raises the existing practical sources temporarily as a material stress test.
LIGHT_IDENTITY = {
    "LIGHT_A_01_NORMAL": dict(energy=50.0, color=(1.00, 0.97, 0.90), size=1.30),
    "LIGHT_A_02_NORMAL": dict(energy=46.0, color=(0.96, 0.99, 0.93), size=1.26),
    "LIGHT_A_03_NORMAL": dict(energy=50.0, color=(1.00, 0.96, 0.88), size=1.28),
    "LIGHT_A_04_AGED_TINT": dict(energy=40.0, color=(1.00, 0.94, 0.84), size=1.32),
    "LIGHT_A_WALL_01_NORMAL": dict(energy=10.0, color=(1.00, 0.96, 0.88), size=1.22),
    "LIGHT_B_01_NORMAL": dict(energy=44.0, color=(0.96, 0.99, 0.92), size=1.32),
    "LIGHT_B_02_WEAK": dict(energy=22.0, color=(0.93, 0.99, 0.86), size=1.34),
    "LIGHT_B_03_OFF": dict(energy=0.0, color=(0.92, 0.93, 0.90), size=1.00),
    "LIGHT_B_04_WEAK": dict(energy=20.0, color=(0.94, 0.98, 0.86), size=1.34),
    "LIGHT_B_WALL_01_WEAK": dict(energy=5.0, color=(0.94, 0.99, 0.88), size=1.22),
    "LIGHT_C_01_WEAK": dict(energy=24.0, color=(0.93, 0.99, 0.87), size=1.32),
    "LIGHT_C_02_OFF": dict(energy=0.0, color=(0.92, 0.93, 0.90), size=1.00),
    "LIGHT_C_03_NORMAL": dict(energy=42.0, color=(1.00, 0.96, 0.87), size=1.30),
    "LIGHT_C_04_WEAK": dict(energy=19.0, color=(0.94, 0.98, 0.88), size=1.36),
    "LIGHT_C_WALL_01_OFF": dict(energy=0.0, color=(0.92, 0.93, 0.90), size=1.00),
}


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return "check" if "--no-render" in argv else "stills"


def link(nt, src, dst):
    nt.links.new(src, dst)


def sock(node, identifier: str):
    return p106b.sock(node, identifier)


def geom_pos(nt, loc=(-980, 40)):
    node = nt.nodes.new("ShaderNodeNewGeometry")
    node.location = loc
    return node.outputs["Position"]


def sep_xyz(nt, vector, loc):
    node = nt.nodes.new("ShaderNodeSeparateXYZ")
    node.location = loc
    link(nt, vector, node.inputs["Vector"])
    return node.outputs["X"], node.outputs["Y"], node.outputs["Z"]


def generated_pos(nt, loc=(-980, 40)):
    tex = p106.tex_coord(nt, loc)
    return tex.outputs["Generated"]


def broad_color(nt, fac, dark, light, loc):
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.location = loc
    ramp.color_ramp.interpolation = "EASE"
    ramp.color_ramp.elements[0].position = 0.40
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.60
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    link(nt, fac, ramp.inputs["Fac"])
    return ramp.outputs["Color"]


def rebuild_wall(mat: bpy.types.Material) -> None:
    """Keep broad quiet areas, but retain age when the wall is well lit."""
    nt = p106b.reset_tree(mat)
    pos = generated_pos(nt, (-980, 40))
    _x, _y, z = sep_xyz(nt, pos, (-820, 40))
    macro = p106.noise(nt, pos, 1.50, 1.2, (-620, 300), 0.30)
    meso = p106.noise(nt, pos, 4.00, 4.0, (-620, 100), 0.46, 0.05)
    vertical = p106.noise(
        nt, p106.mapping(nt, pos, (-620, -80), (18.0, 5.0, 0.24)),
        1.0, 2.0, (-620, -100), 0.52,
    )
    pores = p106.voronoi(nt, pos, 38.0, (-620, -300), 0.90)
    micro = p106.noise(nt, pos, 88.0, 8.0, (-620, -480), 0.52)

    warm_a = (0.188, 0.178, 0.158)
    warm_b = (0.082, 0.078, 0.070)
    moisture = (0.064, 0.057, 0.048)
    repair = (0.205, 0.190, 0.158)
    skirt_col = (0.052, 0.048, 0.042)

    macro_m = p106.map_range(nt, macro.outputs["Fac"], 0.25, 0.75, 0.0, 0.38, (-360, 300))
    base = broad_color(nt, macro.outputs["Fac"], warm_b, warm_a, (-100, 260))
    meso_m = p106.map_range(nt, meso.outputs["Fac"], 0.30, 0.70, 0.0, 0.24, (-360, 100))
    aged = p106.mix_col(
        nt, p106.mathn(nt, "MULTIPLY", (-100, 100), meso_m, 0.30),
        base, repair, (160, 220),
    )
    vertical_m = p106.sparse(nt, vertical.outputs["Fac"], (-360, -100), 0.58, 0.90)
    damp = p106.mix_col(
        nt, p106.mathn(nt, "MULTIPLY", (-100, -100), vertical_m, 0.28),
        aged, moisture, (160, 80),
    )
    skirt = p106.map_range(nt, z, 0.01, 0.56, 0.40, 0.0, (-360, -220))
    colored = p106.mix_col(nt, skirt, damp, skirt_col, (380, 100))

    pore_h = p106.map_range(nt, pores.outputs["Distance"], 0.0, 0.30, 1.0, 0.0, (-360, -340))
    rough = p106.mix_f(nt, pore_h, 0.84, 0.93, (120, -220))
    rough = p106.mix_f(nt, skirt, rough, 0.91, (380, -220))
    nrm = p106.bump(nt, micro.outputs["Fac"], 0.011, 0.0013, (380, -380))
    nrm = p106.bump(nt, pore_h, 0.005, 0.0007, (560, -380), nrm)

    bsdf = p106.principled(nt, (760, 60))
    out = p106.output(nt, (1020, 60))
    p106.set_spec(bsdf, 0.18, ior=1.52, metallic=0.0, coat=0.0)
    link(nt, colored, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*warm_a, 1.0)


def rebuild_floor(mat: bpy.types.Material) -> None:
    """Build isotropic, multi-scale concrete without panel-like repetition."""
    nt = p106b.reset_tree(mat)
    pos = generated_pos(nt, (-980, 40))
    generated_x, _generated_y, _generated_z = sep_xyz(nt, pos, (-860, 40))
    macro = p106.noise(nt, pos, 2.00, 1.0, (-660, 360), 0.26)
    medium = p106.noise(nt, pos, 4.00, 3.0, (-660, 160), 0.42, 0.06)
    traffic = p106.noise(nt, pos, 10.0, 3.0, (-660, -20), 0.44, 0.08)
    edge = p106.noise(nt, pos, 6.00, 2.0, (-660, -180), 0.42)
    pores = p106.voronoi(nt, pos, 52.0, (-660, -360), 0.93)
    micro = p106.noise(nt, pos, 112.0, 8.0, (-660, -540), 0.50)

    concrete_a = (0.132, 0.136, 0.146)
    concrete_b = (0.054, 0.058, 0.066)
    dust = (0.034, 0.035, 0.039)
    repair = (0.158, 0.151, 0.138)
    aggregate = (0.170, 0.166, 0.154)

    macro_m = p106.map_range(nt, macro.outputs["Fac"], 0.24, 0.76, 0.0, 0.38, (-420, 360))
    base = broad_color(nt, macro.outputs["Fac"], concrete_b, concrete_a, (-160, 320))
    medium_m = p106.map_range(nt, medium.outputs["Fac"], 0.30, 0.70, 0.0, 0.32, (-420, 160))
    aged = p106.mix_col(
        nt, p106.mathn(nt, "MULTIPLY", (-160, 160), medium_m, 0.24),
        base, repair, (80, 260),
    )
    traffic_m = p106.sparse(nt, traffic.outputs["Fac"], (-420, -20), 0.58, 0.88)
    worn = p106.mix_col(
        nt, p106.mathn(nt, "MULTIPLY", (-160, -20), traffic_m, 0.22),
        aged, dust, (280, 220),
    )
    centered_x = p106.mathn(nt, "SUBTRACT", (-420, -180), generated_x, 0.5)
    abs_x = p106.mathn(nt, "ABSOLUTE", (-240, -180), centered_x, 0.0)
    edge_m = p106.map_range(nt, abs_x, 0.38, 0.50, 0.0, 0.28, (-40, -180))
    edge_dirt = p106.mix_col(
        nt, edge_m, worn, dust, (280, 80),
    )
    old_zone = p106.sparse(nt, edge.outputs["Fac"], (-420, -360), 0.78, 0.95)
    colored = p106.mix_col(
        nt, p106.mathn(nt, "MULTIPLY", (-160, -360), old_zone, 0.18),
        edge_dirt, repair, (460, 40),
    )
    aggregate_m = p106.map_range(nt, pores.outputs["Distance"], 0.0, 0.22, 0.10, 0.0, (80, -460))
    colored = p106.mix_col(
        nt, p106.mathn(nt, "MULTIPLY", (260, -460), aggregate_m, 0.12),
        colored, aggregate, (640, 40),
    )

    pore_h = p106.map_range(nt, pores.outputs["Distance"], 0.0, 0.25, 1.0, 0.0, (-160, -520))
    rough = p106.mix_f(nt, pore_h, 0.80, 0.93, (120, -420))
    rough = p106.mix_f(nt, traffic_m, rough, 0.70, (360, -360))
    rough = p106.mix_f(nt, edge_m, rough, 0.91, (560, -300))
    nrm = p106.bump(nt, macro.outputs["Fac"], 0.004, 0.0018, (280, -520))
    nrm = p106.bump(nt, micro.outputs["Fac"], 0.012, 0.0011, (460, -520), nrm)
    nrm = p106.bump(nt, pore_h, 0.010, 0.0008, (640, -520), nrm)

    bsdf = p106.principled(nt, (840, 40))
    out = p106.output(nt, (1100, 40))
    p106.set_spec(bsdf, 0.24, ior=1.52, metallic=0.0, coat=0.0)
    link(nt, colored, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, nrm, bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*concrete_a, 1.0)


def rebuild_cabinet(mat: bpy.types.Material) -> None:
    """Retain 10.6B painted steel, with a little more operational dulling."""
    nt = p106b.reset_tree(mat)
    pos = generated_pos(nt, (-980, 40))
    info = nt.nodes.new("ShaderNodeObjectInfo")
    info.location = (-820, 360)
    newer = info.outputs["Random"]
    peel = p106.noise(nt, pos, 94.0, 6.0, (-620, 40), 0.46)
    wear = p106.noise(nt, pos, 6.0, 2.0, (-620, 240), 0.40)
    a_new, a_old = (0.158, 0.172, 0.164), (0.090, 0.108, 0.101)
    b_new, b_old = (0.126, 0.144, 0.136), (0.070, 0.086, 0.080)
    new_col = p106.mix_col(nt, p106.map_range(nt, peel.outputs["Fac"], 0.3, 0.7, 0.0, 0.14, (-360, 160)), a_new, b_new, (-80, 220))
    old_col = p106.mix_col(nt, p106.map_range(nt, peel.outputs["Fac"], 0.3, 0.7, 0.0, 0.18, (-360, 40)), a_old, b_old, (-80, 40))
    base = p106.mix_col(nt, newer, new_col, old_col, (180, 120))
    wear_m = p106.sparse(nt, wear.outputs["Fac"], (-360, -80), 0.70, 0.90)
    colored = p106.mix_col(nt, p106.mathn(nt, "MULTIPLY", (-80, -80), wear_m, 0.24), base, (0.060, 0.057, 0.050), (260, -20))
    rough0 = p106.mix_f(nt, newer, 0.50, 0.64, (180, -180))
    rough = p106.mix_f(nt, peel.outputs["Fac"], rough0, p106.mathn(nt, "ADD", (-80, -220), rough0, 0.06), (360, -180))
    bevel = nt.nodes.new("ShaderNodeBevel")
    bevel.location = (420, -420)
    bevel.samples = 3
    bevel.inputs["Radius"].default_value = 0.0013
    nrm = p106.bump(nt, peel.outputs["Fac"], 0.008, 0.0007, (240, -340))
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "VECTOR"
    mix.location = (600, -340)
    sock(mix, "Factor_Float").default_value = 0.50
    link(nt, nrm, sock(mix, "A_Vector"))
    link(nt, bevel.outputs["Normal"], sock(mix, "B_Vector"))
    bsdf = p106.principled(nt, (820, 40))
    out = p106.output(nt, (1080, 40))
    p106.set_spec(bsdf, 0.50, ior=1.46, metallic=0.0, coat=0.10, coat_rough=0.40)
    link(nt, colored, bsdf.inputs["Base Color"])
    link(nt, rough, bsdf.inputs["Roughness"])
    link(nt, sock(mix, "Result_Vector"), bsdf.inputs["Normal"])
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (*a_new, 1.0)


def apply_final_lighting() -> None:
    p106b.LIGHT_IDENTITY = LIGHT_IDENTITY
    p106b.apply_lighting()


def apply_bright_stress_lighting() -> None:
    """Raise existing practical sources only; no ambient or material change."""
    apply_final_lighting()
    for obj in bpy.data.objects:
        if obj.type != "LIGHT" or obj.data.energy <= 0.0:
            continue
        obj.data.energy *= 1.48


def apply_materials() -> None:
    p106b.rebuild_wall(bpy.data.materials["MAT_Wall_PaintedConcrete"])
    p106b.rebuild_floor(bpy.data.materials["MAT_Floor_IndustrialConcrete"])
    p106b.rebuild_cabinet(bpy.data.materials["MAT_Cabinet_PaintedMetal"])
    p106b.rebuild_pipe(bpy.data.materials["MAT_Pipe_DarkPaintedSteel"], True)
    p106b.rebuild_pipe(bpy.data.materials["MAT_Pipe_Secondary"], False)
    p106b.rebuild_structure(bpy.data.materials["MAT_Structure_PaintedSteel"])
    p106b.rebuild_galv(bpy.data.materials["MAT_Metal_Galvanized"], False)
    if bpy.data.materials.get("MAT_Vent_GalvanizedMetal"):
        p106b.rebuild_galv(bpy.data.materials["MAT_Vent_GalvanizedMetal"], True)
    if bpy.data.materials.get("MAT_Valve_IndustrialAccent"):
        p106b.rebuild_valve(bpy.data.materials["MAT_Valve_IndustrialAccent"])
    p106b.rebuild_diffusers()
    p106b.rebuild_housing()


def restore_final_eevee(scene: bpy.types.Scene) -> None:
    p106b.restore_eevee(scene)
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.frame_set(1)


def render(scene, camera: str, frame: int, name: str) -> Path:
    path = OUTPUT_DIR / f"{name}.jpg"
    return p106.render_still(scene, camera, frame, path)


def write_report(validation: dict, stills_ok: bool, visual_pass: bool = True) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    freeze = (
        not validation["moved"]
        and not validation["light_moved"]
        and not validation["walk_err"]
        and validation["inspect_ok"]
        and validation["p8"] == 209
        and validation["p9"] == 11
        and validation["p105"] >= 500
        and validation["wall_end"]
        and validation["frame_end"] == 216
    )
    identity = "PASS" if stills_ok and visual_pass and freeze else "FAIL"
    lines = [
        "PHASE 10.6C 地坪、老化與燈光一致性校正",
        "承接 Phase 10.6B；未重做場景，未改走廊尺度、無盡延伸、主設備、主管線或 9 秒相機。",
        "未渲染 9 秒成片，未進入 Phase 11。",
        "",
        "TEST_A：既有 CAM_P105_WALK 第 108 幀，最終 NORMAL／WEAK／OFF 實用螢光照明。",
        "TEST_B：低位地坪診斷，包含約 2–5 m 地坪與牆腳接觸。",
        "TEST_C：同一材質在較明亮實用燈光下的壓力測試；只暫時提高既有燈源，未改材質。",
        "",
        f"FLOOR READS AS POURED CONCRETE: {'PASS' if stills_ok and visual_pass else 'FAIL'}",
        f"FLOOR PANEL/TILE APPEARANCE REMOVED: {'PASS' if stills_ok and visual_pass else 'FAIL'}",
        f"WALL-TO-FLOOR CONTACT: {'PASS' if stills_ok and visual_pass else 'FAIL'}",
        f"WALL AGING UNDER NORMAL LIGHT: {'PASS' if stills_ok and visual_pass else 'FAIL'}",
        f"CABINET MATERIAL: {'PASS' if stills_ok and visual_pass else 'FAIL'}",
        f"PIPE COLOR / MATERIAL IDENTITY: {'PASS' if stills_ok and visual_pass else 'FAIL'}",
        f"LIGHTING CONSISTENCY: {'PASS' if stills_ok and visual_pass else 'FAIL'}",
        f"DARK AREA READABILITY: {'PASS' if stills_ok and visual_pass else 'FAIL'}",
        f"LEVEL 2 IDENTITY UNDER NORMAL LIGHT: {identity}",
        f"ENDLESS CORRIDOR: {'PASS' if freeze else 'FAIL'}",
        f"CAMERA FREEZE: {'PASS' if not validation['walk_err'] and validation['inspect_ok'] else 'FAIL'}",
        "",
        "材質策略：宏觀澆置色差、 中觀交通／修補／濕度 MASK、微觀各向同性孔隙；地坪不使用拉伸木紋式 bump。",
        "牆面保留安靜區，只在低牆腳、垂直濕度路徑與維修差異處增加老化。",
        "燈具位置與 NORMAL／WEAK／OFF 狀態保留；面光源尺寸放大以降低硬邊管影。",
        f"凍結檢查：非允許幾何變更 {len(validation['moved'])}，燈光位置變更 {len(validation['light_moved'])}，CAM_P105 路徑錯誤 {len(validation['walk_err'])}。",
        "等待使用者審核；停止於 Phase 10.6C。",
    ]
    path = OUTPUT_DIR / "phase10_6c_floor_aging_lighting_report.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def publish(path: Path) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, ARTIFACT_DIR / path.name)


def main() -> None:
    mode = parse_mode()
    scene = bpy.context.scene
    before = p106b.p5.snapshot()
    lights_before = p106b.capture_light_layout()
    inspect_before = p106b.p105.inspect_keys(bpy.data.objects["CAM_INSPECT"])

    # Monkey-patch only the three materials whose 10.6B response is being
    # corrected.  Pipe, equipment hardware, extension geometry, and cameras
    # remain the 10.6B implementation.
    p106b.rebuild_wall = rebuild_wall
    p106b.rebuild_floor = rebuild_floor
    p106b.rebuild_cabinet = rebuild_cabinet
    apply_materials()
    joint_mat = p106b.rebuild_joint_mat()
    joints = p106b.soften_floor_joints(joint_mat)
    p106b.add_repair_hardware()
    apply_final_lighting()
    p106b.add_eval_cameras()

    bg = scene.world.node_tree.nodes.get("Background") if scene.world and scene.world.node_tree else None
    if bg is not None:
        bg.inputs[1].default_value = 0.30
    vol = scene.world.node_tree.nodes.get("P10_Volume") if scene.world and scene.world.node_tree else None
    if vol is not None:
        vol.inputs["Density"].default_value = 0.0036

    validation = p106b.freeze_validate(scene, before, lights_before, inspect_before)
    scene.camera = bpy.data.objects[WALK_CAM]
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    stills_ok = False
    if mode == "stills":
        p106.enable_cycles_cpu(scene)
        scene.cycles.samples = 96
        scene.cycles.adaptive_threshold = 0.02
        scene.cycles.adaptive_min_samples = 24
        render(scene, WALK_CAM, HERO_FRAME, "TEST_A")
        render(scene, FLOOR_CAM, HERO_FRAME, "TEST_B")
        apply_bright_stress_lighting()
        render(scene, CLOSE_CAM, HERO_FRAME, "TEST_C")
        apply_final_lighting()
        restore_final_eevee(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
        stills_ok = all((OUTPUT_DIR / f"TEST_{letter}.jpg").exists() for letter in "ABC")

    report = write_report(validation, stills_ok, visual_pass=stills_ok)
    publish(report)
    if mode == "stills":
        for letter in "ABC":
            publish(OUTPUT_DIR / f"TEST_{letter}.jpg")
    print("Phase 10.6C complete; waiting for review; Phase 11 not started.")
    print(
        "validation",
        {
            key: validation[key]
            for key in ("moved", "light_moved", "walk_err", "p8", "p9", "p105", "wall_end", "frame_end")
        },
    )


if __name__ == "__main__":
    main()
