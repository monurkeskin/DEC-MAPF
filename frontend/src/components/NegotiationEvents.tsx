import type { useInspectorEvents } from "../hooks/useInspectorEvents";
export function NegotiationEvents({
  model,
  onSeek,
}: {
  model: ReturnType<typeof useInspectorEvents>;
  onSeek?: (tick: number) => void;
}) {
  const {
    session,
    setSession,
    filter,
    setFilter,
    page,
    setPage,
    sessions,
    selectedEvents,
  } = model;
  return (
    <>
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
            Page {page + 1} · {selectedEvents.length} matching events · 100 per
            page.
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
          {selectedEvents.slice(page * 100, (page + 1) * 100).map((e, i) => (
            <details key={i}>
              <summary>
                {typeof e.tick === "number" ? `t=${e.tick}` : "Run metadata"} ·{" "}
                {String(e.event_type)} #{String(e.sequence)}
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
    </>
  );
}
