import json
from pathlib import Path
import statistics
from backend.simulation.models import Scenario
from backend.simulation.fixtures import fixtures
from backend.simulation.engine import simulate

root = Path(__file__).resolve().parents[1]
data = root / "data"
data.mkdir(exist_ok=True)
(data / "scenario.schema.json").write_text(
    json.dumps(Scenario.model_json_schema(), indent=2)
)
measurements = []
for scenario in fixtures():
    (data / f"{scenario.scenario_id}.json").write_text(
        scenario.model_dump_json(indent=2)
    )
    for horizon in [3, 6, 12]:
        runs = [simulate(scenario, horizon) for _ in range(10)]
        measurements.append(
            dict(
                scenario_id=scenario.scenario_id,
                horizon=horizon,
                samples=10,
                median_ms=statistics.median(r["elapsed_ms"] for r in runs),
                max_ms=max(r["elapsed_ms"] for r in runs),
                max_mass_residual=max(r["max_mass_residual"] for r in runs),
                totals=runs[-1]["totals"],
            )
        )
(root / "docs" / "simulation-benchmarks.json").write_text(
    json.dumps(measurements, indent=2)
)
print(
    f"Generated {len(fixtures())} validated fixtures and {len(measurements)} measured benchmarks"
)
