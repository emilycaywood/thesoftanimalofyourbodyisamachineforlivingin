// Keyboard shortcuts: documented defaults, rebindable, stored per browser.

export const DEFAULT_KEYS: Record<string, string> = {
  "Ctrl+Z": "Undo",
  "Ctrl+Y": "Redo",
  "Ctrl+Shift+Z": "Redo",
  F5: "RunSim",
  B: "Bake",
  "Ctrl+Alt+W": "DisplayWireframe",
  "Ctrl+Alt+S": "DisplayShaded",
  "Ctrl+Alt+G": "DisplayGhosted",
  "Ctrl+Alt+X": "DisplayXray",
  "Ctrl+Alt+R": "DisplayRendered",
  "Ctrl+Shift+E": "ZoomExtents",
  "Ctrl+Shift+S": "ZoomSelected",
  H: "Hide",
  "Alt+H": "Show",
  I: "Isolate",
  "Ctrl+A": "SelAll",
  Escape: "SelNone",
  K: "Play",
  M: "Measure",
  F1: "Shortcuts",
};

const STORAGE = "calflab.keys";

export function loadKeys(): Record<string, string> {
  try {
    const raw = localStorage.getItem(STORAGE);
    if (raw) return { ...DEFAULT_KEYS, ...JSON.parse(raw) };
  } catch {
    /* fall through */
  }
  return { ...DEFAULT_KEYS };
}

export function saveKeys(keys: Record<string, string>): void {
  const diff: Record<string, string> = {};
  for (const [k, v] of Object.entries(keys)) if (DEFAULT_KEYS[k] !== v) diff[k] = v;
  for (const k of Object.keys(DEFAULT_KEYS)) if (!(k in keys)) diff[k] = "";
  localStorage.setItem(STORAGE, JSON.stringify(diff));
}

export function resetKeys(): void {
  localStorage.removeItem(STORAGE);
}

/** Canonical chord for a keyboard event, e.g. "Ctrl+Shift+E". */
export function chord(e: { ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean; key: string }): string {
  const parts: string[] = [];
  if (e.ctrlKey || e.metaKey) parts.push("Ctrl");
  if (e.altKey) parts.push("Alt");
  if (e.shiftKey) parts.push("Shift");
  let key = e.key;
  if (key === " ") key = "Space";
  else if (key.length === 1) key = key.toUpperCase();
  if (["Control", "Shift", "Alt", "Meta"].includes(key)) return "";
  parts.push(key);
  return parts.join("+");
}

export function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || !el.tagName) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable;
}
