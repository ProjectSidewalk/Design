#!/usr/bin/env python3
"""
Rebuild the 25 achievement badge SVGs from the Illustrator files in this folder.

The .ai files are PDFs underneath, and each one holds all five levels of a track as layers named
Badge1..Badge5. For each badge we switch on just that one layer, export it to SVG, swap the old
Segoe number for one set in Mulish (the site's font), and redraw the few bits of artwork that were
saved as pictures (the capes, the level-5 clipboard) as real shapes.

Usage:
  python3 build_badges.py --out <Sidewalk checkout>/public/images/badges \
                          --mulish <Sidewalk checkout>/public/fonts/Mulish/Mulish-latin.woff2

Needs: poppler's pdftocairo, and the Python packages pikepdf, fonttools, brotli, numpy, pillow,
potracer.
"""

import argparse
import base64
import collections
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pikepdf
import potrace
from PIL import Image, ImageFilter
from fontTools.misc.transform import Offset
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))

# Per track: the .ai file, which PDF page holds the artwork we ship, what each level's number says
# in the file today, and what it should say. Distance is only drawn in kilometres, so the mile
# badges reuse that artwork with a different label.
TRACKS = [
    {
        "stem": "labels",
        "ai": "badge_labels.ai",
        "page": 1,
        "old": ["50", "250", "500", "1k", "5k"],
        "new": ["50", "200", "500", "1k", "2k"],
        # Level 4's laurels stay where they're drawn, with the number level with them.
        "laurels": {4: {"mode": "keep"}},
    },
    {
        "stem": "missions",
        "ai": "badge_missions.ai",
        "page": 1,
        "old": ["5", "10", "20", "50", "100"],
        "new": ["5", "25", "75", "150", "250"],
        # Level 5 in the .ai is the old no-cape design, but the badge we ship has level 4's cape,
        # nudged over and up a little (offset measured off the shipped PNGs).
        "borrow_cape": {5: {"from": 4, "shift": (1.98, -2.31)}},
        # "150" is too wide to sit between laurels on level 4's ribbon at a readable size, so the
        # ribbons are drawn this much wider on each side (on every level, so they all match).
        "widen_ribbon": {level: 6.0 for level in range(1, 6)},
        "laurels": {4: {"mode": "hug", "scale": 1.0}},
    },
    {
        "stem": "validation",
        "ai": "badge_validation.ai",
        "page": 1,
        "old": ["100", "250", "500", "1k", "5k"],
        "new": ["100", "250", "500", "1k", "5k"],
        # Level 4's laurels stay where they're drawn, with the number level with them.
        "laurels": {4: {"mode": "keep"}},
    },
    {
        "stem": "distance_km",
        "ai": "badge_distance.ai",
        "page": 2,
        "old": ["0.15 km", "0.4 km", "0.8 km", "1.6 km", "8 km"],
        "new": ["1 km", "3 km", "8 km", "15 km", "30 km"],
        # Levels 4 and 5 flank the number with laurels; draw them a fifth bigger than in the .ai and
        # fit them snugly around the new label.
        "laurels": {4: {"mode": "hug", "scale": 1.2}, 5: {"mode": "hug", "scale": 1.2}},
    },
    {
        "stem": "distance",
        "ai": "badge_distance.ai",
        "page": 2,
        "old": ["0.15 km", "0.4 km", "0.8 km", "1.6 km", "8 km"],
        "new": ["0.5 mi", "2 mi", "5 mi", "10 mi", "20 mi"],
        # Levels 4 and 5 flank the number with laurels; draw them a fifth bigger than in the .ai and
        # fit them snugly around the new label.
        "laurels": {4: {"mode": "hug", "scale": 1.2}, 5: {"mode": "hug", "scale": 1.2}},
    },
]

# Gap left between the number and whatever sits beside it (laurels, the edge of a ribbon), as a
# fraction of the number's height.
PAD = 0.07

# How wide the space between a number and its unit is, as a share of Mulish's normal space.
UNIT_GAP = 0.5

# Resolution the badge is drawn at when measuring how much room the number has.
MEASURE_DPI = 600


# ---- Illustrator layers ---------------------------------------------------------------------------

def isolate_layer(ai_path, layer, out_pdf):
    """Write a copy of the .ai with only `layer` switched on."""
    pdf = pikepdf.open(ai_path)
    groups = list(pdf.Root.OCProperties.OCGs)
    on = [g for g in groups if str(g.Name) == layer]
    off = [g for g in groups if str(g.Name) != layer]
    if not on:
        raise SystemExit("%s has no layer %r (has %s)" % (ai_path, layer, [str(g.Name) for g in groups]))
    pdf.Root.OCProperties.D.ON = pdf.make_indirect(pikepdf.Array(on))
    pdf.Root.OCProperties.D.OFF = pdf.make_indirect(pikepdf.Array(off))
    pdf.save(out_pdf)


