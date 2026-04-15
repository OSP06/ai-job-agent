#!/usr/bin/env python3
"""
Generate extension icons from extension/icons/icon.svg.

Usage:
    python scripts/generate_icons.py

Tries cairosvg first (best quality), falls back to Pillow.
Install cairosvg:  pip install cairosvg
Install Pillow:    pip install Pillow
"""

import math
import pathlib
import sys

SIZES = [16, 48, 128]
SVG_PATH = pathlib.Path("extension/icons/icon.svg")


def with_cairosvg():
    import cairosvg
    svg_data = SVG_PATH.read_bytes()
    for size in SIZES:
        out = f"extension/icons/icon{size}.png"
        cairosvg.svg2png(
            bytestring=svg_data,
            write_to=out,
            output_width=size,
            output_height=size,
        )
        print(f"  ✓ icon{size}.png")


def with_pillow():
    from PIL import Image, ImageDraw

    def make_icon(size):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        r     = max(3, int(size * 0.22))
        pad   = max(1, int(size * 0.031))

        # Diagonal gradient bg (indigo #4f46e5 → violet #7c3aed)
        for y in range(size):
            t = y / max(size - 1, 1)
            col = (
                int(79  + (124 - 79)  * t),   # R
                int(70  + (58  - 70)  * t),    # G
                int(229 + (237 - 229) * t),    # B
                255,
            )
            draw.line([(0, y), (size - 1, y)], fill=col)

        # Clip to rounded rectangle
        mask = Image.new("L", (size, size), 0)
        m = ImageDraw.Draw(mask)
        m.rounded_rectangle([(pad, pad), (size - pad - 1, size - pad - 1)], radius=r, fill=255)
        img.putalpha(mask)

        # 4-pointed star (8-vertex polygon approximation of the bezier star)
        cx, cy   = size / 2, size / 2
        outer_r  = size * 0.365
        inner_r  = size * 0.115
        pts = []
        for i in range(8):
            angle  = math.pi * i / 4 - math.pi / 2
            radius = outer_r if i % 2 == 0 else inner_r
            pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))

        overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        o = ImageDraw.Draw(overlay)
        o.polygon(pts, fill=(255, 255, 255, 245))
        img = Image.alpha_composite(img, overlay)

        # Small accent dot (top-right, only visible at 48px+)
        if size >= 48:
            dot_x = int(cx + size * 0.26)
            dot_y = int(cy - size * 0.26)
            dot_r = max(2, int(size * 0.035))
            d2 = ImageDraw.Draw(img)
            d2.ellipse(
                [(dot_x - dot_r, dot_y - dot_r), (dot_x + dot_r, dot_y + dot_r)],
                fill=(255, 255, 255, 122),
            )

        return img

    for size in SIZES:
        make_icon(size).save(f"extension/icons/icon{size}.png")
        print(f"  ✓ icon{size}.png  (Pillow approximate)")


print("Generating extension icons…")
try:
    with_cairosvg()
    print("Done ✓  (cairosvg — pixel-perfect)")
except (ImportError, OSError):
    print("cairosvg unavailable (needs Cairo system lib), falling back to Pillow…")
    try:
        with_pillow()
        print("Done ✓  (Pillow)")
        print("\nFor pixel-perfect SVG rendering:")
        print("  brew install cairo && pip install cairosvg && python scripts/generate_icons.py")
    except ImportError:
        print("ERROR: Pillow is not installed.")
        print("Run:  pip install Pillow")
        sys.exit(1)
