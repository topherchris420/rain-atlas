---
name: tracking-simulation
description: Synthetic range and range-rate of an orbit from ground stations. Use for tracking-simulation tasks in the ORRERY orbital-dynamics engine.
license: MIT
compatibility: Requires Python 3.11+ with numpy, scipy and the rain-atlas package (ATLAS executor).
metadata:
  version: "1.0.0"
  domain: astrodynamics
---
# Tracking Simulation

Generates noiseless range and range-rate observations of an orbit from ground stations above a minimum elevation, using the station's inertial position and velocity (Earth rotation). The measurement geometry follows Vallado chapter 4.

## Limitations

- Range and range-rate only (no angles); light-time and tropospheric effects are not modelled.
- Visibility uses a simple elevation mask.
