# Mobility-aid icons

<img src="MobilityAids_Preview.png" width="720" alt="Five line icons in a row: a walking cane, a walker, a mobility scooter, a manual wheelchair and a motorized wheelchair">

Five icons for the mobility aids in Project Sidewalk's research on personalized accessibility maps: walking cane, walker, mobility scooter, manual wheelchair and motorized wheelchair. Each shows the aid, not a person using it.

## Credit
The icons were designed by **[Chu Li](https://makeabilitylab.cs.washington.edu/member/chuli/)** for Figure 1 of her CHI 2025 paper:

> Chu Li, Rock Yuren Pang, Delphine Labbé, Yochai Eisenberg, Maryam Hosseini, and Jon E. Froehlich. 2025. [Accessibility for Whom? Perceptions of Sidewalk Barriers Across Disability Groups and Implications for Designing Personalized Maps](https://doi.org/10.1145/3706598.3713421). In *CHI Conference on Human Factors in Computing Systems (CHI '25)*, April 26-May 1, 2025, Yokohama, Japan. ACM, New York, NY, USA, 19 pages.

The paper is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). When you use these icons, credit Chu Li, cite the paper, and say that the icons were adapted from it.

## What changed from the original
In the figure, each icon is a dark line with pale fills in the wheels. The versions here were adapted from it by the Project Sidewalk team in November 2026. They are cut from the 4096-pixel-wide image of the figure that Chu used in her CHI 2025 talk slides ([Source/Li_CHI2025_Figure1_4096px.jpg](Source/Li_CHI2025_Figure1_4096px.jpg)), where each icon is about 230 pixels across. The figure as it appears in the paper, where each icon is about 100 pixels across, is in [Source/Li_CHI2025_Figure1.png](Source/Li_CHI2025_Figure1.png) for reference. What changed:

- **One color on a transparent background.** The pale fills are gone, so an icon can take any color.
- **Larger, with a cleaned-up line.** Each icon is 480 × 480 pixels.
- **Centered in a square**, with the same margin, so the five line up in a row.

The shapes and proportions are Chu's. Nothing was redrawn.

## Files
| Mobility aid | White (for dark backgrounds) | Navy `#2D2A3F` (for light backgrounds) |
| :--- | :--- | :--- |
| Walking cane | [MobilityAid_WalkingCane_White.png](White/MobilityAid_WalkingCane_White.png) | [MobilityAid_WalkingCane_Navy.png](Navy/MobilityAid_WalkingCane_Navy.png) |
| Walker | [MobilityAid_Walker_White.png](White/MobilityAid_Walker_White.png) | [MobilityAid_Walker_Navy.png](Navy/MobilityAid_Walker_Navy.png) |
| Mobility scooter | [MobilityAid_MobilityScooter_White.png](White/MobilityAid_MobilityScooter_White.png) | [MobilityAid_MobilityScooter_Navy.png](Navy/MobilityAid_MobilityScooter_Navy.png) |
| Manual wheelchair | [MobilityAid_ManualWheelchair_White.png](White/MobilityAid_ManualWheelchair_White.png) | [MobilityAid_ManualWheelchair_Navy.png](Navy/MobilityAid_ManualWheelchair_Navy.png) |
| Motorized wheelchair | [MobilityAid_MotorizedWheelchair_White.png](White/MobilityAid_MotorizedWheelchair_White.png) | [MobilityAid_MotorizedWheelchair_Navy.png](Navy/MobilityAid_MotorizedWheelchair_Navy.png) |

Every PNG here is generated from the 4096-pixel source image by [build_mobility_aid_icons.py](build_mobility_aid_icons.py). To add a color, add it to `COLORS` in that script and rerun it; don't edit the PNGs by hand.

## Using them
**At what size.** The icons come from an image of the figure, not from vector artwork. Each is about 230 pixels across in the source and about twice that here, and they look clean up to their full size of 480 pixels. Don't enlarge them beyond that. We have not found a vector version: the figure is an image in the paper and in the talk slides. If you need the icons larger, ask Chu whether she has the original artwork.

**In any color on the web.** Use a white icon as a CSS mask and set the color with `background`. Give the element a role and a label so that screen readers announce it:

```html
<span role="img" aria-label="Manual wheelchair"
      style="display: inline-block; width: 48px; height: 48px; background: #EB724E;
             -webkit-mask: url(White/MobilityAid_ManualWheelchair_White.png) center / contain no-repeat;
             mask: url(White/MobilityAid_ManualWheelchair_White.png) center / contain no-repeat;"></span>
```

If the icon sits next to text that already names the aid, use `aria-hidden="true"` instead of the role and label.