def to_svg(pdf_path, page, out_svg):
    subprocess.run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page), pdf_path, out_svg],
                   check=True, capture_output=True)


def to_png_without_text(pdf_path, page, out_stem):
    """Draw the badge with all its text removed, for measuring the space around the number."""
    pdf = pikepdf.open(pdf_path)
    pg = pdf.pages[page - 1]
    # Only drop the operators that draw letters: Illustrator also puts other artwork inside text
    # blocks, so removing whole blocks would erase the laurels too.
    kept = [(operands, op) for operands, op in pikepdf.parse_content_stream(pg)
            if str(op) not in ("Tj", "TJ", "'", '"')]
    pg.Contents = pdf.make_stream(pikepdf.unparse_content_stream(kept))
    bare = out_stem + "-bare.pdf"
    pdf.save(bare)
    subprocess.run(["pdftocairo", "-png", "-r", str(MEASURE_DPI), "-singlefile", "-f", str(page),
                    "-l", str(page), bare, out_stem], check=True, capture_output=True)
    return Image.open(out_stem + ".png").convert("RGB")


# ---- SVG path bounds ------------------------------------------------------------------------------

NUM = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def cubic_extrema(p0, p1, p2, p3):
    """The lowest and highest a curve actually reaches on one axis, not just its control points."""
    lo, hi = min(p0, p3), max(p0, p3)
    a = -p0 + 3 * p1 - 3 * p2 + p3
    b = 2 * (p0 - 2 * p1 + p2)
    c = p1 - p0
    if abs(a) < 1e-12:
        roots = [-c / b] if abs(b) > 1e-12 else []
    else:
        disc = b * b - 4 * a * c
        roots = [] if disc < 0 else [(-b + s * disc ** 0.5) / (2 * a) for s in (1, -1)]
    for t in roots:
        if 0 < t < 1:
            mt = 1 - t
            v = mt ** 3 * p0 + 3 * mt ** 2 * t * p1 + 3 * mt * t * t * p2 + t ** 3 * p3
            lo, hi = min(lo, v), max(hi, v)
    return lo, hi


def path_bbox(d):
    """Exact ink bounds of a path as cairo writes it (only M/L/C/Z ever appear)."""
    toks = re.findall(r"[MLCZmlcz]|" + NUM.pattern, d)
    x0 = y0 = float("inf")
    x1 = y1 = float("-inf")
    cx = cy = sx = sy = 0.0
    i = 0

    def hit(x, y):
        nonlocal x0, y0, x1, y1
        x0, y0 = min(x0, x), min(y0, y)
        x1, y1 = max(x1, x), max(y1, y)

    while i < len(toks):
        op = toks[i]
        i += 1
        if op in "Mm":
            cx, cy = float(toks[i]), float(toks[i + 1])
            sx, sy = cx, cy
            i += 2
            hit(cx, cy)
        elif op in "Ll":
            cx, cy = float(toks[i]), float(toks[i + 1])
            i += 2
            hit(cx, cy)
        elif op in "Cc":
            p = [float(v) for v in toks[i:i + 6]]
            i += 6
            bx = cubic_extrema(cx, p[0], p[2], p[4])
            by = cubic_extrema(cy, p[1], p[3], p[5])
            hit(bx[0], by[0])
            hit(bx[1], by[1])
            cx, cy = p[4], p[5]
        elif op in "Zz":
            cx, cy = sx, sy
    return x0, y0, x1, y1


# ---- Mulish ---------------------------------------------------------------------------------------

class Mulish:
    def __init__(self, path, weight):
        self.font = instancer.instantiateVariableFont(TTFont(path), {"wght": weight}, inplace=False)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.hmtx = self.font["hmtx"]

    def run(self, text, gap=None):
        """Outline `text` as one path in font units; also return its ink bounds and digit height."""
        pen = SVGPathPen(self.glyphs)
        bounds = BoundsPen(self.glyphs)
        digits = BoundsPen(self.glyphs)
        x = 0.0
        for ch in text:
            if ord(ch) not in self.cmap:
                raise SystemExit("Mulish has no glyph for %r" % ch)
            name = self.cmap[ord(ch)]
            self.glyphs[name].draw(TransformPen(pen, Offset(x, 0)))
            self.glyphs[name].draw(TransformPen(bounds, Offset(x, 0)))
            if ch.isdigit():
                self.glyphs[name].draw(TransformPen(digits, Offset(x, 0)))
            # A full-width space pushes the unit ("km", "mi") too far from its number for these tight
            # badges; half of one reads as a single label.
            x += self.hmtx[name][0] * ((UNIT_GAP if gap is None else gap) if ch == " " else 1)
        ref = digits.bounds or bounds.bounds
        return pen.getCommands(), bounds.bounds, ref[3] - ref[1]


