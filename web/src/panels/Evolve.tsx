// Evolve workspace (Galapagos / Wallacei conventions): choose what to start
// from, set up the optimizer, watch fitness over generations and the MAP-Elites
// archive fill in, click a cell to replay that candidate and read its genes.
import { create } from "zustand";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import type { ArchiveView, EvolveHistoryEntry } from "@/api/types";
import { SchemaForm } from "@/components/SchemaForm";
import { Badge, Button, Empty, PanelScroll, Planned, Row, Section, fmt } from "@/components/ui";
import { onLabEvent, useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";

interface Candidate {
  id: string;
  generation: number;
  parents: string[];
  fitness: number;
  fitness_terms: Record<string, { value: number; weight: number; weighted: number }>;
  descriptors: Record<string, number>;
  metrics: Record<string, any>;
  genome: { values: Record<string, unknown> };
  mass_g: number;
  status: string;
}

type GeneValue = number | string | boolean;
type Ref = "current" | "parent" | "compare";

/** One gene of a candidate with its differences, as computed by the server. */
type GeneRow = {
  gene: string;
  label: string;
  group: string | null;
  unit: string | null;
  evolved: boolean;
  value: GeneValue;
  differs: boolean;
} & { [K in Ref]: GeneValue | null } & { [K in `${Ref}_delta`]: number | null } & { [K in `${Ref}_differs`]: boolean };

interface GeneView {
  candidate: string;
  parents: string[];
  parent: string; // a candidate id, or "start" for the run's starting design
  compare: string | null;
  genes: GeneRow[];
  overrides: { name: string; target: string; kind: string; param: string | null; value: number | null }[];
}

/** The part of a run record the Evolve views read. */
interface EvolveRun {
  id: string;
  parent: string | null;
  inputs: { start?: { source: "document" | "design"; design?: string; revision?: number } };
  overrides: unknown[];
}

interface EvolveStore {
  runId: string | null;
  run: EvolveRun | null;
  archive: ArchiveView | null;
  history: EvolveHistoryEntry[];
  candidate: Candidate | null;
  lineage: { id: string; generation: number; fitness: number }[];
  genes: GeneView | null;
  /** candidate kept as a reference column while other cells are clicked */
  pinned: string | null;
  /** baked design the next evolution starts from ("" = the working document) */
  startDesign: string;
  load: (runId: string) => Promise<void>;
  pick: (candidateId: string) => Promise<void>;
  pin: (candidateId: string | null) => Promise<void>;
}

const genesOf = (candidateId: string, pinned: string | null) =>
  api.get<GeneView>(`/api/candidates/${candidateId}/genes${pinned && pinned !== candidateId ? `?compare=${pinned}` : ""}`);

export const useEvolve = create<EvolveStore>((set, get) => ({
  runId: null,
  run: null,
  archive: null,
  history: [],
  candidate: null,
  lineage: [],
  genes: null,
  pinned: null,
  startDesign: "",
  load: async (runId) => {
    const v = await api.get<{ run: EvolveRun; archive: ArchiveView; history: EvolveHistoryEntry[] }>(`/api/evolve/${runId}`);
    set({ runId, run: v.run, archive: v.archive?.axes ? v.archive : null, history: v.history ?? [], candidate: null, lineage: [], genes: null, pinned: null });
  },
  pick: async (candidateId) => {
    const [candidate, lineage, genes] = await Promise.all([
      api.get<Candidate>(`/api/candidates/${candidateId}`),
      api.get<EvolveStore["lineage"]>(`/api/candidates/${candidateId}/lineage`),
      genesOf(candidateId, get().pinned),
    ]);
    set({ candidate, lineage, genes });
    // replay it in the viewport without touching the document
    await api.post(`/api/candidates/${candidateId}/simulate`);
  },
  pin: async (candidateId) => {
    set({ pinned: candidateId });
    const c = get().candidate;
    if (c) set({ genes: await genesOf(c.id, candidateId) });
  },
}));

export function connectEvolve(): () => void {
  return onLabEvent((e) => {
    if (e.type === "evolve.started") {
      useEvolve.setState({ runId: e.run_id, run: null, archive: null, history: [], candidate: null, lineage: [], genes: null, pinned: null });
      void api.get<EvolveRun>(`/api/runs/${e.run_id}`).then((run) => useEvolve.getState().runId === run.id && useEvolve.setState({ run })).catch(() => undefined);
    } else if (e.type === "state.changed" && useEvolve.getState().candidate) {
      // the "vs current design" column follows the document
      const s = useEvolve.getState();
      void genesOf(s.candidate!.id, s.pinned).then((genes) => useEvolve.getState().candidate?.id === genes.candidate && useEvolve.setState({ genes })).catch(() => undefined);
    } else if (e.type === "evolve.update" && useEvolve.getState().runId === e.run_id) {
      useEvolve.setState({ archive: e.archive, history: e.history });
    }
  });
}

// ---------------------------------------------------------------- setup
export function EvolvePanel() {
  const plugins = useLab((s) => s.plugins);
  const state = useLab((s) => s.state);
  const meta = useLab((s) => s.meta);
  const graph = useLab((s) => s.graph);
  const run = useLab((s) => s.run);
  const runs = useLab((s) => s.runs);
  const jobs = useLab((s) => s.jobs);
  const designs = useLab((s) => s.designs);
  const startDesign = useEvolve((s) => s.startDesign);
  const docOverrides = (state?.overrides ?? []).filter((o) => o.enabled).length;
  const optimizers = plugins.optimizer ?? [];
  const backends = plugins.compute_backend ?? [];
  const [optKey, setOptKey] = useState("map_elites_cma");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [duration, setDuration] = useState(4);
  const opt = optimizers.find((o) => o.key === optKey);
  const active = jobs.find((j) => j.kind === "evolve" && (j.status === "running" || j.status === "queued"));
  const fitnessNode = graph?.graph.nodes.find((n) => n.id === graph.graph.roles.fitness);
  const presetName = String(fitnessNode?.params.preset ?? "");
  const preset = meta?.fitness_presets[presetName];
  const evolveRuns = runs.filter((r) => r.kind === "evolve");
  const values = useMemo(() => {
    const d: Record<string, unknown> = {};
    for (const f of opt?.schema.fields ?? []) d[f.name] = f.default;
    return { ...d, ...params };
  }, [opt, params]);
  const budget = Number(values.generations ?? 0) * Number(values.batch_size ?? 0) * (1 + Number(values.inner_iterations ?? 0) * Number(values.inner_popsize ?? 0));

  const start = () =>
    void run("run_evolve", { optimizer: optKey, params, backend: state?.backend ?? "local", sim: { duration_s: duration, record_hz: 25 }, design: startDesign }).catch(() => undefined);

  return (
    <PanelScroll data-testid="evolve-panel">
      <div className="flex items-center gap-2 border-b border-line bg-bg p-2">
        {active ? (
          <>
            <Button variant="danger" onClick={() => void api.post(`/api/jobs/${active.id}/cancel`)}>Cancel</Button>
            <div className="h-1.5 flex-1 overflow-hidden rounded bg-bg3"><div className="h-full bg-accent" style={{ width: `${active.progress * 100}%` }} /></div>
            <span className="text-dim">{active.message}</span>
          </>
        ) : (
          <>
            <Button variant="primary" disabled={!opt || opt.stub} onClick={start} data-testid="evolve-start">Start evolution</Button>
            <span className="text-dim">about {budget} rollouts</span>
          </>
        )}
      </div>
      <Section title="Start from">
        <Row label="Starting design" title="The first candidate is this design; the others vary its evolvable genes">
          <select className="min-w-0 flex-1" value={startDesign} data-testid="evolve-start-from" onChange={(e) => useEvolve.setState({ startDesign: e.target.value })}>
            <option value="">Working document</option>
            {designs.map((d) => <option key={d.id} value={d.id}>{d.id}</option>)}
          </select>
        </Row>
        <div className="text-[11px] text-dim" data-testid="evolve-start-note">
          {startDesign
            ? "Body, gait and overrides come from the baked design; the working document is not changed. The fitness preset and rollout length below still apply."
            : `The working design as it is now${docOverrides ? `, with its ${docOverrides} enabled override${docOverrides > 1 ? "s" : ""}` : ""}.`}{" "}
          Overrides are not genes: they are built into every candidate unchanged, so an overridden part does not evolve.
        </div>
      </Section>
      <Section title="Optimizer">
        <Row label="Optimizer">
          <select className="min-w-0 flex-1" value={optKey} onChange={(e) => { setOptKey(e.target.value); setParams({}); }}>
            {optimizers.map((o) => <option key={o.key} value={o.key}>{o.label}{o.stub ? " (planned)" : ""}</option>)}
          </select>
        </Row>
        {opt && <div className="mb-1 text-dim">{opt.description} {opt.stub && <Planned />}</div>}
        {opt && <SchemaForm schema={opt.schema} values={values} disabled={opt.stub} onChange={(patch) => setParams((p) => ({ ...p, ...patch }))} />}
      </Section>
      <Section title="Evaluation">
        <Row label="Rollout length" title="Simulated seconds per evaluation">
          <input type="range" className="min-w-0 flex-1" min={1} max={10} step={0.5} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
          <span className="w-10 text-right">{duration} s</span>
        </Row>
        <Row label="Fitness preset">
          <select
            className="min-w-0 flex-1"
            value={presetName}
            onChange={(e) => fitnessNode && void run("set_node_params", { node: fitnessNode.id, params: { preset: e.target.value } })}
          >
            {Object.keys(meta?.fitness_presets ?? {}).map((k) => <option key={k}>{k}</option>)}
          </select>
        </Row>
        {preset && (
          <div className="rounded border border-line bg-bg p-1 text-[11px]">
            <div className="text-dim">{preset.name}@{preset.version}: {preset.description}</div>
            {preset.terms.map((t: any) => (
              <div key={t.term} className="flex justify-between font-mono text-[10px]">
                <span>{t.term}{Object.keys(t.params ?? {}).length ? ` ${JSON.stringify(t.params)}` : ""}</span>
                <span>x {t.weight}</span>
              </div>
            ))}
          </div>
        )}
        <Row label="Compute backend">
          <select className="min-w-0 flex-1" value={state?.backend ?? "local"} onChange={(e) => void run("set_backend", { backend: e.target.value })}>
            {backends.map((b) => <option key={b.key} value={b.key} disabled={b.stub}>{b.label}{b.stub ? " (planned)" : ""}</option>)}
          </select>
        </Row>
      </Section>
      <Section title="Past evolution runs">
        {!evolveRuns.length && <div className="text-dim">None yet. Results are stored in the registry with full lineage.</div>}
        {evolveRuns.map((r) => (
          <div key={r.id} className="flex cursor-default items-center gap-2 hover:bg-bg3" onClick={() => void useEvolve.getState().load(r.id)} data-evolve-run={r.id}>
            <span className="truncate font-mono text-[11px]">{r.id}</span>
            <Badge tone={r.status === "done" ? "ok" : "neutral"}>{r.status}</Badge>
            {r.parent && <span className="truncate text-[10px] text-dim" title={`Started from the baked design ${r.parent}`}>from {r.parent}</span>}
            <span className="ml-auto text-dim">{fmt(r.fitness, 3)}</span>
          </div>
        ))}
      </Section>
      <Section title="More views">
        <div className="flex flex-col gap-1 text-dim">
          <span><Planned /> Pareto front and parallel coordinates</span>
          <span><Planned /> Interactive selection: pick parents from a grid of animated candidates</span>
          <span><Planned /> Pin and compare candidates side by side</span>
        </div>
      </Section>
    </PanelScroll>
  );
}

// ---------------------------------------------------------------- archive
function fitnessColor(f: number, lo: number, hi: number): string {
  const t = hi > lo ? (f - lo) / (hi - lo) : 1;
  // dark blue -> teal -> yellow (viridis-like)
  const h = 260 - 200 * t;
  const l = 22 + 40 * t;
  return `hsl(${h} 70% ${l}%)`;
}

function Heatmap({ archive }: { archive: ArchiveView }) {
  const candidate = useEvolve((s) => s.candidate);
  const log = useLab((s) => s.log);
  const [ax, ay] = archive.axes;
  const cellPx = Math.max(14, Math.min(34, Math.floor(420 / Math.max(ax.cells, ay.cells))));
  const fits = archive.cells.map((c) => c.fitness);
  const lo = Math.min(...fits), hi = Math.max(...fits);
  const byKey = new Map(archive.cells.map((c) => [`${c.i},${c.j}`, c]));
  const tick = (a: typeof ax, k: number) => (a.range[0] + ((a.range[1] - a.range[0]) * k) / a.cells).toFixed(a.range[1] > 20 ? 0 : 1);
  const W = ax.cells * cellPx, H = ay.cells * cellPx;
  return (
    <svg width={W + 70} height={H + 46} data-testid="heatmap">
      <g transform="translate(54,6)">
        {Array.from({ length: ax.cells }).map((_, i) =>
          Array.from({ length: ay.cells }).map((__, j) => {
            const c = byKey.get(`${i},${j}`);
            const sel = c && candidate?.id === c.candidate;
            return (
              <rect
                key={`${i},${j}`}
                x={i * cellPx}
                y={H - (j + 1) * cellPx}
                width={cellPx - 1}
                height={cellPx - 1}
                fill={c ? fitnessColor(c.fitness, lo, hi) : "var(--bg-3)"}
                stroke={sel ? "var(--accent)" : "none"}
                strokeWidth={2}
                style={{ cursor: c ? "pointer" : "default" }}
                data-cell={c ? c.candidate : undefined}
                onClick={() => c && void useEvolve.getState().pick(c.candidate).catch((e) => log("error", e.message))}
              >
                {c && <title>{`${c.candidate}\nfitness ${c.fitness.toFixed(3)}\n${ax.label} ${fmt(c.descriptors[ax.key])} ${ax.unit}\n${ay.label} ${fmt(c.descriptors[ay.key])} ${ay.unit}\nClick to load in the viewport`}</title>}
              </rect>
            );
          }),
        )}
        {[0, Math.floor(ax.cells / 2), ax.cells].map((k) => (
          <text key={k} x={k * cellPx} y={H + 12} fontSize={9} fill="var(--fg-dim)" textAnchor="middle">{tick(ax, k)}</text>
        ))}
        {[0, Math.floor(ay.cells / 2), ay.cells].map((k) => (
          <text key={k} x={-4} y={H - k * cellPx + 3} fontSize={9} fill="var(--fg-dim)" textAnchor="end">{tick(ay, k)}</text>
        ))}
        <text x={W / 2} y={H + 28} fontSize={10} fill="var(--fg)" textAnchor="middle">{ax.label} ({ax.unit})</text>
        <text transform={`translate(-40,${H / 2}) rotate(-90)`} fontSize={10} fill="var(--fg)" textAnchor="middle">{ay.label} ({ay.unit})</text>
      </g>
    </svg>
  );
}

function FitnessChart({ history }: { history: EvolveHistoryEntry[] }) {
  const W = 300, H = 130, m = { l: 34, r: 8, t: 8, b: 18 };
  const vals = history.flatMap((h) => [h.best, h.gen_mean, h.mean].filter((v): v is number => v !== null));
  if (!vals.length) return null;
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo === hi) { lo -= 0.5; hi += 0.5; }
  const x = (g: number) => m.l + (history.length > 1 ? (g / (history.length - 1)) * (W - m.l - m.r) : 0);
  const y = (v: number) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
  const path = (key: "best" | "gen_mean" | "mean") =>
    history.filter((h) => h[key] !== null).map((h, i) => `${i ? "L" : "M"}${x(h.generation)},${y(h[key] as number)}`).join(" ");
  return (
    <svg width={W} height={H} data-testid="fitness-chart">
      <rect x={m.l} y={m.t} width={W - m.l - m.r} height={H - m.t - m.b} fill="none" stroke="var(--line)" />
      <path d={path("best")} fill="none" stroke="var(--accent)" strokeWidth={1.6} />
      <path d={path("mean")} fill="none" stroke="var(--accent-2)" strokeWidth={1.2} />
      <path d={path("gen_mean")} fill="none" stroke="var(--fg-dim)" strokeWidth={1} strokeDasharray="3 3" />
      <text x={m.l - 3} y={m.t + 8} fontSize={9} fill="var(--fg-dim)" textAnchor="end">{hi.toFixed(2)}</text>
      <text x={m.l - 3} y={H - m.b} fontSize={9} fill="var(--fg-dim)" textAnchor="end">{lo.toFixed(2)}</text>
      <text x={W / 2} y={H - 4} fontSize={9} fill="var(--fg-dim)" textAnchor="middle">generation (best · archive mean · generation mean)</text>
    </svg>
  );
}

