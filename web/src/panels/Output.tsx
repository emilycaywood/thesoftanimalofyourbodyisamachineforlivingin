// Fabricate, Wire and Journal workspaces. Exporters and analyses are plugins;
// their forms come from schemas and their results from the server.
import { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import type { Job, PluginInfo } from "@/api/types";
import { execute } from "@/commands/registry";
import { SchemaForm } from "@/components/SchemaForm";
import { Badge, Button, Empty, PanelScroll, Planned, Row, Section, Unverified, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";
import { useView } from "@/store/view";

function useAnalysis<T>(key: string, params: Record<string, unknown> = {}): T | null {
  const revision = useLab((s) => s.state?.revision);
  const runCount = useLab((s) => s.runs.length);
  const [data, setData] = useState<T | null>(null);
  const body = JSON.stringify(params);
  useEffect(() => {
    let live = true;
    void api.post<T>(`/api/analysis/${key}`, JSON.parse(body)).then((d) => live && setData(d)).catch(() => live && setData(null));
    return () => {
      live = false;
    };
  }, [key, body, revision, runCount]);
  return data;
}

// ---------------------------------------------------------------- fabricate
function ExporterCard({ p, selection }: { p: PluginInfo; selection: string[] }) {
  const run = useLab((s) => s.run);
  const jobs = useLab((s) => s.jobs);
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [jobId, setJobId] = useState<string | null>(null);
  const job: Job | undefined = jobs.find((j) => j.id === jobId);
  const values = useMemo(() => {
    const d: Record<string, unknown> = {};
    for (const f of p.schema.fields) d[f.name] = f.default;
    return { ...d, ...params };
  }, [p, params]);
  return (
    <details className="border-b border-line/50 px-2 py-1" data-exporter={p.key}>
      <summary className="flex cursor-pointer items-center gap-2">
        <span className="font-semibold">{p.label}</span>
        <span className="font-mono text-[10px] text-dim">{(p.formats as string[]).join(" · ")}</span>
        {p.stub && <Planned />}
      </summary>
      <div className="mt-1 text-dim">{p.description}</div>
      <div className="mt-1"><SchemaForm schema={p.schema} values={values} disabled={p.stub} onChange={(patch) => setParams((v) => ({ ...v, ...patch }))} /></div>
      <div className="mt-1 flex items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={p.stub || job?.status === "running"}
          onClick={() => void run<{ job: string }>("export", { exporter: p.key, params, selection }).then((r) => setJobId(r.job)).catch(() => undefined)}
        >
          {job?.status === "running" ? "Exporting..." : selection.length ? `Export selection (${selection.length})` : "Export"}
        </Button>
        {job?.status === "failed" && <span className="text-err">{job.error}</span>}
      </div>
      {job?.status === "done" && (
        <div className="mt-1 flex flex-col">
          {Object.entries((job.result.files ?? {}) as Record<string, string>).map(([name, rel]) => (
            <a key={name} className="truncate font-mono text-[11px] text-accent2 hover:underline" href={api.fileUrl(rel)} download={name} title={rel}>
              {name}
            </a>
          ))}
        </div>
      )}
    </details>
  );
}

export function FabricatePanel() {
  const scene = useLab((s) => s.scene);
  const exporters = useLab((s) => s.plugins.exporter) ?? [];
  const selection = useView((s) => s.selection);
  const parts = scene?.bodies.filter((b) => b.part) ?? [];
  const groups = ["fabrication", "geometry", "simulation", "firmware"];
  return (
    <PanelScroll data-testid="fabricate-panel">
      <Section title={`Parts list (${parts.length})`}>
        <div className="max-h-40 overflow-auto">
          {parts.map((b) => (
            <div
              key={b.id}
              className={`flex cursor-default justify-between px-1 hover:bg-bg3 ${selection.includes(b.id) ? "bg-accent/25" : ""}`}
              onClick={(e) => useView.getState().select([b.id], e.shiftKey || e.ctrlKey)}
            >
              <span className="font-mono text-[11px]">{b.id}</span>
              <span className="text-dim">{fmt(scene?.mass.by_body_g[b.id], 0)} g</span>
            </div>
          ))}
        </div>
        <div className="mt-1 text-[10px] text-dim">Part IDs are embossed on CAD exports and stored as user text in Rhino files.</div>
      </Section>
      {groups.map((g) => (
        <Section key={g} title={`${g} exports`}>
          {exporters.filter((p) => p.category === g).map((p) => <ExporterCard key={p.key} p={p} selection={selection} />)}
        </Section>
      ))}
      <Section title="Planned fabrication views">
        <div className="flex flex-col gap-1 text-dim">
          <span><Planned /> Printer profiles, print orientation and build-plate nesting</span>
          <span><Planned /> Exploded view and assembly-sequence stepper</span>
          <span><Planned /> Mold view: parting lines, keys, pour and vent, wall thickness</span>
          <span><Planned /> Skin pattern view: seams on the body, flattened pieces, distortion map, tiled 1:1 PDF</span>
        </div>
      </Section>
    </PanelScroll>
  );
}

// ---------------------------------------------------------------- wire
interface BomData {
  lines: { key: string; kind: string; name: string; qty: number; qty_unit?: string; cost_usd: number; mass_g: number; url: string; verified: boolean; source: string }[];
  total_cost_usd: number;
  total_mass_g: number;
  unverified: number;
}
interface PowerData {
  run_id: string | null;
  from_run: boolean;
  bus_voltage_v: number;
  mean_power_w: number;
  peak_power_w: number;
  mean_current_a: number;
  peak_current_a: number;
  battery: { name: string; usable_wh: number; runtime_min: number | null; peak_ok: boolean | null; max_current_a: number } | null;
  actuators: { id: string; name: string; current_rms_a: number; current_peak_a: number; power_rms_w: number }[];
  note: string;
}
interface HarnessData {
  routes: { id: string; src: string; dst: string; length_mm: number; connector: string; wires: { signal: string }[] }[];
  total_length_mm: number;
  svg: string;
  yaml: string;
  renderer: string;
  renderer_note: string;
}

export function WirePanel() {
  const bom = useAnalysis<BomData>("bom");
  const power = useAnalysis<PowerData>("power_budget");
  const harness = useAnalysis<HarnessData>("harness");
  const revision = useLab((s) => s.state?.revision);
  if (!bom) return <Empty title="Wire">Loading the bill of materials...</Empty>;
  return (
    <PanelScroll data-testid="wire-panel">
      <Section title="Power budget" right={power?.from_run ? <Badge tone="ok">from run</Badge> : <Badge tone="warn">idle only</Badge>}>
        {power && (
          <>
            {!power.from_run && <div className="mb-1 text-dim">No simulation run yet: only idle and board loads are counted. Press F5 to get a torque profile.</div>}
            <div className="grid grid-cols-4 gap-1 text-center">
              {[["Mean power", `${power.mean_power_w} W`], ["Peak power", `${power.peak_power_w} W`], ["Mean current", `${power.mean_current_a} A`], ["Runtime", power.battery?.runtime_min ? `${power.battery.runtime_min} min` : "-"]].map(([k, v]) => (
                <div key={k} className="rounded bg-bg p-1"><div className="text-[10px] text-dim">{k}</div><div className="font-semibold">{v}</div></div>
              ))}
            </div>
            {power.battery && (
              <Row label="Battery">
                <span>{power.battery.name}</span>
                {power.battery.peak_ok === false && <Badge tone="err">peak current exceeds {power.battery.max_current_a} A</Badge>}
                <Unverified />
              </Row>
            )}
            <div className="text-[10px] text-dim">{power.note}{power.run_id ? ` Run: ${power.run_id}` : ""}</div>
          </>
        )}
      </Section>
      <Section title={`Bill of materials · $${fmt(bom.total_cost_usd, 0)} · ${fmt(bom.total_mass_g, 0)} g`} right={<Button size="sm" onClick={() => void execute("Export", { exporter: "bom" })}>Export CSV</Button>}>
        <table className="w-full">
          <thead className="text-left text-[10px] text-dim uppercase"><tr><th>Item</th><th className="text-right">Qty</th><th className="text-right">Cost</th><th className="text-right">Mass</th><th /></tr></thead>
          <tbody>
            {bom.lines.map((l) => (
              <tr key={l.key + l.name} className="border-t border-line/40" title={`Source: ${l.source}`}>
                <td className="truncate">{l.url ? <a className="text-accent2 hover:underline" href={l.url} target="_blank" rel="noreferrer">{l.name}</a> : l.name}</td>
                <td className="text-right">{l.qty}{l.qty_unit ? ` ${l.qty_unit}` : ""}</td>
                <td className="text-right">${fmt(l.cost_usd, 0)}</td>
                <td className="text-right">{fmt(l.mass_g, 0)} g</td>
                <td className="pl-1">{!l.verified && <Unverified source={l.source} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-1 text-[10px] text-warn">{bom.unverified} of {bom.lines.length} lines use unverified component data.</div>
      </Section>
      <Section title={harness ? `Harness · ${harness.routes.length} cables · ${fmt(harness.total_length_mm, 0)} mm` : "Harness"} right={<Button size="sm" onClick={() => void execute("Export", { exporter: "wireviz" })}>Export WireViz</Button>}>
        {harness && (
          <>
            <table className="w-full">
              <thead className="text-left text-[10px] text-dim uppercase"><tr><th>Cable</th><th>From</th><th>To</th><th className="text-right">Length</th><th>Connector</th></tr></thead>
              <tbody>
                {harness.routes.map((r) => (
                  <tr key={r.id} className="cursor-default border-t border-line/40 hover:bg-bg3" onClick={() => useView.getState().select([r.id])}>
                    <td className="font-mono text-[11px]">{r.id.replace("harness.", "")}</td>
                    <td className="truncate font-mono text-[10px]">{r.src}</td>
                    <td className="truncate font-mono text-[10px]">{r.dst}</td>
                    <td className="text-right">{fmt(r.length_mm, 0)} mm</td>
                    <td>{r.connector} · {r.wires.length}w</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-2 overflow-auto rounded border border-line bg-white p-1">
              <img src={`${api.fileUrl(harness.svg)}?r=${revision}`} alt="Harness diagram" data-testid="harness-diagram" />
            </div>
            {harness.renderer === "fallback" && (
              <div className="mt-1 text-[10px] text-dim">Built-in diagram renderer ({harness.renderer_note}). The WireViz YAML is exported either way.</div>
            )}
          </>
        )}
      </Section>
      <Section title="Planned">
        <div className="flex flex-col gap-1 text-dim">
          <span><Planned /> Drag components in 3D and re-route cables through the body</span>
          <span><Planned /> Pin map per board</span>
        </div>
      </Section>
    </PanelScroll>
  );
}

// ---------------------------------------------------------------- journal
interface EntrySummary { id: string; title: string; created: string; excerpt: string; tags: string[] }
interface CaptureInfo { id: string; path: string; created: string; provenance: Record<string, unknown> }

const LINK = /calflab:\/\/(run|design|candidate|capture)\/([A-Za-z0-9_-]+)/g;

function Rendered({ body, captures }: { body: string; captures: CaptureInfo[] }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of body.matchAll(LINK)) {
    parts.push(body.slice(last, m.index));
    const [kind, id] = [m[1], m[2]];
    const cap = kind === "capture" ? captures.find((c) => c.id === id) : undefined;
    parts.push(
      cap ? (
        <img key={m.index} src={api.fileUrl(cap.path)} className="my-1 max-h-64 rounded border border-line" alt={id} title={JSON.stringify(cap.provenance)} />
      ) : (
        <button
          key={m.index}
          className="rounded bg-accent2/20 px-1 font-mono text-[11px] text-accent2 hover:bg-accent2/30"
          title={`Open ${kind} ${id}`}
          onClick={() => {
            if (kind === "run") void usePlayback.getState().loadRun(id);
            else if (kind === "candidate") void api.post(`/api/candidates/${id}/simulate`);
            else useLab.getState().log("info", `Design ${id}: see the Designs panel`, "journal");
          }}
        >
          {kind}:{id}
        </button>
      ),
    );
    last = (m.index ?? 0) + m[0].length;
  }
  parts.push(body.slice(last));
  return <div className="selectable whitespace-pre-wrap leading-relaxed">{parts}</div>;
}

export function JournalPanel() {
  const log = useLab((s) => s.log);
  const [entries, setEntries] = useState<EntrySummary[]>([]);
  const [captures, setCaptures] = useState<CaptureInfo[]>([]);
  const [id, setId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [editing, setEditing] = useState(false);

  const refresh = () =>
    api.get<{ entries: EntrySummary[]; captures: CaptureInfo[] }>("/api/journal").then((j) => {
      setEntries(j.entries);
      setCaptures(j.captures);
    });
  useEffect(() => {
    void refresh().catch(() => undefined);
    const onCapture = (e: Event) => {
      const cap = (e as CustomEvent<CaptureInfo>).detail;
      setBody((b) => `${b}${b && !b.endsWith("\n") ? "\n" : ""}calflab://capture/${cap.id}\n`);
      void refresh();
    };
    window.addEventListener("calflab:capture", onCapture);
    return () => window.removeEventListener("calflab:capture", onCapture);
  }, []);

  const open = (eid: string) =>
    void api.get<{ id: string; title: string; body: string }>(`/api/journal/${eid}`).then((e) => {
      setId(e.id);
      setTitle(e.title);
      setBody(e.body);
      setEditing(false);
    });
  const save = () =>
    void api
      .post<{ id: string }>("/api/journal", { id, title: title || "Untitled", body })
      .then((e) => {
        setId(e.id);
        setEditing(false);
        log("info", `Saved journal entry ${e.id}`, "journal");
        return refresh();
      })
      .catch((e) => log("error", e.message));
  const latestRun = useLab.getState().runs[0];
  const latestDesign = useLab.getState().designs[0];

  return (
    <div className="flex h-full" data-testid="journal-panel">
      <div className="w-56 shrink-0 overflow-auto border-r border-line">
        <div className="p-1">
          <Button size="sm" variant="primary" onClick={() => { setId(null); setTitle(""); setBody(""); setEditing(true); }}>New entry</Button>
        </div>
        {entries.map((e) => (
          <div key={e.id} className={`cursor-default border-t border-line/50 px-2 py-1 hover:bg-bg3 ${id === e.id ? "bg-accent/25" : ""}`} onClick={() => open(e.id)}>
            <div className="truncate font-semibold">{e.title}</div>
            <div className="truncate text-[10px] text-dim">{e.created.slice(0, 10)} · {e.excerpt}</div>
          </div>
        ))}
        {!entries.length && <div className="p-2 text-dim">No entries yet.</div>}
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        {id === null && !editing ? (
          <Empty title="Research journal" action={<Button variant="primary" onClick={() => setEditing(true)}>Write an entry</Button>}>
            Markdown notes that link to live runs and designs (calflab://run/..., calflab://design/...). Use the camera button in
            the viewport to attach a capture with full provenance.
          </Empty>
        ) : (
          <>
            <div className="flex h-7 shrink-0 items-center gap-1 border-b border-line bg-bg px-1">
              <input type="text" className="min-w-0 flex-1 font-semibold" placeholder="Title" value={title} disabled={!editing} onChange={(e) => setTitle(e.target.value)} />
              {editing ? (
                <>
                  <Button size="sm" onClick={() => void execute("Capture")}>Capture viewport</Button>
                  <Button size="sm" disabled={!latestRun} title="Insert a link to the latest run" onClick={() => setBody((b) => `${b} calflab://run/${latestRun.id}`)}>Link run</Button>
                  <Button size="sm" disabled={!latestDesign} title="Insert a link to the latest design" onClick={() => setBody((b) => `${b} calflab://design/${latestDesign.id}`)}>Link design</Button>
                  <Button size="sm" variant="primary" onClick={save}>Save</Button>
                </>
              ) : (
                <Button size="sm" onClick={() => setEditing(true)}>Edit</Button>
              )}
            </div>
            {editing ? (
              <textarea className="min-h-0 flex-1 resize-none rounded-none border-0 p-2 font-mono text-[12px]" value={body} placeholder="Write in Markdown..." onChange={(e) => setBody(e.target.value)} />
            ) : (
              <PanelScroll className="p-3"><Rendered body={body} captures={captures} /></PanelScroll>
            )}
          </>
        )}
      </div>
    </div>
  );
}
