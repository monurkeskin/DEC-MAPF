import { post } from "../api/client";
import type { RunDetail } from "../api/types";
import { saveJson } from "../artifacts";

type Props = {
  run: RunDetail | null;
  tick: number;
  importReplay: (file: File) => Promise<void>;
  setNotice: (message: string) => void;
  reportError: (error: unknown) => void;
};
export function ArtifactPanel({
  run,
  tick,
  importReplay,
  setNotice,
  reportError,
}: Props) {
  return (
    <section className="content-scroll">
      <h1>Portable research artifacts</h1>
      <p>
        Bundles contain the scenario, exact inputs, paths, replay, independent
        check, source hashes and environment. Checksums detect modification;
        they do not authenticate an unknown source.
      </p>
      <label>
        Import checked replay bundle
        <input
          type="file"
          accept=".json,application/json"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) importReplay(f);
            e.target.value = "";
          }}
        />
      </label>
      {run ? (
        <>
          <h2>{run.metadata.solver_name}</h2>
          <p>{run.metadata.run_id}</p>
          <div className="export-grid">
            {[
              ["json", "Complete bundle"],
              ["html", "Offline HTML replay"],
              ["csv", "Metrics CSV"],
              ["tex", "LaTeX table"],
              ["svg", `SVG at tick ${tick}`],
            ].map(([ext, label]) => (
              <a
                className="button"
                href={`/api/v1/runs/${run.metadata.run_id}/export/${ext}?tick=${tick}`}
                download
                key={ext}
              >
                {label}
              </a>
            ))}
          </div>
          <details open>
            <summary>Provenance and timing boundaries</summary>
            <pre tabIndex={0}>
              {JSON.stringify(
                {
                  provenance: run.metadata.provenance,
                  timings: run.metadata.timings,
                  trace: run.metadata.trace,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      ) : (
        <p className="empty">
          Load a saved run from the library to export its evidence.
        </p>
      )}
      <h2>Existing archives</h2>
      <p>
        Legacy JSON/CSV can be preserved separately with its original content
        hash. Missing seeds, revisions and trajectory validation remain unknown
        and are excluded from verified comparisons.
      </p>
      <label>
        Quarantine legacy text archive
        <input
          type="file"
          accept=".csv,.json,.jsonl"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f)
              try {
                if (f.size > 1000000)
                  throw new Error("Legacy import limit is 1 MB");
                const receipt = await post("/archives/quarantine", {
                  name: f.name,
                  content: await f.text(),
                });
                saveJson("legacy-import-receipt.json", receipt);
                setNotice(
                  "Legacy archive preserved with explicit provenance gaps",
                );
              } catch (err) {
                reportError(err);
              }
            e.target.value = "";
          }}
        />
      </label>
    </section>
  );
}
