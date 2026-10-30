import numpy as np


def run(inputs, ctx):
    values = np.asarray(inputs["values"], dtype=float)
    ctx.log(f"received {values.size} values")
    return {"sum": float(values.sum()), "mean": float(values.mean()), "array": ctx.save_array("values.npy", values)}
