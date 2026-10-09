// Dockable panel area. Each workspace has a default layout; whatever the user
// re-docks is saved per workspace in the browser.
import { DockviewReact, type DockviewApi, type DockviewReadyEvent, type IDockviewPanelProps } from "dockview";
import { Component, useEffect, useRef, type ErrorInfo, type FC, type ReactNode } from "react";
import { hooks } from "@/commands/registry";
import { PANELS } from "@/panels/registry";
import { useView } from "@/store/view";
import { workspace, type WorkspaceDef } from "@/workspaces";

const LAYOUT_VERSION = 5;
const key = (ws: string) => `calflab.layout.v${LAYOUT_VERSION}.${ws}`;

class PanelBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(error: Error) {
    return { error: error.message };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Panel crashed", error, info);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-3 text-err">
          This panel hit an error: {this.state.error}
          <div>
            <button className="mt-2 underline" onClick={() => this.setState({ error: null })}>Try again</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const components: Record<string, FC<IDockviewPanelProps>> = Object.fromEntries(
  Object.entries(PANELS).map(([id, p]) => {
    const Panel = p.component;
    const Wrapped: FC<IDockviewPanelProps> = () => (
      <div className="h-full w-full overflow-hidden bg-bg2 text-fg">
        <PanelBoundary>
          <Panel />
        </PanelBoundary>
      </div>
    );
    return [id, Wrapped];
  }),
);

function buildDefault(api: DockviewApi, ws: WorkspaceDef) {
  const add = (id: string, position?: { referencePanel: string; direction: "left" | "right" | "below" | "above" | "within" }) =>
    api.addPanel({ id, component: id, title: (PANELS as Record<string, { title: string }>)[id]?.title ?? id, position });
  const [c0, ...cRest] = ws.center;
  add(c0);
  cRest.forEach((id) => add(id, { referencePanel: c0, direction: "within" }));
  if (ws.bottom.length) {
    add(ws.bottom[0], { referencePanel: c0, direction: "below" });
    ws.bottom.slice(1).forEach((id) => add(id, { referencePanel: ws.bottom[0], direction: "within" }));
  }
  const beside = ws.beside ?? [];
  if (beside.length) {
    add(beside[0], { referencePanel: c0, direction: "right" });
    beside.slice(1).forEach((id) => add(id, { referencePanel: beside[0], direction: "within" }));
  }
  if (ws.left.length) {
    add(ws.left[0], { referencePanel: c0, direction: "left" });
    ws.left.slice(1).forEach((id, i) => add(id, { referencePanel: ws.left[i], direction: "below" }));
  }
  if (ws.right.length) {
    add(ws.right[0], { referencePanel: beside[0] ?? c0, direction: "right" });
    ws.right.slice(1).forEach((id) => add(id, { referencePanel: ws.right[0], direction: "within" }));
  }
  // show the first tab of every group, and leave the centre panel active
  for (const id of [ws.right[0], ws.bottom[0], c0]) if (id) api.getPanel(id)?.api.setActive();
  requestAnimationFrame(() => {
    for (const id of ws.left.slice(0, 2)) api.getPanel(id)?.group.api.setSize({ width: 210 });
    if (ws.right[0]) api.getPanel(ws.right[0])?.group.api.setSize({ width: 340 });
    if (ws.bottom[0]) api.getPanel(ws.bottom[0])?.group.api.setSize({ height: 210 });
  });
}

function load(api: DockviewApi, wsId: string) {
  api.clear();
  const saved = localStorage.getItem(key(wsId));
  if (saved) {
    try {
      api.fromJSON(JSON.parse(saved));
      return;
    } catch {
      localStorage.removeItem(key(wsId));
      api.clear();
    }
  }
  buildDefault(api, workspace(wsId));
}

export function Dock() {
  const ws = useView((s) => s.workspace);
  const theme = useView((s) => s.theme);
  const apiRef = useRef<DockviewApi | null>(null);
  const wsRef = useRef(ws);
  const loading = useRef(false);

  const onReady = (e: DockviewReadyEvent) => {
    apiRef.current = e.api;
    loading.current = true;
    load(e.api, wsRef.current);
    loading.current = false;
    e.api.onDidLayoutChange(() => {
      if (loading.current) return;
      try {
        localStorage.setItem(key(wsRef.current), JSON.stringify(e.api.toJSON()));
      } catch {
        /* storage full or blocked: the default layout is used next time */
      }
    });
  };

  useEffect(() => {
    if (wsRef.current === ws || !apiRef.current) {
      wsRef.current = ws;
      return;
    }
    wsRef.current = ws;
    loading.current = true;
    load(apiRef.current, ws);
    loading.current = false;
  }, [ws]);

  useEffect(() => {
    hooks.showPanel = (id) => {
      const api = apiRef.current;
      if (!api || !(id in PANELS)) return;
      const panel = api.getPanel(id) ?? api.addPanel({ id, component: id, title: (PANELS as Record<string, { title: string }>)[id].title });
      if (!panel.api.isVisible) panel.api.setActive();
    };
    return () => {
      hooks.showPanel = () => undefined;
    };
  }, []);

  useEffect(() => {
    const reset = () => {
      localStorage.removeItem(key(wsRef.current));
      if (apiRef.current) {
        loading.current = true;
        load(apiRef.current, wsRef.current);
        loading.current = false;
      }
    };
    window.addEventListener("calflab:reset-layout", reset);
    return () => window.removeEventListener("calflab:reset-layout", reset);
  }, []);

  return (
    <DockviewReact
      className={`${theme === "dark" ? "dockview-theme-abyss" : "dockview-theme-light"} dockview-theme-calflab`}
      components={components}
      onReady={onReady}
    />
  );
}
