"""Astrodynamics skill: orbit-determination (ORRERY). Thin wrapper over rain_atlas.orrery.skill_api."""

from rain_atlas.orrery.skill_api import DISPATCH


def run(inputs, ctx):
    ctx.log("orrery skill: orbit-determination")
    return DISPATCH["orbit-determination"](inputs)
