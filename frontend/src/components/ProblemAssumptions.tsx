import type { Plan } from "../api/types";
export function ProblemAssumptions({
  semantics,
}: {
  semantics: NonNullable<Plan["plans"][number]["semantics"]>;
}) {
  return (
    <aside aria-label="Problem assumptions">
      <strong>Problem assumptions</strong>
      <p>{semantics.motion}</p>
      <p>
        Waiting before the goal:{" "}
        {semantics.wait_before_goal ? "allowed" : "forbidden"}. Goal policy:{" "}
        {semantics.goal_policy}. {semantics.goal_timing}
      </p>
      <p>
        {semantics.coordinates} {semantics.time_origin}
      </p>
      <p>Forbidden conflicts: {semantics.forbidden_conflicts.join("; ")}.</p>
      <p>{semantics.cost}</p>
      <p className="hint">{semantics.scope}</p>
    </aside>
  );
}
