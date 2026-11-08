"""Astrodynamics skill: tracking-simulation (ORRERY). Thin wrapper over rain_atlas.orrery.skill_api."""

from rain_atlas.orrery.skill_api import DISPATCH


def run(inputs, ctx):
    ctx.log("orrery skill: tracking-simulation")
    return DISPATCH["tracking-simulation"](inputs)