# ---- room around the number -----------------------------------------------------------------------

def free_space(img, ink, band, reach):
    """
    The box the new number can fill without touching other artwork (laurels, a ribbon's edges).

    `img` is the badge drawn with its text taken out. Starting from the middle of where the old
    number sat, walk outwards (left and right along every row the number covered, up and down along
    every column) until the colour changes from the background there. Returns left, right, top and
    bottom limits in SVG units.
    """
    k = MEASURE_DPI / 72.0
    arr = np.asarray(img).astype(int)
    h, w, _ = arr.shape
    x0, x1 = max(0, int(ink[0] * k)), min(w - 1, int(ink[2] * k))
    y0, y1 = max(0, int(band[0] * k)), min(h - 1, int(band[1] * k))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    far = int(reach * k)
    near = [tuple(arr[y, x]) for y in range(y0, y1 + 1, 4) for x in range(x0, x1 + 1, 4)]
    bg = np.array(collections.Counter(near).most_common(1)[0][0])

    def first_hit(lines, start, direction, horizontal):
        size = w if horizontal else h
        steps = np.arange(far) * direction + start
        steps = steps[(steps >= 0) & (steps < size)]
        lines = np.array(list(lines))
        strip = arr[np.ix_(lines, steps)] if horizontal else arr[np.ix_(steps, lines)].swapaxes(0, 1)
        differs = np.abs(strip - bg).sum(axis=2) > 90
        hit = differs.any(axis=1)
        nearest = differs.argmax(axis=1)[hit].min() if hit.any() else far
        return (start + direction * nearest) / k

    rows, cols = range(y0, y1 + 1), range(x0, x1 + 1)
    return (first_hit(rows, cx, -1, True), first_hit(rows, cx, 1, True),
            first_hit(cols, cy, -1, False), first_hit(cols, cy, 1, False))


# ---- number replacement ---------------------------------------------------------------------------

# Cairo writes the number either as one <use> per digit in its own filled <g>, or as a run of <use>s
# sharing one, so find the glyphs themselves and read the colour off whatever wraps them.
GLYPH_USE = re.compile(r'\s*<use xlink:href="#(?P<gid>glyph[\w-]+)" x="(?P<x>[-\d.]+)" y="(?P<y>[-\d.]+)"/>')
FILL_G = re.compile(r'<g style="fill:([^"]*)"[^>]*>')


def old_label(svg, old_text):
    """Where the old number sits: its glyphs, full ink box, digit top/bottom, baseline and colour."""
    symbols = dict(re.findall(r'<symbol[^>]*id="([^"]+)"[^>]*>\s*<path[^>]*\bd="([^"]*)"', svg))
    hits = list(GLYPH_USE.finditer(svg))
    if len(hits) != len(old_text):
        raise SystemExit("expected %d glyphs for %r, found %d" % (len(old_text), old_text, len(hits)))

    ink = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    dig = [float("inf"), float("-inf")]
    for ch, m in zip(old_text, hits):
        d = symbols.get(m.group("gid"))
        if not d:
            continue
        bx0, by0, bx1, by1 = path_bbox(d)
        if bx0 == float("inf"):
            continue  # the space has no ink
        gx, gy = float(m.group("x")), float(m.group("y"))
        ink = [min(ink[0], bx0 + gx), min(ink[1], by0 + gy), max(ink[2], bx1 + gx), max(ink[3], by1 + gy)]
        if ch.isdigit():
            dig = [min(dig[0], by0 + gy), max(dig[1], by1 + gy)]

    wrappers = list(FILL_G.finditer(svg[:hits[0].start()]))
    return {
        "hits": hits,
        "ink": ink,
        "digits": dig if dig[0] != float("inf") else [ink[1], ink[3]],
        "baseline": float(hits[0].group("y")),
        "fill": wrappers[-1].group(1) if wrappers else "rgb(0%,0%,0%);fill-opacity:1;",
    }


