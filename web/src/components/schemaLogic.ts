// Pure presentation helpers for schema-driven forms (unit tested with Vitest).
import type { FieldSchema } from "@/api/types";

/** Fields grouped by their `group`, preserving first-seen order; ungrouped fields come first. */
export function groupFields(fields: FieldSchema[], only?: string): [string | null, FieldSchema[]][] {
  const order: (string | null)[] = [];
  const map = new Map<string | null, FieldSchema[]>();
  for (const f of fields) {
    if (only !== undefined && f.group !== only) continue;
    const g = f.group ?? null;
    if (!map.has(g)) {
      map.set(g, []);
      order.push(g);
    }
    map.get(g)!.push(f);
  }
  order.sort((a, b) => (a === null ? -1 : b === null ? 1 : 0));
  return order.map((g) => [g, map.get(g)!]);
}

/** Slider increment: the schema's step, else 1 for integers, else ~1/200 of the range rounded to a 1-2-5 value. */
export function numberStep(field: Pick<FieldSchema, "step" | "type" | "min" | "max">): number {
  if (field.step) return field.step;
  if (field.type === "integer") return 1;
  if (field.min === null || field.max === null) return 0.1;
  const raw = (field.max - field.min) / 200;
  if (raw <= 0) return 0.1;
  const pow = Math.pow(10, Math.floor(Math.log10(raw)));
  const m = raw / pow;
  const nice = m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10;
  return Number((nice * pow).toPrecision(12));
}
