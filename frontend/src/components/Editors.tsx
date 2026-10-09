import type { Connection, Scenario, Zone } from "../types";
import { Button, Modal, Toggle } from "./ui";
import { RotateCcw, Save, ScanLine } from "lucide-react";
type Field = {
  key: keyof Zone;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
};
const fields: Field[] = [
  {
    key: "demand",
    label: "Baseline demand",
    unit: "m³/h",
    min: 0,
    max: 1000,
    step: 1,
  },
  {
    key: "demand_multiplier",
    label: "Explicit demand multiplier",
    unit: "×",
    min: 0.5,
    max: 3,
    step: 0.05,
  },
  {
    key: "supply",
    label: "Scheduled external supply",
    unit: "m³/h",
    min: 0,
    max: 1000,
    step: 1,
  },
  {
    key: "supply_available",
    label: "Available upstream supply",
    unit: "m³/h",
    min: 0,
    max: 1000,
    step: 1,
  },
  {
    key: "supply_capacity",
    label: "Throughput capacity",
    unit: "m³/h",
    min: 0,
    max: 1000,
    step: 1,
  },
  {
    key: "storage",
    label: "Starting storage",
    unit: "m³",
    min: 0,
    max: 10000,
    step: 5,
  },
  {
    key: "storage_capacity",
    label: "Storage capacity",
    unit: "m³",
    min: 1,
    max: 10000,
    step: 5,
  },
  {
    key: "reserve",
    label: "Minimum reserve",
    unit: "m³",
    min: 0,
    max: 10000,
    step: 5,
  },
  {
    key: "supply_loss",
    label: "Supply loss / gross external inflow",
    unit: "fraction",
    min: 0,
    max: 0.8,
    step: 0.01,
  },
  {
    key: "temperature",
    label: "Demo ambient temperature",
    unit: "°C",
    min: -10,
    max: 55,
    step: 0.5,
  },
  {
    key: "humidity",
    label: "Relative humidity",
    unit: "%",
    min: 0,
    max: 100,
    step: 1,
  },
  {
    key: "critical_demand",
    label: "Critical demand within total demand",
    unit: "m³/h",
    min: 0,
    max: 1000,
    step: 1,
  },
  {
    key: "priority",
    label: "Allocation priority",
    unit: "1–5",
    min: 1,
    max: 5,
    step: 1,
  },
  {
    key: "minimum_service",
    label: "Minimum service target",
    unit: "fraction",
    min: 0,
    max: 1,
    step: 0.05,
  },
];
export function ZoneEditor({
  zone,
  scenario,
  onChange,
  onStation,
  onPreview,
  onApply,
  onReset,
  busy,
}: {
  zone: Zone;
  scenario: Scenario;
  onChange: (z: Zone) => void;
  onStation: (id: string, open: boolean) => void;
  onPreview: () => void;
  onApply: () => void;
  onReset: () => void;
  busy: boolean;
}) {
  return (
    <section className="editor card">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">INITIAL CONDITIONS</span>
          <h3>
            Zone {zone.id} · {zone.name}
          </h3>
        </div>
        <span className="badge blue">Draft</span>
      </div>
      <p className="muted small">
        Edits restart from initial conditions. Capacity changes add no water.
      </p>
      <div className="field-grid">
        {fields.map((f) => (
          <label className="field" key={f.key}>
            <span>
              {f.label}
              <small>{f.unit}</small>
            </span>
            <input
              aria-label={f.label}
              type="number"
              min={f.min}
              max={f.max}
              step={f.step}
              value={zone[f.key] as number}
              onChange={(e) =>
                onChange({
                  ...zone,
                  [f.key]: e.target.value === "" ? 0 : Number(e.target.value),
                })
              }
            />
            {["demand_multiplier", "supply_loss", "temperature"].includes(
              f.key,
            ) && (
              <input
                aria-label={`${f.label} slider`}
                type="range"
                min={f.min}
                max={f.max}
                step={f.step}
                value={zone[f.key] as number}
                onChange={(e) =>
                  onChange({ ...zone, [f.key]: Number(e.target.value) })
                }
              />
            )}
          </label>
        ))}
      </div>
      {scenario.stations
        .filter((s) => s.zone_id === zone.id)
        .map((s) => (
          <div className="station-toggle" key={s.id}>
            <span>
              {s.name}
              <small>
                Reported open status; other eligibility checks still apply
              </small>
            </span>
            <Toggle
              label={`Station ${s.id} reported open`}
              checked={s.open}
              onCheckedChange={(open) => onStation(s.id, open)}
            />
          </div>
        ))}
      <div className="button-row">
        <Button variant="outline" onClick={onPreview} disabled={busy}>
          <ScanLine size={15} />
          Preview effects
        </Button>
        <Button onClick={onApply} disabled={busy}>
          <Save size={15} />
          Apply changes
        </Button>
        <Button variant="ghost" onClick={onReset} disabled={busy}>
          <RotateCcw size={15} />
          Reset draft
        </Button>
      </div>
    </section>
  );
}
export function ConnectionEditor({
  connection,
  onChange,
  onClose,
}: {
  connection: Connection | null;
  onChange: (c: Connection) => void;
  onClose: () => void;
}) {
  return (
    <Modal
      open={Boolean(connection)}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={`Connection ${connection?.id}`}
      description="Edit high-level transfer controls in the isolated scenario draft."
    >
      {connection && (
        <div className="connection-form">
          <label className="field">
            <span>
              Transfer capacity <small>m³/h</small>
            </span>
            <input
              aria-label="Transfer capacity"
              type="number"
              min="0"
              max="1000"
              value={connection.capacity}
              onChange={(e) =>
                onChange({ ...connection, capacity: Number(e.target.value) })
              }
            />
          </label>
          <label className="field">
            <span>
              Connection loss / donor outflow <small>fraction</small>
            </span>
            <input
              aria-label="Connection loss"
              type="number"
              min="0"
              max="0.8"
              step="0.01"
              value={connection.loss}
              onChange={(e) =>
                onChange({ ...connection, loss: Number(e.target.value) })
              }
            />
          </label>
          <label className="field">
            <span>Control state</span>
            <select
              value={connection.control}
              onChange={(e) =>
                onChange({
                  ...connection,
                  control: e.target.value as Connection["control"],
                })
              }
            >
              <option value="open">Open</option>
              <option value="restricted">Restricted to 50% capacity</option>
              <option value="closed">Closed</option>
            </select>
          </label>
          <div className="station-toggle">
            <span>Available for transfer</span>
            <Toggle
              label="Connection available"
              checked={connection.available}
              onCheckedChange={(available) =>
                onChange({ ...connection, available })
              }
            />
          </div>
          <p className="small muted">
            One signed flow per connection. Opposite-direction transfers cannot
            bypass capacity.
          </p>
          <Button onClick={onClose}>Done · keep in draft</Button>
        </div>
      )}
    </Modal>
  );
}
