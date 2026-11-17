"""Tests for the protocol, simulation, inference, knowledge and browser modules."""

from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path

import pytest

from rain_atlas.browser import BrowserError, BrowserSession
from rain_atlas.inference import (
    LlamaCppProvider,
    MockProvider,
    OllamaProvider,
    ProviderError,
    discover_providers,
    extract_structured,
)
from rain_atlas.inference.structured import StructuredOutputError
from rain_atlas.knowledge import Conflict, KnowledgeStore
from rain_atlas.protocol import ProtocolCompiler, ValidationError
from rain_atlas.simulation import FaultProfile, ObservationFault, Scenario, ServiceTwin

LEXICON = {
    "coupling strength": {
        "symbol": "k",
        "range": [0.0, 1.0],
        "default_points": 9,
        "instrument": "oscillator-bench",
    },
    "noise level": {
        "symbol": "sigma",
        "range": [0.0, 0.5],
        "default_points": 5,
        "instrument": "oscillator-bench",
    },
}


class TestProtocolCompiler:
    def test_compile_hypothesis_to_spec(self):
        compiler = ProtocolCompiler(LEXICON)
        spec = compiler.compile(
            "Does coupling control phase locking?",
            "increasing coupling strength increases phase locking",
            replicates=12,
        )
        assert spec.independent_variable == "coupling strength"
        assert spec.dependent_measure == "phase locking"
        assert spec.instruments == ["oscillator-bench"]
        assert [s.action for s in spec.steps] == [
            "set-variable",
            "run-ensemble",
            "measure",
            "compare",
            "record",
        ]
        assert spec.problems() == []
        assert spec.acceptance["registered_before_execution"] is True

    def test_unknown_variable_rejected(self):
        compiler = ProtocolCompiler(LEXICON)
        with pytest.raises(ValidationError, match="lexicon"):
            compiler.compile("q", "increasing temperature increases phase locking")

    def test_unparseable_hypothesis_rejected(self):
        compiler = ProtocolCompiler(LEXICON)
        with pytest.raises(ValidationError, match="parse"):
            compiler.compile("q", "stuff happens")

    def test_safety_constraints_present(self):
        compiler = ProtocolCompiler(LEXICON)
        spec = compiler.compile("q", "coupling strength controls phase locking")
        assert spec.safety["physical_actuation"] == "forbidden"
        digest_a = spec.digest()
        digest_b = compiler.compile("q", "coupling strength controls phase locking").digest()
        assert digest_a == digest_b  # deterministic compilation

    def test_too_few_points_rejected(self):
        compiler = ProtocolCompiler(LEXICON)
        with pytest.raises(ValidationError):
            compiler.compile("q", "increasing coupling strength increases phase locking", points=1)

    def test_bad_lexicon_rejected(self):
        with pytest.raises(ValidationError):
            ProtocolCompiler({"bad": {"symbol": "b", "range": [1.0, 0.0], "instrument": "x"}})


