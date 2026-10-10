import { useEffect, useRef, useState } from "react";
import { api, contiguousSequence, mergeEvents } from "./api";
import type { Results, Run, RunEvent } from "../types";

function emptyResults(): Results {
  return {
    baseline: null,
    approved: null,
    plan: null,
    agent: null,
  };
}

export function useRun(runId: string | null) {
  const [run, setRun] = useState<Run | null>(null),
    [results, setResults] = useState<Results>(emptyResults),
    [events, setEvents] = useState<RunEvent[]>([]),
    [error, setError] = useState(""),
    [transport, setTransport] = useState("Polling");
  const cursor = useRef(0),
    eventsRef = useRef<RunEvent[]>([]),
    statusRef = useRef("");
  useEffect(() => {
    setRun(null);
    setResults(emptyResults());
    setEvents([]);
    setError("");
    eventsRef.current = [];
    cursor.current = 0;
    statusRef.current = "";
    if (!runId) return;
    let active = true,
      loading = false,
      socket: WebSocket | undefined,
      reconnect: ReturnType<typeof setTimeout> | undefined,
      attempts = 0;
    function append(incoming: RunEvent[]) {
      eventsRef.current = mergeEvents(eventsRef.current, incoming);
      cursor.current = contiguousSequence(eventsRef.current);
      if (active) setEvents(eventsRef.current);
    }
    async function refresh() {
      if (!active || loading) return;
      loading = true;
      try {
        const [meta, eventBody] = await Promise.all([
          api<Run>(`/runs/${runId}`),
          api<{ events: RunEvent[] }>(
            `/runs/${runId}/events?after_seq=${cursor.current}`,
          ),
        ]);
        if (!active) return;
        setRun(meta);
        append(eventBody.events);
        if (statusRef.current !== meta.status) {
          const next = await api<Results>(`/runs/${runId}/results`);
          if (active) {
            setResults(next);
            statusRef.current = meta.status;
          }
        }
        setError("");
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        loading = false;
      }
    }
    async function connect() {
      if (!active || !import.meta.env.VITE_WS_URL) return;
      try {
        const ticket = await api<{ ticket: string }>("/ws-ticket", {});
        if (!active) return;
        socket = new WebSocket(
          `${import.meta.env.VITE_WS_URL}?ticket=${encodeURIComponent(ticket.ticket)}`,
        );
        socket.onopen = () => {
          attempts = 0;
          setTransport("WebSocket + polling recovery");
          socket?.send(JSON.stringify({ action: "subscribe", run_id: runId }));
          refresh();
        };
        socket.onmessage = (event) => {
          try {
            const value = JSON.parse(event.data);
            if (value.run_id === runId && typeof value.seq === "number")
              append([value]);
            refresh();
          } catch {
            refresh();
          }
        };
        socket.onclose = () => {
          if (active) {
            setTransport("Polling fallback");
            reconnect = setTimeout(
              connect,
              Math.min(30000, 1000 * 2 ** attempts++),
            );
          }
        };
        socket.onerror = () => socket?.close();
      } catch {
        if (active) {
          setTransport("Polling fallback");
          reconnect = setTimeout(connect, 10000);
        }
      }
    }
    refresh();
    connect();
    const timer = setInterval(refresh, 1200);
    return () => {
      active = false;
      clearInterval(timer);
      if (reconnect) clearTimeout(reconnect);
      socket?.close();
    };
  }, [runId]);
  return { run, results, events, error, transport };
}
