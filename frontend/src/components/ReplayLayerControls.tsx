import { layerLabels } from "../hooks/useReplayLayers";
import type { Layer, ReplayLayers } from "../hooks/useReplayLayers";

type Props = {
  layers: ReplayLayers;
  toggle: (key: Layer, checked: boolean) => void;
};
export function ReplayLayerControls({ layers, toggle }: Props) {
  return (
    <div className="layer-bar">
      {(Object.keys(layerLabels) as Layer[]).map((key) => (
        <label className="checkbox" key={key}>
          <input
            type="checkbox"
            checked={layers[key]}
            onChange={(event) => toggle(key, event.target.checked)}
          />
          {layerLabels[key]}
        </label>
      ))}
    </div>
  );
}