def fit_label(old, new_text, mulish, img, reserve=0.0, size_like_full_gap=False, lift=0.0, shrink=1.0,
              centre=None):
    """
    Size and place the new number in the free space around the old one. `reserve` is width to keep
    clear on each side (for laurels that will be moved in beside it). Returns the drawing and the
    box the number's ink will fill. With `size_like_full_gap`, the number is sized as if it had a
    full-width space before its unit, so tightening that space frees room beside it rather than
    making the number bigger. `lift` raises the number by that much; `shrink` scales it down.
    `centre` is the height the middle of the digits should sit at, if not on the old baseline.
    """
    digit_h = old["digits"][1] - old["digits"][0]
    left, right, ceiling, floor = free_space(img, old["ink"], old["digits"], reach=3 * digit_h)
    pad = PAD * digit_h
    left, right = left + reserve, right - reserve

    commands, (nx0, _, nx1, _), new_digit_h = mulish.run(new_text)
    # As tall as the old number, unless that's too wide or too tall for the space it sits in; then
    # just small enough to leave the same padding around it.
    tallest = floor - ceiling - 2 * pad
    scale = min(digit_h, tallest) / new_digit_h
    fx0, fx1 = (mulish.run(new_text, gap=1.0)[1][0::2] if size_like_full_gap else (nx0, nx1))
    scale = min(scale, (right - left - 2 * pad) / (fx1 - fx0)) * shrink
    tx = (left + right) / 2 - scale * (nx0 + nx1) / 2
    baseline = old["baseline"]
    if centre is not None:
        baseline = centre + scale * new_digit_h / 2
    if tallest < digit_h:
        # Squeezed by a box above and below (like a ribbon's plate): centre it top to bottom too.
        baseline = (ceiling + floor) / 2 + scale * new_digit_h / 2
    baseline -= lift
    drawing = ('\n<g style="fill:%s">\n<path style="stroke:none;" d="%s" '
               'transform="matrix(%.6f,0,0,%.6f,%.6f,%.6f)"/>\n</g>'
               % (old["fill"], commands, scale, -scale, tx, baseline))
    box = (tx + scale * nx0, baseline - scale * new_digit_h, tx + scale * nx1, baseline)
    return drawing, box, pad


def swap_label(svg, old, drawing):
    """Replace the old number's glyphs with the new drawing."""
    out, prev = [], 0
    for i, m in enumerate(old["hits"]):
        out.append(svg[prev:m.start()])
        if i == 0:
            out.append(drawing)
        prev = m.end()
    out.append(svg[prev:])
    svg = "".join(out)

    svg = re.sub(r"<symbol[^>]*>.*?</symbol>\s*", "", svg, flags=re.S)
    for _ in range(3):  # the now-empty wrappers the old glyphs sat in, innermost first
        svg = re.sub(r"<g[^>]*>\s*</g>\s*", "", svg)
    return svg


# ---- artwork saved as pictures --------------------------------------------------------------------

IMG_USE = re.compile(r'<use xlink:href="#(?P<color>image\d+)" mask="url\(#(?P<mask>[^)]+)\)"'
                     r'(?: transform="(?P<tf>[^"]*)")?/>')


def decode_images(svg):
    out = {}
    for m in re.finditer(r'<image id="(image\d+)" width="(\d+)" height="(\d+)"[^>]*base64,([^"]+)"', svg):
        out[m.group(1)] = Image.open(io.BytesIO(base64.b64decode(m.group(4))))
    return out


def xy(p):
    return (p.x, p.y) if hasattr(p, "x") else (p[0], p[1])


def trace(mask_img):
    """Outline the solid part of a mask as a path, in the picture's own pixel coordinates."""
    solid = np.array(mask_img.convert("L")) > 128
    # potracer outlines the *dark* pixels, so hand it the solid area as the dark part.
    path = potrace.Bitmap(~solid).trace(turdsize=2, alphamax=1.0, opticurve=True, opttolerance=0.2)
    d = []
    for curve in path:
        d.append("M %.3f %.3f" % xy(curve.start_point))
        for seg in curve:
            if seg.is_corner:
                d.append("L %.3f %.3f L %.3f %.3f" % (xy(seg.c) + xy(seg.end_point)))
            else:
                d.append("C %.3f %.3f %.3f %.3f %.3f %.3f" % (xy(seg.c1) + xy(seg.c2) + xy(seg.end_point)))
        d.append("Z")
    return " ".join(d)


