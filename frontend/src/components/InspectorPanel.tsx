import { useInspectorEvents } from "../hooks/useInspectorEvents";
import { useReplayBookmarks } from "../hooks/useReplayBookmarks";
import { NegotiationEvents } from "./NegotiationEvents";
import { ValidationViolations } from "./ValidationViolations";
import { SelectedAgentEvidence } from "./SelectedAgentEvidence";
import { AgentStateTable } from "./AgentStateTable";
import { ReplayBookmarks } from "./ReplayBookmarks";
import { RunMetrics } from "./RunMetrics";
import type { FrameSnapshot, SolverRunResult } from "../api/types";
interface Props {
  runResult: SolverRunResult | null;
  currentFrame?: FrameSnapshot;
  selectedAgent: string | null;
  onSelectAgent: (id: string | null) => void;
  onSeek?: (tick: number) => void;
}
export function InspectorPanel({
  runResult: r,
  currentFrame: f,
  selectedAgent,
  onSelectAgent,
  onSeek,
}: Props) {
  const bookmarks = useReplayBookmarks();
  const events = useInspectorEvents(r);
  return (
    <aside className="inspector-panel" aria-label="Run inspector">
      <h2>Inspect evidence</h2>
      {!r ? (
        <p className="muted">
          Run a scenario or load a saved replay to inspect its recorded state.
        </p>
      ) : (
        <>
          <RunMetrics result={r} />
          <h3>Agents · t={f?.tick ?? 0}</h3>
          <ReplayBookmarks
            model={bookmarks}
            runId={r.run_id}
            frame={f}
            {...{ selectedAgent, onSelectAgent, onSeek }}
          />
          <AgentStateTable frame={f} {...{ selectedAgent, onSelectAgent }} />
          {selectedAgent && (
            <SelectedAgentEvidence
              frame={f}
              result={r}
              selectedAgent={selectedAgent}
            />
          )}
          <ValidationViolations result={r} onSeek={onSeek} />
          <NegotiationEvents model={events} onSeek={onSeek} />
          <h3>Contracts at this transition</h3>
          {!f?.contracts.length ? (
            <p className="muted">No signed contract recorded on this frame.</p>
          ) : (
            <pre tabIndex={0}>{JSON.stringify(f.contracts, null, 2)}</pre>
          )}
          <p className="muted">
            Full trace records current plans and opponent reservations after
            each move, plus the observation timestamp used for decisions.
            Initial plans and observations are shown only when captured by the
            recorded version.
          </p>
        </>
      )}
    </aside>
  );
}
