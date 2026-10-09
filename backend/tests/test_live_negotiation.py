from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from backend.agents import planner
from backend.agents.negotiation import negotiate, CheckpointFailure
from backend.simulation.engine import simulate
from backend.simulation.fixtures import fixtures


def proposals(context, fraction=0.4):
    return dict(proposals=[dict(
        zone_id=z["zone_id"], request_rate=z["maximum_request_rate"],
        offer_rate=z["maximum_offer_rate"] * fraction,
        reason="Retain reserves and share bounded surplus") for z in context["zones"]])


class Provider:
    def __init__(self, malformed=False):
        self.requests = []
        self.malformed = malformed
        self.models = SimpleNamespace(list=lambda: SimpleNamespace(data=[SimpleNamespace(id="test-model")]))
        self.chat = SimpleNamespace(completions=SimpleNamespace(with_raw_response=SimpleNamespace(create=self.create)))

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        name = kwargs["tool_choice"]["function"]["name"]
        context = json.loads(kwargs["messages"][1]["content"])
        args = dict(zone_id="E", hypothesis="faulty_reading", magnitude=0.2) if name == "simulate_candidate_fault" else proposals(context)
        if self.malformed and name == "propose_zone_round":
            args["proposals"][0]["offer_rate"] = 1000
        usage = dict(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        message = SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(name=name, arguments=json.dumps(args)))])
        result = SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=SimpleNamespace(model_dump=lambda: usage))
        return SimpleNamespace(parse=lambda: result, headers={"x-ratelimit-remaining-tokens": "7000"})


def configure(monkeypatch, provider):
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setenv("GROQ_API_KEY", "placeholder")
    monkeypatch.setattr(planner, "groq_client", lambda: provider)


def test_live_proposals_change_trades_and_round_two_uses_feedback():
    scenario = fixtures()[3]
    baseline = simulate(scenario)
    contexts = []

    def propose(context):
        contexts.append(deepcopy(context))
        return proposals(context, fraction=0.2)

    live = negotiate(scenario, 6, baseline, propose=propose)
    fallback = negotiate(scenario, 6, baseline)
    assert live["mode"] == "live Groq zone negotiation + deterministic coordinator"
    assert live["trades"] != fallback["trades"]
    assert len(contexts) == 2
    assert contexts[1]["previous_trades"]
    initial = {z["zone_id"]: z for z in contexts[0]["zones"]}
    for zone in initial:
        sent = sum(t["outflow_rate"] for t in live["trades"] if t["donor"] == zone)
        assert sent <= initial[zone]["maximum_offer_rate"] + 1e-8
    assert all(value >= -1e-8 for value in live["remaining_offers"].values())
    for connection in scenario.connections:
        assert sum(t["outflow_rate"] for t in live["trades"] if t["connection_id"] == connection.id) <= connection.capacity


@pytest.mark.parametrize("bad", ["over_budget", "duplicate", "nonfinite", "no_agreement"])
def test_invalid_or_non_agreeing_proposals_fall_back_without_claiming_live_agreement(bad):
    scenario = fixtures()[3]

    def invalid(context):
        body = proposals(context)
        if bad == "over_budget":
            body["proposals"][0]["offer_rate"] = 999
        elif bad == "duplicate":
            body["proposals"][0]["zone_id"] = "B"
        elif bad == "nonfinite":
            body["proposals"][0]["offer_rate"] = float("nan")
        else:
            for proposal in body["proposals"]:
                proposal["offer_rate"] = 0
        return body

    result = negotiate(scenario, 6, simulate(scenario), propose=invalid)
    assert result["mode"] == "deterministic fallback"
    assert result["fallback_reasons"]
    assert result["trades"]


def test_provider_rounds_are_bounded_usage_aggregated_and_ground_truth_excluded(monkeypatch):
    provider = Provider()
    configure(monkeypatch, provider)
    scenario = fixtures()[3]
    result = planner.investigate_and_plan(scenario, 6, simulate(scenario))
    assert result["llm_calls"] == len(provider.requests) == 3
    assert result["provider_usage"]["total_tokens"] == 450
    assert result["plan"]["feasible"]
    assert result["negotiation_mode"] == "live Groq zone negotiation + deterministic coordinator"
    assert any(e["tool"] == "propose_zone_round" for e in result["evidence"])
    contexts = [json.loads(request["messages"][1]["content"]) for request in provider.requests[1:]]
    assert contexts[1]["previous_trades"]
    assert "supply_loss" not in json.dumps(contexts)
    assert "compound" not in json.dumps(contexts)
    assert all(c["loss"] == 0.02 for c in contexts[0]["connections"])


def test_completed_round_survives_checkpoint_failure_without_another_provider_call(monkeypatch):
    provider = Provider()
    configure(monkeypatch, provider)
    scenario = fixtures()[3]
    snapshots = []

    def checkpoint(state):
        snapshots.append(deepcopy(state))
        if state.get("provider_calls", {}).get("negotiation-round-1", {}).get("status") == "completed":
            raise RuntimeError("Injected interruption after saved provider response")

    with pytest.raises(CheckpointFailure):
        planner.investigate_and_plan(scenario, 6, simulate(scenario), checkpoint=checkpoint)
    assert len(provider.requests) == 2
    result = planner.investigate_and_plan(scenario, 6, simulate(scenario), restored=snapshots[-1])
    assert len(provider.requests) == result["llm_calls"] == 3
    assert result["plan"]["feasible"]


def test_interrupted_attempt_uses_fallback_and_does_not_repeat_that_round(monkeypatch):
    provider = Provider()
    configure(monkeypatch, provider)
    scenario = fixtures()[3]
    snapshots = []

    def checkpoint(state):
        snapshots.append(deepcopy(state))
        if state.get("provider_calls", {}).get("negotiation-round-1", {}).get("status") == "attempted":
            raise RuntimeError("Injected interruption before provider response")

    with pytest.raises(CheckpointFailure):
        planner.investigate_and_plan(scenario, 6, simulate(scenario), checkpoint=checkpoint)
    result = planner.investigate_and_plan(scenario, 6, simulate(scenario), restored=snapshots[-1])
    assert len(provider.requests) == 2
    assert result["llm_calls"] == 3
    assert result["negotiation_fallback_reasons"]
    assert result["plan"]["feasible"]