class TestServiceTwin:
    def test_deterministic_replay(self):
        scenario = Scenario(seed=7, true_model="damped")
        twin = ServiceTwin(scenario)
        first = twin.run_experiment(0.4)
        twin.reset()
        second = twin.run_experiment(0.4)
        assert first == second

    def test_models_diverge(self):
        linear = ServiceTwin(Scenario(seed=7, true_model="linear"))
        damped = ServiceTwin(Scenario(seed=7, true_model="damped"))
        high_coupling_linear = linear.run_experiment(0.9)["coherence"]
        high_coupling_damped = damped.run_experiment(0.9)["coherence"]
        assert abs(high_coupling_linear - high_coupling_damped) > 0.02

    def test_snapshot_and_restore(self):
        twin = ServiceTwin(Scenario(seed=3, true_model="linear"))
        twin.run_experiment(0.2)
        snapshot = twin.snapshot()
        a = twin.run_experiment(0.5)
        twin.restore(snapshot)
        b = twin.run_experiment(0.5)
        assert a == b
        assert twin.state_version == 2

    def test_dropped_observations_raise(self):
        twin = ServiceTwin(
            Scenario(seed=5, true_model="linear"),
            fault_profile=FaultProfile(drop_probability=1.0),
        )
        with pytest.raises(ObservationFault):
            twin.run_experiment(0.3)
        assert twin.run_log.operations[-1]["response"] is None
        assert twin.run_log.operations[-1]["faulted"]

    def test_noise_and_bias_are_recorded(self):
        twin = ServiceTwin(
            Scenario(seed=5, true_model="linear"),
            fault_profile=FaultProfile(noise_sigma=0.1, bias=0.05),
        )
        result = twin.run_experiment(0.3)
        assert twin.run_log.operations[-1]["faulted"] is True
        assert 0.0 <= result["coherence"] <= 1.0

    def test_evidence_summary(self):
        twin = ServiceTwin(Scenario(seed=1, true_model="linear"))
        twin.run_experiment(0.1)
        twin.run_experiment(0.2)
        evidence = twin.evidence()
        assert evidence["executed_conditions"] == 2
        assert evidence["operations"] == 2

    def test_bad_scenario_rejected(self):
        with pytest.raises(ValueError):
            Scenario(seed=1, true_model="chaotic")

    def test_hidden_truth_not_leaked_in_responses(self):
        twin = ServiceTwin(Scenario(seed=2, true_model="damped"))
        response = twin.run_experiment(0.5)
        assert response["model_hidden"] is True
        assert "damped" not in json.dumps(response)
        assert twin.true_model() == "damped"  # operator-only accessor


