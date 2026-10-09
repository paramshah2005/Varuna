from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from datetime import datetime
from zoneinfo import ZoneInfo


def valid_timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include an explicit timezone")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Zone(StrictModel):
    id: str = Field(pattern=r"^[A-F]$")
    name: str
    scale: Literal["neighborhood"] = "neighborhood"
    population: int = Field(gt=0, le=100000)
    demand: float = Field(ge=0, le=1000)
    demand_multiplier: float = Field(ge=0.5, le=3)
    supply_capacity: float = Field(ge=0, le=1000)
    supply_available: float = Field(ge=0, le=1000)
    supply: float = Field(ge=0, le=1000)
    storage_capacity: float = Field(gt=0, le=10000)
    storage: float = Field(ge=0)
    reserve: float = Field(ge=0)
    critical_demand: float = Field(ge=0)
    priority: int = Field(ge=1, le=5)
    minimum_service: float = Field(ge=0, le=1)
    supply_loss: float = Field(ge=0, le=0.8)
    temperature: float = Field(ge=-10, le=55)
    humidity: float = Field(ge=0, le=100)
    centroid: tuple[float, float] = Field(strict=False)
    environmental_source: str = "synthetic demo"
    source_timestamp: str = "2026-10-09T06:00:00Z"

    @field_validator("source_timestamp")
    @classmethod
    def timestamp_valid(cls, value):
        return valid_timestamp(value)

    @model_validator(mode="after")
    def valid_relationships(self):
        if not -90 <= self.centroid[0] <= 90 or not -180 <= self.centroid[1] <= 180:
            raise ValueError("Invalid zone centroid")
        if self.storage > self.storage_capacity or self.reserve > self.storage_capacity:
            raise ValueError(
                "Starting storage and reserve cannot exceed storage capacity"
            )
        if (
            self.supply > self.supply_available
            or self.supply_available > self.supply_capacity
        ):
            raise ValueError(
                "Scheduled supply <= available supply <= throughput capacity is required"
            )
        if self.critical_demand > self.demand * self.demand_multiplier:
            raise ValueError(
                "Critical demand must be included in effective total demand"
            )
        return self


class Connection(StrictModel):
    id: str = Field(pattern=r"^[A-F]-[A-F]$")
    source: str
    target: str
    bidirectional: bool = True
    capacity: float = Field(ge=0, le=1000)
    available: bool = True
    control: Literal["open", "restricted", "closed"] = "open"
    loss: float = Field(ge=0, le=0.8)
    repair_hours: float = Field(gt=0, le=12)
    repair_cost: float = Field(ge=0)


class Station(StrictModel):
    id: str
    name: str
    zone_id: str
    coordinates: tuple[float, float] = Field(strict=False)
    type: Literal["cooling", "drinking"]
    opens: int = Field(ge=0, le=23)
    closes: int = Field(ge=1, le=24)
    timezone: str = "Asia/Kolkata"
    open: bool
    accessible: bool
    capacity: int = Field(gt=0)
    occupancy: int = Field(ge=0)
    water_available: bool
    added_demand: float = Field(ge=0)
    priority: int = Field(ge=1, le=5)
    verified_at: str = "2026-10-09T06:00:00Z"
    synthetic: bool = True

    @field_validator("timezone")
    @classmethod
    def timezone_valid(cls, value):
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as exc:
            raise ValueError("Unknown IANA station timezone") from exc
        return value

    @field_validator("verified_at")
    @classmethod
    def timestamp_valid(cls, value):
        return valid_timestamp(value)

    @model_validator(mode="after")
    def valid_occupancy(self):
        if self.opens == self.closes:
            raise ValueError(
                "Ambiguous opening interval; use 0–24 for all-day operation"
            )
        if (
            not -90 <= self.coordinates[0] <= 90
            or not -180 <= self.coordinates[1] <= 180
        ):
            raise ValueError("Invalid station coordinates")
        if self.occupancy > self.capacity:
            raise ValueError("Occupancy exceeds station capacity")
        return self


class Scenario(StrictModel):
    scenario_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    scenario_version: int = Field(ge=1)
    name: str
    description: str
    synthetic: Literal[True] = True
    seed: int = Field(ge=0)
    zones: list[Zone] = Field(min_length=6, max_length=6)
    connections: list[Connection] = Field(max_length=15)
    stations: list[Station] = Field(max_length=50)
    observation_mode: Literal["complete", "missing", "faulty"] = "complete"
    recovery_at_hour: float | None = Field(default=None, ge=0, le=12)
    recovered_supply: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_ids(self):
        ids = {z.id for z in self.zones}
        if ids != set("ABCDEF"):
            raise ValueError("Scenario must contain unique zones A through F")
        if len({c.id for c in self.connections}) != len(self.connections):
            raise ValueError("Connection IDs must be unique")
        for c in self.connections:
            if c.source not in ids or c.target not in ids or c.source == c.target:
                raise ValueError("Invalid connection endpoints")
        if len({s.id for s in self.stations}) != len(self.stations):
            raise ValueError("Station IDs must be unique")
        for s in self.stations:
            if s.zone_id not in ids:
                raise ValueError("Unknown station zone")
        for zone_id, supply in self.recovered_supply.items():
            z = next((z for z in self.zones if z.id == zone_id), None)
            if z is None or not 0 <= supply <= z.supply_available:
                raise ValueError("Invalid recovered supply")
        return self


class Action(StrictModel):
    type: Literal["connection", "supply", "repair", "water_point"]
    target: str
    value: float = Field(ge=0, le=1000)
    at_hour: float = Field(default=0, ge=0, le=12)


class RunRequest(StrictModel):
    scenario_id: str
    scenario_version: int = Field(ge=1)
    horizon: Literal[3, 6, 12] = 6
    agents_active: bool = True


class Decision(StrictModel):
    decision: Literal["approve", "reject"]
    plan_version: int = Field(ge=1)
    scenario_version: int = Field(ge=1)
