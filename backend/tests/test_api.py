import json
import time
import pytest
from backend.api.storage import Store, Conflict
from backend.api.handler import dispatch, ApiError
from backend.simulation.fixtures import fixtures
from backend.workflows.jobs import job


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def call(
    store,
    path,
    body=None,
    method="GET",
    owner="operator-a",
    key="test_key_001",
    query=None,
):
    return dispatch(
        method, path, owner, body or {}, query or {}, {"idempotency-key": key}, store
    )


def wait(store, run_id, states):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        meta = store.get(f"RUN#{run_id}", "META")
        if meta["status"] in states:
            return meta
        time.sleep(0.03)
    raise AssertionError(f"Run did not reach {states}: {meta}")


def start(store, sid="compound"):
    request = dict(scenario_id=sid, scenario_version=1, horizon=6, agents_active=True)
    code, result = call(store, "/runs", request, "POST")
    assert code == 202
    return result["run_id"], request


def test_owner_isolation_idempotency_and_report(store):
    rid, request = start(store)
    _, duplicate = call(store, "/runs", request, "POST")
    assert rid == duplicate["run_id"]
    with pytest.raises(Conflict):
        call(store, "/runs", {**request, "horizon": 3}, "POST")
    with pytest.raises(ApiError) as error:
        call(store, f"/runs/{rid}", owner="operator-b")
    assert error.value.code == 404
    meta = wait(store, rid, {"awaiting_approval", "infeasible", "failed"})
    assert meta["status"] == "awaiting_approval"
    assert job(rid, "agents", store)["feasible"] is True
    decision = dict(decision="approve", plan_version=1, scenario_version=1)
    _, answer = call(
        store, f"/runs/{rid}/plans/1/decision", decision, "POST", key="approve_test_01"
    )
    assert answer["accepted"]
    wait(store, rid, {"completed", "failed"})
    _, answer = call(
        store, f"/runs/{rid}/plans/1/decision", decision, "POST", key="approve_test_01"
    )
    assert answer["duplicate"]
    _, report = call(store, f"/runs/{rid}/report")
    assert report["report"]["approved"]["verified"]
    _, events = call(store, f"/runs/{rid}/events")
    assert [e["seq"] for e in events["events"]] == list(
        range(1, len(events["events"]) + 1)
    )
    _, missed = call(store, f"/runs/{rid}/events", query={"after_seq": "3"})
    assert missed["events"][0]["seq"] == 4


def test_preview_isolation_and_stale_approval(store):
    rid, _ = start(store)
    wait(store, rid, {"awaiting_approval"})
    draft = fixtures()[3].model_dump(mode="json")
    draft["zones"][0]["demand"] += 5
    _, preview = call(
        store, "/scenario-previews", dict(scenario=draft, horizon=6), "POST"
    )
    assert preview["isolated"]
    assert (
        preview["draft"]["totals"]["requested"]
        > preview["applied"]["totals"]["requested"]
    )
    _, current = call(store, "/scenarios/compound")
    assert current["scenario_version"] == 1
    _, applied = call(store, "/scenarios/compound/versions", draft, "POST")
    assert applied["scenario_version"] == 2
    with pytest.raises(Conflict):
        call(
            store,
            f"/runs/{rid}/plans/1/decision",
            dict(decision="approve", plan_version=1, scenario_version=1),
            "POST",
        )
    with pytest.raises(Conflict):
        call(store, "/scenarios/compound/versions", draft, "POST")


def test_infeasible_escalation_and_retry_checkpoints(store):
    rid, _ = start(store, "infeasible")
    meta = wait(store, rid, {"infeasible", "failed"})
    assert meta["status"] == "infeasible"
    assert store.object_get(meta["plan_key"])["violations"]
    before = store.get(f"RUN#{rid}", "META")["event_seq"]
    job(rid, "baseline", store)
    assert job(rid, "agents", store)["feasible"] is False
    assert store.get(f"RUN#{rid}", "META")["event_seq"] == before


def test_public_cannot_modify_and_does_not_route_on_water_graph(store):
    with pytest.raises(ApiError) as err:
        call(store, "/runs", {}, "POST", owner=None)
    assert err.value.code == 401
    from backend.api.public import route
    from datetime import datetime
    from zoneinfo import ZoneInfo

    scenario = fixtures()[0]
    for edge in scenario.connections:
        edge.control = "closed"
    routing = route(
        scenario, "B", now=datetime(2026, 10, 9, 12, tzinfo=ZoneInfo("Asia/Kolkata"))
    )
    assert routing["route"]
    assert routing["route"]["graph"] == "seeded pedestrian graph"
    scenario.stations[0].open = False
    scenario.stations[2].water_available = False
    scenario.stations[4].occupancy = scenario.stations[4].capacity
    assert (
        route(
            scenario,
            "B",
            now=datetime(2026, 10, 9, 12, tzinfo=ZoneInfo("Asia/Kolkata")),
        )["route"]
        is None
    )
