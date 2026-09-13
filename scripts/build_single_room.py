#!/usr/bin/env python3
"""Build a small single bedroom with an IKEA VITVAL-style loft bed."""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "single_room.blend"
RENDER_DIR = ROOT / "renders"


def rgb(r, g, b, a=1.0):
    return (r, g, b, a)


# Neutral palette from the reference image.
WALL = rgb(0.93, 0.92, 0.88)
CEILING = rgb(0.98, 0.97, 0.94)
FLOOR = rgb(0.60, 0.42, 0.25)
FLOOR_LIGHT = rgb(0.72, 0.55, 0.36)
METAL = rgb(0.12, 0.13, 0.13)
METAL_HIGHLIGHT = rgb(0.22, 0.23, 0.22)
TEXTILE = rgb(0.58, 0.60, 0.58)
MATTRESS = rgb(0.88, 0.87, 0.81)
PILLOW = rgb(0.95, 0.94, 0.88)
DESK = rgb(0.88, 0.87, 0.82)
WOOD = rgb(0.36, 0.20, 0.10)
GLASS = rgb(0.12, 0.27, 0.40)
CURTAIN = rgb(0.25, 0.28, 0.34)
CURTAIN_LIGHT = rgb(0.72, 0.72, 0.70)
GREEN = rgb(0.14, 0.25, 0.15)
BRASS = rgb(0.45, 0.30, 0.12)


def parse_args():
    args = {"view": "front", "samples": 48, "render": True}
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    i = 0
    while i < len(argv):
        if argv[i] == "--view" and i + 1 < len(argv):
            args["view"] = argv[i + 1]
            i += 1
        elif argv[i] == "--samples" and i + 1 < len(argv):
            args["samples"] = int(argv[i + 1])
            i += 1
        elif argv[i] == "--no-render":
            args["render"] = False
        i += 1
    return args


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.cameras, bpy.data.lights, bpy.data.collections):
        for item in list(datablocks):
            try:
                datablocks.remove(item)
            except Exception:
                pass


def collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def make_mat(name, color, roughness=0.55, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def make_window_mat():
    mat = make_mat("WindowGlass", GLASS, 0.12, 0.05)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Transmission Weight"].default_value = 0.18
        bsdf.inputs["IOR"].default_value = 1.45
    return mat


def add_box(name, center, dims, coll, mat=None, rotation=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    obj.location = center
    obj.dimensions = dims
    if rotation:
        obj.rotation_euler = rotation
    if mat:
        obj.data.materials.append(mat)
    return obj


def add_cylinder(name, center, radius, depth, coll, mat=None, vertices=24, rotation=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=center)
    obj = bpy.context.object
    obj.name = name
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    if rotation:
        obj.rotation_euler = rotation
    if mat:
        obj.data.materials.append(mat)
    return obj


def beam(name, p0, p1, thickness, coll, mat):
    p0, p1 = Vector(p0), Vector(p1)
    direction = p1 - p0
    obj = add_box(name, tuple((p0 + p1) / 2), (thickness, thickness, direction.length), coll, mat)
    obj.rotation_euler = Vector((0, 0, 1)).rotation_difference(direction.normalized()).to_euler()
    return obj


def add_textured_floor(coll, mats):
    add_box("Floor", (0, 0, -0.06), (7.2, 6.0, 0.12), coll, mats["floor"])
    # Wide wood boards running toward the window.
    for i, x in enumerate([-3.0, -2.25, -1.5, -0.75, 0, 0.75, 1.5, 2.25, 3.0]):
        board = add_box(f"FloorBoard{i}", (x, 0, 0.015), (0.72, 5.92, 0.025), coll, mats["floor_light"])
        board.rotation_euler[2] = math.radians(random.Random(i).uniform(-0.6, 0.6))


def add_window(coll, mats):
    # Back wall is y=2.8, window faces the camera.
    add_box("WindowFrameTop", (0, 2.73, 3.25), (4.25, 0.12, 0.12), coll, mats["metal"])
    add_box("WindowFrameBottom", (0, 2.73, 0.45), (4.25, 0.12, 0.12), coll, mats["metal"])
    add_box("WindowFrameLeft", (-2.06, 2.73, 1.85), (0.12, 0.12, 2.85), coll, mats["metal"])
    add_box("WindowFrameRight", (2.06, 2.73, 1.85), (0.12, 0.12, 2.85), coll, mats["metal"])
    add_box("WindowMullionV", (0, 2.70, 1.85), (0.09, 0.08, 2.65), coll, mats["metal"])
    add_box("WindowMullionH", (0, 2.70, 1.85), (4.05, 0.08, 0.09), coll, mats["metal"])
    add_box("WindowGlass", (0, 2.77, 1.85), (4.0, 0.03, 2.65), coll, mats["glass"])
    # Curtains: heavy panels at sides and a light center layer.
    for i, x in enumerate([-2.58, -2.28, 2.28, 2.58]):
        add_box(f"CurtainDark{i}", (x, 2.58, 2.0), (0.38, 0.08, 3.1), coll, mats["curtain"])
    add_box("CurtainSheerL", (-1.55, 2.55, 2.0), (0.42, 0.06, 3.1), coll, mats["sheer"])
    add_box("CurtainSheerR", (1.55, 2.55, 2.0), (0.42, 0.06, 3.1), coll, mats["sheer"])
    add_box("CurtainRod", (0, 2.45, 3.30), (5.7, 0.08, 0.08), coll, mats["metal_high"])
    # Exterior blue panel seen through the window.
    add_box("WindowView", (0, 2.88, 1.85), (3.85, 0.03, 2.55), coll, mats["view"])


def add_room(coll, mats):
    add_textured_floor(coll, mats)
    add_box("BackWall", (0, 2.95, 1.75), (7.0, 0.18, 3.5), coll, mats["wall"])
    add_box("LeftWall", (-3.55, 0.0, 1.75), (0.18, 5.9, 3.5), coll, mats["wall"])
    add_box("RightWall", (3.55, 0.0, 1.75), (0.18, 5.9, 3.5), coll, mats["wall"])
    add_box("Ceiling", (0, 0, 3.55), (7.0, 5.9, 0.18), coll, mats["ceiling"])
    add_window(coll, mats)


def add_bed(coll, mats):
    # VITVAL-like loft bed: charcoal steel square-tube frame with textile guard panels.
    x0, x1 = -2.95, 1.15
    y0, y1 = -0.95, 1.45
    z_floor, z_bed = 0.08, 2.05
    post_t = 0.12
    for i, (x, y) in enumerate([(x0, y0), (x0, y1), (x1, y0), (x1, y1)]):
        add_box(f"BedPost{i}", (x, y, (z_floor + z_bed) / 2), (post_t, post_t, z_bed - z_floor), coll, mats["metal"])
        add_box(f"BedFoot{i}", (x, y, 0.075), (0.24, 0.24, 0.1), coll, mats["metal_high"])
    # Long rails and mattress support.
    add_box("BedRailFront", ((x0 + x1) / 2, y0, z_bed), (x1 - x0, 0.12, 0.16), coll, mats["metal"])
    add_box("BedRailBack", ((x0 + x1) / 2, y1, z_bed), (x1 - x0, 0.12, 0.16), coll, mats["metal"])
    add_box("BedRailLeft", (x0, (y0 + y1) / 2, z_bed), (0.12, y1 - y0, 0.16), coll, mats["metal"])
    add_box("BedRailRight", (x1, (y0 + y1) / 2, z_bed), (0.12, y1 - y0, 0.16), coll, mats["metal"])
    for i in range(8):
        x = x0 + 0.22 + i * (x1 - x0 - 0.44) / 7
        add_box(f"BedSlat{i}", (x, (y0 + y1) / 2, z_bed + 0.055), (0.055, y1 - y0 - 0.16, 0.06), coll, mats["metal_high"])
    # Foam mattress, fitted sheet, blanket and pillow.
    add_box("Mattress", ((x0 + x1) / 2, (y0 + y1) / 2, z_bed + 0.22), (x1 - x0 - 0.2, y1 - y0 - 0.18, 0.33), coll, mats["mattress"])
    add_box("Blanket", (x0 + 1.25, y0 + 0.03, z_bed + 0.405), (1.55, y1 - y0 - 0.22, 0.06), coll, mats["textile"])
    add_box("Pillow", (x0 + 0.55, (y0 + y1) / 2, z_bed + 0.43), (0.78, 1.0, 0.17), coll, mats["pillow"])
    # Guard rails and the signature white VITVAL textile side panel.
    rail_z0, rail_z1 = z_bed + 0.28, z_bed + 0.82
    for y, label in [(y0, "Front"), (y1, "Back")]:
        add_box(f"GuardTop{label}", ((x0 + x1) / 2, y, rail_z1), (x1 - x0, 0.09, 0.09), coll, mats["metal"])
        add_box(f"GuardMid{label}", ((x0 + x1) / 2, y, rail_z0 + 0.12), (x1 - x0, 0.06, 0.06), coll, mats["metal_high"])
        add_box(f"GuardTextile{label}", ((x0 + x1) / 2, y + (0.035 if y == y0 else -0.035), (rail_z0 + rail_z1) / 2), (x1 - x0 - 0.22, 0.035, rail_z1 - rail_z0 - 0.08), coll, mats["textile"])
    # Head/foot end rails.
    for x, label in [(x0, "Head"), (x1, "Foot")]:
        add_box(f"EndTop{label}", (x, (y0 + y1) / 2, rail_z1), (0.09, y1 - y0, 0.09), coll, mats["metal"])


def add_ladder(coll, mats):
    # Slanted VITVAL-style ladder at the front-right corner.
    p0a, p1a = (1.46, -1.05, 0.08), (0.98, -0.62, 2.0)
    p0b, p1b = (2.04, -1.05, 0.08), (1.56, -0.62, 2.0)
    beam("LadderRailL", p0a, p1a, 0.12, coll, mats["metal"])
    beam("LadderRailR", p0b, p1b, 0.12, coll, mats["metal"])
    for i in range(6):
        t = (i + 0.5) / 6
        a = Vector(p0a).lerp(Vector(p0b), 0) + (Vector(p1a) - Vector(p0a)) * t
        b = Vector(p0b) + (Vector(p1b) - Vector(p0b)) * t
        beam(f"LadderStep{i}", tuple(a), tuple(b), 0.09, coll, mats["metal_high"])


def add_desk(coll, mats):
    # White work desk beneath loft.
    add_box("DeskTop", (-1.92, -0.32, 0.98), (1.55, 1.05, 0.12), coll, mats["desk"])
    add_box("DeskSideL", (-2.62, -0.32, 0.50), (0.10, 0.92, 0.95), coll, mats["desk"])
    add_box("DeskSideR", (-1.22, -0.32, 0.50), (0.10, 0.92, 0.95), coll, mats["desk"])
    add_box("DeskBack", (-1.92, 0.08, 0.52), (1.45, 0.08, 0.88), coll, mats["desk"])
    # Monitor/laptop and lamp.
    add_box("Monitor", (-1.94, -0.83, 1.42), (0.78, 0.06, 0.48), coll, mats["metal"])
    add_box("MonitorStand", (-1.94, -0.80, 1.18), (0.08, 0.08, 0.25), coll, mats["metal_high"])
    add_box("Laptop", (-2.36, -0.78, 1.12), (0.46, 0.32, 0.04), coll, mats["metal"])
    add_cylinder("DeskLampStem", (-1.32, -0.72, 1.34), 0.025, 0.38, coll, mats["metal"], 12, rotation=(0, math.radians(-18), 0))
    add_cylinder("DeskLampShade", (-1.25, -0.72, 1.54), 0.11, 0.12, coll, mats["brass"], 20)
    # Small drawer pulls.
    for z in (0.42, 0.67):
        add_box(f"DrawerPull{z}", (-2.62, -0.80, z), (0.22, 0.03, 0.03), coll, mats["metal"])


def add_chair_and_decor(coll, mats):
    # Simple wood chair in front of the desk.
    add_box("ChairSeat", (-0.8, -1.02, 0.52), (0.72, 0.65, 0.10), coll, mats["wood"])
    for x in (-1.08, -0.52):
        for y in (-1.25, -0.80):
            beam(f"ChairLeg{x}{y}", (x, y, 0.05), (x, y, 0.50), 0.06, coll, mats["wood"])
    add_box("ChairBack", (-0.8, -1.30, 0.93), (0.72, 0.08, 0.75), coll, mats["wood"])
    # Hanging egg-chair silhouette on the right, matching the reference mood.
    add_cylinder("HangingChairHook", (2.35, 1.0, 3.08), 0.025, 0.55, coll, mats["metal"], 12)
    add_cylinder("HangingChairRing", (2.35, 1.0, 2.20), 0.68, 0.06, coll, mats["metal_high"], 32, rotation=(math.radians(90), 0, 0))
    add_box("HangingChairSeat", (2.35, 0.70, 1.55), (0.95, 0.72, 0.14), coll, mats["wood"])
    for i in range(6):
        a = math.radians(-68 + i * 27)
        p0 = (2.35 + math.cos(a) * 0.62, 1.0 + math.sin(a) * 0.62, 2.20)
        p1 = (2.35 + math.cos(a) * 0.42, 0.72 + math.sin(a) * 0.42, 1.56)
        beam(f"ChairStrap{i}", p0, p1, 0.035, coll, mats["metal_high"])
    # A framed minimal picture.
    add_box("PictureFrame", (2.72, 2.82, 2.58), (0.62, 0.05, 0.88), coll, mats["wood"])
    add_box("Picture", (2.72, 2.78, 2.58), (0.52, 0.025, 0.78), coll, mats["sheer"])


def add_plants(coll, mats):
    # Small plant on a shelf near the window.
    add_box("Shelf", (1.95, 2.54, 0.95), (0.72, 0.28, 0.07), coll, mats["wood"])
    add_cylinder("PlantPot", (1.95, 2.42, 1.18), 0.13, 0.22, coll, mats["brass"], 20)
    for i in range(7):
        a = math.radians(i * 51)
        beam("PlantLeaf" + str(i), (1.95, 2.42, 1.28), (1.95 + math.cos(a) * 0.23, 2.42 + math.sin(a) * 0.23, 1.65 + 0.08 * math.sin(a)), 0.028, coll, mats["green"])


def add_world_and_lights():
    world = bpy.data.worlds.new("RoomWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.18, 0.25, 0.34, 1)
        bg.inputs["Strength"].default_value = 0.42
    key = bpy.data.lights.new("WindowDaylight", "AREA")
    key.energy = 850
    key.size = 4.2
    key.color = (0.82, 0.90, 1.0)
    key_obj = bpy.data.objects.new("WindowDaylight", key)
    key_obj.location = (0, -0.5, 3.0)
    key_obj.rotation_euler = (math.radians(32), 0, math.radians(180))
    bpy.context.scene.collection.objects.link(key_obj)
    fill = bpy.data.lights.new("WarmRoomFill", "AREA")
    fill.energy = 500
    fill.size = 5.0
    fill.color = (1.0, 0.72, 0.48)
    fill_obj = bpy.data.objects.new("WarmRoomFill", fill)
    fill_obj.location = (-2.2, -2.0, 2.8)
    fill_obj.rotation_euler = (math.radians(22), 0, math.radians(-30))
    bpy.context.scene.collection.objects.link(fill_obj)


def add_camera(view):
    cam = bpy.data.cameras.new("Camera")
    cam.lens = 39 if view == "front" else 30
    cam.sensor_width = 36
    obj = bpy.data.objects.new("Camera", cam)
    if view == "front":
        obj.location = (0.0, -9.2, 2.18)
        target = Vector((0, 0.65, 1.58))
    else:
        obj.location = (2.6, -8.0, 2.35)
        target = Vector((0.1, 0.65, 1.55))
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.scene.camera = obj


def setup_render(args):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(RENDER_DIR / f"single_room_{args['view']}.png")
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.35
    if hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = max(32, args["samples"])
    if hasattr(scene.eevee, "use_raytracing"):
        scene.eevee.use_raytracing = True


def main():
    args = parse_args()
    RENDER_DIR.mkdir(exist_ok=True)
    clear_scene()
    room = collection("Room")
    furniture = collection("Furniture")
    mats = {
        "wall": make_mat("WarmWhiteWall", WALL, 0.8),
        "ceiling": make_mat("Ceiling", CEILING, 0.9),
        "floor": make_mat("WoodFloor", FLOOR, 0.72),
        "floor_light": make_mat("WoodBoard", FLOOR_LIGHT, 0.68),
        "metal": make_mat("VITVALCharcoal", METAL, 0.3, 0.5),
        "metal_high": make_mat("SteelEdges", METAL_HIGHLIGHT, 0.24, 0.65),
        "textile": make_mat("VITVALTextile", TEXTILE, 0.88),
        "mattress": make_mat("Mattress", MATTRESS, 0.95),
        "pillow": make_mat("Pillow", PILLOW, 0.95),
        "desk": make_mat("DeskWhite", DESK, 0.65),
        "wood": make_mat("ChairWood", WOOD, 0.55),
        "glass": make_window_mat(),
        "view": make_mat("WindowView", GLASS, 0.32),
        "curtain": make_mat("SlateCurtain", CURTAIN, 0.9),
        "sheer": make_mat("SheerCurtain", CURTAIN_LIGHT, 0.95),
        "green": make_mat("PlantGreen", GREEN, 0.8),
        "brass": make_mat("Brass", BRASS, 0.32, 0.5),
    }
    add_room(room, mats)
    add_bed(furniture, mats)
    add_ladder(furniture, mats)
    add_desk(furniture, mats)
    add_chair_and_decor(furniture, mats)
    add_plants(furniture, mats)
    add_world_and_lights()
    add_camera(args["view"])
    setup_render(args)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print("Saved", BLEND_PATH)
    if args["render"]:
        bpy.ops.render.render(write_still=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
        print("Rendered", bpy.context.scene.render.filepath)


if __name__ == "__main__":
    main()
