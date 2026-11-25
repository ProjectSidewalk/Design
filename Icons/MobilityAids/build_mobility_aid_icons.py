#!/usr/bin/env python3
"""
Build the single-color mobility-aid icons from Chu Li's artwork.

The five icons (walking cane, walker, mobility scooter, manual wheelchair, motorized wheelchair) were designed
by Chu Li for Figure 1 of:

  Chu Li, Rock Yuren Pang, Delphine Labbé, Yochai Eisenberg, Maryam Hosseini and Jon E. Froehlich. 2025.
  "Accessibility for Whom? Perceptions of Sidewalk Barriers Across Disability Groups and Implications for
  Designing Personalized Maps." CHI '25. https://doi.org/10.1145/3706598.3713421  (CC BY 4.0)

Source/Li_CHI2025_Figure1_4096px.jpg is that figure at 4096 px wide, the image Chu placed in her CHI 2025 talk
slides (the figure fills the middle band of the image; the rest is white). There each icon is about 230 px across,
drawn as a dark line with pale fills in the wheels. Source/Li_CHI2025_Figure1.png is the same figure as it is
embedded in the paper's PDF (1786 x 480), kept for reference; this script does not read it.

This script cuts each icon out of the 4096 px image and turns it into a one-color shape on a transparent background:

  1. keep the dark line and drop the pale fills, so the icon is a single color;
  2. enlarge it two times, blur it slightly and re-sharpen the edge, which removes the JPEG noise along the line;
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
SOURCE = os.path.join(HERE, "Source", "Li_CHI2025_Figure1_4096px.jpg")

# The edge of each icon's ink in the source image: (left, top, right, bottom), in the order the icons are shown.
BOXES = {
    "WalkingCane": (53, 1414, 288, 1622),
    "Walker": (66, 648, 268, 865),
    "MobilityScooter": (435, 876, 656, 1078),
    "ManualWheelchair": (54, 1004, 272, 1246),
    "MotorizedWheelchair": (437, 1225, 666, 1464),
}

# Project Sidewalk's navy is --color-asphalt-500 in the design-system tokens (see the top-level README).
COLORS = {"White": (255, 255, 255), "Navy": (45, 42, 63)}

SIDE = 480      # output size in pixels
MARGIN = 12     # clear space on every side
SCALE = 2       # how much the source crop is enlarged before the edge is re-sharpened
PAD = 8         # source pixels kept around each box, so the blur has room at the edges


def icon_alpha(figure, box):
    """Return one icon as a SIDE x SIDE "L" image: 255 where the icon is, 0 where it is clear.

    Args:
        figure: the source image as an RGB PIL image.
        box: (left, top, right, bottom) of the icon's ink in that image.
    """
    x0, y0, x1, y1 = box
    gray = np.asarray(figure.crop((x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD)).convert("L"), dtype=float)

    # Darkness from 0 (white) to 1 (black). The line is dark and the wheel fills are pale, so a threshold between
    # them keeps the line and drops the fills.
    ink = np.clip(((255 - gray) / 255 - 0.22) / 0.38, 0, 1)

    big = Image.fromarray((ink * 255).astype(np.uint8))
    big = big.resize((ink.shape[1] * SCALE, ink.shape[0] * SCALE), Image.BICUBIC)
    soft = np.asarray(big.filter(ImageFilter.GaussianBlur(1.1)), dtype=float) / 255
    edge = np.clip((soft - 0.38) / 0.24, 0, 1)
    edge = edge * edge * (3 - 2 * edge)                     # smoothstep: a short, even ramp from clear to solid

    # Trim to the shape itself, so that the icon is centered on its ink and the margin is exact.
    rows, cols = np.where(edge > 0.02)
    edge = edge[rows.min():rows.max() + 1, cols.min():cols.max() + 1]

    h, w = edge.shape
    k = (SIDE - 2 * MARGIN) / max(w, h)
    shape = Image.fromarray((edge * 255).astype(np.uint8)).resize((round(w * k), round(h * k)), Image.LANCZOS)
    canvas = Image.new("L", (SIDE, SIDE), 0)
    canvas.paste(shape, ((SIDE - shape.width) // 2, (SIDE - shape.height) // 2))
    return canvas


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
