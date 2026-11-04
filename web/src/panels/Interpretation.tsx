// Interpretation (ADR-085): what the calf did, read from the footage, and what the robot does instead, side by side.
// The server reads, interprets, plays and compares; this file starts the jobs and draws the stored report only.
// Clicking a calf behaviour opens its frames in the Review; clicking the robot's strip seeks the replay.
import { useEffect, useState } from "react";
import { ApiError, api } from "@/api/client";
import { replayRun } from "@/commands/registry";
import { Badge, Button, Section, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";

interface Stretch { video: string; start: number; end: number; t0: number; t1: number; behaviour: string; confidence: number; censored: boolean; evidence: { rule: string } }
interface VideoR { file: string; usable: boolean; reasons: string[]; seconds: number; seconds_read: number; stretches: number; camera?: { motion?: { median_bl_s?: number; moves?: boolean } }; lift?: { reliable_fraction?: number; contact?: string } }
interface Row { feature: string; label: string; calf: number | null; robot: number | null; ratio: number | null; verdict: string; why: string }
interface Rec {
  behaviour: string; primitive: string; params: Record<string, unknown>; within_limits: boolean; fell: boolean; margin: number | null; violations: string[];
  comparison: Row[]; alternatives: { primitive: string; feasible: boolean; best_distance: number; evaluated: number; feasible_share: number }[];
  note: string; cost: { plays: number; cache_hits: number; seconds: number }; read: { n: number; seconds: number; videos: string[] };
}
interface Episode { name: string; primitive: string; t0: number; t1: number; waited_s?: number; unsafe_switch?: boolean }
interface StripRow { key: string; label: string; levels: number[] }
interface Play { seed: number; report: { verdict: string; fell: boolean; fall_time_s: number | null; safety: { margin: number | null; violations: string[] }; strip: { t: number[]; t_end: number; rollout_frame: number[]; rows: StripRow[] }; hooves_down_fewer_than_3_fraction: number | null }; episodes: Episode[] }
interface Cmp {
  behaviours: string[];
  shares: Record<"calf" | "robot_intended" | "robot_read", Record<string, number>>;
  transitions: { calf: Record<string, Record<string, number>>; robot_intended: Record<string, Record<string, number>> };
  durations: Record<string, { calf_median_s: number | null; calf_n: number; robot_median_s: number | null; robot_n: number }>;
  features: Record<string, Record<string, { calf: number | null; robot: number | null }>>;
}
interface Constraint { label: string; margin: number | null; violated: boolean }
interface Report {
  run_id: string; reading_id: string; labels: Record<string, string>; seconds: number; seeds: number[];
  records: Rec[]; plays: Play[]; comparison: Cmp | null; gaps: { what: string; why: string; seen: Record<string, string>; handling: string }[];
  defaults: { primitive: string; default: { within_limits: boolean; violations: string[]; margin: number | null; constraints: Record<string, Constraint> }; interpreted: { behaviour: string; params: Record<string, unknown>; margin: number | null; constraints: Record<string, Constraint> } | null }[];
  calf: { stretches: Stretch[]; videos: VideoR[]; support: { lines: string[] } };
  transitions_checked?: { from: string; to: string; within_limits: boolean; fell: boolean; margin: number | null; violations: string[] }[];
  adr084: { runs: { run: string; project: string; clip: string | null; character_kept: number | null; verdict: string | null }[]; note: string; source: string };
  cost: { plays: number; cache_hits: number; play_seconds: number; seconds: number; total_seconds: number; note: string };
}

const COLOR: Record<string, string> = { stand: "#94a3b8", weight_shift: "#60a5fa", step: "#a78bfa", walk: "#34d399", turn: "#fbbf24", other: "#f87171" };
const VERDICT_TONE: Record<string, "ok" | "warn" | "err" | "info" | "neutral"> = { kept: "ok", exaggerated: "info", reduced: "warn", dropped: "err", reversed: "err" };
const LEVEL = ["#22c55e", "#f59e0b", "#ef4444"];
const pct = (x: number | null | undefined) => (x == null ? "–" : `${fmt(x * 100, 0)} %`);
const val = (x: unknown) => (typeof x === "number" ? fmt(x, Math.abs(x) < 10 ? 2 : 1) : x == null ? "–" : String(x));

function Bar({ items, t1, onPick, label, testid }: { items: { a: number; b: number; beh: string; title: string; key: string }[]; t1: number; onPick: (i: number, frac: number) => void; label: string; testid?: string }) {
  return (
    <div className="flex items-center gap-1" data-testid={testid}>
      <div className="w-24 shrink-0 truncate text-[9px] text-dim" title={label}>{label}</div>
      <svg className="block h-3 w-full cursor-pointer" viewBox={`0 0 ${Math.max(t1, 1e-3)} 1`} preserveAspectRatio="none"
        onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); const x = (e.clientX - r.left) / r.width * t1; const i = items.findIndex((s) => s.a <= x && x < s.b); if (i >= 0) onPick(i, x); }}>
        {items.map((s) => <rect key={s.key} x={s.a} y={0} width={Math.max(s.b - s.a, 0.001)} height={1} fill={COLOR[s.beh] ?? "#64748b"} data-behaviour={s.beh}><title>{s.title}</title></rect>)}
      </svg>
    </div>
  );
}

