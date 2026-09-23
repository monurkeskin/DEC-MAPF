const COLORS = [
  "#06b6d4",
  "#d97706",
  "#10b981",
  "#e11d48",
  "#a78bfa",
  "#60a5fa",
  "#14b8a6",
  "#f97316",
];
export function getAgentColorHex(index: number) {
  return COLORS[index % COLORS.length];
}
