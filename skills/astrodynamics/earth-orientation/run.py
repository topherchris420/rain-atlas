"""Astrodynamics skill: earth-orientation (ORRERY). Thin wrapper over rain_atlas.orrery.skill_api."""

from rain_atlas.orrery.skill_api import DISPATCH


def run(inputs, ctx):
    ctx.log("orrery skill: earth-orientation")
    return DISPATCH["earth-orientation"](inputs)
