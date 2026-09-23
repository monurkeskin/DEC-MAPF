import type { Comparison } from "../api/types";
import { saveJson } from "../artifacts";
export function CohortEvidence({ comparison }: { comparison: Comparison }) {
  return (
    <>
      <table>
        <caption>Right minus left · common-solved pairs</caption>
        <thead>
          <tr>
            <th>Metric</th>
            <th>Mean delta</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(comparison.means_right_minus_left).map(([m, v]) => (
            <tr key={m}>
              <th>{m}</th>
              <td>{v == null ? "Unavailable" : v.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>{comparison.uncertainty}</p>
      <p className="muted">{comparison.denominator_policy}</p>
      <details>
        <summary>Effective input differences and pair records</summary>
        <pre tabIndex={0}>{JSON.stringify(comparison.rows, null, 2)}</pre>
      </details>
      <button onClick={() => saveJson("decmapf-comparison.json", comparison)}>
        Export cohort JSON
      </button>
    </>
  );
}
