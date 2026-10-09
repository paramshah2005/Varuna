import json
import os
from typing import TypedDict
from langgraph.graph import END, StateGraph
from backend.agents.tools import ToolRegistry, agent_view, observations
from backend.simulation.engine import simulate, verify_plan, configuration_hash
from backend.simulation.models import Action
from backend.agents.negotiation import negotiate
from backend.agents.negotiation import RoundProposals, CheckpointFailure


class AgentState(TypedDict, total=False):
    configuration_hash: str
    agent_version: str
    next_node: str
    completed: list[str]
    evidence: list[dict]
    anomaly_zones: list[str]
    candidates: list[dict]
    mode: str
    llm_calls: int
    provider_error: str | None
    plan: dict
    negotiation: list[dict]
    provider_usage: dict
    quota_headers: dict
    provider_calls: dict
    negotiation_mode: str
    negotiation_fallback_reasons: list[str]


def groq_client():
    secret_name = os.getenv("GROQ_SECRET_NAME")
    if not secret_name:
        if os.getenv("GROQ_API_KEY") and not os.getenv("TABLE_NAME"):
            from groq import Groq

            return Groq(api_key=os.environ["GROQ_API_KEY"], timeout=12, max_retries=0)
        return None
    import boto3
    from groq import Groq

    raw = boto3.client("secretsmanager").get_secret_value(SecretId=secret_name)[
        "SecretString"
    ]
    try:
        key = json.loads(raw)["api_key"]
    except (ValueError, KeyError, TypeError):
        key = raw
    return Groq(api_key=key, timeout=12, max_retries=0)


def reasoning_options(model):
    return {"reasoning_effort": "low"} if model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"} else {}


