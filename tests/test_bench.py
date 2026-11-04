from rain_atlas.bench.spectral import evaluate


def test_stress_benchmark_preserves_failures_unknown_truth_and_denominators():
    results = evaluate(3, 42)
    cases = {r["case"]: r for r in results["rows"]}
    assert cases["chirp"]["truth_hz"] is None
    assert cases["chirp"]["methods"]["welch"]["false_positive_trial_rate"] is None
    assert cases["close"]["methods"]["welch"]["false_negative_trial_rate"]["rate"] > 0
    assert cases["colored-null"]["methods"]["welch"]["false_positive_trial_rate"]["rate"] > 0
    assert cases["separated"]["methods"]["welch"]["all_recovered_rate"]["n"] == 3
    assert all(r["method_disagreement"]["n"] == 3 for r in results["rows"])
    assert all(m["runtime_total_s"] > 0 for r in results["rows"] for m in r["methods"].values())
