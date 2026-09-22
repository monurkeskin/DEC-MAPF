import { useState } from "react";
import { GridViewport } from "./GridViewport";
import { TimelineScrubber } from "./TimelineScrubber";

/** Fixed interface fixtures for visual/keyboard review; no experiment is submitted. */
export function ComponentGallery() {
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [theme, setTheme] = useState("dark");
  return (
    <main className="card" data-theme={theme}>
      <h1>Workspace component examples</h1>
      <p>
        Deterministic interface fixtures. These are demonstration states, with
        no scientific results or jobs.
      </p>
      <a href="/">Return to workspace</a>
      <button
        onClick={() => {
          const next = theme === "dark" ? "light" : "dark";
          setTheme(next);
          document.documentElement.dataset.theme = next;
        }}
      >
        Switch theme
      </button>
      <section aria-label="Status examples">
        <h2>Execution and validation states</h2>
        {[
          "pending",
          "running",
          "completed",
          "failed",
          "cancelled",
          "interrupted",
          "disconnected",
          "valid_solution",
          "valid_prefix",
          "invalid",
          "not_checked",
        ].map((state) => (
          <p key={state}>
            <span className={`badge ${state}`}>{state}</span> — textual state
            remains available without color
          </p>
        ))}
      </section>
      <section aria-label="Control examples">
        <h2>Controls</h2>
        <label>
          Example setting
          <select>
            <option>Setting 4</option>
            <option>Setting 1</option>
          </select>
        </label>
        <button disabled>Unavailable action</button>
        <p role="status">Empty: no run selected</p>
        <p role="alert">Example validation error: duplicate starting cell</p>
      </section>
      <section
        aria-label="Renderer and timeline examples"
        style={{ height: 450 }}
      >
        <h2>Rectangular grid and discrete replay</h2>
        <GridViewport
          gridWidth={8}
          gridHeight={4}
          obstacles={[[4, 1]]}
          starts={{ a: [tick, 0] }}
          goals={{ a: [7, 0] }}
        />
      </section>
      <TimelineScrubber
        currentTick={tick}
        totalTicks={7}
        isPlaying={playing}
        speed={speed}
        onSeek={setTick}
        onTogglePlay={() => setPlaying(!playing)}
        onChangeSpeed={setSpeed}
      />
    </main>
  );
}