const shortId = (id: string) => id.split("-").slice(-2).join("-");

function GeneTable({ view }: { view: GeneView }) {
  const [all, setAll] = useState(false);
  const refs: [Ref, string][] = [
    ["current", "vs current design"],
    ["parent", view.parent === "start" ? "vs starting design" : `vs parent ${shortId(view.parent)}`],
  ];
  if (view.compare) refs.push(["compare", `vs pinned ${shortId(view.compare)}`]);
  const rows = all ? view.genes : view.genes.filter((g) => g.differs);
  const cell = (g: GeneRow, ref: Ref) => {
    const was = g[ref];
    if (was === null) return <span className="text-dim">-</span>;
    if (!g[`${ref}_differs`]) return <span className="text-dim">=</span>;
    const d = g[`${ref}_delta`];
    return <span className="text-accent" title={`there: ${fmt(was)}${g.unit ? ` ${g.unit}` : ""}`}>{d === null ? `not ${fmt(was)}` : `${d > 0 ? "+" : ""}${fmt(d, 1)}`}</span>;
  };
  return (
    <div data-testid="candidate-genes">
      <div className="mt-1 flex items-center justify-between">
        <span className="text-[10px] font-semibold text-dim uppercase">Genes ({rows.length} of {view.genes.length})</span>
        <label className="flex items-center gap-1 text-[10px] text-dim"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />show unchanged</label>
      </div>
      <table className="w-full font-mono text-[10px]">
        <thead className="text-left text-dim">
          <tr><th className="font-normal">gene</th><th className="text-right font-normal">this</th>{refs.map(([k, label]) => <th key={k} className="text-right font-normal">{label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((g) => (
            <tr key={g.gene} className="border-t border-line/40" data-gene={g.gene} title={g.evolved ? "Evolved in this run" : "Not evolved: the same in every candidate of this run"}>
              <td className={g.evolved ? "" : "text-dim"}>{g.gene}</td>
              <td className="text-right">{fmt(g.value, 1)}{g.unit ? ` ${g.unit}` : ""}</td>
              {refs.map(([k]) => <td key={k} className="text-right">{cell(g, k)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <div className="text-dim">Identical to the current design{view.compare ? ", its parent and the pinned candidate" : " and its parent"}.</div>}
      {view.overrides.length > 0 && (
        <div className="mt-1 text-[10px] text-dim" data-testid="candidate-overrides">
          Fixed by override in every candidate of this run:{" "}
          {view.overrides.map((o) => (o.kind === "param" ? `${o.target}.${o.param} = ${fmt(o.value)}` : o.kind === "mass" ? `${o.target} (weighed ${fmt(o.value)} g)` : o.kind === "material" ? `${o.target} (material)` : `${o.target} (pushed geometry)`)).join(", ")}
        </div>
      )}
    </div>
  );
}

export function ArchivePanel() {
  const { runId, run: evolveRun, archive, history, candidate, lineage, genes, pinned } = useEvolve();
  const runs = useLab((s) => s.runs);
  const run = useLab((s) => s.run);
  useEffect(() => {
    if (runId) return;
    const latest = runs.find((r) => r.kind === "evolve");
    if (latest) void useEvolve.getState().load(latest.id).catch(() => undefined);
  }, [runId, runs]);

  if (!archive || !archive.cells.length) {
    return (
      <Empty title={runId ? "Waiting for the first generation..." : "No archive yet"}>
        MAP-Elites keeps the best design found for every combination of two behavior descriptors (for example leg length and
        stride frequency). Press <b>Start evolution</b> in the Evolve panel; cells fill in live and each one is clickable.
      </Empty>
    );
  }
  const last = history[history.length - 1];
  return (
    <div className="flex h-full" data-testid="archive-panel">
      <div className="overflow-auto p-2">
        <div className="font-mono text-[10px] text-dim">{runId}</div>
        <div className="mb-1 text-[10px] text-dim" data-testid="evolve-started-from">
          {evolveRun?.inputs.start?.source === "design"
            ? <>Started from baked design <span className="font-mono text-accent2">{evolveRun.inputs.start.design}</span></>
            : evolveRun?.inputs.start
              ? `Started from the working document (revision ${evolveRun.inputs.start.revision})`
              : evolveRun ? "Started from the working document" : ""}
          {evolveRun && evolveRun.overrides.length > 0 && ` · ${evolveRun.overrides.length} override${evolveRun.overrides.length > 1 ? "s" : ""} in every candidate`}
        </div>
        <Heatmap archive={archive} />
      </div>
      <PanelScroll className="min-w-[320px] flex-1 border-l border-line">
        <Section title="Fitness over generations">
          <FitnessChart history={history} />
          {last && (
            <div className="mt-1 grid grid-cols-4 gap-1 text-center">
              {[["Generation", last.generation + 1], ["Elites", last.elites], ["Coverage", `${(last.coverage * 100).toFixed(0)}%`], ["Rollouts", last.evals]].map(([k, v]) => (
                <div key={k} className="rounded bg-bg p-1"><div className="text-[10px] text-dim">{k}</div><div className="font-semibold">{v}</div></div>
              ))}
            </div>
          )}
        </Section>
        {candidate ? (
          <Section
            title="Selected candidate"
            right={<Button size="sm" variant="primary" title="Load this genome and gait into the document (undoable)" onClick={() => void run("adopt_candidate", { id: candidate.id }).then(() => usePlayback.getState().clear())} data-testid="adopt">Adopt into design</Button>}
          >
            <div className="selectable font-mono text-[11px] text-accent">{candidate.id}</div>
            <Row label="Fitness"><b>{candidate.fitness.toFixed(3)}</b></Row>
            <Row label="Speed"><span>{fmt(candidate.metrics.speed_mps, 3)} m/s</span></Row>
            <Row label="Mass"><span>{fmt(candidate.mass_g, 0)} g</span></Row>
            {Object.entries(candidate.descriptors).map(([k, v]) => <Row key={k} label={k.replace(/_/g, " ")}><span>{fmt(v)}</span></Row>)}
            <div className="mt-1 text-[10px] font-semibold text-dim uppercase">Fitness terms</div>
            {Object.entries(candidate.fitness_terms).map(([k, t]) => (
              <div key={k} className="flex justify-between font-mono text-[10px]">
                <span>{k}</span><span>{t.value.toFixed(2)} x {t.weight} = {t.weighted.toFixed(2)}</span>
              </div>
            ))}
            <div className="mt-1 text-[10px] font-semibold text-dim uppercase">Lineage ({lineage.length})</div>
            {lineage.map((l) => (
              <div key={l.id} className="flex justify-between font-mono text-[10px]">
                <span>g{l.generation} {shortId(l.id)}</span><span>{l.fitness.toFixed(3)}</span>
              </div>
            ))}
            <div className="mt-1 flex items-center gap-1">
              {pinned === candidate.id ? (
                <span className="text-[10px] text-dim">Pinned. Click another cell to compare it with this one.</span>
              ) : (
                <Button size="sm" title="Keep this candidate as a comparison column while you click other cells" onClick={() => void useEvolve.getState().pin(candidate.id)} data-testid="pin">Pin to compare</Button>
              )}
              {pinned && <Button size="sm" variant="ghost" onClick={() => void useEvolve.getState().pin(null)}>Unpin {shortId(pinned)}</Button>}
            </div>
            {genes && genes.candidate === candidate.id && <GeneTable view={genes} />}
            <div className="mt-1 text-[10px] text-dim">
              The viewport is replaying this candidate. The document is unchanged until you adopt it.
            </div>
          </Section>
        ) : (
          <div className="p-3 text-dim">Click a cell to replay that candidate in the viewport and see its genes and lineage.</div>
        )}
      </PanelScroll>
    </div>
  );
}
