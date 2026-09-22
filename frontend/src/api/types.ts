import type { components } from "./generated";
export type Point2D = components["schemas"]["Point2D"];
export type FrameSnapshot = components["schemas"]["FrameSnapshot"];
export type DecisionHeatRecord = components["schemas"]["DecisionHeatRecord"];
export type SolverRunResult = components["schemas"]["SolverRunResult"];
export type JobSubmissionRequest =
  components["schemas"]["JobSubmissionRequest"];
export type JobStatusResponse = components["schemas"]["JobStatusResponse"];
export type JobEvent = components["schemas"]["JobEvent"];
export type ScenarioInput = components["schemas"]["ScenarioValidateRequest"];
export type ParameterDescriptor = Omit<
  components["schemas"]["ParameterDescriptor"],
  "name"
> & { name: keyof JobSubmissionRequest };
export type SolverCapability = Omit<
  components["schemas"]["SolverCapability"],
  "parameters"
> & { parameters: ParameterDescriptor[] };
export type ScenarioSummary = components["schemas"]["ScenarioSummary"];
export type ScenarioDetail = components["schemas"]["ScenarioDetail"];
export type RunSummary = components["schemas"]["RunSummary"];
export type RunPage = components["schemas"]["RunPage"];
export type RunDetail = components["schemas"]["RunDetail"];
export type Plan = components["schemas"]["PlanResponse"];
export type ExperimentAnalysis = components["schemas"]["AnalysisResponse"];
export interface Comparison {
  paired: number;
  common_solved: number;
  excluded_from_costs: number;
  unmatched: { left: number; right: number };
  means_right_minus_left: Record<string, number | null>;
  uncertainty: string;
  denominator_policy: string;
  rows: {
    unit_id: string;
    left_run_id: string;
    right_run_id: string;
    common_solved: boolean;
    differences: Record<string, unknown>;
    deltas_right_minus_left: Record<string, number | null>;
  }[];
}
