import { useEffect } from "react";
interface Props {
  indexLabel?: string;
  currentTick: number;
  totalTicks: number;
  isPlaying: boolean;
  speed: number;
  onSeek: (tick: number) => void;
  onTogglePlay: () => void;
  onChangeSpeed: (speed: number) => void;
  onJumpToFirstViolation?: () => void;
}
export function TimelineScrubber(p: Props) {
  useEffect(() => {
    if (!p.isPlaying) return;
    if (p.currentTick >= p.totalTicks) {
      p.onTogglePlay();
      return;
    }
    const timer = window.setTimeout(
      () => p.onSeek(Math.min(p.totalTicks, p.currentTick + 1)),
      400 / p.speed,
    );
    return () => window.clearTimeout(timer);
  }, [p]);
  return (
    <div className="scrubber-bar" aria-label="Replay controls">
      <button onClick={() => p.onSeek(0)} disabled={!p.currentTick}>
        Start
      </button>
      <button
        onClick={() => p.onSeek(Math.max(0, p.currentTick - 1))}
        disabled={!p.currentTick}
      >
        Back
      </button>
      <button onClick={p.onTogglePlay} disabled={!p.totalTicks}>
        {p.isPlaying ? "Pause replay" : "Play replay"}
      </button>
      <button
        onClick={() => p.onSeek(Math.min(p.totalTicks, p.currentTick + 1))}
        disabled={p.currentTick >= p.totalTicks}
      >
        Step
      </button>
      <label className="timeline-label">
        Tick
        <input
          aria-label="Replay tick"
          type="range"
          min="0"
          max={p.totalTicks}
          value={p.currentTick}
          onChange={(e) => p.onSeek(Number(e.target.value))}
        />
      </label>
      <output data-testid="replay-tick">
        {p.indexLabel || "t"} = {p.currentTick} / {p.totalTicks}
      </output>
      <label>
        Speed
        <select
          value={p.speed}
          onChange={(e) => p.onChangeSpeed(Number(e.target.value))}
        >
          {[0.5, 1, 2, 4].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <button
        onClick={p.onJumpToFirstViolation}
        disabled={!p.onJumpToFirstViolation}
      >
        First violation
      </button>
    </div>
  );
}
