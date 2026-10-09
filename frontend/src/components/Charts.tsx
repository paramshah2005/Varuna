import { lazy, Suspense } from "react";
import type { ComponentProps } from "react";
const Plot = lazy(() =>
  import("./ChartPlot").then((m) => ({ default: m.StorageChart })),
);
const Flows = lazy(() =>
  import("./ChartPlot").then((m) => ({ default: m.FlowCharts })),
);
export function FlowCharts(props: ComponentProps<typeof Flows>) {
  return (
    <Suspense
      fallback={<div className="empty-chart">Loading operating charts…</div>}
    >
      <Flows {...props} />
    </Suspense>
  );
}
export function StorageChart(props: ComponentProps<typeof Plot>) {
  return (
    <Suspense fallback={<div className="empty-chart">Loading chart…</div>}>
      <Plot {...props} />
    </Suspense>
  );
}
