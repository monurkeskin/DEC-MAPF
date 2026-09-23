import type { FrameSnapshot } from "../api/types";
import type { useReplayBookmarks } from "../hooks/useReplayBookmarks";
export function ReplayBookmarks({
  model,
  runId,
  frame: f,
  selectedAgent,
  onSelectAgent,
  onSeek,
}: {
  model: ReturnType<typeof useReplayBookmarks>;
  runId: string;
  frame?: FrameSnapshot;
  selectedAgent: string | null;
  onSelectAgent: (id: string | null) => void;
  onSeek?: (tick: number) => void;
}) {
  const { note, setNote, bookmarks, setBookmarks } = model;
  return (
    <details>
      <summary>Bookmarks and notes</summary>
      <label>
        Bookmark note
        <input
          value={note}
          maxLength={240}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      <button
        disabled={!f}
        onClick={() => {
          const next = {
            ...bookmarks,
            [runId]: [
              ...(bookmarks[runId] || []).slice(-99),
              {
                tick: f?.tick || 0,
                note: note.trim() || "Bookmark",
                agent: selectedAgent,
              },
            ],
          };
          setBookmarks(next);
          localStorage.setItem("mapf-bookmarks", JSON.stringify(next));
          setNote("");
        }}
      >
        Bookmark this tick
      </button>
      <p className="muted">Latest 100 notes per run, saved in this browser.</p>
      <ul>
        {(bookmarks[runId] || []).map((b, i) => (
          <li key={i}>
            <button
              onClick={() => {
                onSeek?.(b.tick);
                onSelectAgent(b.agent);
              }}
            >
              t={b.tick} · {b.note}
            </button>
            <button
              aria-label={`Delete bookmark ${i + 1}`}
              onClick={() => {
                const next = {
                  ...bookmarks,
                  [runId]: bookmarks[runId].filter((_, j) => j !== i),
                };
                setBookmarks(next);
                localStorage.setItem("mapf-bookmarks", JSON.stringify(next));
              }}
            >
              Delete
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}
