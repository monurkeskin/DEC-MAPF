const workflows = ["Configure", "Inspect", "Compare", "Export"] as const;
export type Workflow = (typeof workflows)[number];

type Props = {
  screen: Workflow;
  theme: string;
  setTheme: (theme: string) => void;
  onNavigate: (screen: Workflow) => void;
};
export function WorkspaceHeader({
  screen,
  theme,
  setTheme,
  onNavigate,
}: Props) {
  return (
    <header className="app-header">
      <div>
        <strong>DEC-MAPF</strong>
        <span className="brand-sub">Alpha · Research workspace</span>
        <a
          className="brand-sub"
          href="/THIRD_PARTY_NOTICES.txt"
          target="_blank"
          rel="noopener noreferrer"
        >
          Open-source notices
        </a>
      </div>
      <nav aria-label="Workflow">
        {workflows.map((w) => (
          <button
            key={w}
            aria-current={screen === w ? "page" : undefined}
            onClick={() => {
              onNavigate(w);
            }}
          >
            {w}
          </button>
        ))}
      </nav>
      <button
        aria-label="Toggle light or dark theme"
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      >
        {theme === "dark" ? "Light theme" : "Dark theme"}
      </button>
    </header>
  );
}
