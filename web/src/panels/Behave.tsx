// Behave: behaviors from reference footage (ADR-073). Import keypoint tracks
// as clips, see what the body can play of each, preview them on the body,
// add them to the stochastic behaviors and simulate. Every number comes from
// the server; forms come from command and controller schemas.
import { useEffect, useMemo, useState } from "react";
import { ApiError, api } from "@/api/client";
import { execute, replayRun } from "@/commands/registry";
import { SchemaForm } from "@/components/SchemaForm";
import { Badge, Button, Empty, PanelScroll, Section, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";
import { RoleForm } from "./Design";

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
}
interface BehaveData {
  clips: ClipRow[];
  maps: { name: string; description?: string; error?: string }[];
  footage: string[];
  footage_dir: string;
  controller: { type: string; params: Record<string, unknown> };
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
  const importCmd = commands.find((c) => c.key === "import_footage");
  const refresh = () => void api.post<BehaveData>("/api/analysis/behave", {}).then(setData).catch(() => setData(null));
  useEffect(refresh, [revision, runs.length]);
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
  return (
    <PanelScroll data-testid="behave-panel">
      <div className="border-b border-line bg-bg p-2 text-[11px] text-dim">
        Behaviors from reference footage: track the video with a pose tracker (DeepLabCut, SLEAP, or by hand), copy its CSV into{" "}
        <code className="selectable">{data?.footage_dir ?? "<project>\\footage"}</code>, import it here as a clip, check what this body can play
        of it, then add it to the stochastic behaviors and simulate.
      </div>
      {msg && <div className={`border-b border-line px-2 py-1 text-[11px] ${msg.ok ? "text-ok" : "text-err"}`} data-testid="behave-message">{msg.text}</div>}

      <Section title="Import footage keypoints">
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
        {!data || data.clips.length === 0 ? (
          <div className="text-dim">No clips yet. Import footage above (or send a clip from Blender).</div>
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
                <span>{e.name} <span className="text-dim">({e.kind}{e.mirror ? ", mirrored" : ""})</span></span>
                <span className="text-dim">{fmt(e.t0, 1)}–{fmt(e.t1, 1)} s</span>
              </div>
            ))}
          </div>
        )}
      </Section>
    </PanelScroll>
  );
}
