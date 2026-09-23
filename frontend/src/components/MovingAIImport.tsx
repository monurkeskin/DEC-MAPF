import { useState } from "react";
import { post } from "../api/client";
import type { ScenarioDetail } from "../api/types";
export function MovingAIImport({
  setting,
  onSaved,
  onError,
}: {
  setting: ScenarioDetail["setting"];
  onSaved: (scenario: ScenarioDetail) => void;
  onError: (error: unknown) => void;
}) {
  const [mapText, setMapText] = useState(""),
    [scenText, setScenText] = useState(""),
    [count, setCount] = useState(4);
  return (
    <details>
      <summary>MovingAI map and scenario import</summary>
      <label>
        Map text
        <textarea
          value={mapText}
          onChange={(e) => setMapText(e.target.value)}
        />
      </label>
      <label>
        Scenario text
        <textarea
          value={scenText}
          onChange={(e) => setScenText(e.target.value)}
        />
      </label>
      <label>
        First N agents
        <input
          type="number"
          min="1"
          max="100"
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
        />
      </label>
      <button
        onClick={async () => {
          try {
            onSaved(
              await post<ScenarioDetail>("/scenarios/import-movingai", {
                map_text: mapText,
                scenario_text: scenText,
                agent_count: count,
                setting: setting,
                name: "MovingAI import",
              }),
            );
          } catch (e) {
            onError(e);
          }
        }}
      >
        Import and save MovingAI
      </button>
    </details>
  );
}
