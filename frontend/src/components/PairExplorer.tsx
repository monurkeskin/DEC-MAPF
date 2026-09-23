import { useState } from "react";
import type { ExperimentAnalysis } from "../api/types";

/** Display-only exploration. Statistical summaries and export cohort stay authoritative. */
export function PairExplorer({ analysis }: { analysis: ExperimentAnalysis }) {
  const [search, setSearch] = useState("");
  const [solvedOnly, setSolvedOnly] = useState(false);
  const [sort, setSort] = useState("unit");
  const [selected, setSelected] = useState("");
  const pairs = analysis.pairs
    .filter(
      (p) =>
        p.sampling_unit.toLowerCase().includes(search.toLowerCase()) &&
        (!solvedOnly || p.common_solved),
    )
    .sort((a, b) =>
      sort === "delta"
        ? (b.delta_right_minus_left ?? -Infinity) -
          (a.delta_right_minus_left ?? -Infinity)
        : a.sampling_unit.localeCompare(b.sampling_unit),
    );
  const plotted = pairs
    .filter((p) => p.delta_right_minus_left !== null)
    .slice(0, 100);
  const extent = Math.max(
    1,
    ...plotted.map((p) => Math.abs(p.delta_right_minus_left!)),
  );
  const x = (value: number) => 300 + (value / extent) * 250;
  const selectedPair = pairs.find((p) => p.left_trial === selected);
  return (
    <section className="pair-explorer" aria-label="Paired outcome explorer">
      <h3>Explore paired outcomes</h3>
      <p className="muted">
        Display filters do not change the statistical summaries or canonical
        export cohort. Cost differences use common solved pairs; missing costs
        are unavailable.
      </p>
      <div className="two-cols">
        <label>
          Find sampling unit
          <input value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>
        <label>
          Pair order
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="unit">Sampling unit</option>
            <option value="delta">Cost difference, descending</option>
          </select>
        </label>
      </div>
      <label>
        <input
          type="checkbox"
          checked={solvedOnly}
          onChange={(e) => setSolvedOnly(e.target.checked)}
        />
        Show common solved pairs only
      </label>
      <p role="status" data-testid="pair-display-count">
        Showing {pairs.length} of {analysis.pairs.length} pairs;{" "}
        {pairs.filter((p) => p.common_solved).length} common solved. Chart shows
        the first {plotted.length} available costs (maximum 100).
      </p>
      {plotted.length > 0 && (
        <svg
          viewBox={`0 0 600 ${40 + plotted.length * 18}`}
          role="img"
          aria-label="Paired cost differences, right minus left"
        >
          <title>
            Cost difference: {analysis.right_solver} minus{" "}
            {analysis.left_solver}. Positive means higher cost for the right
            method.
          </title>
          <text x="10" y="14" fill="currentColor" fontSize="11">
            Right method lower cost
          </text>
          <text x="420" y="14" fill="currentColor" fontSize="11">
            Right method higher cost
          </text>
          <line
            x1="300"
            x2="300"
            y1="20"
            y2={30 + plotted.length * 18}
            stroke="currentColor"
          />
          {plotted.map((p, i) => (
            <g
              key={p.left_trial}
              tabIndex={0}
              role="button"
              aria-label={`${p.sampling_unit}: cost difference ${p.delta_right_minus_left}`}
              onClick={() => setSelected(p.left_trial)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setSelected(p.left_trial);
                }
              }}
            >
              <title>
                {p.sampling_unit}: {p.delta_right_minus_left} actions
              </title>
              <line
                x1="300"
                x2={x(p.delta_right_minus_left!)}
                y1={30 + i * 18}
                y2={30 + i * 18}
                stroke="currentColor"
                strokeWidth="2"
              />
              <circle
                cx={x(p.delta_right_minus_left!)}
                cy={30 + i * 18}
                r={p.left_trial === selected ? 6 : 4}
                fill={p.delta_right_minus_left! >= 0 ? "#fbbf24" : "#22d3ee"}
                stroke="currentColor"
              />
            </g>
          ))}
        </svg>
      )}
      {selectedPair && (
        <p role="status">
          Selected {selectedPair.sampling_unit}:{" "}
          {selectedPair.delta_right_minus_left ?? "unavailable"} actions (right
          − left). Trials {selectedPair.left_trial} / {selectedPair.right_trial}
          .
        </p>
      )}
      <div className="pair-table">
        <table aria-label="Paired outcomes">
          <thead>
            <tr>
              <th>Sampling unit</th>
              <th>Both solved</th>
              <th>Cost difference (actions)</th>
            </tr>
          </thead>
          <tbody>
            {pairs.slice(0, 500).map((p) => (
              <tr key={p.left_trial} aria-selected={p.left_trial === selected}>
                <td>
                  <button onClick={() => setSelected(p.left_trial)}>
                    {p.sampling_unit}
                  </button>
                </td>
                <td>{p.common_solved ? "Yes" : "No"}</td>
                <td>{p.delta_right_minus_left ?? "Unavailable"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pairs.length > 500 && (
        <p>
          Table displays the first 500 pairs. Narrow the display filter or use
          the complete canonical export.
        </p>
      )}
    </section>
  );
}
