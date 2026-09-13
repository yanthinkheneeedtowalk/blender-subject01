#!/usr/bin/env python3
"""Build a photoreal-leaning single bedroom with an IKEA VITVAL-style loft bed.

Techniques adapted from Workshop Warrior,
"How I Make Realistic Liminal Spaces in Blender"
https://www.youtube.com/watch?v=lf51pJFHWCA

- Start from a reference photo, then add one extra idea (tilted wardrobe mirror).
- Procedural PBR: color-ramp variation + bump, not flat colors.
- Shoot from inside the room like a real camera.
- Cycles with extra glossy bounces.
- Compositor: slight blur, sharpen, bloom glare, streak glare, film grain.
"""

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


def parse_args():
    args = {"view": "front", "samples": 48, "render": True, "fast": False}
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    i = 0
    while i < len(argv):
        if argv[i] == "--view" and i + 1 < len(argv):
            args["view"] = argv[i + 1]
            i += 1
        elif argv[i] == "--samples" and i + 1 < len(argv):
            args["samples"] = int(argv[i + 1])
            i += 1
        elif argv[i] == "--fast":
            args["fast"] = True
            args["samples"] = 12
        elif argv[i] == "--no-render":
            args["render"] = False
        i += 1
    return args


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.curves,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.collections,
        bpy.data.node_groups,
        bpy.data.images,
    ):
        for item in list(datablocks):
            if getattr(item, "name", "") == "Render Result":
                continue
            try:
                datablocks.remove(item)
            except Exception:
                pass


def collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def link(obj, coll):
    coll.objects.link(obj)
    return obj


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
    for coll_old in list(obj.users_collection):
        coll_old.objects.unlink(obj)
    coll.objects.link(obj)
    if rotation:
        obj.rotation_euler = rotation
    if mat:
        obj.data.materials.append(mat)
    return obj


def beam(name, p0, p1, thickness, coll, mat):
    p0, p1 = Vector(p0), Vector(p1)
    direction = p1 - p0
    obj = add_box(name, tuple((p0 + p1) / 2), (thickness, thickness, max(direction.length, 0.01)), coll, mat)
    obj.rotation_euler = Vector((0, 0, 1)).rotation_difference(direction.normalized()).to_euler()
    return obj


def mix_rgb(nt, fac=0.5):
    node = nt.nodes.new("ShaderNodeMixRGB")
    node.inputs["Fac"].default_value = fac
    return node


