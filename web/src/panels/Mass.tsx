// Mass breakdown: every part's mass with where the number comes from (pushed
// solid x material, a pushed solid estimated as printed with infill, weighed,
// component entry, or the parametric estimate) and
// the total against the target. The rows, sums and labels are computed by the
// server (scene.mass.breakdown); this panel only lays them out.
import { useEffect, useState } from "react";
import type { MassItem, MassSource } from "@/api/types";
import { Badge, Button, Empty, PanelScroll, Section, Unverified, fmt } from "@/components/ui";
import { useLab } from "@/store/lab";
import { useView } from "@/store/view";

const TONE: Record<MassSource, "ok" | "info" | "neutral" | "warn"> = {
  infill: "warn",
  geometry: "ok",
  measured: "info",
  component: "neutral",
  parametric: "warn",
};
const SHORT: Record<MassSource, string> = {
  infill: "infill est.",
  geometry: "geometry",
  measured: "measured",
  component: "component",
  parametric: "estimate",
};

export function SourceBadge({ source, label }: { source: MassSource; label: string }) {
  return <Badge tone={TONE[source]} title={label}>{SHORT[source]}</Badge>;
}

function ItemRow({ item, labels }: { item: MassItem; labels: Record<MassSource, string> }) {
  const of = item.component ?? item.material;
  return (
    <tr className="text-dim" data-mass-item={item.id}>
      <td className="truncate pl-4 font-mono text-[10px]" title={item.note || item.infill?.label || item.id}>{item.id}</td>
      <td className="truncate text-[10px]">{of}{item.verified === false && <span className="text-warn" title="Unverified library entry"> *</span>}</td>
      <td><SourceBadge source={item.source} label={labels[item.source]} /></td>
      <td className="text-right">
        {fmt(item.mass_g, 1)}
        {item.computed_g !== null && <span className="text-[10px]" title="Computed value the weighed mass replaced"> (calc. {fmt(item.computed_g, 1)})</span>}
        {item.infill && <span className="text-[10px]" title={item.infill.label}> ({fmt(item.infill.infill_pct)} % infill, dense {fmt(item.infill.dense_g, 1)})</span>}
        {item.replaced_g !== null && <span className="text-[10px]" title="Envelope estimate this solid replaced: not counted"> (est. {fmt(item.replaced_g, 1)})</span>}
      </td>
    </tr>
  );
}

function TargetEditor() {
  const mass = useLab((s) => s.scene!.mass);
  const run = useLab((s) => s.run);
  const [text, setText] = useState("");
  useEffect(() => setText(String(mass.target_g)), [mass.target_g]);
  const commit = () => {
    const v = Number(text);
    if (text.trim() === "" || Number.isNaN(v) || v === mass.target_g) return setText(String(mass.target_g));
    void run("set_mass_target", { mass_g: v }).catch(() => setText(String(mass.target_g)));
  };
  return (
    <span className="flex items-center gap-1">
      <span className="text-dim">target</span>
      <input
        type="text"
        className="w-16 text-right"
        data-testid="mass-target"
        title="This project's mass target in grams (0 = the default from config/robot_defaults.yaml)"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      />
      <span className="text-dim">g</span>
      {mass.target_source === "default" && <span className="text-[10px] text-dim">(default)</span>}
    </span>
  );
}

export function MassPanel() {
  const scene = useLab((s) => s.scene);
  const selection = useView((s) => s.selection);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  if (!scene) return <Empty title="Mass breakdown" />;
  const b = scene.mass.breakdown;
  const labels = b.source_labels;
  const sources = (Object.keys(labels) as MassSource[]).filter((k) => b.by_source_g[k] > 0);
  return (
    <PanelScroll data-testid="mass-panel">
      <Section title="Total" right={<TargetEditor />}>
        <div className="flex items-baseline justify-between">
          <b className={scene.mass.over_budget ? "text-err" : ""} data-testid="mass-breakdown-total">{fmt(b.total_g, 1)} g</b>
          <span className="text-[10px] text-dim">{fmt(b.unverified_g, 0)} g rests on unverified library entries (*)</span>
        </div>
        <table className="mt-1 w-full">
          <tbody>
            {sources.map((k) => (
              <tr key={k} data-mass-source={k}>
                <td className="w-20"><SourceBadge source={k} label={labels[k]} /></td>
                <td className="text-dim">{labels[k]}</td>
                <td className="text-right">{fmt(b.by_source_g[k], 1)} g</td>
              </tr>
            ))}
          </tbody>
        </table>
        {scene.warnings.map((w) => (
          <div key={w} className="mt-1 text-warn" data-testid="design-warning">{w}</div>
        ))}
      </Section>
      <Section
        title="By part"
        right={<Button size="sm" variant="ghost" onClick={() => setOpen(Object.fromEntries(b.bodies.map((r) => [r.body, !Object.values(open).some(Boolean)])))}>Expand / collapse</Button>}
      >
        <table className="w-full table-fixed">
          <thead className="text-left text-[10px] text-dim uppercase">
            <tr><th className="w-[38%]">Part</th><th className="w-[24%]">Material</th><th className="w-[16%]">Source</th><th className="text-right">Mass g</th></tr>
          </thead>
          <tbody>
            {b.bodies.map((r) => (
              <BodyRows
                key={r.body}
                row={r}
                labels={labels}
                open={!!open[r.body]}
                selected={selection.includes(r.body)}
                toggle={() => setOpen((o) => ({ ...o, [r.body]: !o[r.body] }))}
              />
            ))}
          </tbody>
        </table>
        <div className="mt-2 text-[10px] text-dim">
          The Source column is that of the part's printed structure; open a part for its motors, electronics, skin and hoof. A
          pushed solid replaces the envelope estimate (shown as "est.", not counted). "infill est." is a pushed solid weighed
          as printed, a dense shell plus an infilled core: an estimate, not a weighed mass. Select a part to change its material or
          enter a weighed mass in Properties.
        </div>
      </Section>
      {b.not_counted.length > 0 && (
        <Section title="Not in the mass model">
          {b.not_counted.map((n) => (
            <div key={n.component} className="flex justify-between text-dim">
              <span>{n.qty} x {n.name} <Unverified /></span>
              <span>{fmt(n.mass_g, 1)} g</span>
            </div>
          ))}
          <div className="mt-1 text-[10px] text-dim">These sensors have no body in the model, so their library mass is not in the total.</div>
        </Section>
      )}
    </PanelScroll>
  );
}

function BodyRows({ row, labels, open, selected, toggle }: {
  row: import("@/api/types").MassBodyRow;
  labels: Record<MassSource, string>;
  open: boolean;
  selected: boolean;
  toggle: () => void;
}) {
  const st = row.structure;
  return (
    <>
      <tr
        className={`cursor-default border-t border-line/40 hover:bg-bg3 ${selected ? "bg-accent/25" : ""}`}
        data-mass-body={row.body}
        onClick={() => {
          useView.getState().select([row.body]);
          toggle();
        }}
      >
        <td className="truncate font-mono text-[11px]" title={row.name}>{open ? "▾" : "▸"} {row.body}</td>
        <td className="truncate" title={st.material_label}>{st.source ? (st.material ?? st.material_label) : ""}</td>
        <td>
          {st.source && <SourceBadge source={st.source} label={st.source_label} />}
          {st.note && <span className="text-warn" title={st.note}> !</span>}
        </td>
        <td className="text-right">{fmt(row.total_g, 1)}</td>
      </tr>
      {open && row.items.map((i) => <ItemRow key={i.id} item={i} labels={labels} />)}
    </>
  );
}
