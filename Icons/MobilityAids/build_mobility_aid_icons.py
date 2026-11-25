#!/usr/bin/env python3
"""
Build the single-color mobility-aid icons from Chu Li's artwork.

The five icons (walking cane, walker, mobility scooter, manual wheelchair, motorized wheelchair) were designed
by Chu Li for Figure 1 of:

  Chu Li, Rock Yuren Pang, Delphine Labbé, Yochai Eisenberg, Maryam Hosseini and Jon E. Froehlich. 2025.
  "Accessibility for Whom? Perceptions of Sidewalk Barriers Across Disability Groups and Implications for
  Designing Personalized Maps." CHI '25. https://doi.org/10.1145/3706598.3713421  (CC BY 4.0)

Source/Li_CHI2025_Figure1.png is that figure exactly as it is embedded in the paper's PDF (1786 x 480). There each
icon is about 100 px across, drawn as a dark line with pale blue fills in the wheels. This script cuts each one out
and turns it into a one-color shape on a transparent background:

  1. keep the dark line and drop the pale fills, so the icon is a single color;
  2. enlarge it five times, blur it slightly and re-sharpen the edge, which gives a clean line instead of pixels;
  3. center it in a 480 x 480 transparent square with a 12 px margin;
  4. save it once per color in COLORS.

Output, next to this script:
  <Color>/MobilityAid_<Name>_<Color>.png     480 x 480, transparent background
  MobilityAids_Preview.png                   the five white icons in a row on navy, for the README

Usage:
  python build_mobility_aid_icons.py

To add a color, add it to COLORS and rerun. Needs numpy and Pillow.
"""

import os

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "Source", "Li_CHI2025_Figure1.png")

# The edge of each icon's ink in the source figure: (left, top, right, bottom), in the order the icons are shown.
BOXES = {
    "WalkingCane": (7, 340, 110, 431),
    "Walker": (13, 4, 101, 98),
    "MobilityScooter": (175, 104, 271, 192),
    "ManualWheelchair": (8, 160, 103, 266),
    "MotorizedWheelchair": (176, 257, 276, 362),
}

# Project Sidewalk's navy is --color-asphalt-500 in the design-system tokens (see the top-level README).
COLORS = {"White": (255, 255, 255), "Navy": (45, 42, 63)}

SIDE = 480      # output size in pixels
MARGIN = 12     # clear space on every side
SCALE = 5       # how much the source crop is enlarged before the edge is re-sharpened


def icon_alpha(figure, box):
    """Return one icon as a SIDE x SIDE "L" image: 255 where the icon is, 0 where it is clear.

    Args:
        figure: the source figure as an RGB PIL image.
        box: (left, top, right, bottom) of the icon's ink in the figure.
    """
    x0, y0, x1, y1 = box
    gray = np.asarray(figure.crop((x0 - 4, y0 - 4, x1 + 5, y1 + 5)).convert("L"), dtype=float)

    # Darkness from 0 (white) to 1 (black). The line is dark and the wheel fills are pale, so a threshold between
    # them keeps the line and drops the fills.
    ink = np.clip(((255 - gray) / 255 - 0.22) / 0.38, 0, 1)

    big = Image.fromarray((ink * 255).astype(np.uint8))
    big = big.resize((ink.shape[1] * SCALE, ink.shape[0] * SCALE), Image.BICUBIC)
    soft = np.asarray(big.filter(ImageFilter.GaussianBlur(2.2)), dtype=float) / 255
    edge = np.clip((soft - 0.38) / 0.24, 0, 1)
    edge = edge * edge * (3 - 2 * edge)                     # smoothstep: a short, even ramp from clear to solid

    h, w = edge.shape
    k = (SIDE - 2 * MARGIN) / max(w, h)
    shape = Image.fromarray((edge * 255).astype(np.uint8)).resize((round(w * k), round(h * k)), Image.LANCZOS)

    # Paste the shape through its own alpha. That squares the alpha along the edge, which trims the soft fringe.
    solid = Image.new("RGBA", shape.size, (255, 255, 255, 255))
    solid.putalpha(shape)
    canvas = Image.new("RGBA", (SIDE, SIDE), (255, 255, 255, 0))
    canvas.paste(solid, ((SIDE - shape.width) // 2, (SIDE - shape.height) // 2), solid)
    return canvas.getchannel("A")


def main():
    figure = Image.open(SOURCE).convert("RGB")
    alphas = {name: icon_alpha(figure, box) for name, box in BOXES.items()}

    for color, rgb in COLORS.items():
        os.makedirs(os.path.join(HERE, color), exist_ok=True)
        for name, alpha in alphas.items():
            icon = Image.new("RGBA", (SIDE, SIDE), rgb + (0,))
            icon.putalpha(alpha)
            icon.save(os.path.join(HERE, color, f"MobilityAid_{name}_{color}.png"), optimize=True)

    # The preview: white icons at 240 px in a row on navy, so they show on GitHub's light and dark themes alike.
    size, gap = 240, 40
    preview = Image.new("RGB", (gap + len(alphas) * (size + gap), size + 2 * gap), COLORS["Navy"])
    for i, alpha in enumerate(alphas.values()):
        small = alpha.resize((size, size), Image.LANCZOS)
        preview.paste(Image.new("RGB", (size, size), COLORS["White"]), (gap + i * (size + gap), gap), small)
    preview.save(os.path.join(HERE, "MobilityAids_Preview.png"), optimize=True)

    print(f"wrote {len(alphas) * len(COLORS)} icons ({', '.join(COLORS)}) and MobilityAids_Preview.png")


if __name__ == "__main__":
    main()
