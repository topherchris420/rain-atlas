from rain_atlas.science.evaluation import agreement


def run(inputs, ctx):
    result = agreement(
        inputs["estimates_a"], inputs["estimates_b"], float(inputs["tolerance_hz"]),
        float(inputs.get("min_fraction", 0.9)),
    )
    ctx.log(f"{sum(i['agrees'] for i in result['items'])} of {len(result['items'])} item(s) agree")
    return result
