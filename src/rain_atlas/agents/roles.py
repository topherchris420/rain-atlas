"""Built-in research roles (deterministic policies; no language model needed).

Roles are named by function, not after any existing agent persona. An
adapter may later route a role to an external agent; these classes are the
reference behaviour such an agent must match.
"""

from __future__ import annotations

from typing import Any

from ..canonical import from_jsonable
from ..exec.runner import RunResult, SkillRef
from ..ledger.store import Entry
from ..science.evaluation import cluster
from .disagreement import outcome_from_fraction
from .lab import Engineer, Lab, author


class PrincipalInvestigator:
    role = "principal-investigator"

    def __init__(self, lab: Lab):
        self.lab = lab

    def preregister(self, record: dict) -> Entry:
        record = dict(record)
        record["created_by"] = author(self.role)
        return self.lab.ledger.append("preregistration", record)

    def select(self, experiment: str, capability: str) -> SkillRef:
        candidates = self.lab.registry.select(capability)
        if not candidates:
            self.lab.note(
                experiment,
                self.role,
                f"no enabled, approved skill provides {capability}; stopping",
                capability=capability,
            )
            raise LookupError(f"no skill provides {capability}")
        chosen = candidates[0]
        self.lab.note(
            experiment,
            self.role,
            f"selected {chosen.name}@{chosen.version} for {capability}",
            capability=capability,
            selected={"name": chosen.name, "version": chosen.version, "content_hash": chosen.content_hash},
            candidates=[f"{c.name}@{c.version}" for c in candidates],
            rule="registry capability match ranked by trust, determinism, name",
        )
        return chosen

    def report(self, experiment: str, **fields: Any) -> Entry:
        return self.lab.ledger.append(
            "report", {"experiment": experiment, "author": author(self.role), **fields}
        )


class ComputationalScientist:
    role = "computational-scientist"

    def __init__(self, lab: Lab, engineer: Engineer):
        self.lab = lab
        self.engineer = engineer

    def detect_lines(
        self,
        experiment: str,
        skill: SkillRef,
        dataset: dict,
        params: dict,
        *,
        seed: int,
        label: str,
        claim_fraction: float,
        cluster_tolerance: float,
    ) -> dict:
        staged, files = self.lab.stage(dataset)
        run_entry, result = self.engineer.execute(
            experiment,
            skill,
            {"signals": staged[0], **params},
            seed=seed,
            files=files,
            purpose=f"primary line detection ({label})",
        )
        out: dict[str, Any] = {"run": run_entry, "result": result, "claims": [], "estimates": None}
        if not result.ok:
            self.lab.note(
                experiment,
                self.role,
                f"primary analysis failed ({label}): {result.status}",
                run=run_entry.object,
            )
            return out
        outputs = from_jsonable(result.outputs)
        estimates = [[p["frequency_hz"] for p in row] for row in outputs["peaks"]]
        out["estimates"] = estimates
        for c in cluster(estimates, cluster_tolerance):
            if c["fraction"] < claim_fraction:
                self.lab.note(
                    experiment,
                    self.role,
                    f"sporadic detection near {c['frequency_hz']:.3f} Hz in {c['fraction']:.0%} of realizations "
                    f"({label}); below the preregistered claim fraction {claim_fraction:.0%}, not claimed",
                    run=run_entry.object,
                    cluster=c,
                )
                continue
            entry = self.lab.ledger.append(
                "claim",
                {
                    "experiment": experiment,
                    "category": "COMPUTED",
                    "statement": f"A spectral line near {c['frequency_hz']:.3f} Hz is detected in "
                    f"{c['fraction']:.0%} of realizations ({label}).",
                    "value": c["frequency_hz"],
                    "unit": "Hz",
                    "uncertainty": {"kind": "std across realizations", "value": c["spread_hz"]},
                    "detection_fraction": c["fraction"],
                    "label": label,
                    "origin": "primary",
                    "method": f"{skill.name}@{skill.version}",
                    "evidence": [run_entry.object],
                    "author": author(self.role),
                },
            )
            out["claims"].append((entry, c))
        return out


