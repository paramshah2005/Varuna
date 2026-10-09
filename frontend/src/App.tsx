import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Bell,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  Droplets,
  FileJson,
  FlaskConical,
  Globe2,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Network,
  Play,
  Search,
  Settings2,
  ShieldCheck,
  Sun,
  Thermometer,
  Upload,
  Waves,
  X,
} from "lucide-react";
import type { Connection, Plan, Results, Run, Scenario, Zone } from "./types";
import { api, downloadJson, number } from "./lib/api";
import {
  ensureAccessToken,
  cloudMode,
  finishLogin,
  login,
  logout,
} from "./lib/auth";
import { useRun } from "./lib/useRun";
import { Accent } from "./components/Accent";
import { Button, Modal, Toggle } from "./components/ui";
import { ZoneGraph } from "./components/ZoneGraph";
import { ZoneEditor, ConnectionEditor } from "./components/Editors";
import { StorageChart, FlowCharts } from "./components/Charts";
import { PublicPage } from "./components/PublicPage";
const clone = <T,>(v: T): T => structuredClone(v);
const statuses: Record<string, string> = {
  queued: "Queued",
  simulating: "Simulating",
  baseline_complete: "Baseline complete",
  investigating: "Investigating",
  plan_ready: "Verifying plan",
  awaiting_approval: "Awaiting your approval",
  infeasible: "Escalation required",
  applying: "Applying approved plan",
  verified: "Outcome verified",
  completed: "Completed",
  failed: "Run failed",
  rejected: "Plan rejected",
  job_retrying: "Job retrying",
};
const nav = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "zones", label: "Zone conditions", icon: Network },
  { id: "lab", label: "Scenario lab", icon: FlaskConical },
  { id: "alerts", label: "Readiness alerts", icon: Bell },
  { id: "activity", label: "Activity log", icon: Activity },
];
function App() {
  const [ready, setReady] = useState(false),
    [authenticated, setAuthenticated] = useState(!cloudMode),
    [scenarios, setScenarios] = useState<Scenario[]>([]),
    [seeds, setSeeds] = useState<Scenario[]>([]),
    [selectedId, setSelectedId] = useState("compound"),
    [draft, setDraft] = useState<Scenario | null>(null),
    [zoneId, setZoneId] = useState("E"),
    [horizon, setHorizon] = useState(6),
    [agents, setAgents] = useState(true),
    [runId, setRunId] = useState<string | null>(null),
    [preview, setPreview] = useState<{
      draft: import("./types").Result;
      applied: import("./types").Result;
    } | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [navId, setNavId] = useState("dashboard"),
    [search, setSearch] = useState(""),
    [dark, setDark] = useState(localStorage.getItem("aqua_theme") === "dark"),
    [mobile, setMobile] = useState(false),
    [connectionId, setConnectionId] = useState<string | null>(null),
    [historyOpen, setHistoryOpen] = useState(false),
    [savedRuns, setSavedRuns] = useState<Run[]>([]);
  const workspace = useRef<HTMLElement>(null),
    upload = useRef<HTMLInputElement>(null),
    draftRevision = useRef(0),
    decisionKey = useRef(crypto.randomUUID());
  const { run, results, events, error: runError, transport } = useRun(runId);
  const applied = scenarios.find((s) => s.scenario_id === selectedId) || null;
  const zone = draft?.zones.find((z) => z.id === zoneId);
  const shownResult = results.approved || results.baseline;
  const currentRun =
    run &&
    applied &&
    run.scenario_id === applied.scenario_id &&
    run.scenario_version === applied.scenario_version;
  const final = currentRun ? shownResult?.time_series.at(-1) : undefined;
  const selectedState = (
    preview?.draft.time_series.at(-1) || final
  )?.zones.find((z) => z.id === zoneId);
  const displayTotals = currentRun ? shownResult?.totals : undefined;
  const forecastEvidence = results.agent?.evidence.find(
    (e) =>
      e &&
      typeof e === "object" &&
      "tool" in e &&
      e.tool === "forecast_storage",
  ) as { result: { storage_range: number[] } } | undefined;
  const reduced = () =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("aqua_theme", dark ? "dark" : "light");
  }, [dark]);
  useEffect(() => {
    let live = true;
    async function load() {
      try {
        await finishLogin();
        const signed = !cloudMode || Boolean(await ensureAccessToken());
        if (live) setAuthenticated(signed);
        if (signed) {
          const data = await api<{
            scenarios: Scenario[];
            baseline_scenarios?: Scenario[];
          }>("/bootstrap");
          if (live) {
            setScenarios(data.scenarios);
            setSeeds(data.baseline_scenarios || clone(data.scenarios));
            setReady(true);
          }
        } else if (live) setReady(true);
      } catch (e) {
        if (live) {
          setError((e as Error).message);
          setReady(true);
        }
      }
    }
    load();
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (applied) {
      setDraft(clone(applied));
      setPreview(null);
      draftRevision.current++;
    }
  }, [applied]);
  useEffect(() => {
    if (runId && workspace.current) {
      if (!reduced())
        gsap.fromTo(
          workspace.current,
          { opacity: 0, y: 24 },
          { opacity: 1, y: 0, duration: 0.5, ease: "power2.out" },
        );
      workspace.current.scrollIntoView({
        behavior: reduced() ? "instant" : "smooth",
        block: "start",
      });
    }
  }, [runId]);
  useEffect(() => {
    if (!reduced() && document.querySelector(".metric-body strong"))
      gsap.fromTo(
        ".metric-body strong",
        { opacity: 0.4, y: 4 },
        { opacity: 1, y: 0, duration: 0.35 },
      );
  }, [ready, displayTotals?.critical_percent, displayTotals?.below_reserve]);
  function changeDraft(next: Scenario) {
    draftRevision.current++;
    setDraft(next);
    setPreview(null);
    setNotice(
      "Draft changed. Preview it or apply a new version before running.",
    );
  }
  function selectZone(id: string) {
    setZoneId(id);
    if (!reduced() && document.querySelector(".editor"))
      gsap.fromTo(
        ".editor",
        { opacity: 0.6, x: 8 },
        { opacity: 1, x: 0, duration: 0.25 },
      );
  }
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function start() {
    if (!applied) return;
    await action(async () => {
      const response = await api<{ run_id: string }>(
        "/runs",
        {
          scenario_id: applied.scenario_id,
          scenario_version: applied.scenario_version,
          horizon,
          agents_active: agents,
        },
        crypto.randomUUID(),
      );
      decisionKey.current = crypto.randomUUID();
      setPreview(null);
      setRunId(response.run_id);
      setNavId("lab");
      setNotice(
        `Run started from applied scenario v${applied.scenario_version}. Unapplied draft edits are not included. Review the response plan when it is ready.`,
      );
    });
  }
  async function previewDraft() {
    if (!draft) return;
    const revision = draftRevision.current;
    await action(async () => {
      const result = await api<{
        draft: import("./types").Result;
        applied: import("./types").Result;
      }>("/scenario-previews", { scenario: draft, horizon });
      if (revision === draftRevision.current) {
        setPreview(result);
        setNotice("Isolated draft preview. The applied scenario is unchanged.");
      }
    });
  }
  async function applyDraft() {
    if (!draft) return;
    await action(async () => {
      const next = await api<Scenario>(
        `/scenarios/${draft.scenario_id}/versions`,
        draft,
      );
      setScenarios((prev) =>
        prev.map((s) => (s.scenario_id === next.scenario_id ? next : s)),
      );
      setNotice(
        `Applied version ${next.scenario_version}. Previous approval is invalidated; run again from edited initial conditions.`,
      );
      setPreview(null);
    });
  }
  function resetDraft() {
    const seed = seeds.find((s) => s.scenario_id === selectedId);
    if (seed && applied) {
      changeDraft({
        ...clone(seed),
        scenario_version: applied.scenario_version,
      });
      setNotice(
        "Scenario baseline restored in the draft. Apply to create a new version.",
      );
    }
  }
  async function decision(choice: "approve" | "reject") {
    if (!run || !results.plan) return;
    await action(async () => {
      await api(
        `/runs/${run.run_id}/plans/${results.plan!.plan_version}/decision`,
        {
          decision: choice,
          plan_version: results.plan!.plan_version,
          scenario_version: run.scenario_version,
        },
        decisionKey.current,
      );
      setNotice(
        choice === "approve"
          ? "Approval recorded against this exact plan. The backend is simulating the actions."
          : "Plan rejected. Start a new run after editing the scenario.",
      );
    });
  }
  async function report() {
    if (!run) return;
    await action(async () => {
      const body = await api<{ report?: unknown; download_url?: string }>(
        `/runs/${run.run_id}/report`,
      );
      if (body.download_url)
        window.open(body.download_url, "_blank", "noopener,noreferrer");
      else downloadJson(body.report, `aquaagent-${run.run_id}.json`);
    });
  }
  async function importFile(file: File) {
    await action(async () => {
      const parsed = JSON.parse(await file.text()) as Scenario;
      const next = await api<Scenario>("/scenarios", parsed);
      setScenarios((prev) => [
        ...prev.filter((s) => s.scenario_id !== next.scenario_id),
        next,
      ]);
      setSelectedId(next.scenario_id);
      setNotice(
        "Scenario imported and validated by the backend. Initial conditions saved as a new version.",
      );
    });
  }
  async function openHistory() {
    await action(async () => {
      const data = await api<{ runs: Run[] }>("/runs");
      setSavedRuns(data.runs.reverse());
      setHistoryOpen(true);
    });
  }
  function navigate(id: string) {
    setNavId(id);
    setMobile(false);
    document
      .getElementById(id === "lab" ? "scenario-setup" : id)
      ?.scrollIntoView({
        behavior: reduced() ? "instant" : "smooth",
        block: "start",
      });
  }
  const dirty =
    draft && applied && JSON.stringify(draft) !== JSON.stringify(applied);
  if (window.location.pathname === "/public") return <PublicPage />;
  if (!ready)
    return (
      <main className="loading">
        <Droplets size={32} />
        <h2>Opening the resilience workspace…</h2>
        <p>Reading applied scenarios from the backend.</p>
      </main>
    );
  if (!authenticated)
    return (
      <main className="login-page">
        <span className="brand-icon">
          <Droplets />
        </span>
        <h1>AquaAgent</h1>
        <p>Operator access to the water resilience workspace.</p>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <Button onClick={() => action(login)}>
          Sign in with Cognito
          <ArrowRight size={17} />
        </Button>
        <a href="/public">Explore the public cooling-station demo</a>
      </main>
    );
  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
        <a href="/" className="brand">
          <span className="brand-icon">
            <Droplets size={25} />
          </span>
          <span>
            AquaAgent<small>WATER RESILIENCE</small>
          </span>
        </a>
        <div className="workspace-label">
          <span className="workspace-dot" />
          Neighborhood workspace
          <ChevronDown size={14} />
        </div>
        <span className="nav-label">OPERATIONS</span>
        <nav aria-label="Main navigation">
          {nav.map((n) => (
            <button
              key={n.id}
              className={navId === n.id ? "active" : ""}
              onClick={() => navigate(n.id)}
            >
              <n.icon size={19} />
              {n.label}
              {n.id === "alerts" && (
                <span className="nav-count">
                  {displayTotals?.below_reserve ?? "—"}
                </span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="public-link-card">
            <Globe2 size={22} />
            <h4>Support your neighborhood</h4>
            <p>Help people find a cooler place and drinking water.</p>
            <a href="/public">
              Open public interface
              <ArrowRight size={15} />
            </a>
          </div>
          <button
            onClick={() =>
              setNotice(
                "Model: aggregate synthetic neighborhoods, 15-minute steps, scenario forecasts. No hydraulics, pipe-level localization or personal diagnosis.",
              )
            }
            className="help-link"
          >
            <CircleHelp size={18} />
            Model & data notes
          </button>
          <div className="operator">
            <span className="avatar">Y</span>
            <div>
              Yoovan
              <small>
                {cloudMode ? "Cognito operator" : "Local development operator"}
              </small>
            </div>
            {cloudMode && (
              <button aria-label="Sign out" onClick={logout}>
                <LogOut size={17} />
              </button>
            )}
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="mobile-menu"
            aria-label="Open navigation"
            onClick={() => setMobile(!mobile)}
          >
            {mobile ? <X size={22} /> : <Menu size={22} />}
          </button>
          <label className="search">
            <Search size={17} />
            <input
              aria-label="Search zones"
              placeholder="Search neighborhoods, zones…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <kbd>/</kbd>
          </label>
          <div className="header-actions">
            <span className="demo-label">
              <i />
              SYNTHETIC DATA
            </span>
            <button
              aria-label={
                dark ? "Switch to light theme" : "Switch to dark theme"
              }
              onClick={() => setDark(!dark)}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <span className="avatar small-avatar">Y</span>
          </div>
        </header>
        <main className="main-content">
          <section id="dashboard" className="page-heading">
            <div>
              <div className="breadcrumb">
                Workspace <span>/</span> Overview
              </div>
              <h1>Water resilience, in focus.</h1>
              <p>
                Understand your zones. Test a response. Protect essential
                supply.
              </p>
            </div>
            <Button variant="outline" onClick={openHistory}>
              <Clock3 size={16} />
              Saved runs
            </Button>
          </section>
          {(error || runError) && (
            <div className="error" role="alert">
              {error || runError}
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              <ShieldCheck size={16} />
              {notice}
              <button aria-label="Dismiss notice" onClick={() => setNotice("")}>
                <X size={15} />
              </button>
            </div>
          )}
          <div className="metrics">
            <Metric
              title="Connected zones"
              value={applied ? String(applied.zones.length) : "—"}
              suffix="neighborhoods"
              note="Six zones · one aggregate network"
              icon={<Network size={17} />}
              kind="zones"
            />
            <Metric
              title="Zones below reserve"
              value={displayTotals ? String(displayTotals.below_reserve) : "—"}
              suffix={displayTotals ? "zones" : "not run"}
              note="Calculated at the selected horizon"
              icon={<Waves size={17} />}
              kind="reserve"
            />
            <Metric
              title="Critical demand served"
              value={
                displayTotals ? number(displayTotals.critical_percent) : "—"
              }
              suffix={displayTotals ? "%" : "not run"}
              note="Essential demand is part of total demand"
              icon={<ShieldCheck size={17} />}
              kind="priority"
            />
            <Metric
              title="Available cooling centers"
              value={
                applied
                  ? String(
                      applied.stations.filter(
                        (s) =>
                          s.type === "cooling" &&
                          s.open &&
                          s.accessible &&
                          s.water_available &&
                          s.occupancy < s.capacity &&
                          Number(
                            new Intl.DateTimeFormat("en-GB", {
                              hour: "2-digit",
                              hourCycle: "h23",
                              timeZone: s.timezone,
                            }).format(new Date()),
                          ) >= s.opens &&
                          Number(
                            new Intl.DateTimeFormat("en-GB", {
                              hour: "2-digit",
                              hourCycle: "h23",
                              timeZone: s.timezone,
                            }).format(new Date()),
                          ) < s.closes,
                      ).length,
                    )
                  : "—"
              }
              suffix="demo stations"
              note="Status, hours, access and capacity checked"
              icon={<MapPinIcon />}
              kind="stations"
            />
          </div>
          <div className="overview-grid">
            <section id="scenario-setup" className="card setup-card">
              <div className="panel-heading">
                <div className="title-icon">
                  <FlaskConical size={19} />
                  <h2>Scenario lab</h2>
                </div>
                <span className="badge neutral">
                  VERSION {applied?.scenario_version ?? "—"}
                </span>
              </div>
              <p className="muted">
                Explore how heat, demand and disruptions affect your network.
              </p>
              <label className="field scenario-select">
                <span>Choose a scenario</span>
                <select
                  aria-label="Choose a scenario"
                  value={selectedId}
                  onChange={(e) => setSelectedId(e.target.value)}
                >
                  {scenarios.map((s) => (
                    <option key={s.scenario_id} value={s.scenario_id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
              <p className="scenario-description">{applied?.description}</p>
              <div className="setup-bottom">
                <div>
                  <span className="field-label">Forecast horizon</span>
                  <div
                    className="segmented"
                    role="group"
                    aria-label="Forecast horizon"
                  >
                    {[3, 6, 12].map((h) => (
                      <button
                        key={h}
                        className={horizon === h ? "chosen" : ""}
                        onClick={() => {
                          setHorizon(h);
                          setPreview(null);
                        }}
                      >
                        {h} hours
                      </button>
                    ))}
                  </div>
                </div>
                <div className="agent-switch">
                  <Toggle
                    label="Agents active"
                    checked={agents}
                    onCheckedChange={setAgents}
                  />
                  <span>
                    Agents {agents ? "active" : "paused"}
                    <small>
                      {agents
                        ? "Bounded investigation & planning"
                        : "Direct simulation effects only"}
                    </small>
                  </span>
                </div>
              </div>
              <div className="run-row">
                <Button
                  className="run-button"
                  onClick={start}
                  disabled={busy || !applied || Boolean(dirty)}
                >
                  <Play size={17} fill="currentColor" />
                  Run Simulation
                  <ArrowRight size={17} />
                </Button>
                <span>15-min steps · measured outputs</span>
              </div>
              {dirty && (
                <p className="small warning-text">
                  Apply or reset the draft before starting another run.
                </p>
              )}
            </section>
            <section id="alerts" className="card readiness-card">
              <div className="panel-heading">
                <div className="title-icon">
                  <ShieldCheck size={19} />
                  <h2>Readiness brief</h2>
                </div>
                <span className="badge blue">DEMO</span>
              </div>
              <div className="readiness-visual">
                <div className="readiness-ring">
                  <ShieldCheck size={30} />
                </div>
                <div>
                  <h3>Every response needs evidence.</h3>
                  <p>Simulate alternatives before committing to a plan.</p>
                </div>
              </div>
              <div className="readiness-item">
                <span className="tiny-icon amber">
                  <Thermometer size={16} />
                </span>
                <div>
                  <strong>Explicit heatwave assumptions</strong>
                  <p>Demand changes only through the scenario multiplier.</p>
                </div>
              </div>
              <div className="readiness-item">
                <span className="tiny-icon blue">
                  <ShieldCheck size={16} />
                </span>
                <div>
                  <strong>Essential supply comes first</strong>
                  <p>
                    Plans violating critical-service constraints are rejected.
                  </p>
                </div>
              </div>
              <div className="readiness-footer">
                <span className="status-dot" />
                {cloudMode
                  ? "AWS backend configured"
                  : "Local backend · AWS deployment pending"}
                <span>{transport}</span>
              </div>
            </section>
          </div>
          <section id="zones" className="card conditions">
            <div className="panel-heading">
              <div>
                <div className="title-icon">
                  <Network size={19} />
                  <h2>Zone conditions</h2>
                </div>
                <p className="muted small">
                  {currentRun && shownResult
                    ? "Measured ending state"
                    : "Applied initial conditions"}{" "}
                  · consistent neighborhood scale · synthetic units
                </p>
              </div>
              <span className="badge neutral">
                {applied?.zones.length ?? 0} ZONES
              </span>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Neighborhood</th>
                    <th>Demand</th>
                    <th>Scheduled supply</th>
                    <th>Storage</th>
                    <th>Temperature</th>
                    <th>Condition</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {applied?.zones
                    .filter((z) =>
                      `${z.id} ${z.name}`
                        .toLowerCase()
                        .includes(search.toLowerCase()),
                    )
                    .map((z) => {
                      const state = final?.zones.find((s) => s.id === z.id);
                      return (
                        <tr
                          key={z.id}
                          className={
                            runId && zoneId === z.id ? "selected-row" : ""
                          }
                        >
                          <td>
                            <span className="zone-letter">{z.id}</span>
                            <span className="zone-title">
                              {z.name}
                              <small>
                                {number(z.population, 0)} people served
                              </small>
                            </span>
                          </td>
                          <td>
                            {number(z.demand * z.demand_multiplier)}
                            <small>m³/h</small>
                          </td>
                          <td>
                            {number(state ? state.external / 0.25 : z.supply)}
                            <small>m³/h</small>
                          </td>
                          <td>
                            <div className="storage-cell">
                              <span>
                                {number(state?.storage ?? z.storage, 0)}
                                <small> / {z.storage_capacity} m³</small>
                              </span>
                              <div className="mini-bar">
                                <i
                                  style={{
                                    width: `${(100 * (state?.storage ?? z.storage)) / z.storage_capacity}%`,
                                  }}
                                />
                              </div>
                            </div>
                          </td>
                          <td>
                            {number(z.temperature)}
                            <small> °C</small>
                          </td>
                          <td>
                            <span
                              className={`badge ${state?.condition === "Critical" ? "red" : state?.condition === "Stressed" ? "amber" : "green"}`}
                            >
                              <i />
                              {state?.condition ||
                                (z.storage < z.reserve
                                  ? "Below reserve"
                                  : "Initial state")}
                            </span>
                          </td>
                          <td>
                            <button
                              className="table-edit"
                              aria-label={`Edit zone ${z.id}`}
                              onClick={() => {
                                selectZone(z.id);
                                if (!runId) {
                                  setNotice(
                                    "Run a simulation to open the zone workspace and parameter editor.",
                                  );
                                  navigate("lab");
                                } else
                                  workspace.current?.scrollIntoView({
                                    behavior: reduced() ? "instant" : "smooth",
                                  });
                              }}
                            >
                              <Settings2 size={17} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </section>
          {runId && draft && zone && (
            <section
              ref={workspace}
              className="simulation-workspace"
              id="lab"
              aria-label="Simulation workspace"
            >
              <div className="workspace-heading">
                <div>
                  <span className="eyebrow">SIMULATION WORKSPACE</span>
                  <h2>Test. Compare. Respond.</h2>
                  <p className="muted">
                    {run?.scenario_id ?? selectedId} · v
                    {run?.scenario_version ?? applied?.scenario_version} ·{" "}
                    {run?.horizon ?? horizon}h horizon ·{" "}
                    {shownResult?.model_version ?? "Awaiting model output"}
                  </p>
                </div>
                <span
                  className={`badge ${run && !currentRun && run.status === "awaiting_approval" ? "amber" : run?.status === "completed" ? "green" : "blue"}`}
                >
                  <span
                    className={
                      run &&
                      currentRun &&
                      ![
                        "completed",
                        "infeasible",
                        "failed",
                        "rejected",
                      ].includes(run.status)
                        ? "pulse-dot"
                        : ""
                    }
                  />
                  {run && !currentRun && run.status === "awaiting_approval"
                    ? "Rerun required"
                    : run
                      ? statuses[run.status] || run.status
                      : "Starting run"}
                </span>
              </div>
              {!currentRun && run && (
                <div className="notice approval-guidance" role="status">
                  <div>
                    <strong>Scenario changed · approval unavailable</strong>
                    <p>
                      This run uses {run.scenario_id} v{run.scenario_version};
                      the applied scenario is {applied?.scenario_id} v
                      {applied?.scenario_version}. Rerun the applied version to
                      generate a new plan. Unapplied draft edits are not
                      included.
                    </p>
                  </div>
                  <Button onClick={start} disabled={busy || !applied}>
                    Rerun applied scenario v{applied?.scenario_version}
                  </Button>
                </div>
              )}
              {currentRun && run?.status === "awaiting_approval" && (
                <div className="notice approval-guidance" role="status">
                  <div>
                    <strong>Your decision is needed</strong>
                    <p>
                      Review the proposed actions, then approve or reject the
                      exact plan below. The run waits here until you decide.
                    </p>
                  </div>
                  <Button
                    disabled={!results.plan}
                    onClick={() => {
                      const panel = document.getElementById("response-plan");
                      panel?.scrollIntoView({
                        behavior: reduced() ? "instant" : "smooth",
                        block: "start",
                      });
                      panel?.focus({ preventScroll: true });
                    }}
                  >
                    Review response plan
                  </Button>
                </div>
              )}
              <div className="workspace-grid">
                <div className="workspace-left">
                  <section className="card graph-card">
                    <div className="panel-heading">
                      <div className="title-icon">
                        <Network size={19} />
                        <h3>Zone digital twin</h3>
                      </div>
                      <span className="small muted">
                        Abstract water network
                      </span>
                    </div>
                    <ZoneGraph
                      scenario={draft}
                      result={currentRun ? shownResult : null}
                      selected={zoneId}
                      onSelect={selectZone}
                      onConnection={(c) => setConnectionId(c.id)}
                    />
                    <div className="graph-legend">
                      <span>
                        <i className="legend-dot green-dot" />
                        Reserve maintained
                      </span>
                      <span>
                        <i className="legend-dot amber-dot" />
                        Stressed
                      </span>
                      <span>
                        <i className="legend-dot red-dot" />
                        Critical
                      </span>
                    </div>
                    <p className="small muted graph-note">
                      Select a zone to edit. Select a connection to adjust
                      capacity or control. Draft topology is shown; values are
                      from the identified applied run.
                    </p>
                    {selectedState && (
                      <div className="zone-state-strip">
                        <div>
                          <span>Delivered demand</span>
                          <strong>
                            {number(selectedState.delivered / 0.25)}{" "}
                            <small>m³/h</small>
                          </strong>
                        </div>
                        <div>
                          <span>Supply loss</span>
                          <strong>
                            {number(selectedState.supply_loss / 0.25)}{" "}
                            <small>m³/h</small>
                          </strong>
                        </div>
                        <div>
                          <span>Time to reserve</span>
                          <strong>
                            {selectedState.time_to_reserve === null
                              ? "—"
                              : number(selectedState.time_to_reserve)}{" "}
                            <small>
                              {selectedState.time_to_reserve === null
                                ? "not meaningful"
                                : "hours"}
                            </small>
                          </strong>
                        </div>
                        <div>
                          <span>Operating condition</span>
                          <strong>{selectedState.condition}</strong>
                        </div>
                      </div>
                    )}
                  </section>
                  <section className="card chart-card">
                    <div className="panel-heading">
                      <div>
                        <h3>Storage trajectory · Zone {zoneId}</h3>
                        <p className="small muted">
                          m³ over time · scenario water balance
                        </p>
                      </div>
                      <span className="badge neutral">
                        {preview
                          ? "DRAFT PREVIEW"
                          : results.approved
                            ? "APPROVED"
                            : "BASELINE"}
                      </span>
                    </div>
                    {preview ? (
                      <StorageChart
                        baseline={preview.applied}
                        comparison={preview.draft}
                        zone={applied!.zones.find((z) => z.id === zoneId)!}
                        label="Draft preview"
                      />
                    ) : results.baseline ? (
                      <StorageChart
                        baseline={results.baseline}
                        comparison={results.approved}
                        zone={(results.scenario || applied!).zones.find(
                          (z) => z.id === zoneId,
                        )!}
                        label="Approved plan"
                      />
                    ) : (
                      <div className="empty-chart">
                        Waiting for computed time series.
                      </div>
                    )}
                    {forecastEvidence && (
                      <p className="small muted forecast-range">
                        Nominal-loss network storage range:{" "}
                        {number(forecastEvidence.result.storage_range[0], 0)}–
                        {number(forecastEvidence.result.storage_range[1], 0)}{" "}
                        m³. ±10% demand scenarios with an essential-demand
                        floor, not a calibrated probability interval.
                      </p>
                    )}
                  </section>
                </div>
                <ZoneEditor
                  zone={zone}
                  scenario={draft}
                  onChange={(z) =>
                    changeDraft({
                      ...draft,
                      zones: draft.zones.map((old) =>
                        old.id === z.id ? z : old,
                      ),
                    })
                  }
                  onStation={(id, open) =>
                    changeDraft({
                      ...draft,
                      stations: draft.stations.map((s) =>
                        s.id === id ? { ...s, open } : s,
                      ),
                    })
                  }
                  onPreview={previewDraft}
                  onApply={applyDraft}
                  onReset={resetDraft}
                  busy={busy}
                />
              </div>
              {(preview || results.baseline) && (
                <FlowCharts
                  baseline={preview ? preview.applied : results.baseline!}
                  comparison={preview ? preview.draft : results.approved}
                  zoneId={zoneId}
                  label={preview ? "Draft preview" : "Approved plan"}
                />
              )}
              <div className="scenario-tools">
                <p>
                  <FileJson size={16} />
                  Applied scenario v{applied?.scenario_version}. Export contains
                  no credentials or approval tokens.
                </p>
                <div className="button-row">
                  <Button
                    variant="outline"
                    onClick={() =>
                      downloadJson(
                        applied,
                        `aquaagent-${selectedId}-v${applied?.scenario_version}.json`,
                      )
                    }
                  >
                    <ArrowDownToLine size={16} />
                    Export JSON
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => upload.current?.click()}
                    disabled={busy}
                  >
                    <Upload size={16} />
                    Import JSON
                  </Button>
                  <input
                    ref={upload}
                    type="file"
                    accept="application/json,.json"
                    hidden
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) importFile(file);
                      e.target.value = "";
                    }}
                  />
                </div>
              </div>
              <Comparison
                results={results}
                preview={preview}
                scenario={preview ? applied! : results.scenario || applied!}
              />
              {results.plan && (
                <PlanPanel
                  plan={results.plan}
                  run={run}
                  stale={!currentRun}
                  busy={busy}
                  onDecision={decision}
                  onReport={report}
                />
              )}
              <section className="card activity-card" id="activity">
                <div className="panel-heading">
                  <div className="title-icon">
                    <Activity size={19} />
                    <h3>Run activity & evidence</h3>
                  </div>
                  <span className="badge neutral">
                    {run?.llm_calls ?? 0} LLM CALLS
                  </span>
                </div>
                <p className="small muted">
                  {run?.agent_mode ??
                    (agents
                      ? "Agent mode will be reported after execution"
                      : "Agents paused")}{" "}
                  · {transport}. Observable tools and results; no private
                  reasoning.
                </p>
                {run?.provider_error && (
                  <div className="notice">{run.provider_error}</div>
                )}
                <div className="activity-list">
                  {events
                    .slice(-14)
                    .reverse()
                    .map((event) => (
                      <div className="activity-entry" key={event.seq}>
                        <span
                          className={`activity-icon ${event.kind === "error" ? "red" : ""}`}
                        >
                          <Check size={14} />
                        </span>
                        <div>
                          <strong>{event.message}</strong>
                          <small>
                            #{event.seq} · {event.kind} ·{" "}
                            {new Date(
                              event.timestamp * 1000,
                            ).toLocaleTimeString("en-IN", {
                              hour: "2-digit",
                              minute: "2-digit",
                              second: "2-digit",
                            })}
                          </small>
                        </div>
                      </div>
                    ))}
                </div>
                {results.agent?.candidates && (
                  <details>
                    <summary>
                      Candidate localization evidence · fit scores are not
                      probabilities
                    </summary>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Zone</th>
                            <th>Hypothesis</th>
                            <th>Mean squared residual</th>
                            <th>Samples</th>
                          </tr>
                        </thead>
                        <tbody>
                          {results.agent.candidates.map((c, i) => (
                            <tr key={i}>
                              <td>{c.zone_id}</td>
                              <td>{c.hypothesis.replaceAll("_", " ")}</td>
                              <td>{number(c.fit_mse, 4)}</td>
                              <td>{c.compared_samples}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                )}
                {results.agent?.negotiation && (
                  <details>
                    <summary>
                      Zone requests & offers ·{" "}
                      {results.agent?.negotiation_mode ||
                        "deterministic fallback"}
                    </summary>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Round</th>
                            <th>Zone</th>
                            <th>Request m³/h</th>
                            <th>Offer m³/h</th>
                            <th>Reason</th>
                            <th>Decision mode</th>
                          </tr>
                        </thead>
                        <tbody>
                          {results.agent.negotiation.map((n, i) => (
                            <tr key={i}>
                              <td>{n.round}</td>
                              <td>{n.zone_id}</td>
                              <td>{number(n.request_rate)}</td>
                              <td>{number(n.offer_rate)}</td>
                              <td>{n.reason}</td>
                              <td>
                                {n.decision_mode || "deterministic fallback"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {results.agent.negotiation_fallback_reasons?.map(
                      (reason, i) => (
                        <p className="small muted" key={i}>
                          {reason}
                        </p>
                      ),
                    )}
                  </details>
                )}
              </section>
            </section>
          )}
          <footer className="page-footer">
            <span>
              <Droplets size={14} />
              AquaAgent · Synthetic aggregate-zone model
            </span>
            <span>
              Evidence before action. Every cubic metre accounted for.
            </span>
          </footer>
        </main>
      </div>
      <ConnectionEditor
        connection={
          draft?.connections.find((c) => c.id === connectionId) ?? null
        }
        onClose={() => setConnectionId(null)}
        onChange={(c: Connection) =>
          draft &&
          changeDraft({
            ...draft,
            connections: draft.connections.map((old) =>
              old.id === c.id ? c : old,
            ),
          })
        }
      />
      <Modal
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        title="Saved runs"
        description="Reopen persisted run state, plans and evidence."
      >
        <div className="saved-runs">
          {savedRuns.length ? (
            savedRuns.map((r) => (
              <button
                key={r.run_id}
                onClick={() => {
                  setSelectedId(r.scenario_id);
                  setRunId(r.run_id);
                  setHistoryOpen(false);
                }}
              >
                <span>
                  <strong>
                    {r.scenario_id} · v{r.scenario_version}
                  </strong>
                  <small>
                    {r.horizon}h · {r.run_id.slice(0, 8)}
                  </small>
                </span>
                <span className="badge blue">
                  {statuses[r.status] || r.status}
                </span>
                <ArrowRight size={16} />
              </button>
            ))
          ) : (
            <p className="muted">No saved runs yet.</p>
          )}
        </div>
      </Modal>
    </div>
  );
}
function MapPinIcon() {
  return <Globe2 size={17} />;
}
function Metric({
  title,
  value,
  suffix,
  note,
  icon,
  kind,
}: {
  title: string;
  value: string;
  suffix: string;
  note: string;
  icon: React.ReactNode;
  kind: string;
}) {
  return (
    <section className="card metric">
      <div className="metric-title">
        {icon}
        {title}
      </div>
      <div className="metric-body">
        <div>
          <strong key={value}>{value}</strong>
          <span>{suffix}</span>
        </div>
        <Accent kind={kind} />
      </div>
      <p>{note}</p>
    </section>
  );
}
function Comparison({
  results,
  preview,
  scenario,
}: {
  results: Results;
  preview: {
    draft: import("./types").Result;
    applied: import("./types").Result;
  } | null;
  scenario: Scenario;
}) {
  const before = preview?.applied || results.baseline,
    after = preview?.draft || results.approved;
  if (!before) return null;
  return (
    <section className="card comparison">
      <div className="panel-heading">
        <div>
          <h3>Before & after · network effects</h3>
          <p className="small muted">
            {preview
              ? "Isolated draft vs applied initial conditions"
              : "Approved actions vs baseline"}{" "}
            · all quantities calculated over the full horizon
          </p>
        </div>
        <span className="badge green">MASS BALANCE VERIFIED</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Zone</th>
              <th>Ending storage m³</th>
              <th>Unmet demand m³</th>
              <th>Incoming transfers m³</th>
              <th>Critical demand served %</th>
              <th>Ending condition</th>
            </tr>
          </thead>
          <tbody>
            {scenario.zones.map((z) => {
              const a = before.time_series
                  .at(-1)!
                  .zones.find((s) => s.id === z.id)!,
                b = after?.time_series.at(-1)!.zones.find((s) => s.id === z.id);
              const sums = (
                r: typeof before,
                key:
                  | "unmet"
                  | "incoming"
                  | "critical_served"
                  | "critical_requested",
              ) =>
                r.time_series.reduce(
                  (sum, row) =>
                    sum + (row.zones.find((s) => s.id === z.id)?.[key] || 0),
                  0,
                );
              const critical = (r: typeof before) =>
                sums(r, "critical_requested")
                  ? (100 * sums(r, "critical_served")) /
                    sums(r, "critical_requested")
                  : 100;
              return (
                <tr key={z.id}>
                  <td>
                    <span className="zone-letter">{z.id}</span>
                    {z.name}
                  </td>
                  <td>
                    {number(a.storage)}{" "}
                    {b && (
                      <span className="after-value">→ {number(b.storage)}</span>
                    )}
                  </td>
                  <td>
                    {number(sums(before, "unmet"))}{" "}
                    {after && (
                      <span className="after-value">
                        → {number(sums(after, "unmet"))}
                      </span>
                    )}
                  </td>
                  <td>
                    {number(sums(before, "incoming"))}{" "}
                    {after && (
                      <span className="after-value">
                        → {number(sums(after, "incoming"))}
                      </span>
                    )}
                  </td>
                  <td>
                    {number(critical(before))}
                    {after && (
                      <span className="after-value">
                        {" "}
                        → {number(critical(after))}
                      </span>
                    )}
                  </td>
                  <td>
                    {a.condition}
                    {b && <span className="after-value"> → {b.condition}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="small muted verification-note">
        Maximum step balance residual:{" "}
        {before.max_mass_residual.toExponential(2)} m³. Simulation runtime:{" "}
        {number(before.elapsed_ms, 2)} ms.{" "}
        {after && `Compared runtime: ${number(after.elapsed_ms, 2)} ms.`}
      </p>
    </section>
  );
}
function PlanPanel({
  plan,
  run,
  stale,
  busy,
  onDecision,
  onReport,
}: {
  plan: Plan;
  run: Run | null;
  stale: boolean;
  busy: boolean;
  onDecision: (d: "approve" | "reject") => void;
  onReport: () => void;
}) {
  return (
    <section
      className="card plan-card"
      id="response-plan"
      tabIndex={-1}
      aria-label="Response plan"
    >
      <div className="panel-heading">
        <div className="title-icon">
          <ShieldCheck size={20} />
          <h3>
            {plan.feasible
              ? "Verified response plan"
              : "Essential supply shortfall · escalate"}
          </h3>
        </div>
        <span className={`badge ${plan.feasible ? "green" : "red"}`}>
          PLAN v{plan.plan_version}
        </span>
      </div>
      <p className="muted small">
        {plan.mode} · scenario v{plan.scenario_version}. Approval applies to
        these exact actions.
      </p>
      <div className="plan-grid">
        <div>
          {plan.actions.length ? (
            <div className="plan-actions">
              {plan.actions.map((a, i) => (
                <div key={i}>
                  <Check size={16} />
                  <strong>
                    {a.type.replaceAll("_", " ")} · {a.target}
                  </strong>
                  <span>
                    {a.value}{" "}
                    {a.type === "supply"
                      ? "m³/h"
                      : a.type === "repair"
                        ? "repair complete"
                        : "capacity"}{" "}
                    at {a.at_hour}h
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">
              No feasible intervention{" "}
              {plan.feasible
                ? "required"
                : "identified under configured availability"}
              .
            </p>
          )}
          {plan.violations.length > 0 && (
            <div className="error">
              <strong>Hard constraints failed</strong>
              <ul>
                {plan.violations.slice(0, 4).map((v) => (
                  <li key={v}>{v}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="small muted">{plan.uncertainty}</p>
        </div>
        <div className="plan-outcomes">
          <span>Verified critical demand</span>
          <strong>
            {number(plan.verified_totals.critical_percent)}
            <small>%</small>
          </strong>
          <span>Remaining unmet demand</span>
          <b>{number(plan.verified_totals.unmet)} m³</b>
          <span>Losses over horizon</span>
          <b>{number(plan.verified_totals.losses)} m³</b>
        </div>
      </div>
      <div className="button-row">
        <Button
          onClick={() => onDecision("approve")}
          disabled={
            busy ||
            stale ||
            !plan.feasible ||
            run?.status !== "awaiting_approval"
          }
        >
          <ShieldCheck size={16} />
          Approve exact plan
        </Button>
        <Button
          variant="outline"
          onClick={() => onDecision("reject")}
          disabled={busy || stale || run?.status !== "awaiting_approval"}
        >
          Reject plan
        </Button>
        <Button
          variant="ghost"
          onClick={onReport}
          disabled={
            busy ||
            !["completed", "infeasible", "rejected"].includes(run?.status || "")
          }
        >
          <FileJson size={16} />
          Open evidence report
        </Button>
      </div>
      <details>
        <summary>
          Candidate plans, rejected constraints & proposed water points
        </summary>
        <div className="candidate-list">
          {plan.alternatives.map((a, i) => (
            <div key={i}>
              <span className={`badge ${a.feasible ? "green" : "red"}`}>
                {a.feasible ? "Feasible" : "Rejected"}
              </span>
              <span>
                {a.actions.length} actions · {number(a.totals.unmet)} m³ unmet ·{" "}
                {number(a.totals.losses)} m³ lost
              </span>
              <p className="small muted">{a.violations[0]}</p>
            </div>
          ))}
          {plan.candidate_sites.map((s) => (
            <div key={s.zone_id}>
              <span className="badge blue">PROPOSAL</span>Zone {s.zone_id} ·{" "}
              {number(s.footfall)} synthetic footfall · {s.added_demand} m³/h
              added demand ·{" "}
              {s.feasible ? "passes constraints" : "requires additional supply"}
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}
export default App;
