#!/usr/bin/env python3
"""
Build the v2 Project Sidewalk logos as SVG and PNG: the full-color SVGs, and single-color versions
in white, black and each of the logo's four brand colors.

Each logo's Illustrator file is a PDF underneath. We convert it to SVG with poppler's pdftocairo,
then write it out in full color (snapped to the brand guide's hex codes) and once per single color,
and export PNGs at the same sizes as the existing full-color PNGs.

Output, next to each .ai file:
  <stem>.svg                                    full color
  Monochrome/<Color>/<stem>_<Color>.svg         single color, plus <stem>_<Color>_<WxH>.png

In one color, the wheel and the three sidewalk wedges become the same color. In the v2 artwork
the wheel sits directly on top of the wedges, so a plain recolor merges them and the bottom of the
wheel disappears. To keep the wheel readable, the wedges' inner edges are redrawn as an arc that
leaves a transparent "keyline" around the wheel, as wide as the gaps between the wheel's spokes.
The geometry is baked into the paths (no masks or clip paths), so the SVGs behave the same in
browsers, Office, Figma and Illustrator.

Usage:
  python build_v2_logos.py               # writes into the */v2/ folders
  python build_v2_logos.py --no-keyline  # single colors as a plain recolor (wheel merges into wedges)
  python build_v2_logos.py --out DIR     # write everything under DIR instead

Needs: poppler's pdftocairo and Inkscape 1.x (for the PNGs) on PATH or at the default Windows
install path. Python standard library only.
"""

import argparse
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SVG_NS = "http://www.w3.org/2000/svg"

# The brand palette: the 500 level of each color in the design-system tokens, as SidewalkWebpage
# serves them in frontend/css/main.css (the canonical source; see Design#5). The .ai files and
# PS_brand_guidelines.pdf (2017) differ from these by at most 4 units per channel, which can't be
# seen; full-color output is snapped to these values.
PALETTE = {
    "Navy": "#2D2A3F",    # --color-asphalt-500, the hero color (Pantone 5255)
    "Orange": "#EB724E",  # --color-orange-500 (Pantone 7417)
    "Yellow": "#FBD98C",  # --color-banana-500 (Pantone 7403)
    "Green": "#78C9AB",   # --color-pine-500 (Pantone 7472)
}

# Single-color versions to build. Which backgrounds each suits is in the repo README.
COLORS = {"White": "#FFFFFF", "Black": "#000000", **PALETTE}

# Fills the full-color output may contain: the palette, plus the black of the curved text.
FULL_COLOR_FILLS = [*PALETTE.values(), "#000000"]

# Width of the keyline as a fraction of the wheel's outer radius. Measured from the square
# logo: the gap between the two wheel halves (the spoke) is 9.31 units on a 67.39-unit radius.
KEYLINE_RATIO = 9.31 / 67.39

# The non-wedge fills in the v2 artwork: the hero dark (#2D2A3F) and plain black (curved text).
# Every other fill is one of the three sidewalk wedges.
DARK_FILLS = {(17.6, 16.5, 24.7), (0.0, 0.0, 0.0)}

