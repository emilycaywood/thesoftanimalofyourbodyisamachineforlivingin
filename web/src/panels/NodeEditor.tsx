// Parametric node editor (Grasshopper conventions): nodes generated from plugin
// schemas, typed wires coloured by data type, orange/red for warnings/errors,
// grey for disabled, groups, clusters, and an output inspector.
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import clsx from "clsx";
import { Eye, EyeOff, Play, Power } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/api/client";
import type { GraphNode, GraphView, NodeTypeInfo } from "@/api/types";
import { execute } from "@/commands/registry";
import { Button, Empty } from "@/components/ui";
import { useLab } from "@/store/lab";
import { useView } from "@/store/view";

type Status = GraphView["status"][string];
interface CalfData extends Record<string, unknown> {
  node: GraphNode;
  status: Status;
  info?: NodeTypeInfo;
  colors: Record<string, string>;
}
type CalfNode = Node<CalfData, "calf">;
type GroupNode = Node<{ label: string; color: string; w: number; h: number }, "groupBox">;

const STATUS_BORDER: Record<string, string> = {
  ok: "var(--line)",
  warning: "var(--warn)",
  error: "var(--err)",
  stale: "var(--fg-dim)",
  blocked: "var(--fg-dim)",
  disabled: "var(--line)",
};

function CalfNodeView({ data, selected }: NodeProps<CalfNode>) {
  const { node, status, info, colors } = data;
  const run = useLab((s) => s.run);
  const st = status?.status ?? "error";
  const inline = node.type === "slider" || node.type === "number";
  const title = node.label ?? info?.label ?? node.type;
  return (
    <div
      className={clsx("min-w-[190px] rounded-md border-2 bg-bg2 text-[11px] shadow", st === "disabled" && "opacity-45")}
      style={{
        borderColor: selected ? "var(--accent)" : STATUS_BORDER[st],
        borderStyle: st === "stale" || st === "blocked" ? "dashed" : "solid",
        background: st === "error" ? "color-mix(in srgb, var(--err) 14%, var(--bg-2))" : st === "warning" ? "color-mix(in srgb, var(--warn) 12%, var(--bg-2))" : undefined,
      }}
      title={status?.messages.join("\n") || info?.description}
      data-node={node.id}
      data-status={st}
    >
      <div className="flex items-center gap-1 rounded-t border-b border-line bg-bg px-2 py-1">
        <span className="flex-1 truncate font-semibold">{title}</span>
        {status?.expensive && (
          <button className="nodrag hover:text-accent" title="Run this node as a job" onClick={() => void execute("RunSim")}>
            <Play size={12} />
          </button>
        )}
        <button className="nodrag text-dim hover:text-fg" title={node.preview ? "Preview on" : "Preview off"} onClick={() => void run("set_node_flags", { node: node.id, preview: !node.preview })}>
          {node.preview ? <Eye size={12} /> : <EyeOff size={12} />}
        </button>
        <button className={clsx("nodrag hover:text-fg", node.enabled ? "text-ok" : "text-dim")} title={node.enabled ? "Enabled (click to disable)" : "Disabled (click to enable)"} onClick={() => void run("set_node_flags", { node: node.id, enabled: !node.enabled })}>
          <Power size={12} />
        </button>
      </div>
      <div className="flex justify-between gap-4 py-1">
        <div className="flex flex-col gap-0.5">
          {(status?.inputs ?? []).map((s) => (
            <div key={s.name} className="relative pl-3 text-dim">
              <Handle type="target" position={Position.Left} id={s.name} style={{ background: colors[s.type] ?? "#999", width: 9, height: 9, left: -5 }} />
              {s.label || s.name}
            </div>
          ))}
        </div>
        <div className="flex flex-col items-end gap-0.5">
          {(status?.outputs ?? []).map((s) => (
            <div key={s.name} className="relative pr-3 text-dim">
              {s.label || s.name}
              <Handle type="source" position={Position.Right} id={s.name} style={{ background: colors[s.type] ?? "#999", width: 9, height: 9, right: -5 }} />
            </div>
          ))}
        </div>
      </div>
      {inline && (
        <div className="nodrag flex items-center gap-1 border-t border-line px-2 py-1">
          {node.type === "slider" && (
            <input
              type="range"
              className="min-w-0 flex-1"
              min={Number(node.params.min ?? 0)}
              max={Number(node.params.max ?? 1)}
              step={(Number(node.params.max ?? 1) - Number(node.params.min ?? 0)) / 200}
              value={Number(node.params.value ?? 0)}
              onChange={(e) => void run("set_node_params", { node: node.id, params: { value: Number(e.target.value) } })}
              onPointerUp={() => useLab.getState().endGesture()}
            />
          )}
          <span className="w-12 text-right font-mono">{Number(node.params.value ?? 0).toFixed(2)}</span>
        </div>
      )}
      <div className="truncate rounded-b bg-bg px-2 py-0.5 font-mono text-[9px] text-dim">
        {node.id} · {st}
        {status?.cached ? " · cached" : status?.duration_ms ? ` · ${status.duration_ms.toFixed(0)} ms` : ""}
      </div>
    </div>
  );
}

