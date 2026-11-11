"""Astrodynamics skill: nbody-integration (ORRERY). Thin wrapper over rain_atlas.orrery.skill_api."""

from rain_atlas.orrery.skill_api import DISPATCH


def run(inputs, ctx):
    ctx.log("orrery skill: nbody-integration")
    return DISPATCH["nbody-integration"](inputs)
