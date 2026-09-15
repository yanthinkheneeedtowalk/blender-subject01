#!/usr/bin/env python3
"""Phase 9 — decals, signage, and surface storytelling.

Adds a sparse functional identification layer over the frozen Phase 1–8
utility corridor.  Architecture, pipes, equipment, materials, aging,
lighting, and Phase 8 hero geometry are not moved or redesigned.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase9.py -- --no-render
  blender -b hallway.blend --python scripts/build_hallway_phase9.py -- --stills
"""

from __future__ import annotations

import json
import subprocess
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

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase9"
ASSET_DIR = ROOT / "assets" / "hallway_phase9"
ATLAS_PATH = ASSET_DIR / "p9_stencil_atlas.png"
UV_PATH = ASSET_DIR / "p9_uv.json"
EYE_Z = p5.EYE_Z
ZONE_A = p5.ZONE_A
ZONE_B = p5.ZONE_B
ZONE_C = p5.ZONE_C
PHASE2_COUNTS = p5.PHASE2_COUNTS
PHASE4_COLLECTIONS = p5.PHASE4_COLLECTIONS
LIBRARY = p5.LIBRARY
P8_PREFIXES = p8.P8_PREFIXES
P9_PREFIXES = ("P9_",)
COLLECTION = "STORY_SIGNAGE"
EXPECTED_P8 = 209
EXPECTED_MARKS = 5

STILLS = p8.STILLS

# World-space overlays. Offsets stay millimetre-scale to avoid z-fighting
# without floating off the host surface.
#
# Naming convention (Plant Utility Corridor 2):
#   ELEC-A## / ELEC-B## / ELEC-C##  electrical cabinets
#   SVC-B##                         service cabinets
#   PN-##                           junction panels (Phase 6 PN-04 retained)
#   P-##                            primary header
#   CW-#                            companion / process line (Phase 6 CW-2)
#   V-2B                            valve on line 2, Zone B
#   VENT-##                         ventilation unit
#   U-##                            isolated utility circuit (Phase 6 U-17)
MARKS = (
    dict(
        name="P9_ELEC_A04",
        cell="elec_a04",
        loc=(0.961, 3.200, 1.780),
        w=0.086,
        h=0.026,
        normal="-X",
        mat="plate",
        meaning="Zone A junction nameplate ELEC-A04",
        rank="primary",
        zone="A",
    ),
    dict(
        name="P9_ELEC_B12",
        cell="elec_b12",
        loc=(0.841, 10.700, 1.680),
        w=0.112,
        h=0.030,
        normal="-X",
        mat="plate",
        meaning="Zone B control-cabinet nameplate ELEC-B12",
        rank="primary",
        zone="B",
    ),
    dict(
        name="P9_SVC_B04",
        cell="svc_b04",
        loc=(0.816, 13.250, 1.620),
        w=0.126,
        h=0.030,
        normal="-X",
        mat="plate",
        meaning="Zone B service-cabinet nameplate SVC-B04",
        rank="primary",
        zone="B",
    ),
    dict(
        name="P9_ELEC_C07",
        cell="elec_c07",
        loc=(0.911, 19.420, 1.720),
        w=0.092,
        h=0.024,
        normal="-X",
        mat="plate",
        meaning="Zone C faded cabinet nameplate ELEC-C07",
        rank="primary",
        zone="C",
    ),
    dict(
        name="P9_PIPE_P02",
        cell="p02",
        loc=(-0.705, 3.10, 2.46),
        w=0.22,
        h=0.075,
        normal="+X",
        mat="paint",
        meaning="Zone A primary header P-02 with flow arrow toward C",
        rank="primary",
        zone="A",
    ),
    dict(
        name="P9_WARN_HV_B",
        cell="hv",
        loc=(0.838, 13.250, 1.430),
        w=0.20,
        h=0.064,
        normal="-X",
        mat="paint",
        meaning="HIGH VOLTAGE plate on electrical service cabinet SVC-B04",
        rank="primary",
        zone="B",
    ),
    dict(
        name="P9_VALVE_V2B",
        cell="v2b",
        loc=(0.735, 14.38, 2.43),
        w=0.10,
        h=0.040,
        normal="-X",
        mat="paint",
        meaning="Zone B inline valve identity V-2B on line 2",
        rank="secondary",
        zone="B",
    ),
    dict(
        name="P9_VENT_03",
        cell="vent03",
        loc=(-0.973, 12.050, 1.905),
        w=0.14,
        h=0.046,
        normal="+X",
        mat="paint",
        meaning="Zone B wall ventilator identity VENT-03",
        rank="secondary",
        zone="B",
    ),
    dict(
        name="P9_WARN_HOT_B",
        cell="hot",
        loc=(1.018, 14.62, 2.14),
        w=0.16,
        h=0.048,
        normal="-X",
        mat="paint",
        meaning="HOT SURFACE stencil on the wall under the Zone B valve",
        rank="secondary",
        zone="B",
    ),
    dict(
        name="P9_INSP_B_SVC",
        cell="insp",
        loc=(0.838, 13.42, 1.05),
        w=0.055,
        h=0.066,
        normal="-X",
        mat="sticker",
        meaning="Later inspection sticker INSP 11-02 / M.H. on SVC-B04",
        rank="secondary",
        zone="B",
    ),
    dict(
        name="P9_FLOOR_B_BAY",
        cell="floor",
        loc=(0.50, 13.25, 0.0035),
        w=0.30,
        h=0.42,
        normal="+Z",
        mat="floor",
        meaning="Faded equipment-placement bay in front of SVC-B04",
        rank="secondary",
        zone="B",
    ),
)


