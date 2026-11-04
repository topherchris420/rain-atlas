from rain_atlas.science.skill_api import run_method


def run(inputs, ctx):
    return run_method("kuramoto", inputs, ctx)
