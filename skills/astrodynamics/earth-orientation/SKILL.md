---
name: earth-orientation
description: Rotate a state between MJ2000Eq and EarthFixed with the IAU-76/80 FK5 reduction. Use for earth-orientation tasks in the ORRERY orbital-dynamics engine.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: astrodynamics
---
# Earth Orientation

Applies the IAU-1976 precession, IAU-1980 nutation (106 terms), IAU-1982 GMST and polar motion to rotate a state between the MJ2000Eq (GCRF/J2000) and EarthFixed (ITRF) frames at an epoch, using supplied Earth-orientation parameters. Reproduces Vallado's worked reduction.

## Limitations

- EOP must be supplied as daily rows spanning the epoch.
- The 23 mas constant frame bias (ICRF vs FK5) is not applied; nutation corrections are optional.