export function InterpretationSection({ onOpenFrames }: { onOpenFrames: (file: string, frame: number) => void }) {
  const run = useLab((s) => s.run);
  const jobs = useLab((s) => s.jobs);
  const runs = useLab((s) => s.runs);
  const [rep, setRep] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const job = jobs.find((j) => j.id === jobId) ?? null;
  const load = () => void run<Report>("interpretation_report", {}).then((r) => { setRep(r); setErr(null); }).catch(() => setRep(null));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [runs.length]);
  useEffect(() => { if (job?.status === "done") { setJobId(null); load(); } if (job?.status === "failed") setErr(job.error ?? "failed"); },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [job?.status]);
  const start = (cmd: string, args: Record<string, unknown> = {}) => {
    setErr(null);
    void run<{ job: string }>(cmd, args).then((r) => setJobId(r.job)).catch((e: unknown) => setErr(e instanceof ApiError ? e.message : String(e)));
  };
  const busy = job && (job.status === "running" || job.status === "queued");
  const labels = rep?.labels ?? {};
  const seekRobot = (seed: number, frame: number) => {
    if (!rep) return;
    if (seed !== rep.seeds[0]) return; // only the first seed's rollout is stored for replay
    const pb = usePlayback.getState();
    const go = () => usePlayback.getState().setFrame(frame);
    if (pb.runId === rep.run_id && pb.t.length) { pb.set({ playing: false }); go(); return; }
    void replayRun(rep.run_id).then(() => { usePlayback.getState().set({ playing: false }); go(); });
  };
  const calfVideos = rep?.calf.videos.filter((v) => v.usable) ?? [];
  return (
    <Section title="Interpretation: the calf's behaviours in the robot's own movements"
      right={<span className="flex gap-1">
        <Button size="sm" data-testid="read-footage" disabled={!!busy} title="Read every lifted video into behaviours and a semi-Markov model" onClick={() => start("read_footage")}>Read footage</Button>
        <Button size="sm" variant="primary" data-testid="interpret-footage" disabled={!!busy} title="Interpret the latest reading on this body, then play a minute with three seeds (several minutes; cached per body)" onClick={() => start("interpret_footage")}>Interpret</Button>
      </span>}>
      {busy && (
        <div className="flex items-center gap-1 text-[10px] text-dim" data-testid="interpret-busy">
          <span className="inline-block h-1 w-16 rounded bg-bg3"><span className="block h-1 rounded bg-accent" style={{ width: `${Math.round(job.progress * 100)}%` }} /></span>
          {job.message || job.title}
          <Button size="sm" variant="ghost" onClick={() => void api.post(`/api/jobs/${job.id}/cancel`).catch(() => undefined)}>Cancel</Button>
        </div>
      )}
      {err && <div className="text-[11px] text-err" data-testid="interpret-error">{err}</div>}
      {!rep ? (
        <div className="text-[11px] text-dim" data-testid="interpret-empty">
          Between the video and the robot there is an interpretation, not a copy. Read footage labels what the calf does
          (stand, weight shift, step, walk, turn, other) with its timing and vigour; Interpret says each behaviour in one of
          this body's own movements within every limit, plays a minute of it and shows both side by side.
        </div>
      ) : (
        <div className="text-[10px]" data-testid="interpret-report">
          <div className="mb-1 text-[11px]">Reading {rep.reading_id} · run {rep.run_id} · {rep.records.length} behaviours interpreted · {rep.cost.plays} plays ({rep.cost.cache_hits} cached), {fmt(rep.cost.total_seconds, 0)} s</div>
          <div className="mb-1 text-dim" data-testid="interpret-support">{rep.calf.support.lines.map((l, i) => <div key={i}>{l}</div>)}</div>

          <div className="mb-1" data-testid="interpret-strip">
            <div className="text-[9px] uppercase text-dim">Time strip: calf (click a stretch to open its frames) and robot (click to seek the replay)</div>
            {calfVideos.map((v) => {
              const sts = rep.calf.stretches.filter((s) => s.video === v.file);
              const t1 = Math.max(v.seconds, ...sts.map((s) => s.t1));
              return <Bar key={v.file} label={v.file.replace("Recording ", "")} t1={t1} testid="calf-strip"
                items={sts.map((s, i) => ({ a: s.t0, b: s.t1, beh: s.behaviour, key: `${i}`, title: `${labels[s.behaviour] ?? s.behaviour} ${fmt(s.t0, 1)}–${fmt(s.t1, 1)} s, frames ${s.start}–${s.end}, confidence ${fmt(s.confidence, 2)}: ${s.evidence.rule}` }))}
                onPick={(i) => onOpenFrames(v.file, sts[i].start)} />;
            })}
            {rep.plays.map((p) => {
              const t1 = p.report.strip.t_end || rep.seconds;
              return (
                <div key={p.seed}>
                  <Bar label={`robot, seed ${p.seed}`} t1={t1} testid="robot-strip"
                    items={p.episodes.map((e, i) => ({ a: e.t0, b: e.t1, beh: e.name, key: `${i}`, title: `${labels[e.name] ?? e.name} as ${e.primitive}, ${fmt(e.t0, 1)}–${fmt(e.t1, 1)} s${e.unsafe_switch ? " (switched outside a safe phase)" : ""}` }))}
                    onPick={(_i, x) => { const k = p.report.strip.t.findIndex((tt) => tt >= x); seekRobot(p.seed, p.report.strip.rollout_frame[Math.max(0, k)] ?? 0); }} />
                  {p.report.strip.rows.filter((r) => r.levels.some((l) => l > 0)).map((r) => (
                    <div key={r.key} className="flex items-center gap-1">
                      <div className="w-24 shrink-0 truncate pl-2 text-[9px] text-dim">{r.label}</div>
                      <svg className="block h-2 w-full" viewBox={`0 0 ${r.levels.length} 1`} preserveAspectRatio="none">
                        {r.levels.map((lv, i) => <rect key={i} x={i} y={0} width={1.02} height={1} fill={LEVEL[lv]} opacity={lv ? 0.9 : 0.25} />)}
                      </svg>
                    </div>
                  ))}
                </div>
              );
            })}
            <div className="mt-0.5 flex flex-wrap gap-1 text-[9px]">{Object.entries(COLOR).map(([b, c]) => <span key={b}><span className="inline-block h-2 w-2" style={{ background: c }} /> {labels[b] ?? b}</span>)}<span className="text-dim">· limits: green within, amber near, red over (margin)</span></div>
          </div>

          {rep.comparison && (
            <>
              <table className="mt-1 w-full" data-testid="interpret-shares">
                <thead><tr className="text-dim"><td>behaviour</td><td className="text-right">calf</td><td className="text-right">robot (played)</td><td className="text-right">robot (read back)</td><td className="text-right">calf median s</td><td className="text-right">robot median s</td></tr></thead>
                <tbody>{rep.comparison.behaviours.map((b) => (
                  <tr key={b} className="border-t border-line/40">
                    <td><span className="inline-block h-2 w-2" style={{ background: COLOR[b] }} /> {labels[b] ?? b}</td>
                    <td className="text-right">{pct(rep.comparison!.shares.calf[b])}</td>
                    <td className="text-right">{pct(rep.comparison!.shares.robot_intended[b])}</td>
                    <td className="text-right">{pct(rep.comparison!.shares.robot_read[b])}</td>
                    <td className="text-right">{val(rep.comparison!.durations[b]?.calf_median_s)} ({rep.comparison!.durations[b]?.calf_n ?? 0})</td>
                    <td className="text-right">{val(rep.comparison!.durations[b]?.robot_median_s)} ({rep.comparison!.durations[b]?.robot_n ?? 0})</td>
                  </tr>))}</tbody>
              </table>
              <details className="mt-1" data-testid="interpret-transitions">
                <summary className="cursor-pointer text-dim">Transitions (counts: calf / robot)</summary>
                <table className="w-full"><thead><tr className="text-dim"><td>from \ to</td>{rep.comparison.behaviours.map((b) => <td key={b} className="text-right">{labels[b] ?? b}</td>)}</tr></thead>
                  <tbody>{rep.comparison.behaviours.map((a) => (
                    <tr key={a} className="border-t border-line/40"><td>{labels[a] ?? a}</td>{rep.comparison!.behaviours.map((b) => <td key={b} className="text-right">{a === b ? "" : `${rep.comparison!.transitions.calf[a]?.[b] ?? 0} / ${rep.comparison!.transitions.robot_intended[a]?.[b] ?? 0}`}</td>)}</tr>
                  ))}</tbody></table>
              </details>
              <details className="mt-1" data-testid="interpret-features">
                <summary className="cursor-pointer text-dim">Features per behaviour (calf / robot read back)</summary>
                {Object.entries(rep.comparison.features).map(([b, f]) => (
                  <div key={b} className="mt-0.5"><b>{labels[b] ?? b}</b>: {Object.entries(f).map(([k, v]) => <span key={k} className="mr-2">{k} {val(v.calf)} / {val(v.robot)}</span>)}</div>
                ))}
              </details>
            </>
          )}

          <div className="mt-1 text-[9px] uppercase text-dim">What was read, and what the robot does instead</div>
          {rep.records.map((r) => (
            <div key={r.behaviour} className="mb-1 rounded border border-line p-1" data-testid={`interpretation-${r.behaviour}`}>
              <button className="flex w-full items-center gap-1 text-left" onClick={() => setOpen(open === r.behaviour ? null : r.behaviour)}>
                <span className="inline-block h-2 w-2" style={{ background: COLOR[r.behaviour] }} />
                <b>{labels[r.behaviour] ?? r.behaviour}</b>
                <span className="text-dim">({r.read.n} stretches, {fmt(r.read.seconds, 1)} s) as</span>
                <b>{r.primitive}</b>
                <Badge tone={r.within_limits ? "ok" : r.fell ? "err" : "warn"}>{r.within_limits ? `within limits, margin ${val(r.margin)}` : r.fell ? "falls" : `over: ${r.violations.join(", ")}`}</Badge>
                <span className="ml-auto flex gap-0.5">{r.comparison.map((c) => <Badge key={c.feature} tone={VERDICT_TONE[c.verdict] ?? "neutral"} title={`${c.label}: ${c.verdict}${c.why ? ` — ${c.why}` : ""}`}>{c.verdict[0]}</Badge>)}</span>
              </button>
              {r.note && <div className="text-warn">{r.note}</div>}
              {open === r.behaviour && (
                <div className="mt-0.5">
                  <div className="text-dim">Parameters: {Object.entries(r.params).map(([k, v]) => `${k} ${val(v)}`).join(" · ")}</div>
                  <table className="mt-0.5 w-full"><thead><tr className="text-dim"><td>feature</td><td className="text-right">calf</td><td className="text-right">robot</td><td>verdict</td><td>why</td></tr></thead>
                    <tbody>{r.comparison.map((c) => (
                      <tr key={c.feature} className="border-t border-line/40"><td>{c.label}</td><td className="text-right">{val(c.calf)}</td><td className="text-right">{val(c.robot)}</td><td>{c.verdict}</td><td className="text-dim">{c.why}</td></tr>
                    ))}</tbody></table>
                  <div className="text-dim">Tried: {r.alternatives.map((a) => `${a.primitive} (${a.evaluated} plays, ${pct(a.feasible_share)} within limits, best distance ${fmt(a.best_distance, 2)})`).join(" · ")} · cost {r.cost.plays} plays, {fmt(r.cost.seconds, 0)} s</div>
                </div>
              )}
            </div>
          ))}

          <div className="mt-1 text-[9px] uppercase text-dim">The gaits at margin 0.2: as they are, and as interpreted</div>
          <table className="w-full" data-testid="interpret-defaults"><tbody>{rep.defaults.map((d) => (
            <tr key={d.primitive} className="border-t border-line/40">
              <td>{d.primitive}</td>
              <td>as is: {d.default.within_limits ? "within limits" : `over ${d.default.violations.join(", ")}`} (margin {val(d.default.margin)})</td>
              <td>{d.interpreted ? `interpreted for ${labels[d.interpreted.behaviour] ?? d.interpreted.behaviour}: margin ${val(d.interpreted.margin)} (${Object.entries(d.interpreted.params).map(([k, v]) => `${k} ${val(v)}`).join(", ")})` : "not used by the interpretation"}</td>
            </tr>))}</tbody></table>

          <div className="mt-1 text-[9px] uppercase text-dim">Performance: {fmt(rep.seconds, 0)} s per seed</div>
          {rep.plays.map((p) => (
            <div key={p.seed} data-testid="interpret-play">seed {p.seed}: <Badge tone={p.report.fell ? "err" : p.report.safety.violations.length ? "warn" : "ok"}>{p.report.verdict}</Badge>
              {p.report.fell ? ` at ${fmt(p.report.fall_time_s ?? 0, 1)} s` : ""} · margin {val(p.report.safety.margin)}{p.report.safety.violations.length ? ` · over ${p.report.safety.violations.join(", ")}` : ""} · fewer than three hooves down {pct(p.report.hooves_down_fewer_than_3_fraction)} · {p.episodes.length} episodes{p.episodes.some((e) => e.unsafe_switch) ? ", some switched outside a safe phase" : ""}</div>
          ))}

          {rep.transitions_checked && rep.transitions_checked.length > 0 && (
            <div className="mt-0.5" data-testid="interpret-transitions-checked">
              Transitions played in physics: {rep.transitions_checked.map((t) => (
                <span key={`${t.from}-${t.to}`} className={`mr-2 ${t.within_limits ? "" : "text-warn"}`}>
                  {labels[t.from] ?? t.from} → {labels[t.to] ?? t.to}: {t.within_limits ? `ok (margin ${val(t.margin)})` : `dropped (${t.fell ? "falls" : t.violations.join(", ")})`}
                </span>))}
            </div>
          )}

          <div className="mt-1 text-[9px] uppercase text-dim">What the calf did that this body cannot express</div>
          <ul className="list-disc pl-4" data-testid="interpret-gaps">{rep.gaps.map((g) => (
            <li key={g.what}><b>{g.what}</b>: {g.why}. <span className="text-dim">{Object.entries(g.seen).map(([b, s]) => `${labels[b] ?? b}: ${s}`).join("; ")}{Object.keys(g.seen).length ? " · " : ""}{g.handling}</span></li>
          ))}</ul>

          <div className="mt-1 text-[9px] uppercase text-dim">Replayed clips made feasible (ADR-084), for comparison</div>
          <div data-testid="interpret-adr084">{rep.adr084.runs.length ? rep.adr084.runs.map((r) => <span key={r.run} className="mr-2">{r.clip ?? r.run}: character kept {val(r.character_kept)} ({r.project})</span>) : <span className="text-dim">no Make feasible run found</span>} <span className="text-dim">{rep.adr084.note}</span></div>

          <details className="mt-1"><summary className="cursor-pointer text-dim">Videos read</summary>
            {rep.calf.videos.map((v) => (
              <div key={v.file}>{v.file}: {v.usable ? `read ${fmt(v.seconds_read, 1)} of ${fmt(v.seconds, 1)} s, ${v.stretches} stretches` : "not read"}{v.reasons.length ? ` — ${v.reasons.join("; ")}` : ""}{v.camera?.motion?.median_bl_s != null ? ` · background moves ${fmt(v.camera.motion.median_bl_s, 2)} body lengths/s` : ""}</div>
            ))}
          </details>
          <div className="mt-1 text-dim">Cost on this body: {rep.cost.plays} plays, {fmt(rep.cost.play_seconds, 0)} s of physics, {fmt(rep.cost.seconds, 0)} s interpreting. {rep.cost.note}</div>
        </div>
      )}
    </Section>
  );
}
