import { test, expect } from "@playwright/test";
import { parseJobEvent, subscribeToJobStream } from "../src/api/client";

const status = {
  schema_version: "1.0",
  sequence: 1,
  job_id: "job-a",
  run_id: "run-a",
  attempt_id: "attempt-a",
  timestamp: 1,
  type: "status",
  state: "running",
};

for (const [field, value] of [
  ["type", ["status"]],
  ["state", ["running"]],
  ["sequence", 1.5],
  ["schema_version", "2.0"],
  ["job_id", null],
  ["run_id", 123],
  ["attempt_id", false],
  ["timestamp", "1"],
] as const) {
  test(`event schema rejects incompatible ${field}: ${JSON.stringify(value)}`, () => {
    expect(() =>
      parseJobEvent(JSON.stringify({ ...status, [field]: value })),
    ).toThrow();
  });
}

test("event timestamp must be finite even when JSON syntax is valid", () => {
  const raw = JSON.stringify(status).replace(
    '"timestamp":1',
    '"timestamp":1e999',
  );
  expect(() => parseJobEvent(raw)).toThrow();
});

class Source extends EventTarget {
  closed = false;
  onopen?: () => void;
  onerror?: () => void;
  close() {
    this.closed = true;
  }
  send(type: string, event: unknown) {
    this.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(event) }));
  }
}

for (const fault of ["other-job", "gap", "invalid-schema"]) {
  test(`journal ${fault} closes transport without delivering a false update`, () => {
    const source = new Source();
    const original = globalThis.EventSource;
    globalThis.EventSource = class {
      constructor() {
        return source;
      }
    } as unknown as typeof EventSource;
    try {
      const events: number[] = [],
        connections: string[] = [];
      subscribeToJobStream(
        "job-a",
        0,
        (e) => events.push(e.sequence),
        (s) => connections.push(s),
      );
      const bad = { ...status };
      if (fault === "other-job") bad.job_id = "job-b";
      if (fault === "gap") bad.sequence = 2;
      if (fault === "invalid-schema") bad.schema_version = "2.0";
      source.send("status", bad);
      expect(source.closed).toBe(true);
      expect(events).toEqual([]);
      expect(connections[0]).toMatch(/different job|journal gap|Incompatible/);
    } finally {
      globalThis.EventSource = original;
    }
  });
}

test("duplicate replay is ignored and a contiguous done event closes the journal", () => {
  const source = new Source();
  const original = globalThis.EventSource;
  globalThis.EventSource = class {
    constructor() {
      return source;
    }
  } as unknown as typeof EventSource;
  try {
    const events: number[] = [],
      connections: string[] = [];
    const close = subscribeToJobStream(
      "job-a",
      0,
      (e) => events.push(e.sequence),
      (s) => connections.push(s),
    );
    source.onopen?.();
    source.send("status", status);
    source.send("status", status);
    source.onerror?.();
    source.send("done", {
      ...status,
      sequence: 2,
      state: "completed",
      type: "done",
    });
    expect(events).toEqual([1, 2]);
    expect(connections).toEqual([
      "Connected",
      "Disconnected; reconnecting (status polling remains active)",
      "Journal complete",
    ]);
    expect(source.closed).toBe(true);
    close();
  } finally {
    globalThis.EventSource = original;
  }
});
