"""Target 09: Infera — scientific protocol compilation."""

from __future__ import annotations

from ..models import (
    ConformanceRecord,
    EvidenceItem,
    Feature,
    Investigation,
    ReplicaSpec,
    TargetManifest,
)

INFERA_URL = "https://www.infera.bio/"


def investigation() -> Investigation:
    manifest = TargetManifest(
        target_id="T09-infera",
        name="Infera",
        organization="Infera Biosystems, Inc.",
        urls={
            "website": INFERA_URL,
            "ycombinator": "https://www.ycombinator.com/companies/infera",
        },
        reference_version="public website (2026-11-16)",
        reference_commit="",
        license="Proprietary; publicly described behavior only",
        license_notes=(
            "Closed source. Everything recorded here is INFERRED from the "
            "public website; no Infera software was executed or examined."
        ),
        scope="Natural-language experiment specification, protocol compilation, "
        "instrument constraints, procedure validation, experiment scheduling, "
        "data collection, human approval of experimental actions.",
    )
    observed = [
        EvidenceItem(
            id="inf-obs-2",
            classification="OBSERVED",
            statement=(
                "What Infera sells (per its public site and YC launch): "
                "Project IO, 'Our protocol compiler. Describe a workflow "
                "in plain English' — converting workflows to instrument "
                "instructions, verifying them on digital twins and "
                "supervising instruments, which execute only after human "
                "approval; BioBase Reader takes files off instruments as "
                "CSV or Excel; BioBase is 'a desktop research "
                "environment where scientists direct AI agents to "
                "investigate questions and organize data', with a "
                "zero-data-retention option. The sold product's real "
                "laboratory instrument integrations are beyond this "
                "replica's scope, which reconstructs the "
                "compile-validate-approve loop for simulated instruments."
            ),
            sources=[
                "https://www.infera.bio/ (fetched 2026-11-17)",
                "https://www.ycombinator.com/launches/Qdt-infera-control-lab-instruments-with-natural-language",
            ],
            captured_at="2026-11-17",
        ),
        EvidenceItem(
            id="inf-obs-1",
            classification="OBSERVED",
            statement=(
                "The public website describes Project IO as a protocol compiler: "
                "scientists and agents describe a workflow in plain English and "
                "Project IO converts it into instrument instructions, verified on "
                "digital twins, with instruments executing only after human "
                "approval; BioBase Reader takes instrument output as CSV or "
                "Excel; BioBase bundles protocol runs with analysis records."
            ),
            sources=[INFERA_URL, INFERA_URL + "project-io"],
            captured_at="2026-11-16",
        ),
    ]
    interface = [
        EvidenceItem(
            id="inf-if-1",
            classification="COMPUTED",
            statement=(
                "The replica compiles a question and hypothesis into a validated "
                "ProtocolSpec: variables with bounds from a declared lexicon, "
                "simulated instruments only, ordered steps, preregistered "
                "acceptance criteria and safety constraints forbidding physical "
                "actuation; verified by 6 executed tests."
            ),
            sources=["tests/test_replica_modules.py::TestProtocolCompiler"],
            derives_from=["inf-obs-1"],
            captured_at="2026-11-16",
        ),
    ]
    failures = [
        EvidenceItem(
            id="inf-fail-1",
            classification="COMPUTED",
            statement=(
                "Hypotheses whose variables are outside the declared lexicon, "
                "unparseable hypotheses, single-point designs and protocols "
                "without safety constraints are rejected with ValidationError "
                "before any execution."
            ),
            sources=["tests/test_replica_modules.py::TestProtocolCompiler"],
            captured_at="2026-11-16",
        ),
    ]
    replica = ReplicaSpec(
        replica_id="R09-protocol-compiler",
        target_id="T09-infera",
        module="rain_atlas.protocol",
        integration_status="integrated",
        integration_notes=(
            "The vertical slice compiles its hypothesis into a validated "
            "protocol before any experiment runs; the approval gate then gates "
            "execution, mirroring the reference's approve-before-execute concept."
        ),
        features=[
            Feature(
                name="protocol-compilation",
                description="hypothesis to executable spec with variables, steps and criteria",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestProtocolCompiler::test_compile_hypothesis_to_spec",
                    "inf/protocol-compilation",
                ],
                deviations=[
                    "deterministic template parsing over a declared lexicon instead of natural-language understanding"
                ],
            ),
            Feature(
                name="procedure-validation",
                description="lexicon membership, bounds, points and parseability checks",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestProtocolCompiler::test_unknown_variable_rejected"
                ],
            ),
            Feature(
                name="safety-constraints",
                description="physical actuation forbidden; simulated instruments only",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestProtocolCompiler::test_safety_constraints_present"
                ],
            ),
            Feature(
                name="preregistered-acceptance",
                description="criteria fixed in the spec before execution",
                status="verified",
                test_names=[
                    "tests/test_replica_modules.py::TestProtocolCompiler::test_compile_hypothesis_to_spec"
                ],
            ),
            Feature(
                name="physical-instruments",
                description="real laboratory instrument control",
                status="unverified",
                test_names=[],
                coverage="explicitly out of scope; requires separate engineering, safety validation and human authorization",
            ),
        ],
    )
    conformance = [
        ConformanceRecord(
            case="inf/protocol-compilation",
            status="passed",
            reference="Infera public website description (product not executed)",
            comparator="predicate",
            details="plain-language hypothesis compiles to a validated, executable spec",
            ran_at="2026-11-16",
        ),
    ]
    return Investigation(
        manifest=manifest,
        observed_functionality=observed,
        interface_model=interface,
        failure_conditions=failures,
        replicas=[replica],
        conformance=conformance,
        open_questions=[
            "Infera's exact compilation behavior, instrument coverage and "
            "validation rules are UNKNOWN; the replica implements the concept "
            "for simulated instruments only.",
        ],
        confidence="low",
    )