def dominant_color(color_img, mask_img):
    rgb = np.array(color_img.convert("RGB")).reshape(-1, 3)
    keep = (np.array(mask_img.convert("L")) > 128).reshape(-1)
    px = rgb[keep]
    if not len(px):
        return "rgb(0%,0%,0%)"
    packed = (px[:, 0].astype(int) << 16) | (px[:, 1].astype(int) << 8) | px[:, 2].astype(int)
    val = collections.Counter(packed.tolist()).most_common(1)[0][0]
    r, g, b = (val >> 16) & 255, (val >> 8) & 255, val & 255
    return "rgb(%.6f%%,%.6f%%,%.6f%%)" % (r / 2.55, g / 2.55, b / 2.55)


def vectorize_pictures(svg):
    """Swap each masked picture for a traced shape in its main colour, then drop the pictures."""
    images = decode_images(svg)
    if not images:
        return svg, 0
    masks = dict(re.findall(r'<mask id="([^"]+)">\s*<use xlink:href="#(image\d+)"', svg))
    count = 0

    def sub(m):
        nonlocal count
        color_img = images.get(m.group("color"))
        mask_img = images.get(masks.get(m.group("mask"), ""))
        if color_img is None or mask_img is None:
            return m.group(0)
        count += 1
        tf = ' transform="%s"' % m.group("tf") if m.group("tf") else ""
        # evenodd so the holes inside a shape (the clipboard's lines) stay see-through
        return '<path style="stroke:none;fill-rule:evenodd;fill:%s;fill-opacity:1;" d="%s"%s/>' % (
            dominant_color(color_img, mask_img), trace(mask_img), tf)

    svg = IMG_USE.sub(sub, svg)
    svg = re.sub(r'<image id="image\d+"[^>]*/>\s*', "", svg)
    svg = re.sub(r'<mask id="[^"]+">\s*(<use[^>]*/>\s*)?</mask>\s*', "", svg)
    return svg, count


# ---- laurels beside the number --------------------------------------------------------------------

def _wrapped_span(svg, m):
    """Where the path `m` starts and ends, including the clipping groups wrapped tightly around it."""
    start, depth = m.start(), 0
    while True:
        opener = re.search(r"<g\b[^>]*>\s*$", svg[:start])
        if not opener:
            break
        start, depth = opener.start(), depth + 1
    end = m.end()
    for _ in range(depth):
        end += re.match(r"\s*</g>", svg[end:]).end()
    return start, end


def find_sprigs(svg, old):
    """
    The laurel sprigs just left and right of the number: for each side, the spans of its leaves in
    the file and the box around the whole sprig. Each leaf is its own small shape.
    """
    dh = old["digits"][1] - old["digits"][0]
    ink = old["ink"]
    # Clipping outlines live in the same file; blank them out so they aren't mistaken for leaves.
    body = re.sub(r"<clipPath\b.*?</clipPath>", lambda m: " " * len(m.group(0)), svg, flags=re.S)
    sides = {"left": [], "right": []}
    for m in ANY_PATH.finditer(body, body.index('<g id="surface')):
        if "transform=" in m.group(0):
            continue
        x0, y0, x1, y1 = path_bbox(m.group(1))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if max(x1 - x0, y1 - y0) > 0.35 * dh or not old["digits"][0] - 0.25 * dh < cy < old["digits"][1] + 0.25 * dh:
            continue
        if ink[0] - 1.5 * dh < cx < ink[0]:
            sides["left"].append((_wrapped_span(body, m), (x0, y0, x1, y1)))
        elif ink[2] < cx < ink[2] + 1.5 * dh:
            sides["right"].append((_wrapped_span(body, m), (x0, y0, x1, y1)))
    out = {}
    for side, leaves in sides.items():
        if leaves:
            boxes = [b for _, b in leaves]
            out[side] = ([span for span, _ in leaves],
                         (min(b[0] for b in boxes), min(b[1] for b in boxes),
                          max(b[2] for b in boxes), max(b[3] for b in boxes)))
    return out


