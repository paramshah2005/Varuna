from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.api.storage import Store, Conflict
from backend.agents import planner
from backend.agents.tools import ToolRegistry
from backend.simulation.fixtures import fixtures
from backend.simulation.engine import simulate


def test_node_failure_resumes_without_repeating_completed_investigation(monkeypatch):
    scenario = fixtures()[3]
    snapshots = []
    original = ToolRegistry.call

    def failing(self, name, args):
        if name == "evaluate_isolation_options":
            raise RuntimeError("Injected bounded job failure")
        return original(self, name, args)

    monkeypatch.setattr(ToolRegistry, "call", failing)
    with pytest.raises(RuntimeError):
        planner.investigate_and_plan(
            scenario, 6, simulate(scenario), checkpoint=snapshots.append
        )
    assert snapshots[-1]["completed"] == ["detect", "test"]
    monkeypatch.setattr(ToolRegistry, "call", original)
    resumed = planner.investigate_and_plan(
        scenario, 6, simulate(scenario), restored=snapshots[-1]
    )
    assert resumed["completed"] == ["detect", "test", "plan"]
    assert sum(e["tool"] == "get_observation_history" for e in resumed["evidence"]) == 1
    assert any(not a["feasible"] for a in resumed["plan"]["alternatives"])


def test_provider_failure_is_truthful_and_bounded(monkeypatch):
    class Unavailable:
        class models:
            @staticmethod
            def list():
                raise RuntimeError("Provider unavailable")

    monkeypatch.setenv("GROQ_MODEL", "configured-model")
    monkeypatch.setenv("GROQ_SECRET_NAME", "placeholder")
    monkeypatch.setattr(planner, "groq_client", lambda: Unavailable())
    scenario = fixtures()[3]
    result = planner.investigate_and_plan(scenario, 3, simulate(scenario, 3))
    assert result["mode"] == "deterministic fallback"
    assert result["provider_error"]
    assert result["plan"]["feasible"]


def test_atomic_versions_and_contiguous_parallel_events(tmp_path):
    store = Store(tmp_path)
    store.put("RUN#test", "META", dict(event_seq=0))
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda i: store.event("test", "test", str(i)), range(15)))
    assert [e["seq"] for e in store.list("RUN#test", "EVENT#")] == list(range(1, 16))
    store.atomic_puts(
        [
            dict(pk="scenario", sk="current", body=dict(version=1)),
            dict(pk="scenario", sk="v1", body=dict(version=1)),
        ]
    )
    with pytest.raises(Conflict):
        store.atomic_puts(
            [
                dict(
                    pk="scenario",
                    sk="current",
                    old=dict(version=0),
                    body=dict(version=2),
                ),
                dict(pk="scenario", sk="v2", body=dict(version=2)),
            ]
        )
    assert store.get("scenario", "v2") is None
