import { describe, expect, it } from "vitest";
import { contiguousSequence, mergeEvents } from "./api";
import type { RunEvent } from "../types";
const event = (seq: number) =>
  ({
    seq,
    kind: "tool",
    message: "actual result",
    timestamp: 0,
    detail: {},
    run_id: "run",
  }) as RunEvent;
describe("ordered event recovery", () => {
  it("deduplicates retries and keeps sequence order", () => {
    expect(
      mergeEvents([event(1), event(3)], [event(2), event(3)]).map((e) => e.seq),
    ).toEqual([1, 2, 3]);
  });
  it("does not skip missing events after an out-of-order websocket update", () => {
    expect(contiguousSequence([event(1), event(3)])).toBe(1);
    expect(
      contiguousSequence(mergeEvents([event(1), event(3)], [event(2)])),
    ).toBe(3);
  });
});
