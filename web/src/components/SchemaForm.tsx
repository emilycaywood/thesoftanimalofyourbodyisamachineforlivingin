// Schema-driven form. Every plugin's parameter panel is rendered by this one
// component from the schema the server sends; plugins never ship UI code.
import { useEffect, useMemo, useState } from "react";
import type { FieldSchema, Schema } from "@/api/types";
import { groupFields, numberStep } from "./schemaLogic";

interface Props {
  schema: Schema;
  values: Record<string, unknown>;
  /** Called with a partial update. `final` is false while a slider is being dragged. */
  onChange: (patch: Record<string, unknown>, final: boolean) => void;
  disabled?: boolean;
  filterGroup?: string;
}

export function SchemaForm({ schema, values, onChange, disabled, filterGroup }: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const groups = useMemo(() => groupFields(schema.fields, filterGroup), [schema.fields, filterGroup]);
  const hasAdvanced = schema.fields.some((f) => f.advanced);
  return (
    <div className="flex flex-col gap-1">
      {groups.map(([group, fields]) => (
        <div key={group ?? "_"}>
          {group && <div className="mt-1 mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-dim">{group}</div>}
          {fields
            .filter((f) => showAdvanced || !f.advanced)
            .map((f) => (
              <Field
                key={f.name}
                field={f}
                value={values[f.name] ?? f.default}
                disabled={disabled}
                onChange={(v, final) => onChange({ [f.name]: v }, final)}
              />
            ))}
        </div>
      ))}
      {hasAdvanced && (
        <button className="self-start text-[11px] text-accent2 hover:underline" onClick={() => setShowAdvanced((v) => !v)}>
          {showAdvanced ? "Hide advanced" : "Show advanced"}
        </button>
      )}
      {schema.fields.length === 0 && <div className="text-dim">No parameters.</div>}
    </div>
  );
}

function Field({
  field,
  value,
  onChange,
  disabled,
}: {
  field: FieldSchema;
  value: unknown;
  onChange: (v: unknown, final: boolean) => void;
  disabled?: boolean;
}) {
  const unit = field.unit ? <span className="w-8 shrink-0 text-[10px] text-dim">{field.unit}</span> : null;
  const tip = `${field.description}${field.min !== null && field.max !== null ? `\nRange: ${field.min} to ${field.max}${field.unit ? " " + field.unit : ""}` : ""}`;
  return (
    <label className="flex min-h-6 items-center gap-2 py-px" title={tip} data-field={field.name}>
      <span className="w-[38%] shrink-0 truncate text-dim">{field.label}</span>
      <span className="flex min-w-0 flex-1 items-center gap-1">
        <Widget field={field} value={value} onChange={onChange} disabled={disabled} />
        {unit}
      </span>
    </label>
  );
}

function Widget({
  field,
  value,
  onChange,
  disabled,
}: {
  field: FieldSchema;
  value: unknown;
  onChange: (v: unknown, final: boolean) => void;
  disabled?: boolean;
}) {
  switch (field.ui) {
    case "slider":
      return <SliderInput field={field} value={Number(value)} onChange={onChange} disabled={disabled} />;
    case "number":
      return <NumberInput field={field} value={Number(value)} onChange={(v) => onChange(v, true)} disabled={disabled} />;
    case "toggle":
      return (
        <input type="checkbox" checked={Boolean(value)} disabled={disabled} onChange={(e) => onChange(e.target.checked, true)} />
      );
    case "enum":
      return (
        <select
          className="min-w-0 flex-1"
          value={String(value ?? "")}
          disabled={disabled}
          onChange={(e) => {
            const raw = e.target.value;
            const match = (field.choices ?? []).find((c) => String(c) === raw);
            onChange(match ?? raw, true);
          }}
        >
          {(field.choices ?? []).map((c) => (
            <option key={String(c)} value={String(c)}>
              {String(c)}
            </option>
          ))}
        </select>
      );
    case "color":
      return <input type="color" value={String(value ?? "#888888")} disabled={disabled} onChange={(e) => onChange(e.target.value, true)} />;
    case "vector3": {
      const v = Array.isArray(value) ? (value as number[]) : [0, 0, 0];
      return (
        <span className="flex min-w-0 flex-1 gap-1">
          {[0, 1, 2].map((i) => (
            <NumberInput
              key={i}
              field={field}
              value={Number(v[i] ?? 0)}
              disabled={disabled}
              onChange={(n) => {
                const next = [...v];
                next[i] = n;
                onChange(next, true);
              }}
            />
          ))}
        </span>
      );
    }
    case "text":
    case "file":
      return <TextInput value={String(value ?? "")} disabled={disabled} onCommit={(v) => onChange(v, true)} />;
    default:
      return <JsonInput value={value} disabled={disabled} onCommit={(v) => onChange(v, true)} />;
  }
}

