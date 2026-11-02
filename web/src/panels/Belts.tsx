// Belts and springs (feral calf, ADR-063..069). Belt drives are chosen from the
// project's catalog with three dropdowns; everything else is read-only and
// computed on the server (centre distance, servo position, checks, tension).
// There is deliberately no control for the centre distance anywhere.
import { useEffect, useState } from "react";
import { ApiError, api } from "@/api/client";
import { Badge, Button, Empty, PanelScroll, Row, Section, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";
import { RoleForm } from "./Design";

type Status = "pass" | "fail" | "unknown";
interface Check { id: string; label: string; status: Status; detail: string }
interface Choice { system: string; pulleys: string; length: string }
interface DriveReport {
  drive: string;
  choice: Choice;
  system_label: string;
  length_mm: number;
  belt_teeth: number;
  length_source: string;
  purchase_confirmed: boolean;
  driver_teeth: number;
  driven_teeth: number;
  ratio: number;
  d1_mm: number;
  d2_mm: number;
  c_mm: number | null;
  servo_axis_from_driven_mm: number | null;
  servo_axis_from_far_mm: number | null;
  wrap_deg: number | null;
  teeth_in_mesh: number | null;
  tension_travel_mm: number;
  c_with_travel_mm: [number, number] | null;
  allowable_working_tension_n: number | null;
  breaking_strength_n: number | null;
  checks: Check[];
  ok: boolean;
  default_chosen: boolean;
  layout: { segment: string; segment_length_mm: number };
}
interface LengthOption {
  id: string; length_mm: number; teeth: number; source: string; source_label: string; listings: string[];
  purchase_confirmed: boolean; selectable: boolean; reason: string; c_mm: number | null; ok: boolean; failed: string[]; unknown: string[];
}
interface Options {
  systems: { id: string; label: string; usable: boolean; why_not: string; allowable_working_tension_n: number | null; breaking_strength_n: number | null; notes: string }[];
  pairs: { id: string; label: string; usable: boolean; masses_missing: string[] }[];
  lengths: LengthOption[];
}
interface SpringRow {
  spring: string; joint: string; force_n: number; arm_mm: number; torque_nm: number; slack: boolean; side: string; side_note: string;
  gravity_nm: number; servo_reduction_nm: number; belt_reduction_n?: number;
}
interface PanelData {
  error?: string;
  drives: Record<string, { report: DriveReport; stored: boolean; options: Options; joints: string[] }>;
  belted: string[];
  catalog: { origin: string; digest: string; note: string };
  springs: SpringRow[];
  provisional: { name: string; value: unknown; unit: string | null; where: string }[];
  missing_masses: { item: string; label: string; qty: number; where: string[]; enter_in: string }[];
  servo: { name: string; stall_nm: number; rated_nm: number | null; encoder_steps: number | null; servo_resolution_deg: number | null; output_axis_offset_mm: number | null; unknown: string[] };
  checks: { sustained_fraction: number; breaking_fraction: number; rated_fraction: number; belt_efficiency: number };
  standing_height_mm: number;
  front_angle_deg: number;
  total_mass_g: number;
  com_mm: [number, number, number];
  warnings: string[];
}
interface JointSummary {
  joint: string; drive: string; servo_torque_peak_nm: number; servo_torque_mean_abs_nm: number; pct_rated_peak: number | null; pct_stall_peak: number;
  above_rated_fraction_of_cycle: number | null; sustained_above_rated: boolean | null; at_stall: boolean; spring_torque_mean_nm: number;
  belt_tension_peak_n?: number; belt_tension_mean_n?: number; allowable_n?: number | null; breaking_n?: number | null;
  above_allowable_fraction_of_cycle?: number | null; sustained_above_allowable?: boolean | "unknown"; peak_over_breaking?: number | null; breaking_flag?: boolean | "unknown";
}
interface Scenario {
  run_id: string; label: string; summary: JointSummary[]; flags: string[]; outcome: { fell: boolean; distance_mm: number };
  spring_relief: { joint: string; servo_mean_reduction_nm: number; servo_peak_reduction_nm: number; belt_mean_reduction_n?: number; belt_peak_reduction_n?: number }[];
}
interface LoadsView {
  scenarios: Record<string, Scenario>;
  comparison: null | { run_id: string; rows: { system: string; pulleys: string; status: string; reason: string; allowable_n: number | null; breaking_n: number | null; drives: Record<string, { length?: string; c_mm?: number | null; peak_n?: number; sustained_above_allowable?: boolean | "unknown"; peak_over_breaking?: number | null }> }[] };
}

const tone = (s: Status | boolean | "unknown" | null | undefined) =>
  s === "pass" || s === false ? "ok" : s === "fail" || s === true ? "err" : "warn";

function StatusBadge({ status }: { status: Status }) {
  return <Badge tone={tone(status)}>{status}</Badge>;
}

function lengthLabel(o: LengthOption): string {
  const parts = [`${o.length_mm} mm (${o.teeth} T)`, `src ${o.source}`];
  if (o.c_mm !== null) parts.push(`C ${o.c_mm.toFixed(1)}`);
  if (!o.selectable) parts.push("width unconfirmed");
  else if (o.failed.length) parts.push(`fails: ${o.failed.join("; ")}`);
  else if (o.unknown.length) parts.push("check unknown");
  if (!o.purchase_confirmed) parts.push("purchase unconfirmed");
  return parts.join(" · ");
}

function DriveCard({ drive, d, onChoose }: { drive: string; d: PanelData["drives"][string]; onChoose: (field: keyof Choice, value: string) => void }) {
  const r = d.report;
  const sel = d.options.systems.find((s) => s.id === r.choice.system);
  return (
    <div className="mb-3 rounded border border-line p-2" data-testid={`belt-${drive}`}>
      <div className="mb-1 flex items-center gap-2">
        <span className="font-semibold capitalize">{drive}</span>
        <span className="text-dim">{r.ratio}:1, servo on the {r.layout.segment}</span>
        {r.ok ? <Badge tone="ok">valid</Badge> : <Badge tone="err">rejected</Badge>}
        {r.default_chosen && <Badge tone="info" title="No choice stored for this drive: the default rule picked it">default</Badge>}
      </div>
      <Row label="Belt system">
        <select className="min-w-0 flex-1" value={r.choice.system} data-testid={`belt-${drive}-system`} onChange={(e) => onChoose("system", e.target.value)}>
          {d.options.systems.map((s) => (
            <option key={s.id} value={s.id} disabled={!s.usable}>{s.label}{s.usable ? "" : ` · ${s.why_not}`}</option>
          ))}
        </select>
      </Row>
      <Row label="Pulley pair">
        <select className="min-w-0 flex-1" value={r.choice.pulleys} data-testid={`belt-${drive}-pulleys`} onChange={(e) => onChoose("pulleys", e.target.value)}>
          {d.options.pairs.map((p) => (
            <option key={p.id} value={p.id} disabled={!p.usable}>{p.label}</option>
          ))}
        </select>
      </Row>
      <Row label="Belt length">
        <select className="min-w-0 flex-1" value={r.choice.length} data-testid={`belt-${drive}-length`} onChange={(e) => onChoose("length", e.target.value)}>
          {d.options.lengths.map((o) => (
            <option key={o.id} value={o.id} disabled={!o.selectable} title={`${o.source_label}${o.listings.length ? ": " + o.listings.join(", ") : ""}${o.reason ? "\n" + o.reason : ""}`}>
              {lengthLabel(o)}
            </option>
          ))}
        </select>
      </Row>
      <div className="mt-1 grid grid-cols-2 gap-x-3 text-[11px]" data-testid={`belt-${drive}-derived`}>
        <span className="text-dim" title="Derived from the belt length and the two pitch diameters; it cannot be set">Centre distance C</span>
        <span className="selectable font-semibold">{fmt(r.c_mm, 1)} mm</span>
        <span className="text-dim">Tension slot (build tolerance)</span>
        <span>± {fmt(r.tension_travel_mm, 1)} mm → {r.c_with_travel_mm ? `${fmt(r.c_with_travel_mm[0], 1)}–${fmt(r.c_with_travel_mm[1], 1)}` : "-"}</span>
        <span className="text-dim">Servo axis from the {drive} axis</span>
        <span>{fmt(r.servo_axis_from_driven_mm, 1)} mm</span>
        <span className="text-dim">… from the {r.layout.segment}'s other joint</span>
        <span>{fmt(r.servo_axis_from_far_mm, 1)} mm</span>
        <span className="text-dim">Pitch diameters D1 / D2</span>
        <span>{fmt(r.d1_mm, 3)} / {fmt(r.d2_mm, 3)} mm</span>
        <span className="text-dim">Wrap, teeth in mesh (driver)</span>
        <span>{fmt(r.wrap_deg, 1)}°, {fmt(r.teeth_in_mesh, 1)}</span>
        <span className="text-dim">Allowable working tension</span>
        <span>{r.allowable_working_tension_n === null ? <Badge tone="warn">unknown</Badge> : `${r.allowable_working_tension_n} N`}</span>
        <span className="text-dim">Breaking strength</span>
        <span>{r.breaking_strength_n === null ? <Badge tone="warn">unknown</Badge> : `${r.breaking_strength_n} N`}</span>
        <span className="text-dim">Belt</span>
        <span>{r.length_mm} mm, {r.belt_teeth} teeth, source {r.length_source} {!r.purchase_confirmed && <Badge tone="warn" title="Set purchase_confirmed in catalog/belt_lengths.json once you know you can order it">purchase unconfirmed</Badge>}</span>
      </div>
      {sel?.notes && <div className="mt-1 text-[10px] text-warn">{sel.notes}</div>}
      <ul className="mt-1 flex flex-col gap-0.5">
        {r.checks.map((c) => (
          <li key={c.id} className="flex items-start gap-1 text-[11px]" data-check={c.id} data-status={c.status}>
            <StatusBadge status={c.status} />
            <span><span className="text-fg">{c.label}</span> <span className="text-dim">{c.detail}</span></span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BeltsPanel() {
  const revision = useLab((s) => s.state?.revision);
  const runs = useLab((s) => s.runs);
  const run = useLab((s) => s.run);
  const busy = useLab((s) => s.jobs.some((j) => (j.kind === "loads" || j.kind === "belts") && (j.status === "running" || j.status === "queued")));
  const [data, setData] = useState<PanelData | null>(null);
  const [loads, setLoads] = useState<LoadsView | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    void api.post<PanelData>("/api/analysis/belt_drives", {}).then(setData).catch(() => setData(null));
  }, [revision]);
  useEffect(() => {
    void api.post<LoadsView>("/api/analysis/loads", {}).then(setLoads).catch(() => setLoads(null));
  }, [runs.length]);

  if (!data) return <Empty title="Belts and springs">Loading…</Empty>;
  if (data.error)
    return (
      <Empty title="Belts and springs">
        This panel chooses the belt drives and tunes the springs of the final feral calf. {data.error} Create such a project with{" "}
        <code>calflab new-project projects\robot-calf-final --template feral_calf</code>.
      </Empty>
    );

  const choose = (drive: string, field: keyof Choice, value: string) => {
    setMsg(null);
    run<{ c_mm: number; note: string }>("set_belt_drive", { drive, [field]: value })
      .then((r) => setMsg({ ok: true, text: `${drive}: C = ${fmt(r.c_mm, 1)} mm. ${r.note ?? ""}` }))
      .catch((e: unknown) => setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) }));
  };

  return (
    <PanelScroll data-testid="belts-panel">
      <div className="border-b border-line bg-bg px-2 py-1.5 text-[11px]">
        <div className="flex justify-between">
          <span>Mass <b data-testid="feral-mass">{fmt(data.total_mass_g, 0)} g</b> <span className="text-dim">(entered values only)</span></span>
          <span className="text-dim">CoM {data.com_mm.map((v) => fmt(v, 0)).join(", ")} mm</span>
        </div>
        <div className="text-dim">
          Standing height {fmt(data.standing_height_mm, 1)} mm · front legs at {fmt(data.front_angle_deg, 1)}° (back level) · {data.servo.name}: stall{" "}
          {data.servo.stall_nm} N·m, rated {data.servo.rated_nm ?? "?"} N·m
        </div>
        {data.missing_masses.length > 0 && (
          <div className="text-warn" title={data.missing_masses.map((m) => `${m.label} x${m.qty}: enter in ${m.enter_in}`).join("\n")}>
            {data.missing_masses.length} part masses not entered (counted as 0 g)
          </div>
        )}
      </div>
      {msg && <div className={`border-b border-line px-2 py-1 text-[11px] ${msg.ok ? "text-ok" : "text-err"}`} data-testid="belt-message">{msg.text}</div>}

      <Section title="Belt drives" right={<span className="text-[10px] normal-case text-dim">catalog: {data.catalog.origin.split(/[\\/]/).slice(-2).join("/")}</span>}>
        <div className="mb-2 text-[11px] text-dim">
          A drive is three catalog choices; C and the servo position follow from them and cannot be set. A choice that fails a check is
          rejected with the reason. Greyed lengths are not confirmed in this belt's width.
        </div>
        {data.catalog.note && <div className="mb-2 text-[11px] text-warn">{data.catalog.note}</div>}
        {Object.entries(data.drives).map(([drive, d]) => (
          <DriveCard key={drive} drive={drive} d={d} onChoose={(f, v) => choose(drive, f, v)} />
        ))}
        {data.servo.output_axis_offset_mm === null && (
          <div className="text-[11px] text-warn">
            Servo output-axis position on its case is not entered (config/feral_calf.yaml servo.output_axis_offset_mm): checks that depend on it
            say "unknown".
          </div>
        )}
      </Section>

      <Section title="Springs (tension only)">
        <RoleForm role="genome" filterGroup="Springs" />
        <table className="mt-2 w-full text-[11px]" data-testid="spring-table">
          <thead className="text-left text-[10px] uppercase text-dim">
            <tr><th>Standing</th><th className="text-right">F N</th><th className="text-right">arm</th><th className="text-right">τ N·m</th><th className="pl-1">side</th><th className="text-right" title="Servo torque the spring takes off at standing">servo −</th></tr>
          </thead>
          <tbody>
            {data.springs.map((s) => (
              <tr key={s.spring} className="border-t border-line/40" title={s.side_note}>
                <td className="font-mono">{s.spring.replace("spring.", "")}</td>
                <td className="text-right">{fmt(s.force_n, 1)}</td>
                <td className="text-right">{fmt(s.arm_mm, 1)}</td>
                <td className="text-right">{fmt(s.torque_nm, 3)}</td>
                <td className="pl-1">
                  <Badge tone={s.side === "resists" ? "ok" : s.side === "helps_collapse" ? "err" : "warn"}>{s.side.replace("_", " ")}</Badge>
                </td>
                <td className="text-right">{fmt(s.servo_reduction_nm, 3)}{s.belt_reduction_n !== undefined ? ` (${fmt(s.belt_reduction_n, 1)} N)` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-1 text-[10px] text-dim">Arm = perpendicular distance from the joint axis to the spring line. "servo −": what the spring takes off the servo (and belt) at standing; negative = adds.</div>
      </Section>

      <Section
        title="Loads"
        right={
          <span className="flex gap-1">
            <Button size="sm" variant="primary" disabled={busy} data-testid="run-loads" onClick={() => void run("run_loads").catch(() => undefined)}>
              {busy ? "Running…" : "Run load analysis"}
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} data-testid="run-belt-comparison" onClick={() => void run("run_belt_comparison").catch(() => undefined)}>
              Compare belts
            </Button>
          </span>
        }
      >
        <div className="mb-1 text-[11px] text-dim">
          Flags: servo above {Math.round(data.checks.rated_fraction * 100)} % of rated for more than {Math.round(data.checks.sustained_fraction * 100)} % of a gait
          cycle; any moment at stall; belt above its allowable tension for more than {Math.round(data.checks.sustained_fraction * 100)} % of a cycle; belt peak
          above {Math.round(data.checks.breaking_fraction * 100)} % of breaking. CSVs are in each run's folder.
        </div>
        {!loads || Object.keys(loads.scenarios).length === 0 ? (
          <div className="text-dim">No load run yet. Press Run load analysis: standing, a slow walk, and lying down and rising.</div>
        ) : (
          Object.entries(loads.scenarios).map(([name, sc]) => (
            <div key={name} className="mb-2" data-testid={`loads-${name}`}>
              <div className="font-semibold">{sc.label} <span className="font-normal text-dim">{sc.run_id}{sc.outcome.fell ? " · FELL" : ""}</span></div>
              <table className="w-full text-[11px]">
                <thead className="text-left text-[10px] uppercase text-dim">
                  <tr><th>Joint</th><th className="text-right">servo pk</th><th className="text-right">% rated</th><th className="text-right">% stall</th><th className="text-right">belt pk N</th><th className="pl-1">flags</th></tr>
                </thead>
                <tbody>
                  {sc.summary.map((r) => (
                    <tr key={r.joint} className="border-t border-line/40">
                      <td className="font-mono">{r.joint.replace("joint.", "")}</td>
                      <td className="text-right">{fmt(r.servo_torque_peak_nm)}</td>
                      <td className="text-right">{fmt(r.pct_rated_peak, 0)}</td>
                      <td className="text-right">{fmt(r.pct_stall_peak, 0)}</td>
                      <td className="text-right">{r.belt_tension_peak_n !== undefined ? `${fmt(r.belt_tension_peak_n, 0)} / ${r.allowable_n ?? "?"}` : ""}</td>
                      <td className="pl-1">
                        {r.sustained_above_rated && <Badge tone="err">rated</Badge>} {r.at_stall && <Badge tone="err">stall</Badge>}{" "}
                        {r.sustained_above_allowable === true && <Badge tone="err">belt</Badge>}
                        {r.sustained_above_allowable === "unknown" && <Badge tone="warn">belt ?</Badge>} {r.breaking_flag === true && <Badge tone="err">break</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {sc.flags.map((f) => <div key={f} className="text-[11px] text-err">{f}</div>)}
            </div>
          ))
        )}
        {loads?.comparison && (
          <div className="mt-2" data-testid="belt-comparison">
            <div className="font-semibold">Belt comparison (slow walk) <span className="font-normal text-dim">{loads.comparison.run_id}</span></div>
            <table className="w-full text-[11px]">
              <thead className="text-left text-[10px] uppercase text-dim">
                <tr><th>System</th><th>Pulleys</th><th>Drive</th><th className="text-right">C</th><th className="text-right">peak N</th><th className="pl-1">limits</th></tr>
              </thead>
              <tbody>
                {loads.comparison.rows.flatMap((row) => {
                  const drives = Object.entries(row.drives).filter(([, v]) => v.peak_n !== undefined);
                  if (!drives.length)
                    return [
                      <tr key={row.system + row.pulleys} className="border-t border-line/40 text-dim">
                        <td>{row.system}</td><td>{row.pulleys}</td><td colSpan={4}>{row.status}: {row.reason}</td>
                      </tr>,
                    ];
                  return drives.map(([k, v]) => (
                    <tr key={row.system + row.pulleys + k} className="border-t border-line/40">
                      <td>{row.system}</td><td>{row.pulleys}</td><td className="font-mono">{k}</td>
                      <td className="text-right">{fmt(v.c_mm, 1)}</td>
                      <td className="text-right">{fmt(v.peak_n, 0)} / {row.allowable_n ?? "?"}</td>
                      <td className="pl-1">
                        <Badge tone={tone(v.sustained_above_allowable)}>{v.sustained_above_allowable === "unknown" ? "allowable ?" : v.sustained_above_allowable ? "sustained" : "ok"}</Badge>{" "}
                        <span className="text-dim">{fmt((v.peak_over_breaking ?? 0) * 100, 0)} % brk</span>
                      </td>
                    </tr>
                  ));
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Belt checks and limits">
        <RoleForm role="design" />
      </Section>

      <Section title="Provisional and missing values">
        <details>
          <summary className="cursor-pointer text-[11px]">{data.provisional.length} PROVISIONAL values in use</summary>
          <ul className="mt-1 text-[11px]">
            {data.provisional.map((p) => (
              <li key={p.where}><span className="text-warn">{p.name}</span> = {JSON.stringify(p.value)}{p.unit ? ` ${p.unit}` : ""} <span className="text-dim">({p.where})</span></li>
            ))}
          </ul>
        </details>
        <details className="mt-1">
          <summary className="cursor-pointer text-[11px]">{data.missing_masses.length} masses not entered</summary>
          <ul className="mt-1 text-[11px]">
            {data.missing_masses.map((m) => (
              <li key={m.item}>{m.label} × {m.qty} <span className="text-dim">→ {m.enter_in}</span></li>
            ))}
          </ul>
        </details>
        {data.servo.unknown.length > 0 && <div className="mt-1 text-[11px] text-warn">Servo values not given: {data.servo.unknown.join(", ")} (shown as unknown).</div>}
        {data.warnings.length > 0 && (
          <ul className="mt-1 text-[11px] text-warn">{data.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        )}
      </Section>
    </PanelScroll>
  );
}