# One entry per logo. "sizes" are the PNGs to export as (width, height), matching the full-color
# PNGs' pixel sizes where those exist; a height of None keeps the aspect ratio. "crop" trims the
# viewBox to the artwork instead of the Illustrator artboard. "color_pngs" also exports full-color
# PNGs (the others already have Illustrator-made ones).
LOGOS = [
    {
        "ai": "Logo_Horizontal/v2/PS_Logo_Horizontal.ai",
        "stem": "PS_Logo_Horizontal",
        "sizes": [(2393, 624), (798, 209), (600, 156)],
    },
    {
        "ai": "Logo_Square/RGB/v2/ProjectSidewalkLogo_NoText.ai",
        "stem": "ProjectSidewalkLogo_NoText",
        "sizes": [(3240, 3240), (100, 100), (50, 50)],
    },
    {
        "ai": "Logo_Square/RGB/v2/ProjectSidewalkLogo_NoText_WheelchairCircleCentered.ai",
        "stem": "ProjectSidewalkLogo_NoText_WheelchairCircleCentered",
        "sizes": [(3240, 3240), (100, 100), (50, 50)],
    },
    {
        # The "-Cleaned" file has the curved text converted to outlines, so the SVG doesn't need
        # the Raleway font. (The SVGs Illustrator exported from these files drew a notched hub.)
        "ai": "Logo_Square/RGB/v2/ProjectSidewalkLogo_WithCurvedText-Cleaned.ai",
        "stem": "ProjectSidewalkLogo_WithCurvedText",
        "sizes": [(3600, 3600), (1000, 1000), (100, 100)],
    },
    {
        # Its artboard is a US Letter page, so crop to the artwork.
        "ai": "Logo_Square/RGB/v2/ProjectSidewalkLogo_WithHorizontalText.ai",
        "stem": "ProjectSidewalkLogo_WithHorizontalText",
        "sizes": [(3000, None), (1000, None), (500, None)],
        "crop": True,
        "color_pngs": True,
    },
]


# --------------------------------------------------------------------------------------------
# Path parsing and geometry
# --------------------------------------------------------------------------------------------

def parse_path(d):
    """Parse pdftocairo's path data into a list of subpaths.

    pdftocairo only writes absolute M, L, C and Z, which is all this handles. Each subpath is
    (start, segments, closed), and each segment is ("L", end) or ("C", c1, c2, end).

    Example: parse_path("M 0 0 L 1 0 Z") -> [((0.0, 0.0), [("L", (1.0, 0.0))], True)]
    """
    tokens = re.findall(r"[MLCZmlczHVhvSsQqTtAa]|-?\d*\.?\d+(?:e-?\d+)?", d)
    subpaths, i = [], 0

    def nums(n):
        nonlocal i
        vals = [float(t) for t in tokens[i:i + n]]
        i += n
        return [(vals[k], vals[k + 1]) for k in range(0, n, 2)]

    current = None
    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        if cmd == "M":
            current = [nums(2)[0], [], False]
            subpaths.append(current)
        elif cmd == "L":
            current[1].append(("L", *nums(2)))
        elif cmd == "C":
            current[1].append(("C", *nums(6)))
        elif cmd == "Z":
            current[2] = True
        else:
            raise ValueError(f"unexpected path command {cmd!r}; only absolute M/L/C/Z are handled")
    # A trailing "Z M x y" leaves an empty subpath behind; drop it.
    return [tuple(sp) for sp in subpaths if sp[1]]


def cubic_point(p0, c1, c2, p1, t):
    u = 1 - t
    return tuple(u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * e
                 for a, b, c, e in zip(p0, c1, c2, p1))


def path_bbox(subpaths):
    """Tight bounding box (x0, y0, x1, y1) of parsed subpaths, sampling each cubic."""
    xs, ys = [], []
    for start, segs, _ in subpaths:
        prev = start
        xs.append(start[0])
        ys.append(start[1])
        for seg in segs:
            if seg[0] == "L":
                pts = [seg[1]]
            else:
                pts = [cubic_point(prev, seg[1], seg[2], seg[3], k / 64) for k in range(1, 65)]
            xs.extend(p[0] for p in pts)
            ys.extend(p[1] for p in pts)
            prev = seg[-1]
    return min(xs), min(ys), max(xs), max(ys)


def fmt(v):
    """Compact number for path data: 3 decimals, no trailing zeros."""
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pt(p):
    return f"{fmt(p[0])} {fmt(p[1])}"


