import type { FrameSnapshot, Point2D } from "../api/types";

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
