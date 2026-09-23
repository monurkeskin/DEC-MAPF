import { test, expect } from "@playwright/test";
import { GridCanvasController } from "../src/grid/controller";
import type { GridViewportProps } from "../src/grid/types";

type Pointer = { clientX: number; clientY: number; pointerId: number };
const pointer = (x: number, y: number): Pointer => ({
  clientX: x + 10,
  clientY: y + 20,
  pointerId: 1,
});

function setup(props: Partial<GridViewportProps> = {}) {
  const selected: (string | null)[] = [];
  const saved = {
    frame: globalThis.requestAnimationFrame,
    cancel: globalThis.cancelAnimationFrame,
    observer: globalThis.ResizeObserver,
  };
  globalThis.requestAnimationFrame = () => 1;
  globalThis.cancelAnimationFrame = () => {};
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  const rect = () => ({ left: 10, top: 20, width: 300, height: 300 });
  const handlers = new Map<string, (event: unknown) => void>();
  const canvas = {
    getBoundingClientRect: rect,
    setPointerCapture() {},
    addEventListener: (name: string, fn: (e: unknown) => void) =>
      handlers.set(name, fn),
    removeEventListener: (name: string) => handlers.delete(name),
  } as unknown as HTMLCanvasElement;
  const controller = new GridCanvasController(
    canvas,
    { getBoundingClientRect: rect } as HTMLDivElement,
    {} as CanvasRenderingContext2D,
    {
      gridWidth: 4,
      gridHeight: 4,
      obstacles: [],
      starts: { a: [0, 0] },
      goals: { a: [3, 3] },
      onSelectAgent: (id) => selected.push(id),
      ...props,
    },
  );
  controller.start();
  return {
    controller,
    selected,
    handlers,
    cleanup: () => {
      controller.destroy();
      globalThis.requestAnimationFrame = saved.frame;
      globalThis.cancelAnimationFrame = saved.cancel;
      globalThis.ResizeObserver = saved.observer;
    },
  };
}

function click(controller: GridCanvasController, x: number, y: number) {
  controller.pointerDown(pointer(x, y));
  controller.pointerUp(pointer(x, y));
}

test("dragging pans without selecting; Fit grid restores selection coordinates", () => {
  const view = setup();
  try {
    click(view.controller, 60, 60);
    view.controller.pointerDown(pointer(60, 60));
    view.controller.pointerMove(pointer(120, 60));
    view.controller.pointerUp(pointer(120, 60));
    expect(view.selected).toEqual(["a"]);
    click(view.controller, 120, 60);
    view.controller.fit();
    click(view.controller, 60, 60);
    expect(view.selected).toEqual(["a", "a", "a"]);
  } finally {
    view.cleanup();
  }
  expect(view.handlers.size).toBe(0);
});

test("zoom retains the cell under the pointer across both clamp limits", () => {
  const view = setup();
  try {
    for (const deltaY of [...Array(40).fill(-1), ...Array(80).fill(1)]) {
      view.handlers.get("wheel")?.({
        ...pointer(60, 60),
        deltaY,
        preventDefault() {},
      });
      click(view.controller, 60, 60);
    }
    expect(view.selected).toEqual(Array(120).fill("a"));
  } finally {
    view.cleanup();
  }
});

test("cell editing wins over selection while cancellation and margin clicks do nothing", () => {
  const edited: number[][] = [];
  const view = setup({ onEditCell: (x, y) => edited.push([x, y]) });
  try {
    click(view.controller, 60, 60);
    view.controller.pointerDown(pointer(60, 60));
    view.controller.pointerCancel();
    view.controller.pointerUp(pointer(60, 60));
    click(view.controller, 0, 0);
    expect(edited).toEqual([[0, 0]]);
    expect(view.selected).toEqual([]);
  } finally {
    view.cleanup();
  }
});
