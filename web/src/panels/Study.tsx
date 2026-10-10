// Proportion study (Evolve workspace): set ranges for a few lengths, let the
// lab try many bodies in several gaits, and read the whole table. Everything
// shown here is computed by the server (calflab.evolve.study); this panel
// only lays it out, sorts rows and sends commands.
import { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { SchemaForm } from "@/components/SchemaForm";
import { Badge, Button, Empty, PanelScroll, Section, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";

interface JointRow {
  joint: string;
  component: string | null;
  torque_peak_nm: number;
  torque_rms_nm: number;
  torque_limit_nm: number;
  torque_margin: number;
  torque_saturated: number;
  speed_peak_deg_s: number;
  speed_limit_deg_s: number | null;
  speed_margin: number | null;
}

interface GaitResult {
  works: boolean;
  flags: string[];
  metrics: Record<string, number | boolean | null>;
  joints: JointRow[];
  battery: { mean_current_a: number; peak_current_a: number; max_current_a: number | null; peak_ok: boolean | null; runtime_min: number | null; bus_voltage_v: number };
  controller: { key: string; params: Record<string, unknown> };
}

interface StudyBody {
  id: string;
  baseline: boolean;
  real: Record<string, number>;
  height_mm: number;
  mass_g?: number;
  error?: string;
  gaits: Record<string, GaitResult>;
}

interface StudyView {
  run_id: string;
  dimensions: { key: string; label: string; unit: string; min: number; max: number }[];
  gaits: string[];
  bodies: StudyBody[];
  notes: string[];
  summary: {
    works_in_all: string[];
    gaits: Record<string, { tried: number; working: number; front: string[]; fastest: string | null; trends: { text: string }[] }>;
  };
  run: { status: string; duration_s: number };
}

type SortKey = "id" | "height" | "mass" | "speed" | "torque" | "jspeed" | "current" | `dim:${string}`;

const num = (v: unknown): number => (typeof v === "number" ? v : Number.NaN);
const pct = (v: number | null | undefined) => (v === null || v === undefined || Number.isNaN(v) ? "-" : `${Math.round(v * 100)}%`);
const marginTone = (m: number | null | undefined) => (m === null || m === undefined ? "" : m < 0.05 ? "text-err" : m < 0.3 ? "text-warn" : "");

export function StudyPanel() {
  const commands = useLab((s) => s.commands);
  const runs = useLab((s) => s.runs);
  const jobs = useLab((s) => s.jobs);
  const run = useLab((s) => s.run);
  const cmd = commands.find((c) => c.key === "run_study");
  const studies = useMemo(() => runs.filter((r) => r.kind === "study"), [runs]);
  const active = jobs.find((j) => j.kind === "study" && (j.status === "running" || j.status === "queued"));
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [runId, setRunId] = useState("");
  const [view, setView] = useState<StudyView | null>(null);
  const [gait, setGait] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const [sort, setSort] = useState<{ key: SortKey; down: boolean }>({ key: "speed", down: true });
  const shown = runId || studies[0]?.id || "";

  useEffect(() => {
    if (!shown) {
      setView(null);
      return;
    }
    void api
      .get<StudyView>(`/api/study/${shown}`)
      .then((v) => {
        setView(v);
        setGait((g) => (v.gaits.includes(g) ? g : (v.gaits[0] ?? "")));
        setPicked(null);
      })
      .catch(() => setView(null));
  }, [shown]);

  const values = useMemo(() => {
    const d: Record<string, unknown> = {};
    for (const f of cmd?.schema.fields ?? []) d[f.name] = f.default;
    return { ...d, ...params };
  }, [cmd, params]);
  const budget = (Number(values.bodies ?? 0) + 1) * (Array.isArray(values.gaits) ? values.gaits.length : 0) * (2 + Number(values.iterations ?? 0) * Number(values.popsize ?? 0));

  const start = () =>
    void run<{ run_id: string }>("run_study", params)
      .then(() => setRunId(""))
      .catch(() => undefined);

  const summary = view?.summary.gaits[gait];
  const rows = useMemo(() => {
    if (!view) return [];
    const value = (b: StudyBody): number | string => {
      const g = b.gaits[gait];
      switch (sort.key) {
        case "id": return b.id;
        case "height": return b.height_mm;
        case "mass": return b.mass_g ?? Number.NaN;
        case "speed": return num(g?.metrics.speed_mps);
        case "torque": return num(g?.metrics.torque_margin_min);
        case "jspeed": return num(g?.metrics.speed_margin_min);
        case "current": return g?.battery.peak_current_a ?? Number.NaN;
        default: return b.real[sort.key.slice(4)] ?? Number.NaN;
      }
    };
    return [...view.bodies].sort((a, b) => {
      const [x, y] = [value(a), value(b)];
      if (typeof x === "string" || typeof y === "string") return (sort.down ? -1 : 1) * String(x).localeCompare(String(y));
      if (Number.isNaN(x)) return 1;
      if (Number.isNaN(y)) return -1;
      return sort.down ? y - x : x - y;
    });
  }, [view, gait, sort]);
  const body = view?.bodies.find((b) => b.id === picked) ?? null;
  const result = body?.gaits[gait] ?? null;

  const th = (key: SortKey, label: string, title: string, right = true) => (
    <th
      className={`cursor-pointer px-1 select-none ${right ? "text-right" : "text-left"}`}
      title={`${title}\nClick to sort`}
      onClick={() => setSort((s) => ({ key, down: s.key === key ? !s.down : true }))}
    >
      {label}{sort.key === key ? (sort.down ? " v" : " ^") : ""}
    </th>
  );

  return (
    <div className="flex h-full min-h-0" data-testid="study-panel">
      <PanelScroll className="w-[290px] shrink-0 border-r border-line">
        <div className="flex items-center gap-2 border-b border-line bg-bg p-2">
          {active ? (
            <>
              <Button variant="danger" onClick={() => void api.post(`/api/jobs/${active.id}/cancel`)}>Cancel</Button>
              <div className="h-1.5 flex-1 overflow-hidden rounded bg-bg3"><div className="h-full bg-accent" style={{ width: `${active.progress * 100}%` }} /></div>
              <span className="text-dim" data-testid="study-progress">{active.message}</span>
            </>
          ) : (
            <>
              <Button variant="primary" disabled={!cmd} onClick={start} data-testid="study-start">Run proportion study</Button>
              <span className="text-dim">about {budget} rollouts</span>
            </>
          )}
        </div>
        <Section title="Ranges and search">
          <div className="mb-1 text-[11px] text-dim">
            Lengths are real millimetres on the body, as the Form sliders show them. A range of 0 to 0 keeps that length as the
            design has it. The working design is always tried too (body b00) and is not changed.
          </div>
          {cmd && <SchemaForm schema={cmd.schema} values={values} onChange={(patch) => setParams((p) => ({ ...p, ...patch }))} />}
        </Section>
        <Section title="Past studies">
          {!studies.length && <div className="text-dim">None yet.</div>}
          {studies.map((r) => (
            <div key={r.id} className={`flex cursor-default items-center gap-2 hover:bg-bg3 ${r.id === shown ? "bg-bg3" : ""}`} onClick={() => setRunId(r.id)} data-study-run={r.id}>
              <span className="truncate font-mono text-[11px]">{r.id}</span>
              <Badge tone={r.status === "done" ? "ok" : "neutral"}>{r.status}</Badge>
            </div>
          ))}
        </Section>
      </PanelScroll>

      <PanelScroll className="min-w-0 flex-1">
        {!view ? (
          <Empty title="Proportion study">
            Compares many bodies instead of looking for one winner: within the ranges you set for thigh, shank, trunk, stance and
            hip drop, each body gets a gait tuned for it and is tried in walk, trot and bound. You read speed, the torque and
            speed each motor sees against its limits, and the battery current. Set at least one range on the left and press
            <b> Run proportion study</b>.
          </Empty>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 border-b border-line bg-bg p-2" data-testid="study-header">
              <span className="font-mono text-[11px]">{view.run_id}</span>
              <Badge tone={view.run.status === "done" ? "ok" : "neutral"}>{view.run.status}</Badge>
              <span className="text-dim">{view.bodies.length} bodies, {fmt(view.run.duration_s, 0)} s</span>
              <span className="ml-auto flex gap-1">
                {view.gaits.map((g) => (
                  <Button key={g} size="sm" variant={g === gait ? "primary" : "ghost"} data-study-gait={g} onClick={() => setGait(g)}>
                    {g} {view.summary.gaits[g]?.working ?? 0}/{view.summary.gaits[g]?.tried ?? 0}
                  </Button>
                ))}
              </span>
            </div>
            {view.notes.length > 0 && (
              <Section title="Read this first">
                <ul className="list-disc pl-4 text-[11px] text-warn" data-testid="study-notes">
                  {view.notes.map((n) => <li key={n}>{n}</li>)}
                </ul>
              </Section>
            )}
            <Section title={`Bodies in ${gait}`}>
              <div className="mb-1 text-[11px] text-dim">
                {summary?.working ?? 0} of {summary?.tried ?? 0} work in {gait}; {view.summary.works_in_all.length} work in every gait tried.
                <Badge tone="info" title="No other working body is both faster and has more torque margin">front</Badge> marks the
                trade-off front between speed and worst torque margin. Click a row for its joints.
              </div>
              <table className="w-full" data-testid="study-table">
                <thead className="text-[10px] text-dim uppercase">
                  <tr>
                    {th("id", "Body", "Body id; b00 is the working design", false)}
                    {view.dimensions.map((d) => th(`dim:${d.key}`, d.label, `${d.label} (${d.unit}), tried from ${d.min} to ${d.max}`))}
                    {th("height", "Height", "Standing height (mm), the lab's height readout")}
                    {th("mass", "Mass", "Simulated mass (g)")}
                    <th className="px-1 text-left">Works</th>
                    {th("speed", "Speed", "Forward speed over the check run (m/s)")}
                    {th("torque", "Torque margin", "Worst joint: 1 - peak torque / usable torque")}
                    {th("jspeed", "Speed margin", "Worst joint: 1 - peak joint speed / the motor's no-load speed")}
                    {th("current", "Battery peak", "Estimated peak battery current (A)")}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((b) => {
                    const g = b.gaits[gait];
                    return (
                      <tr key={b.id} className={`cursor-default border-t border-line/40 hover:bg-bg3 ${b.id === picked ? "bg-bg3" : ""}`} data-study-body={b.id} onClick={() => setPicked(b.id)}>
                        <td className="px-1 font-mono text-[11px]">
                          {b.id} {b.baseline && <Badge title="The working design as it was when the study started">design</Badge>}{" "}
                          {summary?.front.includes(b.id) && <Badge tone="info" title="No other working body is both faster and has more torque margin">front</Badge>}
                        </td>
                        {view.dimensions.map((d) => <td key={d.key} className="px-1 text-right">{fmt(b.real[d.key], 1)}</td>)}
                        <td className="px-1 text-right">{fmt(b.height_mm, 0)}</td>
                        <td className="px-1 text-right">{fmt(b.mass_g, 0)}</td>
                        {b.error || !g ? (
                          <td className="px-1 text-err" colSpan={5} title={b.error}>failed: {b.error ?? "not tried"}</td>
                        ) : (
                          <>
                            <td className="px-1"><Badge tone={g.works ? "ok" : "err"} title={g.flags.join("\n")}>{g.works ? "yes" : "no"}</Badge></td>
                            <td className="px-1 text-right">{fmt(g.metrics.speed_mps, 3)}</td>
                            <td className={`px-1 text-right ${marginTone(num(g.metrics.torque_margin_min))}`}>{pct(num(g.metrics.torque_margin_min))}</td>
                            <td className={`px-1 text-right ${marginTone(num(g.metrics.speed_margin_min))}`}>{pct(num(g.metrics.speed_margin_min))}</td>
                            <td className={`px-1 text-right ${g.battery.peak_ok === false ? "text-err" : ""}`}>{fmt(g.battery.peak_current_a, 2)}</td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Section>
            {summary && summary.trends.length > 0 && (
              <Section title={`Trends in ${gait}`}>
                <ul className="list-disc pl-4 text-[11px]" data-testid="study-trends">
                  {summary.trends.map((t) => <li key={t.text}>{t.text}</li>)}
                </ul>
                <div className="mt-1 text-[11px] text-dim">Rank correlations over the bodies tried: a direction to look in, not a law.</div>
              </Section>
            )}
            {body && result && (
              <Section
                title={`${body.id} in ${gait}`}
                right={
                  <span className="flex gap-1">
                    <Button size="sm" variant="ghost" data-testid="study-replay" title="Simulate this body with this gait; the document is not changed. The poses play in the Viewport tab." onClick={() => void run("simulate_study_body", { run: view.run_id, body: body.id, gait })}>Replay</Button>
                    <Button size="sm" variant="ghost" data-testid="study-adopt" title="Load this body and this gait into the document (undoable)" onClick={() => void run("adopt_study_body", { run: view.run_id, body: body.id, gait })}>Use this body</Button>
                  </span>
                }
              >
                <div className="mb-1 text-[11px]" data-testid="study-detail">
                  {result.works ? <Badge tone="ok">works</Badge> : <Badge tone="err">does not work</Badge>}{" "}
                  {result.flags.length ? result.flags.join("; ") + "." : "No flags."}{" "}
                  <span className="text-dim">
                    Speed {fmt(result.metrics.speed_mps, 3)} m/s, stability {fmt(result.metrics.stability, 2)}, sideways drift {fmt(result.metrics.lateral_drift_m, 2)} m,
                    roll {fmt(result.metrics.roll_rms_deg, 1)} deg RMS, pitch {fmt(result.metrics.pitch_rms_deg, 1)} deg RMS.
                  </span>
                </div>
                <table className="w-full" data-testid="study-joints">
                  <thead className="text-[10px] text-dim uppercase">
                    <tr>
                      <th className="text-left">Joint</th><th className="text-left">Motor</th>
                      <th className="text-right" title="Peak torque in the check run (N*m)">Peak torque</th>
                      <th className="text-right" title="Usable torque: stall torque x the model's torque derating (N*m)">Usable</th>
                      <th className="text-right" title="1 - peak / usable">Margin</th>
                      <th className="text-right" title="Share of the time the motor gave (nearly) all its usable torque">At limit</th>
                      <th className="text-right" title="Peak joint speed in the check run (deg/s)">Peak speed</th>
                      <th className="text-right" title="The motor's recorded no-load speed at the joint (deg/s)">No-load</th>
                      <th className="text-right" title="1 - peak speed / no-load speed">Margin</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.joints.map((j) => (
                      <tr key={j.joint} className="border-t border-line/40" data-joint={j.joint}>
                        <td className="font-mono text-[11px]">{j.joint.replace("joint.", "")}</td>
                        <td className="text-dim">{j.component}</td>
                        <td className="text-right">{fmt(j.torque_peak_nm, 3)}</td>
                        <td className="text-right">{fmt(j.torque_limit_nm, 3)}</td>
                        <td className={`text-right ${marginTone(j.torque_margin)}`}>{pct(j.torque_margin)}</td>
                        <td className="text-right">{pct(j.torque_saturated)}</td>
                        <td className="text-right">{fmt(j.speed_peak_deg_s, 0)}</td>
                        <td className="text-right">{fmt(j.speed_limit_deg_s, 0)}</td>
                        <td className={`text-right ${marginTone(j.speed_margin)}`}>{pct(j.speed_margin)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="mt-1 text-[11px]" data-testid="study-battery">
                  Battery at {fmt(result.battery.bus_voltage_v, 1)} V: mean {fmt(result.battery.mean_current_a, 2)} A, peak{" "}
                  <span className={result.battery.peak_ok === false ? "text-err" : ""}>{fmt(result.battery.peak_current_a, 2)} A</span>
                  {result.battery.max_current_a ? ` of ${fmt(result.battery.max_current_a, 1)} A allowed` : ""}
                  {result.battery.runtime_min ? `, about ${fmt(result.battery.runtime_min, 0)} min at this load` : ""}.
                  <span className="text-dim"> An estimate from torque and the library's unverified figures, not a measurement.</span>
                </div>
              </Section>
            )}
          </>
        )}
      </PanelScroll>
    </div>
  );
}