function GroupBox({ data }: NodeProps<GroupNode>) {
  return (
    <div
      className="rounded-lg border"
      style={{ width: data.w, height: data.h, borderColor: data.color, background: `color-mix(in srgb, ${data.color} 18%, transparent)` }}
    >
      <div className="px-2 py-0.5 text-[11px] font-semibold tracking-wide uppercase" style={{ color: data.color }}>{data.label}</div>
    </div>
  );
}

const nodeTypesMap = { calf: CalfNodeView, groupBox: GroupBox };
const estimateHeight = (st?: Status) => 62 + 17 * Math.max(st?.inputs.length ?? 0, st?.outputs.length ?? 0);

function Palette({ at, onClose }: { at: { x: number; y: number; fx: number; fy: number }; onClose: () => void }) {
  const types = useLab((s) => s.nodeTypes);
  const run = useLab((s) => s.run);
  const [q, setQ] = useState("");
  const list = types.filter((t) => !t.type.startsWith("cluster") && `${t.label} ${t.type} ${t.category}`.toLowerCase().includes(q.toLowerCase()));
  const add = (type: string) => {
    void run("add_node", { type, x: at.fx, y: at.fy }).catch(() => undefined);
    onClose();
  };
  return (
    <div className="absolute z-30 w-64 rounded border border-line bg-bg2 shadow-xl" style={{ left: at.x, top: at.y }}>
      <input
        autoFocus
        type="text"
        className="w-full rounded-b-none border-0 border-b"
        placeholder="Search nodes..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
          if (e.key === "Enter" && list[0]) add(list[0].type);
        }}
      />
      <div className="max-h-64 overflow-auto">
        {list.map((t) => (
          <div key={t.type} className="cursor-default px-2 py-0.5 hover:bg-bg3" title={t.description} onClick={() => add(t.type)}>
            <span className="text-[10px] text-dim">{t.category} · </span>
            {t.label}
          </div>
        ))}
        {!list.length && <div className="p-2 text-dim">No node matches.</div>}
      </div>
    </div>
  );
}

function Inspector({ nodeId }: { nodeId: string }) {
  const revision = useLab((s) => s.graph?.revision);
  const statusKey = useLab((s) => s.graph?.status[nodeId]?.status);
  const [out, setOut] = useState<any>(null);
  useEffect(() => {
    void api.get(`/api/graph/nodes/${nodeId}/output`).then(setOut).catch(() => setOut(null));
  }, [nodeId, revision, statusKey]);
  return (
    <div className="selectable h-36 shrink-0 overflow-auto border-t border-line bg-bg p-2 font-mono text-[11px]" data-testid="node-inspector">
      <div className="mb-1 font-sans text-[10px] font-semibold text-dim uppercase">Output of {nodeId}</div>
      {out ? <pre className="whitespace-pre-wrap">{JSON.stringify(out.outputs, null, 1)}</pre> : <span className="text-dim">No output.</span>}
      {out?.messages?.map((m: string, i: number) => <div key={i} className="text-warn">{m}</div>)}
    </div>
  );
}

