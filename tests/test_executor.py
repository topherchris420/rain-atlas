import sys
import threading
from pathlib import Path

import pytest

from rain_atlas.exec.policy import HostPolicy
from rain_atlas.exec.runner import run_skill

from conftest import REPO, fixture_ref


def test_echo_runs_and_records_everything(runs_dir):
    result = run_skill(fixture_ref("echo"), {"values": [1, 2, 3.5]}, seed=1, runs_dir=runs_dir)
    assert result.status == "ok", result.error
    assert result.outputs["sum"] == 6.5
    record = result.record()
    for key in ("run_id", "skill", "inputs_hash", "policy", "environment", "artifacts", "wall_s"):
        assert key in record
    assert "inputs" not in record  # inputs are stored separately by the ledger
    assert record["policy"]["network"] is False
    assert all(meta["sha256"].startswith("sha256:") for meta in record["artifacts"].values())


def test_relative_runs_dir_works(tmp_path, monkeypatch):
    # Regression: the CLI passes relative paths; the child runs with its own cwd.
    monkeypatch.chdir(tmp_path)
    result = run_skill(fixture_ref("echo"), {"values": [1, 2]}, seed=1, runs_dir=Path("rel-runs"))
    assert result.status == "ok", (result.error, result.stderr_tail)
    assert result.run_dir.is_absolute()


def test_invalid_inputs_are_refused_before_execution(runs_dir):
    result = run_skill(fixture_ref("echo"), {"values": "not a list"}, seed=1, runs_dir=runs_dir)
    assert result.status == "invalid-input"
    assert not result.run_dir.exists()


def test_host_policy_refuses_escalation(runs_dir):
    result = run_skill(fixture_ref("naughty"), {"mode": "ok"}, seed=1, runs_dir=runs_dir,
                       host=HostPolicy(max_memory_mb=64))
    assert result.status == "refused"
    assert "memory" in result.error["message"]


@pytest.mark.parametrize("mode", ["network", "subprocess"])
def test_network_and_subprocess_are_blocked(runs_dir, mode):
    result = run_skill(fixture_ref("naughty"), {"mode": mode}, seed=1, runs_dir=runs_dir)
    assert result.status == "error"
    assert result.policy_denials, result.error


def test_writes_outside_the_run_are_blocked(runs_dir, tmp_path):
    target = tmp_path / "OUTSIDE.txt"
    result = run_skill(fixture_ref("naughty"), {"mode": "write-outside", "target": str(target)}, seed=1,
                       runs_dir=runs_dir)
    assert result.status == "error"
    assert not target.exists()


def test_reads_outside_the_skill_and_inputs_are_blocked(runs_dir):
    result = run_skill(fixture_ref("naughty"), {"mode": "read-outside", "target": str(REPO / "pyproject.toml")},
                       seed=1, runs_dir=runs_dir)
    assert result.status == "error"
    assert result.policy_denials


@pytest.mark.skipif(sys.platform != "win32", reason="job-object process limit is Windows-specific")
def test_native_process_creation_is_blocked_by_the_job_object(runs_dir):
    result = run_skill(fixture_ref("naughty"), {"mode": "native-subprocess"}, seed=1, runs_dir=runs_dir)
    assert result.status == "ok", result.error  # the attempt fails inside the skill, which reports it
    assert result.outputs["blocked_error"] != 0


def test_timeout_kills_the_run(runs_dir):
    result = run_skill(fixture_ref("naughty"), {"mode": "sleep"}, seed=1, runs_dir=runs_dir, timeout_s=3)
    assert result.status == "timeout"
    assert result.wall_s < 30


def test_cancellation(runs_dir):
    cancel = threading.Event()
    timer = threading.Timer(2.0, cancel.set)
    timer.start()
    try:
        result = run_skill(fixture_ref("naughty"), {"mode": "sleep"}, seed=1, runs_dir=runs_dir, cancel=cancel)
    finally:
        timer.cancel()
    assert result.status == "cancelled"


def test_memory_limit_stops_runaway_allocation(runs_dir):
    result = run_skill(fixture_ref("naughty"), {"mode": "memory"}, seed=1, runs_dir=runs_dir)
    assert result.status in {"error", "crashed"}
    assert result.status != "ok"
    if result.peak_memory_mb is not None and sys.platform == "win32":
        assert result.peak_memory_mb < 256 + 64


def test_runs_are_deterministic_given_seed(runs_dir):
    ref = fixture_ref("echo")
    a = run_skill(ref, {"values": [1, 2]}, seed=5, runs_dir=runs_dir)
    b = run_skill(ref, {"values": [1, 2]}, seed=5, runs_dir=runs_dir)
    assert a.outputs == b.outputs
    assert {k: v["sha256"] for k, v in a.artifacts.items()} == {k: v["sha256"] for k, v in b.artifacts.items()}
