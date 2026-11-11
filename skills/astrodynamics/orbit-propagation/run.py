"""Astrodynamics skill: orbit-propagation (ORRERY). Thin wrapper over rain_atlas.orrery.skill_api."""

from rain_atlas.orrery.skill_api import DISPATCH


def run(inputs, ctx):
    ctx.log("orrery skill: orbit-propagation")
    return DISPATCH["orbit-propagation"](inputs)
