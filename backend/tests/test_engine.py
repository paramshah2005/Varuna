from copy import deepcopy
import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError
from backend.simulation.fixtures import fixtures
from backend.simulation.models import Action, Scenario
from backend.simulation.engine import simulate, verify_plan


@pytest.mark.parametrize("scenario", fixtures(), ids=lambda s: s.scenario_id)
@pytest.mark.parametrize("horizon", [3, 6, 12])
def test_mass_and_demand_invariants(scenario, horizon):
    result = simulate(scenario, horizon)
    t = result["totals"]
    assert t["starting_storage"] + t["external"] == pytest.approx(
        t["ending_storage"] + t["delivered"] + t["losses"] + t["overflow"], abs=1e-7
    )
    assert t["requested"] == pytest.approx(
        sum(z.demand * z.demand_multiplier for z in scenario.zones) * horizon
    )
    for row in result["time_series"]:
        for state, zone in zip(
            row["zones"], sorted(scenario.zones, key=lambda z: z.id)
        ):
            assert 0 <= state["storage"] <= zone.storage_capacity
            assert 0 <= state["critical_served"] <= state["critical_requested"]
            assert state["critical_served"] <= state["delivered"] <= state["requested"]
            assert state["unmet"] == pytest.approx(
                state["requested"] - state["delivered"]
            )
        for flow in row["connections"]:
            assert flow["outflow"] == pytest.approx(flow["inflow"] + flow["loss"])
            assert flow["rate"] <= flow["capacity"] + 1e-8


def test_reproducibility_and_no_scenario_mutation():
    scenario = fixtures()[3]
    before = scenario.model_dump()
    a, b = simulate(scenario), simulate(scenario)
    a.pop("elapsed_ms")
    b.pop("elapsed_ms")
    assert a == b
    assert scenario.model_dump() == before


def test_zero_supply_empty_storage_and_critical_accounting():
    scenario = fixtures()[5]
    result = simulate(scenario)
    assert result["totals"]["delivered"] == 0
    assert (
        result["totals"]["critical_requested"]
        == sum(z.critical_demand for z in scenario.zones) * 6
    )
    assert not verify_plan(scenario, 6, [])["feasible"]


def test_closed_and_unavailable_connections():
    scenario = fixtures()[3]
    for c in scenario.connections:
        c.available = False
    result = simulate(scenario)
    assert all(
        f["outflow"] == 0 for row in result["time_series"] for f in row["connections"]
    )
    for c in scenario.connections:
        c.available = True
        c.control = "closed"
    assert simulate(scenario)["time_series"] == result["time_series"]


def test_overflow_and_capacity_not_water():
    scenario = fixtures()[0]
    for z in scenario.zones:
        z.storage = z.storage_capacity
    a = simulate(scenario)
    assert a["totals"]["overflow"] > 0
    for z in scenario.zones:
        z.storage_capacity *= 2
    b = simulate(scenario)
    assert b["totals"]["starting_storage"] == a["totals"]["starting_storage"]
    assert b["totals"]["overflow"] < a["totals"]["overflow"]


def test_invalid_edits_and_actions():
    data = fixtures()[0].model_dump()
    data["zones"][0]["storage"] = float("nan")
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)
    typed = fixtures()[0].model_dump(mode="json")
    typed["zones"][0]["storage"] = "200"
    with pytest.raises(ValidationError):
        Scenario.model_validate(typed)
    with pytest.raises(ValueError):
        simulate(fixtures()[0], actions=[Action(type="supply", target="A", value=1000)])
    with pytest.raises(ValueError):
        simulate(
            fixtures()[0],
            actions=[Action(type="repair", target="A-B", value=0, at_hour=0)],
        )


@given(
    st.floats(min_value=0, max_value=0.8, allow_nan=False),
    st.floats(min_value=0, max_value=300, allow_nan=False),
)
@settings(max_examples=50, deadline=None)
def test_random_loss_and_storage_conservation(loss, storage):
    scenario = fixtures()[0]
    scenario.zones[0].supply_loss = loss
    scenario.zones[0].storage = storage
    assert simulate(scenario, 3)["max_mass_residual"] < 1e-7
