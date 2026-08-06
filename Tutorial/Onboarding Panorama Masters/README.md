# Onboarding panorama masters

The pre-tiling source images behind the Explore tutorial's two local panoramas (pano ids `tutorial` and
`afterWalkTutorial`). The live app no longer serves these directly — it requests pre-cut tile sets from
`public/images/pano-tutorial/tutorial/` and `public/images/pano-tutorial/afterwalktutorial/` in
[SidewalkWebpage](https://github.com/ProjectSidewalk/SidewalkWebpage) — but these masters are kept here so the
tutorial panorama can be re-cropped, re-tiled, or otherwise revisited without redoing the original capture/edit.

| file | size | role |
|---|---|---|
| `tutorial.png` | 74.7 MB | full-resolution master, pano `tutorial` |
| `afterwalktutorial.png` | 68.3 MB | full-resolution master, pano `afterWalkTutorial` |
| `tutorialSmall.jpg` | 5.4 MB | 4096×2048 downscale, pano `tutorial` |
| `afterwalktutorialsmall.jpg` | 5.1 MB | 4096×2048 downscale, pano `afterWalkTutorial` |

Moved out of the webpage repo in [SidewalkWebpage#4785](https://github.com/ProjectSidewalk/SidewalkWebpage/pull/4785)
(they shipped in every deploy for years without ever being requested by the tutorial). They remain recoverable
byte-identically from that repo's git history — see the PR and its `91b056224` commit message for the exact
`git show <rev>:<path>` commands.
