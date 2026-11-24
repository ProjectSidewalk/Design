# Tool logos

One mark for each Project Sidewalk tool: **AccessScore**, **Gallery**, **Label Map** and **Reports**. The four are
drawn as one family from the Project Sidewalk v2 logo's four colors and its wheel. They were designed and picked in
[SidewalkWebpage#5958](https://github.com/ProjectSidewalk/SidewalkWebpage/issues/5958) (November 2026) and first
shipped in [SidewalkWebpage#5965](https://github.com/ProjectSidewalk/SidewalkWebpage/pull/5965), where each one
heads its tool's left sidebar.

| AccessScore | Gallery | Label Map | Reports |
|:---:|:---:|:---:|:---:|
| <img src="Final/access-score.svg" width="96" alt="AccessScore logo"> | <img src="Final/gallery.svg" width="96" alt="Gallery logo"> | <img src="Final/label-map.svg" width="96" alt="Label Map logo"> | <img src="Final/reports.svg" width="96" alt="Reports logo"> |
| **A26**: a patchwork of five neighborhoods colored by score, with the logo's wheel where they meet | **G19**: two stacked photo frames showing a sidewalk on green ground, with an orange label pin | **L0**: a folded map with an asphalt pin | **R12**: a tri-fold with the logo's wheel, a chart and a findings list on its panels |

## Files

- `Final/*.svg`: the masters, hand-optimised and drawn on a 64-unit grid (`viewBox="0 0 64 64"`). These are
  byte-identical to `public/images/logos/tools/` in SidewalkWebpage, which is what the site serves.
- `Final/PNG/`: square exports at 16, 32, 64, 256 and 1024 px with transparent backgrounds, rendered from the SVGs
  with Inkscape (first rendered with resvg; re-rendered with Inkscape when the colors changed). Regenerate them
  from the SVGs if a master changes.

## Usage

- **Pair a mark with its tool's name** in Raleway ExtraBold. On the website that lockup is one component
  (`@common.toolHeader`), documented in SidewalkWebpage's `docs/style-guide.md` under "Tool logos".
- **"AccessScore" is a wordmark** and is never translated. "Gallery", "Label Map" and "Reports" are ordinary words and
  are translated.
- **These marks are drawn for light backgrounds.** On asphalt the white outlines keep all four readable, but Gallery's
  frames and the other asphalt parts merge into the background. No dark variant exists yet; draw one before a mark
  goes on a dark surface.

## Colors

| Role | Token | Hex |
|---|---|---|
| Asphalt | `--color-asphalt-500` | `#2D2A3F` |
| Green | `--color-pine-500` | `#78C9AB` |
| Yellow | `--color-banana-500` | `#FBD98C` |
| Orange | `--color-orange-500` | `#EB724E` |

These are the design-system tokens in SidewalkWebpage's `frontend/css/main.css`, which this repo's top-level README now
uses as the palette. The marks were first drawn in the v2 logo's file colors (`#78C8AA`, `#FAD68A`, `#EA734D`), a
unit or so off from the tokens, and were recolored to match them
([Design#5](https://github.com/ProjectSidewalk/Design/issues/5)).

## Design process

The exploration ran in seven rounds, with about 36 first ideas (coded A0–A8, G0–G8, L0–L8 and R0–R8) and then riffs
on the ones shortlisted. The issue records each round and the reasoning behind each pick:

1. **Directions**: three family systems (a three-part mark, a mark on the logo's fan, a tile).
2. **Ideas**: nine divergent ideas per tool.
3. **Riffs on picks**: A9–A12, G9–G12, R9–R12.
4. **Shortlist**: bolder versions of G9 (G13–G16), checked down to 16 px.
5. **Frames and AccessScore**: thinner Gallery frames (G17–G19); AccessScore built from parts of the logo
   (A13–A18).
6. **AccessScore patchwork**: neighborhood patchworks (A19–A24); A8 with the wheel at the logo's circle size
   (A25, A26).
7. **Gallery pin color**: orange versus asphalt pin (G20, G21).

The rounds were drawn on a design canvas outside GitHub. The intermediate drawings are not yet archived here
(`Ideation/` is reserved for them).
