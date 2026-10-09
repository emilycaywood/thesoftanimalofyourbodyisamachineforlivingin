// Shapes of the JSON the server sends. Units: mm, g, degrees; quaternions (w, x, y, z).

export type Vec3 = [number, number, number];
export type Quat = [number, number, number, number];

export interface FieldSchema {
  name: string;
  label: string;
  type: "number" | "integer" | "boolean" | "enum" | "string" | "vector3" | "array" | "object" | "json" | "group";
  ui: "slider" | "number" | "toggle" | "enum" | "text" | "color" | "curve" | "vector3" | "json" | "file";
  default: unknown;
  unit: string | null;
  min: number | null;
  max: number | null;
  step: number | null;
  description: string;
  group: string | null;
  advanced: boolean;
  choices?: unknown[];
  fields?: FieldSchema[];
}

export interface Schema {
  title: string;
  description: string;
  fields: FieldSchema[];
}

export interface PluginInfo {
  type: string;
  key: string;
  label: string;
  description: string;
  version: string;
  stub: boolean;
  module: string;
  schema: Schema;
  [extra: string]: unknown;
}

export interface CommandInfo extends PluginInfo {
  mutates: boolean;
  category: string;
  shortcut: string | null;
  aliases: string[];
}

export interface ComponentInfo {
  key: string;
  kind: string;
  name: string;
  manufacturer: string;
  mass_g: number;
  dims_mm: Vec3;
  cost_usd: number;
  url: string;
  source: string;
  verified: boolean;
  notes: string;
  /** spec fields whose value is a guess, not a datasheet value */
  guessed?: string[];
  /** spec fields the entry does not give: the code's default is in use */
  defaulted?: string[];
  [spec: string]: unknown;
}

/** Where a mass comes from: pushed solid x material, weighed, library entry, or the envelope estimate. */
export type MassSource = "geometry" | "measured" | "component" | "parametric";

export interface StructureMass {
  mass_g: number;
  source: MassSource | null;
  source_label: string;
  material: string | null; // null when the part is made of solids in several materials
  materials: string[]; // every material the structure mass was computed with
  material_label: string; // e.g. "pla + stainless_304"
  solids: { id: string; label: string; material: string | null; mass_g: number; verified: boolean | null }[]; // pushed solids
  com_mm: [number, number, number] | null; // centre of mass of the structure, body frame
  computed_g: number | null; // value a weighed mass replaced
  replaced_g: number | null; // envelope estimate a pushed solid replaced (not counted)
  note: string;
}

export interface MassItem {
  id: string;
  label: string;
  layer: string;
  mass_g: number;
  source: MassSource;
  material: string | null;
  component: string | null;
  verified: boolean | null;
  computed_g: number | null;
  replaced_g: number | null;
  note: string;
}

export interface MassBodyRow {
  body: string;
  name: string;
  total_g: number;
  by_source_g: Partial<Record<MassSource, number>>;
  structure: StructureMass;
  items: MassItem[];
}

export interface MassBreakdown {
  total_g: number;
  by_source_g: Record<MassSource, number>;
  source_labels: Record<MassSource, string>;
  geometry_parts: string[];
  measured_parts: string[];
  unverified_g: number;
  bodies: MassBodyRow[];
  not_counted: { component: string; name: string; qty: number; mass_g: number }[];
}

export interface MaterialChoice {
  key: string;
  name: string;
  density_g_cm3: number;
  verified: boolean;
  default: boolean;
}

export interface GeomInfo {
  id: string;
  shape: "box" | "capsule" | "cylinder" | "sphere" | "ellipsoid" | "mesh";
  size: Vec3;
  pos: Vec3;
  quat: Quat;
  layer: string;
  role: "visual" | "collision" | "both";
  color: string | null;
  component: string | null;
  label: string | null;
  mass_g: number;
  mass_source: MassSource;
  material: string | null;
  foot: boolean;
  mesh: string | null;
}

export interface BodyInfo {
  id: string;
  name: string;
  parent: string | null;
  layer: string;
  part: boolean;
  pos: Vec3;
  quat: Quat;
  local_pos: Vec3;
  local_quat: Quat;
  geoms: GeomInfo[];
}

export interface JointInfo {
  id: string;
  name: string;
  body: string;
  parent_body: string | null;
  type: string;
  axis: Vec3;
  world_pos: Vec3;
  world_axis: Vec3;
  range_deg: [number, number];
  rest_deg: number;
  group: string;
  cosmetic: boolean;
  actuator: { id: string; component: ComponentInfo; transmission: { type: string; ratio: number } } | null;
}

export interface ParamValue {
  value: number;
  unit: string | null;
  gene: string | null;
  scale: number;
  offset: number;
  min: number | null;
  max: number | null;
  label: string | null;
  handle_axis: Vec3 | null;
  handle_frac: number;
  parametric: number | null;
  override: string | null;
}

export interface ElementInfo {
  kind: "body" | "geom" | "joint" | "actuator" | "sensor" | "skin" | "harness";
  name: string;
  layer: string;
  params?: Record<string, ParamValue>;
  component?: ComponentInfo | null;
  /** bodies with a fabricated structure: its material and where its mass comes from */
  structure?: StructureMass;
  [k: string]: unknown;
}

