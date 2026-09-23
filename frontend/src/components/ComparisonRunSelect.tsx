import type { RunSummary } from "../api/types";
export function ComparisonRunSelect({
  label,
  value,
  onChange,
  runs,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  runs: RunSummary[];
}) {
  return (
    <label>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select a saved run</option>
        {value && !runs.some((run) => run.run_id === value) && (
          <option value={value}>
            Selected run · {value.slice(-8)} (outside current library filter)
          </option>
        )}
        {runs.map((r) => (
          <option key={r.run_id} value={r.run_id}>
            {r.solver_name} · {r.run_id.slice(-8)}
          </option>
        ))}
      </select>
    </label>
  );
}
