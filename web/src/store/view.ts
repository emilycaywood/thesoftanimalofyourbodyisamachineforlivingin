// View state: what this user is looking at. Persisted per browser (layout,
// theme, navigation preset, overlays). Never holds domain results.
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type DisplayMode = "wireframe" | "shaded" | "ghosted" | "xray" | "rendered";
export type NavPreset = "rhino" | "blender" | "fusion";
export type ViewName = "top" | "front" | "right" | "perspective";
export type SelectionFilter = "body" | "geom";

export interface SavedView {
  name: string;
  position: [number, number, number];
  target: [number, number, number];
}

export const OVERLAYS: { key: string; label: string; ready: boolean }[] = [
  { key: "com", label: "Centre of mass", ready: true },
  { key: "jointAxes", label: "Joint axes + limit arcs", ready: true },
  { key: "support", label: "Support polygon", ready: true },
  { key: "contacts", label: "Contact forces", ready: true },
  { key: "massColors", label: "Mass-budget colours", ready: true },
  { key: "collision", label: "Collision geometry only", ready: true },
  { key: "harness", label: "Harness routes", ready: true },
  { key: "sensors", label: "Sensors", ready: true },
  { key: "grid", label: "Ground grid", ready: true },
  { key: "inertia", label: "Inertia ellipsoids (planned)", ready: false },
  { key: "torqueHeat", label: "Torque / temperature heat map (planned)", ready: false },
  { key: "rom", label: "Range-of-motion sweep (planned)", ready: false },
];

interface ViewStore {
  workspace: string;
  theme: "dark" | "light";
  nav: NavPreset;
  displayMode: DisplayMode;
  overlays: Record<string, boolean>;
  fourView: boolean;
  activeView: ViewName;
  savedViews: SavedView[];
  /** bumped to ask viewports to run a camera action */
  cameraRequest: { id: number; action: "extents" | "selected" | "view" | "saved"; view?: ViewName; saved?: SavedView };
  selection: string[];
  selectionFilter: SelectionFilter;
  hidden: string[];
  isolated: string[] | null;
  selectedNode: string | null;
  snapGrid: boolean;
  snapStep: number;
  gumballParam: string | null;
  gumballBound: boolean;
  /** value under the cursor while a gumball arrow is being dragged (not yet confirmed by the server) */
  gumballLive: number | null;
  measure: boolean;
  tourDone: boolean;
  set: (patch: Partial<ViewStore>) => void;
  select: (ids: string[], additive?: boolean) => void;
  toggleOverlay: (key: string) => void;
  requestCamera: (action: ViewStore["cameraRequest"]["action"], extra?: Partial<ViewStore["cameraRequest"]>) => void;
}

export const useView = create<ViewStore>()(
  persist(
    (set, get) => ({
      workspace: "form",
      theme: "dark",
      nav: "rhino",
      displayMode: "shaded",
      overlays: { com: true, jointAxes: false, support: true, grid: true, contacts: true },
      fourView: false,
      activeView: "perspective",
      savedViews: [],
      cameraRequest: { id: 0, action: "extents" },
      selection: [],
      selectionFilter: "body",
      hidden: [],
      isolated: null,
      selectedNode: null,
      snapGrid: true,
      snapStep: 1,
      gumballParam: null,
      gumballBound: false,
      gumballLive: null,
      measure: false,
      tourDone: false,
      set: (patch) => set(patch),
      select: (ids, additive = false) => {
        if (!additive) return set({ selection: ids, selectedNode: null });
        const cur = new Set(get().selection);
        for (const id of ids) {
          if (cur.has(id)) cur.delete(id);
          else cur.add(id);
        }
        set({ selection: [...cur], selectedNode: null });
      },
      toggleOverlay: (key) => set((s) => ({ overlays: { ...s.overlays, [key]: !s.overlays[key] } })),
      requestCamera: (action, extra = {}) =>
        set((s) => ({ cameraRequest: { ...extra, id: s.cameraRequest.id + 1, action } })),
    }),
    {
      name: "calflab.view",
      partialize: (s) => ({
        workspace: s.workspace,
        theme: s.theme,
        nav: s.nav,
        displayMode: s.displayMode,
        overlays: s.overlays,
        fourView: s.fourView,
        savedViews: s.savedViews,
        selectionFilter: s.selectionFilter,
        snapGrid: s.snapGrid,
        snapStep: s.snapStep,
        gumballBound: s.gumballBound,
        tourDone: s.tourDone,
      }),
    },
  ),
);
