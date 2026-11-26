"""Plan the power of an exact one-sided false-conclusion check; do not run missions."""

import argparse
import json

from rain_atlas.science.safety_planning import maximum_passing_count, probability_of_passing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--missions", nargs="+", type=int, required=True)
    parser.add_argument("--ceiling", type=float, default=0.05, help="maximum false-conclusion probability")
    parser.add_argument("--alpha", type=float, default=0.05, help="one-sided, per-test error budget")
    parser.add_argument("--true-rates", nargs="+", type=float, default=[0.02, 0.03, 0.04])
    args = parser.parse_args()
    try:
        rows = [
            {
                "missions": n,
                "maximum_passing_count": maximum_passing_count(n, args.ceiling, args.alpha),
                "scenarios": [
                    {
                        "assumed_true_rate": p,
                        "probability_of_passing": probability_of_passing(n, args.ceiling, args.alpha, p),
                    }
                    for p in args.true_rates
                ],
            }
            for n in args.missions
        ]
    except ValueError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "schema": "atlas.research-safety-plan/v1",
                "assumption": "fixed sample of independent, identically distributed Bernoulli mission outcomes",
                "ceiling": args.ceiling,
                "per_test_alpha": args.alpha,
                "rows": rows,
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
