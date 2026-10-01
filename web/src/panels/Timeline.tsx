// Timeline: playback transport, scrubbing, and a metric plot whose cursor is
// synced to the viewport frame.
import { AxisBottom, AxisLeft } from "@visx/axis";
import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { LinePath } from "@visx/shape";
import { Pause, Play, SkipBack, Square } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { execute } from "@/commands/registry";
import { Button, Empty, IconButton } from "@/components/ui";
import { usePlayback } from "@/store/playback";

const COLORS = ["#e0823d", "#4fa3d4", "#57b97a", "#ba68c8", "#ffd54f", "#f06292"];

/** Advances playback in real time. Mounted once by the shell. */
export function usePlaybackClock() {
  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      const s = usePlayback.getState();
      if (s.playing && s.t.length > 1) {
        const frameDt = Math.max(1e-3, (s.t[s.t.length - 1] - s.t[0]) / (s.t.length - 1));
        let f = s.frame + (dt * s.speed) / frameDt;
        if (f >= s.t.length - 1) {
          if (s.source === "live") f = s.t.length - 1; // wait for more frames
          else if (s.loop) f = 0;
          else {
            f = s.t.length - 1;
            usePlayback.setState({ playing: false });
          }
        }
        usePlayback.setState({ frame: f });
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
}

function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ w: 600, h: 120 });
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

function Plot({ channels }: { channels: string[] }) {
  const t = usePlayback((s) => s.t);
  const series = usePlayback((s) => s.series);
  const frame = usePlayback((s) => Math.round(s.frame));
  const [ref, { w, h }] = useSize<HTMLDivElement>();
  const m = { l: 44, r: 10, t: 6, b: 20 };
  const iw = Math.max(10, w - m.l - m.r);
  const ih = Math.max(10, h - m.t - m.b);
  const active = channels.filter((c) => series[c]);
  const { x, y } = useMemo(() => {
    let lo = Infinity, hi = -Infinity;
    for (const c of active) for (const v of series[c].values) { if (v < lo) lo = v; if (v > hi) hi = v; }
    if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
    if (lo === hi) { lo -= 0.5; hi += 0.5; }
    const pad = (hi - lo) * 0.06;
    return {
      x: scaleLinear({ domain: [t[0] ?? 0, t[t.length - 1] ?? 1], range: [0, iw] }),
      y: scaleLinear({ domain: [lo - pad, hi + pad], range: [ih, 0] }),
    };
  }, [active, series, t, iw, ih]);
  const scrub = (e: React.PointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    usePlayback.getState().setFrame(frac * (t.length - 1));
  };
  const cursorT = t[Math.min(frame, t.length - 1)] ?? 0;
  return (
    <div ref={ref} className="h-full min-h-0 w-full" data-testid="metric-plot">
      <svg width={w} height={h}>
        <Group left={m.l} top={m.t}>
          <AxisLeft scale={y} numTicks={4} stroke="var(--line)" tickStroke="var(--line)" tickLabelProps={{ fill: "var(--fg-dim)", fontSize: 9 }} />
          <AxisBottom scale={x} top={ih} numTicks={8} stroke="var(--line)" tickStroke="var(--line)" tickLabelProps={{ fill: "var(--fg-dim)", fontSize: 9 }} />
          {active.map((c, i) => (
            <LinePath
              key={c}
              data={series[c].values.map((v, k) => [t[k], v] as [number, number])}
              x={(d) => x(d[0])}
              y={(d) => y(d[1])}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={1.3}
            />
          ))}
          <line x1={x(cursorT)} x2={x(cursorT)} y1={0} y2={ih} stroke="var(--fg)" strokeWidth={1} />
          <rect
            width={iw}
            height={ih}
            fill="transparent"
            style={{ cursor: "ew-resize" }}
            onPointerDown={(e) => {
              e.currentTarget.setPointerCapture(e.pointerId);
              usePlayback.getState().set({ playing: false });
              scrub(e);
            }}
            onPointerMove={(e) => e.buttons === 1 && scrub(e)}
          />
        </Group>
      </svg>
    </div>
  );
}