class TestInference:
    def test_mock_provider_deterministic(self):
        provider = MockProvider(vocabulary=["coupling strength", "noise level"])
        a = provider.complete("propose: which variable matters for phase locking?")
        b = provider.complete("propose: which variable matters for phase locking?")
        assert a.text == b.text
        assert a.usage["total"] > 0

    def test_mock_classify(self):
        provider = MockProvider()
        assert provider.complete("classify: we hypothesize that k matters").text == "hypothesis"
        assert provider.complete("classify: we found a transition").text == "finding"

    def test_structured_extraction_validates(self):
        provider = MockProvider()
        schema = {
            "type": "object",
            "properties": {"hypothesis": {"type": "string"}},
            "required": ["hypothesis"],
        }
        result = provider.complete('reply with {"hypothesis": "k controls locking"}')
        value = extract_structured(result, schema)
        assert value["hypothesis"] == "k controls locking"
        bad = provider.complete("no json here at all")
        with pytest.raises(StructuredOutputError):
            extract_structured(bad, schema)
        wrong = provider.complete('json {"wrong": 1}')
        with pytest.raises(StructuredOutputError):
            extract_structured(wrong, schema)

    def test_discovery_includes_mock_without_network(self):
        providers = discover_providers(include_http=False)
        assert any(p["provider"] == "mock" for p in providers)

    def test_ollama_provider_http(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                body = json.dumps({"response": "hello", "prompt_eval_count": 3, "eval_count": 2}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                body = json.dumps({"models": [{"name": "llama3.2"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            provider = OllamaProvider(f"http://127.0.0.1:{port}")
            result = provider.complete("hi", model="llama3.2")
            assert result.text == "hello"
            assert result.usage == {"input": 3, "output": 2, "total": 5}
            models = provider.discover()
            assert models[0]["model"] == "llama3.2"
        finally:
            server.shutdown()
            server.server_close()

    def test_unreachable_provider_raises_provider_error(self):
        provider = OllamaProvider("http://127.0.0.1:1", timeout_s=0.2)
        with pytest.raises(ProviderError):
            provider.complete("hi")

    def test_llamacpp_discovery_via_discover_providers(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = json.dumps({"data": [{"id": "ggml-model"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            providers = discover_providers(http_timeout_s=0.5)
            # Remote servers not running here; mock is always present.
            assert any(p["provider"] == "mock" for p in providers)
            llamacpp = LlamaCppProvider(f"http://127.0.0.1:{port}")
            assert llamacpp.discover()[0]["model"] == "ggml-model"
        finally:
            server.shutdown()
            server.server_close()


class TestKnowledgeStore:
    def test_put_get_and_history(self):
        store = KnowledgeStore()
        v1 = store.put("exp-1", {"result": "unresolved"}, author="pi", timestamp_ms=1.0)
        v2 = store.put("exp-1", {"result": "supported"}, author="skeptic", timestamp_ms=2.0)
        assert store.get("exp-1").content["result"] == "supported"
        assert [v.version for v in store.history("exp-1")] == [1, 2]
        assert v1.hash != v2.hash

    def test_export_import_round_trip(self, tmp_path: Path):
        store = KnowledgeStore(tmp_path / "ks")
        store.put("a", {"x": 1}, timestamp_ms=1.0)
        store.flush()
        copy = KnowledgeStore(tmp_path / "ks-copy")
        copy.import_state(store.export_state())
        assert copy.get("a").content == {"x": 1}

    def test_persistence_across_restart(self, tmp_path: Path):
        root = tmp_path / "ks"
        store = KnowledgeStore(root)
        store.put("doc", {"n": 1}, timestamp_ms=1.0)
        store.flush()
        reopened = KnowledgeStore(root)
        assert reopened.get("doc").content == {"n": 1}

    def test_conflict_detection_and_resolution(self):
        left = KnowledgeStore()
        right = KnowledgeStore()
        left.put("shared", {"verdict": "supported"}, timestamp_ms=1.0)
        right.put("shared", {"verdict": "contradicted"}, timestamp_ms=1.0)
        conflicts = left.detect_conflicts(right)
        assert len(conflicts) == 1
        assert isinstance(conflicts[0], Conflict)

        merged = KnowledgeStore()
        merged.import_state(left.export_state())
        merged.import_state(right.export_state())
        # Both branches survive; a resolution record explains the divergence.
        hashes = {v.hash for v in merged.history("shared")}
        assert len(hashes) == 2
        assert merged.resolutions
        assert merged.get("shared").content in ({"verdict": "supported"}, {"verdict": "contradicted"})

    def test_bad_state_version_rejected(self):
        import json as _json

        from rain_atlas.knowledge.store import STATE_VERSION

        store = KnowledgeStore()
        bad = _json.dumps({"state_version": STATE_VERSION + 99, "documents": []}).encode()
        with pytest.raises(ValueError):
            store.import_state(bad)


class TestBrowserSession:
    @pytest.fixture()
    def page(self, tmp_path: Path) -> str:
        html = """
        <html><head><title>Reference Notes</title></head>
        <body>
        <script>var ignored = 1;</script>
        <p>The critical frequency is 440 Hz.</p>
        <a href="/details">Details of the experiment</a>
        </body></html>
        """
        path = tmp_path / "page.html"
        path.write_text(html, encoding="utf-8")
        return path.as_uri()

    def test_observes_structured_state(self, page):
        session = BrowserSession(clock=lambda: 42.0)
        observation = session.fetch(page)
        assert observation.title == "Reference Notes"
        assert "440 Hz" in observation.text
        assert "var ignored" not in observation.text  # scripts skipped
        assert observation.links[0]["text"] == "Details of the experiment"
        assert observation.content_hash.startswith("sha256:")
        assert observation.fetched_at_ms == 42.0

    def test_relative_links_resolved(self, page):
        session = BrowserSession()
        observation = session.fetch(page, base_url="https://example.test/docs/")
        assert observation.links[0]["href"] == "https://example.test/details"

    def test_verification_flag(self, page):
        session = BrowserSession()
        ok = session.fetch(page, expect_text="440 Hz")
        missing = session.fetch(page, expect_text="999 Hz")
        assert ok.verified is True
        assert missing.verified is False
        assert "absent" in missing.verification_note

    def test_missing_file_raises(self):
        session = BrowserSession()
        with pytest.raises(BrowserError):
            session.fetch("file:///nonexistent/path.html")

    def test_unsupported_scheme_rejected(self):
        session = BrowserSession()
        with pytest.raises(BrowserError):
            session.fetch("ftp://example.com/file")

    def test_history_recorded(self, page):
        session = BrowserSession()
        session.fetch(page)
        assert len(session.history()) == 1
