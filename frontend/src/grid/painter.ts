/** Recorded grid layers share coordinates, while retaining distinct information sources. */
import type { GridViewportProps } from "./types";
import { localObservation, visiblePositions } from "./scene";
import { getAgentColorHex } from "../components/agentColors";

type Layer = {
  ctx: CanvasRenderingContext2D;
  p: GridViewportProps;
  size: number;
  ids: string[];
  positions: Record<string, number[]>;
  observation: ReturnType<typeof localObservation>;
  visible: boolean;
};

export function paintGrid(
  ctx: CanvasRenderingContext2D,
  p: GridViewportProps,
  size: number,
) {
  const observation = localObservation(p);
  const layer: Layer = {
    ctx,
    p,
    size,
    observation,
    ids: Object.keys(p.starts),
    positions: visiblePositions(p),
    visible: !p.localView || !!observation,
  };
  grid(layer);
  coordinates(layer);
  obstacles(layer);
  rememberedObstacles(layer);
  heat(layer);
  routes(layer);
  broadcasts(layer);
  reservations(layer);
  fov(layer);
  layer.ids.forEach((id, index) => agent(layer, id, index));
}

function grid({ ctx, p, size, visible }: Layer) {
  ctx.lineWidth = 1;
  ctx.strokeStyle = "#334155";
  for (let y = 0; y < p.gridHeight; y++) {
    for (let x = 0; x < p.gridWidth; x++) {
      ctx.fillStyle = visible ? "#17243b" : "#05080f";
      ctx.fillRect(x * size, y * size, size, size);
      ctx.strokeRect(x * size, y * size, size, size);
    }
  }
}

function coordinates({ ctx, p, size }: Layer) {
  ctx.font = `${Math.max(9, Math.min(12, size * 0.3))}px monospace`;
  ctx.fillStyle = "#cbd5e1";
  ctx.textAlign = "center";
  if (size < 14) return;
  for (let x = 0; x < p.gridWidth; x++)
    ctx.fillText(String(x), (x + 0.5) * size, -7);
  ctx.textAlign = "right";
  for (let y = 0; y < p.gridHeight; y++)
    ctx.fillText(String(y), -7, (y + 0.6) * size);
}

function obstacles({ ctx, p, size, visible }: Layer) {
  if (!visible) return;
  for (const [x, y] of p.obstacles) {
    ctx.fillStyle = "#64748b";
    ctx.fillRect(x * size + 1, y * size + 1, size - 2, size - 2);
  }
}

function rememberedObstacles({ ctx, p, size, observation }: Layer) {
  if (!p.localView || !observation?.remembered_obstacles) return;
  ctx.strokeStyle = "#c4b5fd";
  ctx.lineWidth = 2;
  ctx.setLineDash([2, 2]);
  for (const [x, y] of observation.remembered_obstacles)
    ctx.strokeRect(x * size + 3, y * size + 3, size - 6, size - 6);
  ctx.setLineDash([]);
}

function heat(layer: Layer) {
  if (layer.p.showHeat && !layer.p.localView)
    heatField(layer, layer.p.currentFrame?.heat_grid || {}, "244,114,182");
  heatField(layer, layer.p.localHeatGrid || {}, "45,212,191");
}

function heatField(
  { ctx, size }: Layer,
  field: Record<string, number>,
  color: string,
) {
  for (const [key, value] of Object.entries(field)) {
    const [x, y] = key.split("-").map(Number);
    ctx.fillStyle = `rgba(${color},${Math.min(0.7, Number(value) * 0.15)})`;
    ctx.fillRect(x * size, y * size, size, size);
  }
}

function routes(layer: Layer) {
  layer.ids.forEach((id, index) => {
    layer.ctx.strokeStyle = getAgentColorHex(index);
    layer.ctx.lineWidth = 2;
    goal(layer, id);
    executedPath(layer, id);
  });
}

function goal({ ctx, p, size, visible }: Layer, id: string) {
  const position =
    !p.localView || id === p.selectedAgent ? p.goals[id] : undefined;
  if (position && visible)
    ctx.strokeRect(
      (position[0] + 0.23) * size,
      (position[1] + 0.23) * size,
      size * 0.54,
      size * 0.54,
    );
}

function otherAgent(p: GridViewportProps, id: string) {
  return !!p.selectedAgent && p.selectedAgent !== id;
}

function polyline(
  ctx: CanvasRenderingContext2D,
  points: number[][],
  size: number,
) {
  ctx.beginPath();
  points.forEach(([x, y], index) => {
    if (index === 0) ctx.moveTo((x + 0.5) * size, (y + 0.5) * size);
    else ctx.lineTo((x + 0.5) * size, (y + 0.5) * size);
  });
  ctx.stroke();
}

