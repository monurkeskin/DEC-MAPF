import { useState } from "react";
import type { ScenarioDetail } from "../api/types";
import { parseScenarioDraft, scenarioDraftInput } from "../scenarioDraft";
export function ScenarioJsonEditor({
  scenario,
  onChange,
  onStatus,
  onError,
}: {
  scenario: ScenarioDetail;
  onChange: (scenario: ScenarioDetail) => void;
  onStatus: (message: string) => void;
  onError: (error: unknown) => void;
}) {
  const [jsonText, setJsonText] = useState("");
  return (
    <details>
      <summary>JSON import / keyboard obstacle editing</summary>
      <p>
        Import a scenario with dimensions, obstacles, starts, goals and setting.
        Coordinates use [x, y].
      </p>
      <textarea
        aria-label="Scenario JSON"
        value={jsonText}
        onChange={(e) => setJsonText(e.target.value)}
        placeholder="Paste scenario JSON"
      />
      <div className="button-row">
        <button
          onClick={() =>
            setJsonText(JSON.stringify(scenarioDraftInput(scenario), null, 2))
          }
        >
          Copy draft into editor
        </button>
        <button
          onClick={() => {
            try {
              onChange(parseScenarioDraft(jsonText));
              onStatus("Imported draft; validation required");
            } catch (e) {
              onError(e);
            }
          }}
        >
          Load JSON draft
        </button>
      </div>
    </details>
  );
}
