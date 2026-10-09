// Panel registry: every dockable panel by id. Workspaces (workspaces.ts) are
// lists of these ids. To add a panel: write the component, add it here.
import type { FC } from "react";
import { ViewportPanel } from "@/viewport/Viewport";
import { ConsolePanel, DesignsPanel, JobsPanel, LayersPanel, OverridesPanel, RunsPanel, TreePanel } from "./basic";
import { GenomePanel, MechanismPanel, PlannedPanel, SimulatePanel } from "./Design";
import { ArchivePanel, EvolvePanel } from "./Evolve";
import type { PanelId } from "./ids";
import { MassPanel } from "./Mass";
import { NodeEditorPanel } from "./NodeEditor";
import { FabricatePanel, JournalPanel, WirePanel } from "./Output";
import { PropertiesPanel } from "./Properties";
import { TimelinePanel } from "./Timeline";

const BehavePanel: FC = () => (
  <PlannedPanel
    title="Behave (planned for Phase 4)"
    intro="Author reference motions and behaviors here. The motion library already accepts clips exported from the Blender add-on."
    items={[
      "Blender/Maya-style timeline: keyframes, dope sheet, curve editor for reference motions",
      "Behavior graph / state-machine editor with live sensor values on nodes",
      "Library of imported Blender animations (motions/ in the project)",
      "Performance mode: an operator blends authored animation with autonomous behavior",
    ]}
    plugins={[["behavior", "idle"], ["behavior", "touch_response"], ["behavior", "puppeteer_blend"], ["fitness_term", "imitation"]]}
  />
);

const DeployPanel: FC = () => (
  <PlannedPanel
    title="Deploy (planned for Phase 3)"
    intro="Bring a design onto the real robot. The firmware skeleton exporter already writes a PlatformIO project with this design's joint map (Fabricate > firmware exports)."
    items={[
      "Firmware / project generation for Teensy 4.1 and Raspberry Pi 5",
      "Calibration wizards (servo zero, joint limits, IMU alignment)",
      "Single-leg system-ID workflow from bench logs",
      "Live telemetry dashboard over serial/USB or network",
    ]}
    plugins={[["exporter", "firmware"], ["analysis", "system_id"], ["optimizer", "ppo"], ["simulator", "mjx"]]}
  />
);

export const PANELS: Record<PanelId, { title: string; component: FC }> = {
  viewport: { title: "Viewport", component: ViewportPanel },
  graph: { title: "Graph", component: NodeEditorPanel },
  layers: { title: "Layers", component: LayersPanel },
  tree: { title: "Scene tree", component: TreePanel },
  properties: { title: "Properties", component: PropertiesPanel },
  overrides: { title: "Overrides", component: OverridesPanel },
  genome: { title: "Form", component: GenomePanel },
  mass: { title: "Mass", component: MassPanel },
  mechanism: { title: "Mechanism", component: MechanismPanel },
  simulate: { title: "Simulate", component: SimulatePanel },
  timeline: { title: "Timeline", component: TimelinePanel },
  runs: { title: "Runs", component: RunsPanel },
  evolve: { title: "Evolve", component: EvolvePanel },
  archive: { title: "Archive", component: ArchivePanel },
  fabricate: { title: "Fabricate", component: FabricatePanel },
  wire: { title: "Wire", component: WirePanel },
  journal: { title: "Journal", component: JournalPanel },
  designs: { title: "Designs", component: DesignsPanel },
  console: { title: "Console", component: ConsolePanel },
  jobs: { title: "Jobs", component: JobsPanel },
  behave: { title: "Behave", component: BehavePanel },
  deploy: { title: "Deploy", component: DeployPanel },
};
