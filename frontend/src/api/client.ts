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

export function parseJobEvent(raw: string): JobEvent {
  const e: unknown = JSON.parse(raw);
  if (!e || typeof e !== "object") throw new Error("Malformed event payload");
  const value = e as Record<string, unknown>;
  if (
    value.schema_version !== "1.0" ||
    !Number.isInteger(value.sequence) ||
    Number(value.sequence) < 1 ||
    typeof value.job_id !== "string" ||
    typeof value.run_id !== "string" ||
    typeof value.attempt_id !== "string" ||
    typeof value.timestamp !== "number" ||
    !["status", "done", "diagnostic"].includes(String(value.type)) ||
    ![
      "pending",
      "running",
      "completed",
      "failed",
      "cancelled",
      "timed_out",
      "interrupted",
    ].includes(String(value.state))
  ) {
    throw new Error("Incompatible event schema; refresh the workspace client");
  }
  return value as unknown as JobEvent;
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
  let latest = cursor;
  const receive = (message: MessageEvent<string>) => {
    try {
      const event = parseJobEvent(message.data);
      if (event.job_id !== id)
        throw new Error("Event belongs to a different job");
      if (event.sequence <= latest) return;
      if (event.sequence !== latest + 1)
        throw new Error("Event journal gap; reload authoritative job state");
      latest = event.sequence;
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
