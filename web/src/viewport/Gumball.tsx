// Gumball: draggable arrows on the selected part. The server tells us which
// parameters have a handle and along which body axis (ParamValue.handle_axis);
// dragging writes an explicit override, or drives the gene when "bound" is on.
//
// The arrows are drawn here rather than with three's TransformControls: its
// one-pixel axis line starts at the handle and points back into the part, so
// on a leg segment it was hidden inside the highlighted tube.
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { BodyInfo, ParamValue, Scene } from "@/api/types";
import { useLab } from "@/store/lab";
import { usePlayback } from "@/store/playback";
import { useView } from "@/store/view";
import { axisParam, snapValue } from "./viewLogic";

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

export function sendOverride(target: Pick<GumballTarget, "bodyId" | "param">, value: number, final: boolean) {
  const lab = useLab.getState();
  const bound = useView.getState().gumballBound;
  void lab
    .run("add_override", { target: target.bodyId, param: target.param, value, bound, source: "web" })
    .catch(() => undefined)
    .finally(() => final && lab.endGesture());
}

const ARROW_PX = 84; // on-screen length of an arrow, whatever the zoom
const ORDER = 20; // drawn after everything else
const COLORS = { x: "#e05a52", y: "#57b97a", z: "#4f8fe0" };
const HOT = "#ffd54f";