def circle_hit(a, b, center, radius):
    """Point where segment a->b crosses the circle, for a segment with one end on each side."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - center[0], a[1] - center[1]
    qa = dx * dx + dy * dy
    qb = 2 * (fx * dx + fy * dy)
    qc = fx * fx + fy * fy - radius * radius
    disc = qb * qb - 4 * qa * qc
    if disc < 0:
        raise ValueError("edge does not reach the keyline circle")
    roots = [(-qb + s * math.sqrt(disc)) / (2 * qa) for s in (-1, 1)]
    hits = [t for t in roots if 0 <= t <= 1]
    if len(hits) != 1:
        raise ValueError(f"expected one crossing of the keyline circle, got {len(hits)}")
    t = hits[0]
    return a[0] + t * dx, a[1] + t * dy


def keyline_wedge(subpaths, center, radius):
    """Redraw a wedge so its inner edge is an arc of `radius` around the wheel `center`.

    A wedge is one closed loop of two straight edges and two curves: the outer edge of the
    sidewalk, and the inner edge that the wheel covers. We keep the outer curve and the straight
    edges, cut the straight edges where they cross the circle, and join those two points with an
    arc in place of the inner curve.
    """
    if len(subpaths) != 1:
        raise ValueError("a wedge should be a single subpath")
    start, segs, _ = subpaths[0]

    # Build the loop as (kind, p0, ..., p1) with explicit start points, closing it if needed.
    loop, prev = [], start
    for seg in segs:
        loop.append((seg[0], prev, *seg[1:]))
        prev = seg[-1]
    if math.dist(prev, start) > 1e-6:
        loop.append(("L", prev, start))
    kinds = "".join(s[0] for s in loop)
    if sorted(kinds) != ["C", "C", "L", "L"] or kinds in ("CCLL", "LLCC", "CLLC", "LCCL"):
        raise ValueError(f"unexpected wedge shape {kinds!r}; expected alternating lines and curves")

    def mean_dist(seg):
        return (math.dist(seg[1], center) + math.dist(seg[-1], center)) / 2

    curves = [k for k, s in enumerate(loop) if s[0] == "C"]
    outer_k = max(curves, key=lambda k: mean_dist(loop[k]))
    outer = loop[outer_k]
    after = loop[(outer_k + 1) % 4]   # straight edge from the outer curve's end inwards
    before = loop[(outer_k - 1) % 4]  # straight edge from the inner curve out to the outer start
    p_in = circle_hit(after[1], after[2], center, radius)
    p_out = circle_hit(before[1], before[2], center, radius)

    # Sweep the short way round from p_in to p_out. In SVG's y-down space a positive cross
    # product is clockwise on screen, which is sweep-flag 1.
    cross = ((p_in[0] - center[0]) * (p_out[1] - center[1])
             - (p_in[1] - center[1]) * (p_out[0] - center[0]))
    sweep = 1 if cross > 0 else 0
    r = fmt(radius)
    return (f"M {pt(outer[1])} C {pt(outer[2])} {pt(outer[3])} {pt(outer[4])} "
            f"L {pt(p_in)} A {r} {r} 0 0 {sweep} {pt(p_out)} Z")


# --------------------------------------------------------------------------------------------
# Building one logo
# --------------------------------------------------------------------------------------------

def parse_fill(fill):
    m = re.fullmatch(r"rgb\(([\d.]+)%,\s*([\d.]+)%,\s*([\d.]+)%\)", fill.strip())
    if not m:
        raise ValueError(f"unexpected fill {fill!r}")
    return tuple(round(float(v), 1) for v in m.groups())


def load_shapes(svg_path):
    """Read pdftocairo's SVG into (viewBox, [(fill_rgb, subpaths, d)]), checking its clips."""
    root = ET.parse(svg_path).getroot()
    view_box = [float(v) for v in root.get("viewBox").split()]
    clips = {}
    for clip in root.iter(f"{{{SVG_NS}}}clipPath"):
        (cp,) = clip.findall(f"{{{SVG_NS}}}path")
        clips[clip.get("id")] = path_bbox(parse_path(cp.get("d")))

    shapes = []

    def walk(node, clip_box):
        for child in node:
            tag = child.tag.split("}")[1]
            if tag in ("defs", "clipPath"):
                continue
            if child.get("transform"):
                raise ValueError("transforms are not handled; the converted SVG has one")
            box = clip_box
            ref = child.get("clip-path")
            if ref:
                box = clips[re.fullmatch(r"url\(#(.+)\)", ref).group(1)]
            if tag == "g":
                walk(child, box)
            elif tag == "path":
                if child.get("fill-opacity", "1") != "1" or child.get("fill-rule", "nonzero") != "nonzero":
                    raise ValueError("unexpected fill-opacity or fill-rule")
                d = child.get("d")
                subpaths = parse_path(d)
                if box:
                    # pdftocairo wraps some shapes in a clip that is just their bounding box.
                    # Dropping it is safe only if the shape lies entirely inside.
                    x0, y0, x1, y1 = path_bbox(subpaths)
                    eps = 0.01
                    if x0 < box[0] - eps or y0 < box[1] - eps or x1 > box[2] + eps or y1 > box[3] + eps:
                        raise ValueError("a clip path actually clips its shape; not handled")
                shapes.append((parse_fill(child.get("fill")), subpaths, d))
            else:
                raise ValueError(f"unexpected element <{tag}>")

    walk(root, None)
    return view_box, shapes


