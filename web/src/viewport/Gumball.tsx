// Gumball: drag a handle on the selected part. The server tells us which
// parameter a handle drives and along which body axis (ParamValue.handle_axis);
// dragging writes an explicit override, or drives the gene when "bound" is on.
import { TransformControls } from "@react-three/drei";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { ParamValue, Scene } from "@/api/types";
import { useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";
import { useView } from "@/store/view";
import { snapValue } from "./viewLogic";

export interface GumballTarget {
  bodyId: string;
  param: string;
  pv: ParamValue;
  handles: string[];
}

/** The body/parameter the gumball acts on for the current selection, if any. */
export function gumballTarget(scene: Scene | null, selection: string[], preferred: string | null): GumballTarget | null {
  if (!scene || selection.length !== 1) return null;
  const el = scene.elements[selection[0]];
  if (!el || el.kind !== "body" || !el.params) return null;
  const handles = Object.entries(el.params)
    .filter(([, pv]) => pv.handle_axis)
    .map(([name]) => name);
  if (!handles.length) return null;
  const param = preferred && handles.includes(preferred) ? preferred : handles[0];
  return { bodyId: selection[0], param, pv: el.params[param], handles };
}

export function sendOverride(target: GumballTarget, value: number, final: boolean) {
  const lab = useLab.getState();
  const bound = useView.getState().gumballBound;
  void lab
    .run("add_override", { target: target.bodyId, param: target.param, value, bound, source: "web" })
    .catch(() => undefined)
    .finally(() => final && lab.endGesture());
}

export function Gumball({ scene, dragging }: { scene: Scene; dragging: React.MutableRefObject<boolean> }) {
  const selection = useView((s) => s.selection);
  const preferred = useView((s) => s.gumballParam);
  const snapGrid = useView((s) => s.snapGrid);
  const snapStep = useView((s) => s.snapStep);
  const playing = usePlayback((s) => s.source !== "none");
  const target = useMemo(() => gumballTarget(scene, selection, preferred), [scene, selection, preferred]);
  const handle = useRef<THREE.Object3D>(new THREE.Object3D());
  const start = useRef<{ pos: THREE.Vector3; value: number; axis: THREE.Vector3 } | null>(null);
  const lastSent = useRef(0);
  const pendingValue = useRef<number | null>(null);

  const body = target ? scene.bodies.find((b) => b.id === target.bodyId) : undefined;

  // place the handle at the parameter's handle position (unless the user is dragging it)
  useEffect(() => {
    if (!target || !body || dragging.current) return;
    const axis = new THREE.Vector3(...target.pv.handle_axis!);
    const q = new THREE.Quaternion(body.quat[1], body.quat[2], body.quat[3], body.quat[0]);
    const local = axis.clone().multiplyScalar(target.pv.value * target.pv.handle_frac);
    handle.current.position.set(...body.pos).add(local.applyQuaternion(q));
    handle.current.quaternion.copy(q);
    handle.current.updateMatrixWorld();
  }, [target, body, dragging]);

  if (!target || !body || playing) return null;
  const axis = target.pv.handle_axis!;

  const valueFromHandle = () => {
    const s = start.current;
    if (!s) return target.pv.value;
    const delta = handle.current.position.clone().sub(s.pos).dot(s.axis);
    let v = s.value + delta / (target.pv.handle_frac || 1);
    if (snapGrid) v = snapValue(v, snapStep);
    if (target.pv.min !== null) v = Math.max(target.pv.min, v);
    if (target.pv.max !== null) v = Math.min(target.pv.max, v);
    return v;
  };

  return (
    <>
      <primitive object={handle.current} />
      <TransformControls
        object={handle.current}
        mode="translate"
        space="local"
        size={0.7}
        showX={axis[0] !== 0}
        showY={axis[1] !== 0}
        showZ={axis[2] !== 0}
        onMouseDown={() => {
          dragging.current = true;
          const q = handle.current.quaternion;
          start.current = {
            pos: handle.current.position.clone(),
            value: target.pv.value,
            axis: new THREE.Vector3(...axis).applyQuaternion(q).normalize(),
          };
        }}
        onObjectChange={() => {
          const v = valueFromHandle();
          pendingValue.current = v;
          const now = performance.now();
          if (now - lastSent.current > 70) {
            lastSent.current = now;
            sendOverride(target, v, false);
          }
        }}
        onMouseUp={() => {
          const v = pendingValue.current ?? valueFromHandle();
          pendingValue.current = null;
          dragging.current = false;
          start.current = null;
          sendOverride(target, v, true);
        }}
      />
    </>
  );
}
