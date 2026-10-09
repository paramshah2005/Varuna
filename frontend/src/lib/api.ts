import { ensureAccessToken } from "./auth";
export const apiBase = import.meta.env.VITE_API_URL || "/api";
export async function api<T>(
  path: string,
  body?: unknown,
  key?: string,
): Promise<T> {
  const token = await ensureAccessToken();
  const response = await fetch(`${apiBase}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(key ? { "Idempotency-Key": key } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      value.error +
        (value.details
          ? ": " +
            value.details
              .map(
                (d: { field: string; message: string }) =>
                  `${d.field}: ${d.message}`,
              )
              .join("; ")
          : ""),
    );
  return value;
}
export function downloadJson(value: unknown, filename: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function number(value: number | undefined | null, digits = 1) {
  return value == null
    ? "—"
    : new Intl.NumberFormat("en-IN", { maximumFractionDigits: digits }).format(
        value,
      );
}
export function mergeEvents(
  old: import("../types").RunEvent[],
  incoming: import("../types").RunEvent[],
) {
  return [
    ...new Map([...old, ...incoming].map((e) => [e.seq, e])).values(),
  ].sort((a, b) => a.seq - b.seq);
}
export function contiguousSequence(events: import("../types").RunEvent[]) {
  let seq = 0;
  for (const event of events) {
    if (event.seq !== seq + 1) break;
    seq = event.seq;
  }
  return seq;
}