class Skeptic:
    role = "scientific-skeptic"

    def __init__(self, lab: Lab, engineer: Engineer):
        self.lab = lab
        self.engineer = engineer

    def independent_estimates(
        self, experiment: str, skill: SkillRef, dataset: dict, params: dict, *, seed: int, label: str
    ) -> tuple[Entry, RunResult, list[list[float]] | None]:
        """Re-derive estimates from the raw data with a different method."""

        staged, files = self.lab.stage(dataset)
        entry, result = self.engineer.execute(
            experiment,
            skill,
            {"signals": staged[0], **params},
            seed=seed,
            files=files,
            purpose=f"independent estimate ({label})",
        )
        if not result.ok:
            return entry, result, None
        fits = from_jsonable(result.outputs)["fits"]
        return entry, result, [f["frequencies_hz"] for f in fits]

    def compare(
        self,
        experiment: str,
        skill: SkillRef,
        primary: list[list[float]],
        independent: list[list[float]],
        claims: list[tuple[Entry, dict]],
        *,
        tolerance: float,
        min_fraction: float,
        seed: int,
        label: str,
        independent_run: Entry,
    ) -> dict[str, str]:
        entry, result = self.engineer.execute(
            experiment,
            skill,
            {
                "estimates_a": primary,
                "estimates_b": independent,
                "tolerance_hz": tolerance,
                "min_fraction": min_fraction,
            },
            seed=seed,
            purpose=f"cross-method agreement ({label})",
        )
        outcomes: dict[str, str] = {}
        items = from_jsonable(result.outputs)["items"] if result.ok else []
        for claim_entry, c in claims:
            item = min(items, key=lambda i: abs(i["frequency_hz"] - c["frequency_hz"]), default=None)
            if item is None or abs(item["frequency_hz"] - c["frequency_hz"]) > tolerance:
                outcome, fraction = "inconclusive", None
            else:
                fraction = item["agreement_fraction"]
                outcome = outcome_from_fraction(fraction, min_fraction, 0.5)
            outcomes[claim_entry.object] = outcome
            self.lab.ledger.append(
                "challenge",
                {
                    "experiment": experiment,
                    "target": claim_entry.object,
                    "method": "independent re-estimation (NLS + BIC on raw data) and per-realization agreement",
                    "evidence": [independent_run.object, entry.object],
                    "outcome": outcome,
                    "agreement_fraction": fraction,
                    "reasoning": "corroborated when the independent estimator reports a line within "
                    f"{tolerance} Hz in at least {min_fraction:.0%} of the realizations where the primary "
                    "method detected it; contradicted below 50%",
                    "author": author(self.role),
                },
            )
        return outcomes

    def unclaimed_lines(
        self,
        experiment: str,
        independent: list[list[float]],
        claims: list[tuple[Entry, dict]],
        independent_run: Entry,
        *,
        tolerance: float,
        claim_fraction: float,
        label: str,
    ) -> list[tuple[Entry, dict]]:
        """Lines the independent estimator finds consistently that the primary method did not claim."""

        claimed = [c["frequency_hz"] for _, c in claims]
        out = []
        for c in cluster(independent, tolerance):
            if c["fraction"] < claim_fraction or any(
                abs(c["frequency_hz"] - f) <= tolerance for f in claimed
            ):
                continue
            entry = self.lab.ledger.append(
                "claim",
                {
                    "experiment": experiment,
                    "category": "COMPUTED",
                    "statement": f"The independent estimator reports a line near {c['frequency_hz']:.3f} Hz in "
                    f"{c['fraction']:.0%} of realizations ({label}); the primary method did not claim it.",
                    "value": c["frequency_hz"],
                    "unit": "Hz",
                    "uncertainty": {"kind": "std across realizations", "value": c["spread_hz"]},
                    "detection_fraction": c["fraction"],
                    "label": label,
                    "origin": "independent-only",
                    "method": "independent estimator",
                    "evidence": [independent_run.object],
                    "author": author(self.role),
                },
            )
            out.append((entry, c))
        return out

    def falsify(
        self,
        experiment: str,
        skill: SkillRef,
        replicates: dict,
        claims: list[tuple[Entry, dict]],
        *,
        fs: float,
        alpha: float,
        min_fraction: float,
        seed: int,
        label: str,
    ) -> dict[str, str]:
        if not claims:
            return {}
        staged, files = self.lab.stage(replicates)
        freqs = [c["frequency_hz"] for _, c in claims]
        entry, result = self.engineer.execute(
            experiment,
            skill,
            {
                "signals": staged[0],
                "fs": fs,
                "frequencies_hz": freqs,
                "alpha": alpha,
                "min_fraction": min_fraction,
                "max_fraction_contradict": 0.2,
            },
            seed=seed,
            files=files,
            purpose=f"replicate falsification test ({label})",
        )
        tests = from_jsonable(result.outputs)["tests"] if result.ok else []
        # Pair by the frequency each test reports, never by position: a skill
        # may reorder or omit tests, and every claim must still be challenged.
        tested = {t["frequency_hz"]: t for t in tests if isinstance(t, dict) and "frequency_hz" in t}
        outcomes: dict[str, str] = {}
        for claim_entry, c in claims:
            test = tested.get(c["frequency_hz"])
            outcome = test["outcome"] if test else "inconclusive"
            outcomes[claim_entry.object] = outcome
            self.lab.ledger.append(
                "challenge",
                {
                    "experiment": experiment,
                    "target": claim_entry.object,
                    "method": "regression F-test for the claimed frequency on independent replicate measurements",
                    "evidence": [entry.object],
                    "outcome": outcome,
                    "fraction_significant": test["fraction_significant"] if test else None,
                    "reasoning": "the claimed frequency was fixed before these replicates were analysed, so the "
                    "test is not affected by selection; Bonferroni-corrected across claims",
                    "author": author(self.role),
                },
            )
        return outcomes
