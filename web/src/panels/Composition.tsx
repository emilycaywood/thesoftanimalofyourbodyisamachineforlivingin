// The composition study (ADR-078): the same body plays several compositions
// of its behaviors; the server tabulates movement features (kinematics, not
// emotions), clip tracking and safety. This file renders the command's form
// and the stored table.
import { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { SchemaForm } from "@/components/SchemaForm";
import { Badge, Button, Section, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";

interface Stat { mean: number | null; sd: number | null; min: number | null; max: number | null }
interface Row {
  name: string;
  ok: number;
  runs: number;
  falls: number;
  errors: string[];
  features: Record<string, Stat>;
  tracking_rms_deg: Stat;
  safety_margin: Stat;
  rejected_runs: number;
  violations: Record<string, number>;
  clip_tracking_deg: Record<string, Stat>;
}
interface Study {
  run_id: string;
  rows: Row[];
  features: { key: string; label: string; unit: string }[];
  note: string;
  settings: { seeds: number[]; duration_s: number; randomize: boolean };
}

const pm = (s: Stat, d = 2) => (s.mean === null ? "–" : `${fmt(s.mean, d)}${s.sd ? ` ± ${fmt(s.sd, d)}` : ""}`);

export function CompositionStudy({ say }: { say: (p: Promise<unknown>, ok: (r: any) => string) => void }) {
  const run = useLab((s) => s.run);
  const runs = useLab((s) => s.runs);
  const commands = useLab((s) => s.commands);
  const cmd = commands.find((c) => c.key === "run_composition_study");
  const studies = useMemo(() => runs.filter((r) => r.kind === "composition" && r.status !== "running"), [runs]);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [chosen, setChosen] = useState<string | null>(null);
  const [study, setStudy] = useState<Study | null>(null);
  const current = chosen ?? studies[0]?.id ?? null;
  useEffect(() => {
    if (!current) return;
    void api.get<Study>(api.fileUrl(`runs/${current}/composition_study.json`)).then(setStudy).catch(() => setStudy(null));
  }, [current]);
  const values = useMemo(() => ({ ...Object.fromEntries((cmd?.schema.fields ?? []).map((f) => [f.name, f.default])), ...form }), [cmd, form]);

  return (
    <Section title="Composition study">
      <div className="mb-1 text-[11px] text-dim">
        The same body plays the behaviors in several compositions (each a set of the behaviors' parameters, over the ones
        above), with several seeds. Compare how they move and what they cost the hardware.
      </div>
      {cmd && <SchemaForm schema={cmd.schema} values={values} onChange={(p) => setForm((f) => ({ ...f, ...p }))} />}
      <Button size="sm" variant="primary" data-testid="run-composition-study"
        onClick={() => say(run("run_composition_study", values).then((r) => { setChosen(null); return r; }), (r) => `Composition study started (${r.run_id})`)}>
        Run study
      </Button>
      {studies.length > 0 && (
        <div className="mt-2 flex items-center gap-1 text-[11px]">
          <span className="text-dim">Study</span>
          <select value={current ?? ""} onChange={(e) => setChosen(e.target.value)}>
            {studies.map((s) => <option key={s.id} value={s.id}>{s.id}</option>)}
          </select>
        </div>
      )}
      {study && (
        <div className="mt-1 overflow-x-auto" data-testid="composition-table">
          <div className="mb-1 text-[10px] text-dim">
            {study.note} {study.settings.seeds.length} seeds × {fmt(study.settings.duration_s, 0)} s{study.settings.randomize ? ", friction and mass randomised" : ""}; mean ± spread over seeds.
          </div>
          <table className="w-full text-[10px]">
            <thead className="text-left text-dim">
              <tr>
                <th className="pr-2">Measure</th>
                {study.rows.map((r) => <th key={r.name} className="pr-2 text-right">{r.name}</th>)}
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-line/40">
                <td>Falls</td>
                {study.rows.map((r) => <td key={r.name} className={`text-right ${r.falls ? "text-err" : ""}`}>{r.falls} / {r.ok}{r.errors.length ? ` (${r.errors.length} failed)` : ""}</td>)}
              </tr>
              <tr>
                <td title="Commanded vs achieved joint angle, while clips play">Clip tracking (deg RMS)</td>
                {study.rows.map((r) => <td key={r.name} className="text-right">{pm(r.tracking_rms_deg, 1)}</td>)}
              </tr>
              <tr>
                <td title="Smallest headroom over the safety constraints: 1 unloaded, 0 at a limit, below 0 over it">Safety margin</td>
                {study.rows.map((r) => <td key={r.name} className={`text-right ${(r.safety_margin.min ?? 1) < 0 ? "text-warn" : ""}`}>{pm(r.safety_margin)}</td>)}
              </tr>
              <tr>
                <td>Constraints violated (runs)</td>
                {study.rows.map((r) => (
                  <td key={r.name} className="text-right">
                    {Object.keys(r.violations).length === 0 ? "none" : Object.entries(r.violations).map(([k, n]) => <Badge key={k} tone={r.rejected_runs ? "err" : "warn"}>{k.replace("_", " ")} {n}</Badge>)}
                  </td>
                ))}
              </tr>
              {study.features.map((f) => (
                <tr key={f.key} className="border-t border-line/20">
                  <td>{f.label}{f.unit ? ` (${f.unit})` : ""}</td>
                  {study.rows.map((r) => <td key={r.name} className="text-right">{pm(r.features[f.key] ?? { mean: null, sd: null, min: null, max: null })}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
