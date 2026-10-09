from backend.api.storage import get_store
from backend.simulation.models import Scenario, Action
from backend.simulation.engine import simulate, verify_plan
from backend.agents.planner import investigate_and_plan
import time
import hashlib
import json


def status(store, run_id, value, **fields):
    pk = f"RUN#{run_id}"
    for _ in range(10):
        meta = store.get(pk, "META")
        next_status = value if value is not None else meta["status"]
        if meta["status"] == next_status and all(
            meta.get(k) == v for k, v in fields.items()
        ):
            return meta
        from backend.api.storage import Conflict

        try:
            updated = {
                **meta,
                "status": next_status,
                "updated_at": time.time(),
                **fields,
            }
            store.compare_put(pk, "META", meta, updated)
            return updated
        except Conflict:
            continue
    raise RuntimeError("Run metadata contention")


def job(run_id, phase, store=None, task_token=None):
    store = store or get_store()
    pk = f"RUN#{run_id}"
    meta = store.get(pk, "META")
    scenario = Scenario.model_validate(store.object_get(meta["snapshot_key"]))
    prefix = f"runs/{run_id}"
    horizon = meta["horizon"]
    if phase == "baseline":
        key = f"{prefix}/baseline.json"
        if not meta.get("baseline_key"):
            status(store, run_id, "simulating")
            result = simulate(scenario, horizon)
            store.object_put(key, result)
            status(
                store,
                run_id,
                "baseline_complete",
                baseline_key=key,
                model_version=result["model_version"],
                baseline_totals=result["totals"],
            )
        store.event(
            run_id,
            "simulation",
            "Baseline computed and mass balance verified",
            event_key="baseline",
        )
    elif phase == "agents":
        phase_started = time.perf_counter()
        if meta.get("plan_key"):
            cached = store.object_get(meta["plan_key"])
            if meta["status"] == "job_retrying":
                status(
                    store, run_id, "plan_ready" if cached["feasible"] else "infeasible"
                )
            return dict(run_id=run_id, feasible=cached["feasible"])
        status(store, run_id, "investigating")
        baseline = store.object_get(meta["baseline_key"])
        if meta["agents_active"]:
            restored = store.get(pk, "AGENTSTATE")
            if restored and restored.get("state_key"):
                restored = store.object_get(restored["state_key"])

            def persist_agent(state):
                digest = hashlib.sha256(
                    json.dumps(state, sort_keys=True).encode()
                ).hexdigest()
                state_key = store.object_put(
                    f"{prefix}/checkpoints/{digest}.json", state
                )
                compact = {
                    k: state[k]
                    for k in [
                        "completed",
                        "configuration_hash",
                        "agent_version",
                        "next_node",
                        "llm_calls",
                        "mode",
                    ]
                    if k in state
                }
                store.put(pk, "AGENTSTATE", {**compact, "state_key": state_key})
                for i, evidence in enumerate(state["evidence"]):
                    store.event(
                        run_id,
                        "tool",
                        f"Executed {evidence['tool']}",
                        dict(tool=evidence["tool"], arguments=evidence["arguments"]),
                        event_key=f"tool-{i}",
                    )
                for node in state["completed"]:
                    store.event(
                        run_id,
                        "agent_step",
                        f"Completed bounded {node} step",
                        dict(next_node=state["next_node"]),
                        event_key=f"node-{node}",
                    )

            agent = investigate_and_plan(
                scenario,
                horizon,
                baseline,
                restored=restored,
                checkpoint=persist_agent,
            )
            proposed = agent["plan"]
            for i, evidence in enumerate(agent["evidence"]):
                store.event(
                    run_id,
                    "tool",
                    f"Executed {evidence['tool']}",
                    dict(tool=evidence["tool"], arguments=evidence["arguments"]),
                    event_key=f"tool-{i}",
                )
        else:
            check = verify_plan(scenario, horizon, [])
            proposed = dict(
                plan_version=1,
                scenario_version=scenario.scenario_version,
                actions=[],
                feasible=check["feasible"],
                violations=check["violations"],
                alternatives=[],
                candidate_sites=[],
                reasons=["Agents paused: direct simulation only"],
                mode="agents paused",
            )
            agent = dict(
                mode="agents paused",
                llm_calls=0,
                evidence=[],
                completed=[],
                plan=proposed,
            )
        for alternative in proposed["alternatives"]:
            check = verify_plan(
                scenario,
                horizon,
                [Action.model_validate(a) for a in alternative["actions"]],
            )
            alternative.update(
                feasible=check["feasible"],
                violations=check["violations"],
                totals=check["result"]["totals"],
            )
            alternative["score"] = (
                check["result"]["totals"]["unmet"] * 100
                + check["result"]["totals"]["losses"]
            )
        actual = verify_plan(
            scenario, horizon, [Action.model_validate(a) for a in proposed["actions"]]
        )
        if not actual["feasible"]:
            alternatives = sorted(
                (a for a in proposed["alternatives"] if a["feasible"]),
                key=lambda a: a["score"],
            )
            if alternatives:
                store.event(
                    run_id,
                    "replan",
                    "Verifier rejected the proposed plan; selected a measured feasible alternative",
                    dict(violations=actual["violations"]),
                    event_key="replan",
                )
                proposed["actions"] = alternatives[0]["actions"]
                actual = verify_plan(
                    scenario,
                    horizon,
                    [Action.model_validate(a) for a in proposed["actions"]],
                )
        proposed.update(
            feasible=actual["feasible"],
            violations=actual["violations"],
            verified_totals=actual["result"]["totals"],
        )
        proposed.update(run_id=run_id, scenario_id=scenario.scenario_id)
        plan_key = store.object_put(f"{prefix}/plan-1.json", proposed)
        agent_key = store.object_put(f"{prefix}/agent-evidence.json", agent)
        status(
            store,
            run_id,
            "plan_ready" if actual["feasible"] else "infeasible",
            plan_key=plan_key,
            agent_key=agent_key,
            plan_version=1,
            agent_mode=agent["mode"],
            llm_calls=agent["llm_calls"],
            provider_error=agent.get("provider_error"),
            agent_elapsed_ms=(time.perf_counter() - phase_started) * 1000,
        )
        store.event(
            run_id,
            "verification",
            "Plan passed actual-scenario critical-service verification"
            if actual["feasible"]
            else "No verified feasible plan; essential-service shortfall requires escalation",
            event_key="plan",
        )
    elif phase == "wait":
        if meta["status"] == "infeasible":
            return dict(run_id=run_id, feasible=False)
        if task_token:
            store.put(
                pk,
                "CALLBACK",
                dict(
                    token=task_token,
                    plan_version=meta["plan_version"],
                    scenario_version=meta["scenario_version"],
                ),
            )
        status(store, run_id, "awaiting_approval")
        store.event(
            run_id,
            "approval",
            "Verified plan ready for exact-version operator approval",
            event_key="waiting",
        )
    elif phase == "apply":
        decision = store.get(pk, "DECISION")
        if not decision or decision["decision"] != "approve":
            raise ValueError("Approved decision is required")
        if meta.get("result_key"):
            return dict(run_id=run_id)
        current_scenario = store.get(
            f"OWNER#{meta['owner']}", f"SCENARIO#{meta['scenario_id']}"
        )
        if current_scenario["scenario_version"] != meta["scenario_version"]:
            raise ValueError(
                "Scenario edit invalidated approved actions before application"
            )
        status(store, run_id, "applying")
        plan = store.object_get(meta["plan_key"])
        actions = [Action.model_validate(a) for a in plan["actions"]]
        check = verify_plan(scenario, horizon, actions)
        if not check["feasible"]:
            raise ValueError("Approved plan failed re-verification")
        result_key = store.object_put(f"{prefix}/approved-result.json", check["result"])
        status(
            store,
            run_id,
            "verified",
            result_key=result_key,
            result_totals=check["result"]["totals"],
        )
        store.event(
            run_id,
            "outcome",
            "Approved actions simulated; mass balance and critical supply verified",
            event_key="applied",
        )
    elif phase == "failure":
        status(store, run_id, "failed")
        store.event(
            run_id,
            "error",
            "Workflow exhausted retries or approval timed out",
            event_key="workflow-failed",
        )
    elif phase == "report":
        report = dict(
            run_id=run_id,
            scenario_id=scenario.scenario_id,
            scenario_version=scenario.scenario_version,
            baseline=store.object_get(meta["baseline_key"]),
            plan=store.object_get(meta["plan_key"]) if meta.get("plan_key") else None,
            approved=store.object_get(meta["result_key"])
            if meta.get("result_key")
            else None,
            agent=store.object_get(meta["agent_key"])
            if meta.get("agent_key")
            else None,
            synthetic=True,
            limitations=[
                "Aggregate zone model; no hydraulics or pipe-level localization",
                "Scenario forecasts are not calibrated predictions",
                "Public facilities and walking routes are synthetic",
                "Supply restoration depends on configured availability assumptions",
            ],
            events=store.list(pk, "EVENT#"),
        )
        key = store.object_put(f"{prefix}/report.json", report)
        decision = store.get(pk, "DECISION")
        final_status = (
            "completed"
            if meta.get("result_key")
            else "rejected"
            if decision and decision["decision"] == "reject"
            else meta["status"]
        )
        status(
            store,
            run_id,
            final_status,
            report_key=key,
            elapsed_seconds=time.time() - meta["created_at"],
        )
        store.event(
            run_id,
            "report",
            "Evidence report saved; reopen it from this run",
            event_key="report",
        )
    return dict(run_id=run_id, feasible=store.get(pk, "META")["status"] != "infeasible")


def handler(event, context):
    store = get_store()
    try:
        return job(event["run_id"], event["phase"], store, event.get("task_token"))
    except Exception as exc:
        status(store, event["run_id"], "job_retrying", error_type=type(exc).__name__)
        store.event(
            event["run_id"],
            "error",
            "Bounded job failed; workflow retry will resume persisted state",
            dict(phase=event["phase"], error_type=type(exc).__name__),
        )
        raise


def local_start(run_id, store):
    try:
        job(run_id, "baseline", store)
        job(run_id, "agents", store)
        if store.get(f"RUN#{run_id}", "META")["status"] == "infeasible":
            job(run_id, "report", store)
        else:
            job(run_id, "wait", store)
    except Exception as exc:
        status(store, run_id, "failed", error_type=type(exc).__name__)
        store.event(
            run_id,
            "error",
            "Run failed; inspect evidence and retry",
            dict(error_type=type(exc).__name__),
        )


def local_apply(run_id, store):
    try:
        job(run_id, "apply", store)
        job(run_id, "report", store)
    except Exception as exc:
        status(store, run_id, "failed", error_type=type(exc).__name__)