def find_wheel(shapes, wedge_box):
    """Return the wheel's (center, outer radius).

    The wheel is one dark shape (horizontal logo) or two halves split by the spoke (square
    logos). Its pieces are the dark shapes with a square bounding box, at least a third as wide as
    the wedges together, that overlap the wedges. Letters are too small and the body isn't square.
    """
    wx0, wy0, wx1, wy1 = wedge_box
    halves = []
    for fill, subpaths, _ in shapes:
        if fill not in DARK_FILLS:
            continue
        x0, y0, x1, y1 = path_bbox(subpaths)
        w, h = x1 - x0, y1 - y0
        square = abs(w - h) < 0.02 * max(w, h)
        big = w > 0.33 * (wx1 - wx0)
        overlaps = x0 < wx1 and x1 > wx0 and y0 < wy1 and y1 > wy0
        if square and big and overlaps:
            halves.append((x0, y0, x1, y1))
    if len(halves) not in (1, 2):
        raise ValueError(f"expected the wheel in one or two pieces, found {len(halves)} candidates")
    x0 = min(b[0] for b in halves)
    y0 = min(b[1] for b in halves)
    x1 = max(b[2] for b in halves)
    y1 = max(b[3] for b in halves)
    if abs((x1 - x0) - (y1 - y0)) > 0.01 * (x1 - x0):
        raise ValueError("the wheel's pieces don't make a circle")
    return ((x0 + x1) / 2, (y0 + y1) / 2), (x1 - x0) / 2


def hex_of(rgb_percent):
    return "#%02X%02X%02X" % tuple(round(v * 2.55) for v in rgb_percent)


def snap_color(rgb_percent):
    """The full-color fill a shape should get: the nearest allowed color, within 4 units per channel.

    Example: snap_color((92.2, 45.1, 30.2)) -> "#EB724E" (the file stores #EA734D).
    """
    rgb = [v * 2.55 for v in rgb_percent]

    def distance(h):
        return max(abs(int(h[k:k + 2], 16) - c) for k, c in zip((1, 3, 5), rgb))

    best = min(FULL_COLOR_FILLS, key=distance)
    if distance(best) > 4:
        raise ValueError(f"fill {hex_of(rgb_percent)} is not a brand color; not snapping it")
    return best


def load_logo(ai_path):
    """Convert an .ai file with pdftocairo and return (viewBox, shapes); see load_shapes."""
    with tempfile.TemporaryDirectory() as tmp:
        svg_path = os.path.join(tmp, "logo.svg")
        subprocess.run([tool("pdftocairo"), "-svg", ai_path, svg_path], check=True)
        return load_shapes(svg_path)


