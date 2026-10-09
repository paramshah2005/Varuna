from backend.simulation.models import Scenario


def normal():
    names = [
        "Riverside",
        "Civic Quarter",
        "Garden District",
        "East Market",
        "University",
        "Southbank",
    ]
    zones = []
    for i, zid in enumerate("ABCDEF"):
        zones.append(
            dict(
                id=zid,
                name=names[i],
                population=2200 + i * 250,
                demand=[34, 40, 30, 38, 32, 36][i],
                demand_multiplier=1.0,
                supply_capacity=[65, 62, 50, 55, 52, 58][i],
                supply=[48, 45, 38, 43, 40, 46][i],
                storage_capacity=300 + i * 30,
                storage=200 + i * 15,
                reserve=60 + i * 5,
                critical_demand=[12, 22, 8, 14, 12, 10][i],
                priority=[3, 5, 2, 4, 4, 3][i],
                minimum_service=0.5,
                supply_loss=0.03,
                temperature=31,
                humidity=58,
                centroid=[12.97 + (i // 3) * 0.012, 77.58 + (i % 3) * 0.014],
            )
        )
    connections = [
        dict(
            id=f"{a}-{b}",
            source=a,
            target=b,
            capacity=cap,
            loss=0.02,
            repair_hours=1.5,
            repair_cost=1,
        )
        for a, b, cap in [
            ("A", "B", 18),
            ("B", "C", 15),
            ("A", "D", 20),
            ("B", "E", 20),
            ("C", "F", 18),
            ("D", "E", 16),
            ("E", "F", 18),
        ]
    ]
    for zone in zones:
        zone["supply_available"] = zone["supply_capacity"]
    stations = [
        dict(
            id=f"station-{z}",
            name=f"{names[i]} {'Cooling Center' if i % 2 == 0 else 'Water Point'}",
            zone_id=z,
            coordinates=zones[i]["centroid"],
            type="cooling" if i % 2 == 0 else "drinking",
            opens=6,
            closes=22,
            open=True,
            accessible=True,
            capacity=80,
            occupancy=15 + i * 5,
            water_available=True,
            added_demand=2,
            priority=4,
        )
        for i, z in enumerate("ABCDEF")
    ]
    return dict(
        scenario_id="normal",
        scenario_version=1,
        name="Normal demand",
        description="Scheduled supply under typical synthetic neighborhood demand.",
        seed=42,
        zones=zones,
        connections=connections,
        stations=stations,
    )


def fixtures():
    scenarios = []
    for sid, name, description in [
        ("normal", "Normal demand", "Typical demand and scheduled supply."),
        (
            "heatwave",
            "Heatwave demand surge",
            "Explicit 1.45× demand multiplier; temperature is context only.",
        ),
        (
            "loss",
            "Unexplained supply loss",
            "Elevated aggregate loss produces an observable balance residual.",
        ),
        (
            "compound",
            "Heatwave + supply disruption",
            "Heatwave demand, reduced external supply, and increased connection loss.",
        ),
        (
            "missing",
            "Missing / faulty readings",
            "Incomplete observations preserve ambiguity between loss and measurement error.",
        ),
        (
            "infeasible",
            "Critical-service deficit",
            "Insufficient finite storage and inflow to satisfy essential demand.",
        ),
        (
            "recovery",
            "Repair and restoration",
            "Scheduled supply restoration at hour 2 after a simulated repair.",
        ),
        (
            "station-outage",
            "Cooling center unavailable",
            "Station C is closed independently of network water adequacy.",
        ),
    ]:
        data = normal()
        data.update(scenario_id=sid, name=name, description=description)
        if sid in {"heatwave", "compound", "infeasible", "recovery"}:
            for z in data["zones"]:
                z.update(demand_multiplier=1.45, temperature=41, humidity=44)
        if sid in {"loss", "compound", "recovery"}:
            data["connections"][3]["loss"] = 0.38
            data["zones"][4]["supply_loss"] = 0.30
        if sid in {"compound", "recovery"}:
            for i in [1, 4]:
                data["zones"][i]["supply"] = 14 if i == 1 else 10
                data["zones"][i]["storage"] = 65 if i == 1 else 50
        if sid == "missing":
            data["observation_mode"] = "missing"
        if sid == "infeasible":
            for z in data["zones"]:
                z.update(storage=0, supply=0, supply_available=0)
        if sid == "recovery":
            data.update(recovery_at_hour=2, recovered_supply={"B": 45, "E": 40})
        if sid == "station-outage":
            data["stations"][2]["open"] = False
        scenarios.append(Scenario.model_validate(data))
    return scenarios
