// Global shell: workspace tabs, command line, dock area, status bar.
import clsx from "clsx";
import { Moon, Redo2, Sun, Undo2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { chord, isTypingTarget, loadKeys } from "@/commands/keys";
import { execute, hooks, repeatLast } from "@/commands/registry";
import { Badge, Button, Empty, IconButton } from "@/components/ui";
import { connectEvolve } from "@/panels/Evolve";
import { usePlaybackClock } from "@/panels/Timeline";
import { CommandLine } from "@/shell/CommandLine";
import { CommandDialog, ShortcutsDialog, Tour } from "@/shell/Dialogs";
import { Dock } from "@/shell/Dock";
import { useLab } from "@/store/lab";
import { connectPlayback } from "@/store/playback";
import { useView } from "@/store/view";
import { WORKSPACES } from "@/workspaces";

function TopBar() {
  const ws = useView((s) => s.workspace);
  const theme = useView((s) => s.theme);
  const state = useLab((s) => s.state);
  return (
    <div className="flex h-8 shrink-0 items-center gap-1 border-b border-line bg-bg px-2">
      <span className="mr-1 font-semibold tracking-wide text-accent">CALFLAB</span>
      <span className="mr-2 max-w-40 truncate text-dim" title={state?.project.path}>{state?.project.name}</span>
      <div className="flex h-full items-end gap-px" role="tablist">
        {WORKSPACES.map((w) => (
          <button
            key={w.id}
            role="tab"
            aria-selected={ws === w.id}
            data-workspace={w.id}
            className={clsx(
              "h-7 rounded-t px-3 text-[12px]",
              ws === w.id ? "border border-b-0 border-line bg-bg2 font-semibold text-fg" : "text-dim hover:text-fg",
            )}
            title={w.ready ? `${w.label} workspace` : `${w.label} workspace (planned)`}
            onClick={() => useView.getState().set({ workspace: w.id })}
          >
            {w.label}
            {!w.ready && <span className="ml-1 text-[9px] text-accent2">soon</span>}
          </button>
        ))}
      </div>
      <div className="flex-1" />
      <IconButton title="Undo (Ctrl+Z): shared by all clients" disabled={!state?.can_undo} onClick={() => void execute("Undo")} data-testid="undo"><Undo2 size={14} /></IconButton>
      <IconButton title="Redo (Ctrl+Y)" disabled={!state?.can_redo} onClick={() => void execute("Redo")} data-testid="redo"><Redo2 size={14} /></IconButton>
      <Button size="sm" onClick={() => void execute("RunSim")} title="Simulate (F5)">Simulate</Button>
      <Button size="sm" variant="primary" onClick={() => void execute("Bake")} title="Bake a versioned design (B)" data-testid="bake">Bake</Button>
      <Button size="sm" variant="ghost" onClick={() => window.dispatchEvent(new CustomEvent("calflab:reset-layout"))} title="Restore this workspace's default panel layout">Reset layout</Button>
      <Button size="sm" variant="ghost" onClick={() => hooks.openShortcuts()} title="Shortcuts and navigation (F1)">Shortcuts</Button>
      <IconButton title="Toggle dark / light theme" onClick={() => void execute("ToggleTheme")}>{theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}</IconButton>
    </div>
  );
}

function StatusBar() {
  const connected = useLab((s) => s.connected);
  const pending = useLab((s) => s.pending);
  const state = useLab((s) => s.state);
  const meta = useLab((s) => s.meta);
  const jobs = useLab((s) => s.jobs);
  const selection = useView((s) => s.selection);
  const snapGrid = useView((s) => s.snapGrid);
  const snapStep = useView((s) => s.snapStep);
  const nav = useView((s) => s.nav);
  const running = jobs.filter((j) => j.status === "running" || j.status === "queued").length;
  const pluginErrors = Object.keys(meta?.plugin_errors ?? {}).length;
  const set = useView.getState().set;
  return (
    <div className="flex h-6 shrink-0 items-center gap-3 border-t border-line bg-bg px-2 text-[11px] text-dim" data-testid="status-bar">
      <span title="Units used in files and the UI. The simulator uses SI internally.">Units: mm · g · deg</span>
      <span title="Geometric tolerance for display and export">Tol 0.01 mm</span>
      <label className="flex items-center gap-1" title="Snap gumball edits to a grid step">
        <input type="checkbox" checked={snapGrid} onChange={(e) => set({ snapGrid: e.target.checked })} />
        Grid snap
        <select value={snapStep} disabled={!snapGrid} onChange={(e) => set({ snapStep: Number(e.target.value) })}>
          {[0.5, 1, 5, 10].map((s) => <option key={s} value={s}>{s} mm</option>)}
        </select>
      </label>
      <span className="opacity-60" title="Planned snaps">End · Mid · Axis (planned)</span>
      <span>Nav: {nav}</span>
      <div className="flex-1" />
      {selection.length > 0 && <span className="text-fg">{selection.length} selected</span>}
      {running > 0 && <Badge tone="info">{running} job{running > 1 ? "s" : ""} running</Badge>}
      {pluginErrors > 0 && <Badge tone="err">{pluginErrors} plugin error{pluginErrors > 1 ? "s" : ""}</Badge>}
      <span title="Where optimization jobs run">Backend: {state?.backend ?? "-"}</span>
      <span data-testid="save-state" title="Every edit is written to the command log and the project file immediately">
        {pending > 0 ? <span className="text-warn">Saving...</span> : <span>Saved · rev {state?.revision ?? 0}</span>}
      </span>
      <span className={clsx("flex items-center gap-1", connected ? "text-ok" : "text-err")} data-testid="connection">
        <span className={clsx("inline-block h-2 w-2 rounded-full", connected ? "bg-ok" : "bg-err")} />
        {connected ? "Connected" : "Server offline"}
      </span>
    </div>
  );
}

export function App() {
  const ready = useLab((s) => s.ready);
  const theme = useView((s) => s.theme);
  const [error, setError] = useState<string | null>(null);
  const keys = useRef(loadKeys());
  usePlaybackClock();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    const offPlayback = connectPlayback();
    const offEvolve = connectEvolve();
    useLab
      .getState()
      .init()
      .catch((e: Error) => setError(e.message));
    return () => {
      offPlayback();
      offEvolve();
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = isTypingTarget(e.target);
      const c = chord(e);
      if (c === "Ctrl+K") {
        e.preventDefault();
        hooks.focusCommandLine();
        return;
      }
      if (typing) return;
      const command = keys.current[c];
      if (command) {
        e.preventDefault();
        if (command === "SelNone" && useView.getState().measure) useView.getState().set({ measure: false });
        void execute(command);
        return;
      }
      if (c === "Enter" || c === "Space") {
        e.preventDefault();
        repeatLast();
        return;
      }
      // typing a letter anywhere starts a command, as in Rhino
      if (e.key.length === 1 && /[a-zA-Z]/.test(e.key) && !e.ctrlKey && !e.altKey && !e.metaKey) hooks.focusCommandLine();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (error) {
    return (
      <Empty title="CALFLAB cannot reach its server">
        {error}
        <div className="mt-2">Start it with <code>.\calflab.ps1 lab</code>, then reload this page.</div>
      </Empty>
    );
  }
  if (!ready) return <Empty title="Opening the project..." />;
  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <CommandLine />
      <div className="min-h-0 flex-1"><Dock /></div>
      <StatusBar />
      <CommandDialog />
      <ShortcutsDialog onChange={() => (keys.current = loadKeys())} />
      <Tour />
    </div>
  );
}