function Editor() {
  const view = useLab((s) => s.graph);
  const nodeTypes = useLab((s) => s.nodeTypes);
  const meta = useLab((s) => s.meta);
  const run = useLab((s) => s.run);
  const selectedNode = useView((s) => s.selectedNode);
  const flow = useReactFlow();
  const wrap = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<CalfNode | GroupNode>([]);
  const [palette, setPalette] = useState<{ x: number; y: number; fx: number; fy: number } | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const colors = useMemo(() => meta?.socket_types ?? {}, [meta]);
  const selectedNodeRef = useRef<string[]>([]);
  selectedNodeRef.current = selected;

  useEffect(() => {
    if (!view) return;
    const byType = new Map(nodeTypes.map((t) => [t.type, t]));
    const pos = new Map(view.graph.nodes.map((n) => [n.id, n.pos]));
    const live = view.graph.groups.filter((g) => g.nodes.some((id) => pos.has(id)));
    const groupNodes: GroupNode[] = live.map((g) => {
      const members = g.nodes.filter((id) => pos.has(id));
      const xs = members.map((id) => pos.get(id)![0]);
      const ys = members.map((id) => pos.get(id)![1]);
      const bottoms = members.map((id) => pos.get(id)![1] + estimateHeight(view.status[id]));
      const x = Math.min(...xs) - 20;
      const y = Math.min(...ys) - 34;
      return {
        id: `group:${g.id}`,
        type: "groupBox",
        position: { x, y },
        data: { label: g.label, color: g.color, w: Math.max(...xs) + 240 - x, h: Math.max(...bottoms) + 16 - y },
        draggable: false,
        selectable: false,
        zIndex: -1,
      };
    });
    const calfNodes: CalfNode[] = view.graph.nodes.map((n) => ({
      id: n.id,
      type: "calf",
      position: { x: n.pos[0], y: n.pos[1] },
      data: { node: n, status: view.status[n.id], info: byType.get(n.type), colors },
      selected: selectedNodeRef.current.includes(n.id),
    }));
    setNodes([...groupNodes, ...calfNodes]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, nodeTypes, colors]);

  // The panel may be created while its tab is hidden (zero size): frame the
  // graph the first time it actually has room.
  const fitted = useRef(false);
  const hasNodes = nodes.length > 0;
  useEffect(() => {
    const el = wrap.current;
    if (!el || !hasNodes) return;
    const ro = new ResizeObserver(([entry]) => {
      if (fitted.current || entry.contentRect.width < 80 || entry.contentRect.height < 80) return;
      fitted.current = true;
      setTimeout(() => void flow.fitView({ padding: 0.15 }), 60);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [flow, hasNodes]);

  const edges: Edge[] = useMemo(() => {
    if (!view) return [];
    return view.graph.edges.map((e) => {
      const src = view.status[e.source]?.outputs.find((s) => s.name === e.source_socket);
      const stale = !["ok", "warning"].includes(view.status[e.source]?.status ?? "");
      return {
        id: e.id,
        source: e.source,
        sourceHandle: e.source_socket,
        target: e.target,
        targetHandle: e.target_socket,
        style: { stroke: colors[src?.type ?? "any"] ?? "#999", strokeWidth: 2, strokeDasharray: stale ? "5 4" : undefined },
      };
    });
  }, [view, colors]);

  if (!view) return <Empty title="Graph">Loading the dataflow graph...</Empty>;

  const onConnect = (c: Connection) => {
    if (!c.source || !c.target || !c.sourceHandle || !c.targetHandle) return;
    void run("connect", { source: c.source, source_socket: c.sourceHandle, target: c.target, target_socket: c.targetHandle }).catch(() => undefined);
  };
  const real = selected.filter((id) => !id.startsWith("group:"));

  return (
    <div className="flex h-full flex-col" data-testid="node-editor">
      <div className="flex h-7 shrink-0 items-center gap-1 border-b border-line bg-bg px-1">
        <Button size="sm" onClick={() => setPalette({ x: 8, y: 34, fx: 0, fy: -260 })}>Add node</Button>
        <Button size="sm" disabled={!real.length} onClick={() => void run("group_nodes", { ids: real, label: "Group" }).catch(() => undefined)}>Group</Button>
        <Button size="sm" disabled={!real.length} title="Collapse the selected nodes into a reusable cluster" onClick={() => void run("cluster_nodes", { ids: real }).catch(() => undefined)}>Cluster</Button>
        <Button size="sm" onClick={() => void execute("RunSim")}>Run simulation</Button>
        <Button size="sm" variant="primary" onClick={() => void execute("Bake")}>Bake</Button>
        <div className="flex-1" />
        <span className="text-dim">Double-click the canvas to add a node · Delete removes · wire colour = data type</span>
        <Button size="sm" variant="ghost" onClick={() => void execute("ResetGraph", {})}>Reset</Button>
      </div>
      <div ref={wrap} className="relative min-h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypesMap}
          onNodesChange={onNodesChange}
          onConnect={onConnect}
          onNodeDragStop={(_, __, dragged) => {
            const positions: Record<string, [number, number]> = {};
            for (const n of dragged) if (n.type === "calf") positions[n.id] = [n.position.x, n.position.y];
            void run("move_nodes", { positions }).finally(() => useLab.getState().endGesture());
          }}
          onNodesDelete={(del) => void run("remove_nodes", { ids: del.filter((n) => n.type === "calf").map((n) => n.id) }).catch(() => undefined)}
          onEdgesDelete={(del) => void run("disconnect", { ids: del.map((e) => e.id) }).catch(() => undefined)}
          onSelectionChange={({ nodes: sel }) => {
            const ids = sel.map((n) => n.id);
            setSelected(ids);
            const single = ids.length === 1 && !ids[0].startsWith("group:") ? ids[0] : null;
            if (single !== useView.getState().selectedNode) useView.getState().set({ selectedNode: single });
          }}
          onDoubleClick={(e) => {
            if (!(e.target as HTMLElement).classList.contains("react-flow__pane")) return;
            const b = wrap.current!.getBoundingClientRect();
            const p = flow.screenToFlowPosition({ x: e.clientX, y: e.clientY });
            setPalette({ x: e.clientX - b.left, y: e.clientY - b.top, fx: p.x, fy: p.y });
          }}
          onPaneClick={() => setPalette(null)}
          zoomOnDoubleClick={false}
          deleteKeyCode={["Delete", "Backspace"]}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.2}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={24} color="var(--line)" />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeColor={(n) => (n.type === "groupBox" ? "transparent" : "var(--fg-dim)")} maskColor="rgba(0,0,0,0.35)" />
        </ReactFlow>
        {palette && <Palette at={palette} onClose={() => setPalette(null)} />}
      </div>
      {selectedNode && <Inspector nodeId={selectedNode} />}
    </div>
  );
}

export function NodeEditorPanel() {
  return (
    <ReactFlowProvider>
      <Editor />
    </ReactFlowProvider>
  );
}
