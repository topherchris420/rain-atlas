from rain_atlas.science.evaluation import recovery


def run(inputs, ctx):
    result = recovery(
        inputs["estimates"], [float(f) for f in inputs["truth_hz"]], float(inputs["tolerance_hz"]),
        amplitudes=inputs.get("amplitudes"), noise_std=inputs.get("noise_std"), n=inputs.get("n"),
        fs=inputs.get("fs"),
    )
    ctx.log(f"all tones recovered in {result['all_recovered_rate']:.0%} of realizations")
    return result
