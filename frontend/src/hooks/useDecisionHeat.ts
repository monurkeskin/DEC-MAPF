import { useState } from "react";
import type { FrameSnapshot } from "../api/types";

export function useDecisionHeat(
  frame: FrameSnapshot | null,
  agent: string | null,
  enabled: boolean,
) {
  const [decision, setDecision] = useState("");
  const [requestedOffset, setOffset] = useState(-1);
  const records = (frame?.local_heat || []).filter(
    (record) => record.agent_id === agent,
  );
  const selected =
    records.find((record) => record.record_id === decision) || records.at(-1);
  const offset =
    selected && requestedOffset < selected.fields.length ? requestedOffset : -1;
  const grid =
    enabled && selected?.status === "recorded"
      ? offset < 0
        ? selected.aggregate
        : selected.fields[offset] || {}
      : undefined;
  const select = (id: string) => {
    setDecision(id);
    setOffset(-1);
  };
  return { records, selected, offset, grid, select, setOffset };
}
