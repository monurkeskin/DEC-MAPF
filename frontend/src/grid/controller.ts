/** Own viewport geometry, rendering scheduling and pointer interaction. */
import type { GridViewportProps } from "./types";
import { paintGrid } from "./painter";
import { pickAgent } from "./scene";

type View = { x: number; y: number; cell: number; zoom: number };
type Pointer = Pick<PointerEvent, "clientX" | "clientY" | "pointerId">;

export class GridCanvasController {
  private readonly canvas: HTMLCanvasElement;
  private readonly host: HTMLDivElement;
  private readonly context: CanvasRenderingContext2D;
  private props: GridViewportProps;
  private view: View = { x: 0, y: 0, cell: 32, zoom: 1 };
  private drag: { x: number; y: number; moved: boolean } | null = null;
  private scheduled = 0;
  private observer: ResizeObserver | null = null;

  constructor(
    canvas: HTMLCanvasElement,
    host: HTMLDivElement,
    context: CanvasRenderingContext2D,
    props: GridViewportProps,
  ) {
    this.canvas = canvas;
    this.host = host;
    this.context = context;
    this.props = props;
  }

  start() {
    this.observer = new ResizeObserver(this.fit);
    this.observer.observe(this.host);
    this.canvas.addEventListener("wheel", this.wheel, { passive: false });
    this.fit();
  }

  destroy() {
    this.observer?.disconnect();
    this.canvas.removeEventListener("wheel", this.wheel);
    cancelAnimationFrame(this.scheduled);
  }

  update(props: GridViewportProps) {
    this.props = props;
    this.schedule();
  }

  private schedule() {
    cancelAnimationFrame(this.scheduled);
    this.scheduled = requestAnimationFrame(() => this.draw());
  }

  private draw() {
    const { canvas, context: ctx, view, props, host } = this;
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
    ctx.translate(view.x, view.y);
    paintGrid(ctx, props, view.cell * view.zoom);
    ctx.restore();
  }

  fit = () => {
    const { props } = this,
      rect = this.host.getBoundingClientRect();
    const cell = Math.max(
      3,
      Math.min(
        (rect.width - 60) / props.gridWidth,
        (rect.height - 60) / props.gridHeight,
        60,
      ),
    );
    this.view = {
      x: (rect.width - cell * props.gridWidth) / 2,
      y: (rect.height - cell * props.gridHeight) / 2,
      cell,
      zoom: 1,
    };
    this.schedule();
  };

  private wheel = (event: WheelEvent) => {
    event.preventDefault();
    const rect = this.canvas.getBoundingClientRect(),
      view = this.view;
    const next = Math.max(
      0.25,
      Math.min(6, view.zoom * (event.deltaY < 0 ? 1.1 : 1 / 1.1)),
    );
    const ratio = next / view.zoom;
    view.x =
      event.clientX - rect.left - (event.clientX - rect.left - view.x) * ratio;
    view.y =
      event.clientY - rect.top - (event.clientY - rect.top - view.y) * ratio;
    view.zoom = next;
    this.schedule();
  };

  pointerDown(event: Pointer) {
    this.drag = { x: event.clientX, y: event.clientY, moved: false };
    this.canvas.setPointerCapture(event.pointerId);
  }

  pointerMove(event: Pointer) {
    const drag = this.drag;
    if (!drag) return;
    const dx = event.clientX - drag.x,
      dy = event.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) drag.moved = true;
    if (!drag.moved) return;
    this.view.x += dx;
    this.view.y += dy;
    drag.x = event.clientX;
    drag.y = event.clientY;
    this.schedule();
  }

  pointerUp(event: Pointer) {
    const drag = this.drag;
    this.drag = null;
    if (!drag || drag.moved) return;
    const rect = this.canvas.getBoundingClientRect(),
      view = this.view;
    const x = Math.floor(
      (event.clientX - rect.left - view.x) / (view.cell * view.zoom),
    );
    const y = Math.floor(
      (event.clientY - rect.top - view.y) / (view.cell * view.zoom),
    );
    if (
      x < 0 ||
      y < 0 ||
      x >= this.props.gridWidth ||
      y >= this.props.gridHeight
    )
      return;
    if (this.props.onEditCell) this.props.onEditCell(x, y);
    else this.props.onSelectAgent?.(pickAgent(this.props, x, y));
  }

  pointerCancel() {
    this.drag = null;
  }
}
