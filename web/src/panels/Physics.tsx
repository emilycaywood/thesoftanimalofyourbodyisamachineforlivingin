// A clip judged in physics, and its feasible version (ADR-084). The server plays the clip in MuJoCo, judges every
// limit with the researcher's margin and searches for a feasible version; this file only starts those jobs and
// draws the stored report. Clicking the time strip seeks the replay (and the review frame of a candidate).
import { useEffect, useState } from "react";
import { ApiError, api } from "@/api/client";
import { replayRun } from "@/commands/registry";
import { Badge, Button, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";

export interface PhysicsSource { clip?: string; file?: string; candidate?: string; start?: number; end?: number; far_side?: string }

interface PJoint {
  joint: string; in_clip: boolean; drive?: string | null;
  tracking_rms_deg: number | null; tracking_peak_deg: number | null;
  servo_torque_peak_nm: number; rated_nm: number | null; stall_nm: number | null;
  pct_rated_peak: number | null; pct_stall_peak: number | null; above_rated_fraction: number | null;
  speed_peak_deg_s: number; speed_limit_deg_s: number; envelope_peak: number; envelope_saturated_fraction: number;
  belt_tension_peak_n: number | null; belt_allowable_n: number | null; belt_breaking_n: number | null;
}
interface PConstraint { key: string; label?: string; detail?: string; value: number | null; limit: number | null; violated: boolean; action?: string; margin?: number | null }
interface PEvent { key: string; label: string; joint: string; t0: number; t1: number; peak: number; phase: string; video_frame: number | null; rollout_frame: number }
interface PStripRow { key: string; label: string; levels: number[]; joints: string[]; peak: number; peak_joint: string; over_fraction: number }
interface PHoof { foot: string; peak_force_n: number; peak_over_weight: number | null; impacts: number; peak_impact_speed_m_s: number; peak_impact_force_n: number; contact_fraction: number | null; planned_support_fraction: number | null }
export interface PhysicsReport {
  clip: string; name: string; fps: number; frames: number; duration_s: number; margin: number;
  timing: { clip_t0: number; clip_t1: number; end_t: number };
  within_limits: boolean; verdict: string; fell: boolean; fall_time_s: number | null; judged_until_s: number | null;
  first_limit: { key: string; label: string; joint: string; t0: number; peak: number; phase: string; video_frame: number | null } | null;
  tracking_rms_deg: number | null; tracking_peak_deg: number | null;
  joints: PJoint[]; constraints: PConstraint[];
  safety: { violations: string[]; margin: number | null; rejected: boolean; reject_reasons: string[] };
  hooves: PHoof[]; body_weight_n: number; hooves_down_fewer_than_3_fraction: number | null;
  stance: { min_support?: number; stability_margin_mm?: number; com_outside_after_fraction?: number; slip_after_mm?: Record<string, number> } | null;
  battery: { known: boolean; voltage_v: number | null; note: string; peak_power_w: number; mean_power_w: number; peak_current_a: number | null; peak_current_lower_bound_a: number | null; missing_stall_current: string[] };
  events: PEvent[]; events_total: number;
  strip: { t: number[]; t_end: number; phase: number[]; video_frame: (number | null)[]; rollout_frame: number[]; rows: PStripRow[] };
  mass_kg: number | null; servo_model: string | null;
}
interface Basis {
  total_mass_g: number; missing_masses: string[]; armature_scale: number;
  servos: Record<string, { name?: string; verified?: boolean; armature_default?: boolean; armature_kgm2?: number; missing?: string[]; count: number }>;
  provisional: { name: string; value: unknown; unit?: string | null; where?: string }[];
}
interface Side {
  verdict: string; fell: boolean; fall_time_s: number | null; first_limit: PhysicsReport["first_limit"];
  tracking_rms_deg: number | null; margin: number | null; violations: string[]; duration_s: number;
  constraints: Record<string, { value: number | null; limit: number | null; violated: boolean; label?: string }>;
  busiest_joint: { joint: string; envelope_peak: number; pct_stall_peak: number | null } | null;
  character: { quantity_of_motion: number | null; expressive_range: number | null; rhythm: number | null; shape: number | null; shape_rms_deg: number | null; score: number;
    raw: Record<string, number | null>; adapted: Record<string, number | null> };
}
interface Step { round: number; action: string; operations: string; badness: number; fell: boolean; violations: string[]; character: number; limit?: string; joint?: string | null }
export interface PhysicsView {
  kind: "physics" | "adapt"; run_id: string; title: string; status: string; source: Record<string, unknown>;
  report?: PhysicsReport; basis: Basis;
  // adapt only
  feasible?: boolean; plays?: number; operations_text?: string; steps?: Step[]; compare?: { raw: Side; adapted: Side };
  raw?: PhysicsReport; adapted?: PhysicsReport; raw_run?: string; saved_clip?: string | null; adapted_clip?: string;
  stance?: Record<string, unknown>; cancelled?: boolean;
}

interface StoredRun { id: string; kind: "physics" | "adapt"; created: string; title: string; status: string; source: Record<string, unknown>; metrics: Record<string, unknown> }

const LEVEL = ["#22c55e", "#f59e0b", "#ef4444"];
const PHASE = ["lead-in", "clip", "return"];
const pct = (x: number | null | undefined, d = 0) => (x == null ? "–" : `${fmt(x * 100, d)} %`);
const short = (j: string) => j.replace("joint.", "");

/** Two buttons beside "Preview on robot": they start the jobs, wait for them and show the stored report. */
export function PhysicsActions({ source, onSeekVideo }: { source: PhysicsSource; onSeekVideo?: (f: number) => void }) {
  const run = useLab((s) => s.run);
  const jobs = useLab((s) => s.jobs);
  const [jobId, setJobId] = useState<string | null>(null);
  const [view, setView] = useState<PhysicsView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const key = JSON.stringify(source);
  useEffect(() => { setView(null); setJobId(null); setErr(null); }, [key]);
  const runs = useLab((s) => s.runs);
  const [last, setLast] = useState<StoredRun[]>([]);
  useEffect(() => {
    const filter = source.clip ? { clip: source.clip } : { file: source.file, candidate: source.candidate };
    void run<{ runs: StoredRun[] }>("physics_report", filter).then((r) => setLast(r.runs)).catch(() => setLast([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, runs.length, run]);
  const show = (id: string) => void run<PhysicsView>("physics_report", { run: id }).then((v) => { setView(v); return replayRun(id); })
    .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  const lastPlay = last.find((r) => r.kind === "physics");
  const lastAdapt = last.find((r) => r.kind === "adapt");
  const job = jobs.find((j) => j.id === jobId) ?? null;
  const runId = job?.status === "done" ? (job.result?.run_id as string | undefined) : undefined;
  useEffect(() => {
    if (!runId) return;
    void run<PhysicsView>("physics_report", { run: runId }).then((v) => { setView(v); setJobId(null); return replayRun(runId); })
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  }, [runId, run]);
  useEffect(() => { if (job?.status === "failed") setErr(job.error ?? "failed"); }, [job?.status, job?.error]);
  const start = (cmd: string) => {
    setErr(null);
    setView(null);
    void run<{ job: string }>(cmd, { ...source }).then((r) => setJobId(r.job))
      .catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  };
  const busy = job && (job.status === "running" || job.status === "queued");
  return (
    <div className="mt-1" data-testid="physics-actions">
      <div className="flex flex-wrap items-center gap-1">
        <Button size="sm" data-testid="play-in-physics" disabled={!!busy}
          title="Play once on the body in MuJoCo: servos limited in torque and speed, belts, springs, contact. Judged with a 20 % margin."
          onClick={() => start("play_in_physics")}>Play in physics</Button>
        <Button size="sm" data-testid="make-feasible" disabled={!!busy}
          title="Search for a version within every limit (planted hooves, slower, smaller, smoother), then give back what holds. A few minutes."
          onClick={() => start("adapt_clip")}>Make feasible</Button>
        {busy && (
          <span className="flex items-center gap-1 text-[10px] text-dim" data-testid="physics-busy">
            <span className="inline-block h-1 w-16 rounded bg-bg3"><span className="block h-1 rounded bg-accent" style={{ width: `${Math.round(job.progress * 100)}%` }} /></span>
            {job.message || job.title}
            <Button size="sm" variant="ghost" onClick={() => void api.post(`/api/jobs/${job.id}/cancel`).catch(() => undefined)}>Cancel</Button>
          </span>
        )}
      </div>
      {!view && (lastPlay || lastAdapt) && (
        <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[10px] text-dim" data-testid="physics-last">
          {lastPlay && (
            <span>In physics: <b>{String(lastPlay.metrics.verdict ?? "")}</b>{lastPlay.metrics.fall_time_s != null ? ` at ${fmt(Number(lastPlay.metrics.fall_time_s), 1)} s` : ""}{" "}
              <Button size="sm" variant="ghost" data-testid="show-last-physics" onClick={() => show(lastPlay.id)}>Show</Button></span>
          )}
          {lastAdapt && (
            <span>Feasible version: <b>{lastAdapt.metrics.feasible ? "found" : "not found"}</b>, character {fmt(Number(lastAdapt.metrics.character ?? 0), 2)}{" "}
              <Button size="sm" variant="ghost" data-testid="show-last-adapt" onClick={() => show(lastAdapt.id)}>Show</Button></span>
          )}
        </div>
      )}
      {view && <Button size="sm" variant="ghost" onClick={() => setView(null)}>Hide report</Button>}
      {err && <div className="text-[11px] text-err" data-testid="physics-error">{err}</div>}
      {view && <PhysicsViewBlock view={view} onSeekVideo={onSeekVideo} onKept={(v) => setView(v)} />}
    </div>
  );
}

export function PhysicsViewBlock({ view, onSeekVideo, onKept }: { view: PhysicsView; onSeekVideo?: (f: number) => void; onKept?: (v: PhysicsView) => void }) {
  const run = useLab((s) => s.run);
  const [which, setWhich] = useState<"adapted" | "raw">("adapted");
  const [msg, setMsg] = useState<string | null>(null);
  if (view.kind === "physics" && view.report) {
    return <div className="mt-1 rounded border border-line p-1" data-testid="physics-report"><ReportBlock rep={view.report} runId={view.run_id} basis={view.basis} onSeekVideo={onSeekVideo} /></div>;
  }
  const rep = which === "adapted" ? view.adapted! : view.raw!;
  const repRun = which === "adapted" ? view.run_id : view.raw_run!;
  return (
    <div className="mt-1 rounded border border-line p-1" data-testid="adapt-report">
      <div className="mb-1 text-[11px]">
        <Badge tone={view.feasible ? "ok" : "err"}>{view.feasible ? "feasible" : "no feasible version found"}</Badge>{" "}
        {view.operations_text} <span className="text-dim">· {view.plays} plays in physics{view.cancelled ? " · cancelled" : ""}</span>
      </div>
      {view.compare && <CompareTable cmp={view.compare} />}
      {view.steps && (
        <details className="mt-1 text-[10px]">
          <summary className="cursor-pointer text-dim">How it got there ({view.steps.length} steps)</summary>
          <table className="w-full" data-testid="adapt-steps">
            <thead><tr className="text-dim"><td>round</td><td>limit</td><td>step</td><td className="text-right">excess</td><td className="text-right">character</td><td>still over</td></tr></thead>
            <tbody>
              {view.steps.map((s, i) => (
                <tr key={i} className="border-t border-line/40" title={s.operations}>
                  <td>{s.round}</td><td>{s.limit ? `${s.limit}${s.joint ? ` @ ${short(s.joint)}` : ""}` : ""}</td><td>{s.action}</td>
                  <td className="text-right">{fmt(s.badness, 2)}</td><td className="text-right">{fmt(s.character, 2)}</td>
                  <td>{s.fell ? "falls; " : ""}{s.violations.filter((v) => v !== "fall").join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px]">
        <span className="text-dim">Details of</span>
        <Button size="sm" variant={which === "adapted" ? "primary" : "ghost"} data-testid="show-adapted" onClick={() => { setWhich("adapted"); void replayRun(view.run_id); }}>adapted</Button>
        <Button size="sm" variant={which === "raw" ? "primary" : "ghost"} data-testid="show-raw" onClick={() => { setWhich("raw"); void replayRun(view.raw_run!); }}>as retargeted</Button>
        {view.saved_clip ? (
          <span className="text-ok" data-testid="adapted-saved">Saved as clip <b>{view.saved_clip}</b></span>
        ) : (
          <Button size="sm" data-testid="keep-adapted" title="Save this feasible version into the motion library as a new clip"
            onClick={() => void run<{ clip: string }>("keep_adapted_clip", { run: view.run_id })
              .then((r) => { setMsg(`Saved as clip ${r.clip}`); onKept?.({ ...view, saved_clip: r.clip }); })
              .catch((e: unknown) => setMsg(e instanceof ApiError ? e.message : String(e)))}>
            Keep adapted clip
          </Button>
        )}
        {msg && <span className="text-dim">{msg}</span>}
      </div>
      {rep && <ReportBlock rep={rep} runId={repRun} basis={view.basis} onSeekVideo={onSeekVideo} />}
    </div>
  );
}

function CompareTable({ cmp }: { cmp: { raw: Side; adapted: Side } }) {
  const first = (s: Side) => (s.fell ? `falls at ${fmt(s.fall_time_s ?? 0, 2)} s` : s.first_limit ? `${s.first_limit.label} @ ${s.first_limit.joint} (${fmt(s.first_limit.t0, 2)} s, ${s.first_limit.phase})` : "nothing");
  const rows: [string, (s: Side) => string][] = [
    ["verdict", (s) => s.verdict],
    ["limits first", first],
    ["over (with margin)", (s) => s.violations.join(", ") || "none"],
    ["tracking RMS", (s) => (s.tracking_rms_deg == null ? "–" : `${fmt(s.tracking_rms_deg, 1)}°`)],
    ["smallest margin", (s) => (s.margin == null ? "–" : pct(s.margin))],
    ["busiest servo", (s) => (s.busiest_joint ? `${short(s.busiest_joint.joint)}: envelope ${pct(s.busiest_joint.envelope_peak)}, stall ${fmt(s.busiest_joint.pct_stall_peak ?? 0, 0)} %` : "–")],
    ["duration", (s) => `${fmt(s.duration_s, 1)} s`],
    ["character kept", (s) => fmt(s.character.score, 2)],
    ["  quantity of motion", (s) => `${pct(s.character.quantity_of_motion)} (${fmt(s.character.adapted.quantity_of_motion_deg_s ?? 0, 0)} °/s)`],
    ["  expressive range", (s) => pct(s.character.expressive_range)],
    ["  rhythm (tempo)", (s) => `${pct(s.character.rhythm)} (${fmt(s.character.adapted.tempo_s ?? 0, 2)} s)`],
    ["  shape", (s) => `${pct(s.character.shape)}${s.character.shape_rms_deg != null ? ` (${fmt(s.character.shape_rms_deg, 1)}° RMS)` : ""}`],
  ];
  const keys = Object.keys(cmp.adapted.constraints);
  return (
    <table className="w-full text-[10px]" data-testid="adapt-compare">
      <thead><tr className="text-dim"><td /><td>as retargeted</td><td>adapted</td></tr></thead>
      <tbody>
        {rows.map(([label, f]) => (
          <tr key={label} className="border-t border-line/40"><td className="whitespace-pre text-dim">{label}</td><td>{f(cmp.raw)}</td><td>{f(cmp.adapted)}</td></tr>
        ))}
        {keys.map((k) => {
          const a = cmp.raw.constraints[k];
          const b = cmp.adapted.constraints[k];
          const cell = (c?: { value: number | null; limit: number | null; violated: boolean }) =>
            c ? <span className={c.violated ? "text-err" : ""}>{c.value == null ? "unknown" : fmt(c.value, 2)} / {c.limit == null ? "–" : fmt(c.limit, 2)}</span> : "–";
          return <tr key={k} className="border-t border-line/40"><td className="text-dim">{b?.label ?? k}</td><td>{cell(a)}</td><td>{cell(b)}</td></tr>;
        })}
      </tbody>
    </table>
  );
}

function seek(runId: string, frame: number) {
  const pb = usePlayback.getState();
  const go = () => usePlayback.getState().setFrame(frame);
  if (pb.runId === runId && pb.t.length) { pb.set({ playing: false }); go(); return; }
  void pb.loadRun(runId, false).then((ok) => { if (!ok) return; usePlayback.getState().set({ playing: false }); go(); });
}

function ReportBlock({ rep, runId, basis, onSeekVideo }: { rep: PhysicsReport; runId: string; basis: Basis; onSeekVideo?: (f: number) => void }) {
  const pick = (col: number) => {
    seek(runId, rep.strip.rollout_frame[col]);
    const vf = rep.strip.video_frame[col];
    if (vf != null) onSeekVideo?.(vf);
  };
  return (
    <div className="mt-1 text-[10px]" data-testid="physics-block">
      <div className="text-[11px]">
        <Badge tone={rep.fell ? "err" : rep.within_limits ? "ok" : "warn"}>{rep.verdict}</Badge>{" "}
        {rep.fell ? `falls at ${fmt(rep.fall_time_s ?? 0, 2)} s (clip ${fmt(rep.timing.clip_t0, 1)}–${fmt(rep.timing.clip_t1, 1)} s); table judged up to the fall · ` : ""}
        {rep.first_limit ? `first over: ${rep.first_limit.label} at ${rep.first_limit.joint}, ${fmt(rep.first_limit.t0, 2)} s (${rep.first_limit.phase}${rep.first_limit.video_frame != null ? `, video frame ${rep.first_limit.video_frame}` : ""}) · ` : ""}
        tracking {rep.tracking_rms_deg == null ? "–" : `${fmt(rep.tracking_rms_deg, 1)}° RMS`} · margin {pct(rep.margin)} · {rep.servo_model ?? ""} servos · {fmt(rep.mass_kg ?? 0, 2)} kg
      </div>
      <TimeStrip rep={rep} onPick={pick} />
      <table className="mt-1 w-full" data-testid="physics-joints">
        <thead><tr className="text-dim"><td>joint</td><td className="text-right">tracking °</td><td className="text-right">torque N·m</td><td className="text-right">% rated</td><td className="text-right">% stall</td><td className="text-right">speed °/s</td><td className="text-right">envelope</td><td className="text-right">belt N</td></tr></thead>
        <tbody>
          {rep.joints.map((j) => (
            <tr key={j.joint} className="border-t border-line/40">
              <td>{short(j.joint)}{j.in_clip ? "" : " (held)"}{j.drive ? <span className="text-dim"> {j.drive}</span> : null}</td>
              <td className="text-right">{j.tracking_rms_deg == null ? "–" : `${fmt(j.tracking_rms_deg, 1)} (${fmt(j.tracking_peak_deg ?? 0, 0)})`}</td>
              <td className="text-right">{fmt(j.servo_torque_peak_nm, 2)}</td>
              <td className={`text-right ${(j.pct_rated_peak ?? 0) > 100 * 0.6 * (1 - rep.margin) ? "text-warn" : ""}`}>{j.pct_rated_peak == null ? "–" : fmt(j.pct_rated_peak, 0)}{j.above_rated_fraction ? <span className="text-dim"> ({pct(j.above_rated_fraction)} over)</span> : null}</td>
              <td className={`text-right ${(j.pct_stall_peak ?? 0) > 100 * (1 - rep.margin) ? "text-err" : ""}`}>{j.pct_stall_peak == null ? "–" : fmt(j.pct_stall_peak, 0)}</td>
              <td className={`text-right ${j.speed_peak_deg_s > j.speed_limit_deg_s * (1 - rep.margin) ? "text-warn" : ""}`}>{fmt(j.speed_peak_deg_s, 0)} / {fmt(j.speed_limit_deg_s, 0)}</td>
              <td className={`text-right ${j.envelope_peak > 1 - rep.margin ? "text-warn" : ""}`}>{pct(j.envelope_peak)}</td>
              <td className="text-right">{j.belt_tension_peak_n == null ? "" : `${fmt(j.belt_tension_peak_n, 0)} / ${j.belt_allowable_n == null ? "?" : fmt(j.belt_allowable_n, 0)}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-0.5 text-[9px] text-dim">tracking: RMS against the clip (peak in brackets) · % rated is of the servo's rated torque, % stall of its stall torque (peaks) · speed against the servo's no-load speed at the joint · envelope: torque/stall + speed/no-load when driving · belt: peak tension against the allowable working tension</div>
      <table className="mt-1 w-full" data-testid="physics-constraints">
        <thead><tr className="text-dim"><td>limit (margin {pct(rep.margin)})</td><td className="text-right">value</td><td className="text-right">limit</td><td>what</td></tr></thead>
        <tbody>
          {rep.constraints.map((c) => (
            <tr key={c.key} className={`border-t border-line/40 ${c.violated ? "text-err" : ""}`}>
              <td>{c.label ?? c.key}{c.action ? <span className="text-dim"> ({c.action})</span> : null}</td>
              <td className="text-right">{c.value == null ? "unknown" : fmt(c.value, 2)}</td>
              <td className="text-right">{c.limit == null ? "–" : fmt(c.limit, 2)}</td>
              <td className="text-dim">{c.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="mt-1 w-full" data-testid="physics-hooves">
        <thead><tr className="text-dim"><td>hoof</td><td className="text-right">on the ground</td><td className="text-right">planned</td><td className="text-right">peak force</td><td className="text-right">impacts</td></tr></thead>
        <tbody>
          {rep.hooves.map((h) => (
            <tr key={h.foot} className="border-t border-line/40">
              <td>{h.foot.replace("leg.", "").replace(".cannon.hoof", "")}</td>
              <td className="text-right">{pct(h.contact_fraction)}</td>
              <td className="text-right">{pct(h.planned_support_fraction)}</td>
              <td className="text-right">{fmt(h.peak_force_n, 1)} N ({h.peak_over_weight == null ? "–" : `${fmt(h.peak_over_weight, 2)}× weight`})</td>
              <td className="text-right">{h.impacts}{h.impacts ? ` (up to ${fmt(h.peak_impact_speed_m_s, 2)} m/s)` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-0.5 text-dim">
        {rep.hooves_down_fewer_than_3_fraction != null ? `Fewer than three hooves on the ground ${pct(rep.hooves_down_fewer_than_3_fraction)} of the clip. ` : ""}
        {rep.stance ? `Planted: ${rep.stance.min_support} hooves kept down, centre of mass ${rep.stance.stability_margin_mm} mm inside. ` : ""}
        No hoof limit is in the library: forces are reported, not judged.
      </div>
      <div className="mt-0.5" data-testid="physics-battery">
        Battery: peak {fmt(rep.battery.peak_power_w, 1)} W mechanical, mean {fmt(rep.battery.mean_power_w, 1)} W ·{" "}
        {rep.battery.known ? `peak current ${fmt(rep.battery.peak_current_a ?? 0, 2)} A` : `current at least ${fmt(rep.battery.peak_current_lower_bound_a ?? 0, 2)} A (a lower bound)`}
        <span className="text-dim"> · {rep.battery.note}</span>
      </div>
      {rep.events.length > 0 && (
        <details className="mt-0.5">
          <summary className="cursor-pointer text-dim">{rep.events_total} spans over a limit</summary>
          {rep.events.map((e, i) => (
            <button key={i} className="block w-full text-left hover:bg-bg3" onClick={() => { seek(runId, e.rollout_frame); if (e.video_frame != null) onSeekVideo?.(e.video_frame); }}>
              {fmt(e.t0, 2)}–{fmt(e.t1, 2)} s ({e.phase}{e.video_frame != null ? `, frame ${e.video_frame}` : ""}): {e.label} at {e.joint}, {pct(e.peak)} of the limit
            </button>
          ))}
        </details>
      )}
      <BasisLine basis={basis} />
    </div>
  );
}

function TimeStrip({ rep, onPick }: { rep: PhysicsReport; onPick: (col: number) => void }) {
  const cols = rep.strip.t.length;
  const rows = rep.strip.rows;
  if (!cols || !rows.length) return null;
  const h = 6;
  return (
    <div className="mt-1" data-testid="physics-strip">
      <div className="flex">
        <div className="w-28 shrink-0 text-[9px] leading-[12px] text-dim">
          <div className="h-[6px]" />
          {rows.map((r) => <div key={r.key} className="truncate" title={`${r.label}: peak ${pct(r.peak)} at ${r.peak_joint}`}>{r.label}</div>)}
        </div>
        <svg className="block w-full cursor-pointer" style={{ height: 6 + rows.length * 12 }} viewBox={`0 0 ${cols} ${h + rows.length * 12}`} preserveAspectRatio="none"
          onClick={(e) => { const b = e.currentTarget.getBoundingClientRect(); onPick(Math.min(cols - 1, Math.max(0, Math.floor((e.clientX - b.left) / b.width * cols)))); }}>
          {rep.strip.phase.map((p, i) => <rect key={`p${i}`} x={i} y={0} width={1.02} height={h - 1} fill={p === 1 ? "#64748b" : "#cbd5e1"} />)}
          {rows.map((r, k) => r.levels.map((lv, i) => (
            <rect key={`${r.key}${i}`} x={i} y={h + k * 12} width={1.02} height={11} fill={LEVEL[lv]} opacity={lv ? 0.9 : 0.35} data-level={lv}>
              <title>{`${fmt(rep.strip.t[i], 2)} s (${PHASE[rep.strip.phase[i]]}${rep.strip.video_frame[i] != null ? `, video frame ${rep.strip.video_frame[i]}` : ""}): ${r.label}${r.joints[i] ? ` at ${r.joints[i]}` : ""}`}</title>
            </rect>
          )))}
        </svg>
      </div>
      <div className="text-[9px] text-dim">top band: dark = the clip, light = lead-in and return · green within, amber over 90 % of the limit, red over (with the margin) · click a cell to see that moment</div>
    </div>
  );
}

function BasisLine({ basis }: { basis: Basis }) {
  const servos = Object.entries(basis.servos);
  return (
    <div className="mt-1 rounded bg-bg3 p-1 text-[9px] text-dim" data-testid="physics-basis">
      Rests on: mass {fmt(basis.total_mass_g / 1000, 2)} kg as entered
      {basis.missing_masses.length ? ` (no mass for ${basis.missing_masses.length} parts: ${basis.missing_masses.slice(0, 6).join(", ")}${basis.missing_masses.length > 6 ? "…" : ""})` : ""}
      {servos.map(([k, s]) => ` · ${s.count}× ${k} ${s.verified ? "verified" : "UNVERIFIED"}${s.armature_default ? `, armature default ${s.armature_kgm2} kg·m²` : ""}${s.missing?.length ? `, missing ${s.missing.join(", ")}` : ""}`).join("")}
      {basis.armature_scale !== 1 ? ` · armature × ${basis.armature_scale}` : ""}
      {basis.provisional.length ? ` · ${basis.provisional.length} PROVISIONAL values (joint ranges, springs, layout: Belts panel)` : ""}
    </div>
  );
}
