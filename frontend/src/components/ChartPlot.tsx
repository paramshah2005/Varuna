import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Line,
  LineChart,
} from "recharts";
import type { Result, Zone } from "../types";
export function StorageChart({
  baseline,
  comparison,
  zone,
  label,
}: {
  baseline: Result;
  comparison: Result | null;
  zone: Zone;
  label: string;
}) {
  const points = [
    {
      hour: 0,
      baseline:
        baseline.initial_zones?.find((z) => z.id === zone.id)?.storage ??
        zone.storage,
      comparison:
        comparison?.initial_zones?.find((z) => z.id === zone.id)?.storage ??
        zone.storage,
    },
    ...baseline.time_series.map((r, i) => ({
      hour: r.hour,
      baseline: r.zones.find((z) => z.id === zone.id)?.storage,
      comparison: comparison?.time_series[i]?.zones.find(
        (z) => z.id === zone.id,
      )?.storage,
    })),
  ];
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={points}
          margin={{ left: 0, right: 20, top: 12, bottom: 0 }}
        >
          <defs>
            <linearGradient id="waterFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2867df" stopOpacity={0.18} />
              <stop offset="100%" stopColor="#2867df" stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="4 4"
            vertical={false}
            stroke="var(--border)"
          />
          <XAxis
            dataKey="hour"
            tickLine={false}
            axisLine={false}
            unit=" h"
            tick={{ fontSize: 11, fill: "var(--muted)" }}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            width={45}
            tick={{ fontSize: 11, fill: "var(--muted)" }}
          />
          <Tooltip
            formatter={(v) => `${Number(v).toFixed(1)} m³`}
            contentStyle={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 12,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Area
            dataKey="baseline"
            name="Applied baseline"
            type="monotone"
            stroke="#2867df"
            fill="url(#waterFill)"
            strokeWidth={2}
            isAnimationActive={false}
          />
          {comparison && (
            <Area
              dataKey="comparison"
              name={label}
              type="monotone"
              stroke="#20a48b"
              fill="transparent"
              strokeWidth={2}
              isAnimationActive={false}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function FlowCharts({
  baseline,
  comparison,
  zoneId,
  label,
}: {
  baseline: Result;
  comparison: Result | null;
  zoneId: string;
  label: string;
}) {
  const compared = new Map(
    comparison?.time_series.map((row) => [
      row.hour,
      row.zones.find((z) => z.id === zoneId),
    ]),
  );
  const points = baseline.time_series.map((row) => {
    const before = row.zones.find((z) => z.id === zoneId)!;
    const after = compared.get(row.hour);
    return {
      hour: row.hour,
      requested: before.requested / baseline.step_hours,
      delivered: before.delivered / baseline.step_hours,
      supply: before.external / baseline.step_hours,
      shortage: before.unmet / baseline.step_hours,
      comparedRequested: after && after.requested / comparison!.step_hours,
      comparedDelivered: after && after.delivered / comparison!.step_hours,
      comparedSupply: after && after.external / comparison!.step_hours,
      comparedShortage: after && after.unmet / comparison!.step_hours,
    };
  });
  const last = points.at(-1)!;
  const charts = [
    {
      id: "demand",
      title: "Demand & delivery",
      description: "Requested and delivered demand · m³/h",
      keys: ["requested", "delivered"],
      comparedKeys: ["comparedRequested", "comparedDelivered"],
      names: ["Requested", "Delivered"],
      values: `${last.requested.toFixed(1)} requested, ${last.delivered.toFixed(1)} delivered`,
    },
    {
      id: "supply",
      title: "External supply",
      description: "Gross inflow before supply losses · m³/h",
      keys: ["supply"],
      comparedKeys: ["comparedSupply"],
      names: ["Gross external supply"],
      values: last.supply.toFixed(1),
    },
    {
      id: "shortage",
      title: "Unmet demand",
      description: "Requested demand minus delivered demand · m³/h",
      keys: ["shortage"],
      comparedKeys: ["comparedShortage"],
      names: ["Unmet demand"],
      values: last.shortage.toFixed(1),
    },
  ];
  return (
    <div
      className="flow-charts"
      aria-label={`Water operating charts for zone ${zoneId}`}
    >
      {charts.map((chart) => (
        <section
          className="card chart-card"
          key={chart.id}
          data-testid={`${chart.id}-chart`}
        >
          <div className="panel-heading">
            <div>
              <h3>
                {chart.title} · Zone {zoneId}
              </h3>
              <p className="small muted">{chart.description}</p>
            </div>
          </div>
          <div
            className="chart"
            role="img"
            aria-label={`${chart.title} over the ${baseline.horizon}-hour horizon, baseline${comparison ? ` compared with ${label}` : ""}`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={points}
                margin={{ left: 0, right: 12, top: 12, bottom: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="4 4"
                  vertical={false}
                  stroke="var(--border)"
                />
                <XAxis
                  dataKey="hour"
                  tickLine={false}
                  axisLine={false}
                  unit=" h"
                  tick={{ fontSize: 10, fill: "var(--muted)" }}
                />
                <YAxis
                  width={42}
                  tickLine={false}
                  axisLine={false}
                  domain={[0, "auto"]}
                  tick={{ fontSize: 10, fill: "var(--muted)" }}
                />
                <Tooltip
                  formatter={(value) => `${Number(value).toFixed(2)} m³/h`}
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                {chart.keys.map((key, index) => (
                  <Line
                    key={key}
                    dataKey={key}
                    name={`Baseline · ${chart.names[index]}`}
                    stroke={index ? "#7a84a3" : "#2867df"}
                    strokeWidth={2}
                    strokeDasharray={index ? "4 3" : undefined}
                    dot={false}
                    type="linear"
                    isAnimationActive={false}
                  />
                ))}
                {comparison &&
                  chart.comparedKeys.map((key, index) => (
                    <Line
                      key={key}
                      dataKey={key}
                      name={`${label} · ${chart.names[index]}`}
                      stroke={index ? "#82b2a6" : "#20a48b"}
                      strokeWidth={2}
                      strokeDasharray={index ? "4 3" : undefined}
                      dot={false}
                      type="linear"
                      isAnimationActive={false}
                    />
                  ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="small muted">
            At {last.hour} h · Baseline: {chart.values} m³/h
            {comparison
              ? ` · ${label}: ${chart.comparedKeys.map((key) => Number(last[key as keyof typeof last]).toFixed(1)).join(" / ")} m³/h`
              : ""}
          </p>
          <details>
            <summary>View measured values</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Hour</th>
                    {chart.names.map((name) => (
                      <th key={name}>Baseline {name} m³/h</th>
                    ))}
                    {comparison &&
                      chart.names.map((name) => (
                        <th key={name}>
                          {label} {name} m³/h
                        </th>
                      ))}
                  </tr>
                </thead>
                <tbody>
                  {points.map((point) => (
                    <tr key={point.hour}>
                      <td>{point.hour}</td>
                      {[
                        ...chart.keys,
                        ...(comparison ? chart.comparedKeys : []),
                      ].map((key) => (
                        <td key={key}>
                          {point[key as keyof typeof point] == null
                            ? "—"
                            : Number(point[key as keyof typeof point]).toFixed(
                                2,
                              )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </section>
      ))}
    </div>
  );
}
