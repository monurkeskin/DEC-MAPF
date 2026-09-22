import { useState } from "react";
import type { FrameSnapshot, SolverRunResult } from "../api/types";
import { getAgentColorHex } from "./agentColors";
interface Props {
  runResult: SolverRunResult | null;
  currentFrame?: FrameSnapshot;
  selectedAgent: string | null;
  onSelectAgent: (id: string | null) => void;
  onSeek?: (tick: number) => void;
}
export function InspectorPanel({
  runResult: r,
  currentFrame: f,
  selectedAgent,
  onSelectAgent,
  onSeek,
}: Props) {
  const [session, setSession] = useState(""),
    [filter, setFilter] = useState("all");
  const [note, setNote] = useState("");
  const [page, setPage] = useState(0);
  const [bookmarks, setBookmarks] = useState<
    Record<string, { tick: number; note: string; agent: string | null }[]>
  >(() => {
    try {
      return JSON.parse(localStorage.getItem("mapf-bookmarks") || "{}");
    } catch {
      return {};
    }
  });
  const events = r?.telemetry_events || [];
  const sessions = events.filter((e) => e.event_type === "NEGO_SESSION");
  const selectedEvents = events.filter(
    (e) =>
      (!session || e.session_id === session) &&
      (filter === "all" || e.event_type === filter),
  );
  return (
    <aside className="inspector-panel" aria-label="Run inspector">
      <h2>Inspect evidence</h2>
      {!r ? (
        <p className="muted">
          Run a scenario or load a saved replay to inspect its recorded state.
        </p>
      ) : (
        <>
          <dl className="metrics">
            <dt>Solver outcome</dt>
            <dd>{r.solver_outcome}</dd>
            <dt>Independent check</dt>
            <dd data-testid="validation-status">
              {r.validation?.status || "not_checked"}
            </dd>
            <dt>Makespan</dt>
            <dd>{r.makespan} ticks</dd>
            <dt>Sum of costs</dt>
            <dd>{r.sum_of_costs} actions</dd>
            <dt>Solver time</dt>
            <dd>{r.runtime_ms.toFixed(2)} ms</dd>
            <dt>Negotiations</dt>
            <dd>
              {r.metric_availability.negotiation_count
                ? r.negotiation_count
                : "Unavailable"}
            </dd>
            <dt>Measured sharing</dt>
            <dd>
              {r.metric_availability.information_sharing_rate
                ? `${(100 * r.information_sharing_rate).toFixed(2)}%`
                : "Unavailable"}
            </dd>
            <dt>Delivered messages / bytes</dt>
            <dd>
              {String(r.measured_metrics?.message_count ?? "Unavailable")} /{" "}
              {String(r.measured_metrics?.payload_bytes ?? "Unavailable")}
            </dd>
          </dl>
          <details>
            <summary>Metric scope</summary>
            <p>
              Solved costs count actions until first goal arrival. Only
              independently valid solved runs enter cost comparisons. Sharing
              uses actual delivered recipient payloads; spatial and space-time
              definitions are stored separately. Historical proxy values are not
              promoted to measured observations.
            </p>
          </details>
          <h3>Agents · t={f?.tick ?? 0}</h3>
          <details>
            <summary>Bookmarks and notes</summary>
            <label>
              Bookmark note
              <input
                value={note}
                maxLength={240}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            <button
              disabled={!f}
              onClick={() => {
                const next = {
                  ...bookmarks,
                  [r.run_id]: [
                    ...(bookmarks[r.run_id] || []).slice(-99),
                    {
                      tick: f?.tick || 0,
                      note: note.trim() || "Bookmark",
                      agent: selectedAgent,
                    },
                  ],
                };
                setBookmarks(next);
                localStorage.setItem("mapf-bookmarks", JSON.stringify(next));
                setNote("");
              }}
            >
              Bookmark this tick
            </button>
            <p className="muted">
              Latest 100 notes per run, saved in this browser.
            </p>
            <ul>
              {(bookmarks[r.run_id] || []).map((b, i) => (
                <li key={i}>
                  <button
                    onClick={() => {
                      onSeek?.(b.tick);
                      onSelectAgent(b.agent);
                    }}
                  >
                    t={b.tick} · {b.note}
                  </button>
                  <button
                    aria-label={`Delete bookmark ${i + 1}`}
                    onClick={() => {
                      const next = {
                        ...bookmarks,
                        [r.run_id]: bookmarks[r.run_id].filter(
                          (_, j) => j !== i,
                        ),
                      };
                      setBookmarks(next);
                      localStorage.setItem(
                        "mapf-bookmarks",
                        JSON.stringify(next),
                      );
                    }}
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          </details>
          <div className="table-scroll">
            <table>
              <caption className="sr-only">
                Exact agent state at the selected tick
              </caption>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Position</th>
                  <th>Goal</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(f?.positions || {}).map(([id, pos], i) => (
                  <tr key={id} aria-selected={selectedAgent === id}>
                    <td>
                      <button
                        className="agent-select"
                        onClick={() => onSelectAgent(id)}
                        style={{
                          borderLeft: `4px solid ${getAgentColorHex(i)}`,
                        }}
                      >
                        {id}
                      </button>
                    </td>
                    <td>{pos.join(",")}</td>
                    <td>{f?.targets[id]?.join(",")}</td>
                    <td>{f?.statuses[id]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {selectedAgent && (
            <section className="card">
              <h3>{selectedAgent}</h3>
              <p>
                Tokens: {f?.tokens[selectedAgent] ?? "Unavailable at this tick"}
              </p>
              <details>
                <summary>Recorded local observation</summary>
                <pre tabIndex={0}>
                  {JSON.stringify(
                    f?.local_observations?.[selectedAgent] ??
                      "Unavailable at this tick",
                    null,
                    2,
                  )}
                </pre>
              </details>
              <p>Goal: {f?.targets[selectedAgent]?.join(", ")}</p>
              <p>
                Recorded local observations:{" "}
                {f?.local_observations ? "Available in bundle" : "Unavailable"}
              </p>
              <details>
                <summary>Recorded current plan and commitments</summary>
                <pre tabIndex={0}>
                  {JSON.stringify(
                    {
                      planned_path:
                        f?.planned_paths[selectedAgent] ??
                        "Unavailable at this tick",
                      commitments:
                        f?.commitments?.[selectedAgent] ??
                        "Unavailable at this tick",
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              <details>
                <summary>Executed trajectory (hindsight)</summary>
                <pre tabIndex={0}>
                  {JSON.stringify(r.paths[selectedAgent], null, 2)}
                </pre>
              </details>
            </section>
          )}
          <h3>Validation violations</h3>
          {(r.validation?.errors.length || 0) === 0 ? (
            <p className="muted">No validator errors recorded.</p>
          ) : (
            <ul>
              {r.validation?.errors.map((e, i) => (
                <li key={i}>
                  <button onClick={() => onSeek?.(Number(e.time_step || 0))}>
                    {String(e.error_type)} · {String(e.agent_a)} · t=
                    {String(e.time_step ?? "n/a")}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <h3>Negotiation sessions</h3>
          <p className="muted">
            Recorded messages, offers, response decisions, transfers and safety
            actions. Expand an event for its measured components and signed
            balances, when recorded.
          </p>
          <label>
            Session
            <select
              value={session}
              onChange={(e) => {
                setSession(e.target.value);
                setPage(0);
              }}
            >
              <option value="">All sessions and world events</option>
              {sessions.map((e) => (
                <option key={String(e.session_id)} value={String(e.session_id)}>
                  t={String(e.tick)} · {String(e.initiator_id)} /{" "}
                  {String(e.opponent_id)} · {String(e.outcome)}
                </option>
              ))}
            </select>
          </label>
          {
            <>
              <label>
                Event filter
                <select
                  value={filter}
                  onChange={(e) => {
                    setFilter(e.target.value);
                    setPage(0);
                  }}
                >
                  <option value="all">All session events</option>
                  <option value="BID">Offers</option>
                  <option value="NEGO_SESSION">Outcome</option>
                  <option value="MESSAGE">Delivered messages</option>
                  <option value="TOKEN_TRANSFER">Token transfers</option>
                  <option value="SAFETY">Safety actions</option>
                </select>
              </label>
              <p className="muted">
                Page {page + 1} · {selectedEvents.length} matching events · 100
                per page.
              </p>
              <div className="button-row">
                <button disabled={!page} onClick={() => setPage((p) => p - 1)}>
                  Previous events
                </button>
                <button
                  disabled={(page + 1) * 100 >= selectedEvents.length}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next events
                </button>
              </div>
              {selectedEvents
                .slice(page * 100, (page + 1) * 100)
                .map((e, i) => (
                  <details key={i}>
                    <summary>
                      {typeof e.tick === "number"
                        ? `t=${e.tick}`
                        : "Run metadata"}{" "}
                      · {String(e.event_type)} #{String(e.sequence)}
                    </summary>
                    {typeof e.tick === "number" && (
                      <button onClick={() => onSeek?.(Number(e.tick))}>
                        Jump to t={e.tick}
                      </button>
                    )}
                    <pre tabIndex={0}>{JSON.stringify(e, null, 2)}</pre>
                  </details>
                ))}
            </>
          }
          <h3>Contracts at this transition</h3>
          {!f?.contracts.length ? (
            <p className="muted">No signed contract recorded on this frame.</p>
          ) : (
            <pre tabIndex={0}>{JSON.stringify(f.contracts, null, 2)}</pre>
          )}
          <p className="muted">
            Full trace records current plans and opponent reservations after
            each move, plus the observation timestamp used for decisions.
            Initial plans and observations are shown only when captured by the
            recorded version.
          </p>
        </>
      )}
    </aside>
  );
}
