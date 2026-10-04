// Layers, scene tree, console, job queue, runs, designs, overrides.
import clsx from "clsx";
import { Eye, EyeOff, Lock, LockOpen, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import { api } from "@/api/client";
import { execute, replayRun } from "@/commands/registry";
import { Badge, Button, Empty, IconButton, Kbd, PanelScroll, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";
import { useView } from "@/store/view";

// ---------------------------------------------------------------- layers
export function LayersPanel() {
  const layers = useLab((s) => s.state?.layers);
  const meta = useLab((s) => s.meta);
  const run = useLab((s) => s.run);
  const massByLayer = useLab((s) => s.scene?.mass.by_layer_g);
  if (!layers || !meta) return <Empty title="Layers" />;
  return (
    <PanelScroll>
      {meta.layers.map(({ name }) => {
        const l = layers[name];
        if (!l) return null;
        return (
          <div key={name} className="flex h-6 items-center gap-1 border-b border-line/50 px-1" data-layer={name}>
            <IconButton title={l.visible ? "Hide layer" : "Show layer"} onClick={() => void run("set_layer", { layer: name, visible: !l.visible })}>
              {l.visible ? <Eye size={13} /> : <EyeOff size={13} className="text-dim" />}
            </IconButton>
            <IconButton title={l.locked ? "Unlock layer" : "Lock layer (not selectable)"} onClick={() => void run("set_layer", { layer: name, locked: !l.locked })}>
              {l.locked ? <Lock size={12} className="text-warn" /> : <LockOpen size={12} className="text-dim" />}
            </IconButton>
            <input
              type="color"
              className="h-4 w-5 cursor-pointer border-0 bg-transparent p-0"
              value={l.color}
              title="Layer colour"
              onChange={(e) => void run("set_layer", { layer: name, color: e.target.value })}
            />
            <span className={clsx("flex-1 truncate", !l.visible && "text-dim")}>{name}</span>
            <span className="text-[10px] text-dim">{massByLayer?.[name] ? `${fmt(massByLayer[name], 0)} g` : ""}</span>
          </div>
        );
      })}
    </PanelScroll>
  );
}

// ---------------------------------------------------------------- scene tree
export function TreePanel() {
  const scene = useLab((s) => s.scene);
  const selection = useView((s) => s.selection);
  const hidden = useView((s) => s.hidden);
  const children = useMemo(() => {
    const m = new Map<string | null, string[]>();
    for (const b of scene?.bodies ?? []) m.set(b.parent, [...(m.get(b.parent) ?? []), b.id]);
    return m;
  }, [scene]);
  if (!scene) return <Empty title="Scene tree">The parts of the design appear here by their stable IDs.</Empty>;
  const jointOf = new Map(scene.joints.map((j) => [j.body, j]));
  const render = (id: string, depth: number): React.ReactNode => {
    const joint = jointOf.get(id);
    return (
      <div key={id}>
        <div
          className={clsx(
            "flex h-5 cursor-default items-center gap-1 pr-1 hover:bg-bg3",
            selection.includes(id) && "bg-accent/25",
            hidden.includes(id) && "opacity-40",
          )}
          style={{ paddingLeft: 6 + depth * 12 }}
          data-tree-id={id}
          onClick={(e) => useView.getState().select([id], e.shiftKey || e.ctrlKey)}
          onDoubleClick={() => useView.getState().requestCamera("selected")}
        >
          <span className="truncate font-mono text-[11px]">{id}</span>
          {joint && (
            <span
              className={clsx("ml-auto truncate text-[10px] text-dim hover:text-accent2", selection.includes(joint.id) && "text-accent")}
              title={`Joint ${joint.id}`}
              onClick={(e) => {
                e.stopPropagation();
                useView.getState().select([joint.id], e.shiftKey || e.ctrlKey);
              }}
            >
              {joint.id.replace("joint.", "")}
            </span>
          )}
        </div>
        {(children.get(id) ?? []).map((c) => render(c, depth + 1))}
      </div>
    );
  };
  return <PanelScroll data-testid="scene-tree">{(children.get(null) ?? []).map((r) => render(r, 0))}</PanelScroll>;
}

// ---------------------------------------------------------------- console
export function ConsolePanel() {
  const logs = useLab((s) => s.logs);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // braces matter: scrollIntoView returns a Promise in current browsers, and
    // React would treat a returned value as the effect's cleanup function
    end.current?.scrollIntoView({ block: "end" });
  }, [logs.length]);
  if (!logs.length) {
    return (
      <Empty title="Log console">
        Commands, results and errors appear here. Type a command above, e.g. <Kbd>Simulate</Kbd>, or press <Kbd>F5</Kbd>.
      </Empty>
    );
  }
  return (
    <PanelScroll className="selectable p-1 font-mono text-[11px]">
      {logs.map((l) => (
        <div key={l.id} className={clsx("whitespace-pre-wrap", l.level === "error" && "text-err", l.level === "warn" && "text-warn", l.level === "cmd" && "text-accent2")}>
          <span className="text-dim">{l.time}</span> {l.level === "cmd" ? "> " : `[${l.source}] `}
          {l.message}
        </div>
      ))}
      <div ref={end} />
    </PanelScroll>
  );
}