def investigate_and_plan(scenario, horizon, baseline, restored=None, checkpoint=None):
    expected_hash = configuration_hash(scenario, horizon)
    if restored and restored.get("configuration_hash") != expected_hash:
        raise ValueError("Persisted graph configuration changed; create a new run")
    state = restored or dict(
        completed=[],
        evidence=[],
        llm_calls=0,
        mode="deterministic fallback",
        provider_error=None,
        configuration_hash=expected_hash,
        agent_version="bounded-graph-1.1.0",
        next_node="detect",
    )
    visible = agent_view(scenario)
    history = observations(scenario, baseline)
    registry = ToolRegistry(visible, horizon, history, state["evidence"])

    def persist(name, change, current):
        merged = {
            **current,
            **change,
            "evidence": registry.evidence,
            "completed": [*current.get("completed", []), name],
            "next_node": (
                "test"
                if change.get("anomaly_zones")
                or scenario.observation_mode != "complete"
                else "plan"
            )
            if name == "detect"
            else "plan"
            if name == "test"
            else "END",
        }
        if checkpoint:
            checkpoint(merged)
        return merged

    def detect(current):
        if "detect" in current.get("completed", []):
            return current
        registry.call("compare_baseline", {})
        anomalies = sorted(
            {
                o["zone_id"]
                for o in history
                if o["residual"] is not None and abs(o["residual"]) > 0.5
            }
        )
        registry.call("get_observation_history", {})
        return persist("detect", dict(anomaly_zones=anomalies), current)

    def test(current):
        if "test" in current.get("completed", []):
            return current
        candidates = []
        mode, error, calls = current["mode"], None, current.get("llm_calls", 0)
        selection = None
        model = os.getenv("GROQ_MODEL")
        if (
            calls < 1
            and model
            and (os.getenv("GROQ_SECRET_NAME") or os.getenv("GROQ_API_KEY"))
        ):
            try:
                client = groq_client()
                if model not in {m.id for m in client.models.list().data}:
                    raise ValueError("Configured model not accessible")
                calls += 1
                if checkpoint:
                    checkpoint(
                        {**current, "llm_calls": calls, "evidence": registry.evidence}
                    )
                sample = [
                    o
                    for o in history
                    if o["residual"] is not None and abs(o["residual"]) > 0.5
                ][:8] or history[:8]
                raw_response = client.chat.completions.with_raw_response.create(
                    model=model,
                    **reasoning_options(model),
                    max_completion_tokens=600,
                    temperature=0,
                    messages=[
                        dict(
                            role="system",
                            content="You must call simulate_candidate_fault once. Select a zone and hypothesis using observed residuals. A loss is a hypothesis, not a fact. Test alternatives to supply loss: demand surge or faulty measurement. Only valid zones A-F.",
                        ),
                        dict(
                            role="user",
                            content=json.dumps(
                                dict(
                                    anomaly_zones=current["anomaly_zones"],
                                    observations=sample,
                                )
                            ),
                        ),
                    ],
                    tools=[
                        dict(
                            type="function",
                            function=dict(
                                name="simulate_candidate_fault",
                                description="Compare a hypothetical loss or reading error against observations",
                                parameters=dict(
                                    type="object",
                                    properties=dict(
                                        zone_id=dict(
                                            type="string", enum=list("ABCDEF")
                                        ),
                                        hypothesis=dict(
                                            type="string",
                                            enum=[
                                                "supply_loss",
                                                "demand_surge",
                                                "faulty_reading",
                                            ],
                                        ),
                                        magnitude=dict(
                                            type="number", minimum=0, maximum=0.8
                                        ),
                                    ),
                                    required=["zone_id", "hypothesis", "magnitude"],
                                    additionalProperties=False,
                                ),
                            ),
                        )
                    ],
                    tool_choice={
                        "type": "function",
                        "function": {"name": "simulate_candidate_fault"},
                    },
                )
                completion = raw_response.parse()
                current["provider_usage"] = (
                    completion.usage.model_dump() if completion.usage else {}
                )
                current.setdefault("provider_calls", {})["investigation"] = dict(
                    status="completed", model=model, usage=current["provider_usage"]
                )
                current["quota_headers"] = {
                    k: v
                    for k, v in raw_response.headers.items()
                    if k.startswith("x-ratelimit")
                }
                tool_calls = completion.choices[0].message.tool_calls or []
                if (
                    not tool_calls
                    or tool_calls[0].function.name != "simulate_candidate_fault"
                ):
                    raise ValueError("Provider did not return the required typed tool")
                selection = json.loads(tool_calls[0].function.arguments)
                candidates.append(registry.call("simulate_candidate_fault", selection))
                mode = "live Groq tool selection + deterministic verification"
            except Exception as exc:
                error = f"Provider unavailable or invalid tool response ({type(exc).__name__}); deterministic fallback used"
        targets = current["anomaly_zones"] or ["E"]
        for zid in targets[:2]:
            zone_readings = [
                o for o in history if o["zone_id"] == zid and o["residual"] is not None
            ]
            mean_residual = (
                sum(o["residual"] for o in zone_readings) / len(zone_readings)
                if zone_readings
                else 0
            )
            mean_external = (
                sum(o["external_gross_m3"] for o in zone_readings) / len(zone_readings)
                if zone_readings
                else 0
            )
            selected_zone = next(z for z in visible.zones if z.id == zid)
            estimates = {
                "supply_loss": 0.03 + mean_residual / mean_external
                if mean_external
                else 0.03,
                "faulty_reading": mean_residual / 10,
                "demand_surge": mean_residual
                / max(1, selected_zone.demand * selected_zone.demand_multiplier * 0.25),
            }
            for hypothesis in ["supply_loss", "demand_surge", "faulty_reading"]:
                candidates.append(
                    registry.call(
                        "simulate_candidate_fault",
                        dict(
                            zone_id=zid,
                            hypothesis=hypothesis,
                            magnitude=max(0, min(0.8, estimates[hypothesis])),
                        ),
                    )
                )
            edge = next(
                (c for c in visible.connections if c.source == zid or c.target == zid),
                None,
            )
            if edge:
                candidates.append(
                    registry.call(
                        "simulate_candidate_fault",
                        dict(
                            zone_id=zid,
                            connection_id=edge.id,
                            hypothesis="connection_loss",
                            magnitude=0.3,
                        ),
                    )
                )
        candidates.sort(
            key=lambda c: c["fit_mse"] if c["fit_mse"] is not None else float("inf")
        )
        registry.call("forecast_storage", {})
        return persist(
            "test",
            dict(
                candidates=candidates, mode=mode, provider_error=error, llm_calls=calls
            ),
            current,
        )

    def plan(current):
        if "plan" in current.get("completed", []):
            return current
        alternatives = registry.call("evaluate_isolation_options", {})
        trial_actions = [
            [Action.model_validate(a) for a in item["actions"]] for item in alternatives
        ]
        provider = None

        def flush_round():
            if checkpoint:
                try:
                    checkpoint({**current, "evidence": registry.evidence})
                except Exception as exc:
                    raise CheckpointFailure("Round checkpoint unavailable") from exc

        def propose(context):
            nonlocal provider
            phase = f"negotiation-round-{context['round']}"
            journal = current.setdefault("provider_calls", {})
            if phase in journal:
                if journal[phase].get("status") == "completed":
                    return journal[phase]["arguments"]
                raise ValueError("Previous round attempt interrupted or failed; no duplicate provider call")
            model = os.getenv("GROQ_MODEL")
            if not model or current.get("llm_calls", 0) >= 3:
                raise ValueError("Provider not configured or run call budget exhausted")
            if any(entry.get("status") == "failed" for entry in journal.values()):
                raise ValueError("Provider unavailable during this run")
            try:
                if provider is None:
                    provider = groq_client()
                    if provider is None or model not in {m.id for m in provider.models.list().data}:
                        raise ValueError("Configured model not accessible")
                journal[phase] = dict(status="attempted", model=model)
                current["llm_calls"] = current.get("llm_calls", 0) + 1
                flush_round()
                raw = provider.chat.completions.with_raw_response.create(
                    model=model, temperature=0, max_completion_tokens=1200,
                    **reasoning_options(model),
                    messages=[
                        dict(role="system", content="Represent six separate logical neighborhood water agents A-F in one batched negotiation round. All request and offer rates are water in cubic metres per hour, never power or energy. Each agent proposes its own requested and offered rates and a brief public water tradeoff reason. Agents retain essential supply and reserves. Choose rates between zero and each measured maximum; offer about half the available surplus per round where useful. Use previous trades and remaining budgets to revise round two. Return propose_zone_round only. These are proposals: a deterministic coordinator controls transfers. Do not infer hidden incidents or claim feasibility."),
                        dict(role="user", content=json.dumps(context)),
                    ],
                    tools=[dict(type="function", function=dict(
                        name="propose_zone_round", description="Propose one bounded request/offer per zone using feedback from prior allocations",
                        parameters=RoundProposals.model_json_schema()))],
                    tool_choice=dict(type="function", function=dict(name="propose_zone_round")),
                )
                response = raw.parse()
                usage = response.usage.model_dump() if response.usage else {}
                journal[phase]["usage"] = usage
                current["provider_usage"] = {
                    key: sum(entry.get("usage", {}).get(key, 0) or 0 for entry in journal.values())
                    for key in ["prompt_tokens", "completion_tokens", "total_tokens"]
                }
                current["quota_headers"] = {k: v for k, v in raw.headers.items() if k.startswith("x-ratelimit")}
                calls = response.choices[0].message.tool_calls or []
                if len(calls) != 1 or calls[0].function.name != "propose_zone_round":
                    raise ValueError("Required negotiation tool missing")
                arguments = RoundProposals.model_validate_json(calls[0].function.arguments).model_dump(mode="json")
                journal[phase].update(status="completed", arguments=arguments)
                flush_round()
                return arguments
            except CheckpointFailure:
                raise
            except Exception as exc:
                body = getattr(exc, "body", {})
                error_body = body.get("error", body) if isinstance(body, dict) else {}
                code = error_body.get("code") if isinstance(error_body, dict) else None
                journal.setdefault(phase, dict(model=model)).update(
                    status="failed", error=type(exc).__name__,
                    status_code=getattr(exc, "status_code", None),
                    error_code=code if isinstance(code, str) and len(code) < 80 else None,
                )
                flush_round()
                raise

        negotiated = negotiate(visible, horizon, baseline, propose=propose)
        current["negotiation_mode"] = negotiated["mode"]
        current["negotiation_fallback_reasons"] = negotiated["fallback_reasons"]
        for round_number in sorted({m["round"] for m in negotiated["messages"]}):
            if not any(e["tool"] == "propose_zone_round" and e["arguments"]["round"] == round_number for e in registry.evidence):
                registry.evidence.append(dict(tool="propose_zone_round", arguments=dict(round=round_number), result=dict(
                    proposals=[m for m in negotiated["messages"] if m["round"] == round_number],
                    trades=[t for t in negotiated["trades"] if t["round"] == round_number],
                    mode=negotiated["mode"], fallback_reasons=negotiated["fallback_reasons"])))
        if negotiated["live_rounds"]:
            current["mode"] = "live Groq zone proposals + deterministic verification" if current["mode"] == "deterministic fallback" else "live Groq investigation and zone proposals + deterministic verification"
        if checkpoint:
            checkpoint({**current, "evidence": registry.evidence})
        trial_actions.append(negotiated["actions"])
        negotiation_check = registry.call(
            "propose_zone_allocation",
            dict(actions=[a.model_dump() for a in negotiated["actions"]]),
        )
        schedule = [
            Action(type="supply", target=z.id, value=z.supply_available)
            for z in visible.zones
            if z.supply < z.supply_available
        ]
        trial_actions.extend([[], schedule])
        implicated = {
            c["connection_id"]
            for c in current.get("candidates", [])
            if c.get("connection_id")
        }
        repair_connections = [
            c
            for c in visible.connections
            if c.id in implicated
            or c.source in current.get("anomaly_zones", [])
            or c.target in current.get("anomaly_zones", [])
        ] or visible.connections
        for c in repair_connections[:3]:
            trial_actions.append(
                [
                    *schedule,
                    Action(type="repair", target=c.id, value=0, at_hour=c.repair_hours),
                ]
            )
        if len(repair_connections) >= 2:
            elapsed = 0
            sequence = []
            for c in repair_connections[:2]:
                elapsed += c.repair_hours
                if elapsed <= horizon:
                    sequence.append(
                        Action(type="repair", target=c.id, value=0, at_hour=elapsed)
                    )
            if sequence:
                trial_actions.append([*schedule, *sequence])
        evaluated = []
        for actions in trial_actions:
            evidence = registry.call(
                "validate_plan", dict(actions=[a.model_dump() for a in actions])
            )
            score = (
                evidence["totals"]["unmet"] * 100
                + evidence["totals"]["losses"]
                + sum(a.value for a in actions if a.type == "supply") * 0.05
            )
            evaluated.append(
                dict(
                    actions=[a.model_dump() for a in actions],
                    feasible=evidence["feasible"],
                    score=score,
                    violations=evidence["violations"],
                    totals=evidence["totals"],
                )
            )
        safe = sorted((c for c in evaluated if c["feasible"]), key=lambda c: c["score"])
        choice = safe[0] if safe else min(evaluated, key=lambda c: c["score"])
        negotiation = negotiated["messages"]
        registry.call("propose_zone_allocation", dict(actions=choice["actions"]))
        registry.call("simulate_supply_schedule", dict(actions=choice["actions"]))
        registry.call("evaluate_recovery_sequence", dict(actions=choice["actions"]))
        underserved = sorted(
            visible.zones,
            key=lambda z: next(
                s["storage"]
                for s in baseline["time_series"][-1]["zones"]
                if s["id"] == z.id
            ),
        )[:2]
        sites = [
            registry.call(
                "evaluate_water_point_site",
                dict(zone_id=z.id, actions=choice["actions"]),
            )
            for z in underserved
        ]
        plan_record = dict(
            plan_version=1,
            scenario_version=scenario.scenario_version,
            actions=choice["actions"],
            feasible=choice["feasible"],
            violations=choice["violations"],
            alternatives=evaluated,
            candidate_sites=sites,
            repair_assumption="One crew; completion only after configured repair duration",
            reasons=[
                "Candidates measured with the zone-balance engine",
                "Critical demand and minimum service are hard constraints",
                "Supply schedule uses configured available throughput; finite starting storage",
            ],
            uncertainty="Aggregate residuals can be explained by loss, demand changes or faulty readings. Fits are not probabilities.",
            negotiation_mode=negotiated["mode"],
            negotiation_fallback_reasons=negotiated["fallback_reasons"],
            negotiated_transfers=negotiated["trades"],
            negotiation_feasible=negotiation_check["feasible"],
            mode=current["mode"],
        )
        return persist("plan", dict(plan=plan_record, negotiation=negotiation), current)

    graph = StateGraph(AgentState)
    graph.add_node("detect", detect)
    graph.add_node("test", test)
    graph.add_node("plan", plan)
    graph.set_entry_point("detect")
    graph.add_conditional_edges(
        "detect",
        lambda s: (
            "test"
            if s.get("anomaly_zones") or scenario.observation_mode != "complete"
            else "plan"
        ),
    )
    graph.add_edge("test", "plan")
    graph.add_edge("plan", END)
    return graph.compile().invoke(state, config={"recursion_limit": 8})
