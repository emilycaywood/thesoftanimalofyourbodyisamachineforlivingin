// Viewport panel: one or four views of the shared scene, with toolbar, window /
// crossing selection, gumball HUD and the measure tool.
import { Html, Line } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import clsx from "clsx";
import { Camera, Grid2x2, Layers, Ruler, Square } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { Scene } from "@/api/types";
import { execute, hooks } from "@/commands/registry";
import { Empty, IconButton } from "@/components/ui";
import { useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";
import { OVERLAYS, useView, type DisplayMode, type ViewName } from "@/store/view";
import { CameraRig } from "./CameraRig";
import { Gumball, gumballTarget, sendOverride } from "./Gumball";
import { Overlays } from "./Overlays";
import { RobotScene, type BodyGroups } from "./RobotScene";
import { normRect, rectSelect, type Rect } from "./viewLogic";

type RectPicker = (rect: Rect, crossing: boolean) => string[];

/** Lives inside the Canvas: exposes screen-space picking and capture to the DOM side. */
function Bridge({
  groups,
  picker,
  primary,
}: {
  groups: React.MutableRefObject<BodyGroups>;
  picker: React.MutableRefObject<RectPicker | null>;
  primary: boolean;
}) {
  const { camera, size, gl, scene } = useThree();
  useEffect(() => {
    picker.current = (rect, crossing) => {
      const boxes: { id: string; box: Rect }[] = [];
      const v = new THREE.Vector3();
      for (const [id, g] of groups.current) {
        if (!g.visible) continue;
        const b = new THREE.Box3().setFromObject(g);
        if (b.isEmpty()) continue;
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (let i = 0; i < 8; i++) {
          v.set(i & 1 ? b.max.x : b.min.x, i & 2 ? b.max.y : b.min.y, i & 4 ? b.max.z : b.min.z).project(camera);
          const sx = ((v.x + 1) / 2) * size.width;
          const sy = ((1 - v.y) / 2) * size.height;
          x0 = Math.min(x0, sx); x1 = Math.max(x1, sx); y0 = Math.min(y0, sy); y1 = Math.max(y1, sy);
        }
        boxes.push({ id, box: { x0, y0, x1, y1 } });
      }
      return rectSelect(rect, boxes, crossing);
    };
    if (primary) {
      hooks.capture = () => {
        gl.render(scene, camera);
        return gl.domElement.toDataURL("image/png");
      };
    }
    return () => {
      picker.current = null;
    };
  }, [camera, size, gl, scene, groups, picker, primary]);
  return null;
}

function MeasureTool() {
  const [pts, setPts] = useState<THREE.Vector3[]>([]);
  const onPoint = useCallback((p: THREE.Vector3) => setPts((cur) => (cur.length >= 2 ? [p] : [...cur, p])), []);
  const d = pts.length === 2 ? pts[0].distanceTo(pts[1]) : null;
  return (
    <>
      <MeasureCatcher onPoint={onPoint} />
      {pts.map((p, i) => (
        <mesh key={i} position={p} renderOrder={20}>
          <sphereGeometry args={[4, 12, 8]} />
          <meshBasicMaterial color="#ffd54f" depthTest={false} />
        </mesh>
      ))}
      {pts.length === 2 && (
        <>
          <Line points={[pts[0], pts[1]]} color="#ffd54f" lineWidth={2} depthTest={false} />
          <Html position={pts[0].clone().lerp(pts[1], 0.5)} center>
            <div className="rounded bg-black/80 px-1.5 py-0.5 font-mono text-[11px] whitespace-nowrap text-yellow-300">
              {d!.toFixed(1)} mm
            </div>
          </Html>
        </>
      )}
    </>
  );
}

/** Raycasts the robot on click while the measure tool is active. */
function MeasureCatcher({ onPoint }: { onPoint: (p: THREE.Vector3) => void }) {
  const { gl, camera, scene } = useThree();
  useEffect(() => {
    const ray = new THREE.Raycaster();
    const handler = (ev: MouseEvent) => {
      if (ev.button !== 0) return;
      const r = gl.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const robot = scene.getObjectByName("robot");
      const hits = robot ? ray.intersectObject(robot, true) : [];
      if (hits.length) onPoint(hits[0].point.clone());
    };
    gl.domElement.addEventListener("click", handler);
    return () => gl.domElement.removeEventListener("click", handler);
  }, [gl, camera, scene, onPoint]);
  return null;
}

function View({ view, scene, primary, onActivate }: { view: ViewName; scene: Scene; primary: boolean; onActivate: () => void }) {
  const layers = useLab((s) => s.state?.layers) ?? scene.layers;
  const mode = useView((s) => s.displayMode);
  const measure = useView((s) => s.measure);
  const groups = useRef<BodyGroups>(new Map());
  const picker = useRef<RectPicker | null>(null);
  const gumballDragging = useRef(false);
  const wrap = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const [rect, setRect] = useState<{ r: Rect; crossing: boolean } | null>(null);

  const local = (e: React.PointerEvent) => {
    const b = wrap.current!.getBoundingClientRect();
    return { x: e.clientX - b.left, y: e.clientY - b.top };
  };

  return (
    <div
      ref={wrap}
      className={clsx("relative h-full w-full overflow-hidden", primary ? "outline outline-1 outline-accent2/40" : "")}
      style={{ background: "var(--viewport)" }}
      onContextMenu={(e) => e.preventDefault()}
      onPointerDownCapture={(e) => {
        onActivate();
        if (e.button === 0 && !measure) drag.current = local(e);
      }}
      onPointerMove={(e) => {
        if (!drag.current || gumballDragging.current) return;
        const p = local(e);
        if (Math.abs(p.x - drag.current.x) + Math.abs(p.y - drag.current.y) < 6) return;
        setRect({ r: normRect(drag.current.x, drag.current.y, p.x, p.y), crossing: p.x < drag.current.x });
      }}
      onPointerUp={(e) => {
        if (rect && picker.current && !gumballDragging.current) {
          useView.getState().select(picker.current(rect.r, rect.crossing), e.shiftKey || e.ctrlKey);
        }
        drag.current = null;
        setRect(null);
      }}
      onPointerLeave={() => {
        drag.current = null;
        setRect(null);
      }}
    >
      <Canvas
        shadows={mode === "rendered"}
        gl={{ preserveDrawingBuffer: true, antialias: true }}
        onPointerMissed={(e) => {
          if (e.button === 0 && !rect && !measure && !gumballDragging.current) useView.getState().select([]);
        }}
      >
        <CameraRig view={view} groups={groups} active={primary} />
        <Bridge groups={groups} picker={picker} primary={primary} />
        <ambientLight intensity={mode === "rendered" ? 0.55 : 0.9} />
        <hemisphereLight args={["#ffffff", "#667080", 0.6]} />
        <directionalLight
          position={[900, -700, 1800]}
          intensity={mode === "rendered" ? 2.2 : 1.1}
          castShadow={mode === "rendered"}
          shadow-mapSize={[2048, 2048]}
          shadow-camera-left={-1200}
          shadow-camera-right={1200}
          shadow-camera-top={1200}
          shadow-camera-bottom={-1200}
          shadow-camera-far={5000}
          shadow-radius={6}
        />
        {mode === "rendered" && (
          <mesh position={[0, 0, -0.6]} receiveShadow>
            <planeGeometry args={[20000, 20000]} />
            <shadowMaterial opacity={0.28} />
          </mesh>
        )}
        <RobotScene scene={scene} layers={layers} groups={groups} />
        <Overlays scene={scene} layers={layers} />
        {primary && <Gumball scene={scene} dragging={gumballDragging} />}
        {primary && measure && <MeasureTool />}
      </Canvas>
      <div className="pointer-events-none absolute top-1 left-2 text-[11px] font-semibold tracking-wide text-dim uppercase">
        {view}
      </div>
      {rect && (
        <div
          className="pointer-events-none absolute border"
          style={{
            left: rect.r.x0,
            top: rect.r.y0,
            width: rect.r.x1 - rect.r.x0,
            height: rect.r.y1 - rect.r.y0,
            borderStyle: rect.crossing ? "dashed" : "solid",
            borderColor: rect.crossing ? "var(--ok)" : "var(--accent-2)",
            background: rect.crossing ? "color-mix(in srgb, var(--ok) 12%, transparent)" : "color-mix(in srgb, var(--accent-2) 12%, transparent)",
          }}
        />
      )}
    </div>
  );
}

function GumballHud({ scene }: { scene: Scene }) {
  const selection = useView((s) => s.selection);
  const preferred = useView((s) => s.gumballParam);
  const bound = useView((s) => s.gumballBound);
  const live = useView((s) => s.gumballLive);
  const playing = usePlayback((s) => s.source !== "none");
  const target = useMemo(() => gumballTarget(scene, selection, preferred), [scene, selection, preferred]);
  const [text, setText] = useState("");
  useEffect(() => {
    const v = live ?? target?.pv.value;
    setText(v === undefined ? "" : String(Math.round(v * 100) / 100));
  }, [target, live]);
  if (!target || playing) return null;
  const commit = () => {
    const v = Number(text);
    if (text.trim() !== "" && !Number.isNaN(v) && v !== target.pv.value) sendOverride(target, v, true);
  };
  return (
    <div className="absolute bottom-2 left-2 flex items-center gap-1 rounded border border-line bg-bg2/95 px-2 py-1 shadow" data-testid="gumball-hud">
      <span className="font-mono text-[11px] text-accent">{target.bodyId}</span>
      <select value={target.param} onChange={(e) => useView.getState().set({ gumballParam: e.target.value })}>
        {target.handles.map((h) => (
          <option key={h}>{h}</option>
        ))}
      </select>
      <input
        type="text"
        className="w-16 text-right"
        value={text}
        title="Drag the arrow in the viewport, or type an exact value and press Enter"
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      />
      <span className="text-dim">{target.pv.unit}</span>
      <select
        value={bound ? "gene" : "override"}
        title="Override: an explicit edit of this part only. Drive gene: change the gene behind it (all parts that share it)."
        onChange={(e) => useView.getState().set({ gumballBound: e.target.value === "gene" })}
      >
        <option value="override">Override this part</option>
        <option value="gene" disabled={!target.pv.gene}>
          Drive gene {target.pv.gene ?? ""}
        </option>
      </select>
    </div>
  );
}

const MODES: DisplayMode[] = ["wireframe", "shaded", "ghosted", "xray", "rendered"];
const VIEWS: ViewName[] = ["perspective", "top", "front", "right"];

export function ViewportPanel() {
  const docScene = useLab((s) => s.scene);
  const sceneError = useLab((s) => s.sceneError);
  const pbScene = usePlayback((s) => s.scene);
  const pbSource = usePlayback((s) => s.source);
  const fourView = useView((s) => s.fourView);
  const activeView = useView((s) => s.activeView);
  const mode = useView((s) => s.displayMode);
  const overlays = useView((s) => s.overlays);
  const measure = useView((s) => s.measure);
  const filter = useView((s) => s.selectionFilter);
  const savedViews = useView((s) => s.savedViews);
  const request = useView((s) => s.cameraRequest);
  const [menu, setMenu] = useState(false);
  const [focused, setFocused] = useState<ViewName>("perspective");

  // a "view" camera command switches the single viewport
  useEffect(() => {
    if (request.action === "view" && request.view) useView.getState().set({ activeView: request.view });
  }, [request]);

  const scene = pbSource !== "none" && pbScene ? pbScene : docScene;
  if (!scene) {
    return (
      <Empty title={sceneError ? "The design cannot be built" : "Loading the design..."}>
        {sceneError ?? "Waiting for the CALFLAB server."}
        {sceneError && <div className="mt-2">Open the Graph tab to see which node reports the error, or run ResetGraph.</div>}
      </Empty>
    );
  }
  const set = useView.getState().set;
  return (
    <div className="flex h-full flex-col" data-testid="viewport">
      <div className="flex h-7 shrink-0 items-center gap-1 border-b border-line bg-bg px-1">
        <select value={activeView} disabled={fourView} title="Named view" onChange={(e) => {
          const v = e.target.value;
          const saved = savedViews.find((s) => `saved:${s.name}` === v);
          if (saved) {
            set({ activeView: "perspective" });
            useView.getState().requestCamera("saved", { saved });
          } else set({ activeView: v as ViewName });
        }}>
          {VIEWS.map((v) => (
            <option key={v} value={v}>{v[0].toUpperCase() + v.slice(1)}</option>
          ))}
          {savedViews.map((s) => (
            <option key={s.name} value={`saved:${s.name}`}>{s.name}</option>
          ))}
        </select>
        <select value={mode} title="Display mode" onChange={(e) => set({ displayMode: e.target.value as DisplayMode })}>
          {MODES.map((m) => (
            <option key={m} value={m}>{m === "xray" ? "X-Ray" : m[0].toUpperCase() + m.slice(1)}</option>
          ))}
        </select>
        <IconButton title="Four viewports (FourView)" active={fourView} onClick={() => void execute("FourView")}>
          {fourView ? <Square size={14} /> : <Grid2x2 size={14} />}
        </IconButton>
        <div className="relative">
          <IconButton title="Overlays" active={menu} onClick={() => setMenu((m) => !m)}>
            <Layers size={14} />
          </IconButton>
          {menu && (
            <div className="absolute top-7 left-0 z-20 w-64 rounded border border-line bg-bg2 p-1 shadow-lg" onMouseLeave={() => setMenu(false)}>
              {OVERLAYS.map((o) => (
                <label key={o.key} className={clsx("flex items-center gap-2 px-1 py-0.5", !o.ready && "opacity-50")}>
                  <input type="checkbox" disabled={!o.ready} checked={Boolean(overlays[o.key])} onChange={() => useView.getState().toggleOverlay(o.key)} />
                  {o.label}
                </label>
              ))}
            </div>
          )}
        </div>
        <IconButton title="Measure distance (M)" active={measure} onClick={() => void execute("Measure")}>
          <Ruler size={14} />
        </IconButton>
        <IconButton title="Capture viewport to the journal" onClick={() => void execute("Capture")}>
          <Camera size={14} />
        </IconButton>
        <span className="mx-1 h-4 w-px bg-line" />
        <span className="text-dim">Select</span>
        <select value={filter} title="Selection filter" onChange={(e) => set({ selectionFilter: e.target.value as "body" | "geom" })}>
          <option value="body">Parts</option>
          <option value="geom">Geometry / components</option>
        </select>
        <div className="flex-1" />
        {pbSource !== "none" && (
          <button className="rounded bg-accent/20 px-2 text-accent hover:bg-accent/30" onClick={() => usePlayback.getState().clear()} title="Stop playback and return to the design pose">
            Playback · back to design
          </button>
        )}
      </div>
      <div className="relative min-h-0 flex-1">
        {fourView ? (
          <div className="grid h-full grid-cols-2 grid-rows-2 gap-px bg-line">
            {(["top", "perspective", "front", "right"] as ViewName[]).map((v) => (
              <View key={v} view={v} scene={scene} primary={focused === v} onActivate={() => setFocused(v)} />
            ))}
          </div>
        ) : (
          <View view={activeView} scene={scene} primary onActivate={() => undefined} />
        )}
        <GumballHud scene={scene} />
        {measure && (
          <div className="absolute top-2 right-2 rounded bg-black/70 px-2 py-1 text-yellow-300">
            Measure: click two points on the robot. Press M or Esc to finish.
          </div>
        )}
      </div>
    </div>
  );
}