// ---------------------------------------------------------------- jobs
export function JobsPanel() {
  const jobs = useLab((s) => s.jobs);
  const log = useLab((s) => s.log);
  if (!jobs.length) {
    return (
      <Empty title="Job queue">
        Simulations, evolution runs and exports run here in the background with progress and cancel. Start one with <Kbd>F5</Kbd>.
      </Empty>
    );
  }
  const act = (id: string, what: "cancel" | "retry") => void api.post(`/api/jobs/${id}/${what}`).catch((e) => log("error", e.message));
  return (
    <PanelScroll>
      {jobs.map((j) => (
        <div key={j.id} className="flex h-7 items-center gap-2 border-b border-line/50 px-2" data-job-status={j.status}>
          <Badge tone={j.status === "done" ? "ok" : j.status === "failed" ? "err" : j.status === "running" ? "info" : "neutral"}>{j.status}</Badge>
          <span className="w-40 truncate">{j.title}</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded bg-bg3">
            <div className={clsx("h-full", j.status === "failed" ? "bg-err" : "bg-accent")} style={{ width: `${Math.round(j.progress * 100)}%` }} />
          </div>
          <span className="w-44 truncate text-dim" title={j.error ?? j.message}>{j.error ?? j.message}</span>
          <span className="w-12 text-right text-dim">{j.duration_s ? `${j.duration_s.toFixed(1)} s` : ""}</span>
          <span className="w-12 text-dim">{j.backend}</span>
          {j.status === "running" || j.status === "queued" ? (
            <IconButton title="Cancel" onClick={() => act(j.id, "cancel")}><X size={13} /></IconButton>
          ) : (
            <IconButton title="Retry" onClick={() => act(j.id, "retry")}><RotateCcw size={12} /></IconButton>
          )}
        </div>
      ))}
    </PanelScroll>
  );
}

