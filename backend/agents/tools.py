from copy import deepcopy
from pydantic import Field
import networkx as nx
from backend.simulation.models import Action, Scenario, StrictModel
from backend.simulation.engine import configuration_hash, simulate, verify_plan
from backend.api.public import available_stations


class ToolArguments(StrictModel):
    zone_id: str | None = Field(default=None, pattern=r"^[A-F]$")
    connection_id: str | None = Field(default=None, pattern=r"^[A-F]-[A-F]$")
    hypothesis: str = Field(
        default="supply_loss",
        pattern=r"^(supply_loss|connection_loss|demand_surge|faulty_reading)$",
    )
    magnitude: float = Field(default=0.2, ge=0, le=0.8)
    actions: list[Action] = Field(default_factory=list, max_length=20)


def observations(scenario, result):
    history = []
    by_id = {z.id: z for z in scenario.zones}
    for row in result["time_series"]:
        for state in row["zones"]:
            z = by_id[state["id"]]
            nominal_loss = state["external"] * 0.03
            residual = state["supply_loss"] - nominal_loss + state["connection_loss"]
            valid = not (scenario.observation_mode == "missing" and z.id in {"B", "E"})
            measured = residual + (
                3 if scenario.observation_mode == "faulty" and z.id == "E" else 0
            )
            history.append(
                dict(
                    zone_id=z.id,
                    hour=row["hour"],
                    residual=round(measured, 6) if valid else None,
                    delivered=state["delivered"] if valid else None,
                    quality="complete" if valid else "missing",
                    demand_multiplier=z.demand_multiplier,
                    external_gross_m3=state["external"] if valid else None,
                    nominal_supply_loss_fraction=0.03,
                    step_hours=0.25,
                )
            )
    return history


def agent_view(scenario):
    data = scenario.model_dump(mode="json")
    data["name"] = "Observed scenario"
    data["scenario_id"] = "observed"
    data["description"] = (
        "Ground truth excluded; investigate only available observations."
    )
    for z in data["zones"]:
        z["supply_loss"] = 0.03
    for c in data["connections"]:
        c["loss"] = 0.02
    return Scenario.model_validate(data)


