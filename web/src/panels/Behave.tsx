// Behave: behaviors from reference footage (ADR-073). Import keypoint tracks
// as clips, see what the body can play of each, preview them on the body,
// add them to the stochastic behaviors and simulate. Every number comes from
// the server; forms come from command and controller schemas.
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "@/api/client";
import { execute, replayRun } from "@/commands/registry";
import { SchemaForm } from "@/components/SchemaForm";
import { Badge, Button, Empty, PanelScroll, Section, fmt } from "@/components/ui";
import { onLabEvent, useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";
import { RoleForm } from "./Design";
import { CompositionStudy } from "./Composition";
import { CandidateReview, FootageInbox, type InboxData } from "./Footage";
import { PhysicsActions } from "./Physics";

interface JointRow {
  joint: string;
  in_clip: boolean;
  out_of_range_fraction?: number;
  peak_speed_deg_s?: number;
  speed_limit_deg_s: number;
  speed_ratio?: number;
}
interface ClipRow {
  id: string;
  name: string;
  duration_s: number;
  frames: number;
  source: string;
  footage?: string | null;
  error?: string;
  report?: { verdict: string; note: string; playable_speed: number; joints: JointRow[] };
  retarget?: { omitted?: Record<string, string>; map?: string } | null;
  affect?: { valence: number | null; arousal: number | null; words: string[]; note: string } | null;
}
interface BehaveData {
  clips: ClipRow[];
  maps: { name: string; description?: string; error?: string }[];
  footage: string[];
  footage_dir: string;
  controller: { type: string; params: Record<string, unknown> };
  inbox: InboxData;
  tag_words: string[];
  filtered: boolean;
}

const VERDICT: Record<string, ["ok" | "warn" | "err", string]> = {
  plays: ["ok", "plays"],
  clamped: ["warn", "clamped"],
  too_fast: ["warn", "too fast"],
  clamped_and_too_fast: ["err", "clamped, too fast"],
};

export function BehavePanel() {
  const run = useLab((s) => s.run);
  const revision = useLab((s) => s.state?.revision);
  const runs = useLab((s) => s.runs);
  const commands = useLab((s) => s.commands);
  const log = usePlayback((s) => s.controllerLog);
  const [data, setData] = useState<BehaveData | null>(null);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [video, setVideo] = useState<string | null>(null);
  const [filter, setFilter] = useState<Record<string, unknown>>({});
  const [tagging, setTagging] = useState<string | null>(null);
  const [tagForm, setTagForm] = useState<Record<string, unknown>>({});
  const plugins = useLab((s) => s.plugins);
  const filterSchema = plugins.analysis?.find((a) => a.key === "behave")?.schema;
  const tagCmd = commands.find((c) => c.key === "tag_clip");
  const importCmd = commands.find((c) => c.key === "import_footage");
  const filterKey = JSON.stringify(filter);
  const refresh = useCallback(
    () => void api.post<BehaveData>("/api/analysis/behave", JSON.parse(filterKey)).then(setData).catch(() => setData(null)),
    [filterKey],
  );
  useEffect(refresh, [refresh, revision, runs.length]);
  useEffect(() => onLabEvent((e) => {
    if (e.type === "footage.changed" || e.type === "motions.changed") refresh();
  }), [refresh]);
  const values = useMemo(() => {
    const d: Record<string, unknown> = {};
    for (const f of importCmd?.schema.fields ?? []) d[f.name] = f.default;
    if (!form.file && data?.footage.length) d.file = data.footage[0];
    return { ...d, ...form };
  }, [importCmd, form, data]);

  const say = (p: Promise<unknown>, ok: (r: any) => string) =>
    p.then((r) => { setMsg({ ok: true, text: ok(r) }); refresh(); })
      .catch((e: unknown) => setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) }));

  const usingBehaviors = data?.controller.type === "controller:behaviors";
  const reviewing = data?.inbox.videos.find((v) => v.file === video && v.candidates.length > 0) ?? null;
  const sayInbox = (p: Promise<unknown>, ok: (r: any) => string) => say(p, ok);
  return (
    <PanelScroll data-testid="behave-panel">
      <div className="border-b border-line bg-bg p-2 text-[11px] text-dim">
        Behaviors from reference footage: drop a video into the inbox below (or import a CSV tracked elsewhere), review
        the stretches the lab cuts from it, accept them as clips with your own affect tags, check what this body can play
        of each, then add them to the stochastic behaviors and simulate.
      </div>
      {msg && <div className={`border-b border-line px-2 py-1 text-[11px] ${msg.ok ? "text-ok" : "text-err"}`} data-testid="behave-message">{msg.text}</div>}

      {data && <FootageInbox inbox={data.inbox} say={sayInbox} selected={video} onSelect={setVideo} />}
      {reviewing && <CandidateReview key={reviewing.file + reviewing.sha256} video={reviewing} say={sayInbox} />}

      <Section title="Import footage keypoints (CSV)">
        {data && data.footage.length === 0 && <div className="mb-1 text-[11px] text-warn">No CSV in the footage folder yet.</div>}
        {data && data.footage.length > 0 && <div className="mb-1 text-[11px] text-dim">Files: {data.footage.join(", ")}</div>}
        {importCmd && <SchemaForm schema={importCmd.schema} values={values} onChange={(patch) => setForm((f) => ({ ...f, ...patch }))} />}
        <div className="mt-1 text-[10px] text-dim">Maps: {data?.maps.map((m) => m.name).join(", ") || "-"}</div>
        <Button size="sm" variant="primary" data-testid="import-footage" disabled={!values.file}
          onClick={() => say(run("import_footage", values), (r) => `Imported clip ${r.clip}: ${r.body.note}`)}>
          Import
        </Button>
      </Section>

      <Section title="Clips">
        {filterSchema && (
          <details className="mb-1 text-[11px]" data-testid="clip-filter">
            <summary className="cursor-pointer text-dim">Filter by your affect tags{data?.filtered ? " (on)" : ""}{data?.tag_words.length ? ` · words used: ${data.tag_words.join(", ")}` : ""}</summary>
            <SchemaForm schema={filterSchema} values={{ ...Object.fromEntries(filterSchema.fields.map((f) => [f.name, f.default])), ...filter }}
              onChange={(p, final) => final && setFilter((f) => ({ ...f, ...p }))} />
            {data?.filtered && <Button size="sm" variant="ghost" onClick={() => setFilter({})}>Clear filter</Button>}
          </details>
        )}
        {!data || data.clips.length === 0 ? (
          <div className="text-dim">{data?.filtered ? "No clip has these tags." : "No clips yet. Accept a candidate from a video above, import a CSV, or send a clip from Blender."}</div>
        ) : (
          data.clips.map((c) => {
            const [tone, label] = VERDICT[c.report?.verdict ?? ""] ?? ["neutral", c.error ? "error" : "?"];
            return (
              <div key={c.id} className="mb-1 rounded border border-line p-1" data-clip={c.id}>
                <div className="flex items-center gap-1">
                  <button className="font-semibold hover:underline" onClick={() => setOpen(open === c.id ? null : c.id)}>{c.name}</button>
                  <span className="text-[10px] text-dim">{fmt(c.duration_s, 1)} s · {c.source}{c.footage ? ` · ${c.footage}` : ""}</span>
                  <Badge tone={tone as any} title={c.report?.note ?? c.error}>{label}</Badge>
                  <span className="ml-auto flex gap-1">
                    <Button size="sm" variant="ghost" title="Pose the body frame by frame (no physics) and replay it"
                      onClick={() => say(run<{ run_id: string }>("preview_clip", { clip: c.id }).then((r) => replayRun(r.run_id).then(() => r)), () => `Previewing ${c.name}`)}>
                      Preview
                    </Button>
                    <Button size="sm" variant="ghost" data-testid={`add-behavior-${c.id}`} title="Add to the stochastic behaviors, at a speed the servos can follow"
                      onClick={() => say(run("add_behavior", { clip: c.id }), (r) => `Added ${c.name} at ${r.entry.speed.join("-")}x${r.switched ? " (switched to the behaviors controller)" : ""}`)}>
                      Add to behaviors
                    </Button>
                  </span>
                </div>
                {c.report && <div className="text-[10px] text-dim">{c.report.note}</div>}
                <PhysicsActions source={{ clip: c.id }} />
                <div className="flex flex-wrap items-center gap-1 text-[10px]" data-testid={`clip-tags-${c.id}`}>
                  {c.affect ? (
                    <>
                      {c.affect.valence !== null && <Badge tone="info">valence {fmt(c.affect.valence, 1)}</Badge>}
                      {c.affect.arousal !== null && <Badge tone="info">arousal {fmt(c.affect.arousal, 1)}</Badge>}
                      {c.affect.words.map((w) => <Badge key={w}>{w}</Badge>)}
                    </>
                  ) : <span className="text-dim">no tags</span>}
                  <Button size="sm" variant="ghost" onClick={() => { setTagging(tagging === c.id ? null : c.id); setTagForm({ name: c.name, valence: c.affect?.valence ?? null, arousal: c.affect?.arousal ?? null, words: c.affect?.words.join(", ") ?? "", note: c.affect?.note ?? "" }); }}>
                    Name and tags
                  </Button>
                </div>
                {tagging === c.id && tagCmd && (
                  <div className="mt-1 rounded border border-line p-1">
                    <SchemaForm schema={{ ...tagCmd.schema, fields: tagCmd.schema.fields.filter((f) => f.name !== "clip") }} values={tagForm} onChange={(p) => setTagForm((f) => ({ ...f, ...p }))} />
                    <Button size="sm" variant="primary" onClick={() => say(run("tag_clip", { clip: c.id, ...tagForm }), () => { setTagging(null); return `Saved ${c.id}`; })}>Save</Button>
                  </div>
                )}
                {open === c.id && c.report && (
                  <table className="mt-1 w-full text-[10px]">
                    <thead className="text-left uppercase text-dim">
                      <tr><th>Joint</th><th className="text-right">out of range</th><th className="text-right">peak deg/s</th><th className="text-right">servo deg/s</th></tr>
                    </thead>
                    <tbody>
                      {c.report.joints.map((j) => (
                        <tr key={j.joint} className="border-t border-line/40">
                          <td className="font-mono">{j.joint.replace("joint.", "")}</td>
                          <td className="text-right">{j.in_clip ? `${fmt((j.out_of_range_fraction ?? 0) * 100, 0)} %` : "held"}</td>
                          <td className={`text-right ${(j.speed_ratio ?? 0) > 1 ? "text-warn" : ""}`}>{j.in_clip ? fmt(j.peak_speed_deg_s, 0) : ""}</td>
                          <td className="text-right">{fmt(j.speed_limit_deg_s, 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })
        )}
      </Section>

      <Section
        title="Stochastic behaviors"
        right={
          usingBehaviors ? (
            <Button size="sm" variant="primary" onClick={() => void execute("RunSim")}>Simulate (F5)</Button>
          ) : (
            <Button size="sm" data-testid="use-behaviors" onClick={() => say(run("set_controller", { key: "behaviors" }), () => "The simulation now plays the stochastic behaviors")}>
              Use behaviors
            </Button>
          )
        }
      >
        {usingBehaviors ? (
          <RoleForm role="controller" />
        ) : (
          <Empty title="The simulation plays one fixed motion">
            Use behaviors to have it choose, with a seed, among idle sway, walking, trotting and your clips, each with random
            speed and amplitude.
          </Empty>
        )}
        {log?.episodes && log.episodes.length > 0 && (
          <div className="mt-2" data-testid="behavior-episodes">
            <div className="text-[10px] uppercase text-dim">In the run on the timeline</div>
            {log.episodes.map((e, i) => (
              <div key={i} className="flex justify-between text-[11px]">
                <span>{e.name} <span className="text-dim">({e.kind}{e.mirror ? ", mirrored" : ""}{e.composition?.label ? `, ${e.composition.label}` : ""})</span></span>
                <span className="text-dim">{fmt(e.t0, 1)}–{fmt(e.t1, 1)} s</span>
              </div>
            ))}
          </div>
        )}
      </Section>
      <CompositionStudy say={say} />
    </PanelScroll>
  );
}
