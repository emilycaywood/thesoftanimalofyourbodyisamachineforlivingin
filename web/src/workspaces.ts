// Workspaces: named dock layouts over one shared project and scene.
// Each entry lists the panels of its default layout; users can re-dock freely
// and the layout is saved per workspace.

export interface WorkspaceDef {
  id: string;
  label: string;
  ready: boolean; // false = scaffolded workspace (teaching empty state)
  center: string[]; // tabs in the centre group (first is active)
  beside?: string[]; // a second group to the right of the centre, sharing its width
  left: string[];
  right: string[];
  bottom: string[];
}

const LEFT = ["layers", "tree"];
const BOTTOM = ["console", "jobs"];

export const WORKSPACES: WorkspaceDef[] = [
  { id: "form", label: "Form", ready: true, center: ["viewport", "graph"], left: LEFT, right: ["genome", "properties", "overrides"], bottom: [...BOTTOM, "designs"] },
  { id: "mechanism", label: "Mechanism", ready: true, center: ["viewport"], left: LEFT, right: ["mechanism", "properties"], bottom: BOTTOM },
  { id: "simulate", label: "Simulate", ready: true, center: ["viewport", "graph"], left: LEFT, right: ["simulate", "properties"], bottom: ["timeline", "runs", ...BOTTOM] },
  { id: "evolve", label: "Evolve", ready: true, center: ["viewport", "archive"], left: LEFT, right: ["evolve", "properties"], bottom: ["timeline", "designs", ...BOTTOM] },
  { id: "behave", label: "Behave", ready: false, center: ["viewport"], left: LEFT, right: ["behave"], bottom: ["timeline", ...BOTTOM] },
  { id: "fabricate", label: "Fabricate", ready: true, center: ["viewport"], left: LEFT, right: ["fabricate", "properties"], bottom: BOTTOM },
  { id: "wire", label: "Wire", ready: true, center: ["viewport", "wire"], left: LEFT, right: ["properties"], bottom: BOTTOM },
  { id: "deploy", label: "Deploy", ready: false, center: ["viewport"], left: LEFT, right: ["deploy"], bottom: BOTTOM },
  // the viewport sits beside the journal, not behind it: a run or design picked on the right is seen at once
  { id: "journal", label: "Journal", ready: true, center: ["journal"], beside: ["viewport"], left: LEFT, right: ["runs", "designs"], bottom: BOTTOM },
];

export function workspace(id: string): WorkspaceDef {
  return WORKSPACES.find((w) => w.id === id) ?? WORKSPACES[0];
}