export interface LayerState {
  visible: boolean;
  locked: boolean;
  color: string;
}

export interface Scene {
  name: string;
  revision?: number;
  bodies: BodyInfo[];
  joints: JointInfo[];
  sensors: { id: string; type: string; body: string; pos: Vec3 }[];
  harness: { id: string; points: Vec3[]; length_mm: number }[];
  feet: { id: string; body: string; pos: Vec3; radius: number }[];
  com: Vec3;
  support_polygon: [number, number][];
  com_margin_mm: number;
  mass: {
    total_g: number;
    target_g: number;
    target_source: "project" | "default";
    over_budget: boolean;
    by_layer_g: Record<string, number>;
    by_body_g: Record<string, number>;
    breakdown: MassBreakdown;
  };
  /** structure materials a part can be given */
  materials: MaterialChoice[];
  extents: { height_mm: number; length_mm: number; scale: number; target_height_mm: number; target_length_mm: number };
  elements: Record<string, ElementInfo>;
  layers: Record<string, LayerState>;
  warnings: string[];
  genome: { definition: string; version: number; values: Record<string, number | string | boolean> };
}

export interface Override {
  id: string;
  name: string;
  target: string;
  kind: "param" | "geometry" | "material" | "mass";
  param: string | null;
  value: number | null;
  asset: string | null;
  material: string | null;
  meta?: {
    layer?: string;
    material?: string;
    solid?: { closed: boolean; volume_mm3: number };
    solids?: { name: string; material: string; solid: { closed: boolean; volume_mm3: number } }[]; // a push of several solids
  };
  enabled: boolean;
  source: string;
  created: string;
}

export interface LabState {
  project: { name: string; path: string };
  revision: number;
  can_undo: boolean;
  can_redo: boolean;
  overrides: Override[];
  layers: Record<string, LayerState>;
  roles: Record<string, string>;
  backend: string;
  code_version: string;
}

export interface Socket {
  name: string;
  type: string;
  label: string;
  required: boolean;
}

export interface GraphNode {
  id: string;
  type: string;
  params: Record<string, unknown>;
  pos: [number, number];
  enabled: boolean;
  preview: boolean;
  label: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  source_socket: string;
  target: string;
  target_socket: string;
}

export interface GraphView {
  /** the genome as the Form shows it: real values (lengths in mm on the body) and ranges to match */
  genome_form?: { node: string; schema: Schema; values: Record<string, unknown>; scaled: string[] } | null;
  graph: {
    nodes: GraphNode[];
    edges: GraphEdge[];
    groups: { id: string; label: string; color: string; nodes: string[] }[];
    roles: Record<string, string>;
  };
  status: Record<
    string,
    {
      status: "ok" | "warning" | "error" | "stale" | "blocked" | "disabled";
      messages: string[];
      cached: boolean;
      duration_ms: number;
      inputs: Socket[];
      outputs: Socket[];
      expensive: boolean;
    }
  >;
  revision: number;
}

export interface NodeTypeInfo {
  type: string;
  label: string;
  category: string;
  description: string;
  inputs: Socket[];
  outputs: Socket[];
  expensive: boolean;
  schema: Schema;
  defaults: Record<string, unknown>;
}

export interface Job {
  id: string;
  kind: string;
  title: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  message: string;
  created: string;
  duration_s: number;
  result: Record<string, any>;
  error: string | null;
  backend: string;
  retry_of: string | null;
  logs?: string[];
}

export interface RunSummary {
  id: string;
  kind: string;
  title: string;
  status: string;
  created: string;
  duration_s: number;
  seed: number | null;
  backend: string;
  fitness: number | null;
  parent: string | null;
}

export interface Channel {
  label: string;
  unit: string;
  group: string;
  values: number[];
}

export interface RolloutPayload {
  run_id: string;
  body_ids: string[];
  dt: number;
  t: number[];
  pos: number[][];
  quat: number[][];
  com: Vec3[];
  foot_force: number[][];
  foot_pos: Vec3[][];
  support: [number, number][][];
  foot_geoms: string[];
  series: { t: number[]; channels: Record<string, Channel> };
  scene: Scene | null;
  metrics: Record<string, any>;
}

export interface ArchiveView {
  axes: { key: string; label: string; unit: string; range: [number, number]; cells: number }[];
  cells: {
    i: number;
    j: number;
    candidate: string;
    fitness: number;
    generation: number;
    descriptors: Record<string, number>;
    speed_mps: number | null;
  }[];
}

export interface EvolveHistoryEntry {
  generation: number;
  best: number | null;
  mean: number | null;
  gen_best: number | null;
  gen_mean: number | null;
  coverage: number;
  elites: number;
  evals: number;
  failed: number;
}

export interface Meta {
  version: string;
  code_version: string;
  units: { length: string; mass: string; angle: string };
  layers: { name: string; color: string }[];
  socket_types: Record<string, string>;
  metrics: Record<string, { label: string; unit: string; better: string }>;
  fitness_presets: Record<string, { name: string; version: number; description: string; terms: any[] }>;
  plugin_errors: Record<string, string>;
}

export interface LabEvent {
  type: string;
  [k: string]: any;
}
