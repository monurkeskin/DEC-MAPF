import { useEffect, useRef, useState } from "react";
import type { GridViewportProps } from "../grid/types";
import { GridCanvasController } from "../grid/controller";
export type { GridViewportProps } from "../grid/types";

/** Rendering and pointer state stay outside React's frame updates. */
export function GridViewport(props: GridViewportProps) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const controller = useRef<GridCanvasController | null>(null);
  const latestProps = useRef(props);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    if (!canvas.current || !host.current) return;
    const context = canvas.current.getContext("2d");
    if (!context) {
      setUnavailable(true);
      return;
    }
    const owner = new GridCanvasController(
      canvas.current,
      host.current,
      context,
      latestProps.current,
    );
    controller.current = owner;
    owner.start();
    return () => {
      owner.destroy();
      controller.current = null;
    };
  }, []);
  useEffect(() => {
    latestProps.current = props;
    controller.current?.update(props);
  }, [props]);
  useEffect(() => {
    controller.current?.fit();
  }, [props.gridWidth, props.gridHeight]);

  return (
    <div ref={host} className="canvas-container">
      {unavailable && (
        <p role="alert">
          Canvas is unavailable. Use the agent table below to inspect exact
          coordinates.
        </p>
      )}
      <canvas
        ref={canvas}
        aria-label="Scenario grid; coordinates and selection are also available in the agent table"
        role="img"
        onPointerDown={(event) => controller.current?.pointerDown(event)}
        onPointerMove={(event) => controller.current?.pointerMove(event)}
        onPointerUp={(event) => controller.current?.pointerUp(event)}
        onPointerCancel={() => controller.current?.pointerCancel()}
      />
      <div className="canvas-overlay-controls">
        <button onClick={() => controller.current?.fit()}>Fit grid</button>
      </div>
    </div>
  );
}
