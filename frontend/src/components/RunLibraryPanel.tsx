import { useState } from "react";
import { post } from "../api/client";
import type { useRunLibrary } from "../hooks/useRunLibrary";

type Props = {
  library: ReturnType<typeof useRunLibrary>;
  select: (id: string) => void;
  reportError: (error: unknown) => void;
  open: boolean;
};

export function RunLibraryPanel({ library, select, reportError, open }: Props) {
  const [draft, setDraft] = useState(library.filters);
  return (
    <details open={open}>
      <summary>
        Saved runs ({library.items.length} / {library.total})
      </summary>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          library.setFilters({ ...draft });
        }}
      >
        <label>
          Library solver
          <select
            value={draft.solver_name || ""}
            onChange={(e) =>
              setDraft({ ...draft, solver_name: e.target.value })
            }
          >
            <option value="">All solvers</option>
            {library.solverNames.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <label>
          Library validation
          <select
            value={draft.validation_status || ""}
            onChange={(e) =>
              setDraft({ ...draft, validation_status: e.target.value })
            }
          >
            <option value="">All validation states</option>
            {library.statuses.map((status) => (
              <option key={status}>{status}</option>
            ))}
          </select>
        </label>
        <label>
          Library experiment ID
          <input
            value={draft.experiment_id || ""}
            onChange={(e) =>
              setDraft({ ...draft, experiment_id: e.target.value })
            }
            placeholder="All experiments"
            maxLength={160}
          />
        </label>
        <button type="submit">Apply library filters</button>
        <button
          type="button"
          onClick={() => {
            setDraft({});
            library.setFilters({});
          }}
        >
          Clear library filters
        </button>
      </form>
      <button
        disabled={library.loading}
        onClick={() => library.refresh().catch(reportError)}
      >
        Refresh library
      </button>
      {library.loading && <p role="status">Loading saved runs…</p>}
      {!library.loading && !library.items.length && (
        <p>No runs match these filters.</p>
      )}
      {library.items.map((run) => (
        <div className="library-row" key={run.run_id}>
          <button onClick={() => select(run.run_id)}>
            {run.solver_name}
            <small>
              {run.validation_status} · {run.run_id.slice(-8)}
            </small>
          </button>
          <button
            aria-label={`${run.pinned ? "Unpin" : "Pin"} ${run.run_id}`}
            onClick={() =>
              post(`/runs/${run.run_id}/pin?pinned=${!run.pinned}`, {})
                .then(library.refresh)
                .catch(reportError)
            }
          >
            {run.pinned ? "★" : "☆"}
          </button>
        </div>
      ))}
      {library.next && (
        <button
          disabled={library.loading}
          onClick={() => library.loadMore().catch(reportError)}
        >
          Load more runs
        </button>
      )}
      <p className="hint">
        Loaded runs are also available in Compare. Refresh to include new
        arrivals.
      </p>
    </details>
  );
}