function SliderInput({
  field,
  value,
  onChange,
  disabled,
}: {
  field: FieldSchema;
  value: number;
  onChange: (v: unknown, final: boolean) => void;
  disabled?: boolean;
}) {
  const step = numberStep(field);
  const cast = (n: number) => (field.type === "integer" ? Math.round(n) : n);
  return (
    <>
      <input
        type="range"
        className="min-w-0 flex-1"
        min={field.min ?? 0}
        max={field.max ?? 1}
        step={step}
        value={Number.isFinite(value) ? value : 0}
        disabled={disabled}
        onChange={(e) => onChange(cast(Number(e.target.value)), false)}
        onPointerUp={(e) => onChange(cast(Number((e.target as HTMLInputElement).value)), true)}
        onKeyUp={(e) => onChange(cast(Number((e.target as HTMLInputElement).value)), true)}
      />
      <NumberInput field={field} value={value} onChange={(v) => onChange(v, true)} disabled={disabled} narrow />
    </>
  );
}

function NumberInput({
  field,
  value,
  onChange,
  disabled,
  narrow,
}: {
  field: FieldSchema;
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
  narrow?: boolean;
}) {
  const [text, setText] = useState(String(value));
  useEffect(() => setText(Number.isFinite(value) ? String(Math.round(value * 1000) / 1000) : ""), [value]);
  const commit = () => {
    const n = Number(text);
    if (text.trim() === "" || Number.isNaN(n)) return setText(String(value));
    let v = field.type === "integer" ? Math.round(n) : n;
    if (field.min !== null) v = Math.max(field.min, v);
    if (field.max !== null) v = Math.min(field.max, v);
    if (v !== value) onChange(v);
    else setText(String(value));
  };
  return (
    <input
      type="text"
      inputMode="decimal"
      className={narrow ? "w-14 shrink-0 text-right" : "min-w-0 flex-1 text-right"}
      value={text}
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") setText(String(value));
      }}
    />
  );
}

function TextInput({ value, onCommit, disabled }: { value: string; onCommit: (v: string) => void; disabled?: boolean }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  return (
    <input
      type="text"
      className="min-w-0 flex-1"
      value={text}
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => text !== value && onCommit(text)}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
    />
  );
}

function JsonInput({ value, onCommit, disabled }: { value: unknown; onCommit: (v: unknown) => void; disabled?: boolean }) {
  const initial = JSON.stringify(value ?? null);
  const [text, setText] = useState(initial);
  const [bad, setBad] = useState(false);
  useEffect(() => {
    setText(initial);
    setBad(false);
  }, [initial]);
  return (
    <input
      type="text"
      className={`min-w-0 flex-1 font-mono text-[11px] ${bad ? "border-err!" : ""}`}
      value={text}
      disabled={disabled}
      title="JSON value"
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        if (text === initial) return;
        try {
          onCommit(JSON.parse(text));
          setBad(false);
        } catch {
          setBad(true);
        }
      }}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
    />
  );
}
