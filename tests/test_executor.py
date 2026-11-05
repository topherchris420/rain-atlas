import sqlite3
import sys
import threading
from pathlib import Path

import pytest
from conftest import REPO, fixture_ref

from rain_atlas.exec.policy import HostPolicy
from rain_atlas.exec.runner import run_skill


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
    result = run_skill(
        fixture_ref("naughty"), {"mode": "ok"}, seed=1, runs_dir=runs_dir, host=HostPolicy(max_memory_mb=64)
    )
    assert result.status == "refused"
    assert "memory" in result.error["message"]


@pytest.mark.parametrize("mode", ["network", "subprocess"])
def test_network_and_subprocess_are_blocked(runs_dir, mode):
    result = run_skill(fixture_ref("naughty"), {"mode": mode}, seed=1, runs_dir=runs_dir)
    assert result.status == "error"
    assert result.policy_denials, result.error


def test_writes_outside_the_run_are_blocked(runs_dir, tmp_path):
    target = tmp_path / "OUTSIDE.txt"
    result = run_skill(
        fixture_ref("naughty"), {"mode": "write-outside", "target": str(target)}, seed=1, runs_dir=runs_dir
    )
    assert result.status == "error"
    assert not target.exists()


def test_reads_outside_the_skill_and_inputs_are_blocked(runs_dir):
    result = run_skill(
        fixture_ref("naughty"),
        {"mode": "read-outside", "target": str(REPO / "pyproject.toml")},
        seed=1,
        runs_dir=runs_dir,
    )
    assert result.status == "error"
    assert result.policy_denials


def test_sqlite_cannot_create_databases_outside_the_run(runs_dir, tmp_path):
    # Regression: SQLite opens files natively, so the "open" audit event never
    # saw them; sqlite3.connect could create files anywhere.
    target = tmp_path / "OUTSIDE.sqlite"
    result = run_skill(
        fixture_ref("naughty"), {"mode": "sqlite-outside", "target": str(target)}, seed=1, runs_dir=runs_dir
    )
    assert result.status == "error" and result.policy_denials, result.error
    assert not target.exists()


def test_sqlite_cannot_read_databases_outside_the_read_roots(runs_dir, tmp_path):
    # Browser cookie and history stores are SQLite files; mode=ro is still a read.
    import sqlite3

    secret = tmp_path / "host-secret.sqlite"
    with sqlite3.connect(secret) as con:
        con.execute("create table secret (x)")
    result = run_skill(
        fixture_ref("naughty"),
        {"mode": "sqlite-read-outside", "target": secret.as_posix()},
        seed=1,
        runs_dir=runs_dir,
    )
    assert result.status == "error" and result.policy_denials, result.error


@pytest.mark.skipif(
    not hasattr(sqlite3.Connection, "enable_load_extension"),
    reason="sqlite3 built without loadable-extension support: no extension can load",
)
def test_sqlite_native_extensions_are_refused(runs_dir):
    # The child runs this same interpreter build, so the host check is exact.
    result = run_skill(fixture_ref("naughty"), {"mode": "sqlite-extension"}, seed=1, runs_dir=runs_dir)
    assert result.status == "error"
    assert any("SQLite extensions" in d for d in result.policy_denials), result.error


def test_sqlite_in_memory_and_in_the_output_directory_still_work(runs_dir):
    result = run_skill(fixture_ref("naughty"), {"mode": "sqlite-inside"}, seed=1, runs_dir=runs_dir)
    assert result.status == "ok", result.error
    assert "scratch.sqlite" in result.artifacts


