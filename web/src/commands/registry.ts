// Every UI action is a named command. Client commands change view state; server
// commands (from /api/commands) change the document or start work. Menus,
// buttons, shortcuts and the command line all call `execute(name)`.
import { api } from "@/api/client";
import type { CommandInfo, Schema } from "@/api/types";
import { useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";
import { OVERLAYS, useView, type DisplayMode, type ViewName } from "@/store/view";
import { WORKSPACES } from "@/workspaces";

export interface UnifiedCommand {
  name: string; // Rhino-style, e.g. "ZoomExtents"
  key: string; // server key or client id
  label: string;
  description: string;
  category: string;
  origin: "client" | "server";
  schema?: Schema;
  aliases: string[];
  stub?: boolean;
}

interface ClientCommand {
  name: string;
  label: string;
  description: string;
  category: string;
  aliases?: string[];
  run: () => void | Promise<void>;
}

/** Hooks the shell installs so commands can open dialogs / capture the viewport. */
export const hooks: {
  openDialog: (cmd: UnifiedCommand, initial?: Record<string, unknown>) => void;
  capture: () => string | null;
  openShortcuts: () => void;
  startTour: () => void;
  focusCommandLine: () => void;
  /** bring a dock panel to the front of its tab group (adds it if it was closed) */
  showPanel: (id: string) => void;
} = {
  openDialog: () => undefined,
  capture: () => null,
  openShortcuts: () => undefined,
  startTour: () => undefined,
  focusCommandLine: () => undefined,
  showPanel: () => undefined,
};

/** Replay a recorded run in the viewport, and bring the viewport forward so it can be seen. */
export async function replayRun(runId: string): Promise<void> {
  const lab = useLab.getState();
  try {
    await usePlayback.getState().loadRun(runId);
    hooks.showPanel("viewport");
    lab.log("info", `Replaying run ${runId}`, "runs");
  } catch (e) {
    lab.log("error", `Cannot replay run ${runId}: ${(e as Error).message}`, "runs");
  }
}

const view = () => useView.getState();

function displayCmd(mode: DisplayMode): ClientCommand {
  const label = mode[0].toUpperCase() + mode.slice(1);
  return {
    name: `Display${label}`,
    label: `Display: ${label}`,
    description: `Switch the viewport to ${label} display mode.`,
    category: "View",
    aliases: [label],
    run: () => view().set({ displayMode: mode }),
  };
}

function viewCmd(v: ViewName): ClientCommand {
  const label = v[0].toUpperCase() + v.slice(1);
  return {
    name: `View${label}`,
    label: `View: ${label}`,
    description: `Set the active viewport to the ${label} view.`,
    category: "View",
    aliases: [label],
    run: () => view().requestCamera("view", { view: v }),
  };
}

export const CLIENT_COMMANDS: ClientCommand[] = [
  ...(["top", "front", "right", "perspective"] as ViewName[]).map(viewCmd),
  ...(["wireframe", "shaded", "ghosted", "xray", "rendered"] as DisplayMode[]).map(displayCmd),
  {
    name: "ZoomExtents",
    label: "Zoom extents",
    description: "Frame the whole robot.",
    category: "View",
    aliases: ["ZE"],
    run: () => view().requestCamera("extents"),
  },
  {
    name: "ZoomSelected",
    label: "Zoom selected",
    description: "Frame the selection.",
    category: "View",
    aliases: ["ZS"],
    run: () => view().requestCamera("selected"),
  },
  {
    name: "FourView",
    label: "Toggle four viewports",
    description: "Switch between a single viewport and Top/Front/Right/Perspective.",
    category: "View",
    aliases: ["4View"],
    run: () => view().set({ fourView: !view().fourView }),
  },
  {
    name: "SaveView",
    label: "Save named view",
    description: "Store the current camera as a named view.",
    category: "View",
    run: () => {
      window.dispatchEvent(new CustomEvent("calflab:save-view"));
    },
  },
  ...OVERLAYS.filter((o) => o.ready).map<ClientCommand>((o) => ({
    name: `Overlay${o.key[0].toUpperCase()}${o.key.slice(1)}`,
    label: `Overlay: ${o.label}`,
    description: `Toggle the ${o.label.toLowerCase()} overlay.`,
    category: "View",
    run: () => view().toggleOverlay(o.key),
  })),
  {
    name: "Hide",
    label: "Hide selected",
    description: "Hide the selected objects.",
    category: "Select",
    run: () => view().set({ hidden: [...new Set([...view().hidden, ...view().selection])], selection: [] }),
  },
  {
    name: "Show",
    label: "Show all",
    description: "Show everything that was hidden or isolated.",
    category: "Select",
    aliases: ["ShowAll"],
    run: () => view().set({ hidden: [], isolated: null }),
  },
  {
    name: "Isolate",
    label: "Isolate selected",
    description: "Show only the selected objects.",
    category: "Select",
    run: () => {
      if (view().selection.length) view().set({ isolated: [...view().selection] });
    },
  },
  {
    name: "SelNone",
    label: "Select none",
    description: "Clear the selection.",
    category: "Select",
    run: () => view().select([]),
  },
  {
    name: "SelAll",
    label: "Select all",
    description: "Select every part.",
    category: "Select",
    run: () => view().select((useLab.getState().scene?.bodies ?? []).map((b) => b.id)),
  },
  {
    name: "Play",
    label: "Play / pause",
    description: "Play or pause simulation playback.",
    category: "Simulate",
    aliases: ["Pause"],
    run: () => usePlayback.getState().toggle(),
  },
  {
    name: "ClearPlayback",
    label: "Return to design pose",
    description: "Stop playback and show the standing design.",
    category: "Simulate",
    run: () => usePlayback.getState().clear(),
  },
  {
    name: "Measure",
    label: "Measure distance",
    description: "Click two points to measure the distance between them.",
    category: "Analyze",
    aliases: ["Distance"],
    run: () => view().set({ measure: !view().measure }),
  },
  {
    name: "ToggleTheme",
    label: "Toggle dark / light theme",
    description: "Switch the colour theme.",
    category: "Window",
    run: () => view().set({ theme: view().theme === "dark" ? "light" : "dark" }),
  },
  {
    name: "Shortcuts",
    label: "Keyboard shortcuts",
    description: "View and rebind keyboard shortcuts.",
    category: "Window",
    run: () => hooks.openShortcuts(),
  },
  {
    name: "Tour",
    label: "Start the guided tour",
    description: "Replay the 6-step introduction.",
    category: "Window",
    run: () => hooks.startTour(),
  },
  {
    name: "Capture",
    label: "Capture viewport to journal",
    description: "Save a viewport image with full provenance and attach it to the journal.",
    category: "Journal",
    run: async () => {
      const dataUrl = hooks.capture();
      const lab = useLab.getState();
      if (!dataUrl) return lab.log("warn", "No viewport to capture.");
      const pb = usePlayback.getState();
      const cap = await api.post<{ id: string; path: string }>("/api/captures", {
        data_url: dataUrl,
        provenance: { run: pb.runId, frame: Math.round(pb.frame), display: view().displayMode, workspace: view().workspace },
      });
      lab.log("info", `Captured viewport: calflab://capture/${cap.id}`, "journal");
      window.dispatchEvent(new CustomEvent("calflab:capture", { detail: cap }));
    },
  },
  ...WORKSPACES.map<ClientCommand>((w) => ({
    name: `Workspace${w.label}`,
    label: `Workspace: ${w.label}`,
    description: `Switch to the ${w.label} workspace.`,
    category: "Window",
    // no bare-label alias: "Simulate" and "Evolve" must run the action, not switch tabs
    run: () => view().set({ workspace: w.id }),
  })),
];

function pascal(key: string): string {
  return key
    .split("_")
    .map((p) => p[0].toUpperCase() + p.slice(1))
    .join("");
}

export function normalize(text: string): string {
  return text.toLowerCase().replace(/[\s_\-:]/g, "");
}

export function allCommands(server: CommandInfo[]): UnifiedCommand[] {
  const out: UnifiedCommand[] = CLIENT_COMMANDS.map((c) => ({
    name: c.name,
    key: c.name,
    label: c.label,
    description: c.description,
    category: c.category,
    origin: "client",
    aliases: c.aliases ?? [],
  }));
  for (const c of server) {
    out.push({
      name: pascal(c.key),
      key: c.key,
      label: c.label,
      description: c.description,
      category: c.category,
      origin: "server",
      schema: c.schema,
      aliases: c.aliases ?? [],
      stub: c.stub,
    });
  }
  return out;
}

/** Rank commands for the command line: prefix matches first, then substring matches. */
export function matchCommands(query: string, commands: UnifiedCommand[]): UnifiedCommand[] {
  const q = normalize(query);
  if (!q) return [];
  const scored: [number, UnifiedCommand][] = [];
  for (const c of commands) {
    const names = [c.name, c.label, ...c.aliases].map(normalize);
    let score = 0;
    if (names.some((n) => n === q)) score = 4;
    else if (normalize(c.name).startsWith(q) || c.aliases.some((a) => normalize(a).startsWith(q))) score = 3;
    else if (names.some((n) => n.startsWith(q))) score = 2;
    else if (names.some((n) => n.includes(q))) score = 1;
    if (score) scored.push([score, c]);
  }
  return scored.sort((a, b) => b[0] - a[0] || a[1].name.localeCompare(b[1].name)).map(([, c]) => c);
}

export function findCommand(name: string, commands: UnifiedCommand[]): UnifiedCommand | undefined {
  const q = normalize(name);
  return (
    commands.find((c) => normalize(c.name) === q || normalize(c.key) === q) ??
    commands.find((c) => c.aliases.some((a) => normalize(a) === q))
  );
}

/** Parse `key=value` arguments typed after a command name. */
export function parseArgs(parts: string[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const p of parts) {
    const i = p.indexOf("=");
    if (i < 1) continue;
    const raw = p.slice(i + 1);
    let value: unknown = raw;
    if (raw === "true" || raw === "false") value = raw === "true";
    else if (raw !== "" && !Number.isNaN(Number(raw))) value = Number(raw);
    out[p.slice(0, i)] = value;
  }
  return out;
}

let lastCommand: { name: string; params?: Record<string, unknown> } | null = null;
export const recent: string[] = [];

export function lastCommandName(): string | null {
  return lastCommand?.name ?? null;
}

/** Execute a command by name. Server commands with parameters open a dialog unless params are given. */
export async function execute(name: string, params?: Record<string, unknown>, opts: { dialog?: boolean } = {}): Promise<void> {
  const lab = useLab.getState();
  const cmd = findCommand(name, allCommands(lab.commands));
  if (!cmd) {
    lab.log("error", `Unknown command: ${name}`, "command");
    return;
  }
  lastCommand = { name: cmd.name, params };
  const i = recent.indexOf(cmd.name);
  if (i >= 0) recent.splice(i, 1);
  recent.unshift(cmd.name);
  recent.splice(12);

  if (cmd.origin === "client") {
    const c = CLIENT_COMMANDS.find((x) => x.name === cmd.name)!;
    lab.log("cmd", cmd.name, "command");
    await c.run();
    return;
  }
  const hasFields = (cmd.schema?.fields.length ?? 0) > 0;
  if (hasFields && params === undefined && opts.dialog !== false) {
    hooks.openDialog(cmd);
    return;
  }
  lab.log("cmd", `${cmd.name}${params && Object.keys(params).length ? " " + JSON.stringify(params) : ""}`, "command");
  try {
    const result = await lab.run(cmd.key, params ?? {});
    if (result && typeof result === "object" && Object.keys(result).length) {
      lab.log("info", JSON.stringify(result), cmd.name);
    }
    if (cmd.key === "bake") {
      // attach a thumbnail of what was baked
      const dataUrl = hooks.capture();
      if (dataUrl && result?.design) {
        void api.post(`/api/designs/${result.design}/thumbnail`, { data_url: dataUrl }).catch(() => undefined);
      }
    }
  } catch {
    /* already logged by lab.run */
  }
}

export function repeatLast(): void {
  if (lastCommand) void execute(lastCommand.name, lastCommand.params);
}
