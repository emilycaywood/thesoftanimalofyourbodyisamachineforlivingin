// Properties: generated from schemas and element tables for whatever is
// selected (a part, a component, a joint, a graph node). Shows the parametric
// value, override status with internalize / remove, and unverified-spec badges.
import { useEffect, useState } from "react";
import type { ComponentInfo, ElementInfo, ParamValue, StructureMass } from "@/api/types";
import { SchemaForm } from "@/components/SchemaForm";
import { Badge, Button, Empty, PanelScroll, Row, Section, Unverified, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";
import { useView } from "@/store/view";
import { SourceBadge } from "./Mass";

function ParamRow({ element, name, pv }: { element: string; name: string; pv: ParamValue }) {
  const run = useLab((s) => s.run);
  const endGesture = useLab((s) => s.endGesture);
  const [text, setText] = useState("");
  useEffect(() => setText(String(Math.round(pv.value * 1000) / 1000)), [pv.value]);
  const commit = () => {
    const v = Number(text);
    if (text.trim() === "" || Number.isNaN(v) || v === pv.value) return setText(String(pv.value));
    void run("add_override", { target: element, param: name, value: v, source: "web" })
      .catch(() => setText(String(pv.value)))
      .finally(endGesture);
  };
  return (
    <div className="border-b border-line/40 py-1" data-param={name}>
      <div className="flex items-center gap-2">
        <span className="w-[38%] shrink-0 truncate text-dim" title={pv.gene ? `Driven by gene ${pv.gene}` : "Not driven by a gene"}>
          {pv.label ?? name.replace(/_/g, " ")}
        </span>
        <input
          type="text"
          className="min-w-0 flex-1 text-right"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        />
        <span className="w-7 text-[10px] text-dim">{pv.unit}</span>
      </div>
      <div className="mt-0.5 flex flex-wrap items-center gap-1 pl-[38%] text-[10px]">
        {pv.override ? (
          <>
            <Badge tone="warn" title="This value is an explicit override layered over the parametric result.">override</Badge>
            <span className="text-dim">parametric {fmt(pv.parametric)}</span>
            {pv.gene && (
              <Button size="sm" title={`Write ${fmt(pv.value)} into gene ${pv.gene} and remove the override`} onClick={() => void run("internalize_override", { id: pv.override })}>
                Internalize
              </Button>
            )}
            <Button size="sm" onClick={() => void run("remove_override", { id: pv.override })}>Remove</Button>
          </>
        ) : pv.gene ? (
          <span className="text-dim">gene <span className="font-mono">{pv.gene}</span></span>
        ) : (
          <span className="text-dim">explicit only</span>
        )}
      </div>
    </div>
  );
}

const HIDDEN_SPECS = new Set(["key", "kind", "name", "manufacturer", "url", "source", "verified", "notes", "guessed", "defaulted"]);

/** Material and mass of a part's printed structure: choose the material, see where the mass comes from, enter a weighed value. */
function StructureCard({ id, st }: { id: string; st: StructureMass }) {
  const materials = useLab((s) => s.scene?.materials) ?? [];
  const run = useLab((s) => s.run);
  const [text, setText] = useState("");
  const measured = st.source === "measured" ? st.mass_g : null;
  useEffect(() => setText(measured === null ? "" : String(measured)), [measured]);
  const commit = () => {
    const v = text.trim() === "" ? 0 : Number(text);
    if (Number.isNaN(v) || v === (measured ?? 0)) return setText(measured === null ? "" : String(measured));
    void run("set_measured_mass", { target: id, mass_g: v }).catch(() => setText(measured === null ? "" : String(measured)));
  };
  const current = materials.find((m) => m.key === st.material);
  return (
    <Section title="Material and mass" right={st.source ? <SourceBadge source={st.source} label={st.source_label} /> : undefined}>
      <Row label="Material" title="Structure material of this part (config/components/materials.yaml)">
        <select
          className="min-w-0 flex-1"
          data-testid="part-material"
          value={st.material ?? ""}
          onChange={(e) => void run("set_part_material", { target: id, material: e.target.value }).catch(() => undefined)}
        >
          {materials.map((m) => (
            <option key={m.key} value={m.key}>{m.name} · {m.density_g_cm3} g/cm3{m.default ? " (default)" : ""}</option>
          ))}
        </select>
        {current && !current.verified && <Unverified />}
      </Row>
      <Row label="Structure mass" title="Mass of the printed part, without motors, electronics, skin or hoof">
        <b data-testid="part-mass">{fmt(st.mass_g, 1)} g</b>
      </Row>
      <Row label="Source"><span className="selectable" data-testid="part-mass-source">{st.source_label}</span></Row>
      {st.replaced_g !== null && (
        <Row label="Envelope estimate" title="The parametric estimate the pushed solid replaced: not counted">
          <span className="text-dim">{fmt(st.replaced_g, 1)} g (not counted)</span>
        </Row>
      )}
      {st.computed_g !== null && (
        <Row label="Computed" title="What the geometry and material give; the weighed value is used instead">
          <span className="text-dim" data-testid="part-mass-computed">{fmt(st.computed_g, 1)} g</span>
        </Row>
      )}
      <Row label="Measured" title="Weigh the printed part and enter it here; it replaces the computed structure mass. Empty = not weighed.">
        <input
          type="text"
          className="min-w-0 flex-1 text-right"
          data-testid="part-measured"
          placeholder="not weighed"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        />
        <span className="w-7 text-[10px] text-dim">g</span>
      </Row>
      {st.note && <div className="mt-1 text-warn" data-testid="part-mass-note">{st.note}</div>}
    </Section>
  );
}

function ComponentCard({ c }: { c: ComponentInfo }) {
  return (
    <Section title="Component" right={c.verified ? <Badge tone="ok">verified</Badge> : <Unverified source={c.source} />}>
      <div className="font-semibold">{c.name}</div>
      <div className="text-dim">{c.manufacturer}</div>
      <div className="mt-1">
        {Object.entries(c)
          .filter(([k, v]) => !HIDDEN_SPECS.has(k) && v !== "" && v !== null)
          .map(([k, v]) => (
            <Row key={k} label={k.replace(/_/g, " ")}>
              <span className="selectable truncate">{Array.isArray(v) ? v.join(" x ") : fmt(v)}</span>
              {c.guessed?.includes(k) && <Badge tone="warn" title="A guess: this value is not on the datasheet">guess</Badge>}
              {c.defaulted?.includes(k) && <Badge tone="warn" title="Not entered: this is the program's default, not a value of this part">default</Badge>}
            </Row>
          ))}
      </div>
      <div className="selectable mt-1 text-[10px] text-dim">Source: {c.source}</div>
      {c.url && (
        <a className="text-[11px] text-accent2 hover:underline" href={c.url} target="_blank" rel="noreferrer">
          Datasheet / product page
        </a>
      )}
      {c.notes && <div className="mt-1 text-[11px] text-warn">{c.notes}</div>}
    </Section>
  );
}

function ElementProps({ id, el }: { id: string; el: ElementInfo }) {
  const scene = useLab((s) => s.scene)!;
  const params = Object.entries(el.params ?? {});
  const joint = el.kind === "joint" ? scene.joints.find((j) => j.id === id) : undefined;
  const info = Object.entries(el).filter(
    ([k, v]) => !["kind", "name", "layer", "params", "component", "transmission", "wires", "structure"].includes(k) && v !== null && typeof v !== "object",
  );
  return (
    <>
      <Section title={el.kind} right={<Badge>{el.layer}</Badge>}>
        <div className="font-semibold">{el.name}</div>
        <div className="selectable font-mono text-[11px] text-accent">{id}</div>
        {info.map(([k, v]) => (
          <Row key={k} label={k.replace(/_/g, " ")}><span className="selectable truncate">{fmt(v)}</span></Row>
        ))}
        {Array.isArray(el.joints) && (el.joints as string[]).length > 0 && (
          <Row label="joints">
            {(el.joints as string[]).map((j) => (
              <button key={j} className="font-mono text-[11px] text-accent2 hover:underline" onClick={() => useView.getState().select([j])}>{j}</button>
            ))}
          </Row>
        )}
        {joint && (
          <>
            <Row label="range"><span>{joint.range_deg[0]} to {joint.range_deg[1]} deg</span></Row>
            <Row label="axis"><span className="font-mono">{joint.axis.join(", ")}</span></Row>
            {joint.actuator && (
              <Row label="actuator">
                <button className="font-mono text-[11px] text-accent2 hover:underline" onClick={() => useView.getState().select([joint.actuator!.id])}>
                  {joint.actuator.id}
                </button>
              </Row>
            )}
          </>
        )}
      </Section>
      {el.structure && <StructureCard id={id} st={el.structure} />}
      {params.length > 0 && (
        <Section title="Parameters">
          {params.map(([name, pv]) => (
            <ParamRow key={name} element={id} name={name} pv={pv} />
          ))}
        </Section>
      )}
      {el.component && <ComponentCard c={el.component} />}
      {joint?.actuator && <ComponentCard c={joint.actuator.component} />}
    </>
  );
}

function NodeProps({ nodeId }: { nodeId: string }) {
  const graph = useLab((s) => s.graph);
  const nodeTypes = useLab((s) => s.nodeTypes);
  const run = useLab((s) => s.run);
  const endGesture = useLab((s) => s.endGesture);
  const node = graph?.graph.nodes.find((n) => n.id === nodeId);
  if (!node || !graph) return null;
  const nt = nodeTypes.find((t) => t.type === node.type);
  const st = graph.status[nodeId];
  const cmd = node.type.startsWith("genome:") ? "set_genes" : "set_node_params";
  const form = cmd === "set_genes" && graph.genome_form?.node === node.id ? graph.genome_form : null;
  return (
    <>
      <Section title="Graph node" right={<Badge tone={st?.status === "ok" ? "ok" : st?.status === "error" ? "err" : "warn"}>{st?.status}</Badge>}>
        <div className="font-semibold">{node.label ?? nt?.label ?? node.type}</div>
        <div className="font-mono text-[11px] text-accent">{node.id} · {node.type}</div>
        <div className="mt-1 text-dim">{nt?.description}</div>
        {st?.messages.map((m, i) => (
          <div key={i} className={st.status === "error" ? "text-err" : "text-warn"}>{m}</div>
        ))}
      </Section>
      {nt && (
        <Section title="Parameters">
          <SchemaForm
            schema={form?.schema ?? nt.schema}
            values={form?.values ?? node.params}
            onChange={(patch, final) => {
              const params = cmd === "set_genes" ? { values: patch, real: !!form } : { node: node.id, params: patch };
              void run(cmd, params).catch(() => undefined).finally(() => final && endGesture());
            }}
          />
        </Section>
      )}
    </>
  );
}

export function PropertiesPanel() {
  const scene = useLab((s) => s.scene);
  const selection = useView((s) => s.selection);
  const selectedNode = useView((s) => s.selectedNode);
  if (selectedNode) return <PanelScroll data-testid="properties"><NodeProps nodeId={selectedNode} /></PanelScroll>;
  if (!scene) return <Empty title="Properties" />;
  if (selection.length === 0) {
    return (
      <PanelScroll data-testid="properties">
        <Section title="Document">
          <Row label="Mass">
            <span className={scene.mass.over_budget ? "text-err" : ""}>{fmt(scene.mass.total_g, 0)} g</span>
            <span className="text-dim">/ {fmt(scene.mass.target_g, 0)} g</span>
          </Row>
          <Row label="Height"><span>{fmt(scene.extents.height_mm, 0)} mm</span><span className="text-dim">target {scene.extents.target_height_mm}</span></Row>
          <Row label="Length"><span>{fmt(scene.extents.length_mm, 0)} mm</span><span className="text-dim">target {scene.extents.target_length_mm}</span></Row>
          <Row label="Centre of mass"><span className="font-mono">{scene.com.map((v) => v.toFixed(0)).join(", ")}</span></Row>
          <Row label="CoM margin" title="Distance from the CoM projection to the edge of the support polygon (standing)">
            <span className={scene.com_margin_mm < 0 ? "text-err" : ""}>{fmt(scene.com_margin_mm, 0)} mm</span>
          </Row>
        </Section>
        <div className="p-3 text-dim">Select a part in the viewport or the scene tree to see and edit its parameters.</div>
      </PanelScroll>
    );
  }
  if (selection.length > 1) {
    const mass = selection.reduce((m, id) => m + (Number(scene.elements[id]?.mass_g) || 0), 0);
    return (
      <PanelScroll data-testid="properties">
        <Section title={`${selection.length} objects selected`}>
          <Row label="Combined mass"><span>{fmt(mass, 0)} g</span></Row>
          <div className="selectable mt-1 font-mono text-[11px] text-dim">{selection.join(", ")}</div>
        </Section>
      </PanelScroll>
    );
  }
  const id = selection[0];
  const el = scene.elements[id];
  if (!el) return <Empty title="Not in this design">{id} is not part of the current design.</Empty>;
  return (
    <PanelScroll data-testid="properties">
      <ElementProps id={id} el={el} />
    </PanelScroll>
  );
}