def principled(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat, bsdf, nt


def set_bsdf(bsdf, **kwargs):
    mapping = {
        "color": "Base Color",
        "roughness": "Roughness",
        "metallic": "Metallic",
        "specular": "Specular IOR Level",
        "transmission": "Transmission Weight",
        "ior": "IOR",
        "alpha": "Alpha",
        "emission": "Emission Color",
        "emission_strength": "Emission Strength",
    }
    for key, value in kwargs.items():
        bsdf.inputs[mapping[key]].default_value = value


def mat_drywall():
    """Megascans-style drywall: base color + noise variation + faint bump."""
    mat, bsdf, nt = principled("Drywall")
    tex = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (4.5, 4.5, 4.5)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 11.0
    noise.inputs["Roughness"].default_value = 0.55
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.78, 0.76, 0.70, 1)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.93, 0.91, 0.85, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.004
    nt.links.new(tex.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_bsdf(bsdf, roughness=0.78)
    return mat


def mat_wood_floor():
    mat, bsdf, nt = principled("WoodFloor")
    tex = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (2.2, 18.0, 1.0)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = 1.4
    wave.inputs["Distortion"].default_value = 3.5
    wave.inputs["Detail"].default_value = 4.0
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    noise.inputs["Detail"].default_value = 8.0
    mix = mix_rgb(nt, 0.35)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.28
    ramp.color_ramp.elements[0].color = (0.42, 0.28, 0.16, 1)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (0.72, 0.55, 0.34, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    nt.links.new(tex.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(tex.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], mix.inputs["Color1"])
    nt.links.new(noise.outputs["Fac"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(mix.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_bsdf(bsdf, roughness=0.42)
    return mat


def mat_ceiling_tiles():
    mat, bsdf, nt = principled("CeilingTiles")
    tex = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.7, 1.7, 1.7)
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.inputs["Color1"].default_value = (0.86, 0.85, 0.80, 1)
    brick.inputs["Color2"].default_value = (0.78, 0.77, 0.73, 1)
    brick.inputs["Mortar"].default_value = (0.62, 0.61, 0.58, 1)
    brick.inputs["Scale"].default_value = 4.0
    brick.inputs["Mortar Size"].default_value = 0.012
    brick.inputs["Brick Width"].default_value = 0.5
    brick.inputs["Row Height"].default_value = 0.5
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    nt.links.new(tex.outputs["Object"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(brick.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_bsdf(bsdf, roughness=0.82)
    return mat


def mat_metal(name, color, roughness=0.28, metallic=0.72):
    mat, bsdf, _ = principled(name)
    set_bsdf(bsdf, color=color + (1,), roughness=roughness, metallic=metallic, specular=0.55)
    return mat


def mat_cloth(name, color, roughness=0.9):
    mat, bsdf, nt = principled(name)
    tex = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 90.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    nt.links.new(tex.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    set_bsdf(bsdf, color=color + (1,), roughness=roughness)
    return mat


def mat_glass():
    mat, bsdf, _ = principled("WindowGlass")
    set_bsdf(bsdf, color=(0.82, 0.9, 0.95, 1), roughness=0.02, transmission=0.95, ior=1.45, specular=1.0)
    return mat


def mat_mirror():
    mat, bsdf, _ = principled("WardrobeMirror")
    set_bsdf(bsdf, color=(0.95, 0.96, 0.97, 1), roughness=0.02, metallic=1.0, specular=1.0)
    return mat


def mat_emission(name, color, strength):
    mat, bsdf, _ = principled(name)
    set_bsdf(bsdf, color=color + (1,), roughness=1.0, emission=color + (1,), emission_strength=strength)
    return mat


def mat_simple(name, color, roughness=0.5, metallic=0.0):
    mat, bsdf, _ = principled(name)
    set_bsdf(bsdf, color=color + (1,), roughness=roughness, metallic=metallic)
    return mat


def add_room(coll, mats):
    # Interior volume roughly 3.4 x 3.5 x 2.65 m, camera shoots from the open front.
    add_box("Floor", (0, -0.2, -0.04), (3.6, 4.4, 0.08), coll, mats["floor"])
    add_box("Ceiling", (0, -0.2, 2.68), (3.6, 4.4, 0.08), coll, mats["ceiling"])
    add_box("LeftWall", (-1.78, -0.15, 1.32), (0.08, 4.1, 2.68), coll, mats["wall"])
    add_box("RightWall", (1.78, -0.15, 1.32), (0.08, 4.1, 2.68), coll, mats["wall"])
    # Back wall split around a tall window.
    add_box("BackWallLeft", (-1.28, 1.74, 1.32), (0.95, 0.08, 2.68), coll, mats["wall"])
    add_box("BackWallRight", (1.28, 1.74, 1.32), (0.95, 0.08, 2.68), coll, mats["wall"])
    add_box("BackWallSill", (0.0, 1.74, 0.18), (1.62, 0.08, 0.36), coll, mats["wall"])
    add_box("BackWallHeader", (0.0, 1.74, 2.52), (1.62, 0.08, 0.36), coll, mats["wall"])
    add_box("BaseboardL", (-1.72, -0.15, 0.05), (0.04, 4.08, 0.08), coll, mats["trim"])
    add_box("BaseboardR", (1.72, -0.15, 0.05), (0.04, 4.08, 0.08), coll, mats["trim"])
    add_box("BaseboardB", (0.0, 1.68, 0.05), (3.4, 0.04, 0.08), coll, mats["trim"])
    # Window frame and glass.
    add_box("WindowFrame", (0.0, 1.70, 1.35), (1.68, 0.07, 2.18), coll, mats["metal"])
    add_box("WindowMullionV", (0.0, 1.68, 1.35), (0.05, 0.05, 2.05), coll, mats["metal"])
    add_box("WindowMullionH", (0.0, 1.68, 1.35), (1.52, 0.05, 0.05), coll, mats["metal"])
    add_box("WindowGlass", (0.0, 1.69, 1.35), (1.52, 0.02, 2.05), coll, mats["glass"])
    add_box("SkyPanel", (0.0, 1.92, 1.4), (1.7, 0.04, 2.2), coll, mats["sky"])
    # Curtains.
    for i, x in enumerate((-1.05, -0.88, 0.88, 1.05)):
        add_box(f"CurtainDark{i}", (x, 1.58, 1.45), (0.18, 0.05, 2.35), coll, mats["curtain"])
    add_box("CurtainSheerL", (-0.48, 1.56, 1.45), (0.28, 0.04, 2.32), coll, mats["sheer"])
    add_box("CurtainSheerR", (0.48, 1.56, 1.45), (0.28, 0.04, 2.32), coll, mats["sheer"])
    add_box("CurtainRod", (0.0, 1.50, 2.58), (2.35, 0.04, 0.04), coll, mats["metal_high"])


def add_bed(coll, mats):
    # IKEA VITVAL-ish: ~209 x 97 x 191 cm loft.
    x0, x1 = -1.42, 0.67
    y0, y1 = 0.05, 1.02
    z_bed = 1.78
    for i, (x, y) in enumerate(((x0, y0), (x0, y1), (x1, y0), (x1, y1))):
        add_box(f"BedPost{i}", (x, y, z_bed / 2), (0.05, 0.05, z_bed), coll, mats["metal"])
        add_box(f"BedFoot{i}", (x, y, 0.04), (0.10, 0.10, 0.06), coll, mats["metal_high"])
    add_box("BedRailF", ((x0 + x1) / 2, y0, z_bed), (x1 - x0, 0.05, 0.07), coll, mats["metal"])
    add_box("BedRailB", ((x0 + x1) / 2, y1, z_bed), (x1 - x0, 0.05, 0.07), coll, mats["metal"])
    add_box("BedRailL", (x0, (y0 + y1) / 2, z_bed), (0.05, y1 - y0, 0.07), coll, mats["metal"])
    add_box("BedRailR", (x1, (y0 + y1) / 2, z_bed), (0.05, y1 - y0, 0.07), coll, mats["metal"])
    for i in range(9):
        x = x0 + 0.12 + i * (x1 - x0 - 0.24) / 8
        add_box(f"BedSlat{i}", (x, (y0 + y1) / 2, z_bed + 0.03), (0.04, y1 - y0 - 0.08, 0.03), coll, mats["metal_high"])
    add_box("Mattress", ((x0 + x1) / 2, (y0 + y1) / 2, z_bed + 0.14), (x1 - x0 - 0.08, y1 - y0 - 0.08, 0.18), coll, mats["mattress"])
    add_box("Duvet", ((x0 + x1) / 2 + 0.12, (y0 + y1) / 2, z_bed + 0.24), (1.55, 0.82, 0.04), coll, mats["sheet"])
    add_box("Pillow", (x0 + 0.28, (y0 + y1) / 2, z_bed + 0.27), (0.42, 0.62, 0.10), coll, mats["sheet"])
    rail_z = z_bed + 0.42
    for y, label in ((y0, "F"), (y1, "B")):
        add_box(f"GuardTop{label}", ((x0 + x1) / 2, y, rail_z), (x1 - x0, 0.035, 0.035), coll, mats["metal"])
        add_box(
            f"GuardCloth{label}",
            ((x0 + x1) / 2, y + (0.02 if y == y0 else -0.02), z_bed + 0.22),
            (x1 - x0 - 0.1, 0.018, 0.18),
            coll,
            mats["textile"],
        )
    add_box("GuardHead", (x0, (y0 + y1) / 2, rail_z), (0.035, y1 - y0, 0.035), coll, mats["metal"])
    add_box("GuardFoot", (x1, (y0 + y1) / 2, rail_z), (0.035, y1 - y0, 0.035), coll, mats["metal"])


def add_ladder(coll, mats):
    p0a, p1a = (0.82, -0.72, 0.05), (0.62, 0.02, 1.76)
    p0b, p1b = (1.12, -0.72, 0.05), (0.92, 0.02, 1.76)
    beam("LadderRailL", p0a, p1a, 0.045, coll, mats["metal"])
    beam("LadderRailR", p0b, p1b, 0.045, coll, mats["metal"])
    for i in range(5):
        t = (i + 0.55) / 5
        a = Vector(p0a) + (Vector(p1a) - Vector(p0a)) * t
        b = Vector(p0b) + (Vector(p1b) - Vector(p0b)) * t
        beam(f"LadderStep{i}", tuple(a), tuple(b), 0.035, coll, mats["metal_high"])


def add_desk_and_chair(coll, mats):
    add_box("DeskTop", (-0.95, 0.32, 0.74), (1.15, 0.55, 0.04), coll, mats["desk"])
    add_box("DeskPedestal", (-1.38, 0.32, 0.37), (0.28, 0.52, 0.70), coll, mats["desk"])
    add_box("Monitor", (-0.82, 0.52, 1.08), (0.52, 0.03, 0.32), coll, mats["metal"])
    add_box("MonitorStand", (-0.82, 0.50, 0.84), (0.05, 0.05, 0.16), coll, mats["metal_high"])
    add_cylinder("LampStem", (-0.48, 0.42, 0.95), 0.012, 0.28, coll, mats["metal"], 10, rotation=(0, math.radians(-18), 0))
    add_cylinder("LampShade", (-0.42, 0.42, 1.10), 0.06, 0.07, coll, mats["brass"], 16)
    add_box("ChairSeat", (-0.52, -0.02, 0.46), (0.42, 0.40, 0.04), coll, mats["wood"])
    for x, y in ((-0.67, -0.15), (-0.37, -0.15), (-0.67, 0.12), (-0.37, 0.12)):
        beam(f"ChairLeg{x}{y}", (x, y, 0.03), (x, y, 0.45), 0.03, coll, mats["wood"])
    add_box("ChairBack", (-0.52, -0.20, 0.78), (0.42, 0.04, 0.62), coll, mats["wood"])


def add_details(coll, mats):
    # Slightly Z-tilted wardrobe mirror: the tutorial's infinity-mirror trick, scaled to a bedroom.
    add_box("Wardrobe", (1.52, 0.35, 1.05), (0.38, 0.72, 2.05), coll, mats["desk"])
    mirror = add_box("Mirror", (1.32, 0.35, 1.12), (0.02, 0.58, 1.55), coll, mats["mirror"])
    mirror.rotation_euler[2] = math.radians(1.8)
    add_box("Shelf", (1.35, 1.42, 0.92), (0.38, 0.22, 0.04), coll, mats["wood"])
    add_cylinder("Pot", (1.35, 1.42, 1.05), 0.07, 0.14, coll, mats["brass"], 16)
    for i in range(6):
        a = math.radians(i * 60)
        beam(
            f"Leaf{i}",
            (1.35, 1.42, 1.12),
            (1.35 + math.cos(a) * 0.12, 1.42 + math.sin(a) * 0.12, 1.32),
            0.015,
            coll,
            mats["green"],
        )
    add_box("PictureFrame", (1.55, 1.69, 2.15), (0.32, 0.03, 0.42), coll, mats["wood"])
    add_box("Picture", (1.55, 1.67, 2.15), (0.26, 0.01, 0.36), coll, mats["sheer"])
    add_cylinder("HangHook", (1.22, 0.92, 2.42), 0.01, 0.28, coll, mats["metal"], 8)
    add_cylinder("HangRing", (1.22, 0.92, 1.78), 0.32, 0.03, coll, mats["metal_high"], 28, rotation=(math.radians(90), 0, 0))
    add_box("HangSeat", (1.22, 0.78, 1.42), (0.42, 0.32, 0.05), coll, mats["wood"])


def add_lights():
    world = bpy.data.worlds.new("RoomWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.22, 0.32, 0.48, 1)
        bg.inputs["Strength"].default_value = 0.35

    window = bpy.data.lights.new("WindowLight", "AREA")
    window.type = "AREA"
    window.shape = "RECTANGLE"
    window.size = 1.5
    window.size_y = 2.0
    window.energy = 110
    window.color = (0.78, 0.88, 1.0)
    window_obj = bpy.data.objects.new("WindowLight", window)
    window_obj.location = (0.0, 1.85, 1.4)
    window_obj.rotation_euler = (math.radians(-8), 0, math.radians(180))
    bpy.context.scene.collection.objects.link(window_obj)

    fill = bpy.data.lights.new("CeilingFill", "AREA")
    fill.size = 2.4
    fill.energy = 40
    fill.color = (1.0, 0.93, 0.84)
    fill_obj = bpy.data.objects.new("CeilingFill", fill)
    fill_obj.location = (0.0, 0.1, 2.55)
    fill_obj.rotation_euler = (math.radians(180), 0, 0)
    bpy.context.scene.collection.objects.link(fill_obj)

    lamp = bpy.data.lights.new("DeskLamp", "POINT")
    lamp.energy = 8
    lamp.color = (1.0, 0.78, 0.52)
    lamp_obj = bpy.data.objects.new("DeskLamp", lamp)
    lamp_obj.location = (-0.42, 0.18, 1.12)
    bpy.context.scene.collection.objects.link(lamp_obj)


def add_camera(view):
    cam = bpy.data.cameras.new("Camera")
    cam.lens = 24 if view == "front" else 22
    cam.sensor_width = 36
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = 3.2
    obj = bpy.data.objects.new("Camera", cam)
    if view == "front":
        obj.location = (0.10, -2.22, 1.28)
        target = Vector((0.08, 0.50, 1.42))
    else:
        obj.location = (0.78, -2.05, 1.32)
        target = Vector((0.02, 0.38, 1.38))
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()
    focus = bpy.data.objects.new("Focus", None)
    focus.location = (-0.4, 0.25, 0.95)
    bpy.context.scene.collection.objects.link(focus)
    cam.dof.focus_object = focus
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.scene.camera = obj


def setup_compositor():
    """Blur -> sharpen -> bloom glare -> streak glare, then light film grain."""
    ng = bpy.data.node_groups.new("LiminalComp", "CompositorNodeTree")
    ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    blur = ng.nodes.new("CompositorNodeBlur")
    blur.inputs["Size"].default_value = (1.2, 1.2)
    sharp = ng.nodes.new("CompositorNodeFilter")
    try:
        sharp.inputs["Type"].default_value = "Sharpen"
    except TypeError:
        pass
    sharp.inputs["Fac"].default_value = 0.35
    bloom = ng.nodes.new("CompositorNodeGlare")
    for glare_name in ("Bloom", "Fog Glow", "Ghosts"):
        try:
            bloom.inputs["Type"].default_value = glare_name
            break
        except TypeError:
            continue
    bloom.inputs["Threshold"].default_value = 0.85
    bloom.inputs["Strength"].default_value = 0.55
    bloom.inputs["Size"].default_value = 0.45
    streaks = ng.nodes.new("CompositorNodeGlare")
    streaks.inputs["Type"].default_value = "Streaks"
    streaks.inputs["Threshold"].default_value = 1.1
    streaks.inputs["Strength"].default_value = 0.28
    streaks.inputs["Streaks"].default_value = 2
    streaks.inputs["Streaks Angle"].default_value = math.radians(90)
    mix_grain = ng.nodes.new("ShaderNodeMixRGB")
    mix_grain.blend_type = "OVERLAY"
    mix_grain.inputs["Fac"].default_value = 0.045
    grain = bpy.data.images.new("FilmGrain", 1280, 1280, alpha=False)
    pixels = [0.0] * (1280 * 1280 * 4)
    rng = random.Random(7)
    for i in range(0, len(pixels), 4):
        v = 0.5 + (rng.random() - 0.5) * 0.35
        pixels[i] = pixels[i + 1] = pixels[i + 2] = v
        pixels[i + 3] = 1.0
    grain.pixels = pixels
    img_node = ng.nodes.new("CompositorNodeImage")
    img_node.image = grain
    out = ng.nodes.new("NodeGroupOutput")
    links = ng.links
    links.new(rl.outputs["Image"], blur.inputs["Image"])
    links.new(blur.outputs["Image"], sharp.inputs["Image"])
    links.new(sharp.outputs["Image"], bloom.inputs["Image"])
    links.new(bloom.outputs["Image"], streaks.inputs["Image"])
    links.new(streaks.outputs["Image"], mix_grain.inputs["Color1"])
    links.new(img_node.outputs["Image"], mix_grain.inputs["Color2"])
    links.new(mix_grain.outputs["Color"], out.inputs[0])
    scene = bpy.context.scene
    scene.compositing_node_group = ng
    scene.render.use_compositing = True


def setup_render(args):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args["samples"]
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "use_adaptive_sampling"):
        scene.cycles.use_adaptive_sampling = True
    scene.cycles.max_bounces = 16
    scene.cycles.glossy_bounces = 8
    scene.cycles.transmission_bounces = 8
    scene.cycles.diffuse_bounces = 4
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 1280
    scene.render.image_settings.file_format = "PNG"
    suffix = f"{args['view']}_fast" if args.get("fast") else args["view"]
    scene.render.filepath = str(RENDER_DIR / f"single_room_{suffix}.png")
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.15
    setup_compositor()


def main():
    args = parse_args()
    RENDER_DIR.mkdir(exist_ok=True)
    clear_scene()
    room = collection("Room")
    furniture = collection("Furniture")
    mats = {
        "wall": mat_drywall(),
        "ceiling": mat_ceiling_tiles(),
        "floor": mat_wood_floor(),
        "metal": mat_metal("VITVALCharcoal", (0.07, 0.075, 0.08), 0.32, 0.55),
        "metal_high": mat_metal("SteelEdge", (0.18, 0.18, 0.18), 0.22, 0.7),
        "textile": mat_cloth("GuardCloth", (0.62, 0.63, 0.60)),
        "sheet": mat_cloth("Bedding", (0.90, 0.89, 0.84), 0.85),
        "mattress": mat_simple("Mattress", (0.86, 0.85, 0.80), 0.9),
        "desk": mat_simple("Desk", (0.89, 0.88, 0.84), 0.45),
        "wood": mat_simple("ChairWood", (0.32, 0.18, 0.09), 0.48),
        "glass": mat_glass(),
        "mirror": mat_mirror(),
        "curtain": mat_cloth("SlateCurtain", (0.22, 0.24, 0.30)),
        "sheer": mat_cloth("Sheer", (0.78, 0.78, 0.76), 0.7),
        "trim": mat_simple("Trim", (0.9, 0.88, 0.82), 0.55),
        "sky": mat_emission("SkyPanel", (0.42, 0.58, 0.82), 2.2),
        "green": mat_simple("Plant", (0.12, 0.28, 0.12), 0.7),
        "brass": mat_metal("Brass", (0.42, 0.28, 0.12), 0.35, 0.6),
    }
    add_room(room, mats)
    add_bed(furniture, mats)
    add_ladder(furniture, mats)
    add_desk_and_chair(furniture, mats)
    add_details(furniture, mats)
    add_lights()
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
