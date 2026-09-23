import type { FrameSnapshot } from "../api/types";
import { getAgentColorHex } from "./agentColors";
export function AgentStateTable({
  frame: f,
  selectedAgent,
  onSelectAgent,
}: {
  frame?: FrameSnapshot;
  selectedAgent: string | null;
  onSelectAgent: (id: string) => void;
}) {
  return (
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
  );
}
