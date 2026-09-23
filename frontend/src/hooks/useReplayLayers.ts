import { useState } from "react";

export const layerLabels = {
  paths: "Executed paths",
  heat: "Hindsight heat",
  localHeat: "Recorded local heat",
  fov: "FoV geometry",
  localView: "Recorded local view",
  reservations: "Recorded reservations",
} as const;
export type Layer = keyof typeof layerLabels;
export type ReplayLayers = Record<Layer, boolean>;
export const initialLayers: ReplayLayers = {
  paths: true,
  heat: false,
  localHeat: false,
  fov: false,
  localView: false,
  reservations: false,
};
export function toggleLayer(
  current: ReplayLayers,
  key: Layer,
  checked: boolean,
): ReplayLayers {
  const next = { ...current, [key]: checked };
  if (checked && key === "heat") next.localHeat = false;
  if (checked && key === "localHeat") next.heat = false;
  return next;
}
export function useReplayLayers() {
  const [layers, setLayers] = useState(initialLayers);
  const toggle = (key: Layer, checked: boolean) =>
    setLayers((value) => toggleLayer(value, key, checked));
  return { layers, toggle };
}