// ---------------------------------------------------------------- runs
export function RunsPanel() {
  const runs = useLab((s) => s.runs);
  const current = usePlayback((s) => s.runId);
  const sims = runs.filter((r) => r.kind === "sim");
  if (!sims.length) {
    return (
      <Empty title="No simulation runs yet" action={<Button variant="primary" onClick={() => void execute("RunSim")}>Simulate (F5)</Button>}>
        Every run is recorded with its genome, seed, code version and metrics, and can be replayed here.
      </Empty>
    );
  }
  return (
    <PanelScroll>
      <table className="w-full">
        <thead className="sticky top-0 bg-bg text-left text-[10px] text-dim uppercase">
          <tr><th className="px-2">Run</th><th>Title</th><th>Fitness</th><th>Seed</th><th>Time</th></tr>
        </thead>
        <tbody>
          {sims.map((r) => (
            <tr
              key={r.id}
              className={clsx("cursor-pointer hover:bg-bg3", current === r.id && "bg-accent/30 font-semibold")}
              data-run={r.id}
              data-current={current === r.id || undefined}
              onClick={() => void replayRun(r.id)}
              title="Click to replay this run in the viewport"
            >
              <td className="px-2 font-mono text-[11px]">{current === r.id ? "\u25B6 " : ""}{r.id}</td>
              <td className="truncate">{r.title}</td>
              <td>{fmt(r.fitness, 3)}</td>
              <td>{r.seed ?? "-"}</td>
              <td className="text-dim">{r.duration_s.toFixed(2)} s</td>
            </tr>
          ))}
        </tbody>
      </table>
    </PanelScroll>
  );
}

// ---------------------------------------------------------------- designs
export function DesignsPanel() {
  const designs = useLab((s) => s.designs);
  if (!designs.length) {
    return (
      <Empty title="No designs baked yet" action={<Button variant="primary" onClick={() => void execute("Bake")}>Bake (B)</Button>}>
        Bake freezes the current state into an immutable, named, versioned Design you can cite: press <Kbd>B</Kbd> or click Bake.
      </Empty>
    );
  }
  return (
    <PanelScroll className="p-1">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-1">
        {designs.map((d) => (
          <div key={d.id} className="rounded border border-line bg-bg p-1" data-design={d.id} title={d.note}>
            <div className="flex aspect-[4/3] items-center justify-center overflow-hidden rounded bg-bg3">
              {d.thumbnail ? <img src={api.fileUrl(d.thumbnail)} className="h-full w-full object-cover" alt={d.id} /> : <span className="text-dim">no thumbnail</span>}
            </div>
            <div className="selectable mt-1 truncate font-mono text-[11px]">{d.id}</div>
            <div className="flex justify-between text-[10px] text-dim">
              <span>{fmt(d.mass_g, 0)} g</span>
              <span>{d.created.slice(0, 10)}</span>
            </div>
          </div>
        ))}
      </div>
    </PanelScroll>
  );
}

// ---------------------------------------------------------------- overrides
export function OverridesPanel() {
  const overrides = useLab((s) => s.state?.overrides) ?? [];
  const run = useLab((s) => s.run);
  if (!overrides.length) {
    return (
      <Empty title="No overrides">
        Direct edits (a gumball drag, a typed value, geometry pushed from Rhino) are stored here as named records layered over the
        parametric design. Select a leg segment and drag its handle to make one.
      </Empty>
    );
  }
  return (
    <PanelScroll>
      {overrides.map((o) => (
        <div key={o.id} className="flex items-center gap-1 border-b border-line/50 px-2 py-1" data-override={o.id}>
          <input type="checkbox" checked={o.enabled} title="Enable / disable" onChange={() => void run("toggle_override", { id: o.id })} />
          <div className="min-w-0 flex-1">
            <div className="truncate">{o.name}</div>
            <div className="truncate font-mono text-[10px] text-dim">
              {o.target}{o.kind === "param" ? `.${o.param} = ${fmt(o.value)}` : ` · geometry (${o.asset})`} · from {o.source}
            </div>
          </div>
          {o.kind === "param" && (
            <Button size="sm" title="Write this value into the gene that drives it, then remove the override" onClick={() => void run("internalize_override", { id: o.id }).catch(() => undefined)}>
              Internalize
            </Button>
          )}
          <Button size="sm" variant="danger" onClick={() => void run("remove_override", { id: o.id })}>Remove</Button>
        </div>
      ))}
      <div className="p-2">
        <Button size="sm" onClick={() => void run("clear_overrides")}>Remove all</Button>
      </div>
    </PanelScroll>
  );
}
