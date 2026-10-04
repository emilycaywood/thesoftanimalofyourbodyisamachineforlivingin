// Command parameter dialog, shortcut editor and the first-run guided tour.
import { useEffect, useMemo, useState } from "react";
import { DEFAULT_KEYS, chord, loadKeys, resetKeys, saveKeys } from "@/commands/keys";
import { allCommands, execute, hooks, type UnifiedCommand } from "@/commands/registry";
import { SchemaForm } from "@/components/SchemaForm";
import { Button, Kbd } from "@/components/ui";
import { useLab } from "@/store/lab";
import { useView } from "@/store/view";

function Modal({ title, onClose, children, width = 420 }: { title: string; onClose: () => void; children: React.ReactNode; width?: number }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-24" onMouseDown={onClose}>
      <div className="rounded-md border border-line bg-bg2 shadow-2xl" style={{ width }} onMouseDown={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <div className="border-b border-line px-3 py-2 text-[13px] font-semibold">{title}</div>
        {children}
      </div>
    </div>
  );
}

export function CommandDialog() {
  const [cmd, setCmd] = useState<UnifiedCommand | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  useEffect(() => {
    hooks.openDialog = (c, initial) => {
      const d: Record<string, unknown> = {};
      for (const f of c.schema?.fields ?? []) d[f.name] = f.default;
      setValues({ ...d, ...initial });
      setCmd(c);
    };
  }, []);
  if (!cmd?.schema) return null;
  const go = () => {
    const c = cmd;
    setCmd(null);
    void execute(c.name, values);
  };
  return (
    <Modal title={cmd.label} onClose={() => setCmd(null)}>
      <div className="p-3" onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLElement).tagName !== "TEXTAREA" && setTimeout(go, 0)} data-testid="command-dialog">
        <div className="mb-2 text-dim">{cmd.description}</div>
        <SchemaForm schema={cmd.schema} values={values} onChange={(patch) => setValues((v) => ({ ...v, ...patch }))} />
      </div>
      <div className="flex justify-end gap-2 border-t border-line px-3 py-2">
        <Button onClick={() => setCmd(null)}>Cancel</Button>
        <Button variant="primary" onClick={go} data-testid="dialog-run">Run {cmd.name}</Button>
      </div>
    </Modal>
  );
}

