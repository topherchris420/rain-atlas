"""Astrodynamics skill: covariance-propagation (ORRERY). Thin wrapper over rain_atlas.orrery.skill_api."""

from rain_atlas.orrery.skill_api import DISPATCH


def run(inputs, ctx):
    ctx.log("orrery skill: covariance-propagation")
    return DISPATCH["covariance-propagation"](inputs)
