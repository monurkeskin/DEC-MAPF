import type { DecisionHeatRecord } from "../api/types";

export function DecisionHeatPanel({
  records,
  selected,
  offset,
  omitted,
  onSelect,
  onOffset,
}: {
  records: DecisionHeatRecord[];
  selected?: DecisionHeatRecord;
  offset: number;
  omitted: number;
  onSelect: (id: string) => void;
  onOffset: (offset: number) => void;
}) {
  if (!selected)
    return (
      <p role="status">
        No recorded heat decision for this agent and frame. Select an agent and
        a frame containing a HeatMap negotiation. Older or reduced recordings
        may not contain this layer.
        {omitted > 0
          ? ` ${omitted} heat records omitted by the recording budget.`
          : ""}
      </p>
    );
  const grid = offset < 0 ? selected.aggregate : selected.fields[offset] || {};
  return (
    <fieldset className="decision-heat">
      <legend>Actual local decision heat</legend>
      <label>
        Recorded heat decision
        <select
          aria-label="Recorded heat decision"
          value={selected.record_id}
          onChange={(e) => onSelect(e.target.value)}
        >
          {records.map((record) => (
            <option key={record.record_id} value={record.record_id}>
              {record.agent_id} · t={record.tick} · opponent{" "}
              {record.opponent_id ?? "none"} · {record.session_id}
            </option>
          ))}
        </select>
      </label>
      <p role="status">
        Decision t={selected.tick}; agent {selected.agent_id}; opponent{" "}
        {selected.opponent_id ?? "none"} excluded. Captured strategy weights
        before movement. Displayed with the following post-move frame.
      </p>
      {selected.status === "budget_exhausted" ? (
        <p role="alert">
          Local heat recording budget exhausted. This decision required{" "}
          {selected.required_entries} values. Its heat values are unavailable.
        </p>
      ) : (
        <>
          <label>
            Heat time slice
            <select
              aria-label="Heat time slice"
              value={offset}
              onChange={(e) => onOffset(Number(e.target.value))}
            >
              <option value={-1}>Aggregate planning weights</option>
              {selected.fields.map((_, i) => (
                <option key={i} value={i}>
                  Relative t+{i} · absolute t={selected.tick + i}
                </option>
              ))}
            </select>
          </label>
          <p className="muted">
            {Object.keys(grid).length} nonzero cells. Values are sums of the
            recorded congestion kernel; absent cells have zero weight. Initial
            planning does not compute this field.
          </p>
          <details>
            <summary>Recorded heat values</summary>
            <table aria-label="Recorded heat values">
              <thead>
                <tr>
                  <th>Cell x-y</th>
                  <th>Weight</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(grid)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([cell, value]) => (
                    <tr key={cell}>
                      <td>{cell}</td>
                      <td>{value}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </details>
        </>
      )}
      {omitted > 0 && (
        <p role="status">
          {omitted} heat records were partially or fully omitted by the
          recording budget at this step.
        </p>
      )}
    </fieldset>
  );
}