class ToolRegistry:
    def __init__(self, scenario, horizon, history, evidence=None):
        self.scenario = scenario
        self.horizon = horizon
        self.history = history
        self.evidence = evidence if evidence is not None else []
        self.cache = {}
        self.names = [
            "get_zone_state",
            "get_observation_history",
            "compare_baseline",
            "simulate_candidate_fault",
            "forecast_storage",
            "evaluate_isolation_options",
            "propose_zone_allocation",
            "simulate_supply_schedule",
            "evaluate_recovery_sequence",
            "validate_plan",
            "evaluate_water_point_site",
            "get_available_stations",
            "save_incident_report",
        ]

    def call(self, name, arguments):
        if name not in self.names:
            raise ValueError("Unknown tool")
        args = ToolArguments.model_validate(arguments)
        zone = next((z for z in self.scenario.zones if z.id == args.zone_id), None)
        edge = next(
            (c for c in self.scenario.connections if c.id == args.connection_id), None
        )
        if args.connection_id and edge is None:
            raise ValueError("Unknown connection")
        if (
            name
            in {
                "get_zone_state",
                "simulate_candidate_fault",
                "evaluate_water_point_site",
            }
            and zone is None
        ):
            raise ValueError("Tool requires a valid zone")
        key = (
            configuration_hash(self.scenario, self.horizon, args.actions)
            + name
            + args.model_dump_json()
        )
        cached = key in self.cache
        if cached:
            output = deepcopy(self.cache[key])
        elif name == "get_zone_state":
            output = zone.model_dump(mode="json")
        elif name == "get_observation_history":
            output = [
                o
                for o in self.history
                if args.zone_id is None or o["zone_id"] == args.zone_id
            ]
        elif name in {"compare_baseline", "forecast_storage"}:
            base = simulate(self.scenario, self.horizon)
            output = dict(
                totals=base["totals"],
                final_zones=base["time_series"][-1]["zones"],
                range_label="Scenario range, not a calibrated prediction interval",
            )
            if name == "forecast_storage":
                bounds = []
                for multiplier in [0.9, 1.1]:
                    data = self.scenario.model_dump(mode="json")
                    for z in data["zones"]:
                        z["demand_multiplier"] = max(
                            0.5,
                            z["critical_demand"] / z["demand"] if z["demand"] else 0.5,
                            min(3, z["demand_multiplier"] * multiplier),
                        )
                    bounds.append(
                        simulate(Scenario.model_validate(data), self.horizon)["totals"][
                            "ending_storage"
                        ]
                    )
                output["storage_range"] = sorted(bounds)
        elif name == "simulate_candidate_fault":
            data = self.scenario.model_dump(mode="json")
            if args.hypothesis == "supply_loss":
                next(z for z in data["zones"] if z["id"] == args.zone_id)[
                    "supply_loss"
                ] = args.magnitude
            elif args.hypothesis == "connection_loss":
                if edge is None:
                    raise ValueError("Connection loss hypothesis requires a connection")
                next(c for c in data["connections"] if c["id"] == edge.id)["loss"] = (
                    args.magnitude
                )
            elif args.hypothesis == "demand_surge":
                next(z for z in data["zones"] if z["id"] == args.zone_id)[
                    "demand_multiplier"
                ] = min(3, zone.demand_multiplier * (1 + args.magnitude))
            trial = Scenario.model_validate(data)
            result = simulate(trial, self.horizon)
            predicted = observations(trial, result)
            if args.hypothesis == "demand_surge":
                nominal = simulate(self.scenario, self.horizon)
                nominal_delivery = [
                    s["delivered"] for r in nominal["time_series"] for s in r["zones"]
                ]
                for i, reading in enumerate(predicted):
                    if reading["residual"] is not None:
                        reading["residual"] += (
                            reading["delivered"] - nominal_delivery[i]
                        )
            pairs = [
                (a, b)
                for a, b in zip(self.history, predicted)
                if a["zone_id"] == args.zone_id and a["residual"] is not None
            ]
            errors = [
                (
                    a["residual"]
                    - (
                        b["residual"]
                        + (
                            args.magnitude * 10
                            if args.hypothesis == "faulty_reading"
                            else 0
                        )
                    )
                )
                ** 2
                for a, b in pairs
            ]
            output = dict(
                hypothesis=args.hypothesis,
                magnitude=args.magnitude,
                zone_id=args.zone_id,
                connection_id=args.connection_id,
                fit_mse=sum(errors) / len(errors) if errors else None,
                compared_samples=len(errors),
                label="Fit error, not probability",
                totals=result["totals"],
            )
        elif name == "evaluate_isolation_options":
            output = []
            options = [
                [Action(type="connection", target=c.id, value=0)]
                for c in self.scenario.connections
            ]
            options.extend(
                [
                    Action(type="connection", target=c.id, value=0)
                    for c in self.scenario.connections
                    if z.id in {c.source, c.target}
                ]
                for z in self.scenario.zones
            )
            for actions in options:
                check = verify_plan(self.scenario, self.horizon, actions)
                output.append(
                    dict(
                        actions=[a.model_dump() for a in actions],
                        feasible=check["feasible"],
                        violations=check["violations"],
                        totals=check["result"]["totals"],
                    )
                )
        elif name in {
            "validate_plan",
            "simulate_supply_schedule",
            "evaluate_recovery_sequence",
            "propose_zone_allocation",
        }:
            check = verify_plan(self.scenario, self.horizon, args.actions)
            graph = nx.DiGraph()
            graph.add_nodes_from(z.id for z in self.scenario.zones)
            final_flows = {
                f["connection_id"]: f
                for f in check["result"]["time_series"][-1]["connections"]
            }
            for c in self.scenario.connections:
                if final_flows[c.id]["capacity"] > 0:
                    graph.add_edge(c.source, c.target)
                    if c.bidirectional:
                        graph.add_edge(c.target, c.source)
            output = dict(
                feasible=check["feasible"],
                violations=check["violations"],
                totals=check["result"]["totals"],
                isolated_zones=list(nx.isolates(graph)),
                connected_components=[
                    sorted(c) for c in nx.weakly_connected_components(graph)
                ],
                reachability={
                    z.id: sorted(nx.descendants(graph, z.id))
                    for z in self.scenario.zones
                },
            )
        elif name == "evaluate_water_point_site":
            action = Action(type="water_point", target=zone.id, value=2)
            check = verify_plan(self.scenario, self.horizon, [*args.actions, action])
            pedestrian_access = zone.id not in {"C", "F"}
            output = dict(
                proposal=True,
                zone_id=zone.id,
                footfall=zone.population * 0.12,
                pedestrian_access=pedestrian_access,
                occupancy_capacity=60,
                source="Seeded candidate site assumptions; no existing facility claimed",
                added_demand=2,
                feasible=check["feasible"] and pedestrian_access,
                totals=check["result"]["totals"],
            )
        elif name == "get_available_stations":
            output = available_stations(self.scenario)
        else:
            output = dict(
                evidence_count=len(self.evidence), report_saved_by_workflow=True
            )
        self.cache[key] = deepcopy(output)
        self.evidence.append(
            dict(
                tool=name,
                arguments=args.model_dump(mode="json"),
                result=output,
                cached=cached,
            )
        )
        return output
