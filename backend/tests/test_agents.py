from backend.simulation.fixtures import fixtures
from backend.simulation.engine import simulate
from backend.agents.planner import investigate_and_plan
from backend.agents.tools import agent_view, observations, ToolRegistry
import pytest
from backend.agents.negotiation import negotiate


def test_hidden_truth_and_result_driven_path():
    scenario = fixtures()[3]
    view = agent_view(scenario)
    assert all(z.supply_loss == 0.03 for z in view.zones)
    assert all(c.loss == 0.02 for c in view.connections)
    assert "compound" not in view.description
    checkpoints = []
    result = investigate_and_plan(
        scenario, 6, simulate(scenario), checkpoint=checkpoints.append
    )
    assert result["anomaly_zones"]
    assert result["candidates"]
    assert any(e["tool"] == "simulate_candidate_fault" for e in result["evidence"])
    resumed = investigate_and_plan(
        scenario, 6, simulate(scenario), restored=checkpoints[-1]
    )
    assert resumed["plan"] == result["plan"]
    assert len(resumed["evidence"]) == len(result["evidence"])


def test_normal_path_skips_fault_tests():
    scenario = fixtures()[0]
    result = investigate_and_plan(scenario, 3, simulate(scenario))
    assert "test" not in result["completed"]
    assert result["mode"] == "deterministic fallback"


def test_typed_tool_rejects_bad_ids():
    scenario = fixtures()[0]
    registry = ToolRegistry(scenario, 3, observations(scenario, simulate(scenario, 3)))
    with pytest.raises(ValueError):
        registry.call("simulate_candidate_fault", {"zone_id": "Z"})
    with pytest.raises(ValueError):
        registry.call("arbitrary_code", {})


def test_negotiation_conserves_offers_and_uses_real_feedback():
    scenario = fixtures()[3]
    baseline = simulate(scenario)
    result = negotiate(scenario, 6, baseline)
    assert result["trades"]
    first = {m["zone_id"]: m for m in result["messages"] if m["round"] == 1}
    second = {m["zone_id"]: m for m in result["messages"] if m["round"] == 2}
    assert any(second[z]["request_rate"] < first[z]["request_rate"] for z in first)
    for donor in first:
        sent = sum(t["outflow_rate"] for t in result["trades"] if t["donor"] == donor)
        assert sent <= first[donor]["maximum_offer_rate"] + 1e-8
    for t in result["trades"]:
        assert t["outflow_rate"] == pytest.approx(t["inflow_rate"] + t["loss_rate"])


def test_constant_residual_retains_loss_and_reading_ambiguity():
    scenario = fixtures()[2]
    result = investigate_and_plan(scenario, 6, simulate(scenario))
    supply = next(
        c
        for c in result["candidates"]
        if c["zone_id"] == "E" and c["hypothesis"] == "supply_loss"
    )
    reading = next(
        c
        for c in result["candidates"]
        if c["zone_id"] == "E" and c["hypothesis"] == "faulty_reading"
    )
    assert supply["fit_mse"] == pytest.approx(reading["fit_mse"], abs=1e-9)
    assert supply["fit_mse"] < 1e-8


def test_forecast_range_preserves_essential_demand_floor():
    scenario = fixtures()[0]
    scenario.zones[0].critical_demand = scenario.zones[0].demand
    registry = ToolRegistry(scenario, 3, observations(scenario, simulate(scenario, 3)))
    forecast = registry.call("forecast_storage", {})
    assert len(forecast["storage_range"]) == 2
    assert forecast["storage_range"][0] <= forecast["storage_range"][1]
