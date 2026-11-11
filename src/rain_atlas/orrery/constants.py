"""Physical constants with their sources.

Two families are kept apart on purpose:

* ``GMAT_*`` values reproduce the defaults NASA GMAT R2026a uses (read from
  ``src/gmatutil/util/GmatDefaults.hpp`` and the shipped ``JGM3.cof``), so a
  cross-implementation comparison uses identical inputs.
* ``DE421_*`` values come from JPL's official DE421 header file
  (``header.421``, SHA-256 0fe9e0d60df4b33772e7332d87eb883eaf4cf3219b5a4cd2d5bc2356e98b2d16,
  https://ssd.jpl.nasa.gov/ftp/eph/planets/ascii/de421/header.421), and are
  the constants consistent with the DE421 ephemeris used for N-body checks.

A constant is never silently substituted for another: scenario definitions
name the family they use and every recorded experiment copies its constants
into its configuration.
"""

from __future__ import annotations

SECONDS_PER_DAY = 86400.0
DAYS_PER_JULIAN_CENTURY = 36525.0
JD_J2000 = 2451545.0  # 2000-01-01 12:00:00 TT
MJD_OFFSET = 2400000.5  # JD - MJD
GMAT_MODJULIAN_OFFSET = 2430000.0  # GMAT "ModJulian" = JD - 2430000.0 (5 Jan 1941 12:00)
TT_MINUS_TAI_S = 32.184  # IAU 1991 definition of TT
A1_MINUS_TAI_S = 0.0343817  # GMAT Math Spec section 2.1 (USNO A.1 atomic scale)
ARCSEC_TO_RAD = 4.84813681109535993589914102357947975e-6  # pi / 648000
SPEED_OF_LIGHT_KM_S = 299792.458

# --- Earth, as configured in GMAT R2026a (JGM-3 header and GmatDefaults.hpp) ---
GMAT_EARTH_MU = 398600.4415  # km^3/s^2, JGM-3 (Tapley et al. 1996)
GMAT_EARTH_RADIUS = 6378.1363  # km, JGM-3 reference radius
GMAT_EARTH_FLATTENING = 0.00335270  # GmatDefaults.hpp ("match to STK 2006.01.31")
GMAT_MOON_MU = 4902.8005821478  # km^3/s^2, GmatDefaults.hpp
GMAT_SUN_MU = 132712440017.99  # km^3/s^2, GmatDefaults.hpp STAR_MU
# Normalized JGM-3 C(2,0) from the JGM3.cof file shipped with GMAT R2026a.
JGM3_C20_NORMALIZED = -4.84165374886470e-04
JGM3_J2 = -JGM3_C20_NORMALIZED * 5.0**0.5  # unnormalized J2 = -C20 * sqrt(5)

# Nominal Earth rotation rate used with LOD (Vallado 2013, eq. 3-40; GMAT Math Spec).
EARTH_ROTATION_RATE = 7.29211514670698e-5  # rad/s

# --- JPL DE421 (header.421, GROUP 1041) ---
DE421_AU_KM = 149597870.6996262
DE421_EMRAT = 81.3005690699153  # Earth/Moon mass ratio
_DE421_GM_AU3_DAY2 = {
    "mercury": 4.91254957186794e-11,
    "venus": 7.243452332698441e-10,
    "earth-moon-barycenter": 8.997011408268049e-10,
    "mars-barycenter": 9.54954869562239e-11,
    "jupiter-barycenter": 2.82534584085505e-07,
    "saturn-barycenter": 8.459706073308477e-08,
    "uranus-barycenter": 1.29202482579265e-08,
    "neptune-barycenter": 1.52435910924974e-08,
    "pluto-barycenter": 2.17844105199052e-12,
    "sun": 0.0002959122082855911,
}


def _au3_day2_to_km3_s2(value: float) -> float:
    return value * DE421_AU_KM**3 / SECONDS_PER_DAY**2


DE421_GM = {name: _au3_day2_to_km3_s2(v) for name, v in _DE421_GM_AU3_DAY2.items()}
DE421_GM["earth"] = DE421_GM["earth-moon-barycenter"] * DE421_EMRAT / (1.0 + DE421_EMRAT)
DE421_GM["moon"] = DE421_GM["earth-moon-barycenter"] / (1.0 + DE421_EMRAT)

GMAT_CONSTANTS = {
    "earth_mu_km3_s2": GMAT_EARTH_MU,
    "earth_radius_km": GMAT_EARTH_RADIUS,
    "earth_flattening": GMAT_EARTH_FLATTENING,
    "earth_rotation_rate_rad_s": EARTH_ROTATION_RATE,
    "earth_j2": JGM3_J2,
    "moon_mu_km3_s2": GMAT_MOON_MU,
    "sun_mu_km3_s2": GMAT_SUN_MU,
    "source": "NASA GMAT R2026a defaults (GmatDefaults.hpp, JGM3.cof)",
}