def hide(img, sprigs):
    """Paint the laurels out of the measuring image, so the number is sized as if they weren't there."""
    k = MEASURE_DPI / 72.0
    arr = np.asarray(img).copy()
    for side, (_, (x0, y0, x1, y1)) in sprigs.items():
        ya, yb, xa, xb = int(y0 * k) - 10, int(y1 * k) + 11, int(x0 * k) - 10, int(x1 * k) + 11
        # The background colour is taken just past the sprig, on the side facing the number.
        probe = xb + 4 if side == "left" else xa - 4
        arr[ya:yb, xa:xb] = arr[(ya + yb) // 2, probe]
    return Image.fromarray(arr)


def plan_laurels(img, bare, sprigs, label_box, pad, ceiling, want):
    """
    How big the laurels can grow (up to `want`) and how far the number must rise, with its laurels
    centred on it, so no leaf comes within `pad` of other artwork. Badges narrow towards the bottom,
    so bigger laurels often need to sit a little higher. Returns (scale, lift).
    """
    k = MEASURE_DPI / 72.0
    step = 8  # check on a smaller copy of the drawing: plenty precise, and fast
    big = np.asarray(img).astype(int)
    lx0, ly0, lx1, ly1 = label_box
    bg = big[int((ly0 + ly1) / 2 * k), int((lx0 + lx1) / 2 * k)]
    small = np.abs(np.asarray(bare).astype(int)[::step, ::step] - bg).sum(axis=2) > 90
    # Grow every obstacle by the padding, so "not overlapping" means "at least `pad` apart".
    grown = np.asarray(Image.fromarray(small.astype(np.uint8) * 255).filter(
        ImageFilter.MaxFilter(2 * int(pad * k / step) + 1))) > 0

    leaves = {}
    for side, (_, (x0, y0, x1, y1)) in sprigs.items():
        crop = big[int(y0 * k):int(y1 * k) + 1, int(x0 * k):int(x1 * k) + 1]
        leaves[side] = (np.abs(crop - bg).sum(axis=2) > 90, (x0, y0, x1, y1))

    def clear(s, lift):
        for side, (mask, (x0, y0, x1, y1)) in leaves.items():
            w, h = (x1 - x0) * s, (y1 - y0) * s
            nx = (lx0 - pad - w) if side == "left" else (lx1 + pad)
            ny = (ly0 + ly1) / 2 - lift - h / 2
            pw, ph = max(1, int(w * k / step)), max(1, int(h * k / step))
            m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((pw, ph))) > 0
            px, py = int(nx * k / step), int(ny * k / step)
            if px < 0 or py < 0 or px + pw > grown.shape[1] or py + ph > grown.shape[0]:
                return False
            if (grown[py:py + ph, px:px + pw] & m).any():
                return False
        return True

    most_lift = max(0.0, ly0 - pad - ceiling)
    for s in np.arange(want, 0.995, -0.02):
        for lift in np.linspace(0.0, most_lift, 41):
            if clear(s, lift):
                return float(s), float(lift)
    return 1.0, 0.0


