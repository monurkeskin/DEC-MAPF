import type { ScenarioDetail } from "../api/types";
export function AgentCoordinateEditor({
  scenario,
  onChange,
}: {
  scenario: ScenarioDetail;
  onChange: (scenario: ScenarioDetail) => void;
}) {
  const move = (
    agent: string,
    kind: "starts" | "goals",
    axis: number,
    value: number,
  ) => {
    const positions = { ...scenario[kind] },
      position = [...positions[agent]] as [number, number];
    position[axis] = value;
    positions[agent] = position;
    onChange({ ...scenario, [kind]: positions });
  };
  return (
    <div className="table-scroll">
      <table>
        <caption>Agent coordinate editor</caption>
        <thead>
          <tr>
            <th>Agent</th>
            <th>Start x/y</th>
            <th>Goal x/y</th>
          </tr>
        </thead>
        <tbody>
          {Object.keys(scenario.starts).map((id) => (
            <tr key={id}>
              <th>{id}</th>
              {(["starts", "goals"] as const).map((kind) => (
                <td key={kind}>
                  {[0, 1].map((axis) => (
                    <input
                      key={axis}
                      className="coord-input"
                      aria-label={`${id} ${kind} ${axis === 0 ? "x" : "y"}`}
                      type="number"
                      value={scenario[kind][id][axis]}
                      onChange={(e) =>
                        move(id, kind, axis, Number(e.target.value))
                      }
                    />
                  ))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