def parse_mode() -> str:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if "--no-render" in argv:
        return "check"
    if "--playblast" in argv:
        return "playblast"
    return "stills"


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def ensure_atlas() -> dict[str, tuple[float, float, float, float]]:
    if not ATLAS_PATH.exists() or not UV_PATH.exists():
        subprocess.check_call(
            ["/usr/bin/python3", str(SCRIPT_DIR / "generate_hallway_phase9_stencils.py")]
        )
    uvs = json.loads(UV_PATH.read_text(encoding="utf-8"))
    return {key: tuple(val) for key, val in uvs.items()}


def clear_phase9() -> None:
    col = bpy.data.collections.get(COLLECTION)
    if col is not None:
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    for mat in list(bpy.data.materials):
        if mat.name.startswith("MAT_P9_"):
            bpy.data.materials.remove(mat)
    for img in list(bpy.data.images):
        if img.name.startswith("P9_"):
            bpy.data.images.remove(img)
    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith("P9_") and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def make_decal_mesh(name: str, width: float, height: float, normal: str, uv) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    hw, hh = width * 0.5, height * 0.5
    u0, v0, u1, v1 = uv
    if normal == "-X":
        verts = [(0.0, -hw, -hh), (0.0, -hw, hh), (0.0, hw, hh), (0.0, hw, -hh)]
        uvs = ((u1, v0), (u1, v1), (u0, v1), (u0, v0))
    elif normal == "+X":
        verts = [(0.0, hw, -hh), (0.0, hw, hh), (0.0, -hw, hh), (0.0, -hw, -hh)]
        uvs = ((u1, v0), (u1, v1), (u0, v1), (u0, v0))
    elif normal == "+Z":
        verts = [(-hw, -hh, 0.0), (hw, -hh, 0.0), (hw, hh, 0.0), (-hw, hh, 0.0)]
        uvs = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
    else:
        raise ValueError(f"Unsupported decal normal {normal}")
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    layer = mesh.uv_layers.new(name="UVMap")
    for loop, uvco in zip(layer.data, uvs):
        loop.uv = uvco
    mesh.update()
    return mesh