function Arrow({
  body,
  param,
  pv,
  active,
  dragging,
}: {
  body: BodyInfo;
  param: string;
  pv: ParamValue;
  active: boolean;
  dragging: React.MutableRefObject<boolean>;
}) {
  const { camera, gl, size } = useThree();
  const group = useRef<THREE.Group>(null);
  const dragPos = useRef<THREE.Vector3 | null>(null);
  const [hot, setHot] = useState(false);
  const [held, setHeld] = useState(false);

  // where the handle sits and which way it points, in world coordinates
  const { base, dir, quat, color } = useMemo(() => {
    const axis = new THREE.Vector3(...pv.handle_axis!);
    const q = new THREE.Quaternion(body.quat[1], body.quat[2], body.quat[3], body.quat[0]);
    const dir = axis.clone().applyQuaternion(q).normalize();
    const base = new THREE.Vector3(...body.pos).add(dir.clone().multiplyScalar(pv.value * pv.handle_frac));
    const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), dir);
    const dominant = Math.abs(axis.x) > 0.7 ? "x" : Math.abs(axis.y) > 0.7 ? "y" : "z";
    return { base, dir, quat, color: COLORS[dominant] };
  }, [body, pv]);

  useFrame(() => {
    const g = group.current;
    if (!g) return;
    g.position.copy(dragPos.current ?? base);
    const ortho = camera as THREE.OrthographicCamera;
    const persp = camera as THREE.PerspectiveCamera;
    const unitsPerPx = ortho.isOrthographicCamera
      ? 1 / ortho.zoom
      : (2 * camera.position.distanceTo(g.position) * Math.tan(THREE.MathUtils.degToRad(persp.fov / 2))) / size.height;
    g.scale.setScalar(unitsPerPx * ARROW_PX);
    if (active) {
      // where the active arrow is on screen (canvas pixels: base x y, tip x y), for UI tests
      const px = (p: THREE.Vector3) => {
        const v = p.clone().project(camera);
        return `${Math.round(((v.x + 1) / 2) * size.width)} ${Math.round(((1 - v.y) / 2) * size.height)}`;
      };
      const where = `${param} ${px(g.position)} ${px(g.position.clone().add(dir.clone().multiplyScalar(g.scale.x)))}`;
      if (gl.domElement.dataset.gumball !== where) gl.domElement.dataset.gumball = where;
    }
  });
  useEffect(() => {
    const el = gl.domElement;
    return () => {
      delete el.dataset.gumball;
    };
  }, [gl]);

  const onDown = (e: ThreeEvent<PointerEvent>) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const origin = base.clone();
    const t0 = axisParam(e.ray.origin.toArray(), e.ray.direction.toArray(), origin.toArray(), dir.toArray());
    if (t0 === null) return; // looking straight down the axis: nothing to drag along
    dragging.current = true;
    setHeld(true);
    useView.getState().set({ gumballParam: param, gumballLive: pv.value });
    const target = { bodyId: body.id, param };
    const startValue = pv.value;
    const frac = pv.handle_frac || 1;
    const ray = new THREE.Raycaster();
    let value = startValue;
    let lastSent = 0;

    const move = (ev: PointerEvent) => {
      const r = gl.domElement.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1), camera);
      const t = axisParam(ray.ray.origin.toArray(), ray.ray.direction.toArray(), origin.toArray(), dir.toArray());
      if (t === null) return;
      let v = startValue + (t - t0) / frac;
      const { snapGrid, snapStep } = useView.getState();
      if (snapGrid) v = snapValue(v, snapStep);
      if (pv.min !== null) v = Math.max(pv.min, v);
      if (pv.max !== null) v = Math.min(pv.max, v);
      if (v === value) return;
      value = v;
      dragPos.current = origin.clone().add(dir.clone().multiplyScalar((v - startValue) * frac));
      useView.getState().set({ gumballLive: v });
      const now = performance.now();
      if (now - lastSent > 70) {
        lastSent = now;
        sendOverride(target, v, false);
      }
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      if (value !== startValue) sendOverride(target, value, true);
      setHeld(false);
      // keep the arrow where it was dropped until the scene with the new value arrives
      setTimeout(() => {
        dragging.current = false;
        dragPos.current = null;
        useView.getState().set({ gumballLive: null });
      }, 150);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };

  const shown = hot || held ? HOT : color;
  const opacity = active || hot || held ? 1 : 0.55;
  return (
    <group ref={group} quaternion={quat}>
      {/* shaft and head, one unit long along +Z; the group is scaled to ARROW_PX */}
      <mesh position={[0, 0, 0.36]} rotation={[Math.PI / 2, 0, 0]} renderOrder={ORDER}>
        <cylinderGeometry args={[0.03, 0.03, 0.72, 12]} />
        <meshBasicMaterial color={shown} depthTest={false} transparent opacity={opacity} />
      </mesh>
      <mesh position={[0, 0, 0.86]} rotation={[Math.PI / 2, 0, 0]} renderOrder={ORDER}>
        <coneGeometry args={[0.11, 0.28, 20]} />
        <meshBasicMaterial color={shown} depthTest={false} transparent opacity={opacity} />
      </mesh>
      <mesh renderOrder={ORDER}>
        <sphereGeometry args={[0.07, 16, 12]} />
        <meshBasicMaterial color={shown} depthTest={false} transparent opacity={opacity} />
      </mesh>
      {/* a fatter invisible grip so the arrow is easy to catch */}
      <mesh
        position={[0, 0, 0.5]}
        rotation={[Math.PI / 2, 0, 0]}
        userData={{ gumball: param }}
        onPointerDown={onDown}
        onClick={(e) => e.stopPropagation()}
        onPointerOver={(e) => {
          e.stopPropagation();
          setHot(true);
        }}
        onPointerOut={() => setHot(false)}
      >
        <cylinderGeometry args={[0.17, 0.17, 1.1, 10]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} depthTest={false} />
      </mesh>
    </group>
  );
}

export function Gumball({ scene, dragging }: { scene: Scene; dragging: React.MutableRefObject<boolean> }) {
  const selection = useView((s) => s.selection);
  const preferred = useView((s) => s.gumballParam);
  const playing = usePlayback((s) => s.source !== "none");
  const target = useMemo(() => gumballTarget(scene, selection, preferred), [scene, selection, preferred]);
  const body = target ? scene.bodies.find((b) => b.id === target.bodyId) : undefined;
  const el = target ? scene.elements[target.bodyId] : undefined;

  // a selection change must never leave a stale live value in the HUD
  useEffect(() => {
    useView.getState().set({ gumballLive: null });
  }, [target?.bodyId]);

  if (!target || !body || !el?.params || playing) return null;
  return (
    <>
      {target.handles.map((name) => (
        <Arrow key={`${body.id}.${name}`} body={body} param={name} pv={el.params![name]} active={name === target.param} dragging={dragging} />
      ))}
    </>
  );
}