@pytest.mark.skipif(not hasattr(__import__("os"), "setxattr"), reason="extended attributes are Linux-only")
def test_extended_attributes_outside_the_run_are_blocked(runs_dir, tmp_path):
    import os

    target = tmp_path / "victim.txt"
    target.write_text("x", encoding="utf-8")
    try:
        os.setxattr(target, "user.probe", b"1")
    except OSError:
        pytest.skip("this filesystem does not support user extended attributes")
    os.removexattr(target, "user.probe")
    result = run_skill(
        fixture_ref("naughty"), {"mode": "xattr-outside", "target": str(target)}, seed=1, runs_dir=runs_dir
    )
    assert result.status == "error" and result.policy_denials, result.error
    assert "user.atlas" not in os.listxattr(target)


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
        result = run_skill(
            fixture_ref("naughty"), {"mode": "sleep"}, seed=1, runs_dir=runs_dir, cancel=cancel
        )
    finally:
        timer.cancel()
    assert result.status == "cancelled"


def test_memory_limit_stops_runaway_allocation(runs_dir):
    result = run_skill(fixture_ref("naughty"), {"mode": "memory"}, seed=1, runs_dir=runs_dir)
    assert result.status in {"error", "crashed"}
    assert result.status != "ok"
    if result.peak_memory_mb is not None and sys.platform == "win32":
        assert result.peak_memory_mb < 256 + 64


def test_peak_memory_is_measured_per_run(runs_dir):
    # Regression (POSIX): RUSAGE_CHILDREN is a running maximum over every
    # child the host ever reaped, so a small run after a large one inherited
    # the large run's peak. Each record must describe its own process.
    small_before = run_skill(fixture_ref("echo"), {"values": [1.0]}, seed=1, runs_dir=runs_dir)
    large = run_skill(
        fixture_ref("naughty"), {"mode": "allocate", "megabytes": 160}, seed=1, runs_dir=runs_dir
    )
    small_after = run_skill(fixture_ref("echo"), {"values": [1.0]}, seed=1, runs_dir=runs_dir)
    assert small_before.ok and large.ok and small_after.ok, (large.error, small_after.error)
    peaks = [r.peak_memory_mb for r in (small_before, large, small_after)]
    assert all(p is not None for p in peaks), [r.peak_memory_note for r in (small_before, large, small_after)]
    assert peaks[1] >= 160, peaks
    assert peaks[2] < peaks[1] - 100, peaks
    assert abs(peaks[2] - peaks[0]) < 50, peaks
    if sys.platform.startswith("linux"):
        # wait4 alone is not enough: Linux folds the host's RSS at spawn into
        # the child's maxrss, which made every run in a large host look large.
        assert all("VmHWM" in r.peak_memory_note for r in (small_before, large, small_after))


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="VmHWM is read from Linux /proc")
def test_peak_memory_includes_result_serialization(runs_dir):
    # Regression: VmHWM was sampled before finish() converted and serialized
    # the outputs, so a skill whose peak is its own result under-reported it.
    # 3e6 zeros: an 8-byte-per-item list, a converted copy and ~9 MB of JSON.
    small = run_skill(fixture_ref("naughty"), {"mode": "ok"}, seed=1, runs_dir=runs_dir)
    large = run_skill(
        fixture_ref("naughty"), {"mode": "large-output", "count": 3_000_000}, seed=1, runs_dir=runs_dir
    )
    assert small.ok and large.ok, large.error
    assert "VmHWM" in large.peak_memory_note
    list_mb = 3_000_000 * 8 / 2**20
    # Sampled too early, the excess is only the skill's own list (~23 MiB).
    assert large.peak_memory_mb - small.peak_memory_mb > 1.7 * list_mb, (
        small.peak_memory_mb,
        large.peak_memory_mb,
    )


def test_runs_are_deterministic_given_seed(runs_dir):
    ref = fixture_ref("echo")
    a = run_skill(ref, {"values": [1, 2]}, seed=5, runs_dir=runs_dir)
    b = run_skill(ref, {"values": [1, 2]}, seed=5, runs_dir=runs_dir)
    assert a.outputs == b.outputs
    assert {k: v["sha256"] for k, v in a.artifacts.items()} == {
        k: v["sha256"] for k, v in b.artifacts.items()
    }