export function ShortcutsDialog({ onChange }: { onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const [keys, setKeys] = useState(loadKeys);
  const [capturing, setCapturing] = useState<string | null>(null);
  const server = useLab((s) => s.commands);
  const commands = useMemo(() => allCommands(server), [server]);
  const nav = useView((s) => s.nav);
  useEffect(() => {
    hooks.openShortcuts = () => {
      setKeys(loadKeys());
      setOpen(true);
    };
  }, []);
  useEffect(() => {
    if (!capturing) return;
    const h = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const c = chord(e);
      if (!c) return;
      const next: Record<string, string> = {};
      for (const [k, v] of Object.entries(keys)) if (v !== capturing && k !== c) next[k] = v;
      if (c !== "Escape") next[c] = capturing;
      setKeys(next);
      saveKeys(next);
      setCapturing(null);
      onChange();
    };
    window.addEventListener("keydown", h, true);
    return () => window.removeEventListener("keydown", h, true);
  }, [capturing, keys, onChange]);
  if (!open) return null;
  const byCommand = new Map(Object.entries(keys).filter(([, v]) => v).map(([k, v]) => [v, k]));
  const listed = commands.filter((c) => byCommand.has(c.name) || Object.values(DEFAULT_KEYS).includes(c.name));
  return (
    <Modal title="Keyboard shortcuts and navigation" onClose={() => setOpen(false)} width={560}>
      <div className="max-h-[60vh] overflow-auto p-3">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-dim">Viewport navigation</span>
          <select value={nav} onChange={(e) => useView.getState().set({ nav: e.target.value as "rhino" | "blender" | "fusion" })}>
            <option value="rhino">Rhino: right-drag orbit, Shift+right-drag pan, wheel zoom</option>
            <option value="blender">Blender: middle-drag orbit, Shift+middle-drag pan, wheel zoom</option>
            <option value="fusion">Fusion: middle-drag pan, Shift+middle-drag orbit, wheel zoom</option>
          </select>
        </div>
        <div className="mb-2 text-dim">
          Left-drag selects: left-to-right is a window (fully inside), right-to-left is a crossing. <Kbd>Enter</Kbd> or <Kbd>Space</Kbd> on an
          empty command line repeats the last command. Click a shortcut to rebind it (Esc clears).
        </div>
        <table className="w-full">
          <tbody>
            {listed.map((c) => (
              <tr key={c.name} className="border-t border-line/40">
                <td className="py-0.5 font-mono">{c.name}</td>
                <td className="text-dim">{c.label}</td>
                <td className="text-right">
                  <button className="rounded border border-line bg-bg px-2 font-mono hover:border-accent2" onClick={() => setCapturing(c.name)}>
                    {capturing === c.name ? "press keys..." : (byCommand.get(c.name) ?? "none")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex justify-between border-t border-line px-3 py-2">
        <Button onClick={() => { resetKeys(); setKeys(loadKeys()); onChange(); }}>Reset to defaults</Button>
        <Button variant="primary" onClick={() => setOpen(false)}>Done</Button>
      </div>
    </Modal>
  );
}

const TOUR: { title: string; body: string }[] = [
  { title: "Welcome to CALFLAB", body: "This is the sample project with the reference calf. One project and one scene are shared by every workspace, and by Rhino, Blender and notebooks if you connect them." },
  { title: "Workspaces", body: "The tabs at the top (Form, Mechanism, Simulate, Evolve, Fabricate, Wire, Journal...) are different dock layouts over the same design. Panels can be dragged and re-docked; your layout is remembered." },
  { title: "Viewport", body: "Navigate like Rhino: right-drag orbits, Shift+right-drag pans, the wheel zooms. Left-click selects; drag left-to-right for a window, right-to-left for a crossing. Change the preset under Shortcuts (F1)." },
  { title: "Parametric and explicit", body: "Sliders in Form change genes. Select a leg segment and drag its gumball handle to make an explicit override: it is listed in Properties and Overrides, and can be removed or internalized into the gene." },
  { title: "Command line", body: "Every action is a named command. Type in the viewport or press Ctrl+K: Simulate, Bake, ZoomExtents, DisplayGhosted... Enter or Space repeats the last command. Ctrl+Z undoes for every connected client." },
  { title: "Simulate, evolve, record", body: "Press F5 to simulate and scrub the result on the timeline. Evolve fills a MAP-Elites archive you can click through. Press B to bake a design. Every run is recorded with its inputs, seed and code version. Component specs are unverified until you check them." },
];

export function Tour() {
  const done = useView((s) => s.tourDone);
  const [step, setStep] = useState<number | null>(null);
  useEffect(() => {
    hooks.startTour = () => setStep(0);
    if (!done) setStep(0);
  }, [done]);
  if (step === null) return null;
  const finish = () => {
    setStep(null);
    useView.getState().set({ tourDone: true });
  };
  const s = TOUR[step];
  return (
    <div className="fixed right-4 bottom-10 z-50 w-[360px] rounded-md border border-accent bg-bg2 shadow-2xl" data-testid="tour">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <span className="text-[13px] font-semibold">{s.title}</span>
        <span className="text-dim">{step + 1} / {TOUR.length}</span>
      </div>
      <div className="p-3 leading-relaxed">{s.body}</div>
      <div className="flex justify-between border-t border-line px-3 py-2">
        <Button variant="ghost" onClick={finish} data-testid="tour-skip">Skip tour</Button>
        <div className="flex gap-2">
          {step > 0 && <Button onClick={() => setStep(step - 1)}>Back</Button>}
          {step < TOUR.length - 1 ? (
            <Button variant="primary" onClick={() => setStep(step + 1)}>Next</Button>
          ) : (
            <Button variant="primary" onClick={finish}>Start working</Button>
          )}
        </div>
      </div>
    </div>
  );
}
