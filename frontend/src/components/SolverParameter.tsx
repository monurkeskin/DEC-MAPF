import type { Dispatch, SetStateAction } from "react";
import type { ParameterDescriptor, JobSubmissionRequest } from "../api/types";
type Props = {
  p: ParameterDescriptor;
  options: JobSubmissionRequest;
  setOptions: Dispatch<SetStateAction<JobSubmissionRequest>>;
};
function NumericParameter({ p, options, setOptions }: Props) {
  return (
    <input
      type="number"
      min={p.min_value}
      max={p.max_value}
      step={p.step || 1}
      value={
        options[p.name] === null ||
        (options[p.name] === undefined && p.default === null)
          ? ""
          : Number(options[p.name] ?? p.default)
      }
      placeholder={p.default === null ? "Follow FoV width" : undefined}
      onChange={(e) =>
        setOptions((o) => ({
          ...o,
          [p.name]:
            e.target.value === "" && p.default === null
              ? null
              : Number(e.target.value),
        }))
      }
    />
  );
}
function SelectParameter({ p, options, setOptions }: Props) {
  return (
    <select
      value={String(options[p.name] ?? p.default)}
      onChange={(e) => setOptions((o) => ({ ...o, [p.name]: e.target.value }))}
    >
      {p.options?.map((v) => (
        <option key={v} value={v}>
          {{ SC: "SC — Standard", DC: "DC — Dynamic", ZC: "ZC — Zero" }[v] || v}
        </option>
      ))}
    </select>
  );
}
export function SolverParameter(props: Props) {
  const p = props.p;
  return (
    <label title={p.description}>
      {p.display_name}
      {p.param_type === "select" ? (
        <SelectParameter {...props} />
      ) : (
        <NumericParameter {...props} />
      )}
    </label>
  );
}
