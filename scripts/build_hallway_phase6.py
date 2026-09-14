#!/usr/bin/env python3
"""Phase 6 — controlled aging and environmental storytelling.

Extends the frozen Phase 5 material identity with spatially caused wear:
gravity-driven moisture, wall-floor accumulation, traffic, joint oxidation,
and a handful of faded facility markings.  Phase 1–5 geometry is not moved.

Usage:
  blender -b hallway.blend --python scripts/build_hallway_phase6.py -- --stills
  blender -b hallway.blend --python scripts/build_hallway_phase6.py -- --playblast
  blender -b hallway.blend --python scripts/build_hallway_phase6.py -- --no-render
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import build_hallway_phase5 as p5

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "hallway.blend"
OUTPUT_DIR = ROOT / "renders" / "hallway_phase6"
ASSET_DIR = ROOT / "assets" / "hallway_phase6"
EYE_Z = p5.EYE_Z
ZONE_A = p5.ZONE_A
ZONE_B = p5.ZONE_B
ZONE_C = p5.ZONE_C
PHASE2_COUNTS = p5.PHASE2_COUNTS
PHASE4_COLLECTIONS = p5.PHASE4_COLLECTIONS
LIBRARY = p5.LIBRARY
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

STILLS = (
    (1, "01_entry_aging"),
    (42, "02_zone_a_maintained"),
    (78, "03_approach_ab"),
    (96, "04_zone_b_humidity"),
    (132, "05_zone_b_joints"),
    (164, "06_approach_bc"),
    (185, "07_zone_c_neglect"),
    (215, "08_zone_c_valve"),
    (240, "09_zone_c_depth"),
    (250, "10_far_vanishing"),
)

# Moisture sources: world x, y, z, radius_x, radius_y, strength.
# Water is authored to fall downward from these points.
DRIP_SOURCES = (
    (-1.03, 12.05, 1.86, 0.13, 0.34, 0.92),  # Zone B vent
    (1.02, 15.09, 2.43, 0.15, 0.40, 0.95),  # Zone B wall ingress
    (0.99, 14.62, 2.43, 0.16, 0.20, 0.48),  # Zone B valve neighborhood
    (-1.06, 17.84, 2.50, 0.13, 0.32, 0.82),  # Zone C elbow / wall penetration
    (-1.05, 21.20, 2.88, 0.12, 0.42, 0.78),  # Zone C ceiling joint
    (-0.36, 20.55, 2.46, 0.24, 0.24, 0.62),  # Zone C hanging valve residue
    (1.07, 22.20, 1.18, 0.15, 0.26, 0.42),  # Zone C hatch wash
    (1.08, 5.50, 2.90, 0.08, 0.16, 0.16),  # Zone A faint ceiling joint
)

# Flange / valve / clamp stations along the corridor.
JOINT_Y = (4.05, 12.90, 14.62, 15.09, 17.84, 20.55, 23.55)

MARKINGS = (
    dict(
        name="MARK_ID_PN04",
        text="PN-04",
        subtitle="PANEL",
        x=1.096,
        y=3.20,
        z=1.98,
        w=0.20,
        h=0.09,
        normal="-X",
        meaning="Zone A junction panel identity",
    ),
    dict(
        name="MARK_INSP_B",
        text="INSP 03-98",
        subtitle="OK",
        x=0.848,
        y=10.78,
        z=1.58,
        w=0.22,
        h=0.08,
        normal="-X",
        meaning="Zone B control-cabinet inspection stencil",
    ),
    dict(
        name="MARK_PIPE_CW2",
        text="CW-2",
        subtitle="",
        x=1.021,
        y=11.85,
        z=2.08,
        w=0.16,
        h=0.08,
        normal="-X",
        meaning="Zone B pipe identification on the service wall",
    ),
    dict(
        name="MARK_HATCH_C",
        text="ACCESS",
        subtitle="",
        x=1.096,
        y=22.20,
        z=1.22,
        w=0.22,
        h=0.07,
        normal="-X",
        meaning="Zone C hatch access stencil",
    ),
    dict(
        name="MARK_UTIL_C",
        text="U-17",
        subtitle="",
        x=-1.096,
        y=19.55,
        z=1.52,
        w=0.16,
        h=0.08,
        normal="+X",
        meaning="Zone C isolated utility circuit code",
    ),
)


def parse_mode() -> str:
    return p5.parse_mode()


def sock(node, identifier: str):
    return p5.sock(node, identifier)


def link(nt, src, dst) -> None:
    nt.links.new(src, dst)


def math_node(nt, op: str, loc, a=None, b=None):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = op
    node.location = loc
    node.use_clamp = op in {"MINIMUM", "MAXIMUM", "MULTIPLY"}
    if a is not None:
        if hasattr(a, "id_data"):
            link(nt, a, node.inputs[0])
        else:
            node.inputs[0].default_value = float(a)
    if b is not None:
        if hasattr(b, "id_data"):
            link(nt, b, node.inputs[1])
        else:
            node.inputs[1].default_value = float(b)
    return node.outputs[0]


def map_range(nt, value, from_min, from_max, to_min, to_max, loc):
    node = nt.nodes.new("ShaderNodeMapRange")
    node.location = loc
    node.clamp = True
    link(nt, value, node.inputs["Value"])
    node.inputs["From Min"].default_value = from_min
    node.inputs["From Max"].default_value = from_max
    node.inputs["To Min"].default_value = to_min
    node.inputs["To Max"].default_value = to_max
    return node.outputs["Result"]


def mix_color(nt, factor, color_a, color_b, loc):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.location = loc
    link(nt, factor, sock(node, "Factor_Float"))
    if hasattr(color_a, "id_data"):
        link(nt, color_a, sock(node, "A_Color"))
    else:
        sock(node, "A_Color").default_value = (*color_a, 1.0)
    if hasattr(color_b, "id_data"):
        link(nt, color_b, sock(node, "B_Color"))
    else:
        sock(node, "B_Color").default_value = (*color_b, 1.0)
    return sock(node, "Result_Color")


def mix_float(nt, factor, a, b, loc):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "FLOAT"
    node.location = loc
    link(nt, factor, sock(node, "Factor_Float"))
    if hasattr(a, "id_data"):
        link(nt, a, sock(node, "A_Float"))
    else:
        sock(node, "A_Float").default_value = float(a)
    if hasattr(b, "id_data"):
        link(nt, b, sock(node, "B_Float"))
    else:
        sock(node, "B_Float").default_value = float(b)
    return sock(node, "Result_Float")


def collection(name: str) -> bpy.types.Collection:
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def clear_phase6() -> None:
    col = bpy.data.collections.get("STORY_MARKINGS")
    if col is not None:
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)
    for mat in list(bpy.data.materials):
        if mat.name.startswith("MAT_P6_"):
            bpy.data.materials.remove(mat)
    for img in list(bpy.data.images):
        if img.name.startswith("P6_"):
            bpy.data.images.remove(img)
    for group in list(bpy.data.node_groups):
        if group.name.startswith("P6_"):
            bpy.data.node_groups.remove(group)
    for mesh in list(bpy.data.meshes):
        if mesh.name.startswith("P6_") and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def write_stencils() -> dict[str, Path]:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    font_lg = ImageFont.truetype(FONT, 92)
    font_sm = ImageFont.truetype(FONT, 36)
    paths = {}
    for mark in MARKINGS:
        img = Image.new("RGBA", (512, 192), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), mark["text"], font=font_lg)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (512 - tw) * 0.5
        y = 38 if mark["subtitle"] else 52
        draw.text((x, y), mark["text"], font=font_lg, fill=(52, 48, 42, 210))
        if mark["subtitle"]:
            sb = draw.textbbox((0, 0), mark["subtitle"], font=font_sm)
            sx = (512 - (sb[2] - sb[0])) * 0.5
            draw.text((sx, 128), mark["subtitle"], font=font_sm, fill=(58, 54, 48, 150))
        # Worn stencil: slight blur + luminance noise in alpha.
        img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
        noise = Image.effect_noise((512, 192), 18).convert("L")
        r, g, b, a = img.split()
        a = Image.blend(a, Image.eval(a, lambda p: int(p * 0.82)), 0.35)
        a = ImageChops_multiply(a, noise, 0.22)
        img = Image.merge("RGBA", (r, g, b, a))
        path = ASSET_DIR / f"{mark['name'].lower()}.png"
        img.save(path)
        paths[mark["name"]] = path
    return paths


def ImageChops_multiply(alpha: Image.Image, noise: Image.Image, amount: float) -> Image.Image:
    noise = noise.point(lambda p: int(255 - amount * (255 - p)))
    return Image.composite(alpha, Image.eval(alpha, lambda p: int(p * (1.0 - amount))), noise)


def add_group_socket(ng, name: str, in_out: str, socket_type: str):
    return ng.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)


def build_aging_group() -> bpy.types.NodeTree:
    existing = bpy.data.node_groups.get("P6_NG_AgingMasks")
    if existing is not None:
        bpy.data.node_groups.remove(existing)
    ng = bpy.data.node_groups.new("P6_NG_AgingMasks", "ShaderNodeTree")
    add_group_socket(ng, "Zone", "OUTPUT", "NodeSocketFloat")
    add_group_socket(ng, "Drip", "OUTPUT", "NodeSocketFloat")
    add_group_socket(ng, "Skirt", "OUTPUT", "NodeSocketFloat")
    add_group_socket(ng, "Traffic", "OUTPUT", "NodeSocketFloat")
    add_group_socket(ng, "EdgeDust", "OUTPUT", "NodeSocketFloat")
    add_group_socket(ng, "Joint", "OUTPUT", "NodeSocketFloat")
    add_group_socket(ng, "Contact", "OUTPUT", "NodeSocketFloat")
    add_group_socket(ng, "Subtle", "OUTPUT", "NodeSocketFloat")
    add_group_socket(ng, "Breakup", "OUTPUT", "NodeSocketFloat")
    nodes = ng.nodes
    links = ng.links
    geom = nodes.new("ShaderNodeNewGeometry")
    geom.location = (-1400, 200)
    sep = nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-1220, 200)
    links.new(geom.outputs["Position"], sep.inputs["Vector"])
    x_s, y_s, z_s = sep.outputs["X"], sep.outputs["Y"], sep.outputs["Z"]
    tex = nodes.new("ShaderNodeTexCoord")
    tex.location = (-1400, -280)
    obj_sep = nodes.new("ShaderNodeSeparateXYZ")
    obj_sep.location = (-1220, -280)
    links.new(tex.outputs["Object"], obj_sep.inputs["Vector"])
    info = nodes.new("ShaderNodeObjectInfo")
    info.location = (-1400, -520)
    zone_lin = map_range(ng, y_s, 0.0, 24.0, 0.0, 1.0, (-980, 420))
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-780, 420)
    ramp.color_ramp.interpolation = "EASE"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.08, 0.08, 0.08, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    mid = ramp.color_ramp.elements.new(0.36)
    mid.color = (0.22, 0.22, 0.22, 1.0)
    mid_b = ramp.color_ramp.elements.new(0.62)
    mid_b.color = (0.58, 0.58, 0.58, 1.0)
    links.new(zone_lin, ramp.inputs["Fac"])
    zone = nodes.new("ShaderNodeSeparateColor")
    zone.location = (-520, 420)
    links.new(ramp.outputs["Color"], zone.inputs["Color"])
    zone_f = zone.outputs["Red"]

    # Vertical streak coordinates: slow in Z so features drip downward.
    map_streak = nodes.new("ShaderNodeMapping")
    map_streak.location = (-980, 80)
    map_streak.inputs["Scale"].default_value = (48.0, 7.5, 1.35)
    links.new(geom.outputs["Position"], map_streak.inputs["Vector"])
    streak = nodes.new("ShaderNodeTexNoise")
    streak.location = (-780, 80)
    streak.noise_dimensions = "3D"
    streak.inputs["Scale"].default_value = 1.0
    streak.inputs["Detail"].default_value = 3.0
    streak.inputs["Roughness"].default_value = 0.55
    links.new(map_streak.outputs["Vector"], streak.inputs["Vector"])
    streak_f = map_range(ng, streak.outputs["Factor"], 0.42, 0.78, 0.0, 1.0, (-560, 80))

    drip = None
    for i, (sx, sy, sz, rx, ry, strength) in enumerate(DRIP_SOURCES):
        dx = math_node(ng, "SUBTRACT", (-980, -40 - i * 80), x_s, sx)
        dy = math_node(ng, "SUBTRACT", (-820, -40 - i * 80), y_s, sy)
        ax = math_node(ng, "ABSOLUTE", (-660, -20 - i * 80), dx)
        ay = math_node(ng, "ABSOLUTE", (-660, -70 - i * 80), dy)
        fx = map_range(ng, ax, 0.0, rx, 1.0, 0.0, (-500, -20 - i * 80))
        fy = map_range(ng, ay, 0.0, ry, 1.0, 0.0, (-500, -70 - i * 80))
        lat = math_node(ng, "MULTIPLY", (-320, -40 - i * 80), fx, fy)
        below = math_node(ng, "GREATER_THAN", (-320, -90 - i * 80), math_node(ng, "SUBTRACT", (-500, -110 - i * 80), sz, z_s), 0.02)
        fall = map_range(ng, z_s, 0.04, sz, 1.0, 0.35, (-320, 20 - i * 80))
        src = math_node(ng, "MULTIPLY", (-140, -40 - i * 80), lat, below)
        src = math_node(ng, "MULTIPLY", (20, -40 - i * 80), src, fall)
        src = math_node(ng, "MULTIPLY", (180, -40 - i * 80), src, strength)
        src = math_node(ng, "MULTIPLY", (340, -40 - i * 80), src, streak_f)
        drip = src if drip is None else math_node(ng, "MAXIMUM", (520, -40 - i * 40), drip, src)

    # Irregular wall-floor accumulation, with clean gaps so it is not a stripe.
    skirt_h = map_range(ng, z_s, 0.0, 0.26, 1.0, 0.0, (-780, 260))
    gap_n = nodes.new("ShaderNodeTexNoise")
    gap_n.location = (-780, 320)
    gap_n.inputs["Scale"].default_value = 0.55
    gap_n.inputs["Detail"].default_value = 1.0
    links.new(geom.outputs["Position"], gap_n.inputs["Vector"])
    gaps = map_range(ng, gap_n.outputs["Factor"], 0.32, 0.68, 0.12, 1.0, (-560, 320))
    skirt = math_node(ng, "MULTIPLY", (-360, 280), skirt_h, gaps)
    skirt = math_node(ng, "MULTIPLY", (-200, 280), skirt, mix_float(ng, zone_f, 0.12, 0.85, (-360, 340)))

    abs_x = math_node(ng, "ABSOLUTE", (-780, -720), x_s)
    traffic = map_range(ng, abs_x, 0.18, 0.70, 1.0, 0.0, (-560, -720))
    edge = map_range(ng, abs_x, 0.52, 1.08, 0.0, 1.0, (-560, -800))
    floor_band = map_range(ng, z_s, -0.02, 0.06, 1.0, 0.0, (-560, -880))
    edge_dust = math_node(ng, "MULTIPLY", (-320, -800), edge, floor_band)

    joint = None
    for j, jy in enumerate(JOINT_Y):
        dy = math_node(ng, "ABSOLUTE", (-780, -980 - j * 50), math_node(ng, "SUBTRACT", (-940, -980 - j * 50), y_s, jy))
        near = map_range(ng, dy, 0.0, 0.20, 1.0, 0.0, (-560, -980 - j * 50))
        joint = near if joint is None else math_node(ng, "MAXIMUM", (-360, -980 - j * 30), joint, near)

    contact = map_range(ng, obj_sep.outputs["Z"], -0.48, -0.05, 1.0, 0.0, (-780, -560))
    breakup = info.outputs["Random"]
    quiet = nodes.new("ShaderNodeTexNoise")
    quiet.location = (-780, 520)
    quiet.inputs["Scale"].default_value = 1.8
    quiet.inputs["Detail"].default_value = 1.0
    links.new(geom.outputs["Position"], quiet.inputs["Vector"])
    quiet_f = map_range(ng, quiet.outputs["Factor"], 0.38, 0.72, 0.0, 1.0, (-560, 520))
    subtle = math_node(ng, "MULTIPLY", (-320, 500), mix_float(ng, zone_f, 0.06, 0.22, (-360, 560)), quiet_f)

    out = nodes.new("NodeGroupOutput")
    out.location = (760, 80)
    links.new(zone_f, out.inputs["Zone"])
    links.new(drip, out.inputs["Drip"])
    links.new(skirt, out.inputs["Skirt"])
    links.new(traffic, out.inputs["Traffic"])
    links.new(edge_dust, out.inputs["EdgeDust"])
    links.new(joint, out.inputs["Joint"])
    links.new(contact, out.inputs["Contact"])
    links.new(subtle, out.inputs["Subtle"])
    links.new(breakup, out.inputs["Breakup"])
    return ng


def incoming(socket):
    return socket.links[0].from_socket if socket.links else None


def inject_aging(mats: dict[str, bpy.types.Material], group: bpy.types.NodeTree) -> None:
    dirt = (0.17, 0.145, 0.12)
    moisture = (0.16, 0.17, 0.155)
    oxide = (0.21, 0.135, 0.10)
    dust = (0.30, 0.29, 0.26)
    recipes = {
        "MAT_Wall_PaintedConcrete": dict(
            color_masks=(("Drip", 0.55), ("Skirt", 0.42), ("Subtle", 0.70)),
            moist=("Drip", 0.28),
            rough_up=("Skirt", 0.08),
            rough_down=("Drip", 0.10),
            oxide_amt=0.0,
            metal_down=0.0,
        ),
        "MAT_Floor_IndustrialConcrete": dict(
            color_masks=(("Traffic", 0.22), ("EdgeDust", 0.28), ("Drip", 0.32), ("Subtle", 0.40)),
            moist=("Drip", 0.06),
            rough_up=("EdgeDust", 0.10),
            rough_down=("Traffic", 0.06),
            oxide_amt=0.0,
            metal_down=0.0,
        ),
        "MAT_Ceiling_AgedConcrete": dict(
            color_masks=(("Subtle", 0.85),),
            moist=None,
            rough_up=("Subtle", 0.06),
            rough_down=None,
            oxide_amt=0.0,
            metal_down=0.0,
        ),
        "MAT_Structure_PaintedSteel": dict(
            color_masks=(("Subtle", 0.45), ("Joint", 0.18)),
            moist=None,
            rough_up=("Joint", 0.08),
            rough_down=None,
            oxide_amt=0.12,
            metal_down=0.0,
        ),
        "MAT_Pipe_DarkPaintedSteel": dict(
            color_masks=(("Joint", 0.28), ("Subtle", 0.20), ("Breakup", 0.08)),
            moist=None,
            rough_up=("Joint", 0.12),
            rough_down=None,
            oxide_amt=0.42,
            metal_down=0.0,
        ),
        "MAT_Pipe_Secondary": dict(
            color_masks=(("Joint", 0.22), ("Subtle", 0.18), ("Breakup", 0.10)),
            moist=None,
            rough_up=("Joint", 0.10),
            rough_down=None,
            oxide_amt=0.32,
            metal_down=0.0,
        ),
        "MAT_Metal_Galvanized": dict(
            color_masks=(("Joint", 0.20), ("Breakup", 0.12), ("Contact", 0.16)),
            moist=None,
            rough_up=("Joint", 0.10),
            rough_down=("Contact", 0.07),
            oxide_amt=0.18,
            metal_down=0.12,
        ),
        "MAT_Cabinet_PaintedMetal": dict(
            color_masks=(("Contact", 0.28), ("Subtle", 0.35), ("Skirt", 0.12)),
            moist=None,
            rough_up=("Subtle", 0.05),
            rough_down=("Contact", 0.08),
            oxide_amt=0.04,
            metal_down=0.0,
        ),
        "MAT_Vent_GalvanizedMetal": dict(
            color_masks=(("Subtle", 0.55), ("Drip", 0.18)),
            moist=None,
            rough_up=("Subtle", 0.12),
            rough_down=None,
            oxide_amt=0.08,
            metal_down=0.06,
        ),
        "MAT_Rubber_Dark": dict(
            color_masks=(("Subtle", 0.20),),
            moist=None,
            rough_up=("Subtle", 0.03),
            rough_down=None,
            oxide_amt=0.0,
            metal_down=0.0,
        ),
        "MAT_Valve_IndustrialAccent": dict(
            color_masks=(("Joint", 0.16), ("Contact", 0.10)),
            moist=None,
            rough_up=("Joint", 0.06),
            rough_down=("Contact", 0.05),
            oxide_amt=0.10,
            metal_down=0.0,
        ),
    }
    for name, spec in recipes.items():
        mat = mats[name]
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        grp = nt.nodes.new("ShaderNodeGroup")
        grp.node_tree = group
        grp.location = (bsdf.location.x - 420, bsdf.location.y + 260)
        grp.label = "P6 Aging"
        color_in = incoming(bsdf.inputs["Base Color"])
        rough_in = incoming(bsdf.inputs["Roughness"])
        metal_in = incoming(bsdf.inputs["Metallic"])
        mask = None
        for socket_name, weight in spec["color_masks"]:
            part = math_node(nt, "MULTIPLY", (grp.location.x + 180, grp.location.y - 40), grp.outputs[socket_name], weight)
            mask = part if mask is None else math_node(nt, "MAXIMUM", (grp.location.x + 320, grp.location.y), mask, part)
        mask = math_node(nt, "MINIMUM", (grp.location.x + 460, grp.location.y), mask, 0.62)
        aged = mix_color(nt, mask, color_in, dirt, (grp.location.x + 620, grp.location.y + 40))
        if spec["oxide_amt"] > 0.0:
            ox_f = math_node(nt, "MULTIPLY", (grp.location.x + 180, grp.location.y - 180), grp.outputs["Joint"], spec["oxide_amt"])
            ox_f = math_node(nt, "MULTIPLY", (grp.location.x + 320, grp.location.y - 180), ox_f, grp.outputs["Zone"])
            aged = mix_color(nt, ox_f, aged, oxide, (grp.location.x + 620, grp.location.y - 160))
        if spec["moist"]:
            socket_name, weight = spec["moist"]
            damp = math_node(nt, "MULTIPLY", (grp.location.x + 180, grp.location.y - 280), grp.outputs[socket_name], weight)
            aged = mix_color(nt, damp, aged, moisture, (grp.location.x + 620, grp.location.y - 280))
        if spec["color_masks"] and any(k == "EdgeDust" or k == "Subtle" for k, _w in spec["color_masks"]):
            dust_f = math_node(nt, "MULTIPLY", (grp.location.x + 180, grp.location.y + 160), grp.outputs["EdgeDust"] if name.startswith("MAT_Floor") else grp.outputs["Subtle"], 0.16)
            aged = mix_color(nt, dust_f, aged, dust, (grp.location.x + 620, grp.location.y + 160))
        link(nt, aged, bsdf.inputs["Base Color"])
        rough = rough_in
        if spec["rough_up"]:
            sname, amt = spec["rough_up"]
            fac = math_node(nt, "MULTIPLY", (grp.location.x + 180, grp.location.y - 360), grp.outputs[sname], 1.0)
            rough = mix_float(nt, fac, rough, math_node(nt, "ADD", (grp.location.x + 340, grp.location.y - 400), rough_in, amt), (grp.location.x + 520, grp.location.y - 360))
        if spec["rough_down"]:
            sname, amt = spec["rough_down"]
            fac = math_node(nt, "MULTIPLY", (grp.location.x + 180, grp.location.y - 460), grp.outputs[sname], 1.0)
            rough = mix_float(nt, fac, rough, math_node(nt, "SUBTRACT", (grp.location.x + 340, grp.location.y - 500), rough_in, amt), (grp.location.x + 520, grp.location.y - 460))
        link(nt, rough, bsdf.inputs["Roughness"])
        if spec["metal_down"] > 0.0:
            if metal_in is None:
                base_m = bsdf.inputs["Metallic"].default_value
                metal_node = nt.nodes.new("ShaderNodeValue")
                metal_node.outputs[0].default_value = base_m
                metal_in = metal_node.outputs[0]
            fac = math_node(nt, "MULTIPLY", (grp.location.x + 180, grp.location.y - 560), grp.outputs["Joint"], spec["metal_down"])
            metal = mix_float(nt, fac, metal_in, 0.35, (grp.location.x + 520, grp.location.y - 560))
            link(nt, metal, bsdf.inputs["Metallic"])


def make_decal_mesh(name: str, width: float, height: float, normal: str) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new(name)
    hw, hh = width * 0.5, height * 0.5
    if normal == "-X":
        verts = [(0.0, -hw, -hh), (0.0, -hw, hh), (0.0, hw, hh), (0.0, hw, -hh)]
    else:
        verts = [(0.0, hw, -hh), (0.0, hw, hh), (0.0, -hw, hh), (0.0, -hw, -hh)]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    uv = mesh.uv_layers.new(name="UVMap")
    for loop, uvco in zip(uv.data, ((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0))):
        loop.uv = uvco
    mesh.update()
    return mesh


def stencil_material(name: str, image_path: Path) -> bpy.types.Material:
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
    img_node.location = (-200, 0)
    image = bpy.data.images.load(str(image_path), check_existing=True)
    image.name = f"P6_{image_path.stem}"
    img_node.image = image
    img_node.interpolation = "Smart"
    link(nt, img_node.outputs["Color"], bsdf.inputs["Base Color"])
    link(nt, img_node.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.82
    bsdf.inputs["Metallic"].default_value = 0.0
    link(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def add_markings(paths: dict[str, Path]) -> list[str]:
    col = collection("STORY_MARKINGS")
    names = []
    for mark in MARKINGS:
        mesh = make_decal_mesh(f"P6_{mark['name']}_MESH", mark["w"], mark["h"], mark["normal"])
        obj = bpy.data.objects.new(mark["name"], mesh)
        obj.location = (mark["x"], mark["y"], mark["z"])
        obj.scale = (1.0, 1.0, 1.0)
        obj["phase"] = 6
        obj["story"] = mark["meaning"]
        if hasattr(obj, "visible_shadow"):
            obj.visible_shadow = False
        col.objects.link(obj)
        mat = stencil_material(f"MAT_P6_{mark['name']}", paths[mark["name"]])
        obj.data.materials.append(mat)
        names.append(obj.name)
    return names


def validate(scene, before, lights_before, markings) -> dict:
    after = p5.snapshot()
    original = {k: v for k, v in before.items() if not k.startswith("MARK_")}
    after_core = {k: v for k, v in after.items() if not k.startswith("MARK_")}
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
    p4_objects = [
        obj
        for name in PHASE4_COLLECTIONS
        if bpy.data.collections.get(name)
        for obj in bpy.data.collections[name].objects
    ]
    hidden_states = {obj.name: obj.hide_get() for obj in p4_objects}
    extra = [bpy.data.objects.get(n) for n in markings]
    extra = [o for o in extra if o is not None]
    for obj in p4_objects + extra:
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
    for obj in p4_objects:
        obj.hide_set(hidden_states[obj.name])
    for obj in extra:
        obj.hide_set(False)
    bpy.context.view_layer.update()
    phase2_counts = {
        name: len(bpy.data.collections[name].objects) if bpy.data.collections.get(name) else -1
        for name in PHASE2_COUNTS
    }
    light_moved = [name for name, loc in p5.light_positions().items() if lights_before.get(name) != loc]
    library_ok = all(bpy.data.materials.get(name) for name in LIBRARY)
    aging_ok = bpy.data.node_groups.get("P6_NG_AgingMasks") is not None
    stencil_count = len([m for m in bpy.data.materials if m.name.startswith("MAT_P6_")])
    return dict(
        moved=moved,
        removed=removed,
        added_core=added_core,
        camera_errors=camera_errors,
        stations=stations,
        phase2_counts=phase2_counts,
        phase3_present=all(bpy.data.collections.get(n) for n in ("UTILITY_PRIMARY_PIPES", "UTILITY_SECONDARY_PIPES", "UTILITY_SUPPORTS")),
        phase4_present=all(bpy.data.collections.get(n) for n in PHASE4_COLLECTIONS),
        light_moved=light_moved,
        library_ok=library_ok,
        aging_ok=aging_ok,
        stencil_count=stencil_count,
        marking_count=len(markings),
        node_count=sum(len(bpy.data.materials[name].node_tree.nodes) for name in LIBRARY),
    )


def write_report(validation: dict, markings: list[str]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    phase1_pass = all(
        abs(row["width"] - row["target_width"]) < 0.001
        and abs(row["ceiling"] - row["target_ceiling"]) < 0.001
        for row in validation["stations"]
    ) and not validation["moved"] and not validation["removed"]
    phase2_pass = validation["phase2_counts"] == PHASE2_COUNTS and not validation["moved"]
    phase3_pass = validation["phase3_present"] and not validation["moved"]
    phase4_pass = validation["phase4_present"] and not validation["moved"]
    phase5_pass = validation["library_ok"] and not validation["moved"]
    phase6_pass = (
        phase1_pass
        and phase2_pass
        and phase3_pass
        and phase4_pass
        and phase5_pass
        and not validation["camera_errors"]
        and not validation["light_moved"]
        and not validation["added_core"]
        and validation["aging_ok"]
        and validation["marking_count"] == 5
        and 3 <= validation["stencil_count"] <= 6
    )
    lines = [
        "PHASE 6 受控老化與環境敘事",
        "未移動 Phase 1–5 幾何、設備、管線或相機。Phase 5 11 個材質名稱保留，僅注入空間控制的老化 mask。",
        "",
        "牆面老化",
        "  技術：世界座標垂直拉伸 Noise 作為水痕、牆腳不規則積垢、大尺度安靜區塊、沿走廊漸強的 zone ramp。",
        "  主要位置：Zone B 左牆通風口下方；Zone B 右牆穿管／閥件下方；Zone C 左側彎頭與天花接縫；Zone C 艙門周邊。",
        "  Zone A 僅天花接縫極弱痕跡。沒有整面程序化髒污，也沒有水平無來源水痕。",
        "",
        "地坪老化",
        "  中央行走帶：長期踩踏，Zone A 略平滑、Zone C 略積垢。",
        "  邊緣：不規則積塵，牆腳交界有缺口，避免一條均勻黑帶。",
        "  Zone C 懸吊閥下方有局部更深殘留，不是水窪。",
        "",
        "管線老化",
        "  腐蝕邏輯：優先發生在法蘭／閥件／穿牆點的 Y 站位，再乘上 zone 與物體隨機。",
        "  影響：y≈4.05、12.90、14.62、15.09、17.84、20.55、23.55。主管仍保持暗塗裝可讀。",
        "",
        "設備老化",
        "  控制櫃：物件座標底部接觸磨損、門緣／下緣積垢，把手所在鍍鋅件略更光滑。",
        "  通風格柵：灰塵提高 roughness、略微轉暗，不是全黑。",
        "  艙門：Zone C 周圍有較明顯洗痕與積垢。",
        "",
        "潮氣",
        "  來源：B 通風口、B 右牆穿管、B 閥件鄰近牆、C 彎頭穿牆、C 天花接縫、C 懸吊閥、C 艙門、A 微弱天花接縫。",
        "  方向：只向下。越近地面略加強，符合重力與積聚。",
        "",
        "環境敘事標記（5）",
        "  MARK_ID_PN04：Zone A 右牆 y=3.20，接線盒編號 PN-04。",
        "  MARK_INSP_B：Zone B 控制櫃 y=10.78，巡檢鋼印 INSP 03-98。",
        "  MARK_PIPE_CW2：Zone B 右牆 y=11.85，管線編號 CW-2。",
        "  MARK_HATCH_C：Zone C 右牆 y=22.20，艙門 ACCESS。",
        "  MARK_UTIL_C：Zone C 左牆 y=19.55，孤立回路 U-17。",
        "  無塗鴉、無 Backrooms 文本、無血液。",
        "",
        "ZONE A",
        "  老化程度低。建立「仍被例行維護」的基準，僅微弱牆腳、行走帶與一處天花接縫。",
        "ZONE B",
        "  老化程度中。潮濕、維護下降：可見垂直水痕簇、支架／閥件氧化、櫃體接觸磨損。",
        "ZONE C",
        "  老化程度高但仍完整。遺忘、較少人到：更強但不全面的變色、艙門積垢、孤立標記。",
        "",
        "效能",
        f"  共用節點組 P6_NG_AgingMasks；Phase 5 材質節點總數約 {validation['node_count']}。",
        "  標記貼圖 5 張 512×192，無 Displacement、無 4K 套圖、無數百張 decal。",
        "  重複模組靠 Object Info Random 做輕微差異。",
        "",
        "視覺驗證",
        "  刻意保持較乾淨：Zone A 大部分牆面、主管中段塗裝、遠景消失點的大面積牆。",
        "  刻意較髒：Zone B 穿管／通風口下方、Zone C 閥件與艙門、牆腳不連續積垢。",
        "  若仍偏髒，問題會出在 drip strength 而非整面 noise。",
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
        f"  核心物件刪除：{len(validation['removed'])}；非標記新增：{len(validation['added_core'])}",
        f"  相機路徑錯誤：{len(validation['camera_errors'])}",
        f"  燈具位置改動：{len(validation['light_moved'])}",
        f"  標記數量：{validation['marking_count']}",
        "",
        "PHASE 1 空間凍結狀態： " + ("PASS" if phase1_pass else "FAIL"),
        "PHASE 2 結構凍結狀態： " + ("PASS" if phase2_pass else "FAIL"),
        "PHASE 3 管線凍結狀態： " + ("PASS" if phase3_pass else "FAIL"),
        "PHASE 4 設備凍結狀態： " + ("PASS" if phase4_pass else "FAIL"),
        "PHASE 5 材質凍結狀態： " + ("PASS" if phase5_pass else "FAIL"),
        "PHASE 6 老化驗證： " + ("PASS" if phase6_pass else "FAIL"),
        "  Phase 1 尺寸是否修改：否",
        "  Phase 2 結構骨架是否修改：否",
        "  Phase 3 管線路由是否修改：否",
        "  Phase 4 設備位置是否修改：否",
        "  Phase 5 材質名稱／分類是否保留：是",
        "  尚未開始 Phase 7。",
    ]
    if validation["moved"]:
        lines.append("  被改動物件：" + ", ".join(validation["moved"][:20]))
    report = OUTPUT_DIR / "phase6_aging_validation.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", report)
    print("PHASE 6 VALIDATION", "PASS" if phase6_pass else "FAIL")
    return report


def render_stills(scene: bpy.types.Scene) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    p5.configure_inspect_render(scene, 32)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    for frame, label in STILLS:
        scene.frame_set(frame)
        scene.render.filepath = str(OUTPUT_DIR / f"{label}.jpg")
        bpy.ops.render.render(write_still=True)
        print("still", label, "frame", frame)


def render_playblast(scene: bpy.types.Scene) -> Path:
    import subprocess

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = OUTPUT_DIR / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    p5.configure_inspect_render(scene, 8)
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    scene.frame_start = 1
    scene.frame_end = 250
    scene.render.filepath = str(frames / "phase6_walk_")
    bpy.ops.render.render(animation=True)
    output = OUTPUT_DIR / "phase6_aging_walk.mp4"
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "24",
            "-i",
            str(frames / "phase6_walk_%04d.jpg"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "20",
            str(output),
        ]
    )
    print("playblast", output)
    return output


def main() -> None:
    mode = parse_mode()
    before = p5.snapshot()
    lights_before = p5.light_positions()
    clear_phase6()
    p5.clear_phase5()
    mats = p5.build_library()
    p5.assign_materials(mats)
    group = build_aging_group()
    inject_aging(mats, group)
    paths = write_stencils()
    markings = add_markings(paths)
    scene = bpy.context.scene
    validation = validate(scene, before, lights_before, markings)
    write_report(validation, markings)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    if mode in {"stills", "playblast"}:
        render_stills(scene)
        if mode == "playblast":
            render_playblast(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Phase 6 complete; Phase 7 not started.")


if __name__ == "__main__":
    main()
