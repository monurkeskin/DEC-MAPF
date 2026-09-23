import { useState } from "react";
import type { Plan } from "../api/types";
export function useBatchDraft() {
  const [batchText, setBatchText] = useState(""),
    [batchPlan, setBatchPlan] = useState<Plan | null>(null),
    [batchId, setBatchId] = useState("");
  return {
    batchText,
    setBatchText,
    batchPlan,
    setBatchPlan,
    batchId,
    setBatchId,
  };
}