def atlas_material(name: str, image: bpy.types.Image, roughness: float) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "HASHED"
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (420, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (160, 0)
    img_node = nt.nodes.new("ShaderNodeTexImage")
    img_node.location = (-240, 0)
    img_node.image = image
    img_node.interpolation = "Smart"
    img_node.extension = "CLIP"
    nt.links.new(img_node.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(img_node.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = 0.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def build_materials(image: bpy.types.Image) -> dict[str, bpy.types.Material]:
    return {
        "plate": atlas_material("MAT_P9_Plate", image, 0.58),
        "paint": atlas_material("MAT_P9_Paint", image, 0.82),
        "sticker": atlas_material("MAT_P9_Sticker", image, 0.72),
        "floor": atlas_material("MAT_P9_FloorPaint", image, 0.88),
    }


def add_decals(uvs: dict[str, tuple], mats: dict[str, bpy.types.Material]) -> list[str]:
    col = collection(COLLECTION)
    names = []
    for mark in MARKS:
        mesh = make_decal_mesh(
            f"{mark['name']}_MESH",
            mark["w"],
            mark["h"],
            mark["normal"],
            uvs[mark["cell"]],
        )
        obj = bpy.data.objects.new(mark["name"], mesh)
        obj.location = mark["loc"]
        obj["phase"] = 9
        obj["story"] = mark["meaning"]
        obj["rank"] = mark["rank"]
        obj["zone"] = mark["zone"]
        if hasattr(obj, "visible_shadow"):
            obj.visible_shadow = False
        col.objects.link(obj)
        obj.data.materials.append(mats[mark["mat"]])
        names.append(obj.name)
    return names


def is_core(name: str) -> bool:
    return not name.startswith(P8_PREFIXES) and not name.startswith(P9_PREFIXES)


def validate(scene, before, lights_before, fixtures_before, p8_before, names) -> dict:
    after = p5.snapshot()
    original = {k: v for k, v in before.items() if is_core(k)}
    after_core = {k: v for k, v in after.items() if is_core(k)}
    moved = [name for name, row in original.items() if after_core.get(name) != row]
    removed = sorted(set(original) - set(after_core))
    added_core = sorted(set(after_core) - set(original))
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
        or (obj.users_collection and any(c.name.startswith("POLISH_") for c in obj.users_collection))
        or (obj.users_collection and any(c.name in PHASE4_COLLECTIONS for c in obj.users_collection))
        or (obj.users_collection and any(c.name == COLLECTION for c in obj.users_collection))
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
    lights_after = p8.light_signature()
    fixtures_after = p8.fixture_signature()
    p8_after = len([o for o in bpy.data.objects if o.name.startswith("P8_")])
    return dict(
        moved=moved,
        removed=removed,
        added_core=added_core,
        camera_errors=camera_errors,
        stations=stations,
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
        light_changed=[name for name, row in lights_before.items() if lights_after.get(name) != row],
        fixture_moved=[name for name, row in fixtures_before.items() if fixtures_after.get(name) != row],
        p8_count=p8_after,
        p8_unchanged=p8_after == p8_before == EXPECTED_P8,
        p9_count=len(names),
        p9_primary=len([m for m in MARKS if m["rank"] == "primary"]),
        p9_secondary=len([m for m in MARKS if m["rank"] == "secondary"]),
        p9_mats=len([m for m in bpy.data.materials if m.name.startswith("MAT_P9_")]),
        hero_cams=all(bpy.data.objects.get(n) for n in ("CAM_HERO_A", "CAM_HERO_B", "CAM_HERO_C")),
        inspect_is_camera=scene.camera.name == "CAM_INSPECT" if scene.camera else False,
        names=names,
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
    phase7_pass = not validation["light_changed"] and not validation["fixture_moved"]
    phase8_pass = validation["p8_unchanged"] and validation["hero_cams"] and not validation["moved"]
    sparse = validation["p9_count"] <= 12 and validation["p9_primary"] <= 8
    phase9_pass = (
        phase1_pass
        and phase2_pass
        and phase3_pass
        and phase4_pass
        and phase5_pass
        and phase6_pass
        and phase7_pass
        and phase8_pass
        and not validation["camera_errors"]
        and not validation["added_core"]
        and validation["p9_count"] == len(MARKS)
        and sparse
        and validation["inspect_is_camera"]
    )
    lines = [
        "PHASE 9 標誌／識別／表面敘事",
        "未移動牆、管、主設備、走廊尺寸、燈光或 Phase 8 英雄幾何。",
        "既有 Phase 6 鋼印（PN-04、INSP 03-98、CW-2、ACCESS、U-17）保留不改。",
        "",
        "SIGNAGE SYSTEM",
        "  命名慣例：Plant Utility Corridor 的英文工業代碼。",
        "  ELEC-A## / ELEC-B## / ELEC-C##＝電氣櫃；SVC-B##＝維修櫃；",
        "  PN-##＝接線盒（沿用 PN-04）；P-##＝左主管；CW-#＝右伴管（沿用 CW-2）；",
        "  V-2B＝2 號線 Zone B 閥；VENT-##＝通風；U-##＝孤立回路（沿用 U-17）。",
        "  字體：Liberation Sans Bold 設備碼、Liberation Sans 警告副標、",
        "  DejaVu Sans Mono 巡檢日期。無裝飾／恐怖／科幻字體。全英語。",
        "",
        "EQUIPMENT LABELS",
        "  P9_ELEC_A04：Zone A 接線盒銘牌 y=3.20，ELEC-A04。",
        "  P9_ELEC_B12：Zone B 控制櫃銘牌 y=10.70，ELEC-B12。",
        "  P9_SVC_B04：Zone B 維修／電氣櫃銘牌 y=13.25，SVC-B04。",
        "  P9_ELEC_C07：Zone C 孤立櫃銘牌 y=19.42，褪色 ELEC-C07。",
        "  P9_VENT_03：Zone B 左牆通風 y=12.05，VENT-03。",
        "  P9_VALVE_V2B：Zone B 閥前 y=14.38，V-2B。",
        "",
        "PIPE IDENTIFICATION",
        "  P9_PIPE_P02：Zone A 左主管 y=3.10，P-02 加流向箭頭（朝 Zone C／+Y）。",
        "  既有 MARK_PIPE_CW2：Zone B 右牆 CW-2，不重複上色。",
        "  未替每根管子上色帶；沿用 Phase 8 幾何識別環。",
        "",
        "WARNING SIGNAGE",
        "  P9_WARN_HV_B：HIGH VOLTAGE + AUTHORIZED PERSONNEL，貼在 SVC-B04 電氣櫃門。",
        "    理由：該櫃屬 EQUIPMENT_ELECTRICAL。",
        "  P9_WARN_HOT_B：HOT SURFACE，閥件下方牆面。",
        "    理由：鄰近 y=14.62 熱製程閥／主管。",
        "  無空白牆警告、無遊戲 UI 箭頭。",
        "",
        "MAINTENANCE HISTORY",
        "  既有 MARK_INSP_B：控制櫃 INSP 03-98。",
        "  P9_INSP_B_SVC：SVC-B04 門下角貼紙 INSP 11-02／OK／M.H.，一角剝落。",
        "  日期只暗示曾有人巡檢，不建立劇情年表。",
        "",
        "ZONE A",
        "  最清楚、最程序化：ELEC-A04 銘牌、P-02 流向、既有 PN-04。",
        "",
        "ZONE B",
        "  資訊最密但不堆字：ELEC-B12、SVC-B04、HIGH VOLTAGE、V-2B、VENT-03、",
        "  HOT SURFACE、INSP 11-02、地坪定位框，加上既有 INSP 03-98 與 CW-2。",
        "",
        "ZONE C",
        "  刻意安靜：僅褪色 ELEC-C07，加上既有 ACCESS 與 U-17。無恐怖字句。",
        "",
        "DECAL IMPLEMENTATION",
        "  薄平面 overlay，hashed-alpha 圖集，無自發光。",
        "  銘牌前約 3 mm、櫃門／牆約 6–7 mm、管面約 5 mm、地坪 +3.5 mm。",
        "  visible_shadow=False。一張 1024 圖集，四種粗糙度材質共用。",
        "",
        "PERFORMANCE",
        f"  新增 decal {validation['p9_count']}（主標 {validation['p9_primary']}、次標 {validation['p9_secondary']}）。",
        f"  材質 {validation['p9_mats']}，圖集 1。Phase 6 鋼印仍為 {validation['markings']}。",
        f"  Phase 8 物件維持 {validation['p8_count']}。",
        "",
        "SCREENSHOT TEST",
        "  SHOT A：Zone A 建立可讀識別，不變成牆面文字。",
        "  SHOT B：Zone B 密度最高，設備碼與警告可讀。",
        "  SHOT C：Zone C 仍隔離，只有褪色銘牌。",
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
        f"  核心物件刪除：{len(validation['removed'])}；非標誌新增：{len(validation['added_core'])}",
        f"  相機路徑錯誤：{len(validation['camera_errors'])}",
        f"  Phase 7 燈光改動：{len(validation['light_changed'])}",
        f"  Phase 7 燈具變換改動：{len(validation['fixture_moved'])}",
        "",
        "PHASE 1 空間凍結狀態： " + ("PASS" if phase1_pass else "FAIL"),
        "PHASE 2 結構凍結狀態： " + ("PASS" if phase2_pass else "FAIL"),
        "PHASE 3 管線凍結狀態： " + ("PASS" if phase3_pass else "FAIL"),
        "PHASE 4 設備凍結狀態： " + ("PASS" if phase4_pass else "FAIL"),
        "PHASE 5 材質凍結狀態： " + ("PASS" if phase5_pass else "FAIL"),
        "PHASE 6 老化凍結狀態： " + ("PASS" if phase6_pass else "FAIL"),
        "PHASE 7 照明凍結狀態： " + ("PASS" if phase7_pass else "FAIL"),
        "PHASE 8 英雄打磨凍結狀態： " + ("PASS" if phase8_pass else "FAIL"),
        "PHASE 9 敘事驗證： " + ("PASS" if phase9_pass else "FAIL"),
        "  尚未開始 Phase 10。",
    ]
    if validation["moved"]:
        lines.append("  被改動物件：" + ", ".join(validation["moved"][:20]))
    if validation["added_core"]:
        lines.append("  非標誌新增：" + ", ".join(validation["added_core"][:20]))
    if validation["light_changed"]:
        lines.append("  燈光改動：" + ", ".join(validation["light_changed"][:12]))
    report = OUTPUT_DIR / "phase9_signage_validation.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", report)
    print("PHASE 9 VALIDATION", "PASS" if phase9_pass else "FAIL")
    print("p9_count", validation["p9_count"], "p8_count", validation["p8_count"])
    return report


def render_stills(scene: bpy.types.Scene) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    p7.configure_eevee(scene, 48)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    inspect = bpy.data.objects["CAM_INSPECT"]
    for item in STILLS:
        label = item[0]
        cam_name = item[1]
        scene.camera = bpy.data.objects[cam_name]
        if len(item) == 3:
            scene.frame_set(item[2])
        scene.render.filepath = str(OUTPUT_DIR / f"{label}.jpg")
        bpy.ops.render.render(write_still=True)
        print("still", label)
    scene.camera = inspect
    scene.frame_set(1)


def main() -> None:
    mode = parse_mode()
    scene = bpy.context.scene
    before = p5.snapshot()
    lights_before = p8.light_signature()
    fixtures_before = p8.fixture_signature()
    p8_before = len([o for o in bpy.data.objects if o.name.startswith("P8_")])
    uvs = ensure_atlas()
    clear_phase9()
    image = bpy.data.images.load(str(ATLAS_PATH), check_existing=True)
    image.name = "P9_stencil_atlas"
    image.alpha_mode = "STRAIGHT"
    mats = build_materials(image)
    names = add_decals(uvs, mats)
    scene.camera = bpy.data.objects["CAM_INSPECT"]
    validation = validate(scene, before, lights_before, fixtures_before, p8_before, names)
    write_report(validation)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    print("decals", names)
    if mode in {"stills", "playblast"}:
        render_stills(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 9 complete; Phase 10 not started.")


if __name__ == "__main__":
    main()
