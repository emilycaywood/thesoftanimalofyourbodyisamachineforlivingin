// Form (genome sliders), Simulate (controller + sim settings) and Mechanism
// (actuator assignment, torque margins). All forms come from server schemas.
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { GraphNode, NodeTypeInfo } from "@/api/types";
import { execute } from "@/commands/registry";
import { SchemaForm } from "@/components/SchemaForm";
import { Badge, Button, Empty, PanelScroll, Row, Section, Unverified, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";

/** The node playing a pipeline role (genome, controller, simulation...) and its type. */
export function useRoleNode(role: string): { node: GraphNode; type: NodeTypeInfo } | null {
  const graph = useLab((s) => s.graph);
  const nodeTypes = useLab((s) => s.nodeTypes);
  const id = graph?.graph.roles[role];
  const node = graph?.graph.nodes.find((n) => n.id === id);
  const type = node && nodeTypes.find((t) => t.type === node.type);
  return node && type ? { node, type } : null;
}

function RoleForm({ role, filterGroup }: { role: string; filterGroup?: string }) {
  const rn = useRoleNode(role);
  const run = useLab((s) => s.run);
  const endGesture = useLab((s) => s.endGesture);
  if (!rn) return <div className="text-err">The graph has no {role} node. Run ResetGraph.</div>;
  const isGenome = rn.node.type.startsWith("genome:");
  return (
    <SchemaForm
      schema={rn.type.schema}
      values={rn.node.params}
      filterGroup={filterGroup}
      onChange={(patch, final) => {
        const req = isGenome ? run("set_genes", { values: patch }) : run("set_node_params", { node: rn.node.id, params: patch });
        void req.catch(() => undefined).finally(() => final && endGesture());
      }}
    />
  );
}

export function MassReadout() {
  const scene = useLab((s) => s.scene);
  if (!scene) return null;
  const pct = Math.min(100, (scene.mass.total_g / scene.mass.target_g) * 100);
  return (
    <div className="border-b border-line bg-bg px-2 py-1.5" data-testid="mass-readout">
      <div className="flex items-baseline justify-between">
        <span className="text-dim">Mass</span>
        <span>
          <b className={scene.mass.over_budget ? "text-err" : ""} data-testid="mass-total">{fmt(scene.mass.total_g, 0)}</b>
          <span className="text-dim"> / {fmt(scene.mass.target_g, 0)} g</span>
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded bg-bg3">
        <div className={scene.mass.over_budget ? "h-full bg-err" : "h-full bg-ok"} style={{ width: `${pct}%` }} />
      </div>
      {scene.warnings.length > 0 && (
        <div className="mt-1 text-[10px] text-warn" data-testid="mass-warning" title={scene.warnings.join("\n")}>
          {scene.warnings.length} warning{scene.warnings.length > 1 ? "s" : ""}: {scene.warnings[0]}
        </div>
      )}
      <div className="mt-1 flex justify-between text-[10px] text-dim">
        <span>height {fmt(scene.extents.height_mm, 0)} mm</span>
        <span>length {fmt(scene.extents.length_mm, 0)} mm</span>
        <span>CoM z {fmt(scene.com[2], 0)} mm</span>
      </div>
    </div>
  );
}

export function GenomePanel() {
  const run = useLab((s) => s.run);
  return (
    <div className="flex h-full flex-col" data-testid="genome-panel">
      <MassReadout />
      <PanelScroll className="p-2">
        <RoleForm role="genome" />
        <div className="mt-2 flex gap-1">
          <Button size="sm" onClick={() => void run("reset_genes")}>Reset to defaults</Button>
          <Button size="sm" variant="primary" onClick={() => void execute("Bake")}>Bake design</Button>
        </div>
      </PanelScroll>
    </div>
  );
}

export function SimulatePanel() {
  const metrics = usePlayback((s) => s.metrics);
  const meta = useLab((s) => s.meta);
  const busy = useLab((s) => s.jobs.some((j) => j.kind === "sim" && (j.status === "running" || j.status === "queued")));
  const tuning = useLab((s) => s.jobs.some((j) => j.kind === "tune" && (j.status === "running" || j.status === "queued")));
  return (
    <PanelScroll data-testid="simulate-panel">
      <div className="flex items-center gap-2 border-b border-line bg-bg p-2">
        <Button variant="primary" disabled={busy} onClick={() => void execute("RunSim")}>{busy ? "Simulating..." : "Simulate (F5)"}</Button>
        <span className="text-dim">Poses stream into the viewport; scrub them on the timeline.</span>
      </div>
      <Section
        title="Controller"
        right={
          <span className="flex gap-1">
            <Button
              size="sm"
              variant="ghost"
              disabled={tuning}
              title="Search gait numbers for this body as it is, within the motors' speed, and write them here (a job; undoable)"
              data-testid="tune-gait"
              onClick={() => void execute("TuneGait")}
            >
              {tuning ? "Tuning..." : "Tune for this body"}
            </Button>
            <Button size="sm" variant="ghost" title="Put every gait value back to its default (undoable)" data-testid="reset-gait" onClick={() => void execute("ResetNodeParams", { node: "controller" })}>Reset to defaults</Button>
          </span>
        }
      >
        <RoleForm role="controller" />
      </Section>
      <Section title="Simulation"><RoleForm role="simulation" /></Section>
      <Section title="Model (terrain, servos, skin)"><RoleForm role="model" /></Section>
      <Section title="Fitness"><RoleForm role="fitness" /></Section>
      {metrics && meta && (
        <Section title="Metrics of the run on the timeline">
          {Object.entries(meta.metrics).map(([key, def]) => (
            <Row key={key} label={def.label} title={`${def.better} is better`}>
              <span className="selectable">{fmt(metrics[key], 3)}</span>
              <span className="text-[10px] text-dim">{def.unit}</span>
            </Row>
          ))}
        </Section>
      )}
    </PanelScroll>
  );
}

interface MarginRow {
  joint: string;
  actuator: string;
  name: string;
  transmission: string;
  available_nm: number;
  required_peak_nm: number | null;
  margin: number | null;
  verified: boolean;
}

export function MechanismPanel() {
  const revision = useLab((s) => s.state?.revision);
  const runs = useLab((s) => s.runs);
  const [data, setData] = useState<{ run_id: string | null; rows: MarginRow[] } | null>(null);
  const [runId, setRunId] = useState("");
  const sims = runs.filter((r) => r.kind === "sim");
  useEffect(() => {
    void api.post<{ run_id: string | null; rows: MarginRow[] }>("/api/analysis/torque_margin", { run_id: runId }).then(setData).catch(() => setData(null));
  }, [revision, runId, runs.length]);
  return (
    <PanelScroll data-testid="mechanism-panel">
      <Section title="Actuators and transmission"><RoleForm role="genome" filterGroup="Mechanism" /></Section>
      <Section
        title="Torque margin per joint"
        right={
          <select value={runId} onChange={(e) => setRunId(e.target.value)} title="Sim run the required torques come from">
            <option value="">latest run</option>
            {sims.map((r) => <option key={r.id} value={r.id}>{r.id}</option>)}
          </select>
        }
      >
        {!data?.run_id && (
          <div className="mb-2 text-dim">
            No simulation run yet: only available torque is shown. Press F5 to simulate, then required torque and margins appear here.
          </div>
        )}
        <table className="w-full">
          <thead className="text-left text-[10px] text-dim uppercase">
            <tr><th>Joint</th><th>Actuator</th><th className="text-right">Req.</th><th className="text-right">Avail.</th><th className="pl-2">Margin</th></tr>
          </thead>
          <tbody>
            {data?.rows.map((r) => {
              const m = r.margin;
              const tone = m === null ? "bg-bg3" : m < 0.05 ? "bg-err" : m < 0.3 ? "bg-warn" : "bg-ok";
              return (
                <tr key={r.joint} className="border-t border-line/40" data-joint={r.joint}>
                  <td className="font-mono text-[11px]">{r.joint.replace("joint.", "")}</td>
                  <td className="truncate" title={`${r.name} (${r.transmission})`}>
                    {r.name.replace("Dynamixel ", "").replace("Feetech ", "")} {!r.verified && <Unverified />}
                  </td>
                  <td className="text-right">{fmt(r.required_peak_nm)}</td>
                  <td className="text-right">{fmt(r.available_nm)}</td>
                  <td className="pl-2">
                    <div className="flex items-center gap-1">
                      <div className="h-1.5 w-14 overflow-hidden rounded bg-bg3">
                        <div className={`h-full ${tone}`} style={{ width: `${Math.max(0, Math.min(1, m ?? 0)) * 100}%` }} />
                      </div>
                      <span className={m !== null && m < 0.05 ? "text-err" : ""}>{m === null ? "-" : `${Math.round(m * 100)}%`}</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="mt-2 text-[10px] text-dim">
          Required = peak torque in the chosen run (N*m). Available = stall torque x derating. All actuator figures are unverified
          until checked against a datasheet or bench test.
        </div>
      </Section>
      <Section title="Planned checks">
        <div className="flex flex-col gap-1 text-dim">
          <span><Badge tone="info">planned</Badge> Range-of-motion sweep and interference check between parts across the joint range</span>
          <span><Badge tone="info">planned</Badge> Linkage transmission editor</span>
        </div>
      </Section>
    </PanelScroll>
  );
}

export function PlannedPanel({ title, intro, items, plugins }: { title: string; intro: string; items: string[]; plugins?: [string, string][] }) {
  const all = useLab((s) => s.plugins);
  return (
    <PanelScroll className="p-3">
      <Empty title={title}>{intro}</Empty>
      <Section title="What will live here">
        <ul className="list-disc pl-4 text-dim">
          {items.map((i) => <li key={i}>{i}</li>)}
        </ul>
      </Section>
      {plugins && (
        <Section title="Already scaffolded as plugins">
          {plugins.map(([type, key]) => {
            const p = (all[type] ?? []).find((x) => x.key === key);
            return p ? (
              <div key={key} className="py-0.5">
                <span className="font-semibold">{p.label}</span> {p.stub ? <Badge tone="info">planned</Badge> : <Badge tone="ok">ready</Badge>}
                <div className="text-dim">{p.description}</div>
              </div>
            ) : null;
          })}
        </Section>
      )}
    </PanelScroll>
  );
}
