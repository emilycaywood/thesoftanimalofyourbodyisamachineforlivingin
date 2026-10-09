// Ids of all dockable panels (kept free of React imports so tests can check
// workspace definitions without loading the UI). Must match panels/registry.tsx.
export const PANEL_IDS = [
  "viewport",
  "graph",
  "layers",
  "tree",
  "properties",
  "overrides",
  "genome",
  "mass",
  "mechanism",
  "simulate",
  "timeline",
  "runs",
  "evolve",
  "archive",
  "fabricate",
  "wire",
  "journal",
  "designs",
  "console",
  "jobs",
  "behave",
  "deploy",
] as const;

export type PanelId = (typeof PANEL_IDS)[number];
