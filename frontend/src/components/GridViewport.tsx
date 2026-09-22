import { useEffect, useRef, useState } from "react";
import type { FrameSnapshot, Point2D } from "../api/types";

import { getAgentColorHex } from "./agentColors";
export interface GridViewportProps {
  gridWidth: number;
  gridHeight: number;
  obstacles: number[][];
  starts: Record<string, number[]>;
  goals: Record<string, number[]>;
  currentFrame?: FrameSnapshot;
  paths?: Record<string, Point2D[]>;
  selectedAgent?: string | null;
  onSelectAgent?: (id: string | null) => void;
  onEditCell?: (x: number, y: number) => void;
  showPaths?: boolean;
  showHeat?: boolean;
  localHeatGrid?: Record<string, number>;
  showFov?: boolean;
  fovSize?: number;
  localView?: boolean;
  showReservations?: boolean;
}

/** Canvas 2D renderer. No React state updates occur inside the draw loop. */
export function GridViewport(props: GridViewportProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const propsRef = useRef(props);
  const view = useRef({ x: 0, y: 0, cell: 32, zoom: 1 });
  const drawRef = useRef<() => void>(() => {});
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const fitRef = useRef<() => void>(() => {});

  useEffect(() => {
    const canvas = canvasRef.current,
      host = hostRef.current;
    if (!canvas || !host) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      setUnavailable(true);
      return;
    }
    let scheduled = 0;
    const draw = () => {
      const p = propsRef.current,
        { x: ox, y: oy, cell, zoom } = view.current,
        size = cell * zoom;
      const rect = host.getBoundingClientRect(),
        dpr = Math.min(devicePixelRatio || 1, 2);
      if (
        canvas.width !== Math.round(rect.width * dpr) ||
        canvas.height !== Math.round(rect.height * dpr)
      ) {
        canvas.width = Math.round(rect.width * dpr);
        canvas.height = Math.round(rect.height * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, rect.height);
      ctx.fillStyle = "#0f172a";
      ctx.fillRect(0, 0, rect.width, rect.height);
      ctx.save();
      ctx.translate(ox, oy);
      const observation =
        p.currentFrame?.local_observations?.[p.selectedAgent || ""];
      const localPositions: Record<string, number[]> = {};
      if (observation) {
        localPositions[observation.agent_id] = observation.position;
        for (const message of observation.messages)
          if (message.points.length)
            localPositions[message.sender] = message.points[0];
      }
      const positions = p.localView
        ? localPositions
        : p.currentFrame?.positions || p.starts;
      const selected = positions[p.selectedAgent || ""];
      const radius = Math.floor((p.fovSize || 3) / 2);
      const visible = (_x: number, _y: number) => !p.localView || !!observation;
      ctx.lineWidth = 1;
      ctx.strokeStyle = "#334155";
      for (let y = 0; y < p.gridHeight; y++)
        for (let x = 0; x < p.gridWidth; x++) {
          ctx.fillStyle = visible(x, y) ? "#17243b" : "#05080f";
          ctx.fillRect(x * size, y * size, size, size);
          ctx.strokeRect(x * size, y * size, size, size);
        }
      ctx.font = `${Math.max(9, Math.min(12, size * 0.3))}px monospace`;
      ctx.fillStyle = "#cbd5e1";
      ctx.textAlign = "center";
      if (size >= 14) {
        for (let x = 0; x < p.gridWidth; x++)
          ctx.fillText(String(x), (x + 0.5) * size, -7);
        ctx.textAlign = "right";
        for (let y = 0; y < p.gridHeight; y++)
          ctx.fillText(String(y), -7, (y + 0.6) * size);
      }
      for (const [x, y] of p.obstacles)
        if (visible(x, y)) {
          ctx.fillStyle = "#64748b";
          ctx.fillRect(x * size + 1, y * size + 1, size - 2, size - 2);
        }
      if (p.showHeat && !p.localView)
        for (const [key, value] of Object.entries(
          p.currentFrame?.heat_grid || {},
        )) {
          const [x, y] = key.split("-").map(Number);
          ctx.fillStyle = `rgba(244,114,182,${Math.min(0.7, Number(value) * 0.15)})`;
          ctx.fillRect(x * size, y * size, size, size);
        }
      for (const [key, value] of Object.entries(p.localHeatGrid || {})) {
        const [x, y] = key.split("-").map(Number);
        ctx.fillStyle = `rgba(45,212,191,${Math.min(0.7, value * 0.15)})`;
        ctx.fillRect(x * size, y * size, size, size);
      }
      const ids = Object.keys(p.starts);
      ids.forEach((id, index) => {
        const color = getAgentColorHex(index),
          goal =
            !p.localView || id === p.selectedAgent ? p.goals[id] : undefined;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        if (goal && visible(goal[0], goal[1]))
          ctx.strokeRect(
            (goal[0] + 0.23) * size,
            (goal[1] + 0.23) * size,
            size * 0.54,
            size * 0.54,
          );
        const points = p.paths?.[id];
        if (p.showPaths && !p.localView && points?.length) {
          ctx.globalAlpha =
            p.selectedAgent && p.selectedAgent !== id ? 0.15 : 0.65;
          ctx.beginPath();
          points.forEach((point, i) => {
            if (i === 0)
              ctx.moveTo((point.x + 0.5) * size, (point.y + 0.5) * size);
            else ctx.lineTo((point.x + 0.5) * size, (point.y + 0.5) * size);
          });
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
      });
      if (p.localView && observation && p.showPaths) {
        for (const message of observation.messages) {
          ctx.strokeStyle = getAgentColorHex(ids.indexOf(message.sender));
          ctx.setLineDash([4, 3]);
          ctx.beginPath();
          message.points.forEach(([x, y], i) => {
            if (i === 0) ctx.moveTo((x + 0.5) * size, (y + 0.5) * size);
            else ctx.lineTo((x + 0.5) * size, (y + 0.5) * size);
          });
          ctx.stroke();
        }
        ctx.setLineDash([]);
      }
      if (p.showReservations && !p.localView) {
        const owners = Object.entries(p.currentFrame?.commitments || {});
        ctx.strokeStyle = "#fbbf24";
        ctx.lineWidth = 2;
        ctx.setLineDash([3, 3]);
        for (const [owner, records] of owners) {
          if (p.selectedAgent && owner !== p.selectedAgent) continue;
          for (const record of records) {
            const start = Number(record.start_tick),
              points = record.points;
            if (!Array.isArray(points) || !Number.isInteger(start)) continue;
            const tick = p.currentFrame?.tick || 0;
            points.forEach((point: unknown, i: number) => {
              if (
                !Array.isArray(point) ||
                point.length !== 2 ||
                start + i < tick
              )
                return;
              const [x, y] = point.map(Number);
              if (!Number.isFinite(x) || !Number.isFinite(y)) return;
              ctx.strokeRect(
                (x + 0.1) * size,
                (y + 0.1) * size,
                0.8 * size,
                0.8 * size,
              );
              ctx.fillStyle = "#fde68a";
              ctx.font = `${Math.min(10, size * 0.24)}px monospace`;
              ctx.textAlign = "left";
              if (size > 25)
                ctx.fillText(
                  "t" + (start + i),
                  (x + 0.12) * size,
                  (y + 0.23) * size,
                );
              const next = points[i + 1];
              if (Array.isArray(next) && next.length === 2) {
                ctx.beginPath();
                ctx.moveTo((x + 0.5) * size, (y + 0.5) * size);
                ctx.lineTo(
                  (Number(next[0]) + 0.5) * size,
                  (Number(next[1]) + 0.5) * size,
                );
                ctx.stroke();
              }
            });
          }
        }
        ctx.setLineDash([]);
      }
      if (p.showFov && selected) {
        ctx.fillStyle = "rgba(6,182,212,.08)";
        ctx.strokeStyle = "#67e8f9";
        ctx.setLineDash([4, 4]);
        ctx.fillRect(
          (selected[0] - radius) * size,
          (selected[1] - radius) * size,
          (2 * radius + 1) * size,
          (2 * radius + 1) * size,
        );
        ctx.strokeRect(
          (selected[0] - radius) * size,
          (selected[1] - radius) * size,
          (2 * radius + 1) * size,
          (2 * radius + 1) * size,
        );
        ctx.setLineDash([]);
      }
      ids.forEach((id, index) => {
        if (!p.localView && p.currentFrame?.statuses[id] === "disappeared")
          return;
        const pos = positions[id];
        if (!pos || !visible(pos[0], pos[1])) return;
        const [x, y] = pos;
        ctx.fillStyle = getAgentColorHex(index);
        ctx.beginPath();
        ctx.arc((x + 0.5) * size, (y + 0.5) * size, size * 0.3, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = p.selectedAgent === id ? "#ffffff" : "#111827";
        ctx.lineWidth = p.selectedAgent === id ? 3 : 1;
        ctx.stroke();
        if (p.currentFrame?.statuses[id] === "collided") {
          ctx.strokeStyle = "#fb7185";
          ctx.strokeRect(x * size, y * size, size, size);
        }
        if (size > 15) {
          ctx.fillStyle = "#020617";
          ctx.textAlign = "center";
          ctx.font = `bold ${Math.min(13, size * 0.32)}px monospace`;
          ctx.fillText(String(index + 1), (x + 0.5) * size, (y + 0.62) * size);
        }
      });
      ctx.restore();
    };
    const schedule = () => {
      cancelAnimationFrame(scheduled);
      scheduled = requestAnimationFrame(draw);
    };
    drawRef.current = schedule;
    const fit = () => {
      const p = propsRef.current,
        r = host.getBoundingClientRect();
      const cell = Math.max(
        3,
        Math.min(
          (r.width - 60) / p.gridWidth,
          (r.height - 60) / p.gridHeight,
          60,
        ),
      );
      view.current = {
        x: (r.width - cell * p.gridWidth) / 2,
        y: (r.height - cell * p.gridHeight) / 2,
        cell,
        zoom: 1,
      };
      schedule();
    };
    fitRef.current = fit;
    const observer = new ResizeObserver(fit);
    observer.observe(host);
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const r = canvas.getBoundingClientRect(),
        v = view.current,
        n = Math.max(
          0.25,
          Math.min(6, v.zoom * (event.deltaY < 0 ? 1.1 : 1 / 1.1)),
        ),
        ratio = n / v.zoom;
      v.x = event.clientX - r.left - (event.clientX - r.left - v.x) * ratio;
      v.y = event.clientY - r.top - (event.clientY - r.top - v.y) * ratio;
      v.zoom = n;
      schedule();
    };
    canvas.addEventListener("wheel", wheel, { passive: false });
    fit();
    return () => {
      observer.disconnect();
      canvas.removeEventListener("wheel", wheel);
      cancelAnimationFrame(scheduled);
    };
  }, []);
  useEffect(() => {
    propsRef.current = props;
    drawRef.current();
  }, [props]);
  useEffect(() => {
    fitRef.current();
  }, [props.gridWidth, props.gridHeight]);
  return (
    <div ref={hostRef} className="canvas-container">
      {unavailable && (
        <p role="alert">
          Canvas is unavailable. Use the agent table below to inspect exact
          coordinates.
        </p>
      )}
      <canvas
        ref={canvasRef}
        aria-label="Scenario grid; coordinates and selection are also available in the agent table"
        role="img"
        onPointerDown={(e) => {
          drag.current = { x: e.clientX, y: e.clientY, moved: false };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const dx = e.clientX - d.x,
            dy = e.clientY - d.y;
          if (Math.abs(dx) + Math.abs(dy) > 2) d.moved = true;
          if (d.moved) {
            view.current.x += dx;
            view.current.y += dy;
            d.x = e.clientX;
            d.y = e.clientY;
            drawRef.current();
          }
        }}
        onPointerUp={(e) => {
          const d = drag.current;
          drag.current = null;
          if (!d || d.moved) return;
          const r = e.currentTarget.getBoundingClientRect(),
            v = view.current;
          const x = Math.floor((e.clientX - r.left - v.x) / (v.cell * v.zoom)),
            y = Math.floor((e.clientY - r.top - v.y) / (v.cell * v.zoom));
          if (x < 0 || y < 0 || x >= props.gridWidth || y >= props.gridHeight)
            return;
          if (props.onEditCell) {
            props.onEditCell(x, y);
            return;
          }
          const observation =
            props.currentFrame?.local_observations?.[props.selectedAgent || ""];
          const localPositions: Record<string, number[]> = {};
          if (observation) {
            localPositions[observation.agent_id] = observation.position;
            for (const message of observation.messages)
              if (message.points.length)
                localPositions[message.sender] = message.points[0];
          }
          const positions = props.localView
            ? localPositions
            : props.currentFrame?.positions || props.starts;
          const id = Object.keys(props.starts).find(
            (a) =>
              positions[a]?.[0] === x &&
              positions[a]?.[1] === y &&
              props.currentFrame?.statuses[a] !== "disappeared",
          );
          props.onSelectAgent?.(id || null);
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      />
      <div className="canvas-overlay-controls">
        <button onClick={() => fitRef.current()}>Fit grid</button>
      </div>
    </div>
  );
}
