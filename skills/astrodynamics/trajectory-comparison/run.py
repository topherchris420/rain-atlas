"""Astrodynamics skill: trajectory-comparison (ORRERY). Thin wrapper over rain_atlas.orrery.skill_api."""

from rain_atlas.orrery.skill_api import DISPATCH


def run(inputs, ctx):
    ctx.log("orrery skill: trajectory-comparison")
    return DISPATCH["trajectory-comparison"](inputs)