def rearrange_sprigs(svg, sprigs, how, label_box, pad):
    """
    Take the laurels out (how["mode"] == "remove"), or grow them by how["scale"] and slide them so
    they sit a small gap either side of the new number ("hug"). Either way they end up centred on
    the number top to bottom ("keep" only does that).
    """
    lx0, ly0, lx1, ly1 = label_box
    edits = []
    for side, (spans, (x0, y0, x1, y1)) in sprigs.items():
        if how["mode"] == "remove":
            edits += [(start, end, None) for start, end in spans]
            continue
        s = how.get("scale", 1.0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        inner = x1 if side == "left" else x0  # the sprig's edge facing the number
        target = lx0 - pad if side == "left" else lx1 + pad
        dx = 0.0 if how["mode"] == "keep" else target - (cx + s * (inner - cx))
        dy = (ly0 + ly1) / 2 - cy
        tf = "matrix(%.5f,0,0,%.5f,%.4f,%.4f)" % (s, s, (1 - s) * cx + dx, (1 - s) * cy + dy)
        edits += [(start, end, tf) for start, end in spans]
    for start, end, tf in sorted(edits, key=lambda e: -e[0]):
        if tf is None:
            svg = svg[:start] + svg[end:]
        else:
            svg = svg[:start] + '<g transform="%s">' % tf + svg[start:end] + "</g>" + svg[end:]
    return svg


# ---- a wider ribbon -------------------------------------------------------------------------------

DIAGONAL = re.compile(r'transform="matrix\(([-\d.]+),0,0,([-\d.]+),([-\d.]+),([-\d.]+)\)"')


def widen_ribbon(svg, img, old, dx):
    """
    Make the ribbon the number sits on `dx` wider on each side: cut it down the middle and slide the
    two halves apart, so the plate's top and bottom edges get longer and everything else (its curled
    ends, the tails) keeps its shape. Does the same to the measuring image. Returns both.
    """
    lx0, ly0, lx1, ly1 = old["ink"]
    body = re.sub(r"<clipPath\b.*?</clipPath>", lambda m: " " * len(m.group(0)), svg, flags=re.S)
    # The ribbon is the flattest shape the number sits inside (the badge's body is much taller).
    around = [path_bbox(m.group(1)) for m in ANY_PATH.finditer(body, body.index('<g id="surface'))
              if "transform=" not in m.group(0)]
    around = [b for b in around if b[0] <= lx0 and b[1] <= ly0 and b[2] >= lx1 and b[3] >= ly1]
    rx0, top, rx1, bottom = min(around, key=lambda b: b[3] - b[1])
    mid, top, bottom = (rx0 + rx1) / 2, top - 1, bottom + 1

    def spread(m):
        tag, d = m.group(0), m.group(1)
        tf = DIAGONAL.search(tag)
        sx, sy, ex, ey = (float(v) for v in tf.groups()) if tf else (1.0, 1.0, 0.0, 0.0)
        if "transform=" in tag and not tf:
            return tag  # nothing slanted or rotated sits on the ribbon
        x0, y0, x1, y1 = path_bbox(d)
        y0, y1 = sorted((sy * y0 + ey, sy * y1 + ey))
        # Some clipping shapes poke a little past the ribbon, so allow a few points of slack.
        if y0 < top - 3 or y1 > bottom + 3:
            return tag
        vals = NUM.findall(d)
        # Cairo writes only absolute M/L/C coordinates, so every other number is an x.
        for i in range(0, len(vals), 2):
            x = float(vals[i])
            vals[i] = "%.4f" % (x + (dx if sx * x + ex > mid else -dx) / sx)
        it = iter(vals)
        return tag.replace(d, NUM.sub(lambda _: next(it), d))

    # The ribbon's pieces, and the rectangles that clip them.
    svg = re.sub(r'<path[^>]*\bd="([^"]*)"[^>]*/>', spread, svg)

    k = MEASURE_DPI / 72.0
    arr = np.asarray(img).copy()
    r0, r1, c, s = int(top * k), int(bottom * k) + 1, int(mid * k), int(round(dx * k))
    band = arr[r0:r1].copy()
    arr[r0:r1, :c - s] = band[:, s:c]
    arr[r0:r1, c + s:] = band[:, c:-s]
    arr[r0:r1, c - s:c + s] = band[:, c:c + 1]
    return svg, Image.fromarray(arr)


TRACED = re.compile(r'<path style="stroke:none;fill-rule:evenodd;[^"]*" d="[^"]*"(?: transform="[^"]*")?/>')
ANY_PATH = re.compile(r'<path[^>]*\bd="([^"]*)"[^>]*/>')


def lift_cape(src_svg):
    """Another level's traced cape, plus the outline of the shape drawn straight after it."""
    cape = TRACED.search(src_svg)
    following = ANY_PATH.search(src_svg, cape.end())
    return cape.group(0), path_bbox(following.group(1))


def insert_cape(svg, cape, following_bbox, shift):
    """
    Draw a borrowed cape into this badge at the same point in the stacking order it had in its own
    badge: just before this badge's copy of the shape that came after it (the rider), so it sits on
    top of the laurels but behind the rider.
    """
    for m in ANY_PATH.finditer(svg, svg.index('<g id="surface')):
        if all(abs(a - b) < 3 for a, b in zip(path_bbox(m.group(1)), following_bbox)):
            pos = m.start()
            # Step outside any clipping groups that wrap the rider, so they don't clip the cape.
            while True:
                before = svg[:pos].rstrip()
                opener = re.search(r'<g\b[^>]*>$', before)
                if not opener:
                    break
                pos = opener.start()
            g = '<g transform="translate(%.3f,%.3f)">\n%s\n</g>\n' % (shift[0], shift[1], cape)
            return svg[:pos] + g + svg[pos:]
    raise SystemExit("couldn't find where the borrowed cape belongs")


# ---- tidy -----------------------------------------------------------------------------------------

def shrink(svg, places=2):
    """Cairo writes six decimal places; two is already finer than any of these outlines can show."""
    def cut(m):
        out = ("%.*f" % (places, round(float(m.group(0)), places))).rstrip("0").rstrip(".")
        return out if out not in ("", "-", "-0") else "0"

    # Only outlines. A transform's scale multiplies everything under it (the number is drawn in font
    # units at a scale of about 0.02), so rounding one would visibly resize what it holds.
    return re.sub(r'\b(d|points)="([^"]*)"',
                  lambda m: '%s="%s"' % (m.group(1), NUM.sub(cut, m.group(2))), svg)


def tidy(svg, title):
    # Only the <svg> element's version attribute, not the one in the XML declaration above it.
    svg = re.sub(r'(<svg\b[^>]*?)\s*version="[\d.]+"', r"\1", svg, count=1)
    svg = re.sub(r'width="([\d.]+)pt" height="([\d.]+)pt"', r'width="\1" height="\2"', svg)
    svg = svg.replace("<defs>\n</defs>\n", "")
    svg = re.sub(r"\n{2,}", "\n", svg)
    return svg.replace("<svg ", '<svg role="img" aria-label="%s" ' % title, 1)


# ---- main -----------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="folder to write the 25 SVGs into")
    ap.add_argument("--mulish", required=True, help="path to Mulish-latin.woff2 (the variable font)")
    ap.add_argument("--weight", type=float, default=800.0, help="Mulish weight for the numbers")
    ap.add_argument("--only", help="just build badges whose name contains this, e.g. distance_badge5")
    args = ap.parse_args()

    mulish = Mulish(args.mulish, args.weight)
    tmp = tempfile.mkdtemp(prefix="badges-")
    os.makedirs(args.out, exist_ok=True)
    written = traced = 0
    try:
        for track in TRACKS:
            ai = os.path.join(HERE, track["ai"])
            for level in range(1, 6):
                name = "badge_%s_badge%d" % (track["stem"], level)
                if args.only and args.only not in name:
                    continue
                old_text, new_text = track["old"][level - 1], track["new"][level - 1]

                pdf = os.path.join(tmp, name + ".pdf")
                raw = os.path.join(tmp, name + ".svg")
                isolate_layer(ai, "Badge%d" % level, pdf)
                to_svg(pdf, track["page"], raw)
                img = to_png_without_text(pdf, track["page"], os.path.join(tmp, name))

                svg = open(raw).read()
                svg, n = vectorize_pictures(svg)

                borrow = track.get("borrow_cape", {}).get(level)
                if borrow:
                    src_pdf, src_svg = os.path.join(tmp, "src.pdf"), os.path.join(tmp, "src.svg")
                    isolate_layer(ai, "Badge%d" % borrow["from"], src_pdf)
                    to_svg(src_pdf, track["page"], src_svg)
                    cape, following = lift_cape(vectorize_pictures(open(src_svg).read())[0])
                    svg = insert_cape(svg, cape, following, borrow["shift"])
                    n += 1
                old = old_label(svg, old_text)
                widen = track.get("widen_ribbon", {}).get(level)
                if widen:
                    svg, img = widen_ribbon(svg, img, old, widen)
                    old = old_label(svg, old_text)
                how = track.get("laurels", {}).get(level)
                if how:
                    sprigs = find_sprigs(svg, old)
                    bare = hide(img, sprigs)
                    if how.get("overflow") or how["mode"] == "remove":
                        # The number takes the laurels' space; any laurels go outside it.
                        drawing, box, pad = fit_label(old, new_text, mulish, bare)
                    elif how["mode"] == "keep":
                        # The laurels stay put and the number sits level with them.
                        mid = sum(b[1] + b[3] for _, b in sprigs.values()) / (2 * len(sprigs))
                        drawing, box, pad = fit_label(old, new_text, mulish, img, centre=mid)
                    else:
                        # The number keeps its size between the laurels; the laurels grow into what
                        # the tighter unit spacing frees, up to the badge's edge.
                        dh = old["digits"][1] - old["digits"][0]
                        ceiling = free_space(img, old["ink"], old["digits"], reach=3 * dh)[2]
                        want = how.get("scale", 1.0)
                        # Only if the laurels can't reach their size otherwise, let the number give up
                        # a little of its size to them.
                        mid = sum(old["digits"]) / 2
                        for smaller in (1.0, 0.97, 0.94, 0.91, 0.88):
                            drawing, box, pad = fit_label(old, new_text, mulish, img, size_like_full_gap=True,
                                                          shrink=smaller, centre=mid)
                            grow, lift = plan_laurels(img, bare, sprigs, box, pad, ceiling, want)
                            if grow >= want - 0.021:
                                break
                        drawing, box, pad = fit_label(old, new_text, mulish, img, size_like_full_gap=True,
                                                      lift=lift, shrink=smaller, centre=mid)
                        how = dict(how, scale=grow)
                    svg = rearrange_sprigs(svg, sprigs, how, box, pad)
                    old = old_label(svg, old_text)
                else:
                    drawing, _, _ = fit_label(old, new_text, mulish, img)
                svg = swap_label(svg, old, drawing)
                svg = tidy(shrink(svg), "%s badge, level %d" % (track["stem"].replace("_", " "), level))

                with open(os.path.join(args.out, name + ".svg"), "w") as fh:
                    fh.write(svg)
                written += 1
                traced += n
                print("%-32s %-8s -> %-8s %s" % (name + ".svg", old_text, new_text, "traced %d" % n if n else ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n%d SVGs written to %s (%d pictures redrawn as shapes)" % (written, args.out, traced))


if __name__ == "__main__":
    sys.exit(main())
