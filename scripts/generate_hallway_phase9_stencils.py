#!/usr/bin/env python3
"""Generate a sparse industrial stencil atlas for Phase 9 signage.

Uses system Python + Pillow.  Blender's bundled Python has no PIL.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "hallway_phase9"
ATLAS = OUT / "p9_stencil_atlas.png"
SHEET = OUT / "p9_stencil_contact_sheet.png"
UV_JSON = OUT / "p9_uv.json"
FONT_SANS = Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")
FONT_REG = Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
FONT_MONO = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")

ATLAS_SIZE = 1024

# Cell rectangles in atlas pixels (x, y, w, h).  UV origin is bottom-left in Blender,
# so the generator stores top-left pixels and converts at the end.
# Cell aspect ratios match world-space decal planes so lettering is not stretched.
CELLS = {
    "elec_a04": (16, 16, 248, 75),
    "elec_b12": (280, 16, 280, 75),
    "svc_b04": (576, 16, 315, 75),
    "elec_c07": (16, 108, 287, 75),
    "p02": (320, 108, 410, 140),
    "v2b": (748, 108, 188, 75),
    "hv": (16, 268, 500, 160),
    "vent03": (532, 268, 243, 80),
    "hot": (532, 360, 267, 80),
    "insp": (810, 268, 100, 120),
    "floor": (16, 452, 210, 294),
}


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def tracked_width(text: str, fnt: ImageFont.FreeTypeFont, tracking: float) -> float:
    if not text:
        return 0.0
    widths = [fnt.getlength(ch) for ch in text]
    return float(sum(widths) + tracking * (len(text) - 1))


def draw_tracked(draw: ImageDraw.ImageDraw, xy, text, fnt, fill, tracking: float = 1.0) -> None:
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += fnt.getlength(ch) + tracking


def center_tracked(draw, box, text, fnt, fill, tracking, dy=0):
    x, y, w, h = box
    tw = tracked_width(text, fnt, tracking)
    bbox = fnt.getbbox("Ag")
    th = bbox[3] - bbox[1]
    tx = x + (w - tw) * 0.5
    ty = y + (h - th) * 0.5 + dy
    draw_tracked(draw, (tx, ty), text, fnt, fill, tracking)


def noise_field(w: int, h: int, scale: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    nw = max(2, int(w / scale))
    nh = max(2, int(h / scale))
    small = rng.random((nh, nw)).astype(np.float32)
    img = Image.fromarray((small * 255).astype(np.uint8), mode="L")
    img = img.resize((w, h), Image.Resampling.BICUBIC)
    return np.asarray(img, dtype=np.float32) / 255.0


def apply_wear(img: Image.Image, amount: float, seed: int, fade: float) -> Image.Image:
    """Bake edge wear, paint loss, and dirt into RGB+alpha. amount 0..1."""
    arr = np.asarray(img.convert("RGBA"), dtype=np.float32)
    h, w = arr.shape[:2]
    n1 = noise_field(w, h, 7.0 + amount * 4.0, seed)
    n2 = noise_field(w, h, 2.4, seed + 17)
    n3 = noise_field(w, h, 18.0, seed + 31)
    alpha = arr[:, :, 3] / 255.0
    # Soft edge distance via min-filter equivalent: blurred alpha as coverage.
    blur = Image.fromarray((alpha * 255).astype(np.uint8), "L").filter(
        ImageFilter.GaussianBlur(radius=1.1 + amount * 1.8)
    )
    edge = np.asarray(blur, dtype=np.float32) / 255.0
    rim = np.clip((edge - alpha) * 4.0 + (1.0 - edge) * 0.35, 0.0, 1.0)
    loss = np.clip((n1 * 0.72 + n2 * 0.28) - (0.62 - amount * 0.42), 0.0, 1.0)
    scratches = (n2 > (0.89 - amount * 0.08)).astype(np.float32)
    # Horizontal scratch bias.
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    scratch_band = (np.abs(np.sin(yy * 37.0 + seed)) > 0.97).astype(np.float32)
    scratches = np.clip(scratches * scratch_band * n3 * 1.8, 0.0, 1.0)
    worn = alpha * (1.0 - loss * (0.35 + amount * 0.55)) * (1.0 - scratches * (0.25 + amount * 0.45))
    worn *= 1.0 - rim * (0.18 + amount * 0.40)
    worn *= fade
    worn = np.clip(worn, 0.0, 1.0)
    # Dirt slightly darkens remaining paint; do not add a global grime veil.
    dirt = 0.78 + 0.22 * n3
    arr[:, :, 0] *= dirt
    arr[:, :, 1] *= dirt * (0.98 + 0.02 * n1)
    arr[:, :, 2] *= dirt * (0.96 + 0.04 * n2)
    arr[:, :, 3] = worn * 255.0
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def paste_cell(atlas: Image.Image, cell: Image.Image, key: str) -> None:
    x, y, w, h = CELLS[key]
    cell = cell.resize((w, h), Image.Resampling.LANCZOS)
    atlas.alpha_composite(cell, (x, y))


def id_plate(text: str, wear: float, seed: int, fade: float, size: tuple[int, int]) -> Image.Image:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font(FONT_SANS, 54 if len(text) <= 8 else 46)
    tracking = 3.2
    # Dark filled industrial lettering, not glossy white.
    center_tracked(draw, (0, 0, size[0], size[1]), text, fnt, (36, 32, 28, 255), tracking, dy=-2)
    return apply_wear(img, wear, seed, fade)


def pipe_mark() -> Image.Image:
    size = (800, 280)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font(FONT_SANS, 96)
    draw_tracked(draw, (48, 78), "P-02", fnt, (42, 38, 34, 255), 4.0)
    # Chevron pointing to image-right = corridor +Y on +X-facing planes.
    ax = 470
    ay = 140
    draw.polygon(
        [(ax, ay - 46), (ax + 92, ay), (ax, ay + 46), (ax + 22, ay), (ax, ay - 46)],
        fill=(42, 38, 34, 255),
    )
    draw.rectangle((ax - 70, ay - 14, ax + 8, ay + 14), fill=(42, 38, 34, 255))
    return apply_wear(img, 0.22, 41, 0.90)


def hv_plate() -> Image.Image:
    size = (1120, 360)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Faded institutional yellow plate, not OSHA-plastic gloss.
    draw.rounded_rectangle((18, 18, size[0] - 18, size[1] - 18), radius=18, fill=(138, 116, 46, 230))
    draw.rounded_rectangle((38, 38, size[0] - 38, size[1] - 38), radius=12, outline=(28, 24, 20, 255), width=10)
    fnt = font(FONT_SANS, 92)
    center_tracked(draw, (0, 8, size[0], size[1] - 40), "HIGH VOLTAGE", fnt, (24, 22, 18, 255), 4.5)
    sub = font(FONT_REG, 36)
    center_tracked(draw, (0, 250, size[0], 90), "AUTHORIZED PERSONNEL", sub, (28, 26, 22, 255), 2.4)
    return apply_wear(img, 0.34, 77, 0.88)


def small_id(text: str, wear: float, seed: int, fade: float) -> Image.Image:
    img = Image.new("RGBA", (440, 176), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font(FONT_SANS, 64)
    center_tracked(draw, (0, 0, 440, 176), text, fnt, (40, 36, 32, 255), 3.0)
    return apply_wear(img, wear, seed, fade)


def hot_stencil() -> Image.Image:
    img = Image.new("RGBA", (680, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font(FONT_SANS, 62)
    center_tracked(draw, (0, 0, 680, 200), "HOT SURFACE", fnt, (48, 42, 32, 255), 3.6)
    return apply_wear(img, 0.40, 91, 0.78)


def inspection_sticker() -> Image.Image:
    size = (248, 296)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((8, 8, size[0] - 8, size[1] - 8), radius=10, fill=(176, 166, 138, 235))
    draw.rounded_rectangle((16, 16, size[0] - 16, size[1] - 16), radius=8, outline=(62, 56, 44, 200), width=3)
    title = font(FONT_SANS, 36)
    body = font(FONT_MONO, 34)
    tiny = font(FONT_REG, 22)
    center_tracked(draw, (0, 28, size[0], 50), "INSP", title, (40, 36, 30, 255), 2.0)
    center_tracked(draw, (0, 88, size[0], 50), "11-02", body, (36, 32, 28, 255), 1.4)
    center_tracked(draw, (0, 148, size[0], 44), "OK", title, (46, 52, 38, 255), 3.0)
    center_tracked(draw, (0, 210, size[0], 40), "M.H.", tiny, (58, 52, 44, 220), 1.8)
    worn = apply_wear(img, 0.38, 113, 0.86)
    # Peel one corner so it reads as a sticker, not a shader.
    arr = np.array(worn, dtype=np.uint8, copy=True)
    yy, xx = np.mgrid[0 : size[1], 0 : size[0]]
    peel = (xx + yy) > (size[0] + size[1] - 54)
    arr[peel, 3] = 0
    return Image.fromarray(arr, "RGBA")


def floor_bay() -> Image.Image:
    size = (840, 520)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (126, 108, 40, 200)
    # Broken equipment-placement rectangle, not a continuous hazard stripe.
    segs = [
        (40, 40, 300, 62),
        (520, 40, 800, 62),
        (40, 458, 280, 480),
        (560, 458, 800, 480),
        (40, 40, 62, 210),
        (40, 310, 62, 480),
        (778, 40, 800, 190),
        (778, 300, 800, 480),
    ]
    for box in segs:
        draw.rectangle(box, fill=color)
    return apply_wear(img, 0.55, 129, 0.42)


def build_atlas() -> Image.Image:
    atlas = Image.new("RGBA", (ATLAS_SIZE, ATLAS_SIZE), (0, 0, 0, 0))
    paste_cell(atlas, id_plate("ELEC-A04", 0.16, 3, 0.94, (480, 176)), "elec_a04")
    paste_cell(atlas, id_plate("ELEC-B12", 0.28, 5, 0.90, (560, 176)), "elec_b12")
    paste_cell(atlas, id_plate("SVC-B04", 0.30, 7, 0.88, (560, 176)), "svc_b04")
    paste_cell(atlas, id_plate("ELEC-C07", 0.62, 11, 0.52, (288, 176)), "elec_c07")
    paste_cell(atlas, pipe_mark(), "p02")
    paste_cell(atlas, hv_plate(), "hv")
    paste_cell(atlas, small_id("V-2B", 0.36, 13, 0.84), "v2b")
    paste_cell(atlas, small_id("VENT-03", 0.33, 17, 0.86), "vent03")
    paste_cell(atlas, hot_stencil(), "hot")
    paste_cell(atlas, inspection_sticker(), "insp")
    paste_cell(atlas, floor_bay(), "floor")
    return atlas


def contact_sheet(atlas: Image.Image) -> Image.Image:
    sheet = Image.new("RGB", (1100, 1280), (32, 30, 28))
    draw = ImageDraw.Draw(sheet)
    fnt = font(FONT_REG, 18)
    draw.text((24, 16), "Phase 9 stencil atlas (baked wear, hashed-alpha source)", font=fnt, fill=(200, 196, 188))
    preview = atlas.copy()
    # Composite on dark so alpha is visible.
    bg = Image.new("RGB", atlas.size, (42, 40, 38))
    bg.paste(preview, mask=preview.split()[-1])
    bg = bg.resize((1024, 1024), Image.Resampling.LANCZOS)
    sheet.paste(bg, (38, 48))
    y = 1088
    for i, key in enumerate(CELLS):
        draw.text((24 + (i % 4) * 270, y + (i // 4) * 28), key, font=fnt, fill=(168, 162, 150))
    return sheet


def uv_map() -> dict[str, tuple[float, float, float, float]]:
    """Return Blender UV rects (u0, v0, u1, v1) with origin at bottom-left."""
    out = {}
    for key, (x, y, w, h) in CELLS.items():
        u0 = x / ATLAS_SIZE
        u1 = (x + w) / ATLAS_SIZE
        v1 = 1.0 - y / ATLAS_SIZE
        v0 = 1.0 - (y + h) / ATLAS_SIZE
        out[key] = (u0, v0, u1, v1)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    atlas = build_atlas()
    atlas.save(ATLAS)
    contact_sheet(atlas).save(SHEET, quality=92)
    uvs = uv_map()
    UV_JSON.write_text(json.dumps(uvs, indent=2), encoding="utf-8")
    print("Wrote", ATLAS)
    print("Wrote", SHEET)
    print("Wrote", UV_JSON)
    for key, uv in uvs.items():
        print(f"UV {key:10s} {uv}")


if __name__ == "__main__":
    main()
