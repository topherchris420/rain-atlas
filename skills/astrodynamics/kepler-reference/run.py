"""Astrodynamics skill: kepler-reference (ORRERY). Thin wrapper over rain_atlas.orrery.skill_api."""

from rain_atlas.orrery.skill_api import DISPATCH


def run(inputs, ctx):
    ctx.log("orrery skill: kepler-reference")
    return DISPATCH["kepler-reference"](inputs)