export function TimelinePanel() {
  const n = usePlayback((s) => s.t.length);
  const t = usePlayback((s) => s.t);
  const frame = usePlayback((s) => Math.round(s.frame));
  const playing = usePlayback((s) => s.playing);
  const speed = usePlayback((s) => s.speed);
  const loop = usePlayback((s) => s.loop);
  const runId = usePlayback((s) => s.runId);
  const source = usePlayback((s) => s.source);
  const series = usePlayback((s) => s.series);
  const [channels, setChannels] = useState<string[]>(["speed", "pitch"]);
  const pb = usePlayback.getState();
  const groups = useMemo(() => {
    const g: Record<string, string[]> = {};
    for (const [k, c] of Object.entries(series)) (g[c.group] ??= []).push(k);
    return g;
  }, [series]);

  if (!n) {
    return (
      <Empty title="Timeline" action={<Button variant="primary" onClick={() => void execute("RunSim")}>Simulate (F5)</Button>}>
        Run a simulation to scrub through it here. Body poses are streamed (not video), so display modes and overlays keep
        working during playback.
      </Empty>
    );
  }
  const i = Math.min(frame, n - 1);
  return (
    <div className="flex h-full flex-col" data-testid="timeline">
      <div className="flex h-7 shrink-0 items-center gap-1 border-b border-line bg-bg px-1">
        <IconButton title="Back to start" onClick={() => pb.setFrame(0)}><SkipBack size={13} /></IconButton>
        <IconButton title="Play / pause (K)" onClick={() => pb.toggle()} data-testid="play">
          {playing ? <Pause size={13} /> : <Play size={13} />}
        </IconButton>
        <IconButton title="Stop and return to the design pose" onClick={() => pb.clear()}><Square size={12} /></IconButton>
        <input
          type="range"
          className="min-w-0 flex-1"
          min={0}
          max={n - 1}
          step={1}
          value={i}
          data-testid="scrubber"
          onChange={(e) => {
            pb.set({ playing: false });
            pb.setFrame(Number(e.target.value));
          }}
        />
        <span className="w-28 text-right font-mono text-[11px]" data-testid="frame-readout">
          {(t[i] ?? 0).toFixed(2)} s · {i + 1}/{n}
        </span>
        <select value={speed} title="Playback speed" onChange={(e) => pb.set({ speed: Number(e.target.value) })}>
          {[0.1, 0.25, 0.5, 1, 2].map((s) => <option key={s} value={s}>{s}x</option>)}
        </select>
        <label className="flex items-center gap-1 text-dim"><input type="checkbox" checked={loop} onChange={(e) => pb.set({ loop: e.target.checked })} />loop</label>
        <span className="w-48 truncate text-right font-mono text-[10px] text-dim" title={runId ?? ""}>{source === "live" ? "live stream" : runId}</span>
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="w-44 shrink-0 overflow-auto border-r border-line p-1">
          {Object.keys(groups).length === 0 && <div className="text-dim">Metrics appear when the run finishes.</div>}
          {Object.entries(groups).map(([g, keys]) => (
            <details key={g} open={g === "Body"}>
              <summary className="cursor-pointer text-[10px] font-semibold text-dim uppercase">{g}</summary>
              {keys.map((k) => {
                const on = channels.includes(k);
                const color = on ? COLORS[channels.filter((c) => series[c]).indexOf(k) % COLORS.length] : undefined;
                return (
                  <label key={k} className="flex items-center gap-1 truncate" title={`${series[k].label} (${series[k].unit})`}>
                    <input type="checkbox" checked={on} onChange={() => setChannels((c) => (on ? c.filter((x) => x !== k) : [...c, k]))} />
                    <span style={{ color }}>{series[k].label.replace("Torque act.", "").replace("Temperature act.", "").replace("Foot force leg.", "")}</span>
                  </label>
                );
              })}
            </details>
          ))}
        </div>
        <div className="min-w-0 flex-1"><Plot channels={channels} /></div>
      </div>
    </div>
  );
}
