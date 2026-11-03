// The video inbox and the review of candidate clips (ADR-076, ADR-077,
// ADR-078). The server tracks, retargets and cuts; it serves the frames and
// the tracked points, which this file only draws. Forms come from command
// schemas.
import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "@/api/client";
import type { Schema } from "@/api/types";
import { replayRun } from "@/commands/registry";
import { SchemaForm } from "@/components/SchemaForm";
import { Badge, Button, Section, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";

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
}
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
                      {v.view.verdict ? ` · ${v.view.verdict}` : ""}
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
                        <Button size="sm" variant="ghost" title="Process again (e.g. with new settings)" onClick={() => say(run("retry_video", { file: v.file }), () => `Queued ${v.file}`)}>Retry</Button>
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

/** The video frame with the tracked points drawn over it. */
function FrameView({ file, frame, points }: { file: string; frame: number; points: Points | null }) {
  const size = points?.image_size ?? null;
  const row = points && frame >= points.start && frame < points.end ? points.frames[frame - points.start] : null;
  const idx = useMemo(() => new Map((points?.names ?? []).map((n, i) => [n, i])), [points]);
  return (
    <div className="relative w-full bg-black" data-testid="review-frame">
      <img className="block w-full" src={`/api/footage/${encodeURIComponent(file)}/frame/${frame}?width=640`} alt={`${file} frame ${frame}`} />
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
  const [report, setReport] = useState<{ verdict: string; note: string } | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
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
    setForm({});
    const pad = Math.round(fps * 2); // a little either side, for trimming outward
    void api.get<Points>(`/api/footage/${encodeURIComponent(video.file)}/points?start=${Math.max(0, candStart - pad)}&end=${candEnd + pad}`)
      .then(setPoints).catch(() => setPoints(null));
  }, [cid, candStart, candEnd, fps, video.file, video.sha256]);
  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => setFrame((f) => (f + 1 >= r1 ? r0 : f + 1)), Math.max(40, 1000 / fps));
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [playing, r0, r1, fps]);

  const formSchema: Schema | null = acceptCmd ? { ...acceptCmd.schema, fields: acceptCmd.schema.fields.filter((f) => !HIDDEN.has(f.name)) } : null;
  const params = (extra: Record<string, unknown> = {}) => ({
    file: video.file, candidate: cand?.id, start: range[0], end: range[1], ...extra,
  });

  return (
    <Section title={`Review: ${video.file}`}>
      <div className="mb-1 text-[11px] text-dim" data-testid="review-summary">
        {video.view.verdict && <span><Badge tone={video.view.verdict.startsWith("side view OK") ? "ok" : video.view.verdict.startsWith("too") ? "err" : "neutral"} title={video.view.note}>{video.view.verdict}</Badge> </span>}
        near side {video.near_side.near_side ?? "?"} ({video.near_side.method ?? "map"}{video.near_side.agree === false ? ", confidence disagrees" : ""}) · map {video.map.name} · {video.tracker.model ?? video.tracker.tracker} {video.tracker.version}
        {video.tracker.device ? ` on ${video.tracker.device}` : ""}
      </div>
      <div className="mb-1 flex flex-wrap gap-1">
        {video.candidates.map((c) => (
          <button key={c.id} data-testid={`candidate-${c.id}`} onClick={() => setCid(c.id)}
            className={`rounded border px-1 text-[11px] ${c.id === cid ? "border-accent" : "border-line"} ${c.status === "rejected" ? "opacity-50 line-through" : ""}`}
            title={`${c.kind}${c.period_s ? `, period ${c.period_s} s` : ""}, frames ${c.start}-${c.end}${c.view_ok === false ? ", turned from the camera" : ""}`}>
            {c.id} {c.kind} {fmt(c.seconds, 1)} s {c.status === "accepted" ? "✓" : ""}{c.view_ok === false ? " ⚠" : ""}
          </button>
        ))}
      </div>
      {cand && (
        <>
          <FrameView file={video.file} frame={frame} points={points} />
          <div className="mt-1 flex items-center gap-1 text-[11px]">
            <Button size="sm" onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Play"}</Button>
            <input type="range" className="flex-1" min={points?.start ?? range[0]} max={Math.max((points?.end ?? range[1]) - 1, range[0])} value={frame}
              onChange={(e) => setFrame(Number(e.target.value))} aria-label="Frame" />
            <span className="w-24 text-right text-dim">frame {frame} · {fmt(frame / fps, 2)} s</span>
          </div>
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
          </div>
          <div className="mt-1 flex gap-1">
            <Button size="sm" data-testid="preview-candidate" title="Pose the robot with this cut (no physics) and replay it in the viewport"
              onClick={() => say(run<{ run_id: string; report: { verdict: string; note: string } }>("preview_candidate", params({ far_side: form.far_side ?? "" }))
                .then((r) => { setReport(r.report); return replayRun(r.run_id).then(() => r); }), (r) => `Previewing on the robot: ${r.report.note}`)}>
              Preview on robot
            </Button>
            {report && <span className="text-[11px] text-dim" data-testid="candidate-report">{report.verdict}: {report.note}</span>}
          </div>
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
