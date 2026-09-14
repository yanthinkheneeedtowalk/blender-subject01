#!/usr/bin/env python3
"""Labeled 2D floor plan of the Level 0 office. Metres, north = +Y (up)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reference" / "backrooms_floorplan.png"

SIZE_X, SIZE_Y = 12.0, 10.0
PPM = 80
PAD_L, PAD_R, PAD_T, PAD_B = 72, 48, 88, 56

# Same wall boxes as scripts/build_backrooms.py (x0, y0, x1, y1) in metres.
WALLS = [
    (0.00, 0.00, 0.20, 10.00),
    (11.80, 0.00, 12.00, 10.00),
    (0.20, 9.80, 11.80, 10.00),
    (0.20, 0.00, 10.60, 0.20),
    (3.20, 0.20, 3.40, 3.00),
    (0.20, 3.00, 1.30, 3.20),
    (2.80, 3.00, 3.40, 3.20),
    (1.10, 3.20, 1.30, 5.80),
    (2.80, 3.20, 3.00, 4.40),
    (2.80, 4.40, 3.50, 4.60),
    (4.80, 4.40, 5.40, 4.60),
    (4.00, 4.40, 4.20, 4.95),
    (3.40, 1.40, 3.60, 4.40),
    (4.80, 1.40, 5.00, 4.40),
    (3.60, 1.40, 4.80, 1.60),
    (5.20, 0.20, 5.40, 4.20),
    (5.40, 4.20, 7.00, 4.40),
    (8.60, 4.20, 10.40, 4.40),
    (10.40, 0.20, 10.60, 1.80),
    (10.40, 3.60, 10.60, 4.40),
    (7.60, 1.90, 7.80, 4.20),
    (7.80, 1.90, 9.10, 2.10),
    (7.50, 1.80, 7.90, 2.20),
    (10.60, 4.40, 11.80, 4.60),
    (6.40, 5.80, 10.40, 6.00),
    (4.60, 5.80, 4.80, 6.00),
    (6.20, 5.80, 6.40, 6.00),
    (0.20, 5.80, 4.40, 6.00),
    (4.40, 6.00, 4.60, 8.00),
    (4.40, 9.60, 4.60, 9.80),
    (5.90, 6.80, 6.40, 7.00),
    (6.40, 6.00, 6.60, 6.80),
    (6.40, 8.40, 6.60, 9.80),
    (7.80, 6.60, 8.00, 8.40),
    (6.60, 6.60, 7.80, 6.80),
    (8.20, 6.20, 10.40, 8.40),
    (8.00, 8.40, 10.60, 8.60),
    (10.40, 6.00, 10.60, 8.40),
    (10.60, 5.80, 11.80, 6.00),
    (3.60, 0.20, 5.20, 1.40),
]

LABELS = [
    (2.3, 8.0, "Room A", "4.2 × 3.8 m"),
    (1.7, 1.5, "Room B", "3.0 × 2.8 m"),
    (8.0, 3.2, "Main", "5.0 × 4.0 m"),
    (11.2, 2.2, "入口", "1.2 m"),
    (6.5, 5.1, "Hall B", "1.4 m"),
    (2.05, 4.5, "Hall B", "1.5 m"),
    (5.5, 7.9, "Corr A", "1.8 m"),
    (7.1, 8.2, "死角", ""),
    (9.30, 7.30, "Core", "", (236, 228, 200)),
    (9.4, 9.1, "Hall N", "1.4 m"),
    (11.2, 7.1, "Hall E", "1.2 m"),
    (4.15, 2.9, "死角", ""),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", size)
    except OSError:
        return ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", size)


def main() -> None:
    w = int(SIZE_X * PPM) + PAD_L + PAD_R
    h = int(SIZE_Y * PPM) + PAD_T + PAD_B
    img = Image.new("RGB", (w, h), (28, 26, 24))
    draw = ImageDraw.Draw(img)

    def xy(x: float, y: float) -> tuple[float, float]:
        return PAD_L + x * PPM, PAD_T + (SIZE_Y - y) * PPM

    def rect(x0, y0, x1, y1, fill, outline=None):
        (xa, ya), (xb, yb) = xy(x0, y0), xy(x1, y1)
        draw.rectangle([min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)], fill=fill, outline=outline)

    rect(0, 0, SIZE_X, SIZE_Y, (214, 196, 130))
    for box in WALLS:
        rect(*box, (32, 28, 24))

    title = font(22, bold=True)
    body = font(16)
    small = font(13)
    draw.text((PAD_L, 18), "Backrooms Level 0  平面圖", font=title, fill=(236, 228, 200))
    draw.text((PAD_L, 48), "12.0 × 10.0 m    牆厚 0.20 m    淨高 2.7 m    北向上", font=small, fill=(180, 170, 145))

    for item in LABELS:
        x, y, name, dim = item[:4]
        fill = item[4] if len(item) > 4 else (42, 36, 28)
        dim_fill = (214, 196, 130) if fill[0] > 200 else (70, 58, 40)
        px, py = xy(x, y)
        draw.text((px, py - 8), name, font=body, fill=fill, anchor="mm")
        if dim:
            draw.text((px, py + 12), dim, font=small, fill=dim_fill, anchor="mm")

    # Overall dimensions.
    ax0, ay0 = xy(0, 0)
    ax1, ay1 = xy(SIZE_X, SIZE_Y)
    draw.line([(ax0, ay0 + 28), (ax1, ay0 + 28)], fill=(200, 190, 160), width=1)
    draw.text(((ax0 + ax1) / 2, ay0 + 40), "12.0 m", font=small, fill=(200, 190, 160), anchor="mm")
    draw.line([(ax0 - 28, ay0), (ax0 - 28, ay1)], fill=(200, 190, 160), width=1)
    draw.text((ax0 - 40, (ay0 + ay1) / 2), "10.0 m", font=small, fill=(200, 190, 160), anchor="mm")

    # North arrow.
    nx, ny = w - 36, 40
    draw.polygon([(nx, ny - 16), (nx - 7, ny + 8), (nx + 7, ny + 8)], fill=(236, 228, 200))
    draw.text((nx, ny + 18), "N", font=small, fill=(236, 228, 200), anchor="mm")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
