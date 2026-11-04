// The video inbox and the review of candidate clips (ADR-076, ADR-077,
// ADR-078, ADR-080). The server tracks, retargets or lifts in 3D, and cuts;
// it serves the frames, the tracked points and the per-frame reliability of
// the lift, which this file only draws. Forms come from command schemas.
// Play advances only once the shown frame has loaded, dropping frames rather
// than freezing (ADR-081).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "@/api/client";
import type { Schema } from "@/api/types";
import { replayRun } from "@/commands/registry";
import { SchemaForm } from "@/components/SchemaForm";
import { Badge, Button, Section, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";
import { PhysicsActions } from "./Physics";

export interface Candidate {
  id: string;
  start: number;
  end: number;
  kind: string;
  name: string;
  period_s: number | null;
  far_side: string;
  seconds: number;
  periodicity: number;
  turned_fraction: number | null;
  view_ok: boolean | null;
  status: "pending" | "accepted" | "rejected";
  clip: string;
  reliable_fraction?: number | null;
  ambiguous_fraction?: number | null;
  view_yaw_range_deg?: [number, number] | null;
  turn_deg?: number | null;
  reference?: string;
  legs_seen?: Record<string, number> | null;
}
interface LiftSummary {
  map?: string;
  camera?: { elevation_deg?: number; roll_deg?: number; fixed?: boolean; note?: string; depth_note?: string };
  proportions?: { trunk_length?: number; trunk_width?: number; front_leg?: number; width_over_length?: number; width_source?: string; note?: string; landmark_at?: Record<string, number> };
  summary?: { reliable_fraction?: number; ambiguous_fraction?: number; median_view_yaw_deg?: number | null; heading_range_deg?: [number, number]; median_residual_px?: number; labels_exchanged_fraction?: number };
  landmark_residual_px?: Record<string, number> | null;
  unobservable_fraction?: Record<string, number> | null;
}
interface LiftFrames {
  mode: string;
  frames: number;
  state: string[];
  view_yaw_deg: number[];
  heading_deg: number[];
  residual_px: (number | null)[];
  reasons: string[][];
  ambiguous: string[][];
  unobservable: string[][];
}
interface JointRow { joint: string; in_clip: boolean; min_deg?: number; max_deg?: number; range_deg: [number, number]; peak_speed_deg_s?: number; speed_limit_deg_s: number; speed_ratio?: number; out_of_range_fraction?: number; note?: string }
interface ClipReport { verdict: string; note: string; joints?: JointRow[] }
interface Motion { turn_deg?: number; heading_range_deg?: [number, number]; travel_mm?: number; legs?: Record<string, string>; reference?: string; unreliable_frames?: number }
export interface VideoRow {
  file: string;
  sha256: string;
  status: string;
  reason: string;
  progress: number;
  job: string;
  info: { fps?: number; frames?: number; width?: number; height?: number; duration_s?: number; reader?: string };
  tracker: { tracker?: string; model?: string; version?: string; device?: string };
  map: { name?: string; near_side?: string };
  near_side: { near_side?: string; method?: string; agree?: boolean };
  view: { verdict?: string; note?: string; median_yaw_deg?: number | null };
  standing_frame: number | null;
  candidates: Candidate[];
  mode?: string;
  lift?: LiftSummary;
  reference?: string;
}
export interface InboxData {
  dir: string;
  videos: VideoRow[];
  settings: Record<string, unknown>;
  trackers: { key: string; label: string; available: boolean; availability: string; model_id: string }[];
  models: { key: string; label: string; licence: string; research_use: string; missing: string[]; size_mb: number }[];
  watching: boolean;
}
interface Points {
  names: string[];
  links: [string, string][];
  used: string[];
  start: number;
  end: number;
  image_size: [number, number] | null;
  min_likelihood: number;
  frames: [number | null, number | null, number][][];
}

const STATUS: Record<string, "ok" | "warn" | "err" | "info" | "neutral"> = {
  waiting: "neutral", queued: "neutral", tracking: "info", retargeting: "info", needs_review: "warn", ready: "ok",
  failed: "err", cancelled: "neutral", missing: "err",
};
const BUSY = ["queued", "waiting", "tracking", "retargeting"];
const HIDDEN = new Set(["file", "candidate", "start", "end"]);

type Say = (p: Promise<unknown>, ok: (r: any) => string) => void;

export function FootageInbox({ inbox, say, selected, onSelect }: { inbox: InboxData; say: Say; selected: string | null; onSelect: (f: string | null) => void }) {
  const run = useLab((s) => s.run);
  const jobs = useLab((s) => s.jobs);
  const commands = useLab((s) => s.commands);
  const settingsCmd = commands.find((c) => c.key === "set_footage_settings");
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const tracker = inbox.trackers.find((t) => t.key === inbox.settings.tracker);
  const missingModels = inbox.models.filter((m) => m.missing.length > 0);
  return (
    <Section
      title="Video inbox"
      right={
        <span className="flex gap-1">
          <Button size="sm" variant="ghost" title="Tracker, map and segmentation settings" onClick={() => setShowSettings(!showSettings)}>Settings</Button>
          <Button size="sm" data-testid="scan-footage" onClick={() => say(run("scan_footage"), (r) => (r.started ? `Processing ${r.started}` : "Nothing new in the folder"))}>Scan now</Button>
        </span>
      }
    >
      <div className="mb-1 text-[11px] text-dim">
        Drop mp4, mov, avi or mkv files into <code className="selectable">{inbox.dir}</code>.{" "}
        {inbox.watching ? "The lab looks every few seconds" : "Press Scan now"}; each new or changed video is tracked with{" "}
        <b>{tracker?.label ?? String(inbox.settings.tracker)}</b>, retargeted with <b>{String(inbox.settings.map)}</b> and cut into candidates for you to review.
      </div>
      {tracker && !tracker.available && <div className="mb-1 text-[11px] text-warn" data-testid="tracker-unavailable">{tracker.availability}</div>}
      {missingModels.map((m) => (
        <div key={m.key} className="mb-1 rounded border border-line p-1 text-[11px]">
          <div><b>{m.label}</b> ({fmt(m.size_mb, 0)} MB) is not downloaded.</div>
          <div className="text-dim">Licence: {m.licence}. Research use: {m.research_use}.</div>
          <Button size="sm" onClick={() => say(run("download_tracker_model", { package: m.key }), () => `Downloading ${m.key} (a job)`)}>Download</Button>
        </div>
      ))}
      {showSettings && settingsCmd && (
        <div className="mb-1 rounded border border-line p-1">
          <SchemaForm schema={settingsCmd.schema} values={{ ...inbox.settings, segmentation: {}, ...(settings ?? {}) }} onChange={(p) => setSettings((s) => ({ ...(s ?? {}), ...p }))} />
          <Button size="sm" variant="primary" disabled={!settings}
            onClick={() => say(run("set_footage_settings", { ...inbox.settings, segmentation: {}, ...(settings ?? {}) }).then((r) => { setSettings(null); return r; }), () => "Footage settings saved (Retry a video to use them)")}>
            Save settings
          </Button>
        </div>
      )}
      {inbox.videos.length === 0 ? (
        <div className="text-dim">No videos yet. Copy a video of a calf, filmed from the side, into the folder above.</div>
      ) : (
        <table className="w-full text-[11px]" data-testid="video-inbox">
          <tbody>
            {inbox.videos.map((v) => {
              const job = jobs.find((j) => j.id === v.job && j.status === "running");
              const progress = job ? job.progress : v.progress;
              const pending = v.candidates.filter((c) => c.status === "pending").length;
              return (
                <tr key={v.file} className={`border-t border-line/40 ${selected === v.file ? "bg-bg3" : ""}`} data-video={v.file}>
                  <td className="py-0.5">
                    <button className="font-semibold hover:underline" onClick={() => onSelect(selected === v.file ? null : v.file)}>{v.file}</button>
                    <div className="text-[10px] text-dim">
                      {v.info.duration_s ? `${fmt(v.info.duration_s, 1)} s · ${fmt(v.info.fps, 2)} fps · ` : ""}
                      {v.candidates.length ? `${v.candidates.length} candidates${pending ? `, ${pending} to review` : ""}` : ""}
                      {v.mode ? ` · ${v.mode.toUpperCase()}` : ""}{v.view.verdict ? ` · ${v.view.verdict}` : ""}
                    </div>
                    {v.reason && <div className={`text-[10px] ${v.status === "failed" ? "text-err" : "text-dim"}`}>{v.reason}</div>}
                    {BUSY.includes(v.status) && v.status !== "waiting" && (
                      <div className="mt-0.5 h-1 w-full rounded bg-bg3"><div className="h-1 rounded bg-accent" style={{ width: `${Math.round(progress * 100)}%` }} /></div>
                    )}
                  </td>
                  <td className="w-24 text-right align-top">
                    <Badge tone={STATUS[v.status] ?? "neutral"}>{v.status.replace("_", " ")}</Badge>
                    <div className="mt-0.5 flex justify-end gap-1">
                      {BUSY.includes(v.status) ? (
                        <Button size="sm" variant="ghost" onClick={() => say(run("cancel_video", { file: v.file }), () => `Cancelled ${v.file}`)}>Cancel</Button>
                      ) : (
                        <>
                          <Button size="sm" variant="ghost" title="Track and process again" onClick={() => say(run("retry_video", { file: v.file }), () => `Queued ${v.file}`)}>Retry</Button>
                          {v.sha256 && v.status !== "failed" && (
                            <Button size="sm" variant="ghost" data-testid={`reanalyse-${v.file}`} title="Analyse again with the current settings (2D or 3D), keeping the tracks"
                              onClick={() => say(run("reanalyse_video", { file: v.file }), () => `Analysing ${v.file} again`)}>Analyse again</Button>
                          )}
                        </>
                      )}
                      {v.candidates.length > 0 && (
                        <Button size="sm" data-testid={`review-${v.file}`} onClick={() => onSelect(v.file)}>Review</Button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Section>
  );
}

export const frameUrl = (file: string, frame: number) => `/api/footage/${encodeURIComponent(file)}/frame/${frame}?width=640`;

/** The video frame with the tracked points drawn over it. The points follow the image actually shown, which can
 * lag the requested frame while it loads. */
function FrameView({ file, frame, points, onShown }: { file: string; frame: number; points: Points | null; onShown?: (f: number) => void }) {
  const [shown, setShown] = useState(frame);
  const size = points?.image_size ?? null;
  const row = points && shown >= points.start && shown < points.end ? points.frames[shown - points.start] : null;
  const idx = useMemo(() => new Map((points?.names ?? []).map((n, i) => [n, i])), [points]);
  return (
    <div className="relative w-full bg-black" data-testid="review-frame" data-shown={shown}>
      <img className="block w-full" src={frameUrl(file, frame)} alt={`${file} frame ${frame}`}
        onLoad={() => { setShown(frame); onShown?.(frame); }} onError={() => onShown?.(frame)} />
      {size && row && (
        <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="none">
          {points!.links.map(([a, b]) => {
            const pa = row[idx.get(a)!];
            const pb = row[idx.get(b)!];
            if (!pa || !pb || pa[0] === null || pb[0] === null) return null;
            const weak = pa[2] < points!.min_likelihood || pb[2] < points!.min_likelihood;
            return <line key={`${a}-${b}`} x1={pa[0]} y1={pa[1]!} x2={pb[0]} y2={pb[1]!} stroke={weak ? "#888" : "#38bdf8"} strokeWidth={size[0] / 300} strokeDasharray={weak ? `${size[0] / 150}` : undefined} />;
          })}
          {points!.names.map((n, i) => {
            const p = row[i];
            if (!p || p[0] === null) return null;
            const used = points!.used.includes(n);
            const weak = p[2] < points!.min_likelihood;
            return (
              <circle key={n} cx={p[0]} cy={p[1]!} r={(used ? 5 : 3.5) * size[0] / 640} fill={weak ? "none" : used ? "#f59e0b" : "#38bdf8"} stroke={weak ? "#f87171" : "#000"} strokeWidth={size[0] / 640}>
                <title>{`${n} (${p[2].toFixed(2)})`}</title>
              </circle>
            );
          })}
        </svg>
      )}
    </div>
  );
}

const STATE_COLOUR: Record<string, string> = { ok: "#22c55e", ambiguous: "#f59e0b", unreliable: "#ef4444", missing: "#6b7280" };

/** Per-frame reliability of the 3D lift and the estimated yaw, under the frame slider (values from the server). */
function LiftStrip({ lift, start, end, frame, onPick }: { lift: LiftFrames; start: number; end: number; frame: number; onPick: (f: number) => void }) {
  const n = Math.max(1, end - start);
  const yawPath = useMemo(() => {
    const pts: string[] = [];
    for (let f = start; f < end && f < lift.frames; f++) pts.push(`${f - start + 0.5},${(90 - lift.view_yaw_deg[f]) / 180 * 20}`);
    return pts.join(" ");
  }, [lift, start, end]);
  const f = Math.min(Math.max(frame, 0), lift.frames - 1);
  const why = [...(lift.reasons[f] ?? []), ...(lift.ambiguous[f] ?? []).map((a) => `ambiguous: ${a}`)];
  return (
    <div className="mt-0.5" data-testid="lift-strip">
      <svg className="block h-6 w-full cursor-pointer" viewBox={`0 0 ${n} 20`} preserveAspectRatio="none"
        onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); onPick(start + Math.floor((e.clientX - r.left) / r.width * n)); }}>
        {Array.from({ length: n }, (_, i) => start + i).filter((g) => g < lift.frames).map((g) => (
          <rect key={g} x={g - start} y={0} width={1.02} height={20} fill={STATE_COLOUR[lift.state[g]] ?? "#6b7280"} opacity={0.55} />
        ))}
        <line x1={0} x2={n} y1={10} y2={10} stroke="#000" strokeOpacity={0.25} strokeWidth={0.3} vectorEffect="non-scaling-stroke" />
        <polyline points={yawPath} fill="none" stroke="#0f172a" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        <rect x={frame - start} y={0} width={1} height={20} fill="none" stroke="#fff" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="flex justify-between text-[10px] text-dim" data-testid="lift-frame">
        <span>
          <b style={{ color: STATE_COLOUR[lift.state[f]] }}>{lift.state[f]}</b> · yaw {fmt(lift.view_yaw_deg[f], 0)}° {lift.view_yaw_deg[f] >= 0 ? "toward" : "away from"} the camera · heading {lift.heading_deg[f] >= 0 ? "+" : ""}{fmt(lift.heading_deg[f], 0)}°
          {lift.residual_px[f] !== null ? ` · residual ${fmt(lift.residual_px[f]!, 0)} px` : ""}
        </span>
        <span title={(lift.unobservable[f] ?? []).length ? `not seen in this view: ${lift.unobservable[f].join(", ")}` : undefined}>{why.join("; ")}</span>
      </div>
      <div className="text-[9px] text-dim">strip: green reliable · amber ambiguous · red unreliable (a gap) · line: yaw from a side view (top = head-on toward the camera, middle = side view, bottom = turned away)</div>
    </div>
  );
}

/** What the 3D lift found for the whole video. */
function LiftSummaryLine({ video }: { video: VideoRow }) {
  const l = video.lift;
  if (!l?.summary) return null;
  const p = l.proportions ?? {};
  return (
    <div className="mb-1 text-[10px] text-dim" data-testid="lift-summary">
      <Badge tone="info">3D lift</Badge> {fmt((l.summary.reliable_fraction ?? 0) * 100, 0)} % of frames reliable
      {l.summary.median_view_yaw_deg != null ? ` · median yaw ${fmt(l.summary.median_view_yaw_deg, 0)}°` : ""}
      {l.summary.heading_range_deg ? ` · heading ${fmt(l.summary.heading_range_deg[0], 0)}…${fmt(l.summary.heading_range_deg[1], 0)}°` : ""}
      {` · camera elevation ${fmt(l.camera?.elevation_deg ?? 0, 0)}°${l.camera?.fixed === false ? " (may move)" : ""}`}
      {` · calf/robot: trunk ${fmt(p.trunk_length ?? 1, 2)}, width ${fmt(p.trunk_width ?? 1, 2)}${p.width_source === "prior" ? " (prior W/L 0.35, PROVISIONAL)" : ""}, front leg ${fmt(p.front_leg ?? 1, 2)}`}
      {video.reference ? ` · angles relative to ${video.reference}` : ""}
      <span title={[l.camera?.note, l.camera?.depth_note, p.note,
        p.landmark_at ? `landmarks placed: ${Object.entries(p.landmark_at).map(([k, v]) => `${k} ${fmt(v, 2)}`).join(", ")}` : "",
        l.landmark_residual_px ? `residual per landmark (px): ${Object.entries(l.landmark_residual_px).map(([k, v]) => `${k} ${v}`).join(", ")}` : ""].filter(Boolean).join("\n")}> ⓘ</span>
    </div>
  );
}

/** The body report of a preview: per joint, range used against the joint's range, and peak speed against the servo's. */
function JointTable({ rows }: { rows: JointRow[] }) {
  return (
    <table className="mt-0.5 w-full text-[10px]" data-testid="joint-report">
      <thead><tr className="text-dim"><td>joint</td><td className="text-right">clip range °</td><td className="text-right">joint range °</td><td className="text-right">peak °/s</td><td className="text-right">servo °/s</td></tr></thead>
      <tbody>
        {rows.filter((r) => r.in_clip).map((r) => (
          <tr key={r.joint} className={(r.speed_ratio ?? 0) > 1 || (r.out_of_range_fraction ?? 0) > 0 ? "text-warn" : ""}>
            <td>{r.joint.replace("joint.", "")}{r.joint.endsWith("hip_abd") ? " (ab/ad)" : ""}</td>
            <td className="text-right">{fmt(r.min_deg ?? 0, 1)} … {fmt(r.max_deg ?? 0, 1)}</td>
            <td className="text-right">{r.range_deg[0]} … {r.range_deg[1]}</td>
            <td className="text-right">{fmt(r.peak_speed_deg_s ?? 0, 0)}</td>
            <td className="text-right">{fmt(r.speed_limit_deg_s, 0)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function CandidateReview({ video, say }: { video: VideoRow; say: Say }) {
  const run = useLab((s) => s.run);
  const commands = useLab((s) => s.commands);
  const acceptCmd = commands.find((c) => c.key === "accept_candidate");
  const [cid, setCid] = useState<string | null>(video.candidates.find((c) => c.status === "pending")?.id ?? video.candidates[0]?.id ?? null);
  const cand = video.candidates.find((c) => c.id === cid) ?? null;
  const [trim, setTrim] = useState<[number, number] | null>(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [points, setPoints] = useState<Points | null>(null);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [report, setReport] = useState<ClipReport | null>(null);
  const [motion, setMotion] = useState<Motion | null>(null);
  const [lift, setLift] = useState<LiftFrames | null>(null);
  const loading = useRef(false); // a frame is on its way: Play waits for it instead of piling up requests
  const fps = video.info.fps ?? 25;
  const range: [number, number] = trim ?? (cand ? [cand.start, cand.end] : [0, 1]);

  const candStart = cand?.start ?? -1;
  const candEnd = cand?.end ?? -1;
  const [r0, r1] = range;
  useEffect(() => {
    if (candStart < 0) return;
    setTrim(null);
    setFrame(candStart);
    setReport(null);
    setMotion(null);
    setForm({});
    const pad = Math.round(fps * 2); // a little either side, for trimming outward
    const file = encodeURIComponent(video.file);
    void api.get<Points>(`/api/footage/${file}/points?start=${Math.max(0, candStart - pad)}&end=${candEnd + pad}`)
      .then(setPoints).catch(() => setPoints(null));
    void api.post(`/api/footage/${file}/prefetch?start=${candStart}&end=${candEnd}&width=640`, {}).catch(() => undefined);
  }, [cid, candStart, candEnd, fps, video.file, video.sha256]);
  useEffect(() => {
    if (video.mode !== "3d") { setLift(null); return; }
    void api.get<LiftFrames>(`/api/footage/${encodeURIComponent(video.file)}/lift`).then(setLift).catch(() => setLift(null));
  }, [video.file, video.sha256, video.mode]);
  // Play: the frame follows the clock, but a new one is asked for only once the last has loaded (frames are
  // dropped, never queued), so a slow server shows fewer frames instead of freezing on the first.
  // The next frame is asked for when the last one has loaded (or, if it is not yet due, when it is).
  const next = useRef<(() => void) | null>(null);
  const frameRef = useRef(frame);
  useEffect(() => { frameRef.current = frame; }, [frame]);
  useEffect(() => {
    if (!playing) { next.current = null; return; }
    const t0 = performance.now();
    const f0 = frame;
    const span = Math.max(1, r1 - r0);
    let timer: ReturnType<typeof setTimeout> | undefined;
    loading.current = false;
    const tick = () => {
      clearTimeout(timer);
      if (loading.current || next.current !== tick) return;
      const elapsed = (performance.now() - t0) / 1000 * fps;
      const target = r0 + ((f0 - r0 + Math.floor(elapsed)) % span + span) % span;
      if (target !== frameRef.current) {
        frameRef.current = target;
        loading.current = true; // onShown calls tick again
        setFrame(target);
      } else timer = setTimeout(tick, Math.max(4, (1 - (elapsed % 1)) * 1000 / fps));
    };
    next.current = tick;
    tick();
    return () => { clearTimeout(timer); next.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, r0, r1, fps]);
  const onShown = useCallback(() => { loading.current = false; next.current?.(); }, []);

  const formSchema: Schema | null = acceptCmd ? { ...acceptCmd.schema, fields: acceptCmd.schema.fields.filter((f) => !HIDDEN.has(f.name)) } : null;
  const params = (extra: Record<string, unknown> = {}) => ({
    file: video.file, candidate: cand?.id, start: range[0], end: range[1], ...extra,
  });

  return (
    <Section title={`Review: ${video.file}`}>
      {video.mode === "3d" && <LiftSummaryLine video={video} />}
      <div className="mb-1 text-[11px] text-dim" data-testid="review-summary">
        {video.view.verdict && video.mode !== "3d" && <span><Badge tone={video.view.verdict.startsWith("side view OK") ? "ok" : video.view.verdict.startsWith("too") ? "err" : "neutral"} title={video.view.note}>{video.view.verdict}</Badge> </span>}
        near side {video.near_side.near_side ?? "?"} ({video.near_side.method ?? "map"}{video.near_side.agree === false ? ", confidence disagrees" : ""}) · map {video.map.name} · {video.tracker.model ?? video.tracker.tracker} {video.tracker.version}
        {video.tracker.device ? ` on ${video.tracker.device}` : ""}
      </div>
      <div className="mb-1 flex flex-wrap gap-1">
        {video.candidates.map((c) => (
          <button key={c.id} data-testid={`candidate-${c.id}`} onClick={() => setCid(c.id)}
            className={`rounded border px-1 text-[11px] ${c.id === cid ? "border-accent" : "border-line"} ${c.status === "rejected" ? "opacity-50 line-through" : ""}`}
            title={`${c.kind}${c.period_s ? `, period ${c.period_s} s` : ""}, frames ${c.start}-${c.end}${c.reliable_fraction != null ? `, ${Math.round(c.reliable_fraction * 100)} % reliable` : c.view_ok === false ? ", turned from the camera" : ""}`}>
            {c.id} {c.kind} {fmt(c.seconds, 1)} s {c.status === "accepted" ? "✓" : ""}{c.view_ok === false ? " ⚠" : ""}
          </button>
        ))}
      </div>
      {cand && (
        <>
          <FrameView file={video.file} frame={frame} points={points} onShown={onShown} />
          <div className="mt-1 flex items-center gap-1 text-[11px]">
            <Button size="sm" onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Play"}</Button>
            <input type="range" className="flex-1" min={points?.start ?? range[0]} max={Math.max((points?.end ?? range[1]) - 1, range[0])} value={frame}
              onChange={(e) => setFrame(Number(e.target.value))} aria-label="Frame" />
            <span className="w-24 text-right text-dim">frame {frame} · {fmt(frame / fps, 2)} s</span>
          </div>
          {lift && lift.frames > 0 && (
            <LiftStrip lift={lift} start={points?.start ?? range[0]} end={points?.end ?? range[1]} frame={frame} onPick={setFrame} />
          )}
          <div className="mt-1 flex items-center gap-1 text-[11px]">
            <span className="text-dim">Cut</span>
            <span data-testid="trim-range">{range[0]}–{range[1]}</span>
            <span className="text-dim">({fmt((range[1] - range[0]) / fps, 2)} s)</span>
            <Button size="sm" variant="ghost" onClick={() => setTrim([Math.min(frame, range[1] - 1), range[1]])}>Start here</Button>
            <Button size="sm" variant="ghost" onClick={() => setTrim([range[0], Math.max(frame + 1, range[0] + 1)])}>End here</Button>
            {trim && <Button size="sm" variant="ghost" onClick={() => setTrim(null)}>Reset</Button>}
          </div>
          <div className="mt-1 text-[10px] text-dim">
            {cand.kind}{cand.period_s ? ` · period ${cand.period_s} s (${cand.periodicity} regular) · far legs half a period behind` : ""}
            {cand.turned_fraction ? ` · turned from the camera ${fmt(cand.turned_fraction * 100, 0)} % of the time` : ""}
            {cand.reliable_fraction != null ? ` · ${fmt(cand.reliable_fraction * 100, 0)} % of frames reliable` : ""}
            {cand.turn_deg != null ? ` · turns ${cand.turn_deg >= 0 ? "left" : "right"} ${fmt(Math.abs(cand.turn_deg), 0)}°` : ""}
            {cand.view_yaw_range_deg ? ` · yaw ${fmt(cand.view_yaw_range_deg[0], 0)}…${fmt(cand.view_yaw_range_deg[1], 0)}°` : ""}
            {cand.reference ? ` · relative to ${cand.reference}` : ""}
          </div>
          <div className="mt-1 flex gap-1">
            <Button size="sm" data-testid="preview-candidate" title="Pose the robot with this cut (no physics) and replay it in the viewport"
              onClick={() => say(run<{ run_id: string; report: ClipReport; motion?: Motion }>("preview_candidate", params({ far_side: form.far_side ?? "" }))
                .then((r) => { setReport(r.report); setMotion(r.motion ?? null); return replayRun(r.run_id).then(() => r); }), (r) => `Previewing on the robot: ${r.report.note}`)}>
              Preview on robot
            </Button>
            {report && <span className="text-[11px] text-dim" data-testid="candidate-report">{report.verdict}: {report.note}</span>}
          </div>
          <PhysicsActions source={{ file: video.file, candidate: cand.id, start: range[0], end: range[1], far_side: String(form.far_side ?? "") }}
            onSeekVideo={(f) => { setPlaying(false); setFrame(f); }} />
          {motion && (
            <div className="mt-0.5 text-[10px] text-dim" data-testid="candidate-motion">
              turns {fmt(motion.turn_deg ?? 0, 0)}° (heading {fmt(motion.heading_range_deg?.[0] ?? 0, 0)}…{fmt(motion.heading_range_deg?.[1] ?? 0, 0)}°) · travels {fmt((motion.travel_mm ?? 0) / 1000, 2)} m
              {motion.unreliable_frames ? ` · ${motion.unreliable_frames} unreliable frames interpolated` : ""}
              {motion.legs ? ` · legs: ${Object.entries(motion.legs).map(([k, v]) => `${k} ${v}`).join(", ")}` : ""}
              <div>The preview shows the turn; the simulator does not steer to follow it yet.</div>
            </div>
          )}
          {report?.joints && <JointTable rows={report.joints} />}
          {cand.status === "pending" && formSchema && (
            <div className="mt-1 rounded border border-line p-1">
              <div className="mb-0.5 text-[10px] uppercase text-dim">Your annotation (the lab never infers affect)</div>
              <SchemaForm schema={formSchema} values={{ ...Object.fromEntries(formSchema.fields.map((f) => [f.name, f.default])), name: cand.name, ...form }}
                onChange={(p) => setForm((f) => ({ ...f, ...p }))} />
              <div className="mt-1 flex gap-1">
                <Button size="sm" variant="primary" data-testid="accept-candidate"
                  onClick={() => say(run("accept_candidate", params({ name: cand.name, ...form })), (r) => `Accepted as clip ${r.clip}: ${r.report.note}`)}>
                  Accept as clip
                </Button>
                <Button size="sm" variant="danger" onClick={() => say(run("reject_candidate", { file: video.file, candidate: cand.id }), () => `Rejected ${cand.id}`)}>Reject</Button>
              </div>
            </div>
          )}
          {cand.status === "accepted" && <div className="mt-1 text-[11px] text-ok">Accepted as clip <b>{cand.clip}</b> (see Clips below).</div>}
        </>
      )}
    </Section>
  );
}

export function sayWith(setMsg: (m: { ok: boolean; text: string }) => void, refresh: () => void): Say {
  return (p, ok) =>
    void p.then((r) => { setMsg({ ok: true, text: ok(r) }); refresh(); })
      .catch((e: unknown) => setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) }));
}
