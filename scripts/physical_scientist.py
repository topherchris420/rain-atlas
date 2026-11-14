"""Offline Physical Scientist interface. There are deliberately no actuator commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rain_atlas.ledger.store import Ledger
from rain_atlas.observatory.export import export
from rain_atlas.physical_scientist import (
    ResonanceModel,
    demo,
    evaluate,
    observe,
    preregister,
    select_frequency,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    d = command.add_parser("demo", help="new three-act simulation; never physical evidence")
    d.add_argument("--root", type=Path, required=True)
    d.add_argument("--seed", type=int, default=7)
    d.add_argument("--truth-hz", type=float, default=186.0)

    p = command.add_parser("plan", help="preregister without operating hardware")
    p.add_argument("--ledger", type=Path, required=True)
    p.add_argument("--models", nargs="+", required=True, metavar="NAME:FREQUENCY_HZ")
    p.add_argument("--weights", type=float, nargs="+", required=True)
    p.add_argument("--sigma", type=float, required=True)
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--frequency", type=float, help="human-chosen permitted frequency")
    choice.add_argument("--candidates", type=float, nargs="+", help="select by disagreement")

    o = command.add_parser("observe", help="import operator-attested CSV; no acquisition")
    o.add_argument("--ledger", type=Path, required=True)
    o.add_argument("--experiment", required=True)
    o.add_argument("--csv", type=Path, required=True)
    o.add_argument("--operator", required=True)
    o.add_argument("--instrument-id", required=True)
    o.add_argument("--calibration-ref", required=True)
    o.add_argument("--acquired-at-utc", required=True)

    e = command.add_parser("evaluate", help="deterministic frozen-prediction evaluation")
    e.add_argument("--ledger", type=Path, required=True)
    e.add_argument("--experiment", required=True)
    e.add_argument("--observation", required=True)

    v = command.add_parser("export", help="existing verified offline observatory exporter")
    v.add_argument("--ledger", type=Path, required=True)
    v.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "demo":
        value = demo(args.root, seed=args.seed, truth_hz=args.truth_hz)
    elif args.command == "plan":
        models = []
        for item in args.models:
            name, hz = item.rsplit(":", 1)
            models.append(ResonanceModel(name, float(hz)))
        if args.candidates:
            selection = select_frequency(models, args.weights, args.sigma, args.candidates)
        else:
            selection = {"frequency_hz": args.frequency, "selection_rule": "human_fixed_v1"}
        experiment = preregister(
            Ledger(args.ledger), models, args.weights, args.sigma,
            selection["frequency_hz"], selection=selection
        )
        value = {"experiment": experiment, "selection": selection, "execution": "NONE"}
    elif args.command == "observe":
        provenance = {
            "operator": args.operator,
            "instrument_id": args.instrument_id,
            "calibration_ref": args.calibration_ref,
            "acquired_at_utc": args.acquired_at_utc,
            "attestation": "operator-attested",
        }
        ref = observe(
            Ledger(args.ledger), args.experiment, args.csv.read_bytes(),
            origin="empirical", provenance=provenance
        )
        value = {"observation": ref, "evidence_level": "OPERATOR_ATTESTED_IMPORT"}
    elif args.command == "evaluate":
        value = evaluate(Ledger(args.ledger), args.experiment, args.observation)
    else:
        value = {"observatory": str(export(args.ledger, args.out))}
    print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