def render_svg(view_box, shapes, color, keyline, crop, title):
    """Return SVG text for a logo: one color if `color` is a hex code, full color if None.

    `keyline` (single color only) cuts the wedges back from the wheel; `crop` trims the viewBox
    to the artwork.
    """
    wedges = [k for k, (fill, _, _) in enumerate(shapes) if fill not in DARK_FILLS]
    if len(wedges) != 3:
        raise ValueError(f"expected 3 sidewalk wedges, found {len(wedges)}")

    ds = [d.strip() for _, _, d in shapes]
    if crop:
        # Measured before the keyline, which only removes area the wheel already covers.
        boxes = [path_bbox(subpaths) for _, subpaths, _ in shapes]
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        view_box = [x0, y0, x1 - x0, y1 - y0]

    if keyline and color:
        boxes = [path_bbox(shapes[k][1]) for k in wedges]
        wedge_box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                     max(b[2] for b in boxes), max(b[3] for b in boxes))
        center, radius = find_wheel(shapes, wedge_box)
        cut = radius * (1 + KEYLINE_RATIO)
        for k in wedges:
            ds[k] = keyline_wedge(shapes[k][1], center, cut)

    if color:
        body = [f'  <g fill="{color}">', *[f'    <path d="{d}"/>' for d in ds], "  </g>"]
    else:
        body = [f'  <path fill="{snap_color(fill)}" d="{d}"/>'
                for (fill, _, _), d in zip(shapes, ds)]

    vb = " ".join(fmt(v) for v in view_box)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(view_box[2])}" '
        f'height="{fmt(view_box[3])}" viewBox="{vb}" role="img" aria-labelledby="title">',
        f'  <title id="title">{title}</title>',
        *body,
        "</svg>",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------
# Tools and output
# --------------------------------------------------------------------------------------------

def tool(name):
    found = shutil.which(name)
    if found:
        return found
    if name == "inkscape":
        for p in (r"C:\Program Files\Inkscape\bin\inkscape.com",
                  "/Applications/Inkscape.app/Contents/MacOS/inkscape"):
            if os.path.exists(p):
                return p
    sys.exit(f"{name} not found; install it or put it on PATH")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def export_png(svg_path, size, out_dir, stem):
    """Export a transparent PNG at `size` (width, height or None) named with its pixel size."""
    width, height = size
    tmp_png = os.path.join(out_dir, f"{stem}_tmp.png")
    extra = [f"--export-height={height}"] if height else []
    subprocess.run([tool("inkscape"), svg_path, "--export-type=png", f"--export-width={width}",
                    *extra, f"--export-filename={tmp_png}"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w, h = png_size(tmp_png)
    final = os.path.join(out_dir, f"{stem}_{w}x{h}.png")
    os.replace(tmp_png, final)
    return final


def shown(path):
    """Path relative to this folder when possible, for the progress listing."""
    try:
        return os.path.relpath(path, HERE)
    except ValueError:  # a different drive on Windows
        return path


def write_svg(text, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(shown(path))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", help="write all files under this folder instead of next to each .ai")
    ap.add_argument("--no-keyline", action="store_true",
                    help="single colors as a plain recolor: let the wheel merge into the wedges")
    args = ap.parse_args()
    title = "Project Sidewalk logo"

    for logo in LOGOS:
        ai = os.path.join(HERE, logo["ai"])
        base = args.out or os.path.dirname(ai)
        crop = logo.get("crop", False)
        view_box, shapes = load_logo(ai)

        svg_path = os.path.join(base, f"{logo['stem']}.svg")
        write_svg(render_svg(view_box, shapes, None, False, crop, title), svg_path)
        if logo.get("color_pngs"):
            for size in logo["sizes"]:
                print(shown(export_png(svg_path, size, base, logo["stem"])))

        for name, color in COLORS.items():
            out_dir = os.path.join(base, "Monochrome", name)
            stem = f"{logo['stem']}_{name}"
            svg_path = os.path.join(out_dir, f"{stem}.svg")
            write_svg(render_svg(view_box, shapes, color, not args.no_keyline, crop, title),
                      svg_path)
            for size in logo["sizes"]:
                print(shown(export_png(svg_path, size, out_dir, stem)))


if __name__ == "__main__":
    main()
