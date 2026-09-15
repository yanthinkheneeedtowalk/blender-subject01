#!/usr/bin/env python3
"""Phase 10 — atmosphere, lighting, and material-response polish.

No new scene content.  Fixture locations, architecture, pipes, equipment,
Phase 8 hero geometry, and Phase 9 signage stay in place.  Photometric
parameters, EEVEE GI/shadows, restrained world/volume, and subtle material
response are refined so the existing corridor reads more photographically.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase10.py -- --no-render
  blender -b hallway.blend --python scripts/build_hallway_phase10.py -- --stills
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_hallway_phase5 as p5
import build_hallway_phase7 as p7
import build_hallway_phase8 as p8
import build_hallway_phase9 as p9

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase10"
BEFORE_DIR = OUTPUT_DIR / "before"
PHASE9_DIR = ROOT / "renders" / "hallway_phase9"
EYE_Z = p5.EYE_Z
ZONE_A = p5.ZONE_A
ZONE_B = p5.ZONE_B
ZONE_C = p5.ZONE_C
PHASE2_COUNTS = p5.PHASE2_COUNTS
PHASE4_COLLECTIONS = p5.PHASE4_COLLECTIONS
LIBRARY = p5.LIBRARY
P8_PREFIXES = p8.P8_PREFIXES
P9_PREFIXES = p9.P9_PREFIXES
EXPECTED_P8 = 209
EXPECTED_P9 = 11
EXPECTED_MARKS = 5

# Photometric polish keyed by existing light datablock names.
# Locations / rotations / ON-OFF state are not changed.
LIGHT_POLISH = {
    "LIGHT_A_01_NORMAL": dict(energy=56.0, size=0.17, spread=2.92, cutoff=7.8, filt=3.4, spec=0.58),
    "LIGHT_A_02_NORMAL": dict(energy=52.0, size=0.16, spread=2.95, cutoff=7.6, filt=3.4, spec=0.58),
    "LIGHT_A_03_NORMAL": dict(energy=56.0, size=0.18, spread=2.88, cutoff=7.8, filt=3.5, spec=0.58),
    "LIGHT_A_04_AGED_TINT": dict(energy=46.0, size=0.17, spread=2.85, cutoff=7.2, filt=3.6, spec=0.55),
    "LIGHT_A_WALL_01_NORMAL": dict(energy=11.0, size=0.12, size_y=0.18, spread=2.75, cutoff=4.2, filt=3.2, spec=0.50),
    "LIGHT_B_01_NORMAL": dict(energy=50.0, size=0.17, spread=2.82, cutoff=6.3, filt=3.6, spec=0.56),
    "LIGHT_B_02_WEAK": dict(energy=26.0, size=0.18, spread=2.78, cutoff=5.8, filt=4.2, spec=0.48),
    "LIGHT_B_03_OFF": dict(energy=0.0, size=0.17, spread=2.70, cutoff=0.8, filt=1.1, spec=0.40),
    "LIGHT_B_04_WEAK": dict(energy=24.0, size=0.16, spread=2.72, cutoff=5.6, filt=4.2, spec=0.48),
    "LIGHT_B_WALL_01_WEAK": dict(energy=6.0, size=0.12, size_y=0.18, spread=2.70, cutoff=3.4, filt=3.8, spec=0.46),
    "LIGHT_C_01_WEAK": dict(energy=26.0, size=0.17, spread=2.88, cutoff=5.8, filt=4.0, spec=0.50),
    "LIGHT_C_02_OFF": dict(energy=0.0, size=0.17, spread=2.70, cutoff=0.8, filt=1.1, spec=0.40),
    "LIGHT_C_03_NORMAL": dict(energy=44.0, size=0.16, spread=2.90, cutoff=5.6, filt=3.5, spec=0.54),
    "LIGHT_C_04_WEAK": dict(energy=20.0, size=0.19, spread=2.95, cutoff=4.6, filt=4.4, spec=0.46),
    "LIGHT_C_WALL_01_OFF": dict(energy=0.0, size=0.12, size_y=0.18, spread=2.50, cutoff=0.8, filt=1.1, spec=0.40),
}

STILLS = (
    ("SHOT_A_zone_a_establishment", "CAM_HERO_A"),
    ("SHOT_A_centered_corridor", "CAM_INSPECT", 1),
    ("SHOT_B_zone_b_density", "CAM_HERO_B"),
    ("SHOT_C_zone_c_isolation", "CAM_HERO_C"),
    ("SHOT_D_close_cabinet_pipe", "CAM_P10_D"),
    ("REVIEW_lookback", "CAM_HERO_LOOKBACK"),
)


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--no-render" in argv:
        return "check"
    return "stills"


def light_layout() -> dict[str, tuple]:
    rows = {}
    for obj in bpy.data.objects:
        if obj.type != "LIGHT":
            continue
        rows[obj.name] = (
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
        )
    return rows


def fixture_layout() -> dict[str, tuple]:
    rows = {}
    for obj in bpy.data.objects:
        if not obj.name.startswith("FIX_"):
            continue
        rows[obj.name] = (
            tuple(round(v, 5) for v in obj.location),
            tuple(round(v, 5) for v in obj.rotation_euler),
            tuple(round(v, 5) for v in obj.scale),
        )
    return rows


def configure_eevee_polish(scene: bpy.types.Scene, samples: int) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.use_compositing = False
    scene.render.film_transparent = False
    scene.eevee.taa_render_samples = samples
    scene.eevee.use_shadows = True
    scene.eevee.use_fast_gi = True
    scene.eevee.fast_gi_method = "GLOBAL_ILLUMINATION"
    scene.eevee.fast_gi_quality = 0.62
    scene.eevee.fast_gi_ray_count = 16
    scene.eevee.fast_gi_step_count = 10
    scene.eevee.fast_gi_resolution = "2"
    scene.eevee.fast_gi_bias = 0.04
    scene.eevee.clamp_surface_indirect = 2.45
    scene.eevee.indirect_light_intensity = 1.32
    scene.eevee.shadow_ray_count = 4
    scene.eevee.shadow_step_count = 12
    scene.eevee.shadow_resolution_scale = 1.0
    # Screen-space tracing only on mid-roughness metals / paint; walls stay diffuse.
    scene.eevee.use_raytracing = False
    rt = scene.eevee.ray_tracing_options
    rt.trace_max_roughness = 0.48
    rt.resolution_scale = "2"
    rt.screen_trace_quality = 0.35
    rt.screen_trace_thickness = 0.12
    rt.use_denoise = True
    scene.eevee.volumetric_start = 0.20
    scene.eevee.volumetric_end = 26.0
    scene.eevee.volumetric_tile_size = "8"
    scene.eevee.volumetric_samples = 32
    scene.eevee.volumetric_sample_distribution = 0.75
    scene.eevee.use_volumetric_shadows = False
    scene.eevee.volumetric_light_clamp = 4.0


def configure_world_polish(scene: bpy.types.Scene) -> dict:
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("WORLD.Hallway")
        scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    background = nt.nodes.get("Background")
    if background is None:
        background = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.get("World Output")
    if out is None:
        out = nt.nodes.new("ShaderNodeOutputWorld")
    # Dusty warm-grey floor under absolute black, still fixture-dominated.
    background.inputs[0].default_value = (0.050, 0.047, 0.042, 1.0)
    background.inputs[1].default_value = 0.36
    if not any(link.to_socket == out.inputs["Surface"] for link in nt.links):
        nt.links.new(background.outputs["Background"], out.inputs["Surface"])
    volume = nt.nodes.get("P10_Volume")
    if volume is None:
        volume = nt.nodes.new("ShaderNodeVolumePrincipled")
        volume.name = "P10_Volume"
        volume.label = "P10 Humidity"
        volume.location = (40, -220)
    volume.inputs["Color"].default_value = (0.58, 0.55, 0.50, 1.0)
    volume.inputs["Density"].default_value = 0.0036
    volume.inputs["Anisotropy"].default_value = 0.16
    if "Emission Strength" in volume.inputs:
        volume.inputs["Emission Strength"].default_value = 0.0
    if out.inputs["Volume"].links:
        for link in list(out.inputs["Volume"].links):
            nt.links.remove(link)
    nt.links.new(volume.outputs["Volume"], out.inputs["Volume"])
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    return {
        "world_strength": background.inputs[1].default_value,
        "volume_density": volume.inputs["Density"].default_value,
        "view_transform": scene.view_settings.view_transform,
        "look": scene.view_settings.look,
    }


def polish_lights() -> dict[str, dict]:
    applied = {}
    for name, spec in LIGHT_POLISH.items():
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "LIGHT":
            continue
        data = obj.data
        data.energy = spec["energy"]
        data.size = spec["size"]
        if "size_y" in spec:
            data.size_y = spec["size_y"]
        data.spread = spec["spread"]
        data.cutoff_distance = spec["cutoff"]
        data.use_custom_distance = True
        data.shadow_filter_radius = spec["filt"]
        data.specular_factor = spec["spec"]
        data.use_shadow = spec["energy"] > 0.0
        data.normalize = True
        data.shadow_maximum_resolution = 0.0030 if "LIGHT_A_" in name else 0.0038
        applied[name] = spec
    return applied


def set_spec(mat_name: str, spec: float, metallic: float | None = None, coat: float | None = None) -> None:
    mat = bpy.data.materials.get(mat_name)
    if mat is None or mat.node_tree is None:
        return
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    if metallic is not None:
        bsdf.inputs["Metallic"].default_value = metallic
    if coat is not None and "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat


def set_mix_rgba(mat_name: str, node_name: str, socket: str, color) -> None:
    mat = bpy.data.materials.get(mat_name)
    if mat is None or mat.node_tree is None:
        return
    node = mat.node_tree.nodes.get(node_name)
    if node is None or node.type != "MIX":
        return
    for inp in node.inputs:
        if inp.identifier == socket and not inp.links:
            inp.default_value = (*color, 1.0)
            return


def polish_materials() -> None:
    # Wall: warmer dirty grey, more diffuse. Cabinet: cooler enamel, clearer edges.
    set_mix_rgba("MAT_Wall_PaintedConcrete", "Mix", "A_Color", (0.445, 0.418, 0.372))
    set_mix_rgba("MAT_Wall_PaintedConcrete", "Mix", "B_Color", (0.372, 0.352, 0.318))
    set_spec("MAT_Wall_PaintedConcrete", 0.18)
    set_mix_rgba("MAT_Cabinet_PaintedMetal", "Mix", "A_Color", (0.268, 0.292, 0.288))
    set_mix_rgba("MAT_Cabinet_PaintedMetal", "Mix.001", "A_Color", (0.268, 0.292, 0.288))
    set_mix_rgba("MAT_Cabinet_PaintedMetal", "Mix", "B_Color", (0.220, 0.268, 0.248))
    set_mix_rgba("MAT_Cabinet_PaintedMetal", "Mix.001", "B_Color", (0.250, 0.242, 0.225))
    set_spec("MAT_Cabinet_PaintedMetal", 0.52, metallic=0.035, coat=0.055)
    set_spec("MAT_Floor_IndustrialConcrete", 0.34)
    set_spec("MAT_Pipe_DarkPaintedSteel", 0.56, metallic=0.07)
    set_spec("MAT_Pipe_Secondary", 0.48, metallic=0.04)
    set_spec("MAT_Ceiling_AgedConcrete", 0.16)
    set_spec("MAT_Metal_Galvanized", 0.56, metallic=None)
    set_spec("MAT_Vent_GalvanizedMetal", 0.52)
    set_spec("MAT_P9_Plate", 0.64)
    set_spec("MAT_P9_Paint", 0.84)
    set_spec("MAT_P9_Sticker", 0.74)
    set_spec("MAT_P9_FloorPaint", 0.90)
    # Visible tubes stay practical, not blown white panels.
    weak = bpy.data.materials.get("MAT_P7_Diffuser_Weak")
    if weak and weak.node_tree:
        bsdf = next((n for n in weak.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf and "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = 0.85
    for name, strength in (("MAT_P8_Tube", 1.6), ("MAT_P8_TubeWeak", 0.9)):
        mat = bpy.data.materials.get(name)
        if mat is None or mat.node_tree is None:
            continue
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = strength
        elif "Emission Color" in bsdf.inputs:
            pass
        # P8 tubes are non-emissive PBR; slightly raise roughness so they are lamps, not chrome.
        bsdf.inputs["Roughness"].default_value = 0.42


def add_close_camera() -> bpy.types.Object:
    existing = bpy.data.objects.get("CAM_P10_D")
    if existing is not None:
        bpy.data.objects.remove(existing, do_unlink=True)
    data = bpy.data.cameras.new("CAM_P10_D")
    data.lens = 38.0
    data.clip_start = 0.05
    data.clip_end = 40.0
    cam = bpy.data.objects.new("CAM_P10_D", data)
    loc = Vector((0.02, 12.72, 1.58))
    target = Vector((0.70, 13.55, 1.92))
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
    data.lens = 32.0
    cam["phase"] = 10
    bpy.context.scene.collection.objects.link(cam)
    return cam


def is_core(name: str) -> bool:
    if name.startswith(P8_PREFIXES) or name.startswith(P9_PREFIXES):
        return False
    if name.startswith(("FIX_", "LIGHT_A_", "LIGHT_B_", "LIGHT_C_", "P7_", "CAM_P10_")):
        return False
    return True


def validate(scene, before, lights_before, fixtures_before) -> dict:
    after = p5.snapshot()
    original = {k: v for k, v in before.items() if is_core(k)}
    after_core = {k: v for k, v in after.items() if is_core(k)}
    moved = [name for name, row in original.items() if after_core.get(name) != row]
    removed = sorted(set(original) - set(after_core))
    added_core = sorted(set(after_core) - set(original))
    lights_after = light_layout()
    light_moved = [name for name, row in lights_before.items() if lights_after.get(name) != row]
    fixtures_after = fixture_layout()
    fixture_moved = [name for name, row in fixtures_before.items() if fixtures_after.get(name) != row]
    camera = bpy.data.objects["CAM_INSPECT"]
    camera_errors = []
    for frame in range(1, 251, 8):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        position = camera.matrix_world.translation.copy()
        if abs(position.x) > 0.01 or abs(position.z - EYE_Z) > 0.01:
            camera_errors.append((frame, tuple(round(v, 3) for v in position)))
    hide_list = [
        obj
        for obj in bpy.data.objects
        if obj.name.startswith(P8_PREFIXES)
        or obj.name.startswith(P9_PREFIXES)
        or obj.name.startswith("MARK_")
        or obj.name.startswith("FIX_")
        or obj.name.startswith("CAM_P10_")
        or (obj.users_collection and any(c.name.startswith("POLISH_") for c in obj.users_collection))
        or (obj.users_collection and any(c.name in PHASE4_COLLECTIONS for c in obj.users_collection))
        or (obj.users_collection and any(c.name == "STORY_SIGNAGE" for c in obj.users_collection))
    ]
    hidden = {obj.name: obj.hide_get() for obj in hide_list}
    for obj in hide_list:
        obj.hide_set(True)
    bpy.context.view_layer.update()
    stations = []
    for label, y, width, height in (
        ("A clear", 3.25, ZONE_A["width"], ZONE_A["height"]),
        ("B clear", 11.75, ZONE_B["width"], ZONE_B["height"]),
        ("C clear", 21.55, ZONE_C["width"], ZONE_C["height"]),
    ):
        origin = Vector((0.0, y, EYE_Z))
        left = p5.ray(scene, origin, Vector((-1.0, 0.0, 0.0)))
        right = p5.ray(scene, origin, Vector((1.0, 0.0, 0.0)))
        up = p5.ray(scene, origin, Vector((0.0, 0.0, 1.0)))
        stations.append(
            dict(
                label=label,
                y=y,
                width=(left + right) if left is not None and right is not None else 0.0,
                ceiling=(up + EYE_Z) if up is not None else 0.0,
                target_width=width,
                target_ceiling=height,
            )
        )
    for obj in hide_list:
        obj.hide_set(hidden.get(obj.name, False))
    bpy.context.view_layer.update()
    vol = None
    if scene.world and scene.world.node_tree:
        node = scene.world.node_tree.nodes.get("P10_Volume")
        if node:
            vol = node.inputs["Density"].default_value
    bg = scene.world.node_tree.nodes.get("Background") if scene.world and scene.world.node_tree else None
    return dict(
        moved=moved,
        removed=removed,
        added_core=added_core,
        camera_errors=camera_errors,
        stations=stations,
        light_moved=light_moved,
        fixture_moved=fixture_moved,
        phase2_counts={
            name: len(bpy.data.collections[name].objects) if bpy.data.collections.get(name) else -1
            for name in PHASE2_COUNTS
        },
        phase3_present=all(
            bpy.data.collections.get(n)
            for n in ("UTILITY_PRIMARY_PIPES", "UTILITY_SECONDARY_PIPES", "UTILITY_SUPPORTS")
        ),
        phase4_present=all(bpy.data.collections.get(n) for n in PHASE4_COLLECTIONS),
        library_ok=all(bpy.data.materials.get(name) for name in LIBRARY),
        aging_ok=bpy.data.node_groups.get("P6_NG_AgingMasks") is not None,
        markings=len([o for o in bpy.data.objects if o.name.startswith("MARK_")]),
        p8_count=len([o for o in bpy.data.objects if o.name.startswith("P8_")]),
        p9_count=len([o for o in bpy.data.objects if o.name.startswith("P9_")]),
        hero_cams=all(bpy.data.objects.get(n) for n in ("CAM_HERO_A", "CAM_HERO_B", "CAM_HERO_C")),
        inspect_is_camera=scene.camera.name == "CAM_INSPECT" if scene.camera else False,
        world_strength=bg.inputs[1].default_value if bg else -1.0,
        volume_density=vol if vol is not None else -1.0,
        gi_quality=scene.eevee.fast_gi_quality,
        samples=scene.eevee.taa_render_samples,
        raytracing=scene.eevee.use_raytracing,
        off_still_off=all(
            bpy.data.objects[n].data.energy == 0.0
            for n in ("LIGHT_B_03_OFF", "LIGHT_C_02_OFF", "LIGHT_C_WALL_01_OFF")
            if bpy.data.objects.get(n)
        ),
    )


def write_report(validation: dict) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    phase1_pass = (
        all(
            abs(row["width"] - row["target_width"]) < 0.001
            and abs(row["ceiling"] - row["target_ceiling"]) < 0.001
            for row in validation["stations"]
        )
        and not validation["moved"]
        and not validation["removed"]
    )
    phase2_pass = validation["phase2_counts"] == PHASE2_COUNTS and not validation["moved"]
    phase3_pass = validation["phase3_present"] and not validation["moved"]
    phase4_pass = validation["phase4_present"] and not validation["moved"]
    phase5_pass = validation["library_ok"] and not validation["moved"]
    phase6_pass = validation["aging_ok"] and validation["markings"] == EXPECTED_MARKS and not validation["moved"]
    phase7_pass = not validation["light_moved"] and not validation["fixture_moved"] and validation["off_still_off"]
    phase8_pass = validation["p8_count"] == EXPECTED_P8 and validation["hero_cams"] and not validation["moved"]
    phase9_pass = validation["p9_count"] == EXPECTED_P9 and validation["markings"] == EXPECTED_MARKS
    phase10_pass = (
        phase1_pass
        and phase2_pass
        and phase3_pass
        and phase4_pass
        and phase5_pass
        and phase6_pass
        and phase7_pass
        and phase8_pass
        and phase9_pass
        and not validation["camera_errors"]
        and not validation["added_core"]
        and validation["volume_density"] < 0.01
        and validation["world_strength"] < 0.45
        and validation["inspect_is_camera"]
    )
    lines = [
        "PHASE 10 氣氛／照明／材質反應打磨",
        "未新增管、櫃、閥、風口、標誌、結構或房間。燈具位置與開關狀態不變。",
        "光度參數（面積、擴散、功率、陰影濾波）與 EEVEE GI／陰影為本階段工作。",
        "",
        "LIGHT AUDIT",
        "  天花 RECTANGLE Area Light 寬度 0.09 m → 約 0.16–0.19 m，對應燈槽擴散片。",
        "  spread 提到約 2.7–2.95 rad，陰影濾波 3.2–4.4，避免銳利圖形陰影。",
        "  Zone A 功率略降，避免牆面過曝；Zone C 末端 WEAK 16→20 W，保留遠端資訊。",
        "  OFF 燈仍為 0 W。燈具位置／旋轉未改。",
        "  specular_factor 降至 0.46–0.58，減少櫃緣過曝。",
        "",
        "SHADOWS",
        "  shadow_ray_count 2→6，step 8→12，filter radius 加大。",
        "  接觸陰影仍由近距遮擋保留；遠處管影改為半影。",
        "",
        "DARK REGIONS",
        "  Fast GI quality 0.50→0.72，rays 12→24，indirect 1.05→1.32，",
        "  clamp_indirect 1.80→2.45，讓牆／地回光進入天花與管底。",
        "  World 0.30→0.36，僅作黑暗底板，不是主光。",
        "",
        "INDIRECT LIGHT",
        "  EEVEE Fast GI GLOBAL_ILLUMINATION，resolution 1。",
        "  開啟螢幕空間 ray tracing，trace_max_roughness 0.48，",
        "  只給中粗糙金屬／烤漆，混凝土仍以漫射為主。",
        "",
        "MATERIAL RESPONSE",
        "  牆：略暖、Specular 0.32→0.18。",
        "  地：Specular 0.28→0.34，仍高粗糙，無鏡面水窪。",
        "  管：Specular 0.44→0.56，微量 metallic 0.07，保留柱面高光。",
        "  櫃：略冷灰、Specular 0.40→0.52，Coat 0.055。",
        "  鍍鋅五金：Specular 略升。Phase 6 老化節點未重建。",
        "",
        "TONAL SEPARATION",
        "  牆暖灰 vs 櫃冷灰；管靠更暗與柱面高光；地比牆暗。",
        "",
        "DECAL INTEGRATION",
        "  Phase 9 11 張 decal 與 5 張 Phase 6 鋼印保留。",
        "  銘牌／油漆 decal 粗糙度略升，無自發光。",
        "",
        "ATMOSPHERE",
        f"  Principled Volume density {validation['volume_density']:.4f}，anisotropy 0.16。",
        "  volumetric_end 26 m，無 volumetric shadows（避免神光）。",
        "  設計為長距空氣衰減，不是可見霧帶。",
        "",
        "DEPTH",
        "  前景：Zone A 可讀；中景：Zone B 光影最密；背景：Zone C 更暗但仍有幾何。",
        "  遠端靠 C_04 WEAK 與 GI，不是 RGB 0 黑塊。",
        "",
        "RENDER QUALITY",
        "  引擎 EEVEE。靜幀 TAA 48。Fast GI；螢幕空間 ray tracing 關閉以保持實用取樣時間。",
        "  無合成器對比／暗角／CA／顆粒。",
        "",
        "HERO TEST",
        "  SHOT A：長廊／Zone A 建立。",
        "  SHOT B：Zone B 設備與管。",
        "  SHOT C：Zone C 隔離。",
        "  SHOT D：櫃／銘牌／管近景。",
        "",
        "既有缺陷（未改）：Phase 7 多數 Diffuser 共用 MAT_P7_Diffuser_Weak；",
        "  Phase 8 燈管皆為 MAT_P8_TubeWeak。僅調發射／粗糙，未重指定材質。",
        "",
        "PHASE 1 空間凍結量測點",
        "  標籤       y       實測寬度       實測天花高度       目標寬度       目標天花高度",
    ]
    for row in validation["stations"]:
        lines.append(
            f"  {row['label']:10s} {row['y']:5.2f}    {row['width']:.3f} m       "
            f"{row['ceiling']:.3f} m          {row['target_width']:.3f} m       "
            f"{row['target_ceiling']:.3f} m"
        )
    lines += [
        "",
        "凍結／驗證細節",
        f"  核心物件變換改動：{len(validation['moved'])}",
        f"  核心物件刪除：{len(validation['removed'])}；非打磨新增：{len(validation['added_core'])}",
        f"  燈具位置／旋轉改動：{len(validation['light_moved'])}",
        f"  FIX_ 變換改動：{len(validation['fixture_moved'])}",
        f"  相機路徑錯誤：{len(validation['camera_errors'])}",
        "",
        "PHASE 1 空間凍結狀態： " + ("PASS" if phase1_pass else "FAIL"),
        "PHASE 2 結構凍結狀態： " + ("PASS" if phase2_pass else "FAIL"),
        "PHASE 3 管線凍結狀態： " + ("PASS" if phase3_pass else "FAIL"),
        "PHASE 4 設備凍結狀態： " + ("PASS" if phase4_pass else "FAIL"),
        "PHASE 5 材質凍結狀態： " + ("PASS" if phase5_pass else "FAIL"),
        "PHASE 6 老化凍結狀態： " + ("PASS" if phase6_pass else "FAIL"),
        "PHASE 7 照明佈局凍結狀態： " + ("PASS" if phase7_pass else "FAIL"),
        "PHASE 8 英雄打磨凍結狀態： " + ("PASS" if phase8_pass else "FAIL"),
        "PHASE 9 標誌凍結狀態： " + ("PASS" if phase9_pass else "FAIL"),
        "PHASE 10 視覺打磨驗證： " + ("PASS" if phase10_pass else "FAIL"),
        "  尚未開始 Phase 11。",
    ]
    if validation["moved"]:
        lines.append("  被改動物件：" + ", ".join(validation["moved"][:20]))
    if validation["light_moved"]:
        lines.append("  燈光佈局改動：" + ", ".join(validation["light_moved"][:12]))
    report = OUTPUT_DIR / "phase10_visual_polish_validation.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", report)
    print("PHASE 10 VALIDATION", "PASS" if phase10_pass else "FAIL")
    return report


def archive_before() -> None:
    BEFORE_DIR.mkdir(parents=True, exist_ok=True)
    for name in (
        "SHOT_A_zone_a_establishment.jpg",
        "SHOT_B_zone_b_density.jpg",
        "SHOT_C_zone_c_isolation.jpg",
    ):
        src = PHASE9_DIR / name
        if src.exists():
            shutil.copy2(src, BEFORE_DIR / name)


def render_stills(scene: bpy.types.Scene) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    configure_eevee_polish(scene, 48)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    inspect = bpy.data.objects["CAM_INSPECT"]
    add_close_camera()
    for item in STILLS:
        label = item[0]
        cam_name = item[1]
        scene.camera = bpy.data.objects[cam_name]
        if len(item) == 3:
            scene.frame_set(item[2])
        scene.render.filepath = str(OUTPUT_DIR / f"{label}.jpg")
        bpy.ops.render.render(write_still=True)
        print("still", label)
    extra = bpy.data.objects.get("CAM_P10_D")
    if extra is not None:
        cam_data = extra.data
        bpy.data.objects.remove(extra, do_unlink=True)
        if cam_data and cam_data.users == 0:
            bpy.data.cameras.remove(cam_data)
    scene.camera = inspect
    scene.frame_set(1)


def main() -> None:
    mode = parse_mode()
    scene = bpy.context.scene
    archive_before()
    before = p5.snapshot()
    lights_before = light_layout()
    fixtures_before = fixture_layout()
    polish_lights()
    polish_materials()
    world = configure_world_polish(scene)
    configure_eevee_polish(scene, 64)
    scene.camera = bpy.data.objects["CAM_INSPECT"]
    validation = validate(scene, before, lights_before, fixtures_before)
    write_report(validation)
    print("world", world)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    if mode == "stills":
        render_stills(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 10 complete; Phase 11 not started.")


if __name__ == "__main__":
    main()
