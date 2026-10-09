import hashlib
import json
import time
from datetime import datetime, timedelta
import numpy as np
from backend.simulation.models import Action, Scenario

MODEL_VERSION = "zone-balance-1.0.0"
STEP_HOURS = 0.25


def configuration_hash(scenario, horizon, actions=()):
    payload = {
        "scenario": scenario.model_dump(mode="json"),
        "horizon": horizon,
        "actions": [a.model_dump() for a in actions],
        "model_version": MODEL_VERSION,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_actions(scenario, actions):
    zones = {z.id: z for z in scenario.zones}
    edges = {c.id: c for c in scenario.connections}
    repair_times = []
    for action in actions:
        if action.type in {"supply", "water_point"}:
            if action.target not in zones:
                raise ValueError("Unknown zone ID")
            if (
                action.type == "supply"
                and action.value > zones[action.target].supply_available
            ):
                raise ValueError("Supply action exceeds available throughput")
        else:
            if action.target not in edges:
                raise ValueError("Unknown connection ID")
            if (
                action.type == "connection"
                and action.value > edges[action.target].capacity
            ):
                raise ValueError("Transfer action exceeds connection capacity")
            if action.type == "repair":
                if action.at_hour < edges[action.target].repair_hours:
                    raise ValueError("Repair cannot finish before assumed duration")
                if action.value != 0:
                    raise ValueError("Repair value must be zero")
                repair_times.append(
                    (action.at_hour - edges[action.target].repair_hours, action.at_hour)
                )
    for i, (start, end) in enumerate(repair_times):
        if any(max(start, s) < min(end, e) for s, e in repair_times[i + 1 :]):
            raise ValueError("Repair sequences exceed one available crew")


def simulate(scenario: Scenario, horizon: int = 6, actions: list[Action] | None = None):
    if horizon not in {3, 6, 12}:
        raise ValueError("Horizon must be 3, 6, or 12 hours")
    started = time.perf_counter()
    actions = actions or []
    validate_actions(scenario, actions)
    zones = sorted(scenario.zones, key=lambda z: z.id)
    index = {z.id: i for i, z in enumerate(zones)}
    storage = np.array([z.storage for z in zones], dtype=float)
    capacity = np.array([z.storage_capacity for z in zones])
    reserve = np.array([z.reserve for z in zones])
    demand_rate = np.array([z.demand * z.demand_multiplier for z in zones])
    critical_rate = np.array([z.critical_demand for z in zones])
    records = []
    total = dict(
        external=0.0,
        delivered=0.0,
        requested=0.0,
        losses=0.0,
        overflow=0.0,
        critical_requested=0.0,
        critical_served=0.0,
    )
    max_residual = 0.0
    for step in range(horizon * 4):
        hour = step * STEP_HOURS
        start_storage = storage.copy()
        supply = np.array([z.supply for z in zones])
        if scenario.recovery_at_hour is not None and hour >= scenario.recovery_at_hour:
            for zid, value in scenario.recovered_supply.items():
                supply[index[zid]] = value
        extra_demand = np.zeros(6)
        for a in actions:
            if hour >= a.at_hour:
                if a.type == "supply":
                    supply[index[a.target]] = a.value
                elif a.type == "water_point":
                    extra_demand[index[a.target]] += a.value
        gross = supply * STEP_HOURS
        supply_loss = gross * np.array([z.supply_loss for z in zones])
        pool = storage + gross - supply_loss
        requested = (demand_rate + extra_demand) * STEP_HOURS
        critical = critical_rate * STEP_HOURS
        incoming = np.zeros(6)
        outgoing = np.zeros(6)
        connection_loss = np.zeros(6)
        flows = []
        for c in sorted(scenario.connections, key=lambda c: c.id):
            limit = c.capacity if c.available and c.control != "closed" else 0.0
            if c.control == "restricted":
                limit *= 0.5
            loss = c.loss
            for a in actions:
                if a.target == c.id and hour >= a.at_hour:
                    if a.type == "connection":
                        limit = min(limit, a.value)
                    if a.type == "repair":
                        loss = 0.02
                        limit = c.capacity
            u, v = index[c.source], index[c.target]
            urgency_u = max(0, requested[u] + reserve[u] - pool[u]) * zones[u].priority
            urgency_v = max(0, requested[v] + reserve[v] - pool[v]) * zones[v].priority
            donor, receiver = (u, v) if urgency_v > urgency_u else (v, u)
            amount = 0.0
            if limit and (c.bidirectional or donor == u):
                excess = max(0, pool[donor] - requested[donor] - reserve[donor])
                deficit = max(
                    0, requested[receiver] + reserve[receiver] - pool[receiver]
                )
                amount = min(limit * STEP_HOURS, excess, deficit / (1 - loss))
            received = amount * (1 - loss)
            pool[donor] -= amount
            pool[receiver] += received
            outgoing[donor] += amount
            incoming[receiver] += received
            connection_loss[donor] += amount - received
            flows.append(
                dict(
                    connection_id=c.id,
                    source=zones[donor].id,
                    target=zones[receiver].id,
                    outflow=amount,
                    inflow=received,
                    loss=amount - received,
                    rate=amount / STEP_HOURS,
                    capacity=limit,
                )
            )
        delivered = np.minimum(requested, np.maximum(pool, 0))
        served = np.minimum(critical, delivered)
        pool -= delivered
        overflow = np.maximum(pool - capacity, 0)
        storage = np.clip(pool, 0, capacity)
        residual = float(
            start_storage.sum()
            + gross.sum()
            - storage.sum()
            - delivered.sum()
            - supply_loss.sum()
            - connection_loss.sum()
            - overflow.sum()
        )
        max_residual = max(max_residual, abs(residual))
        if abs(residual) > 1e-8 * max(1, float(start_storage.sum() + gross.sum())):
            raise ArithmeticError("Network water balance violated")
        zone_records = []
        for i, z in enumerate(zones):
            unmet = float(requested[i] - delivered[i])
            delta = float(storage[i] - start_storage[i])
            condition = (
                "Critical"
                if served[i] + 1e-9 < critical[i] or unmet > 1e-6
                else "Stressed"
                if storage[i] < reserve[i]
                else "Recovering"
                if start_storage[i] < reserve[i] and delta > 0
                else "Normal"
            )
            reasons = (
                ["Essential demand shortfall"]
                if served[i] + 1e-9 < critical[i]
                else ["Unmet total demand"]
                if unmet > 1e-6
                else ["Storage below minimum reserve"]
                if storage[i] < reserve[i]
                else ["Reserve rebuilding"]
                if condition == "Recovering"
                else ["Demand served; reserve maintained"]
            )
            timestamp = (
                datetime.fromisoformat(z.source_timestamp.replace("Z", "+00:00"))
                + timedelta(hours=hour + STEP_HOURS)
            ).isoformat()
            zone_records.append(
                dict(
                    id=z.id,
                    timestamp=timestamp,
                    state_version=step + 1,
                    temperature=z.temperature,
                    humidity=z.humidity,
                    environmental_source=z.environmental_source,
                    source_timestamp=z.source_timestamp,
                    data_quality=scenario.observation_mode,
                    storage=float(storage[i]),
                    requested=float(requested[i]),
                    delivered=float(delivered[i]),
                    unmet=unmet,
                    critical_requested=float(critical[i]),
                    critical_served=float(served[i]),
                    external=float(gross[i]),
                    current_supply=float(supply[i]),
                    consumption_rate=float(delivered[i] / STEP_HOURS),
                    supply_loss=float(supply_loss[i]),
                    incoming=float(incoming[i]),
                    outgoing=float(outgoing[i]),
                    connection_loss=float(connection_loss[i]),
                    overflow=float(overflow[i]),
                    storage_change=delta,
                    time_to_reserve=(
                        float((storage[i] - reserve[i]) / (-delta / STEP_HOURS))
                        if delta < 0 and storage[i] > reserve[i]
                        else None
                    ),
                    condition=condition,
                    reasons=reasons,
                )
            )
        records.append(
            dict(
                hour=hour + STEP_HOURS,
                zones=zone_records,
                connections=flows,
                mass_residual=residual,
            )
        )
        for key, value in [
            ("external", gross.sum()),
            ("delivered", delivered.sum()),
            ("requested", requested.sum()),
            ("losses", supply_loss.sum() + connection_loss.sum()),
            ("overflow", overflow.sum()),
            ("critical_requested", critical.sum()),
            ("critical_served", served.sum()),
        ]:
            total[key] += float(value)
    total.update(
        unmet=total["requested"] - total["delivered"],
        ending_storage=float(storage.sum()),
        starting_storage=float(sum(z.storage for z in zones)),
        critical_percent=(
            100 * total["critical_served"] / total["critical_requested"]
            if total["critical_requested"]
            else 100
        ),
        below_reserve=int(sum(storage[i] < z.reserve for i, z in enumerate(zones))),
    )
    return dict(
        model_version=MODEL_VERSION,
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        seed=scenario.seed,
        horizon=horizon,
        step_hours=STEP_HOURS,
        configuration_hash=configuration_hash(scenario, horizon, actions),
        initial_zones=[dict(id=z.id, storage=z.storage) for z in zones],
        time_series=records,
        totals=total,
        verified=True,
        max_mass_residual=max_residual,
        elapsed_ms=(time.perf_counter() - started) * 1000,
    )


def verify_plan(scenario, horizon, actions):
    result = simulate(scenario, horizon, actions)
    violations = []
    for row in result["time_series"]:
        for state in row["zones"]:
            z = next(z for z in scenario.zones if z.id == state["id"])
            if state["critical_served"] + 1e-8 < state["critical_requested"]:
                violations.append(
                    f"{z.id}: essential demand deficit at {row['hour']:g} h"
                )
            if state["delivered"] + 1e-8 < state["requested"] * z.minimum_service:
                violations.append(
                    f"{z.id}: minimum service violated at {row['hour']:g} h"
                )
    return dict(feasible=not violations, violations=violations[:24], result=result)
