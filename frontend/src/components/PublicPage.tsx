import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Droplets,
  LocateFixed,
  MapPin,
  ShieldCheck,
  Thermometer,
  Wind,
} from "lucide-react";
import type { Station } from "../types";
import { api, number } from "../lib/api";
import { Button, Toggle } from "./ui";
type PublicZone = {
  id: string;
  name: string;
  temperature: number;
  humidity: number;
};
type WalkingRoute = {
  station: Station;
  zone_path: string[];
  walking_minutes: number;
  synthetic: boolean;
};
export function PublicPage() {
  const [zones, setZones] = useState<PublicZone[]>([]),
    [stations, setStations] = useState<Station[]>([]),
    [selected, setSelected] = useState("B"),
    [accessible, setAccessible] = useState(true),
    [outage, setOutage] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [walk, setWalk] = useState<WalkingRoute | null | undefined>();
  useEffect(() => {
    api<{ zones: PublicZone[]; stations: Station[] }>(
      `/public/stations${outage ? "?scenario_id=station-outage" : ""}`,
    )
      .then((v) => {
        setZones(v.zones);
        setStations(v.stations);
        setWalk(undefined);
      })
      .catch((e) => setError(e.message));
  }, [outage]);
  const zone = zones.find((z) => z.id === selected);
  async function find(body: Record<string, unknown> = { zone_id: selected }) {
    setBusy(true);
    setError("");
    try {
      const v = await api<{ route: WalkingRoute | null }>(
        "/public/demo-route",
        {
          ...body,
          accessible,
          scenario_id: outage ? "station-outage" : "normal",
        },
      );
      setWalk(v.route);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function locate() {
    if (!navigator.geolocation) {
      setError("Geolocation unavailable. Choose a zone manually.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) =>
        find({ latitude: p.coords.latitude, longitude: p.coords.longitude }),
      () => setError("Location unavailable. Choose a zone manually."),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 },
    );
  }
  return (
    <main className="public-page">
      <a className="back-link" href="/">
        <ArrowLeft size={16} />
        Operator workspace
      </a>
      <div className="brand">
        <span className="brand-icon">
          <Droplets />
        </span>
        <span>
          AquaAgent<small>NEIGHBORHOOD SUPPORT</small>
        </span>
      </div>
      <span className="badge blue">Synthetic walking demo</span>
      <h1>
        A cooler place.
        <br />A little closer.
      </h1>
      <p className="muted">
        Explore available cooling centers in our seeded neighborhood. These
        facilities and paths are demonstration data.
      </p>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <section className="card public-controls">
        <label className="field">
          <span>Your demo neighborhood</span>
          <select
            aria-label="Your demo neighborhood"
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              setWalk(undefined);
            }}
          >
            {zones.map((z) => (
              <option key={z.id} value={z.id}>
                {z.id} · {z.name}
              </option>
            ))}
          </select>
        </label>
        <div className="public-weather">
          <div>
            <Thermometer size={20} />
            <strong>{number(zone?.temperature)}°C</strong>
            <small>Demo ambient temperature</small>
          </div>
          <div>
            <Wind size={20} />
            <strong>{number(zone?.humidity)}%</strong>
            <small>Demo relative humidity</small>
          </div>
        </div>
        <div className="station-toggle">
          <span>Step-free access required</span>
          <Toggle
            label="Step-free access required"
            checked={accessible}
            onCheckedChange={setAccessible}
          />
        </div>
        <div className="station-toggle">
          <span>Simulate station C closure</span>
          <Toggle
            label="Simulate station C closure"
            checked={outage}
            onCheckedChange={setOutage}
          />
        </div>
        <Button onClick={() => find()} disabled={busy}>
          <MapPin size={17} />
          {busy ? "Finding a path…" : "Find a cooling center"}
          <ArrowRight size={16} />
        </Button>
        <Button variant="ghost" onClick={locate}>
          <LocateFixed size={16} />
          Use my location
        </Button>
        <p className="small muted">
          Location stays in the routing request and is not stored. GPS outside
          the synthetic area uses manual fallback.
        </p>
      </section>
      {walk !== undefined && (
        <section className="card public-route" aria-live="polite">
          {walk ? (
            <>
              <span className="eyebrow">ELIGIBLE COOLING CENTER</span>
              <h2>{walk.station.name}</h2>
              <div className="walking-time">
                {walk.walking_minutes}
                <small>minutes on a synthetic walking graph</small>
              </div>
              <div className="path-pills">
                {walk.zone_path.map((z, i) => (
                  <span key={z}>
                    {i > 0 && <ArrowRight size={15} />}Zone {z}
                  </span>
                ))}
              </div>
              <p>
                <ShieldCheck size={16} />
                Reported open · water available · capacity available
              </p>
              <p className="small muted">
                {walk.station.capacity - walk.station.occupancy} places
                remaining. Source: synthetic fixture, {walk.station.verified_at}
                . This is not a verified real-world route.
              </p>
            </>
          ) : (
            <>
              <h2>No eligible cooling center</h2>
              <p className="muted">
                Operating hours, closure, accessibility, occupancy and reported
                water availability are checked separately. Try another demo
                option.
              </p>
            </>
          )}
        </section>
      )}
      <section className="guidance">
        <ShieldCheck size={21} />
        <div>
          <h3>Environmental guidance</h3>
          <p>
            Seek shade or a cooler place, take breaks, and keep drinking water
            available. This demo cannot assess your health. For a medical
            emergency, seek urgent local help.
          </p>
          <a
            href="https://www.cdc.gov/extreme-heat/prevention/"
            target="_blank"
            rel="noreferrer"
            className="guidance-source"
          >
            CDC heat-prevention guidance
            <ArrowRight size={12} />
          </a>
        </div>
      </section>
      <p className="small muted">
        {stations.filter((s) => s.type === "cooling").length} demo cooling
        centers currently eligible. Stations follow Asia/Kolkata operating
        hours. Water simulation decisions do not determine this guidance.
      </p>
    </main>
  );
}
