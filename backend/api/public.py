from datetime import datetime
from zoneinfo import ZoneInfo
import networkx as nx
from backend.simulation.models import Scenario


def available_stations(scenario: Scenario, accessible=True, now=None):
    now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    eligible = []
    for station in scenario.stations:
        hour = now.astimezone(ZoneInfo(station.timezone)).hour
        hours_ok = (
            station.opens <= hour < station.closes
            if station.opens < station.closes
            else hour >= station.opens or hour < station.closes
        )
        if (
            station.open
            and hours_ok
            and station.water_available
            and station.occupancy < station.capacity
            and (station.accessible or not accessible)
        ):
            eligible.append(station.model_dump(mode="json"))
    return eligible


def route(scenario, zone_id, accessible=True, now=None):
    if zone_id not in set("ABCDEF"):
        raise ValueError("Unknown zone")
    graph = nx.Graph()
    for a, b, minutes in [
        ("A", "B", 8),
        ("B", "C", 9),
        ("A", "D", 7),
        ("B", "E", 6),
        ("C", "F", 8),
        ("D", "E", 8),
        ("E", "F", 7),
        ("A", "E", 11),
    ]:
        graph.add_edge(a, b, minutes=minutes)
    candidates = []
    for station in available_stations(scenario, accessible, now):
        if station["type"] != "cooling":
            continue
        path = nx.shortest_path(graph, zone_id, station["zone_id"], weight="minutes")
        minutes = sum(graph[a][b]["minutes"] for a, b in zip(path, path[1:])) + 2
        candidates.append(
            dict(
                station=station,
                zone_path=path,
                walking_minutes=minutes,
                graph="seeded pedestrian graph",
                synthetic=True,
            )
        )
    candidates.sort(key=lambda c: (c["walking_minutes"], c["station"]["id"]))
    return dict(
        route=candidates[0] if candidates else None,
        alternatives=candidates[1:3],
        guidance="Synthetic environmental guidance: seek shade or a cooler place, take breaks, and keep drinking water available. This demo cannot assess your health or real-world route safety.",
        location_retained=False,
    )


def zone_from_coordinates(scenario, lat, lon):
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Invalid coordinates")
    nearest = min(
        scenario.zones,
        key=lambda z: (z.centroid[0] - lat) ** 2 + (z.centroid[1] - lon) ** 2,
    )
    if abs(nearest.centroid[0] - lat) > 0.015 or abs(nearest.centroid[1] - lon) > 0.017:
        raise ValueError(
            "Location outside the synthetic demo area; choose a zone manually"
        )
    return nearest.id
