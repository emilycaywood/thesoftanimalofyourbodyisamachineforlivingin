// Mirror of server state. This store never computes domain results; it fetches
// them and reacts to the event stream.
import { create } from "zustand";
import { api, ApiError } from "@/api/client";
import { events } from "@/api/socket";
import type {
  CommandInfo,
  GraphView,
  Job,
  LabEvent,
  LabState,
  Meta,
  NodeTypeInfo,
  PluginInfo,
  RunSummary,
  Scene,
} from "@/api/types";

export interface LogLine {
  id: number;
  time: string;
  level: "info" | "warn" | "error" | "cmd";
  source: string;
  message: string;
}

export interface DesignSummary {
  id: string;
  name: string;
  version: number;
  created: string;
  note: string;
  mass_g: number;
  thumbnail: string | null;
}

interface LabStore {
  connected: boolean;
  ready: boolean;
  meta: Meta | null;
  state: LabState | null;
  scene: Scene | null;
  sceneError: string | null;
  graph: GraphView | null;
  nodeTypes: NodeTypeInfo[];
  plugins: Record<string, PluginInfo[]>;
  commands: CommandInfo[];
  jobs: Job[];
  runs: RunSummary[];
  designs: DesignSummary[];
  logs: LogLine[];
  pending: number;
  init: () => Promise<void>;
  refreshDoc: () => Promise<void>;
  refreshRuns: () => Promise<void>;
  refreshDesigns: () => Promise<void>;
  refreshPlugins: () => Promise<void>;
  log: (level: LogLine["level"], message: string, source?: string) => void;
  /** Run a server command; errors go to the log and are re-thrown as ApiError. */
  run: <T = any>(name: string, params?: Record<string, unknown>) => Promise<T>;
  endGesture: () => void;
}

let logId = 0;
let docTimer: ReturnType<typeof setTimeout> | null = null;
const eventHandlers = new Set<(e: LabEvent) => void>();

/** Other stores subscribe to raw events through this (after init). */
export function onLabEvent(handler: (e: LabEvent) => void): () => void {
  eventHandlers.add(handler);
  return () => eventHandlers.delete(handler);
}

export const useLab = create<LabStore>((set, get) => ({
  connected: false,
  ready: false,
  meta: null,
  state: null,
  scene: null,
  sceneError: null,
  graph: null,
  nodeTypes: [],
  plugins: {},
  commands: [],
  jobs: [],
  runs: [],
  designs: [],
  logs: [],
  pending: 0,

  log: (level, message, source = "lab") =>
    set((s) => ({
      logs: [
        ...s.logs.slice(-499),
        { id: ++logId, time: new Date().toLocaleTimeString(), level, source, message },
      ],
    })),

  refreshDoc: async () => {
    try {
      const [state, graph] = await Promise.all([api.get<LabState>("/api/state"), api.get<GraphView>("/api/graph")]);
      set({ state, graph });
    } catch (e) {
      get().log("error", (e as Error).message);
      return;
    }
    try {
      set({ scene: await api.get<Scene>("/api/scene"), sceneError: null });
    } catch (e) {
      set({ sceneError: (e as Error).message });
    }
  },

  refreshRuns: async () => {
    try {
      set({ runs: await api.get<RunSummary[]>("/api/runs") });
    } catch {
      /* reported on the next command */
    }
  },

  refreshDesigns: async () => {
    try {
      set({ designs: await api.get<DesignSummary[]>("/api/designs") });
    } catch {
      /* ignore */
    }
  },

  refreshPlugins: async () => {
    const [p, nodeTypes, commands] = await Promise.all([
      api.get<{ plugins: Record<string, PluginInfo[]>; errors: Record<string, string> }>("/api/plugins"),
      api.get<NodeTypeInfo[]>("/api/graph/node-types"),
      api.get<CommandInfo[]>("/api/commands"),
    ]);
    set({ plugins: p.plugins, nodeTypes, commands });
    for (const [src, err] of Object.entries(p.errors)) get().log("error", `Plugin ${src}: ${err}`, "plugins");
  },

  init: async () => {
    const meta = await api.get<Meta>("/api/meta");
    set({ meta });
    await Promise.all([get().refreshPlugins(), get().refreshDoc(), get().refreshRuns(), get().refreshDesigns()]);
    set({ jobs: await api.get<Job[]>("/api/jobs"), ready: true });

    events.onStatus((connected) => {
      const was = get().connected;
      set({ connected });
      if (connected && !was && get().ready) void get().refreshDoc();
    });
    events.on((e) => {
      switch (e.type) {
        case "state.changed":
          // coalesce bursts (slider drags) into one refresh
          if (docTimer) clearTimeout(docTimer);
          docTimer = setTimeout(() => void get().refreshDoc(), 30);
          break;
        case "job.updated": {
          const job = e.job as Job;
          set((s) => {
            const i = s.jobs.findIndex((j) => j.id === job.id);
            const jobs = i >= 0 ? s.jobs.map((j) => (j.id === job.id ? job : j)) : [job, ...s.jobs];
            return { jobs };
          });
          break;
        }
        case "job.finished": {
          const job = e.job as Job;
          if (job.status === "failed") get().log("error", `${job.title} failed: ${job.error}`, "jobs");
          else get().log("info", `${job.title}: ${job.status} (${job.duration_s.toFixed(1)} s)`, "jobs");
          if (job.kind === "sim") void get().refreshDoc();
          break;
        }
        case "runs.changed":
          void get().refreshRuns();
          break;
        case "designs.changed":
          void get().refreshDesigns();
          break;
        case "log":
          get().log(e.level ?? "info", e.message, e.source);
          break;
        case "plugins.changed":
          get().log("info", `Plugins reloaded: ${(e.files as string[]).map((f) => f.split(/[\\/]/).pop()).join(", ")}`, "plugins");
          void get().refreshPlugins().then(() => get().refreshDoc());
          break;
        case "backend.changed":
          void get().refreshDoc();
          break;
      }
      eventHandlers.forEach((h) => h(e));
    });
    events.connect();
  },

  run: async (name, params = {}) => {
    set((s) => ({ pending: s.pending + 1 }));
    try {
      const r = await api.command(name, params);
      return r.result;
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      get().log("error", `${name}: ${msg}`, "command");
      throw e;
    } finally {
      set((s) => ({ pending: Math.max(0, s.pending - 1) }));
    }
  },

  endGesture: () => {
    void api.post("/api/gesture/end").catch(() => undefined);
  },
}));
