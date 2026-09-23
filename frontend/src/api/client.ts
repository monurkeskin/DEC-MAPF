import type {
  JobEvent,
  JobStatusResponse,
  JobSubmissionRequest,
  RunDetail,
  RunSummary,
  ScenarioDetail,
  ScenarioSummary,
  SolverCapability,
} from "./types";

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: res.statusText }));
    const detail =
      typeof payload.detail === "string"
        ? payload.detail
        : JSON.stringify(payload.detail);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}
export function post<T>(path: string, body: unknown, key?: string) {
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    headers: key ? { "Idempotency-Key": key } : {},
  });
}
export const fetchCapabilities = () =>
  request<SolverCapability[]>("/capabilities");
export const fetchScenarios = () => request<ScenarioSummary[]>("/scenarios");
export const fetchScenario = (id: string) =>
  request<ScenarioDetail>(`/scenarios/${encodeURIComponent(id)}`);
export const submitSimulationJob = (body: JobSubmissionRequest, key: string) =>
  post<JobStatusResponse>("/jobs", body, key);
export const fetchJobStatus = (id: string) =>
  request<JobStatusResponse>(`/jobs/${encodeURIComponent(id)}`);
export const cancelJob = (id: string) =>
  post<{ cancelled: boolean }>(`/jobs/${encodeURIComponent(id)}/cancel`, {});
export const fetchRuns = () => request<RunSummary[]>("/runs?limit=100");
export const fetchRunDetails = (id: string, signal?: AbortSignal) =>
  request<RunDetail>(`/runs/${encodeURIComponent(id)}?include_frames=false`, {
    signal,
  });

type EventRecord = Record<string, unknown>;

function hasEventIdentity(value: EventRecord): boolean {
  return [value.job_id, value.run_id, value.attempt_id].every(
    (id) => typeof id === "string",
  );
}

function hasEventOrdering(value: EventRecord): boolean {
  return (
    value.schema_version === "1.0" &&
    Number.isInteger(value.sequence) &&
    Number(value.sequence) >= 1 &&
    typeof value.timestamp === "number" &&
    Number.isFinite(value.timestamp)
  );
}

function hasEventState(value: EventRecord): boolean {
  const types = ["status", "done", "diagnostic"];
  const states = [
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
    "interrupted",
  ];
  return (
    typeof value.type === "string" &&
    types.includes(value.type) &&
    typeof value.state === "string" &&
    states.includes(value.state)
  );
}

export function parseJobEvent(raw: string): JobEvent {
  const event: unknown = JSON.parse(raw);
  if (!event || typeof event !== "object")
    throw new Error("Malformed event payload");
  const value = event as EventRecord;
  if (
    !hasEventIdentity(value) ||
    !hasEventOrdering(value) ||
    !hasEventState(value)
  )
    throw new Error("Incompatible event schema; refresh the workspace client");
  return value as unknown as JobEvent;
}

class EventCursor {
  private readonly jobId: string;
  private sequence: number;

  constructor(jobId: string, sequence: number) {
    this.jobId = jobId;
    this.sequence = sequence;
  }

  accept(event: JobEvent): boolean {
    if (event.job_id !== this.jobId)
      throw new Error("Event belongs to a different job");
    if (event.sequence <= this.sequence) return false;
    if (event.sequence !== this.sequence + 1)
      throw new Error("Event journal gap; reload authoritative job state");
    this.sequence = event.sequence;
    return true;
  }
}

export function subscribeToJobStream(
  id: string,
  cursor: number,
  onEvent: (event: JobEvent) => void,
  onConnection: (status: string) => void,
): () => void {
  const stream = new EventSource(
    `/api/v1/jobs/${encodeURIComponent(id)}/stream?cursor=${cursor}`,
  );
  const position = new EventCursor(id, cursor);
  const receive = (message: MessageEvent<string>) => {
    try {
      const event = parseJobEvent(message.data);
      if (!position.accept(event)) return;
      onEvent(event);
      if (event.type === "done") {
        stream.close();
        onConnection("Journal complete");
      }
    } catch (error) {
      stream.close();
      onConnection(
        error instanceof Error ? error.message : "Event schema error",
      );
    }
  };
  stream.addEventListener("status", receive as EventListener);
  stream.addEventListener("done", receive as EventListener);
  stream.addEventListener("diagnostic", receive as EventListener);
  stream.onopen = () => onConnection("Connected");
  stream.onerror = () =>
    onConnection("Disconnected; reconnecting (status polling remains active)");
  return () => stream.close();
}
