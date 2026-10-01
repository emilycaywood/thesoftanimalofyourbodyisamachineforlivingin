// Pure view helpers (screen-space selection, snapping). Unit tested with Vitest.

export interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export function normRect(ax: number, ay: number, bx: number, by: number): Rect {
  return { x0: Math.min(ax, bx), y0: Math.min(ay, by), x1: Math.max(ax, bx), y1: Math.max(ay, by) };
}

/**
 * Rhino selection semantics: dragging left-to-right is a *window* (objects must
 * be entirely inside); right-to-left is a *crossing* (touching is enough).
 */
export function rectSelect(rect: Rect, boxes: { id: string; box: Rect }[], crossing: boolean): string[] {
  const out: string[] = [];
  for (const { id, box } of boxes) {
    const inside = box.x0 >= rect.x0 && box.x1 <= rect.x1 && box.y0 >= rect.y0 && box.y1 <= rect.y1;
    const touches = box.x0 <= rect.x1 && box.x1 >= rect.x0 && box.y0 <= rect.y1 && box.y1 >= rect.y0;
    if (crossing ? touches : inside) out.push(id);
  }
  return out;
}

export function snapValue(value: number, step: number): number {
  if (!step || step <= 0) return value;
  return Math.round(value / step) * step;
}