function executedPath({ ctx, p, size }: Layer, id: string) {
  if (!p.showPaths || p.localView) return;
  const points = p.paths?.[id];
  if (!points?.length) return;
  ctx.globalAlpha = otherAgent(p, id) ? 0.15 : 0.65;
  polyline(
    ctx,
    points.map(({ x, y }) => [x, y]),
    size,
  );
  ctx.globalAlpha = 1;
}

function broadcasts({ ctx, p, size, ids, observation }: Layer) {
  if (!p.localView || !p.showPaths) return;
  if (!observation) return;
  for (const message of observation.messages) {
    ctx.strokeStyle = getAgentColorHex(ids.indexOf(message.sender));
    ctx.setLineDash([4, 3]);
    polyline(ctx, message.points, size);
  }
  ctx.setLineDash([]);
}

function selectedReservations(p: GridViewportProps) {
  return Object.entries(p.currentFrame?.commitments || {})
    .filter(([owner]) => !otherAgent(p, owner))
    .flatMap(([, records]) => records);
}

function reservations(layer: Layer) {
  const { ctx, p } = layer;
  if (!p.showReservations || p.localView) return;
  ctx.strokeStyle = "#fbbf24";
  ctx.lineWidth = 2;
  ctx.setLineDash([3, 3]);
  for (const record of selectedReservations(p)) reservation(layer, record);
  ctx.setLineDash([]);
}

function reservation(layer: Layer, record: Record<string, unknown>) {
  const start = Number(record.start_tick),
    points = record.points;
  if (!Array.isArray(points) || !Number.isInteger(start)) return;
  points.forEach((_, index) => reservationCell(layer, points, index, start));
}

function cell(point: unknown): number[] | null {
  if (!Array.isArray(point) || point.length !== 2) return null;
  const coordinates = point.map(Number);
  return coordinates.every(Number.isFinite) ? coordinates : null;
}

function reservationCell(
  { ctx, p, size }: Layer,
  points: unknown[],
  index: number,
  start: number,
) {
  const position = cell(points[index]);
  if (!position || start + index < (p.currentFrame?.tick || 0)) return;
  const [x, y] = position;
  ctx.strokeRect((x + 0.1) * size, (y + 0.1) * size, 0.8 * size, 0.8 * size);
  ctx.fillStyle = "#fde68a";
  ctx.font = `${Math.min(10, size * 0.24)}px monospace`;
  ctx.textAlign = "left";
  if (size > 25)
    ctx.fillText("t" + (start + index), (x + 0.12) * size, (y + 0.23) * size);
  const next = cell(points[index + 1]);
  if (next) {
    ctx.beginPath();
    ctx.moveTo((x + 0.5) * size, (y + 0.5) * size);
    ctx.lineTo((next[0] + 0.5) * size, (next[1] + 0.5) * size);
    ctx.stroke();
  }
}

function fov({ ctx, p, size, positions }: Layer) {
  const selected = positions[p.selectedAgent || ""];
  if (!p.showFov || !selected) return;
  const radius = Math.floor((p.fovSize || 3) / 2);
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

function globalStatus(p: GridViewportProps, id: string, status: string) {
  return !p.localView && p.currentFrame?.statuses[id] === status;
}

function agent(layer: Layer, id: string, index: number) {
  if (globalStatus(layer.p, id, "disappeared")) return;
  const position = layer.positions[id];
  if (!position || !layer.visible) return;
  agentBody(layer, id, index, position);
  if (globalStatus(layer.p, id, "collided")) {
    layer.ctx.strokeStyle = "#fb7185";
    layer.ctx.strokeRect(
      position[0] * layer.size,
      position[1] * layer.size,
      layer.size,
      layer.size,
    );
  }
  agentLabel(layer, position, index);
}

function agentBody(
  { ctx, p, size }: Layer,
  id: string,
  index: number,
  [x, y]: number[],
) {
  ctx.fillStyle = getAgentColorHex(index);
  ctx.beginPath();
  ctx.arc((x + 0.5) * size, (y + 0.5) * size, size * 0.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = p.selectedAgent === id ? "#ffffff" : "#111827";
  ctx.lineWidth = p.selectedAgent === id ? 3 : 1;
  ctx.stroke();
}

function agentLabel({ ctx, size }: Layer, [x, y]: number[], index: number) {
  if (size <= 15) return;
  ctx.fillStyle = "#020617";
  ctx.textAlign = "center";
  ctx.font = `bold ${Math.min(13, size * 0.32)}px monospace`;
  ctx.fillText(String(index + 1), (x + 0.5) * size, (y + 0.62) * size);
}
